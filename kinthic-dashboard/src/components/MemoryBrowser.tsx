"use client";

import { useCallback, useEffect, useState } from "react";
import { Database01Icon, Search01Icon, Delete02Icon } from "hugeicons-react";
import { apiFetch } from "@/lib/api";

type Memory = {
  id: string;
  content: string;
  importance: number;
  confidence: number;
  memory_type: string;
  tags: string[];
  created_at: string;
  access_count: number;
};

export default function MemoryBrowser() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const limit = 20;

  const loadMemories = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        offset: String(offset),
        limit: String(limit),
      });
      if (query) params.set("q", query);
      const res = await apiFetch(`/api/memories?${params}`);
      const data = await res.json();
      setMemories(data.memories || []);
      setTotal(data.total || 0);
    } catch (err) {
      console.warn("Failed to load memories:", err);
    } finally {
      setLoading(false);
    }
  }, [offset, query]);

  useEffect(() => {
    loadMemories();
  }, [loadMemories]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setOffset(0);
    setQuery(searchInput.trim());
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this memory permanently?")) return;
    setDeletingId(id);
    try {
      const res = await apiFetch(`/api/memories/${id}?confirm=true`, { method: "DELETE" });
      if (res.ok) {
        setMemories((prev) => prev.filter((m) => m.id !== id));
        setTotal((t) => Math.max(0, t - 1));
      }
    } catch (err) {
      console.error(err);
    } finally {
      setDeletingId(null);
    }
  };

  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  return (
    <div className="h-full bg-black/40 text-neutral-300 p-6 overflow-y-auto">
      <div className="flex items-center gap-3 mb-6 text-white border-b border-white/10 pb-4">
        <Database01Icon className="w-7 h-7 text-[#312E81]" />
        <div>
          <h2 className="text-xl font-bold tracking-widest uppercase">Memory Browser</h2>
          <p className="text-sm text-neutral-500 mt-1">
            Search and inspect the Silex memory store ({total.toLocaleString()} total)
          </p>
        </div>
      </div>

      <form onSubmit={handleSearch} className="flex gap-2 mb-6 max-w-xl">
        <div className="relative flex-1">
          <Search01Icon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-500" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search memories..."
            className="w-full bg-black border border-white/10 rounded-lg pl-10 pr-4 py-2.5 text-white text-sm focus:outline-none focus:border-[#312E81]"
          />
        </div>
        <button
          type="submit"
          className="px-4 py-2.5 bg-white/10 hover:bg-white/15 rounded-lg text-sm font-semibold text-white transition-colors"
        >
          Search
        </button>
        {query && (
          <button
            type="button"
            onClick={() => { setQuery(""); setSearchInput(""); setOffset(0); }}
            className="px-4 py-2.5 text-neutral-400 hover:text-white text-sm"
          >
            Clear
          </button>
        )}
      </form>

      {loading ? (
        <div className="text-[#312E81] animate-pulse">Loading memories...</div>
      ) : memories.length === 0 ? (
        <div className="text-neutral-500 italic p-8 border border-dashed border-white/10 rounded-xl text-center">
          {query ? "No memories match your search." : "No memories stored yet."}
        </div>
      ) : (
        <div className="space-y-3 max-w-4xl">
          {memories.map((m) => (
            <div
              key={m.id}
              className="bg-black/60 border border-white/5 rounded-xl p-4 hover:border-white/10 transition-colors group"
            >
              <div className="flex justify-between gap-4">
                <p className="text-white text-sm leading-relaxed flex-1">{m.content}</p>
                <button
                  onClick={() => handleDelete(m.id)}
                  disabled={deletingId === m.id}
                  className="opacity-0 group-hover:opacity-100 p-2 text-neutral-500 hover:text-red-400 transition-all disabled:opacity-50"
                  title="Delete memory"
                >
                  <Delete02Icon className="w-4 h-4" />
                </button>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-neutral-500">
                <span className="font-mono bg-white/5 px-2 py-0.5 rounded">{m.memory_type}</span>
                <span>importance {m.importance.toFixed(2)}</span>
                <span>confidence {m.confidence.toFixed(2)}</span>
                <span>{m.access_count} reads</span>
                {m.tags?.map((tag) => (
                  <span key={tag} className="text-[#312E81]">#{tag}</span>
                ))}
              </div>
              <div className="mt-2 text-[10px] font-mono text-neutral-600 truncate">{m.id}</div>
            </div>
          ))}
        </div>
      )}

      {total > limit && (
        <div className="flex items-center justify-between mt-8 max-w-4xl text-sm text-neutral-400">
          <button
            disabled={offset === 0}
            onClick={() => setOffset((o) => Math.max(0, o - limit))}
            className="px-4 py-2 rounded-lg bg-white/5 hover:bg-white/10 disabled:opacity-30"
          >
            Previous
          </button>
          <span>Page {page} of {totalPages}</span>
          <button
            disabled={offset + limit >= total}
            onClick={() => setOffset((o) => o + limit)}
            className="px-4 py-2 rounded-lg bg-white/5 hover:bg-white/10 disabled:opacity-30"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
