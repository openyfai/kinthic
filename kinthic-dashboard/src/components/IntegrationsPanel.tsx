"use client";

import { useEffect, useState } from "react";
import { LinkSquare02Icon, Copy01Icon, CheckmarkCircle01Icon, Plug01Icon } from "hugeicons-react";
import { apiFetch } from "@/lib/api";

type McpTool = { name: string; description: string };

type IntegrationsData = {
  mcp_active: boolean;
  http_endpoint: string;
  health_endpoint: string;
  stdio_command: string;
  stdio_command_python: string;
  claude_config: object;
  cursor_config: object;
  tools: McpTool[];
};

export default function IntegrationsPanel() {
  const [data, setData] = useState<IntegrationsData | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [client, setClient] = useState<"claude" | "cursor">("claude");

  useEffect(() => {
    apiFetch("/api/integrations")
      .then((res) => res.json())
      .then(setData)
      .catch((err) => console.warn("Failed to load integrations:", err));
  }, []);

  const copyText = async (key: string, text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 2000);
  };

  const configJson = data
    ? JSON.stringify(client === "cursor" ? data.cursor_config : data.claude_config, null, 2)
    : "";

  if (!data) {
    return (
      <div className="h-full flex items-center justify-center text-[#312E81] animate-pulse">
        Loading integrations...
      </div>
    );
  }

  return (
    <div className="h-full bg-black/40 text-neutral-300 p-6 overflow-y-auto">
      <div className="flex items-center gap-3 mb-6 text-white border-b border-white/10 pb-4">
        <Plug01Icon className="w-7 h-7 text-[#312E81]" />
        <div>
          <h2 className="text-xl font-bold tracking-widest uppercase">Integrations</h2>
          <p className="text-sm text-neutral-500 mt-1">
            Connect Claude Desktop, Cursor, or any MCP client to Silex memory
          </p>
        </div>
      </div>

      <div className="max-w-3xl space-y-8">
        <section className="bg-black/60 border border-white/5 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold uppercase tracking-widest text-neutral-400">Status</h3>
            <span
              className={`text-xs font-mono px-2 py-1 rounded ${
                data.mcp_active ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/20 text-red-400"
              }`}
            >
              {data.mcp_active ? "MCP ACTIVE" : "MCP OFFLINE"}
            </span>
          </div>
          <div className="space-y-3 text-sm">
            <CopyRow
              label="HTTP endpoint"
              value={data.http_endpoint}
              copied={copied === "http"}
              onCopy={() => copyText("http", data.http_endpoint)}
            />
            <CopyRow
              label="stdio bridge"
              value={data.stdio_command}
              copied={copied === "stdio"}
              onCopy={() => copyText("stdio", data.stdio_command)}
            />
            <CopyRow
              label="stdio (Python fallback)"
              value={data.stdio_command_python}
              copied={copied === "stdio_py"}
              onCopy={() => copyText("stdio_py", data.stdio_command_python)}
            />
          </div>
        </section>

        <section className="bg-black/60 border border-white/5 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold uppercase tracking-widest text-neutral-400">Client Config</h3>
            <div className="flex gap-1 bg-black rounded-lg p-1 border border-white/10">
              {(["claude", "cursor"] as const).map((c) => (
                <button
                  key={c}
                  onClick={() => setClient(c)}
                  className={`px-3 py-1 text-xs rounded capitalize ${
                    client === c ? "bg-white/10 text-white" : "text-neutral-500 hover:text-neutral-300"
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
          <pre className="bg-black border border-white/10 rounded-lg p-4 text-xs font-mono text-neutral-300 overflow-x-auto">
            {configJson}
          </pre>
          <button
            onClick={() => copyText("config", configJson)}
            className="mt-3 flex items-center gap-2 px-4 py-2 bg-white/10 hover:bg-white/15 rounded-lg text-sm font-semibold text-white"
          >
            {copied === "config" ? (
              <CheckmarkCircle01Icon className="w-4 h-4 text-emerald-400" />
            ) : (
              <Copy01Icon className="w-4 h-4" />
            )}
            Copy JSON
          </button>
          <p className="mt-3 text-xs text-neutral-500">
            Paste into your MCP client config. Requires kinthic web or daemon running for the stdio bridge to proxy to the gateway.
          </p>
        </section>

        <section className="bg-black/60 border border-white/5 rounded-xl p-5">
          <h3 className="text-sm font-bold uppercase tracking-widest text-neutral-400 mb-4">
            Silex MCP Tools ({data.tools.length})
          </h3>
          <div className="space-y-3">
            {data.tools.map((tool) => (
              <div key={tool.name} className="border-b border-white/5 pb-3 last:border-0">
                <div className="font-mono text-sm text-[#312E81]">{tool.name}</div>
                <div className="text-xs text-neutral-500 mt-1">{tool.description}</div>
              </div>
            ))}
          </div>
        </section>

        <a
          href={data.http_endpoint}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 text-sm text-neutral-400 hover:text-white"
        >
          <LinkSquare02Icon className="w-4 h-4" />
          Open MCP endpoint
        </a>
      </div>
    </div>
  );
}

function CopyRow({
  label,
  value,
  copied,
  onCopy,
}: {
  label: string;
  value: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="min-w-0">
        <div className="text-xs text-neutral-500 uppercase mb-0.5">{label}</div>
        <div className="font-mono text-white truncate">{value}</div>
      </div>
      <button
        onClick={onCopy}
        className="shrink-0 p-2 rounded-lg bg-white/5 hover:bg-white/10 text-neutral-400 hover:text-white"
        title="Copy"
      >
        {copied ? (
          <CheckmarkCircle01Icon className="w-4 h-4 text-emerald-400" />
        ) : (
          <Copy01Icon className="w-4 h-4" />
        )}
      </button>
    </div>
  );
}
