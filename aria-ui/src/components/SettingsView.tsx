"use client";

import { useMemo, useState } from "react";

import { apiUrl, getAuthHeaders, setApiBase, setApiKey } from "@/lib/api";

type ProviderModel = {
  id: string;
  label: string;
  tier?: string;
};

type ProviderInfo = {
  id: string;
  label: string;
  models: ProviderModel[];
};

type SettingsData = {
  provider: string;
  model: string;
  fast_model?: string;
  reasoning_model?: string;
  security?: {
    require_tool_approvals?: boolean;
    browser_actions?: boolean;
    terminal_execution?: boolean;
    code_apply?: boolean;
    background_actions?: boolean;
  };
  usage?: {
    soft_cap_usd?: number | null;
    warning_threshold_usd?: number | null;
    disable_expensive_models?: boolean;
  };
};

interface Props {
  providers: ProviderInfo[];
  settings: SettingsData;
  onSaved: (payload: { settings?: SettingsData }) => void;
}

export default function SettingsView({ providers, settings, onSaved }: Props) {
  const [provider, setProvider] = useState(settings.provider);
  const [model, setModel] = useState(settings.model);
  const [apiKey, setProviderKey] = useState("");
  const [webApiKey, setWebApiKey] = useState("");
  const [apiBase, setLocalApiBase] = useState("");
  const [softCap, setSoftCap] = useState(settings.usage?.soft_cap_usd?.toString() || "");
  const [warningThreshold, setWarningThreshold] = useState(settings.usage?.warning_threshold_usd?.toString() || "");
  const [requireApprovals, setRequireApprovals] = useState(settings.security?.require_tool_approvals ?? true);
  const [browserActions, setBrowserActions] = useState(settings.security?.browser_actions ?? true);
  const [terminalExecution, setTerminalExecution] = useState(settings.security?.terminal_execution ?? false);
  const [codeApply, setCodeApply] = useState(settings.security?.code_apply ?? false);
  const [backgroundActions, setBackgroundActions] = useState(settings.security?.background_actions ?? false);
  const [disableExpensive, setDisableExpensive] = useState(settings.usage?.disable_expensive_models ?? false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const models = useMemo(
    () => providers.find((entry) => entry.id === provider)?.models ?? [],
    [provider, providers],
  );

  async function saveSettings() {
    setSaving(true);
    setError(null);
    try {
      const response = await fetch(apiUrl("/api/settings"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          provider,
          model,
          fast_model: model,
          reasoning_model: models.find((entry) => entry.tier === "reasoning")?.id || model,
          provider_secrets: apiKey ? { [provider]: apiKey } : {},
          web_api_key: webApiKey,
          security: {
            require_tool_approvals: requireApprovals,
            browser_actions: browserActions,
            terminal_execution: terminalExecution,
            code_apply: codeApply,
            background_actions: backgroundActions,
          },
          usage: {
            soft_cap_usd: softCap ? Number(softCap) : null,
            warning_threshold_usd: warningThreshold ? Number(warningThreshold) : null,
            disable_expensive_models: disableExpensive,
          },
        }),
      });
      if (!response.ok) {
        throw new Error("Failed to update settings.");
      }
      if (webApiKey) {
        setApiKey(webApiKey);
      }
      if (apiBase) {
        setApiBase(apiBase);
      }
      onSaved(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update settings.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <div>
          <div className="text-[11px] uppercase tracking-[0.32em] text-white/42">Local control plane</div>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-white">Settings</h1>
          <p className="mt-2 max-w-2xl text-sm text-white/60">
            Switch providers and models, rotate secrets, set local cost guardrails, and tune
            ARIA&apos;s autonomy policy without editing the codebase.
          </p>
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <section className="rounded-[28px] border border-white/10 bg-white/[0.03] p-6">
            <div className="grid gap-4">
              <Field label="Provider">
                <select value={provider} onChange={(e) => {
                  const nextProvider = e.target.value;
                  setProvider(nextProvider);
                  const nextModels = providers.find((entry) => entry.id === nextProvider)?.models ?? [];
                  setModel(nextModels[0]?.id || "");
                }} className={inputClassName}>
                  {providers.map((entry) => (
                    <option key={entry.id} value={entry.id}>{entry.label}</option>
                  ))}
                </select>
              </Field>

              <Field label="Model">
                <select value={model} onChange={(e) => setModel(e.target.value)} className={inputClassName}>
                  {models.map((entry) => (
                    <option key={entry.id} value={entry.id}>{entry.label}</option>
                  ))}
                </select>
              </Field>

              <Field label="New provider API key">
                <input value={apiKey} onChange={(e) => setProviderKey(e.target.value)} className={inputClassName} placeholder="Leave blank to keep the current key" />
              </Field>

              <Field label="New web API key">
                <input value={webApiKey} onChange={(e) => setWebApiKey(e.target.value)} className={inputClassName} placeholder="Stored locally and used for REST + WebSocket auth" />
              </Field>

              <Field label="Override API base URL">
                <input value={apiBase} onChange={(e) => setLocalApiBase(e.target.value)} className={inputClassName} placeholder="Optional client-side override for this browser" />
              </Field>
            </div>
          </section>

          <section className="rounded-[28px] border border-white/10 bg-white/[0.03] p-6">
            <div className="grid gap-3">
              <ToggleRow label="Require tool approvals" checked={requireApprovals} onChange={setRequireApprovals} />
              <ToggleRow label="Allow browser actions" checked={browserActions} onChange={setBrowserActions} />
              <ToggleRow label="Allow terminal execution" checked={terminalExecution} onChange={setTerminalExecution} />
              <ToggleRow label="Allow direct code apply" checked={codeApply} onChange={setCodeApply} />
              <ToggleRow label="Enable background actions" checked={backgroundActions} onChange={setBackgroundActions} />
              <ToggleRow label="Disable expensive models" checked={disableExpensive} onChange={setDisableExpensive} />

              <div className="grid gap-4 pt-2 sm:grid-cols-2">
                <Field label="Soft cap (USD)">
                  <input value={softCap} onChange={(e) => setSoftCap(e.target.value)} className={inputClassName} placeholder="e.g. 10" />
                </Field>
                <Field label="Warning threshold (USD)">
                  <input value={warningThreshold} onChange={(e) => setWarningThreshold(e.target.value)} className={inputClassName} placeholder="e.g. 5" />
                </Field>
              </div>

              {error && <div className="rounded-2xl border border-red-500/20 bg-red-500/8 px-4 py-3 text-sm text-red-200">{error}</div>}

              <button
                type="button"
                onClick={() => void saveSettings()}
                disabled={saving}
                className="mt-2 rounded-2xl bg-white px-4 py-3 text-sm font-medium text-black transition hover:bg-white/90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saving ? "Saving settings..." : "Save settings"}
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-2">
      <span className="text-xs uppercase tracking-[0.22em] text-white/46">{label}</span>
      {children}
    </label>
  );
}

function ToggleRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-4 rounded-2xl border border-white/8 bg-black/30 px-4 py-3 text-sm text-white/84">
      <span>{label}</span>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className={`inline-flex h-7 w-12 items-center rounded-full p-1 transition ${checked ? "bg-white text-black" : "bg-white/10 text-white/55"}`}
      >
        <span className={`h-5 w-5 rounded-full bg-current transition ${checked ? "translate-x-5" : ""}`} />
      </button>
    </label>
  );
}

const inputClassName =
  "w-full rounded-2xl border border-white/10 bg-black/35 px-4 py-3 text-sm text-white outline-none transition placeholder:text-white/28 focus:border-white/25";
