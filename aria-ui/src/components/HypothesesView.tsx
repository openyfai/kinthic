"use client";

import { useCallback, useEffect, useState } from "react";
import { apiUrl, getAuthHeaders } from "@/lib/api";

interface Hypothesis {
  id: string;
  claim: string;
  reasoning: string;
  status: string;
  created_at: string;
}

function statusBadge(status: string) {
  if (status === "confirmed") return "bg-emerald-900/40 text-emerald-300 border border-emerald-800/40";
  if (status === "denied")    return "bg-red-900/40    text-red-300    border border-red-800/40";
  return "bg-amber-900/30 text-amber-300 border border-amber-800/30";
}

export default function HypothesesView() {
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "pending" | "confirmed" | "denied">("pending");

  const load = useCallback(async () => {
    setLoading(true);
    const res = await fetch(apiUrl("/api/hypotheses"), { headers: getAuthHeaders() });
    if (res.ok) setHypotheses(await res.json());
    setLoading(false);
  }, []);

  useEffect(() => { void load(); }, [load]);

  const resolve = async (id: string, action: "confirm" | "deny") => {
    await fetch(apiUrl(`/api/hypotheses/${id}/${action}`), { method: "POST", headers: getAuthHeaders() });
    await load();
  };

  const counts = {
    all: hypotheses.length,
    pending: hypotheses.filter(h => h.status === "pending").length,
    confirmed: hypotheses.filter(h => h.status === "confirmed").length,
    denied: hypotheses.filter(h => h.status === "denied").length,
  };

  const filtered = filter === "all" ? hypotheses : hypotheses.filter(h => h.status === filter);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-8">
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Hypotheses</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Beliefs VYN has formed that are awaiting confirmation or denial.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {(["pending", "confirmed", "denied", "all"] as const).map(f => (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium capitalize transition-colors ${
                filter === f
                  ? "bg-white text-black"
                  : "border border-white/10 bg-white/[0.04] text-white/60 hover:bg-white/[0.08]"
              }`}
            >
              {f} ({counts[f]})
            </button>
          ))}
        </div>

        {loading ? (
          <div className="text-center py-8 text-muted-foreground">Loading hypotheses...</div>
        ) : filtered.length === 0 ? (
          <div className="rounded-2xl border border-border bg-sidebar p-8 text-center text-sm text-muted-foreground">
            No {filter === "all" ? "" : filter} hypotheses yet.
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map(h => (
              <div key={h.id} className="rounded-xl border border-border bg-sidebar p-4 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 space-y-1.5">
                    <p className="text-sm font-medium text-foreground">{h.claim}</p>
                    <p className="text-xs text-muted-foreground leading-relaxed">{h.reasoning}</p>
                  </div>
                  <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium capitalize ${statusBadge(h.status)}`}>
                    {h.status}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-xs text-muted-foreground">{new Date(h.created_at).toLocaleString()}</span>
                  {h.status === "pending" && (
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => void resolve(h.id, "confirm")}
                        className="rounded-lg bg-emerald-900 px-3 py-1.5 text-xs text-emerald-100 hover:bg-emerald-800 transition-colors"
                      >
                        Confirm
                      </button>
                      <button
                        type="button"
                        onClick={() => void resolve(h.id, "deny")}
                        className="rounded-lg bg-red-950 px-3 py-1.5 text-xs text-red-200 hover:bg-red-900 transition-colors"
                      >
                        Deny
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
