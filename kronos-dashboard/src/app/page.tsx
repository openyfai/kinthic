"use client";

import EpistemicGraph from '@/components/EpistemicGraph';
import TerminalOutput from '@/components/TerminalOutput';
import SkillForge from '@/components/SkillForge';
import SystemMetrics from '@/components/SystemMetrics';
import EngineSettings from '@/components/EngineSettings';
import { ComputerTerminal01Icon, NeuralNetworkIcon, Settings01Icon, BookOpen01Icon, Activity01Icon } from 'hugeicons-react';
import { useState } from 'react';

export default function Home() {
  const [activeTab, setActiveTab] = useState<'graph' | 'terminal' | 'skills' | 'metrics' | 'settings'>('graph');

  return (
    <main className="flex h-screen w-screen relative">
      {/* Sidebar / Left Panel */}
      <aside className="w-[320px] shrink-0 border-r border-white/5 bg-black/40 backdrop-blur-xl flex flex-col z-20 shadow-2xl shadow-black">
        <div className="p-6 border-b border-white/5 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-extrabold tracking-widest text-transparent bg-clip-text bg-gradient-to-r from-white to-neutral-400">
              KRONOS
            </h1>
            <div className="mt-2 flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#F5A623] opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-[#F5A623]"></span>
              </span>
              <span className="text-xs font-semibold tracking-wider text-[#F5A623]/80 uppercase">
                Studio Online
              </span>
            </div>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto p-4 space-y-2">
          <div className="text-xs font-bold text-neutral-500 uppercase tracking-widest mb-4 mt-2 px-2">Navigation</div>
          
          <button 
            onClick={() => setActiveTab('graph')}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors font-medium ${activeTab === 'graph' ? 'bg-white/10 text-white' : 'text-neutral-400 hover:bg-white/5 hover:text-neutral-200'}`}
          >
            <NeuralNetworkIcon className={`w-5 h-5 ${activeTab === 'graph' ? 'text-[#F5A623]' : ''}`} />
            Epistemic Topology
          </button>
          
          <button 
            onClick={() => setActiveTab('terminal')}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors font-medium ${activeTab === 'terminal' ? 'bg-white/10 text-white' : 'text-neutral-400 hover:bg-white/5 hover:text-neutral-200'}`}
          >
            <ComputerTerminal01Icon className={`w-5 h-5 ${activeTab === 'terminal' ? 'text-[#F5A623]' : ''}`} />
            Terminal Output
          </button>
          
          <button 
            onClick={() => setActiveTab('skills')}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors font-medium ${activeTab === 'skills' ? 'bg-white/10 text-white' : 'text-neutral-400 hover:bg-white/5 hover:text-neutral-200'}`}
          >
            <BookOpen01Icon className={`w-5 h-5 ${activeTab === 'skills' ? 'text-[#F5A623]' : ''}`} />
            Skill Forge
          </button>
          
          <button 
            onClick={() => setActiveTab('metrics')}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors font-medium ${activeTab === 'metrics' ? 'bg-white/10 text-white' : 'text-neutral-400 hover:bg-white/5 hover:text-neutral-200'}`}
          >
            <Activity01Icon className={`w-5 h-5 ${activeTab === 'metrics' ? 'text-[#F5A623]' : ''}`} />
            System Metrics
          </button>
        </nav>

        <div className="p-4 border-t border-white/5">
          <button 
            onClick={() => setActiveTab('settings')}
            className={`w-full flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm font-semibold transition-colors ${activeTab === 'settings' ? 'bg-white/10 text-white' : 'text-neutral-400 hover:text-white hover:bg-white/10'}`}
          >
            <Settings01Icon className="w-4 h-4" />
            Engine Settings
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <section className="flex-1 relative bg-black/20 overflow-hidden">
        <div className="absolute inset-0">
          {activeTab === 'graph' && <EpistemicGraph />}
          {activeTab === 'terminal' && <TerminalOutput />}
          {activeTab === 'skills' && <SkillForge />}
          {activeTab === 'metrics' && <SystemMetrics />}
          {activeTab === 'settings' && <EngineSettings />}
        </div>
        
        {/* Graph Overlay UI (only show on Graph tab) */}
        {activeTab === 'graph' && (
          <div className="absolute top-6 left-1/2 -translate-x-1/2 z-10 pointer-events-none">
            <div className="bg-black/60 backdrop-blur-md border border-white/10 rounded-full px-5 py-2 shadow-xl flex items-center gap-3">
              <NeuralNetworkIcon className="w-4 h-4 text-[#F5A623]" />
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
