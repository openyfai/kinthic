"use client";

import EpistemicGraph from '@/components/EpistemicGraph';
import TerminalOutput from '@/components/TerminalOutput';
import SkillForge from '@/components/SkillForge';
import SystemMetrics from '@/components/SystemMetrics';
import EngineSettings from '@/components/EngineSettings';
import MemoryBrowser from '@/components/MemoryBrowser';
import DataVault from '@/components/DataVault';
import IntegrationsPanel from '@/components/IntegrationsPanel';
import {
  ComputerTerminal01Icon,
  NeuralNetworkIcon,
  Settings01Icon,
  BookOpen01Icon,
  Activity01Icon,
  Database01Icon,
  FloppyDiskIcon,
  Plug01Icon,
} from 'hugeicons-react';
import { useState } from 'react';

type Tab =
  | 'graph'
  | 'terminal'
  | 'skills'
  | 'memories'
  | 'data'
  | 'integrations'
  | 'metrics'
  | 'settings';

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>('graph');

  const navBtn = (tab: Tab, label: string, Icon: typeof NeuralNetworkIcon) => (
    <button
      onClick={() => setActiveTab(tab)}
      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors font-medium ${
        activeTab === tab ? 'bg-white/10 text-white' : 'text-neutral-400 hover:bg-white/5 hover:text-neutral-200'
      }`}
    >
      <Icon className={`w-5 h-5 ${activeTab === tab ? 'text-[#312E81]' : ''}`} />
      {label}
    </button>
  );

  return (
    <main className="flex h-screen w-screen relative">
      <aside className="w-[320px] shrink-0 border-r border-white/5 bg-black/40 backdrop-blur-xl flex flex-col z-20 shadow-2xl shadow-black">
        <div className="p-6 border-b border-white/5 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-extrabold tracking-widest text-transparent bg-clip-text bg-gradient-to-r from-white to-neutral-400">
              KINTHIC
            </h1>
            <div className="mt-2 flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#312E81] opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-[#312E81]"></span>
              </span>
              <span className="text-xs font-semibold tracking-wider text-[#312E81]/80 uppercase">
                Studio Online
              </span>
            </div>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto p-4 space-y-2">
          <div className="text-xs font-bold text-neutral-500 uppercase tracking-widest mb-4 mt-2 px-2">Core</div>
          {navBtn('graph', 'Epistemic Topology', NeuralNetworkIcon)}
          {navBtn('terminal', 'Terminal Output', ComputerTerminal01Icon)}
          {navBtn('skills', 'Skill Forge', BookOpen01Icon)}
          {navBtn('memories', 'Memory Browser', Database01Icon)}

          <div className="text-xs font-bold text-neutral-500 uppercase tracking-widest mb-4 mt-6 px-2">System</div>
          {navBtn('data', 'Data Vault', FloppyDiskIcon)}
          {navBtn('integrations', 'Integrations', Plug01Icon)}
          {navBtn('metrics', 'System Metrics', Activity01Icon)}
        </nav>

        <div className="p-4 border-t border-white/5">
          <button
            onClick={() => setActiveTab('settings')}
            className={`w-full flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm font-semibold transition-colors ${
              activeTab === 'settings' ? 'bg-white/10 text-white' : 'text-neutral-400 hover:text-white hover:bg-white/10'
            }`}
          >
            <Settings01Icon className="w-4 h-4" />
            Engine Settings
          </button>
        </div>
      </aside>

      <section className="flex-1 relative bg-black/20 overflow-hidden">
        <div className="absolute inset-0">
          {activeTab === 'graph' && <EpistemicGraph />}
          {activeTab === 'terminal' && <TerminalOutput />}
          {activeTab === 'skills' && <SkillForge />}
          {activeTab === 'memories' && <MemoryBrowser />}
          {activeTab === 'data' && <DataVault />}
          {activeTab === 'integrations' && <IntegrationsPanel />}
          {activeTab === 'metrics' && <SystemMetrics />}
          {activeTab === 'settings' && <EngineSettings />}
        </div>

        {activeTab === 'graph' && (
          <div className="absolute top-6 left-1/2 -translate-x-1/2 z-10 pointer-events-none">
            <div className="bg-black/60 backdrop-blur-md border border-white/10 rounded-full px-5 py-2 shadow-xl flex items-center gap-3">
              <NeuralNetworkIcon className="w-4 h-4 text-[#312E81]" />
              <h2 className="text-sm font-bold text-white tracking-wide whitespace-nowrap">
                World Model State
              </h2>
              <div className="w-1 h-1 rounded-full bg-neutral-600"></div>
              <p className="text-xs text-neutral-400 whitespace-nowrap">Live rendering</p>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
