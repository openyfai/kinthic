"use client";

import { useCallback, useEffect, useState } from "react";
import { apiUrl, getAuthHeaders } from "@/lib/api";

interface Memory {
  id: string;
  content: string;
  memory_type: string;
  source: string;
  importance: string;
  confidence: number;
  tags: string[];
  created_at: string;
}

function typeBadge(type: string) {
  const map: Record<string, string> = {
    normative:  "bg-purple-900/40 text-purple-300 border border-purple-800/40",
    character:  "bg-blue-900/40   text-blue-300   border border-blue-800/40",
    semantic:   "bg-emerald-900/40 text-emerald-300 border border-emerald-800/40",
    episodic:   "bg-amber-900/30  text-amber-300  border border-amber-800/30",
    procedural: "bg-zinc-800/60   text-zinc-300   border border-zinc-700/40",
  };
  return map[type] ?? "bg-zinc-800/60 text-zinc-300 border border-zinc-700/40";
}

export default function MemoriesView() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [typeFilter, setTypeFilter] = useState("all");

  const load = useCallback(async () => {
    setLoading(true);
    const res = await fetch(apiUrl("/api/memories"), { headers: getAuthHeaders() });
    if (res.ok) setMemories(await res.json());
    setLoading(false);
  }, []);

  useEffect(() => { void load(); }, [load]);

  const search = async () => {
    if (!query.trim()) { void load(); return; }
    setSearching(true);
    const res = await fetch(apiUrl(`/api/memories/search?q=${encodeURIComponent(query)}`), { headers: getAuthHeaders() });
    if (res.ok) setMemories(await res.json());
    setSearching(false);
  };

  const archive = async (id: string) => {
    await fetch(apiUrl(`/api/memories/${id}`), { method: "DELETE", headers: getAuthHeaders() });
    setMemories(prev => prev.filter(m => m.id !== id));
  };

  const types = ["all", ...Array.from(new Set(memories.map(m => m.memory_type)))];
  const filtered = typeFilter === "all" ? memories : memories.filter(m => m.memory_type === typeFilter);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-8">
      <div className="max-w-3xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Memories</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {memories.length} stored memories. Normative and character memories are identity-relevant.
          </p>
        </div>

        {/* Search */}
        <div className="flex gap-2">
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && void search()}
            placeholder="Semantic search..."
            className="flex-1 rounded-xl border border-white/10 bg-black/35 px-4 py-2.5 text-sm text-white outline-none placeholder:text-white/30 focus:border-white/25"
          />
          <button
            type="button"
            onClick={() => void search()}
            disabled={searching}
            className="rounded-xl bg-white px-4 py-2.5 text-sm font-medium text-black hover:bg-white/90 disabled:opacity-60"
          >
            {searching ? "..." : "Search"}
          </button>
          {query && (
            <button
              type="button"
              onClick={() => { setQuery(""); void load(); }}
              className="rounded-xl border border-white/10 px-3 py-2.5 text-sm text-muted-foreground hover:text-white"
            >
              Clear
            </button>
          )}
        </div>

        {/* Type filter */}
        <div className="flex flex-wrap gap-2">
          {types.map(t => (
            <button
              key={t}
              type="button"
              onClick={() => setTypeFilter(t)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors capitalize ${
                typeFilter === t
                  ? "bg-white text-black"
                  : "border border-white/10 bg-white/[0.04] text-white/60 hover:bg-white/[0.08]"
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="text-center py-8 text-muted-foreground">Loading memories...</div>
        ) : filtered.length === 0 ? (
          <div className="rounded-2xl border border-border bg-sidebar p-8 text-center text-sm text-muted-foreground">
            No memories found.
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map(m => (
              <div key={m.id} className="rounded-xl border border-border bg-sidebar p-4 space-y-2">
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm text-foreground leading-relaxed flex-1">{m.content}</p>
                  <button
                    type="button"
                    onClick={() => void archive(m.id)}
                    className="shrink-0 text-xs text-muted-foreground hover:text-red-400 transition-colors px-2 py-1 rounded-lg hover:bg-red-950/30"
                  >
                    Archive
                  </button>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className={`rounded-full px-2 py-0.5 capitalize ${typeBadge(m.memory_type)}`}>{m.memory_type}</span>
                  <span className="text-muted-foreground capitalize">{m.source}</span>
                  <span className="text-muted-foreground">·</span>
                  <span className="text-muted-foreground capitalize">{m.importance}</span>
                  <span className="text-muted-foreground">·</span>
                  <span className="text-muted-foreground">{Math.round(m.confidence * 100)}% confidence</span>
                  {m.tags.length > 0 && (
                    <>
                      <span className="text-muted-foreground">·</span>
                      <span className="text-muted-foreground">{m.tags.join(", ")}</span>
                    </>
                  )}
                  <span className="ml-auto text-muted-foreground">{new Date(m.created_at).toLocaleDateString()}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
