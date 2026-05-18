"use client";

import { useState, useEffect, useCallback } from "react";
import { apiUrl, getAuthHeaders } from "@/lib/api";

interface BenchmarkRun {
  id?: string;
  run_at?: string;
  score?: number;
  total?: number;
  passed?: number;
  failed?: number;
  results?: Array<{ name: string; passed: boolean; detail?: string }>;
}

export default function BenchmarkView() {
  const [history, setHistory] = useState<BenchmarkRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    const res = await fetch(apiUrl("/api/benchmark/history"), { headers: getAuthHeaders() });
    if (res.ok) setHistory(await res.json());
    setLoading(false);
  }, []);

  useEffect(() => { void loadHistory(); }, [loadHistory]);

  const runBenchmark = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await fetch(apiUrl("/api/benchmark/run"), { method: "POST", headers: getAuthHeaders() });
      if (!res.ok) throw new Error("Benchmark run failed.");
      await loadHistory();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to run benchmark.");
    } finally {
      setRunning(false);
    }
  };

  const latest = history[0];

  return (
    <div className="flex-1 overflow-y-auto px-4 py-8">
      <div className="max-w-3xl mx-auto space-y-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Benchmark</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Evaluate VYN&apos;s reasoning quality across a fixed test suite.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void runBenchmark()}
            disabled={running}
            className="rounded-xl bg-white px-4 py-2.5 text-sm font-medium text-black hover:bg-white/90 disabled:opacity-60 transition-colors"
          >
            {running ? "Running…" : "Run now"}
          </button>
        </div>

        {error && (
          <div className="rounded-xl border border-red-900 bg-red-950/30 p-4 text-sm text-red-300">{error}</div>
        )}

        {latest && (
          <section className="rounded-2xl border border-border bg-sidebar p-5 space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">Latest run</h2>
              <span className="text-xs text-muted-foreground">
                {latest.run_at ? new Date(latest.run_at).toLocaleString() : ""}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-xl bg-background p-3 text-center">
                <div className="text-2xl font-semibold text-foreground">{latest.score ?? "—"}</div>
                <div className="text-xs text-muted-foreground mt-1">Score</div>
              </div>
              <div className="rounded-xl bg-background p-3 text-center">
                <div className="text-2xl font-semibold text-emerald-400">{latest.passed ?? 0}</div>
                <div className="text-xs text-muted-foreground mt-1">Passed</div>
              </div>
              <div className="rounded-xl bg-background p-3 text-center">
                <div className="text-2xl font-semibold text-red-400">{latest.failed ?? 0}</div>
                <div className="text-xs text-muted-foreground mt-1">Failed</div>
              </div>
            </div>
            {latest.results && latest.results.length > 0 && (
              <div className="space-y-1.5">
                {latest.results.map((r, i) => (
                  <div key={i} className="flex items-start gap-3 rounded-lg bg-background px-3 py-2 text-sm">
                    <span className={r.passed ? "text-emerald-400" : "text-red-400"}>{r.passed ? "✓" : "✗"}</span>
                    <div className="flex-1">
                      <span className="font-medium text-foreground">{r.name}</span>
                      {r.detail && <p className="text-xs text-muted-foreground mt-0.5">{r.detail}</p>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {loading ? (
          <div className="text-center py-4 text-muted-foreground text-sm">Loading history...</div>
        ) : history.length > 1 ? (
          <section className="rounded-2xl border border-border bg-sidebar p-5 space-y-3">
            <h2 className="text-sm font-semibold">History</h2>
            <div className="space-y-2">
              {history.slice(1).map((run, i) => (
                <div key={i} className="flex items-center justify-between rounded-xl bg-background px-4 py-2.5 text-sm">
                  <span className="text-muted-foreground">{run.run_at ? new Date(run.run_at).toLocaleString() : `Run ${i + 2}`}</span>
                  <div className="flex items-center gap-4">
                    <span className="text-emerald-400 text-xs">{run.passed ?? 0} passed</span>
                    <span className="text-red-400 text-xs">{run.failed ?? 0} failed</span>
                    <span className="font-medium">{run.score ?? "—"}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        ) : !latest ? (
          <div className="rounded-2xl border border-border bg-sidebar p-8 text-center text-sm text-muted-foreground">
            No benchmark runs yet. Click &quot;Run now&quot; to start.
          </div>
        ) : null}
      </div>
    </div>
  );
}
