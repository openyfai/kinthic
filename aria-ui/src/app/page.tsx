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
import { useAriaSocket } from "@/hooks/useAriaSocket";
import { wsUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

const PANEL_WIDTH = 420;
const PANEL_REVEAL_WIDTH = PANEL_WIDTH;
const DRAG_OPEN_THRESHOLD = 100;

export default function Home() {
  const [isSidebarOpen] = useState(true);
  const [isMonologueOpen, setMonologueOpen] = useState(false);
  const [currentView, setCurrentView] = useState<ViewType>("chat");
  const shellX = useMotionValue(0);

  const {
    messages, monologue, isThinking, isStreaming, isConnected, currentThought,
    metrics, sessions, activeSessionId, activityFeed, telemetry,
    sendMessage, stopGeneration, regenerate, editAndResend, retryLast,
    loadSession, createNewSession
  } = useAriaSocket(wsUrl("/ws/chat"));

  const panelScale = useTransform(shellX, [-PANEL_REVEAL_WIDTH, 0], [1, 0.985]);
  const panelOpacity = useTransform(shellX, [-PANEL_REVEAL_WIDTH, 0], [1, 0]);
  const shellRadius = useTransform(shellX, [-PANEL_REVEAL_WIDTH, 0], [34, 26]);

  useEffect(() => {
    const controls = animate(shellX, isMonologueOpen ? -PANEL_REVEAL_WIDTH : 0, {
      type: "spring",
      stiffness: 280,
      damping: 32,
      mass: 0.9,
    });
    return () => controls.stop();
  }, [isMonologueOpen, shellX]);

  return (
    <div className="flex h-screen w-full bg-background text-foreground overflow-hidden font-sans">
      <div className="relative flex min-w-0 flex-1 overflow-hidden bg-background">
        <div className="relative z-20 shrink-0">
          <Sidebar
            isOpen={isSidebarOpen}
            toggle={() => {}}
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
                  Reconnecting to ARIA...
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
                    <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                      <div className="mt-[18vh] w-full max-w-3xl px-8 pointer-events-auto">
                        <MessageInput
                          onSend={sendMessage}
                          onStop={stopGeneration}
                          isDisabled={isThinking || isStreaming}
                        />
                        <div className="text-center mt-3 text-[11px] text-muted-foreground">
                          ARIA can make mistakes. Consider verifying critical information.
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
                          ARIA can make mistakes. Consider verifying critical information.
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )}

              {currentView === "goals" && <GoalsView />}
              {currentView === "graph" && <GraphView />}
              {currentView === "operator" && <OperatorPanel />}
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
