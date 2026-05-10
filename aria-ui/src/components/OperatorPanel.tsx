"use client";

import { useCallback, useEffect, useState } from "react";
import { apiUrl, getAuthHeaders } from "@/lib/api";

type Health = {
  database_path: string;
  project_root: string;
  vector_store_active: boolean;
  docker_available: boolean;
  browser_registered: boolean;
  current_session: string | null;
  autonomy_policy: Record<string, boolean | string | number>;
  telegram_public_mode?: boolean;
};

type Approval = {
  id: string;
  tool_name: string;
  risk_level: string;
  arguments_json: string;
  reason: string;
  created_at: string;
};

type UsageSummary = {
  totals?: {
    requests?: number;
    input_tokens?: number;
    output_tokens?: number;
    estimated_cost_usd?: number;
  };
  models?: Array<{
    provider: string;
    model: string;
    requests: number;
    estimated_cost_usd: number;
  }>;
  approvals?: Array<{ status: string; count: number }>;
  tools?: Array<{ tool_name: string; calls: number; successes: number }>;
};

type ImprovementProposal = {
  id: string;
  target_system: string;
  description: string;
  rationale: string;
  success_metric: string;
  status: string;
  created_at: string;
  resolved_at: string | null;
};

type TelegramUser = {
  user_id: number;
  username?: string;
  paired_at: string;
};

export default function OperatorPanel() {
  const [health, setHealth] = useState<Health | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [telegramUsers, setTelegramUsers] = useState<TelegramUser[]>([]);
  const [pairCode, setPairCode] = useState<string | null>(null);
  const [proposals, setProposals] = useState<ImprovementProposal[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [healthRes, approvalsRes, usageRes, usersRes, proposalsRes] = await Promise.all([
        fetch(apiUrl("/api/health"), { headers: getAuthHeaders() }),
        fetch(apiUrl("/api/tool-approvals"), { headers: getAuthHeaders() }),
        fetch(apiUrl("/api/usage"), { headers: getAuthHeaders() }),
        fetch(apiUrl("/api/telegram/users"), { headers: getAuthHeaders() }),
        fetch(apiUrl("/api/improvement-proposals"), { headers: getAuthHeaders() }),
      ]);
      if (!healthRes.ok || !approvalsRes.ok || !usageRes.ok || !usersRes.ok || !proposalsRes.ok) throw new Error("Failed to load operator state");
      setHealth(await healthRes.json());
      setApprovals(await approvalsRes.json());
      setUsage(await usageRes.json());
      setTelegramUsers(await usersRes.json());
      setProposals(await proposalsRes.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load operator state");
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void refresh(), 0);
    return () => clearTimeout(timer);
  }, [refresh]);

  const resolveApproval = async (id: string, decision: "approved" | "rejected") => {
    await fetch(apiUrl(`/api/tool-approvals/${id}/${decision}`), {
      method: "POST",
      headers: getAuthHeaders(),
    });
    await refresh();
  };

  const resolveProposal = async (id: string, decision: "approved" | "rejected" | "implemented") => {
    await fetch(apiUrl(`/api/improvement-proposals/${id}/${decision}`), {
      method: "POST",
      headers: getAuthHeaders(),
    });
    await refresh();
  };

  const generatePairCode = async () => {
    const response = await fetch(apiUrl("/api/telegram/pair-code"), {
      method: "POST",
      headers: getAuthHeaders(),
    });
    if (response.ok) {
      const payload = await response.json();
      setPairCode(payload.code);
      await refresh();
    }
  };

  return (
    <div className="flex-1 overflow-y-auto px-4 py-8">
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Operator Panel</h1>
          <p className="text-sm text-muted-foreground mt-1">Runtime health, tool approvals, self-improvement proposals, and Telegram pairing.</p>
        </div>

        {error && <div className="rounded-xl border border-red-900 bg-red-950/30 p-4 text-sm text-red-300">{error}</div>}

        {health && (
          <section className="rounded-2xl border border-border bg-sidebar p-5 space-y-3">
            <h2 className="text-sm font-semibold">Health</h2>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Status label="Vector store" value={health.vector_store_active} />
              <Status label="Docker" value={health.docker_available} />
              <Status label="Browser tool" value={health.browser_registered} />
              <Status label="Session" value={health.current_session || "none"} />
            </div>
            <div className="text-xs text-muted-foreground break-all">Project: {health.project_root}</div>
            <div className="text-xs text-muted-foreground break-all">DB: {health.database_path}</div>
          </section>
        )}

        {health && (
          <section className="rounded-2xl border border-border bg-sidebar p-5 space-y-3">
            <h2 className="text-sm font-semibold">Autonomy Policy</h2>
            {health.telegram_public_mode && (
              <div className="rounded-xl border border-amber-700/40 bg-amber-950/40 px-4 py-3 text-sm text-amber-200">
                Warning: Telegram public mode is enabled. Any Telegram user can reach this ARIA instance until you disable it.
              </div>
            )}
            <div className="grid grid-cols-2 gap-3 text-sm">
              {Object.entries(health.autonomy_policy).map(([key, value]) => (
                <Status key={key} label={key.replaceAll("_", " ")} value={String(value)} />
              ))}
            </div>
          </section>
        )}

        {usage && (
          <section className="rounded-2xl border border-border bg-sidebar p-5 space-y-4">
            <div>
              <h2 className="text-sm font-semibold">Usage</h2>
              <p className="mt-1 text-xs text-muted-foreground">Local provider, model, and tool activity across this ARIA brain.</p>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Status label="requests" value={usage.totals?.requests ?? 0} />
              <Status label="input tokens" value={usage.totals?.input_tokens ?? 0} />
              <Status label="output tokens" value={usage.totals?.output_tokens ?? 0} />
              <Status label="estimated cost" value={`$${Number(usage.totals?.estimated_cost_usd ?? 0).toFixed(2)}`} />
            </div>

            <div className="space-y-2">
              <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">By model</div>
              {(usage.models ?? []).slice(0, 5).map((model) => (
                <div key={`${model.provider}-${model.model}`} className="rounded-xl bg-background p-3 text-sm">
                  <div className="font-medium">{model.provider} / {model.model}</div>
                  <div className="text-xs text-muted-foreground">{model.requests} requests · ${Number(model.estimated_cost_usd ?? 0).toFixed(2)}</div>
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="rounded-2xl border border-border bg-sidebar p-5 space-y-3">
          <h2 className="text-sm font-semibold">Self-improvement proposals</h2>
          <p className="text-xs text-muted-foreground">
            Explicit proposals from meta-analysis or inline model output. Approving does not auto-edit code — it records human review.
          </p>
          {proposals.filter((p) => p.status === "pending").length === 0 ? (
            <p className="text-sm text-muted-foreground">No pending proposals.</p>
          ) : (
            proposals
              .filter((p) => p.status === "pending")
              .map((p) => (
                <div key={p.id} className="rounded-xl border border-border p-4 space-y-2">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 space-y-1">
                      <div className="text-xs uppercase tracking-wide text-muted-foreground">{p.target_system}</div>
                      <div className="text-sm font-medium">{p.description}</div>
                      <div className="text-xs text-muted-foreground">Metric: {p.success_metric}</div>
                      <div className="text-xs text-muted-foreground line-clamp-3">{p.rationale}</div>
                    </div>
                    <div className="flex shrink-0 flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => void resolveProposal(p.id, "approved")}
                        className="rounded-lg bg-emerald-900 px-3 py-1.5 text-xs text-emerald-100"
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        onClick={() => void resolveProposal(p.id, "rejected")}
                        className="rounded-lg bg-red-950 px-3 py-1.5 text-xs text-red-200"
                      >
                        Reject
                      </button>
                      <button
                        type="button"
                        onClick={() => void resolveProposal(p.id, "implemented")}
                        className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs text-slate-200"
                      >
                        Mark done
                      </button>
                    </div>
                  </div>
                </div>
              ))
          )}
          {proposals.some((p) => p.status !== "pending") && (
            <details className="text-sm">
              <summary className="cursor-pointer text-muted-foreground">
                Resolved proposals ({proposals.filter((p) => p.status !== "pending").length})
              </summary>
              <ul className="mt-2 space-y-2 text-xs text-muted-foreground">
                {proposals
                  .filter((p) => p.status !== "pending")
                  .map((p) => (
                    <li key={p.id}>
                      <span className="font-medium text-foreground/80">{p.status}</span> · {p.description.slice(0, 120)}
                      {p.description.length > 120 ? "…" : ""}
                    </li>
                  ))}
              </ul>
            </details>
          )}
        </section>

        <section className="rounded-2xl border border-border bg-sidebar p-5 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">Telegram Pairing</h2>
              <p className="mt-1 text-xs text-muted-foreground">Generate a short-lived pairing code, then send it to your bot with <code>/start CODE</code>.</p>
            </div>
            <button onClick={() => void generatePairCode()} className="rounded-lg bg-white px-3 py-2 text-xs font-medium text-black">New code</button>
          </div>
          {pairCode && (
            <div className="rounded-xl border border-emerald-900 bg-emerald-950/30 px-4 py-3 text-sm text-emerald-200">
              Active pairing code: <span className="font-semibold tracking-[0.2em]">{pairCode}</span>
            </div>
          )}
          <div className="space-y-2">
            {telegramUsers.length === 0 ? (
              <p className="text-sm text-muted-foreground">No paired Telegram users yet.</p>
            ) : telegramUsers.map((user) => (
              <div key={user.user_id} className="rounded-xl bg-background p-3 text-sm">
                <div className="font-medium">{user.username ? `@${user.username}` : `User ${user.user_id}`}</div>
                <div className="text-xs text-muted-foreground">Paired {new Date(user.paired_at).toLocaleString()}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-border bg-sidebar p-5 space-y-3">
          <h2 className="text-sm font-semibold">Pending Approvals</h2>
          {approvals.length === 0 ? (
            <p className="text-sm text-muted-foreground">No pending tool approvals.</p>
          ) : approvals.map(approval => (
            <div key={approval.id} className="rounded-xl border border-border p-4 space-y-2">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium">{approval.tool_name}</div>
                  <div className="text-xs text-muted-foreground">Risk: {approval.risk_level}</div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => resolveApproval(approval.id, "approved")} className="text-xs rounded-lg bg-emerald-900 px-3 py-1.5 text-emerald-100">Approve</button>
                  <button onClick={() => resolveApproval(approval.id, "rejected")} className="text-xs rounded-lg bg-red-950 px-3 py-1.5 text-red-200">Reject</button>
                </div>
              </div>
              <pre className="max-h-32 overflow-auto rounded-lg bg-background p-3 text-xs text-muted-foreground">{approval.arguments_json}</pre>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}

function Status({ label, value }: { label: string; value: boolean | string | number }) {
  return (
    <div className="rounded-xl bg-background p-3">
      <div className="text-xs text-muted-foreground capitalize">{label}</div>
      <div className="text-sm font-medium">{typeof value === "boolean" ? (value ? "on" : "off") : value}</div>
    </div>
  );
}
