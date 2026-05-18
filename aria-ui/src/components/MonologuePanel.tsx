'use client';

import { AiBrain01Icon as BrainCircuit } from 'hugeicons-react';
import { ActivityEntry, AriaTelemetry, MonologueEntry } from '@/hooks/useAriaSocket';
import { cn } from '@/lib/utils';

interface Props {
  monologue: MonologueEntry[];
  metrics: { confidence: number; nodesAdded: number; goalsUpdated: number };
  telemetry: AriaTelemetry;
  activityFeed: ActivityEntry[];
}

function phaseDotClass(phase: AriaTelemetry['phase']) {
  switch (phase) {
    case 'thinking':
      return 'bg-amber-500 shadow-[0_0_24px_rgba(245,158,11,0.55)]';
    case 'responding':
      return 'bg-blue-500 shadow-[0_0_24px_rgba(59,130,246,0.55)]';
    case 'error':
      return 'bg-rose-500 shadow-[0_0_24px_rgba(244,63,94,0.45)]';
    case 'offline':
      return 'bg-zinc-400 shadow-[0_0_20px_rgba(113,113,122,0.35)]';
    default:
      return 'bg-emerald-500 shadow-[0_0_20px_rgba(16,185,129,0.45)]';
  }
}

function toneBadgeClass(tone: ActivityEntry['tone']) {
  switch (tone) {
    case 'thinking':
      return 'bg-amber-50 text-amber-700 border-amber-200';
    case 'response':
      return 'bg-blue-50 text-blue-700 border-blue-200';
    case 'error':
      return 'bg-rose-50 text-rose-700 border-rose-200';
    default:
      return 'bg-zinc-50 text-zinc-700 border-zinc-200';
  }
}

function sessionLabel(sessionId: string | null) {
  if (!sessionId) return 'No active session';
  return `${sessionId.slice(0, 8)}...${sessionId.slice(-4)}`;
}

function leadText(telemetry: AriaTelemetry) {
  if (telemetry.lastError) return telemetry.lastError;
  if (telemetry.liveThought) return telemetry.liveThought;
  if (telemetry.phase === 'responding') return 'VYN is composing the outward response for the current run.';
  if (telemetry.phase === 'thinking') return 'VYN is analyzing context, memory, and tool options before answering.';
  if (telemetry.phase === 'offline') return 'The live link is down. The panel will refresh as soon as the socket reconnects.';
  return 'Waiting for cognitive activity. New traces, metrics, and session events will appear here.';
}

function phaseLabel(phase: AriaTelemetry['phase']) {
  switch (phase) {
    case 'thinking':
      return 'Thinking';
    case 'responding':
      return 'Responding';
    case 'error':
      return 'Error';
    case 'offline':
      return 'Offline';
    default:
      return 'Idle';
  }
}

function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="rounded-[1.2rem] border border-black/8 bg-black/[0.03] px-4 py-3">
      <div className="text-[10px] uppercase tracking-[0.22em] text-black/35">{label}</div>
      <div className="mt-2 text-[1.05rem] font-semibold tracking-tight text-black">{value}</div>
      <div className="mt-1 text-[11px] leading-5 text-black/42">{hint}</div>
    </div>
  );
}

function clampStyle(lines: number) {
  return {
    display: '-webkit-box',
    WebkitLineClamp: lines,
    WebkitBoxOrient: 'vertical' as const,
    overflow: 'hidden',
  };
}

export default function MonologuePanel({
  monologue,
  metrics,
  telemetry,
  activityFeed,
}: Props) {
  const recentThoughts = monologue.slice(-2).reverse();
  const recentActivity = activityFeed.slice(0, 2);

  return (
    <aside className="relative flex h-full w-[26.25rem] shrink-0 overflow-hidden rounded-l-[2.35rem] border border-black/10 bg-white shadow-[-24px_0_60px_rgba(0,0,0,0.22)]">
      <div className="flex w-[5.25rem] shrink-0 flex-col items-center justify-between border-r border-black/6 px-3 py-6">
          <div className="flex flex-col items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-[1.35rem] bg-black text-white shadow-[0_18px_35px_rgba(0,0,0,0.22)]">
              <BrainCircuit size={18} />
            </div>
            <div className={cn('h-3 w-3 rounded-full', phaseDotClass(telemetry.phase))} />
            <div className="space-y-2">
              <div className="rounded-full bg-black px-2 py-1 text-center text-[10px] font-medium text-white">
                {metrics.confidence}%
              </div>
              <div className="rounded-full border border-black/10 px-2 py-1 text-center text-[10px] font-medium text-black/70">
                +{metrics.nodesAdded}
              </div>
              <div className="rounded-full border border-black/10 px-2 py-1 text-center text-[10px] font-medium text-black/70">
                {metrics.goalsUpdated}
              </div>
            </div>
          </div>

          <div className="[writing-mode:vertical-rl] rotate-180 text-[10px] font-semibold uppercase tracking-[0.35em] text-black/30">
            VYN
          </div>
        </div>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="border-b border-black/8 px-6 py-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.32em] text-black/35">
                  Live cognitive trace
                </div>
                <h3 className="mt-2 text-[1.85rem] font-semibold tracking-tight text-black">
                  Cognitive State
                </h3>
              </div>
              <div className="rounded-full border border-black/10 bg-black px-3 py-1.5 text-xs font-medium text-white">
                {telemetry.statusLabel}
              </div>
            </div>

            <div className="mt-4 grid grid-cols-[1fr_7rem] gap-3">
              <div className="rounded-[1.55rem] bg-black px-5 py-4.5 text-white shadow-[0_20px_50px_rgba(0,0,0,0.18)]">
                <div className="text-[10px] uppercase tracking-[0.24em] text-white/50">
                  Current signal
                </div>
                <p className="mt-3 text-[15px] leading-7 text-white/88" style={clampStyle(4)}>
                  {leadText(telemetry)}
                </p>
              </div>
              <div className="space-y-3">
                <div className="rounded-[1.2rem] border border-black/10 bg-black/[0.03] px-4 py-3">
                  <div className="text-[10px] uppercase tracking-[0.22em] text-black/40">Mode</div>
                  <div className="mt-2 text-base font-semibold text-black">{phaseLabel(telemetry.phase)}</div>
                </div>
                <div className="rounded-[1.2rem] border border-black/10 bg-black/[0.03] px-4 py-3">
                  <div className="text-[10px] uppercase tracking-[0.22em] text-black/40">Busy</div>
                  <div className="mt-2 text-base font-semibold text-black">
                    {telemetry.busySeconds > 0 ? `${telemetry.busySeconds}s` : 'Idle'}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="flex flex-1 flex-col overflow-hidden px-6 py-5">
            <div className="grid grid-cols-2 gap-3">
              <StatCard
                label="Connection"
                value={telemetry.connectionLabel}
                hint={telemetry.lastEventTime ? `Last event at ${telemetry.lastEventTime}` : 'No events yet'}
              />
              <StatCard
                label="Active Session"
                value={sessionLabel(telemetry.activeSessionId)}
                hint="Current conversation context"
              />
              <StatCard
                label="Trace Frames"
                value={String(telemetry.monologueCount)}
                hint="Internal trace updates"
              />
              <StatCard
                label="Turns"
                value={`${telemetry.userTurns}/${telemetry.ariaResponses}`}
                hint="User / VYN replies"
              />
            </div>

            <div className="mt-5 grid flex-1 grid-rows-[auto_1fr] gap-4 overflow-hidden">
              <section className="min-h-0">
                <div className="mb-2 flex items-center justify-between">
                  <h4 className="text-xs font-semibold uppercase tracking-[0.24em] text-black/35">
                    Latest Activity
                  </h4>
                  <span className="text-xs text-black/35">
                    {recentActivity.length || 0}
                  </span>
                </div>

                <div className="rounded-[1.4rem] border border-black/8 bg-black/[0.02] p-2.5">
                  {recentActivity.length === 0 ? (
                    <div className="rounded-[1rem] px-3 py-3 text-sm text-black/45">
                      Activity will appear here.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {recentActivity.map((entry) => (
                        <div
                          key={entry.id}
                          className="rounded-[1rem] bg-white px-3 py-3 shadow-[0_8px_18px_rgba(0,0,0,0.03)]"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex min-w-0 items-center gap-2">
                              <span
                                className={cn(
                                  'rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em]',
                                  toneBadgeClass(entry.tone)
                                )}
                              >
                                {entry.tone}
                              </span>
                              <span className="truncate text-sm font-semibold text-black">{entry.title}</span>
                            </div>
                            <span className="text-[11px] font-medium text-black/35">{entry.time}</span>
                          </div>
                          <p className="mt-1.5 text-[13px] leading-5 text-black/52" style={clampStyle(2)}>
                            {entry.detail}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </section>

              <section className="min-h-0">
                <div className="mb-2 flex items-center justify-between">
                  <h4 className="text-xs font-semibold uppercase tracking-[0.24em] text-black/35">
                    Reasoning
                  </h4>
                  <span className="text-xs text-black/35">
                    {recentThoughts.length || 0}
                  </span>
                </div>

                <div className="rounded-[1.4rem] border border-black/8 bg-black text-white shadow-[0_18px_40px_rgba(0,0,0,0.12)]">
                  {recentThoughts.length === 0 ? (
                    <div className="px-4 py-4 text-sm italic text-white/55">
                      Waiting for cognitive activity...
                    </div>
                  ) : (
                    <div className="divide-y divide-white/10">
                      {recentThoughts.map((entry) => (
                        <div key={entry.id} className="px-4 py-3.5">
                          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-white/38">
                            {entry.time}
                          </div>
                          <p className="mt-2 font-mono text-[13px] leading-5 text-white/78" style={clampStyle(2)}>
                            {entry.text}
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </section>
            </div>
          </div>

          <div className="border-t border-black/8 px-6 py-4">
            <div className="flex flex-wrap gap-2">
              <div className="rounded-full border border-black/10 bg-black px-3 py-1.5 text-xs font-medium text-white">
                Confidence {metrics.confidence}%
              </div>
              <div className="rounded-full border border-black/10 bg-black/[0.04] px-3 py-1.5 text-xs font-medium text-black/70">
                Nodes +{metrics.nodesAdded}
              </div>
              <div className="rounded-full border border-black/10 bg-black/[0.04] px-3 py-1.5 text-xs font-medium text-black/70">
                Goals {metrics.goalsUpdated}
              </div>
              <div className="rounded-full border border-black/10 bg-black/[0.04] px-3 py-1.5 text-xs font-medium text-black/70">
                {telemetry.statusLabel}
              </div>
            </div>
          </div>
        </div>
    </aside>
  );
}
