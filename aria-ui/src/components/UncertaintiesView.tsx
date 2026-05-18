"use client";

import { useEffect, useState } from "react";
import { apiUrl, getAuthHeaders } from "@/lib/api";

interface Uncertainty {
  id: string;
  topic: string;
  why_uncertain: string;
  status: string;
  created_at: string;
}

export default function UncertaintiesView() {
  const [uncertainties, setUncertainties] = useState<Uncertainty[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(apiUrl("/api/uncertainties"), { headers: getAuthHeaders() })
      .then(res => res.ok ? res.json() : [])
      .then(data => { setUncertainties(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const open   = uncertainties.filter(u => u.status === "open");
  const closed = uncertainties.filter(u => u.status !== "open");

  return (
    <div className="flex-1 overflow-y-auto px-4 py-8">
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Uncertainties</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Topics VYN flagged as uncertain. {open.length} open, {closed.length} resolved.
          </p>
        </div>
        {loading ? (
          <div className="text-center py-8 text-muted-foreground">Loading...</div>
        ) : uncertainties.length === 0 ? (
          <div className="rounded-2xl border border-border bg-sidebar p-8 text-center text-sm text-muted-foreground">
            No uncertainties recorded yet.
          </div>
        ) : (
          <>
            {open.length > 0 && (
              <section className="space-y-3">
                <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Open</h2>
                {open.map(u => (
                  <div key={u.id} className="rounded-xl border border-amber-900/40 bg-amber-950/10 p-4 space-y-1.5">
                    <p className="text-sm font-medium text-amber-200">{u.topic}</p>
                    <p className="text-xs text-amber-200/60 leading-relaxed">{u.why_uncertain}</p>
                    <p className="text-xs text-muted-foreground">{new Date(u.created_at).toLocaleString()}</p>
                  </div>
                ))}
              </section>
            )}
            {closed.length > 0 && (
              <section className="space-y-3">
                <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Resolved</h2>
                {closed.map(u => (
                  <div key={u.id} className="rounded-xl border border-border bg-sidebar p-4 space-y-1.5 opacity-60">
                    <p className="text-sm font-medium text-foreground">{u.topic}</p>
                    <p className="text-xs text-muted-foreground leading-relaxed">{u.why_uncertain}</p>
                    <p className="text-xs text-muted-foreground">{new Date(u.created_at).toLocaleString()}</p>
                  </div>
                ))}
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}
