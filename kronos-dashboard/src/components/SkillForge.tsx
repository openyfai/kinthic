"use client";

import { useEffect, useState } from "react";
import { BookOpen01Icon, AiFileIcon } from "hugeicons-react";

export default function SkillForge() {
  const [skills, setSkills] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("http://localhost:8000/api/skills")
      .then((res) => res.json())
      .then((data) => {
        setSkills(data.skills || []);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="h-full bg-black/40 text-neutral-300 p-6 overflow-y-auto">
      <div className="flex items-center gap-3 mb-8 text-cyan-400 border-b border-white/10 pb-4">
        <BookOpen01Icon className="w-7 h-7" />
        <h2 className="text-xl font-bold tracking-widest uppercase">Skill Forge Library</h2>
      </div>

      <p className="text-neutral-400 mb-8 max-w-2xl">
        This repository contains autonomous skills synthesized by the Genesis engine. Kronos automatically 
        distills successful problem-solving trajectories into reusable code blocks.
      </p>

      {loading ? (
        <div className="text-cyan-400 animate-pulse">Scanning skill repository...</div>
      ) : skills.length === 0 ? (
        <div className="text-neutral-500 italic p-8 border border-dashed border-white/10 rounded-xl text-center">
          No synthesized skills found yet. Kronos will generate them automatically over time.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {skills.map((skill, i) => (
            <div key={i} className="bg-black/60 border border-white/10 rounded-xl p-5 hover:border-cyan-500/50 transition-colors group relative overflow-hidden">
              <div className="absolute top-0 left-0 w-1 h-full bg-gradient-to-b from-cyan-400 to-blue-600 opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="flex items-start justify-between mb-3">
                <AiFileIcon className="w-6 h-6 text-cyan-500" />
                <span className="text-xs font-mono text-neutral-500">{(skill.size / 1024).toFixed(1)} KB</span>
              </div>
              <h3 className="text-white font-bold mb-2 truncate">{skill.title}</h3>
              <p className="text-xs text-neutral-400 font-mono whitespace-pre-wrap line-clamp-4">
                {skill.preview}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
