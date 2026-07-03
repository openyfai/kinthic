"use client";

import { useEffect, useState } from "react";
import { Settings01Icon, FloppyDiskIcon, Shield01Icon, CpuIcon, AiLockIcon } from "hugeicons-react";

export default function EngineSettings() {
  const [settings, setSettings] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch("http://localhost:8000/api/settings")
      .then((res) => res.json())
      .then((data) => setSettings(data))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await fetch("http://localhost:8000/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      // brief flash to indicate save
      setTimeout(() => setSaving(false), 500);
    } catch (e) {
      console.error(e);
      setSaving(false);
    }
  };

  const updateSecurity = (key: string, val: boolean) => {
    setSettings((prev: any) => ({
      ...prev,
      security: { ...prev.security, [key]: val }
    }));
  };

  const updateRoot = (key: string, val: string) => {
    setSettings((prev: any) => ({ ...prev, [key]: val }));
  };

  const updateTelegram = (key: string, val: boolean) => {
    setSettings((prev: any) => ({
      ...prev,
      telegram: { ...prev.telegram, [key]: val }
    }));
  };

  if (loading || !settings) {
    return <div className="h-full flex items-center justify-center text-[#F5A623] animate-pulse">Loading settings...</div>;
  }

  return (
    <div className="h-full bg-black/40 text-neutral-300 p-8 overflow-y-auto">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-12">
        <div className="flex items-center gap-4 text-white">
          <Settings01Icon className="w-8 h-8 text-neutral-400" />
          <div>
            <h2 className="text-2xl font-bold tracking-widest uppercase">Engine Configuration</h2>
            <p className="text-sm text-neutral-500 mt-1">Manage core SILEX settings and security policies.</p>
          </div>
        </div>
        <button 
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-6 py-2.5 bg-white text-black hover:bg-neutral-200 rounded-full font-bold transition-colors disabled:opacity-50"
        >
          <FloppyDiskIcon className="w-5 h-5" />
          {saving ? "Saving..." : "Save Configuration"}
        </button>
      </div>

      <div className="max-w-4xl space-y-16 pb-20">
        
        {/* Model Configuration */}
        <section>
          <div className="flex items-center gap-3 text-white font-semibold mb-6">
            <CpuIcon className="w-5 h-5 text-neutral-400" />
            <h3 className="text-lg tracking-wide">Neural Providers</h3>
          </div>
          
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-neutral-500 uppercase mb-2">Active Provider</label>
              <select 
                value={settings.provider || "gemini"} 
                onChange={(e) => updateRoot("provider", e.target.value)}
                className="w-full bg-black border border-white/10 rounded-lg p-3 text-white focus:outline-none focus:border-blue-500"
              >
                <option value="gemini">Google Gemini</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
                <option value="ollama">Ollama (Local)</option>
                <option value="custom">Custom Configuration</option>
              </select>
            </div>
            
            <div>
              <label className="block text-xs font-bold text-neutral-500 uppercase mb-2">Primary Model</label>
              <input 
                type="text" 
                value={settings.model || ""} 
                onChange={(e) => updateRoot("model", e.target.value)}
                className="w-full bg-black border border-white/10 rounded-lg p-3 text-white focus:outline-none focus:border-blue-500 font-mono text-sm"
              />
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-neutral-500 uppercase mb-2">Fast Model (Tools)</label>
                <input 
                  type="text" 
                  value={settings.fast_model || ""} 
                  onChange={(e) => updateRoot("fast_model", e.target.value)}
                  className="w-full bg-black border border-white/10 rounded-lg p-3 text-white focus:outline-none focus:border-blue-500 font-mono text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-neutral-500 uppercase mb-2">Reasoning Model (Critique)</label>
                <input 
                  type="text" 
                  value={settings.reasoning_model || ""} 
                  onChange={(e) => updateRoot("reasoning_model", e.target.value)}
                  className="w-full bg-black border border-white/10 rounded-lg p-3 text-white focus:outline-none focus:border-blue-500 font-mono text-sm"
                />
              </div>
            </div>
          </div>
        </section>

        {/* Security & Autonomy */}
        <section>
          <div className="flex items-center gap-3 text-white font-semibold mb-6">
            <Shield01Icon className="w-5 h-5 text-neutral-400" />
            <h3 className="text-lg tracking-wide">Autonomy & Safety</h3>
          </div>

          <div className="space-y-4">
            <label className="flex items-center justify-between py-2 cursor-pointer group">
              <div>
                <div className="text-white font-medium group-hover:text-neutral-300 transition-colors">Require Tool Approvals</div>
                <div className="text-sm text-neutral-500 mt-1">Require human confirmation before executing high-risk tools.</div>
              </div>
              <div className="relative inline-flex items-center">
                <input 
                  type="checkbox" 
                  checked={settings.security?.require_tool_approvals ?? true}
                  onChange={(e) => updateSecurity("require_tool_approvals", e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-white/20 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#34C759]"></div>
              </div>
            </label>

            <label className="flex items-center justify-between py-2 cursor-pointer group">
              <div>
                <div className="text-white font-medium group-hover:text-neutral-300 transition-colors">Terminal Execution</div>
                <div className="text-sm text-neutral-500 mt-1">Allow Kronos to run arbitrary CLI commands in the workspace.</div>
              </div>
              <div className="relative inline-flex items-center">
                <input 
                  type="checkbox" 
                  checked={settings.security?.terminal_execution ?? false}
                  onChange={(e) => updateSecurity("terminal_execution", e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-white/20 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#34C759]"></div>
              </div>
            </label>

            <label className="flex items-center justify-between py-2 cursor-pointer group">
              <div>
                <div className="text-white font-medium group-hover:text-neutral-300 transition-colors">Code Application</div>
                <div className="text-sm text-neutral-500 mt-1">Allow direct file modification and code injection without manual patching.</div>
              </div>
              <div className="relative inline-flex items-center">
                <input 
                  type="checkbox" 
                  checked={settings.security?.code_apply ?? false}
                  onChange={(e) => updateSecurity("code_apply", e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-white/20 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#34C759]"></div>
              </div>
            </label>
            
            <label className="flex items-center justify-between py-2 cursor-pointer group">
              <div>
                <div className="text-white font-medium group-hover:text-neutral-300 transition-colors">Background Autonomy</div>
                <div className="text-sm text-neutral-500 mt-1">Allow Kronos to proactively wake up and execute asynchronous goals.</div>
              </div>
              <div className="relative inline-flex items-center">
                <input 
                  type="checkbox" 
                  checked={settings.security?.background_actions ?? false}
                  onChange={(e) => updateSecurity("background_actions", e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-white/20 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#34C759]"></div>
              </div>
            </label>
          </div>
        </section>

        {/* Telegram specific settings */}
        <section>
          <div className="flex items-center gap-3 text-white font-semibold mb-6">
            <AiLockIcon className="w-5 h-5 text-neutral-400" />
            <h3 className="text-lg tracking-wide">Access Control</h3>
          </div>

          <div className="space-y-4">
             <label className="flex items-center justify-between py-2 cursor-pointer group">
              <div>
                <div className="text-white font-medium group-hover:text-neutral-300 transition-colors">Telegram Public Mode</div>
                <div className="text-sm text-neutral-500 mt-1">Allow ANY user on Telegram to interact with this node without a pairing code.</div>
              </div>
              <div className="relative inline-flex items-center">
                <input 
                  type="checkbox" 
                  checked={settings.telegram?.public_mode ?? false}
                  onChange={(e) => updateTelegram("public_mode", e.target.checked)}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-white/20 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#34C759]"></div>
              </div>
            </label>
          </div>
        </section>

      </div>
    </div>
  );
}
