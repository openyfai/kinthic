"use client";

import { createPortal } from "react-dom";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";

import { apiUrl, getAuthHeaders, setApiKey } from "@/lib/api";
import { cn } from "@/lib/utils";

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
  onCancel?: () => void;
  variant?: "first-run" | "review";
}

const STEPS = 4;

export default function SetupWizard({
  providers,
  initialSettings,
  onComplete,
  onCancel,
  variant = "first-run",
}: Props) {
  const [step, setStep] = useState(0);
  const [provider, setProvider] = useState(initialSettings.provider || providers[0]?.id || "gemini");
  const [model, setModel] = useState(initialSettings.model || providers[0]?.models?.[0]?.id || "");
  const [apiKey, setProviderKey] = useState("");
  const [webApiKey, setWebApiKey] = useState("");
  const [telegramToken, setTelegramToken] = useState("");
  const [requireApprovals, setRequireApprovals] = useState(initialSettings.security?.require_tool_approvals ?? true);
  const [browserActions, setBrowserActions] = useState(initialSettings.security?.browser_actions ?? true);
  const [terminalExecution, setTerminalExecution] = useState(initialSettings.security?.terminal_execution ?? false);
  const [codeApply, setCodeApply] = useState(initialSettings.security?.code_apply ?? false);
  const [backgroundActions, setBackgroundActions] = useState(initialSettings.security?.background_actions ?? false);
  const [submitting, setSubmitting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testMessage, setTestMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pairingCode, setPairingCode] = useState("");
  /** Only one custom dropdown open at a time — avoids overlap and native-select quirks. */

  // Generate pairing code on mount or when needed
  useEffect(() => {
    if (!pairingCode) {
      setPairingCode("PAIR-" + Math.random().toString(36).substring(2, 6).toUpperCase());
    }
  }, [pairingCode]);
  const [openSelect, setOpenSelect] = useState<"provider" | "model" | null>(null);

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
          model,
          api_key: apiKey,
        }),
      });
      const payload = (await response.json()) as {
        ok?: boolean;
        message?: string;
        hint?: string;
        detail?: string;
      };
      if (!response.ok) {
        const detail = typeof payload.detail === "string" ? payload.detail : response.statusText;
        throw new Error(detail || "Provider test failed.");
      }
      if (!payload.ok) {
        const parts = [payload.message, payload.hint].filter(Boolean) as string[];
        throw new Error(parts.length ? parts.join(" ") : "Provider test failed.");
      }
      const okParts = [payload.message, payload.hint].filter(Boolean) as string[];
      setTestMessage(okParts.length ? okParts.join(" — ") : "Provider credentials work.");
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
          telegram_token: telegramToken,
          telegram_pairing_code: telegramToken && pairingCode ? pairingCode : undefined,
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
    <div
      className="fixed inset-0 z-[200] flex min-h-[100dvh] flex-col bg-background text-foreground"
      role="dialog"
      aria-modal="true"
      aria-labelledby="setup-wizard-title"
    >
      {variant === "review" && onCancel && (
        <div className="flex shrink-0 justify-end border-b border-border px-4 py-3 md:px-8">
          <button
            type="button"
            onClick={onCancel}
            className="text-sm text-muted-foreground transition hover:text-foreground"
          >
            Close
          </button>
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
        <div className="mx-auto flex w-full max-w-xl flex-1 flex-col px-6 pb-28 pt-12 md:px-8 md:pt-16">
          {step === 0 && (
            <section className="animate-in fade-in slide-in-from-bottom-2 duration-300">
              <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
                {variant === "review" ? "Setup" : "Welcome"}
              </p>
              <h1 id="setup-wizard-title" className="mt-3 text-3xl font-semibold tracking-tight md:text-4xl">
                {variant === "review" ? "Review your ARIA setup" : "Welcome to ARIA"}
              </h1>
              <p className="mt-4 max-w-lg text-sm leading-relaxed text-muted-foreground">
                {variant === "review"
                  ? "Nothing changes until you finish. You can close anytime."
                  : "A local-first agent with memory, an inspectable graph, and governed tools. A few quick steps to connect your model—no code edits."}
              </p>

              <ul className="mt-10 grid gap-3 sm:grid-cols-2">
                {[
                  { t: "Runs locally", d: "Your data stays on this machine." },
                  { t: "Safe defaults", d: "Approvals on; risky tools off until you choose." },
                  { t: "Any provider", d: "Switch models in Settings later." },
                  { t: "You’re in control", d: "Operator panel and CLI for policy." },
                ].map((item) => (
                  <li
                    key={item.t}
                    className="rounded-xl border border-border bg-card/30 px-4 py-4 transition hover:bg-card/50"
                  >
                    <div className="text-sm font-medium text-foreground">{item.t}</div>
                    <div className="mt-1 text-xs leading-snug text-muted-foreground">{item.d}</div>
                  </li>
                ))}
              </ul>

              <p className="mt-8 rounded-xl border border-border/80 bg-muted/30 px-4 py-3 text-xs leading-relaxed text-muted-foreground">
                Tip: keep tool approvals enabled and avoid exposing the web UI without a web API key.
              </p>
            </section>
          )}

          {step === 1 && (
            <section className="animate-in fade-in slide-in-from-bottom-2 duration-300">
              <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
                Connection
              </p>
              <h2 className="mt-3 text-2xl font-semibold tracking-tight md:text-3xl">Model & credentials</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                Choose a provider and paste keys. For Ollama, leave the provider key blank if unused.
              </p>

              <div className="mt-10 grid gap-6">
                <OnboardingSelect
                  label="Provider"
                  value={provider}
                  options={providers.map((p) => ({ id: p.id, label: p.label }))}
                  onChange={(id) => {
                    setProvider(id);
                    const nextModels = providers.find((entry) => entry.id === id)?.models ?? [];
                    setModel(nextModels[0]?.id ?? "");
                  }}
                  menuKey="provider"
                  openSelect={openSelect}
                  setOpenSelect={setOpenSelect}
                />

                <OnboardingSelect
                  label="Model"
                  value={model}
                  options={models.map((m) => ({ id: m.id, label: m.label }))}
                  onChange={setModel}
                  menuKey="model"
                  openSelect={openSelect}
                  setOpenSelect={setOpenSelect}
                />

                <Field label="Provider API key">
                  <input
                    value={apiKey}
                    onChange={(e) => setProviderKey(e.target.value)}
                    placeholder="Paste key from your provider’s dashboard"
                    className={inputClassName}
                    autoComplete="off"
                  />
                </Field>

                <Field label="Web API key (optional)">
                  <input
                    value={webApiKey}
                    onChange={(e) => setWebApiKey(e.target.value)}
                    placeholder="If you access this UI remotely"
                    className={inputClassName}
                    autoComplete="off"
                  />
                </Field>

                <div className="flex flex-wrap items-center gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => void testProvider()}
                    disabled={testing || (provider !== "ollama" && !apiKey)}
                    className="rounded-xl border border-border bg-secondary px-5 py-2.5 text-sm font-medium text-foreground transition hover:bg-secondary/80 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {testing ? "Testing…" : "Test connection"}
                  </button>
                </div>

                {testMessage && (
                  <div className="rounded-xl border border-border bg-muted/40 px-4 py-3 text-sm text-foreground">
                    {testMessage}
                  </div>
                )}
                {error && (
                  <div className="rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                    {error}
                  </div>
                )}
              </div>
            </section>
          )}

          {step === 2 && (
            <section className="animate-in fade-in slide-in-from-bottom-2 duration-300">
              <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
                Integration
              </p>
              <h2 className="mt-3 text-2xl font-semibold tracking-tight md:text-3xl">Telegram Setup</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                Connect ARIA to Telegram for a 24/7 background AI experience. Chat from anywhere, anytime.
              </p>

              <div className="mt-10 grid gap-6">
                <Field label="Telegram Bot Token (optional)">
                  <input
                    value={telegramToken}
                    onChange={(e) => setTelegramToken(e.target.value)}
                    placeholder="1234567890:AAH... (from BotFather)"
                    className={inputClassName}
                    autoComplete="off"
                  />
                  <p className="mt-2 text-[13px] text-muted-foreground">
                    Get this by talking to{" "}
                    <a href="https://t.me/botfather" target="_blank" rel="noreferrer" className="underline">
                      @BotFather
                    </a>{" "}
                    on Telegram and creating a new bot. Keep it blank if you only want the Web UI.
                  </p>
                </Field>
                
                {telegramToken && (
                  <div className="rounded-xl border border-primary/20 bg-primary/5 p-5">
                    <p className="mb-2 text-sm font-semibold text-primary">Your Pairing Code</p>
                    <div className="flex items-center gap-4">
                       <code className="rounded bg-background px-3 py-2 text-lg font-mono tracking-widest text-primary shadow-sm border border-primary/20">
                         {pairingCode}
                       </code>
                    </div>
                    <p className="mt-3 text-[13px] text-muted-foreground leading-relaxed">
                      When you finish setup, send this exact code as the first message to your bot.
                      The bot will be locked and will refuse all messages until you unlock it with this code, 
                      securing it to your Telegram account.
                    </p>
                  </div>
                )}
              </div>
            </section>
          )}

          {step === 3 && (
            <section className="animate-in fade-in slide-in-from-bottom-2 duration-300">
              <p className="text-[11px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
                Autonomy
              </p>
              <h2 className="mt-3 text-2xl font-semibold tracking-tight md:text-3xl">What ARIA can do</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                Tune permissions. You can change these anytime in Settings.
              </p>

              <div className="mt-10 grid max-w-lg gap-3">
                <ToggleRow label="Require tool approvals" checked={requireApprovals} onChange={setRequireApprovals} />
                <ToggleRow label="Allow browser actions" checked={browserActions} onChange={setBrowserActions} />
                <ToggleRow
                  label="Allow terminal execution"
                  checked={terminalExecution}
                  onChange={setTerminalExecution}
                />
                <ToggleRow label="Allow direct code apply" checked={codeApply} onChange={setCodeApply} />
                <ToggleRow
                  label="Enable background actions"
                  checked={backgroundActions}
                  onChange={setBackgroundActions}
                />
              </div>

              {error && step === 3 && (
                <div className="mt-6 rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                  {error}
                </div>
              )}

              <button
                type="button"
                onClick={() => void submit()}
                disabled={submitting || !provider || !model}
                className="mt-10 w-full max-w-xs rounded-xl bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? "Saving…" : "Finish setup"}
              </button>
            </section>
          )}

          <nav className="mt-auto flex min-h-[72px] items-center justify-between pt-10">
            <div>
              {step > 0 && (
                <button
                  type="button"
                  onClick={() => {
                    setStep((s) => Math.max(0, s - 1));
                    setError(null);
                  }}
                  className="text-sm text-muted-foreground transition hover:text-foreground"
                >
                  Back
                </button>
              )}
            </div>
            <div className="flex items-center gap-6">
              {variant === "review" && onCancel && step === 0 && (
                <button
                  type="button"
                  onClick={onCancel}
                  className="text-sm text-muted-foreground transition hover:text-foreground"
                >
                  Close
                </button>
              )}
              {step < STEPS - 1 && (
                <button
                  type="button"
                  onClick={() => {
                    const next = Math.min(STEPS - 1, step + 1);
                    if (next !== 1) setOpenSelect(null);
                    setStep(next);
                    setError(null);
                  }}
                  className="rounded-xl bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground transition hover:opacity-90"
                >
                  Next
                </button>
              )}
            </div>
          </nav>
        </div>
      </div>

      <div className="pointer-events-none fixed bottom-0 left-0 right-0 flex justify-center border-t border-transparent bg-background pb-safe pb-6 pt-2">
        <div className="flex items-center gap-2" aria-hidden>
          {Array.from({ length: STEPS }).map((_, i) => (
            <span
              key={i}
              className={
                i === step
                  ? "h-1.5 w-6 rounded-full bg-foreground transition-all"
                  : "h-1.5 w-1.5 rounded-full bg-muted-foreground/35 transition-all"
              }
            />
          ))}
        </div>
      </div>
    </div>
  );
}

type SelectKey = "provider" | "model";

function OnboardingSelect({
  label,
  value,
  options,
  onChange,
  menuKey,
  openSelect,
  setOpenSelect,
}: {
  label: string;
  value: string;
  options: { id: string; label: string }[];
  onChange: (id: string) => void;
  menuKey: SelectKey;
  openSelect: SelectKey | null;
  setOpenSelect: (v: SelectKey | null) => void;
}) {
  const isOpen = openSelect === menuKey;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({});

  const updatePosition = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const margin = 8;
    const maxMenuH = 280;
    const sideMenuWidth = 240; // Clean, fixed width when opening to the side

    // Calculate space around the trigger
    const spaceRight = window.innerWidth - r.right - margin;
    const spaceLeft = r.left - margin;
    const spaceBelow = window.innerHeight - r.bottom - margin;
    const spaceAbove = r.top - margin;
    
    // Determine if we can open to the side
    const canOpenRight = spaceRight >= sideMenuWidth;
    const canOpenLeft = spaceLeft >= sideMenuWidth;

    if (canOpenRight || canOpenLeft) {
      // Open to the side (prefer right)
      const openLeft = !canOpenRight && canOpenLeft;
      
      // Vertical placement for side menu: align top with button top
      const spaceBelowTop = window.innerHeight - r.top - margin;
      const spaceAboveBottom = r.bottom - margin;
      const openUp = spaceBelowTop < maxMenuH && spaceAboveBottom > spaceBelowTop;
      
      const maxH = openUp ? Math.min(maxMenuH, spaceAboveBottom - margin) : Math.min(maxMenuH, spaceBelowTop - margin);
      
      setMenuStyle({
        position: "fixed",
        left: openLeft ? "auto" : r.right + margin,
        right: openLeft ? window.innerWidth - r.left + margin : "auto",
        top: openUp ? "auto" : r.top,
        bottom: openUp ? window.innerHeight - r.bottom : "auto",
        width: sideMenuWidth,
        maxHeight: maxH,
        zIndex: 400,
      });
    } else {
      // Fallback: open below or above
      const openUp = spaceBelow < 140 && spaceAbove > spaceBelow;
      const maxH = Math.min(maxMenuH, openUp ? spaceAbove - margin : spaceBelow - margin);

      setMenuStyle({
        position: "fixed",
        left: r.left,
        width: r.width,
        top: openUp ? "auto" : r.bottom + margin,
        bottom: openUp ? window.innerHeight - r.top + margin : "auto",
        maxHeight: maxH,
        zIndex: 400,
      });
    }
  }, []);

  useLayoutEffect(() => {
    if (!isOpen) return;
    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [isOpen, updatePosition, options.length, value]);

  useEffect(() => {
    if (!isOpen) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (triggerRef.current?.contains(t)) return;
      const menu = document.getElementById(`onboarding-select-menu-${menuKey}`);
      if (menu?.contains(t)) return;
      setOpenSelect(null);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [isOpen, menuKey, setOpenSelect]);

  useEffect(() => {
    if (!isOpen) return;
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpenSelect(null);
    };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [isOpen, setOpenSelect]);

  const selected = options.find((o) => o.id === value);

  const menu =
    isOpen &&
    typeof document !== "undefined" &&
    createPortal(
      <div
        id={`onboarding-select-menu-${menuKey}`}
        role="listbox"
        className="overflow-auto rounded-xl border border-border bg-popover py-1 shadow-[0_16px_48px_rgba(0,0,0,0.55)]"
        style={menuStyle}
      >
        {options.map((opt) => (
          <button
            key={opt.id}
            type="button"
            role="option"
            aria-selected={opt.id === value}
            className={cn(
              "flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm transition hover:bg-muted/80",
              opt.id === value && "bg-muted text-foreground",
            )}
            onClick={() => {
              onChange(opt.id);
              setOpenSelect(null);
            }}
          >
            <span className="min-w-4 text-xs text-muted-foreground">
              {opt.id === value ? "✓" : ""}
            </span>
            <span>{opt.label}</span>
          </button>
        ))}
      </div>,
      document.body,
    );

  return (
    <div className="grid gap-2">
      <span className="text-sm font-medium text-foreground">{label}</span>
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={label}
        onClick={() => setOpenSelect(isOpen ? null : menuKey)}
        className={cn(
          "flex w-full items-center justify-between gap-3 rounded-xl border border-border bg-background px-4 py-3 text-left text-sm text-foreground shadow-sm outline-none transition",
          "hover:border-ring/60 focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30",
          isOpen && "border-ring ring-2 ring-ring/25",
        )}
      >
        <span className="truncate">{selected?.label ?? "Choose…"}</span>
        <ChevronDown flipped={isOpen} />
      </button>
      {menu}
    </div>
  );
}

function ChevronDown({ flipped }: { flipped: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className={cn("shrink-0 text-muted-foreground transition-transform", flipped && "rotate-180")}
      aria-hidden
    >
      <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-2">
      <span className="text-sm font-medium text-foreground">{label}</span>
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
    <label className="flex cursor-pointer items-center justify-between gap-4 rounded-xl border border-border px-4 py-3.5 text-sm text-foreground transition hover:bg-muted/30">
      <span>{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`inline-flex h-7 w-11 shrink-0 items-center rounded-full p-0.5 transition ${
          checked ? "bg-primary" : "bg-muted"
        }`}
      >
        <span
          className={`h-6 w-6 rounded-full bg-primary-foreground shadow transition ${
            checked ? "translate-x-4" : "translate-x-0"
          }`}
        />
      </button>
    </label>
  );
}

const inputClassName =
  "w-full rounded-xl border border-border bg-background px-4 py-3 text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus:border-ring focus:ring-1 focus:ring-ring";
