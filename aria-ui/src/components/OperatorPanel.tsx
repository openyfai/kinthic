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
};

type Approval = {
  id: string;
  tool_name: string;
  risk_level: string;
  arguments_json: string;
  reason: string;
  created_at: string;
};

export default function OperatorPanel() {
  const [health, setHealth] = useState<Health | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [healthRes, approvalsRes] = await Promise.all([
        fetch(apiUrl("/api/health"), { headers: getAuthHeaders() }),
        fetch(apiUrl("/api/tool-approvals"), { headers: getAuthHeaders() }),
      ]);
      if (!healthRes.ok || !approvalsRes.ok) throw new Error("Failed to load operator state");
      setHealth(await healthRes.json());
      setApprovals(await approvalsRes.json());
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

  return (
    <div className="flex-1 overflow-y-auto px-4 py-8">
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Operator Panel</h1>
          <p className="text-sm text-muted-foreground mt-1">Runtime health, autonomy policy, and pending tool approvals.</p>
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
            <div className="grid grid-cols-2 gap-3 text-sm">
              {Object.entries(health.autonomy_policy).map(([key, value]) => (
                <Status key={key} label={key.replaceAll("_", " ")} value={String(value)} />
              ))}
            </div>
          </section>
        )}

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
