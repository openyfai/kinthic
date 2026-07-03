"use client";

import { useState, useRef, useEffect } from "react";
import { SentIcon, ComputerTerminal01Icon, StopIcon, CheckmarkCircle01Icon, Cancel01Icon, Attachment01Icon, NeuralNetworkIcon } from "hugeicons-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { atomDark } from "react-syntax-highlighter/dist/cjs/styles/prism";
import TextareaAutosize from "react-textarea-autosize";

type Turn = {
  id: string;
  role: "user" | "kronos";
  content: string;
  thinking?: string;
  processSteps?: { id: string; type: string; content: string; timestamp: number }[];
  toolCalls?: { id: string; name: string; args: any; result?: string }[];
  approval?: { approval_id: string; tool_name: string; risk_level: string; reason: string; arguments_preview: any; resolved?: boolean };
  cost?: { total_cost_usd: number; total_tokens: number; turns: number; model: string };
  error?: string;
  cancelled?: boolean;
};

export default function TerminalOutput() {
  const [history, setHistory] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [currentRequestId, setCurrentRequestId] = useState<string | null>(null);
  
  // Command History
  const [commandHistory, setCommandHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);

  // Attachments
  const [attachments, setAttachments] = useState<{file: File, url: string, base64?: string}[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const chatContainerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll logic
  useEffect(() => {
    if (chatContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = chatContainerRef.current;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 150;
      if (isNearBottom) {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      }
    }
  }, [history]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    files.forEach(file => {
      const reader = new FileReader();
      reader.onload = (ev) => {
        setAttachments(prev => [...prev, {
          file,
          url: URL.createObjectURL(file),
          base64: ev.target?.result as string
        }]);
      };
      reader.readAsDataURL(file);
    });
    if (e.target) e.target.value = '';
  };

  const handleEvent = (turnId: string, event: any) => {
    setHistory(prev => prev.map(turn => {
      if (turn.id !== "kronos-" + turnId) return turn;
      
      const updated = { ...turn };
      
      switch (event.type) {
        case "thinking":
        case "routing":
        case "context":
          const text = event.data?.status || event.data?.detail || event.type;
          updated.thinking = text;
          updated.processSteps = [...(updated.processSteps || []), {
            id: Date.now().toString() + Math.random().toString(),
            type: event.type,
            content: text,
            timestamp: Date.now()
          }];
          break;
        case "tool_call":
          updated.toolCalls = [...(updated.toolCalls || []), {
            id: event.data?.tool_call_id || Date.now().toString(),
            name: event.data?.name,
            args: event.data?.arguments
          }];
          updated.thinking = `Running tool: ${event.data?.name}...`;
          break;
        case "tool_result":
          // Update the last tool call that doesn't have a result
          if (updated.toolCalls && updated.toolCalls.length > 0) {
              const reversed = [...updated.toolCalls].reverse();
              const target = reversed.find(tc => !tc.result);
              if (target) {
                  target.result = event.data?.result || "Success";
                  updated.toolCalls = reversed.reverse();
              }
          }
          updated.thinking = undefined;
          break;
        case "response":
          updated.content += (event.data?.text || "");
          updated.thinking = undefined;
          break;
        case "approval_requested":
          updated.approval = event.data;
          updated.thinking = "Awaiting user approval...";
          break;
        case "approval_resolved":
          if (updated.approval && updated.approval.approval_id === event.data?.approval_id) {
            updated.approval.resolved = true;
          }
          updated.thinking = undefined;
          break;
        case "cost_update":
          updated.cost = event.data;
          break;
        case "error":
          updated.error = event.data?.message;
          updated.thinking = undefined;
          break;
        case "cancel":
          updated.cancelled = true;
          updated.thinking = undefined;
          break;
        case "done":
          updated.thinking = undefined;
          break;
      }
      return updated;
    }));
  };

  const handleSend = async () => {
    const cmd = input.trim();
    if ((!cmd && attachments.length === 0) || loading) return;

    // Slash commands
    if (cmd === "/clear") {
      setHistory([]);
      setInput("");
      return;
    }
    
    if (cmd === "/pause" && currentRequestId) {
      handlePause();
      setInput("");
      return;
    }

    if (cmd) {
      setCommandHistory(prev => [...prev, cmd]);
    }
    setHistoryIndex(-1);
    setInput("");

    // Force scroll to bottom on user send
    setTimeout(() => {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, 50);

    const turnId = Date.now().toString();
    setHistory(prev => [
      ...prev, 
      { id: "user-" + turnId, role: "user", content: cmd },
      { id: "kronos-" + turnId, role: "kronos", content: "", toolCalls: [] }
    ]);
    
    setLoading(true);

    const imagesPayload = attachments.map(a => ({
      data: a.base64?.split(",")[1] || "",
      mime_type: a.file.type
    }));
    setAttachments([]);

    try {
      const res = await fetch("http://localhost:8000/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: cmd, images: imagesPayload.length > 0 ? imagesPayload : undefined }),
      });

      const reqId = res.headers.get("X-Request-Id");
      if (reqId) setCurrentRequestId(reqId);

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();

      if (reader) {
        let done = false;
        let buffer = "";
        while (!done) {
          const { value, done: doneReading } = await reader.read();
          done = doneReading;
          if (value) {
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\\n");
            buffer = lines.pop() || "";

            for (const line of lines) {
              if (!line.trim()) continue;
              try {
                const event = JSON.parse(line);
                handleEvent(turnId, event);
              } catch (e) {
                console.error("Failed to parse event line:", line);
              }
            }
          }
        }
      }
    } catch (err) {
      setHistory(prev => prev.map(t => t.id === "kronos-" + turnId ? { ...t, error: `Connection Error: ${err}` } : t));
    } finally {
      setLoading(false);
      setCurrentRequestId(null);
    }
  };

  const handlePause = async () => {
    if (currentRequestId) {
      await fetch("http://localhost:8000/api/chat/cancel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: currentRequestId }),
      });
    }
  };

  const handleApprove = async (approvalId: string, approved: boolean) => {
    await fetch("http://localhost:8000/api/chat/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approval_id: approvalId, approved }),
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (commandHistory.length > 0 && historyIndex < commandHistory.length - 1) {
        const nextIdx = historyIndex + 1;
        setHistoryIndex(nextIdx);
        setInput(commandHistory[commandHistory.length - 1 - nextIdx]);
      }
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (historyIndex > 0) {
        const prevIdx = historyIndex - 1;
        setHistoryIndex(prevIdx);
        setInput(commandHistory[commandHistory.length - 1 - prevIdx]);
      } else if (historyIndex === 0) {
        setHistoryIndex(-1);
        setInput("");
      }
    }
  };

  return (
    <div className="flex flex-col h-full bg-black/40 text-neutral-300 font-mono text-sm p-4">
      <div className="flex items-center justify-between mb-4 border-b border-white/10 pb-2">
        <div className="flex items-center gap-3 text-[#F5A623]">
          <ComputerTerminal01Icon className="w-6 h-6" />
          <h2 className="font-bold tracking-widest uppercase">Direct Neural Interface</h2>
        </div>
        
        {loading && (
          <button 
            onClick={handlePause}
            className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 transition-colors bg-red-400/10 px-2 py-1 rounded"
          >
            <StopIcon className="w-3 h-3" /> Pause Engine
          </button>
        )}
      </div>

      <div ref={chatContainerRef} className="flex-1 overflow-y-auto space-y-4 mb-4 pr-2 custom-scrollbar">
        {history.length === 0 ? (
          <div className="text-neutral-500 italic opacity-50">Kronos terminal online. Type /help for commands. Awaiting input...</div>
        ) : (
          history.map((msg) => (
            <div key={msg.id} className="flex flex-col w-full py-2 items-start">
              <div
                className={`w-full ${
                  msg.role === "user"
                    ? "max-w-[85%] bg-white/5 border border-white/10 rounded p-3 text-white"
                    : "text-neutral-300"
                }`}
              >
                <div className="flex justify-between items-center mb-2">
                  <div className="text-xs font-bold tracking-wider opacity-60 text-[#F5A623]">
                    {msg.role === "user" ? "USER" : "KRONOS"}
                  </div>
                  {msg.cost && (
                    <div className="text-[10px] opacity-50">
                      ${msg.cost.total_cost_usd?.toFixed(4)} • {msg.cost.total_tokens} tkns • {msg.cost.model}
                    </div>
                  )}
                </div>

                {/* Tool Calls */}
                {msg.toolCalls?.map((tc, idx) => (
                  <div key={idx} className="mb-3 bg-black/40 border border-white/10 rounded p-2 text-xs">
                    <div className="text-emerald-400 mb-1 font-semibold">λ {tc.name}</div>
                    <div className="text-neutral-500 font-mono text-[10px] break-all">{JSON.stringify(tc.args)}</div>
                    {tc.result && <div className="text-neutral-400 mt-2 pl-2 border-l border-emerald-500/30 max-h-40 overflow-y-auto whitespace-pre-wrap text-[10px] custom-scrollbar">{tc.result}</div>}
                  </div>
                ))}

                {/* Approvals */}
                {msg.approval && !msg.approval.resolved && (
                  <div className="my-3 p-3 border border-red-500/50 bg-red-500/10 rounded-lg">
                    <div className="text-red-400 font-bold text-sm mb-1">⚠️ Tool Approval Required</div>
                    <div className="text-white text-xs mb-2">The engine wants to run a high-risk command:</div>
                    <div className="bg-black/50 p-2 rounded text-red-300 font-mono text-xs mb-3 truncate">
                      {msg.approval.tool_name}({JSON.stringify(msg.approval.arguments_preview)})
                    </div>
                    <div className="text-neutral-400 text-xs italic mb-3">Reason: {msg.approval.reason}</div>
                    
                    <div className="flex gap-2">
                      <button 
                        onClick={() => handleApprove(msg.approval!.approval_id, true)}
                        className="flex-1 flex items-center justify-center gap-1 bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 py-1.5 rounded transition-colors"
                      >
                        <CheckmarkCircle01Icon className="w-4 h-4" /> Approve
                      </button>
                      <button 
                        onClick={() => handleApprove(msg.approval!.approval_id, false)}
                        className="flex-1 flex items-center justify-center gap-1 bg-red-500/20 text-red-400 hover:bg-red-500/30 py-1.5 rounded transition-colors"
                      >
                        <Cancel01Icon className="w-4 h-4" /> Deny
                      </button>
                    </div>
                  </div>
                )}

                {/* Cognitive Process */}
                {msg.processSteps && msg.processSteps.length > 0 && (
                  <details className="group mb-4 border border-white/10 bg-black/40 rounded-lg overflow-hidden">
                    <summary className="flex items-center gap-2 p-2 cursor-pointer text-xs font-semibold text-neutral-400 hover:text-white transition-colors bg-white/5 list-none outline-none">
                      <div className="flex-1 flex items-center gap-2">
                        <NeuralNetworkIcon className="w-4 h-4 text-[#5E5CE6]" />
                        <span>Cognitive Process ({msg.processSteps.length} steps)</span>
                        {msg.thinking && !msg.content && !msg.approval && (
                          <span className="text-[#F5A623] animate-pulse italic ml-2 text-[10px]">
                            {msg.thinking}
                          </span>
                        )}
                      </div>
                      <div className="transition-transform duration-200 group-open:rotate-180">▼</div>
                    </summary>
                    <div className="p-3 space-y-2 max-h-60 overflow-y-auto custom-scrollbar border-t border-white/5">
                      {msg.processSteps.map((step) => (
                        <div key={step.id} className="flex items-start gap-2 text-[11px]">
                          <span className={`px-1.5 py-0.5 rounded uppercase font-bold tracking-wider ${
                            step.type === 'routing' ? 'bg-[#5E5CE6]/20 text-[#5E5CE6]' :
                            step.type === 'context' ? 'bg-[#32ADE6]/20 text-[#32ADE6]' :
                            'bg-[#F5A623]/20 text-[#F5A623]'
                          }`}>
                            {step.type}
                          </span>
                          <span className="text-neutral-400 mt-0.5">{step.content}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}

                {/* Thinking state fallback if no process steps */}
                {msg.thinking && !msg.processSteps?.length && !msg.approval?.resolved && (
                  <div className="text-[#F5A623] animate-pulse italic text-xs mb-2">
                    {msg.thinking}
                  </div>
                )}

                {/* Error */}
                {msg.error && (
                  <div className="text-red-400 font-semibold mb-2">
                    {msg.error}
                  </div>
                )}

                {msg.cancelled && (
                  <div className="text-yellow-500/80 italic mb-2 text-xs">
                    ⚠️ Request cancelled by user.
                  </div>
                )}

                {/* Markdown Content */}
                {msg.content && (
                  <div className="prose prose-invert prose-sm max-w-none prose-pre:bg-black/50 prose-pre:border prose-pre:border-white/10">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        code({node, inline, className, children, ...props}: any) {
                          const match = /language-(\w+)/.exec(className || '')
                          return !inline && match ? (
                            <SyntaxHighlighter
                              {...props}
                              children={String(children).replace(/\\n$/, '')}
                              style={atomDark}
                              language={match[1]}
                              PreTag="div"
                            />
                          ) : (
                            <code {...props} className={className + " bg-white/10 px-1 py-0.5 rounded text-[#F5A623]"}>
                              {children}
                            </code>
                          )
                        }
                      }}
                    >
                      {msg.content}
                    </ReactMarkdown>
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      <div className="relative">
        {/* Upload previews */}
        {attachments.length > 0 && (
          <div className="flex gap-2 p-2 mb-2 bg-black/40 rounded-lg overflow-x-auto border border-white/10">
            {attachments.map((att, i) => (
              <div key={i} className="relative group flex-shrink-0">
                {att.file.type.startsWith('image/') ? (
                  <img src={att.url} className="w-16 h-16 object-cover rounded border border-white/20" alt="upload preview" />
                ) : (
                  <div className="w-16 h-16 flex items-center justify-center bg-white/10 rounded border border-white/20 text-[10px] text-neutral-400 p-1 text-center overflow-hidden">
                    {att.file.name}
                  </div>
                )}
                <button 
                  onClick={() => setAttachments(prev => prev.filter((_, idx) => idx !== i))} 
                  className="absolute -top-2 -right-2 bg-red-500 rounded-full p-0.5 text-white opacity-0 group-hover:opacity-100 transition-opacity z-10"
                >
                  <Cancel01Icon className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="relative flex items-center">
          <input
            type="file"
            multiple
            className="hidden"
            ref={fileInputRef}
            onChange={handleFileSelect}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            className="absolute left-2 bottom-1.5 p-2 rounded hover:bg-white/10 text-neutral-400 hover:text-white transition-colors z-10"
            title="Attach file"
          >
            <Attachment01Icon className="w-5 h-5" />
          </button>
          
          <TextareaAutosize
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Enter command or query (↑↓ for history, Shift+Enter for new line)..."
            className="w-full bg-black/60 border border-white/20 rounded-lg py-3 pl-12 pr-12 text-white focus:outline-none focus:border-[#F5A623] transition-colors resize-none custom-scrollbar"
            minRows={1}
            maxRows={10}
            autoFocus
          />
          <button
            onClick={handleSend}
            disabled={loading || (!input.trim() && attachments.length === 0)}
            className="absolute right-2 bottom-1.5 p-2 rounded hover:bg-white/10 text-neutral-400 hover:text-white disabled:opacity-50 transition-colors z-10"
          >
            <SentIcon className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
}
