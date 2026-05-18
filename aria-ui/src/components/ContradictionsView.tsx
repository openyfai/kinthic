"use client";

import { useEffect, useState } from "react";
import { apiUrl, getAuthHeaders } from "@/lib/api";

interface Contradiction {
  id: string;
  belief_a: string;
  belief_b: string;
  resolution: string | null;
  status: string;
  created_at: string;
}

function statusBadge(status: string) {
  if (status === "resolved") return "bg-emerald-900/40 text-emerald-300 border border-emerald-800/40";
  return "bg-red-900/40 text-red-300 border border-red-800/40";
}

export default function ContradictionsView() {
  const [contradictions, setContradictions] = useState<Contradiction[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "unresolved" | "resolved">("unresolved");

  useEffect(() => {
    fetch(apiUrl("/api/contradictions"), { headers: getAuthHeaders() })
      .then(res => res.ok ? res.json() : [])
      .then(data => { setContradictions(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const counts = {
    all: contradictions.length,
    unresolved: contradictions.filter(c => c.status !== "resolved").length,
    resolved: contradictions.filter(c => c.status === "resolved").length,
  };

  const filtered = filter === "all"
    ? contradictions
    : filter === "resolved"
      ? contradictions.filter(c => c.status === "resolved")
      : contradictions.filter(c => c.status !== "resolved");

  return (
    <div className="flex-1 overflow-y-auto px-4 py-8">
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Contradictions</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Beliefs VYN has detected as mutually inconsistent.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {(["unresolved", "resolved", "all"] as const).map(f => (
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
          <div className="text-center py-8 text-muted-foreground">Loading contradictions...</div>
        ) : filtered.length === 0 ? (
          <div className="rounded-2xl border border-border bg-sidebar p-8 text-center text-sm text-muted-foreground">
            {filter === "unresolved"
              ? "No unresolved contradictions — VYN's beliefs are consistent."
              : `No ${filter} contradictions.`}
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map(c => (
              <div key={c.id} className="rounded-xl border border-border bg-sidebar p-4 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium capitalize ${statusBadge(c.status)}`}>
                    {c.status}
                  </span>
                  <span className="text-xs text-muted-foreground">{new Date(c.created_at).toLocaleString()}</span>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded-lg border border-border bg-background p-3">
                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1.5">Belief A</div>
                    <p className="text-sm text-foreground leading-relaxed">{c.belief_a}</p>
                  </div>
                  <div className="rounded-lg border border-border bg-background p-3">
                    <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1.5">Belief B</div>
                    <p className="text-sm text-foreground leading-relaxed">{c.belief_b}</p>
                  </div>
                </div>
                {c.resolution && (
                  <div className="rounded-lg border border-emerald-900/40 bg-emerald-950/20 p-3">
                    <div className="text-[10px] uppercase tracking-widest text-emerald-400/70 mb-1.5">Resolution</div>
                    <p className="text-sm text-emerald-200 leading-relaxed">{c.resolution}</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
