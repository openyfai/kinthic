"use client";

import { useEffect, useState } from "react";
import { Activity01Icon, Database01Icon, NeuralNetworkIcon, AiBrain01Icon, BinaryCodeIcon } from "hugeicons-react";

export default function SystemMetrics() {
  const [metrics, setMetrics] = useState<any>(null);

  useEffect(() => {
    fetch("http://localhost:8000/api/metrics")
      .then((res) => res.json())
      .then((data) => setMetrics(data));
      
    const int = setInterval(() => {
      fetch("http://localhost:8000/api/metrics")
        .then((res) => res.json())
        .then((data) => setMetrics(data));
    }, 5000);
    return () => clearInterval(int);
  }, []);

  const stats = [
    { label: "Epistemic Nodes", value: metrics?.nodes || 0, icon: NeuralNetworkIcon, color: "text-purple-400" },
    { label: "Relational Edges", value: metrics?.edges || 0, icon: Activity01Icon, color: "text-blue-400" },
    { label: "Archived Memories", value: metrics?.memories || 0, icon: Database01Icon, color: "text-emerald-400" },
    { label: "Synthesized Trajectories", value: metrics?.trajectories || 0, icon: AiBrain01Icon, color: "text-amber-400" },
  ];

  return (
    <div className="h-full bg-black/40 text-neutral-300 p-8 flex flex-col justify-center items-center">
      <div className="w-full max-w-4xl">
        <h2 className="text-3xl font-extrabold tracking-widest text-transparent bg-clip-text bg-gradient-to-r from-neutral-200 to-neutral-600 mb-2 uppercase text-center">
          Core Telemetry
        </h2>
        <p className="text-center text-neutral-500 mb-12 uppercase tracking-widest text-sm">Real-time subsystem analytics</p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {stats.map((stat, i) => (
            <div key={i} className="bg-black/60 border border-white/5 rounded-2xl p-6 flex items-center gap-6 shadow-2xl backdrop-blur-sm hover:bg-white/[0.02] transition-colors">
              <div className={`p-4 rounded-xl bg-white/5 ${stat.color}`}>
                <stat.icon className="w-8 h-8" />
              </div>
              <div>
                <div className="text-sm font-semibold tracking-wider text-neutral-400 uppercase mb-1">{stat.label}</div>
                <div className="text-4xl font-mono font-bold text-white">
                  {metrics === null ? "..." : stat.value.toLocaleString()}
                </div>
              </div>
            </div>
          ))}
        </div>
        
        <div className="mt-12 p-6 bg-black/60 border border-white/5 rounded-2xl flex items-center gap-4 text-neutral-400">
          <BinaryCodeIcon className="w-5 h-5" />
          <div className="text-sm">
            Gateway Server: <span className="text-emerald-400 font-mono">ONLINE</span> (Port 8000)
          </div>
        </div>
      </div>
    </div>
  );
}
