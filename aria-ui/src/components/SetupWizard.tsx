"use client";

import { useMemo, useState } from "react";

import { apiUrl, getAuthHeaders, setApiKey } from "@/lib/api";

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

type SettingsSnapshot = {
  provider: string;
  model: string;
  security?: {
    require_tool_approvals?: boolean;
    browser_actions?: boolean;
    terminal_execution?: boolean;
    code_apply?: boolean;
    background_actions?: boolean;
  };
};

interface Props {
  providers: ProviderInfo[];
  initialSettings: SettingsSnapshot;
  onComplete: (payload: { settings: SettingsSnapshot; status: { setup_completed: boolean } }) => void;
}

export default function SetupWizard({ providers, initialSettings, onComplete }: Props) {
  const [provider, setProvider] = useState(initialSettings.provider || providers[0]?.id || "gemini");
  const [model, setModel] = useState(initialSettings.model || providers[0]?.models?.[0]?.id || "");
  const [apiKey, setProviderKey] = useState("");
  const [webApiKey, setWebApiKey] = useState("");
  const [requireApprovals, setRequireApprovals] = useState(initialSettings.security?.require_tool_approvals ?? true);
  const [browserActions, setBrowserActions] = useState(initialSettings.security?.browser_actions ?? true);
  const [terminalExecution, setTerminalExecution] = useState(initialSettings.security?.terminal_execution ?? false);
  const [codeApply, setCodeApply] = useState(initialSettings.security?.code_apply ?? false);
  const [backgroundActions, setBackgroundActions] = useState(initialSettings.security?.background_actions ?? false);
  const [submitting, setSubmitting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testMessage, setTestMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const models = useMemo(
    () => providers.find((entry) => entry.id === provider)?.models ?? [],
    [provider, providers],
  );

  async function testProvider() {
    setTesting(true);
    setError(null);
    setTestMessage(null);
    try {
      const response = await fetch(apiUrl("/api/setup/test-provider"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          provider,
          api_key: apiKey,
        }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.message || "Provider test failed.");
      }
      setTestMessage(payload.message || "Provider settings look valid.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Provider test failed.");
    } finally {
      setTesting(false);
    }
  }

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch(apiUrl("/api/setup"), {
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
        }),
      });
      if (!response.ok) {
        throw new Error("Failed to save setup.");
      }
      if (webApiKey) {
        setApiKey(webApiKey);
      }
      onComplete(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save setup.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/75 px-6 py-10 backdrop-blur-md">
      <div className="w-full max-w-4xl rounded-[32px] border border-white/10 bg-[#050505] p-8 shadow-[0_30px_120px_rgba(0,0,0,0.6)]">
        <div className="grid gap-8 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="space-y-6">
            <div>
              <div className="text-[11px] uppercase tracking-[0.32em] text-white/45">First-run setup</div>
              <h1 className="mt-3 text-4xl font-semibold tracking-tight text-white">Bring ARIA online.</h1>
              <p className="mt-3 max-w-xl text-sm leading-6 text-white/62">
                Choose your provider, set a model, lock down high-risk actions, and finish the
                local onboarding without editing source files.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <CardStat label="Local-first" value="Data stays on your machine" />
              <CardStat label="Safe defaults" value="Approvals on, writes off" />
              <CardStat label="Model choice" value="Switch providers later" />
              <CardStat label="Operator control" value="Dashboard + CLI commands" />
            </div>

            <div className="rounded-3xl border border-emerald-500/20 bg-emerald-500/6 p-5 text-sm text-emerald-100/90">
              Recommended launch posture: keep approvals enabled, keep terminal/code editing disabled,
              and only set a web API key if you plan to expose the web server beyond localhost.
            </div>
          </div>

          <div className="rounded-[28px] border border-white/10 bg-white/[0.03] p-6">
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

              <Field label="Provider API key">
                <input value={apiKey} onChange={(e) => setProviderKey(e.target.value)} placeholder="Paste the selected provider key" className={inputClassName} />
              </Field>

              <Field label="Web API key (optional)">
                <input value={webApiKey} onChange={(e) => setWebApiKey(e.target.value)} placeholder="Recommended if you expose the web UI remotely" className={inputClassName} />
              </Field>

              <div className="grid gap-3 pt-2">
                <ToggleRow label="Require tool approvals" checked={requireApprovals} onChange={setRequireApprovals} />
                <ToggleRow label="Allow browser actions" checked={browserActions} onChange={setBrowserActions} />
                <ToggleRow label="Allow terminal execution" checked={terminalExecution} onChange={setTerminalExecution} />
                <ToggleRow label="Allow direct code apply" checked={codeApply} onChange={setCodeApply} />
                <ToggleRow label="Enable background actions" checked={backgroundActions} onChange={setBackgroundActions} />
              </div>

              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => void testProvider()}
                  disabled={testing || (provider !== "ollama" && !apiKey)}
                  className="rounded-2xl border border-white/12 bg-white/[0.05] px-4 py-3 text-sm font-medium text-white transition hover:bg-white/[0.08] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {testing ? "Testing..." : "Test provider"}
                </button>
              </div>

              {testMessage && <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/8 px-4 py-3 text-sm text-emerald-200">{testMessage}</div>}
              {error && <div className="rounded-2xl border border-red-500/20 bg-red-500/8 px-4 py-3 text-sm text-red-200">{error}</div>}

              <button
                type="button"
                onClick={() => void submit()}
                disabled={submitting || !provider || !model}
                className="mt-2 rounded-2xl bg-white px-4 py-3 text-sm font-medium text-black transition hover:bg-white/90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {submitting ? "Saving setup..." : "Finish setup"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function CardStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.03] px-4 py-4">
      <div className="text-[11px] uppercase tracking-[0.24em] text-white/42">{label}</div>
      <div className="mt-2 text-sm text-white/85">{value}</div>
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
