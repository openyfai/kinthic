"use client";

import { useEffect, useState } from "react";
import { animate, motion, useMotionValue, useTransform } from "framer-motion";
import { AiBrain01Icon as BrainCircuit } from "hugeicons-react";
import Sidebar, { ViewType } from "@/components/Sidebar";
import ChatArea from "@/components/ChatArea";
import MessageInput from "@/components/MessageInput";
import MonologuePanel from "@/components/MonologuePanel";
import GoalsView from "@/components/GoalsView";
import GraphView from "@/components/GraphView";
import OperatorPanel from "@/components/OperatorPanel";
import SettingsView from "@/components/SettingsView";
import SetupWizard from "@/components/SetupWizard";
import MemoriesView from "@/components/MemoriesView";
import HypothesesView from "@/components/HypothesesView";
import ContradictionsView from "@/components/ContradictionsView";
import UncertaintiesView from "@/components/UncertaintiesView";
import BenchmarkView from "@/components/BenchmarkView";
import { useAriaSocket } from "@/hooks/useAriaSocket";
import { apiUrl, clearApiKey, getAuthHeaders, getApiKey, setApiKey, wsUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

const PANEL_WIDTH = 420;
const PANEL_REVEAL_WIDTH = PANEL_WIDTH;
const DRAG_OPEN_THRESHOLD = 100;

/** Session flag so the post-setup checklist survives a refresh until dismissed. */
const POST_SETUP_NEXT_PENDING_KEY = "aria_post_setup_next_pending";

type RuntimeSettings = {
  provider: string;
  model: string;
  security?: {
    require_tool_approvals?: boolean;
    browser_actions?: boolean;
    terminal_execution?: boolean;
    code_apply?: boolean;
    background_actions?: boolean;
  };
};

type RuntimeStatus = {
  setup_completed: boolean;
};

type RuntimeProvider = {
  id: string;
  label: string;
  models: Array<{ id: string; label: string; tier?: string }>;
};

type RuntimeData = {
  settings: RuntimeSettings;
  status: RuntimeStatus;
  providers: RuntimeProvider[];
};

type BootstrapData = {
  auth_required: boolean;
  has_local_api_key: boolean;
  setup: RuntimeStatus & {
    provider?: string;
    model?: string;
    provider_configured?: boolean;
    web_api_key_configured?: boolean;
  };
  providers: RuntimeProvider[];
};

function mergeRuntimeData(current: RuntimeData | null, patch: Partial<RuntimeData>): RuntimeData | null {
  if (!current) {
    return patch.providers && patch.settings && patch.status
      ? { providers: patch.providers, settings: patch.settings, status: patch.status }
      : current;
  }
  return {
    providers: patch.providers ?? current.providers,
    settings: patch.settings ?? current.settings,
    status: patch.status ?? current.status,
  };
}

export default function Home() {
  const [isSidebarOpen] = useState(true);
  const [isMonologueOpen, setMonologueOpen] = useState(false);
  const [currentView, setCurrentView] = useState<ViewType>("chat");
  const [bootstrapData, setBootstrapData] = useState<BootstrapData | null>(null);
  const [runtimeData, setRuntimeData] = useState<RuntimeData | null>(null);
  const [authInput, setAuthInput] = useState("");
  const [authNeeded, setAuthNeeded] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [runtimeLoading, setRuntimeLoading] = useState(true);
  const [postSetupNextOpen, setPostSetupNextOpen] = useState(false);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [setupWizardReview, setSetupWizardReview] = useState(false);
  const shellX = useMotionValue(0);
  const socketEnabled = !runtimeLoading && !authNeeded;

  const {
    messages, monologue, isThinking, isStreaming, isConnected, currentThought,
    metrics, sessions, activeSessionId, activityFeed, telemetry,
    sendMessage, stopGeneration, regenerate, editAndResend, retryLast,
    loadSession, createNewSession
  } = useAriaSocket(wsUrl("/ws/chat"), socketEnabled);

  const panelScale = useTransform(shellX, [-PANEL_REVEAL_WIDTH, 0], [1, 0.985]);
  const panelOpacity = useTransform(shellX, [-PANEL_REVEAL_WIDTH, 0], [1, 0]);
  const shellRadius = useTransform(shellX, [-PANEL_REVEAL_WIDTH, 0], [34, 26]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (sessionStorage.getItem(POST_SETUP_NEXT_PENDING_KEY) === "1") {
      queueMicrotask(() => setPostSetupNextOpen(true));
    }
  }, []);

  useEffect(() => {
    const controls = animate(shellX, isMonologueOpen ? -PANEL_REVEAL_WIDTH : 0, {
      type: "spring",
      stiffness: 280,
      damping: 32,
      mass: 0.9,
    });
    return () => controls.stop();
  }, [isMonologueOpen, shellX]);

  useEffect(() => {
    let cancelled = false;
    async function loadRuntime() {
      setRuntimeLoading(true);
      try {
        const bootstrapRes = await fetch(apiUrl("/api/bootstrap"));
        if (!bootstrapRes.ok) {
          throw new Error("Failed to load bootstrap state.");
        }
        const bootstrapPayload: BootstrapData = await bootstrapRes.json();
        if (cancelled) return;
        setBootstrapData(bootstrapPayload);

        const storedApiKey = getApiKey();
        const needsAuth = bootstrapPayload.auth_required && !storedApiKey;
        setAuthNeeded(needsAuth);
        if (needsAuth) {
          setRuntimeError(null);
          setRuntimeLoading(false);
          return;
        }

        const response = await fetch(apiUrl("/api/settings"), { headers: getAuthHeaders() });
        if (response.status === 401) {
          setAuthNeeded(true);
          setAuthError("Enter the VYN web API key for this instance to continue.");
          setRuntimeLoading(false);
          return;
        }
        if (!response.ok) {
          throw new Error("Failed to load runtime settings.");
        }
        const payload = await response.json();
        if (!cancelled) {
          setRuntimeData(payload);
          setRuntimeError(null);
          setAuthNeeded(false);
          setAuthError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setRuntimeError(
            error instanceof TypeError
              ? "Cannot reach the VYN server yet. Start `vyn web` or `docker compose --profile web up --build`."
              : error instanceof Error
                ? error.message
                : "Failed to load runtime settings."
          );
        }
      } finally {
        if (!cancelled) {
          setRuntimeLoading(false);
        }
      }
    }

    void loadRuntime();
    return () => {
      cancelled = true;
    };
  }, []);

  async function unlockWithApiKey() {
    const candidate = authInput.trim();
    if (!candidate) {
      setAuthError("Enter the VYN web API key to continue.");
      return;
    }
    setApiKey(candidate);
    setAuthError(null);
    setRuntimeError(null);
    setRuntimeLoading(true);
    try {
      const response = await fetch(apiUrl("/api/settings"), {
        headers: {
          Authorization: `Bearer ${candidate}`,
        },
      });
      if (!response.ok) {
        throw new Error("That API key was rejected.");
      }
      const payload: RuntimeData = await response.json();
      setRuntimeData(payload);
      setAuthNeeded(false);
      setAuthInput("");
    } catch (error) {
      clearApiKey();
      setAuthError(error instanceof Error ? error.message : "That API key was rejected.");
    } finally {
      setRuntimeLoading(false);
    }
  }

  return (
    <div className="flex h-screen w-full bg-background text-foreground overflow-hidden font-sans">
      {authNeeded && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/78 px-6 py-10 backdrop-blur-md">
          <div className="w-full max-w-xl rounded-[30px] border border-white/10 bg-[#050505] p-8 shadow-[0_30px_120px_rgba(0,0,0,0.65)]">
            <div className="text-[11px] uppercase tracking-[0.32em] text-white/42">Secure instance</div>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white">Enter the VYN web API key.</h1>
            <p className="mt-3 text-sm leading-6 text-white/62">
              This instance is bound beyond localhost or has API protection enabled. Enter the local web key first,
              then the onboarding flow will continue normally.
            </p>
            {bootstrapData && (
              <div className="mt-4 rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3 text-sm text-white/70">
                {bootstrapData.setup.setup_completed
                  ? `Current runtime: ${bootstrapData.setup.provider ?? "configured provider"} / ${bootstrapData.setup.model ?? "configured model"}.`
                  : "Setup has not been completed yet. After unlocking, VYN will open the first-run setup flow."}
              </div>
            )}
            <div className="mt-6 grid gap-3">
              <input
                value={authInput}
                onChange={(event) => setAuthInput(event.target.value)}
                placeholder="VYN_WEB_API_KEY"
                className="w-full rounded-2xl border border-white/10 bg-black/35 px-4 py-3 text-sm text-white outline-none transition placeholder:text-white/28 focus:border-white/25"
              />
              <button
                type="button"
                onClick={() => void unlockWithApiKey()}
                className="rounded-2xl bg-white px-4 py-3 text-sm font-medium text-black transition hover:bg-white/90"
              >
                Unlock setup
              </button>
              {authError && (
                <div className="rounded-2xl border border-red-500/20 bg-red-500/8 px-4 py-3 text-sm text-red-200">
                  {authError}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {runtimeData && runtimeData.status && (!runtimeData.status.setup_completed || setupWizardReview) && (
        <SetupWizard
          providers={runtimeData.providers ?? []}
          initialSettings={runtimeData.settings}
          variant={runtimeData.status.setup_completed ? "review" : "first-run"}
          onCancel={runtimeData.status.setup_completed ? () => setSetupWizardReview(false) : undefined}
          onComplete={(payload) => {
            setSetupWizardReview(false);
            setRuntimeData((current) => mergeRuntimeData(current, {
              settings: payload.settings,
              status: payload.status,
            }));
            if (typeof window !== "undefined") {
              sessionStorage.setItem(POST_SETUP_NEXT_PENDING_KEY, "1");
            }
            setPostSetupNextOpen(true);
          }}
        />
      )}
      <div className="relative flex min-w-0 flex-1 overflow-hidden bg-background">
        <div className="relative z-20 shrink-0">
          <Sidebar
            isOpen={isSidebarOpen}
            sessions={sessions}
            activeSessionId={activeSessionId}
            currentView={currentView}
            onViewChange={setCurrentView}
            onSelectSession={(id) => { loadSession(id); setCurrentView("chat"); }}
            onNewChat={() => { createNewSession(); setCurrentView("chat"); }}
          />
        </div>

        <div className="relative min-w-0 flex-1 overflow-hidden">
          <motion.div
            className="absolute inset-y-0 right-0 z-0"
            style={{
              width: PANEL_WIDTH,
              scale: panelScale,
              opacity: panelOpacity,
              transformOrigin: "right center",
            }}
          >
            <MonologuePanel
              monologue={monologue}
              metrics={metrics}
              telemetry={telemetry}
              activityFeed={activityFeed}
            />
          </motion.div>

          <motion.div
            drag="x"
            dragConstraints={{ left: -PANEL_REVEAL_WIDTH, right: 0 }}
            dragElastic={0.04}
            dragMomentum={false}
            onDragEnd={(_, info) => {
              const draggedOpen = info.offset.x <= -DRAG_OPEN_THRESHOLD;
              const draggedClosed = info.offset.x >= DRAG_OPEN_THRESHOLD;

              if (draggedOpen) {
                setMonologueOpen(true);
                return;
              }

              if (draggedClosed) {
                setMonologueOpen(false);
                return;
              }

              setMonologueOpen(shellX.get() <= -(PANEL_REVEAL_WIDTH / 2));
            }}
            style={{
              x: shellX,
              borderTopRightRadius: shellRadius,
              borderBottomRightRadius: shellRadius,
            }}
            className="absolute inset-0 z-10 flex min-w-0 overflow-hidden bg-background shadow-[0_28px_80px_rgba(0,0,0,0.45)]"
          >
            {isMonologueOpen && (
              <button
                type="button"
                onClick={() => setMonologueOpen(false)}
                aria-expanded={true}
                aria-label="Collapse cognitive panel"
                className="absolute right-0 top-1/2 z-30 flex h-14 w-7 translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-l-full rounded-r-[999px] border border-white/10 bg-black text-lg font-light text-white shadow-[0_12px_28px_rgba(0,0,0,0.22)] transition-transform duration-200 ease-out hover:scale-[1.03] active:scale-[0.97]"
              >
                <span className={cn("transition-transform duration-300 ease-out translate-x-px")}>
                  {"<"}
                </span>
              </button>
            )}

            <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
              {!isConnected && (
                <div className="absolute top-0 left-0 right-0 bg-amber-950 border-b border-amber-800 text-amber-400 text-xs text-center py-1.5 z-30 font-medium">
                  {runtimeLoading ? "Loading VYN runtime..." : "Reconnecting to VYN..."}
                </div>
              )}

              {postSetupNextOpen &&
                runtimeData?.status?.setup_completed &&
                currentView === "chat" && (
                <div className="absolute top-4 left-1/2 z-30 w-[min(100%-2rem,28rem)] -translate-x-1/2 rounded-2xl border border-border bg-card/95 px-5 py-4 shadow-xl backdrop-blur-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-[11px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
                        Next steps
                      </div>
                      <p className="mt-2 text-sm font-medium text-foreground">
                        VYN is ready. Try a prompt below, or explore:
                      </p>
                    </div>
                    <button
                      type="button"
                      aria-label="Dismiss next steps"
                      onClick={() => {
                        setPostSetupNextOpen(false);
                        if (typeof window !== "undefined") {
                          sessionStorage.removeItem(POST_SETUP_NEXT_PENDING_KEY);
                        }
                      }}
                      className="shrink-0 rounded-lg px-2 py-1 text-xs text-muted-foreground transition hover:bg-muted hover:text-foreground"
                    >
                      Dismiss
                    </button>
                  </div>
                  <ul className="mt-4 grid gap-2 text-sm text-foreground">
                    <li className="flex flex-wrap items-center gap-2">
                      <span className="text-muted-foreground">Chat</span>
                      <span className="text-xs text-muted-foreground">— you are here; use the box or starter prompts.</span>
                    </li>
                    <li>
                      <button
                        type="button"
                        onClick={() => {
                          setCurrentView("graph");
                          setPostSetupNextOpen(false);
                          if (typeof window !== "undefined") {
                            sessionStorage.removeItem(POST_SETUP_NEXT_PENDING_KEY);
                          }
                        }}
                        className="font-medium text-foreground underline decoration-white/20 underline-offset-4 transition hover:decoration-foreground"
                      >
                        Open Graph
                      </button>
                      <span className="text-xs text-muted-foreground"> — inspect the knowledge graph.</span>
                    </li>
                    <li>
                      <button
                        type="button"
                        onClick={() => {
                          setCurrentView("goals");
                          setPostSetupNextOpen(false);
                          if (typeof window !== "undefined") {
                            sessionStorage.removeItem(POST_SETUP_NEXT_PENDING_KEY);
                          }
                        }}
                        className="font-medium text-foreground underline decoration-white/20 underline-offset-4 transition hover:decoration-foreground"
                      >
                        Open Goals
                      </button>
                    </li>
                    <li>
                      <button
                        type="button"
                        onClick={() => {
                          setCurrentView("operator");
                          setPostSetupNextOpen(false);
                          if (typeof window !== "undefined") {
                            sessionStorage.removeItem(POST_SETUP_NEXT_PENDING_KEY);
                          }
                        }}
                        className="font-medium text-foreground underline decoration-white/20 underline-offset-4 transition hover:decoration-foreground"
                      >
                        Open Operator
                      </button>
                      <span className="text-xs text-muted-foreground">
                        {" "}
                        — approvals, usage, optional Telegram pairing.
                      </span>
                    </li>
                  </ul>
                </div>
              )}

              {currentView === "chat" && (
                <>
                  <ChatArea
                    messages={messages}
                    isThinking={isThinking}
                    isStreaming={isStreaming}
                    currentThought={currentThought}
                    onRegenerate={regenerate}
                    onEditAndResend={editAndResend}
                    onRetry={retryLast}
                    onSendSuggestion={sendMessage}
                  />

                  {messages.length === 0 && !isThinking ? (
                    <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none px-6 py-8">
                      <div className="w-full max-w-3xl pointer-events-auto flex flex-col items-center gap-6">
                        <h1 className="text-3xl font-semibold tracking-tight text-foreground text-center">
                          How can I help you today?
                        </h1>
                        <MessageInput
                          onSend={sendMessage}
                          onStop={stopGeneration}
                          isDisabled={isThinking || isStreaming}
                        />
                        <div className="flex flex-wrap justify-center gap-2 -mt-2">
                          {[
                            "Analyze this repo and build a knowledge graph of the architecture.",
                            "Find one contradiction or risk in this project and explain it.",
                            "Propose one safe improvement and ask before acting.",
                          ].map((prompt) => (
                            <button
                              key={prompt}
                              type="button"
                              onClick={() => sendMessage(prompt)}
                              className="rounded-full border border-white/10 bg-white/[0.04] px-4 py-2 text-xs text-white/85 transition hover:bg-white/[0.08]"
                            >
                              {prompt}
                            </button>
                          ))}
                        </div>
                        <div className="text-center text-[11px] text-muted-foreground -mt-1">
                          VYN can make mistakes. Consider verifying critical information.
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="absolute bottom-0 w-full p-6 pt-12 bg-gradient-to-t from-background via-background/95 to-transparent pointer-events-none">
                      <div className="pointer-events-auto">
                        <MessageInput
                          onSend={sendMessage}
                          onStop={stopGeneration}
                          isDisabled={isThinking || isStreaming}
                        />
                        <div className="text-center mt-3 text-[11px] text-muted-foreground">
                          VYN can make mistakes. Consider verifying critical information.
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )}

              {currentView === "goals"           && <GoalsView />}
              {currentView === "graph"           && <GraphView />}
              {currentView === "memories"        && <MemoriesView />}
              {currentView === "hypotheses"      && <HypothesesView />}
              {currentView === "contradictions"  && <ContradictionsView />}
              {currentView === "uncertainties"   && <UncertaintiesView />}
              {currentView === "benchmark"       && <BenchmarkView />}
              {currentView === "operator"        && <OperatorPanel />}
              {currentView === "settings" && runtimeData && (
                <SettingsView
                  providers={runtimeData.providers ?? []}
                  settings={runtimeData.settings}
                  onOpenOnboarding={() => {
                    setCurrentView("settings");
                    setSetupWizardReview(true);
                  }}
                  onSaved={(payload) => {
                    setRuntimeData((current) => mergeRuntimeData(current, {
                      settings: payload.settings,
                    }));
                  }}
                />
              )}

              {runtimeError && (
                <div className="absolute bottom-6 left-6 rounded-2xl border border-red-500/20 bg-red-500/8 px-4 py-3 text-sm text-red-200">
                  {runtimeError}
                </div>
              )}
            </main>
          </motion.div>

          {!isMonologueOpen && (
            <button
              type="button"
              onClick={() => setMonologueOpen(true)}
              aria-expanded={false}
              aria-label="Expand cognitive panel"
              className="absolute right-0 top-7 z-30 flex h-14 w-14 translate-x-1/2 items-center justify-center rounded-full border border-white/10 bg-black text-white shadow-[0_16px_36px_rgba(0,0,0,0.28)] transition-transform duration-200 ease-out hover:scale-[1.03] active:scale-[0.97]"
            >
              <BrainCircuit size={18} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
