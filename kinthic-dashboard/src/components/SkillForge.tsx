"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BookOpen01Icon,
  Search01Icon,
  RefreshIcon,
  Download01Icon,
  Delete02Icon,
  Cancel01Icon,
} from "hugeicons-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { apiFetch } from "@/lib/api";

type Skill = {
  name: string;
  description: string;
  trust_level: string;
  trigger?: string;
  source?: string;
  layout?: string;
  size_bytes?: number;
};

type CatalogEntry = {
  name: string;
  description: string;
  trust_level?: string;
  installed?: boolean;
  tags?: string[];
};

const TRUST_COLORS: Record<string, string> = {
  core: "text-emerald-400 bg-emerald-400/10 border-emerald-400/30",
  verified: "text-indigo-400 bg-indigo-400/10 border-indigo-400/30",
  community: "text-neutral-400 bg-white/5 border-white/10",
};

export default function SkillForge() {
  const [tab, setTab] = useState<"installed" | "catalog">("installed");
  const [skills, setSkills] = useState<Skill[]>([]);
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [statusIsError, setStatusIsError] = useState(false);
  const [urlInstall, setUrlInstall] = useState("");
  const [detail, setDetail] = useState<{ name: string; body: string; metadata: Skill } | null>(null);

  const setStatusMessage = (message: string | null, isError = false) => {
    setStatus(message);
    setStatusIsError(isError);
  };

  const loadInstalled = useCallback(async () => {
    const res = await apiFetch("/api/skills");
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Failed to load installed skills");
    }
    const data = await res.json();
    setSkills(data.skills || []);
  }, []);

  const loadCatalog = useCallback(async (q?: string) => {
    const params = q ? `?q=${encodeURIComponent(q)}` : "";
    const res = await apiFetch(`/api/skills/catalog${params}`);
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Failed to load skill catalog");
    }
    const data = await res.json();
    setCatalog(data.entries || []);
  }, []);

  useEffect(() => {
    setLoading(true);
    setLoadError(null);
    Promise.all([loadInstalled(), loadCatalog()])
      .catch((err) => setLoadError(err.message || "Could not reach the skills API"))
      .finally(() => setLoading(false));
  }, [loadInstalled, loadCatalog]);

  const openDetail = async (name: string) => {
    try {
      const res = await apiFetch(`/api/skills/${encodeURIComponent(name)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Not found");
      setDetail({ name, body: data.body, metadata: data.metadata || {} });
      setStatusMessage(null);
    } catch (err: any) {
      setStatusMessage(err.message || "Could not load skill", true);
    }
  };

  const openCatalogPreview = async (entry: CatalogEntry) => {
    try {
      const res = await apiFetch(`/api/skills/${encodeURIComponent(entry.name)}`);
      if (res.ok) {
        const data = await res.json();
        setDetail({ name: entry.name, body: data.body, metadata: data.metadata || entry });
        setStatusMessage(null);
        return;
      }
    } catch {
      // Fall back to catalog metadata preview
    }
    const tags = entry.tags?.length ? `\n\nTags: ${entry.tags.join(", ")}` : "";
    setDetail({
      name: entry.name,
      body: `# ${entry.name}\n\n${entry.description}${tags}\n\n---\n\n*Install this skill to load full instructions.*`,
      metadata: {
        name: entry.name,
        description: entry.description,
        trust_level: entry.trust_level || "community",
        source: entry.installed ? "installed" : "catalog",
      },
    });
  };

  const handleInstall = async (name: string) => {
    setBusy(name);
    setStatusMessage(null);
    try {
      const res = await apiFetch("/api/skills/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Install failed");
      setStatusMessage(data.message || `Installed ${name}`);
      await loadInstalled();
      await loadCatalog(query);
    } catch (err: any) {
      setStatusMessage(err.message, true);
    } finally {
      setBusy(null);
    }
  };

  const handleUrlInstall = async (e: React.FormEvent) => {
    e.preventDefault();
    const target = urlInstall.trim();
    if (!target.startsWith("https://")) {
      setStatusMessage("URL install requires an https:// link to a .md skill file", true);
      return;
    }
    setBusy("url");
    setStatusMessage(null);
    try {
      const res = await apiFetch("/api/skills/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: target }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Install failed");
      setStatusMessage(data.message || "Skill installed from URL");
      setUrlInstall("");
      await loadInstalled();
      await loadCatalog(query);
    } catch (err: any) {
      setStatusMessage(err.message, true);
    } finally {
      setBusy(null);
    }
  };

  const handleUninstall = async (name: string) => {
    if (!confirm(`Remove skill '${name}'?`)) return;
    setBusy(name);
    try {
      const res = await apiFetch("/api/skills/uninstall", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Uninstall failed");
      setStatusMessage(data.message || `Removed ${name}`);
      if (detail?.name === name) setDetail(null);
      await loadInstalled();
      await loadCatalog(query);
    } catch (err: any) {
      setStatusMessage(err.message, true);
    } finally {
      setBusy(null);
    }
  };

  const handleRefreshHub = async () => {
    setBusy("refresh");
    try {
      const res = await apiFetch("/api/skills/catalog/refresh", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Refresh failed");
      setStatusMessage(data.message || "Catalog refreshed");
      await loadCatalog(query);
    } catch (err: any) {
      setStatusMessage(err.message, true);
    } finally {
      setBusy(null);
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    loadCatalog(query.trim());
    setTab("catalog");
  };

  const trustBadge = (level: string) => {
    const cls = TRUST_COLORS[level] || TRUST_COLORS.community;
    return (
      <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded border ${cls}`}>
        {level}
      </span>
    );
  };

  return (
    <div className="h-full bg-black/40 text-neutral-300 flex flex-col overflow-hidden">
      <div className="p-6 border-b border-white/10 shrink-0">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-3">
            <BookOpen01Icon className="w-7 h-7 text-[#312E81]" />
            <div>
              <h2 className="text-xl font-bold tracking-widest uppercase text-white">Skill Forge</h2>
              <p className="text-sm text-neutral-500 mt-1">
                Workflow skills — bundled, synthesized, and community packs
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => {
                setLoadError(null);
                Promise.all([loadInstalled(), loadCatalog(query)]).catch((err) =>
                  setLoadError(err.message || "Reload failed")
                );
              }}
              className="p-2.5 rounded-lg bg-white/5 hover:bg-white/10"
              title="Reload"
            >
              <RefreshIcon className="w-5 h-5" />
            </button>
            <button
              onClick={handleRefreshHub}
              disabled={busy === "refresh"}
              className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/15 text-sm font-semibold disabled:opacity-50"
            >
              Refresh Hub
            </button>
          </div>
        </div>

        {loadError && (
          <div className="mt-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-sm text-red-300">
            {loadError}
          </div>
        )}

        {status && (
          <div
            className={`mt-4 p-3 rounded-lg text-sm border ${
              statusIsError
                ? "bg-red-500/10 border-red-500/30 text-red-300"
                : "bg-[#312E81]/20 border-[#312E81]/40"
            }`}
          >
            {status}
          </div>
        )}

        <div className="flex gap-4 mt-4 items-center flex-wrap">
          <div className="flex gap-1 bg-black rounded-lg p-1 border border-white/10">
            {(["installed", "catalog"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-4 py-1.5 text-sm rounded capitalize ${
                  tab === t ? "bg-white/10 text-white" : "text-neutral-500 hover:text-neutral-300"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
          <form onSubmit={handleSearch} className="flex gap-2 flex-1 min-w-[200px] max-w-md">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search catalog..."
              className="flex-1 bg-black border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#312E81]"
            />
            <button type="submit" className="p-2 rounded-lg bg-white/10 hover:bg-white/15">
              <Search01Icon className="w-4 h-4" />
            </button>
          </form>
          <form onSubmit={handleUrlInstall} className="flex gap-2 flex-1 min-w-[240px] max-w-lg">
            <input
              value={urlInstall}
              onChange={(e) => setUrlInstall(e.target.value)}
              placeholder="Install from https://…/skill.md"
              className="flex-1 bg-black border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#312E81]"
            />
            <button
              type="submit"
              disabled={busy === "url"}
              className="px-3 py-2 rounded-lg bg-[#312E81]/40 hover:bg-[#312E81]/60 text-xs font-semibold disabled:opacity-50"
            >
              URL Install
            </button>
          </form>
        </div>
      </div>

      <div className="flex-1 overflow-hidden flex">
        <div className={`flex-1 overflow-y-auto p-6 ${detail ? "hidden lg:block lg:w-1/2" : "w-full"}`}>
          {loading ? (
            <div className="text-[#312E81] animate-pulse">Loading skills...</div>
          ) : tab === "installed" ? (
            skills.length === 0 ? (
              <div className="p-8 border border-dashed border-white/10 rounded-xl text-center text-neutral-500">
                No skills loaded. Install from the catalog or let Genesis synthesize from successful trajectories.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {skills.map((skill) => (
                  <SkillCard
                    key={skill.name}
                    skill={skill}
                    busy={busy === skill.name}
                    onView={() => openDetail(skill.name)}
                    onUninstall={() => handleUninstall(skill.name)}
                    trustBadge={trustBadge}
                  />
                ))}
              </div>
            )
          ) : catalog.length === 0 ? (
            <div className="p-8 border border-dashed border-white/10 rounded-xl text-center text-neutral-500">
              No catalog entries match. Try Refresh Hub to pull remote skills.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {catalog.map((entry) => (
                <div
                  key={entry.name}
                  className="bg-black/60 border border-white/5 rounded-xl p-4 hover:border-white/15 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <h3 className="font-bold text-white truncate">{entry.name}</h3>
                    {trustBadge(entry.trust_level || "community")}
                  </div>
                  <p className="text-xs text-neutral-400 line-clamp-3 mb-3">{entry.description}</p>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => openCatalogPreview(entry)}
                      className="text-xs text-white bg-white/10 px-3 py-1 rounded-lg hover:bg-white/15"
                    >
                      Preview
                    </button>
                    {entry.installed ? (
                      <span className="text-xs text-emerald-400">Installed</span>
                    ) : (
                      <button
                        onClick={() => handleInstall(entry.name)}
                        disabled={busy === entry.name}
                        className="flex items-center gap-1 text-xs font-semibold text-[#312E81] hover:text-indigo-300 disabled:opacity-50"
                      >
                        <Download01Icon className="w-3.5 h-3.5" />
                        Install
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {detail && (
          <div className="w-full lg:w-1/2 border-l border-white/10 flex flex-col bg-black/60">
            <div className="p-4 border-b border-white/10 flex items-center justify-between shrink-0">
              <div>
                <h3 className="font-bold text-white">{detail.name}</h3>
                <div className="flex gap-2 mt-1">
                  {detail.metadata.trust_level && trustBadge(detail.metadata.trust_level)}
                  {detail.metadata.source && (
                    <span className="text-[10px] text-neutral-500 uppercase">{detail.metadata.source}</span>
                  )}
                </div>
              </div>
              <button onClick={() => setDetail(null)} className="p-2 text-neutral-400 hover:text-white">
                <Cancel01Icon className="w-5 h-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6 prose prose-invert prose-sm max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{detail.body}</ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SkillCard({
  skill,
  busy,
  onView,
  onUninstall,
  trustBadge,
}: {
  skill: Skill;
  busy: boolean;
  onView: () => void;
  onUninstall: () => void;
  trustBadge: (level: string) => React.ReactNode;
}) {
  return (
    <div className="bg-black/60 border border-white/5 rounded-xl p-4 hover:border-[#312E81]/40 transition-colors group">
      <div className="flex items-start justify-between gap-2 mb-2">
        <button onClick={onView} className="font-bold text-white truncate text-left hover:text-[#312E81]">
          {skill.name}
        </button>
        {trustBadge(skill.trust_level || "community")}
      </div>
      <p className="text-xs text-neutral-400 line-clamp-2 mb-2">{skill.description}</p>
      <div className="flex flex-wrap gap-2 text-[10px] text-neutral-600 uppercase">
        {skill.source && <span>{skill.source}</span>}
        {skill.layout && <span>{skill.layout}</span>}
        {skill.trigger && <span className="normal-case text-neutral-500">trigger: {skill.trigger}</span>}
      </div>
      <div className="flex gap-2 mt-3 opacity-0 group-hover:opacity-100 transition-opacity">
        <button onClick={onView} className="text-xs text-white bg-white/10 px-3 py-1 rounded-lg hover:bg-white/15">
          View
        </button>
        <button
          onClick={onUninstall}
          disabled={busy}
          className="text-xs text-red-400 hover:text-red-300 disabled:opacity-50 flex items-center gap-1"
        >
          <Delete02Icon className="w-3.5 h-3.5" />
          Remove
        </button>
      </div>
    </div>
  );
}
