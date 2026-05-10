import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { apiUrl, getApiKey, getAuthHeaders } from '@/lib/api';

export interface Message {
  id: string;
  sender: 'user' | 'aria';
  text: string;
  status: 'done' | 'streaming' | 'error';
  attachments?: string[];
  errorKind?: 'model_error' | 'network_error';
}

export interface MonologueEntry {
  id: string;
  time: string;
  text: string;
}

export interface SessionMeta {
  id: string;
  started_at: string;
  turn_count: number;
  topics: string[];
}

export interface ActivityEntry {
  id: string;
  time: string;
  title: string;
  detail: string;
  tone: 'system' | 'thinking' | 'response' | 'error';
}

export interface AriaTelemetry {
  phase: 'offline' | 'idle' | 'thinking' | 'responding' | 'error';
  statusLabel: string;
  connectionLabel: string;
  liveThought: string;
  activeSessionId: string | null;
  monologueCount: number;
  userTurns: number;
  ariaResponses: number;
  busySeconds: number;
  lastEventTime: string | null;
  lastError: string | null;
}

type IncomingWsMessage = {
  type?: string;
  text?: string;
  error_kind?: 'model_error' | 'network_error';
  confidence?: number;
  graph_nodes_added?: number;
  goals_updated?: number;
};

type LoadedTurn = {
  id: string;
  user_input: string;
  response: string;
};

const WS_RECONNECT_BASE_MS = 1800;
const WS_MAX_RETRIES = 12;

export function useAriaSocket(url: string, enabled = true) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [monologue, setMonologue] = useState<MonologueEntry[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [currentThought, setCurrentThought] = useState("");
  const [metrics, setMetrics] = useState({ confidence: 0, nodesAdded: 0, goalsUpdated: 0 });
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [activityFeed, setActivityFeed] = useState<ActivityEntry[]>([]);
  const [busyStartedAt, setBusyStartedAt] = useState<number | null>(null);
  const [busySeconds, setBusySeconds] = useState(0);
  const [lastEventTime, setLastEventTime] = useState<string | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  /** True only after the server has accepted the WebSocket auth handshake. */
  const linkReadyRef = useRef(false);
  /** User prompt waiting for link + auth before `send` runs (text-only; attachments cannot be queued). */
  const pendingSendRef = useRef<{ text: string } | null>(null);
  const streamingMsgIdRef = useRef<string | null>(null);
  const retriesRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeSessionIdRef = useRef<string | null>(null);

  const pushActivity = useCallback((entry: Omit<ActivityEntry, 'id' | 'time'>) => {
    const now = new Date();
    const time = now.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });

    setLastEventTime(time);
    setActivityFeed((prev) => [
      {
        id: `${now.getTime()}-${Math.random().toString(36).slice(2, 8)}`,
        time,
        ...entry
      },
      ...prev
    ].slice(0, 18));
  }, []);

  // ----- Session fetching -----
  const fetchSessions = useCallback(async () => {
    if (!enabled) return;
    try {
      const res = await fetch(apiUrl('/api/sessions'), { headers: getAuthHeaders() });
      if (res.ok) setSessions(await res.json());
    } catch (e) {
      console.error("Failed to fetch sessions", e);
    }
  }, [enabled]);

  useEffect(() => {
    if (!enabled) return;
    const timer = setTimeout(() => void fetchSessions(), 0);
    return () => clearTimeout(timer);
  }, [enabled, fetchSessions]);

  useEffect(() => {
    if (!busyStartedAt || (!isThinking && !isStreaming)) {
      setBusySeconds(0);
      return;
    }

    const updateElapsed = () => {
      setBusySeconds(Math.max(1, Math.floor((Date.now() - busyStartedAt) / 1000)));
    };

    updateElapsed();
    const interval = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(interval);
  }, [busyStartedAt, isThinking, isStreaming]);

  useEffect(() => {
    activeSessionIdRef.current = activeSessionId;
  }, [activeSessionId]);

  const flushPendingSend = useCallback(() => {
    const pending = pendingSendRef.current;
    if (!pending || !linkReadyRef.current) return;
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    pendingSendRef.current = null;
    setLastError(null);
    const { text } = pending;
    setCurrentThought('Thinking...');
    setBusyStartedAt(Date.now());
    pushActivity({
      tone: 'thinking',
      title: 'Sending queued prompt',
      detail: text.trim() ? text.slice(0, 160) : 'Queued message',
    });
    wsRef.current.send(JSON.stringify({ text, session_id: activeSessionIdRef.current }));
  }, [pushActivity]);

  // ----- WebSocket with auto-reconnect -----
  const connectWs = useCallback(function connectWs() {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ type: 'auth', api_key: getApiKey() }));
    };

    ws.onmessage = (event) => {
      let data: IncomingWsMessage;
      try {
        data = JSON.parse(event.data);
      } catch {
        console.warn("Ignoring non-JSON WebSocket message");
        return;
      }

      switch (data.type) {
        case 'auth_ok': {
          linkReadyRef.current = true;
          setIsConnected(true);
          retriesRef.current = 0;
          setLastError(null);
          pushActivity({
            tone: 'system',
            title: 'Live link established',
            detail: 'ARIA is connected and ready for new prompts.'
          });
          flushPendingSend();
          break;
        }

        case 'monologue': {
          const entry: MonologueEntry = {
            id: Date.now().toString() + Math.random(),
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            text: data.text ?? ''
          };
          setMonologue(prev => [...prev, entry]);
          setCurrentThought(data.text ?? '');
          break;
        }

        case 'response_start': {
          setIsThinking(false);
          setIsStreaming(true);
          setCurrentThought("");
          setBusyStartedAt((current) => current ?? Date.now());
          setLastError(null);
          const msgId = 'aria-' + Date.now();
          streamingMsgIdRef.current = msgId;
          setMessages(prev => [...prev, {
            id: msgId,
            sender: 'aria',
            text: '',
            status: 'streaming'
          }]);
          pushActivity({
            tone: 'response',
            title: 'Response stream started',
            detail: 'ARIA has moved from reasoning into answer delivery.'
          });
          break;
        }

        case 'response_chunk': {
          const id = streamingMsgIdRef.current;
          if (!id) break;
          setMessages(prev => prev.map(m =>
            m.id === id ? { ...m, text: m.text + (data.text ?? '') } : m
          ));
          break;
        }

        case 'response_done': {
          const id = streamingMsgIdRef.current;
          if (id) {
            setMessages(prev => prev.map(m =>
              m.id === id ? { ...m, status: 'done' } : m
            ));
          }
          streamingMsgIdRef.current = null;
          setIsStreaming(false);
          setBusyStartedAt(null);
          setBusySeconds(0);
          setLastError(null);
          setMetrics({
            confidence: data.confidence ?? 0,
            nodesAdded: data.graph_nodes_added ?? 0,
            goalsUpdated: data.goals_updated ?? 0
          });
          pushActivity({
            tone: 'response',
            title: 'Response completed',
            detail: `Confidence ${data.confidence ?? 0}% · Nodes +${data.graph_nodes_added ?? 0} · Goals ${data.goals_updated ?? 0}`
          });
          fetchSessions();
          break;
        }

        case 'error': {
          const id = streamingMsgIdRef.current;
          if (id) {
            setMessages(prev => prev.map(m =>
              m.id === id ? { ...m, status: 'error', errorKind: data.error_kind } : m
            ));
          } else {
            setMessages(prev => [...prev, {
              id: 'err-' + Date.now(),
              sender: 'aria',
              text: data.text ?? '',
              status: 'error',
              errorKind: data.error_kind
            }]);
          }
          streamingMsgIdRef.current = null;
          setIsThinking(false);
          setIsStreaming(false);
          setBusyStartedAt(null);
          setBusySeconds(0);
          setLastError(data.text ?? 'An error interrupted the current run.');
          pushActivity({
            tone: 'error',
            title: 'Run interrupted',
            detail: data.text ?? 'An error interrupted the current run.'
          });
          break;
        }

        // Legacy fallback
        case 'response': {
          setIsThinking(false);
          setIsStreaming(false);
          setBusyStartedAt(null);
          setBusySeconds(0);
          setLastError(null);
          setMessages(prev => [...prev, { id: Date.now().toString(), sender: 'aria', text: data.text ?? '', status: 'done' }]);
          setMetrics({
            confidence: data.confidence ?? 0,
            nodesAdded: data.graph_nodes_added ?? 0,
            goalsUpdated: data.goals_updated ?? 0
          });
          pushActivity({
            tone: 'response',
            title: 'Response completed',
            detail: `Confidence ${data.confidence ?? 0}% · Nodes +${data.graph_nodes_added ?? 0} · Goals ${data.goals_updated ?? 0}`
          });
          break;
        }
      }
    };

    ws.onerror = () => {
      const id = streamingMsgIdRef.current;
      if (id) {
        setMessages(prev => prev.map(m =>
          m.id === id ? { ...m, status: 'error', errorKind: 'network_error' } : m
        ));
        streamingMsgIdRef.current = null;
      }
      setIsThinking(false);
      setIsStreaming(false);
      setBusyStartedAt(null);
      setBusySeconds(0);
      setLastError('Network error — connection lost.');
    };

    ws.onclose = () => {
      linkReadyRef.current = false;
      setIsConnected(false);
      pushActivity({
        tone: 'error',
        title: 'Live link lost',
        detail: retriesRef.current < WS_MAX_RETRIES
          ? 'Attempting to reconnect to ARIA.'
          : 'The connection has stopped retrying.'
      });
      // Auto-reconnect with capped exponential backoff
      if (retriesRef.current < WS_MAX_RETRIES) {
        retriesRef.current += 1;
        const delayMs = Math.min(
          28000,
          Math.round(WS_RECONNECT_BASE_MS * Math.pow(1.45, retriesRef.current - 1))
        );
        reconnectTimerRef.current = setTimeout(() => {
          connectWs();
        }, delayMs);
      } else {
        setLastError('Could not reconnect — refresh the page or confirm `aria web` is running.');
      }
    };
  }, [url, fetchSessions, pushActivity, flushPendingSend]);

  useEffect(() => {
    if (!enabled) {
      linkReadyRef.current = false;
      setIsConnected(false);
      return;
    }
    connectWs();
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
    };
  }, [connectWs, enabled]);

  // ----- Send message -----
  const sendMessage = useCallback(async (text: string, files?: File[]) => {
    const hasFiles = Boolean(files && files.length > 0);
    if (!linkReadyRef.current || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      if (hasFiles) {
        setLastError('Wait until the live link shows “WebSocket live” before sending images.');
        return;
      }
      pendingSendRef.current = { text };
      setMessages(prev => [...prev, {
        id: 'user-' + Date.now(),
        sender: 'user',
        text,
        status: 'done',
      }]);
      setIsThinking(true);
      setCurrentThought('Queued — waiting for a live link…');
      setBusyStartedAt(Date.now());
      setLastError('Message queued — will send automatically when the connection is ready.');
      pushActivity({
        tone: 'system',
        title: 'Prompt queued',
        detail: 'ARIA is reconnecting; your text will send after the link is authenticated.'
      });
      return;
    }

    const fileUrls = files ? files.map(f => URL.createObjectURL(f)) : [];
    setMessages(prev => [...prev, {
      id: 'user-' + Date.now(),
      sender: 'user',
      text,
      status: 'done',
      attachments: fileUrls.length > 0 ? fileUrls : undefined
    }]);
    setIsThinking(true);
    setCurrentThought("Thinking...");
    setBusyStartedAt(Date.now());
    setLastError(null);
    pushActivity({
      tone: 'thinking',
      title: files && files.length > 0 ? 'Prompt submitted with files' : 'Prompt submitted',
      detail: text.trim() || `${files?.length ?? 0} file attachment(s) sent to ARIA.`
    });

    if (!files || files.length === 0) {
      wsRef.current.send(JSON.stringify({ text, session_id: activeSessionId }));
      return;
    }

    const base64Files = await Promise.all(files.map(file => {
      return new Promise<{mime: string, data: string}>((resolve) => {
        const reader = new FileReader();
        reader.onload = (e) => {
          const result = e.target?.result as string;
          const base64Data = result.split(',')[1];
          resolve({ mime: file.type, data: base64Data });
        };
        reader.readAsDataURL(file);
      });
    }));

    wsRef.current.send(JSON.stringify({ text, images: base64Files, session_id: activeSessionId }));
  }, [activeSessionId, pushActivity]);

  const stopGeneration = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ text: "__STOP__", session_id: activeSessionId }));
    }
    const id = streamingMsgIdRef.current;
    if (id) {
      setMessages(prev => prev.map(m =>
        m.id === id ? { ...m, status: 'done' } : m
      ));
      streamingMsgIdRef.current = null;
    }
    setIsThinking(false);
    setIsStreaming(false);
    setBusyStartedAt(null);
    setBusySeconds(0);
    pushActivity({
      tone: 'system',
      title: 'Generation stopped',
      detail: 'The current response was halted by the operator.'
    });
  }, [activeSessionId, pushActivity]);

  // ----- Regenerate last response -----
  const regenerate = useCallback(() => {
    if (!linkReadyRef.current || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setLastError('Not connected — wait for “WebSocket live” or refresh the page.');
      return;
    }
    const lastUserMsg = [...messages].reverse().find(m => m.sender === 'user');
    if (!lastUserMsg) return;
    setMessages(prev => {
      const copy = [...prev];
      const lastAriaIdx = copy.map(m => m.sender).lastIndexOf('aria');
      if (lastAriaIdx !== -1) copy.splice(lastAriaIdx, 1);
      return copy;
    });
    setIsThinking(true);
    setCurrentThought("Regenerating...");
    setBusyStartedAt(Date.now());
    setLastError(null);
    pushActivity({
      tone: 'thinking',
      title: 'Regeneration requested',
      detail: 'ARIA is producing a fresh version of the last response.'
    });
    wsRef.current.send(JSON.stringify({ text: lastUserMsg.text, session_id: activeSessionId }));
  }, [messages, activeSessionId, pushActivity]);

  // ----- Edit & resend -----
  const editAndResend = useCallback((messageId: string, newText: string) => {
    if (!linkReadyRef.current || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setLastError('Not connected — wait for “WebSocket live” or refresh the page.');
      return;
    }
    setMessages(prev => {
      const idx = prev.findIndex(m => m.id === messageId);
      if (idx === -1) return prev;
      const truncated = prev.slice(0, idx);
      truncated.push({ ...prev[idx], text: newText });
      return truncated;
    });
    setIsThinking(true);
    setCurrentThought("Thinking...");
    setBusyStartedAt(Date.now());
    setLastError(null);
    pushActivity({
      tone: 'thinking',
      title: 'Edited prompt resent',
      detail: newText
    });
    wsRef.current.send(JSON.stringify({ text: newText, session_id: activeSessionId }));
  }, [activeSessionId, pushActivity]);

  // ----- Retry errored -----
  const retryLast = useCallback(() => {
    if (!linkReadyRef.current || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setLastError('Not connected — wait for “WebSocket live” or refresh the page.');
      return;
    }
    const lastUserMsg = [...messages].reverse().find(m => m.sender === 'user');
    if (!lastUserMsg) return;
    setMessages(prev => {
      const copy = [...prev];
      const lastAriaIdx = copy.map(m => m.sender).lastIndexOf('aria');
      if (lastAriaIdx !== -1 && copy[lastAriaIdx].status === 'error') {
        copy.splice(lastAriaIdx, 1);
      }
      return copy;
    });
    setIsThinking(true);
    setCurrentThought("Retrying...");
    setBusyStartedAt(Date.now());
    setLastError(null);
    pushActivity({
      tone: 'thinking',
      title: 'Retry requested',
      detail: 'ARIA is retrying the last failed response.'
    });
    wsRef.current.send(JSON.stringify({ text: lastUserMsg.text, session_id: activeSessionId }));
  }, [messages, activeSessionId, pushActivity]);

  // ----- Load past session -----
  const loadSession = useCallback(async (sessionId: string) => {
    try {
      const res = await fetch(apiUrl(`/api/sessions/${sessionId}`), { headers: getAuthHeaders() });
      if (res.ok) {
        const turns = await res.json();
        const loadedMessages: Message[] = [];
        turns.forEach((t: LoadedTurn) => {
          loadedMessages.push({ id: t.id + '-u', sender: 'user', text: t.user_input, status: 'done' });
          loadedMessages.push({ id: t.id + '-a', sender: 'aria', text: t.response, status: 'done' });
        });
        setMessages(loadedMessages);
        setMonologue([]);
        setActiveSessionId(sessionId);
        setCurrentThought("");
        setBusyStartedAt(null);
        setBusySeconds(0);
        setLastError(null);
        pushActivity({
          tone: 'system',
          title: 'Session loaded',
          detail: `Loaded ${turns.length} turn(s) from session ${sessionId.slice(0, 8)}.`
        });
      }
    } catch (e) {
      console.error("Failed to load session", e);
    }
  }, [pushActivity]);

  // ----- New session -----
  const createNewSession = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/sessions/new'), {
        method: "POST",
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        setMessages([]);
        setMonologue([]);
        setActiveSessionId(data.id);
        setCurrentThought("");
        setLastError(null);
        setBusyStartedAt(null);
        setBusySeconds(0);
        pushActivity({
          tone: 'system',
          title: 'New session created',
          detail: `Session ${data.id.slice(0, 8)} is ready for a new run.`
        });
        fetchSessions();
      }
    } catch (e) {
      console.error("Failed to create new session", e);
    }
  }, [fetchSessions, pushActivity]);

  const userTurns = useMemo(
    () => messages.filter((message) => message.sender === 'user').length,
    [messages]
  );

  const ariaResponses = useMemo(
    () => messages.filter((message) => message.sender === 'aria').length,
    [messages]
  );

  const telemetry = useMemo<AriaTelemetry>(() => {
    const phase: AriaTelemetry['phase'] =
      !isConnected ? 'offline'
      : lastError ? 'error'
      : isStreaming ? 'responding'
      : isThinking ? 'thinking'
      : 'idle';

    const statusLabel =
      phase === 'offline' ? 'Link offline'
      : phase === 'error' ? 'Needs attention'
      : phase === 'responding' ? 'Delivering answer'
      : phase === 'thinking' ? 'Reasoning'
      : 'Standing by';

    return {
      phase,
      statusLabel,
      connectionLabel: isConnected ? 'WebSocket live' : 'Reconnecting',
      liveThought: currentThought,
      activeSessionId,
      monologueCount: monologue.length,
      userTurns,
      ariaResponses,
      busySeconds,
      lastEventTime,
      lastError,
    };
  }, [
    activeSessionId,
    ariaResponses,
    busySeconds,
    currentThought,
    isConnected,
    isStreaming,
    isThinking,
    lastError,
    lastEventTime,
    monologue.length,
    userTurns,
  ]);

  return {
    messages, monologue, isThinking, isStreaming, isConnected, currentThought,
    metrics, sessions, activeSessionId, activityFeed, telemetry,
    sendMessage, stopGeneration, regenerate, editAndResend, retryLast,
    loadSession, createNewSession
  };
}
