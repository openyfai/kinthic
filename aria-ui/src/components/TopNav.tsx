'use client';

import { Message01Icon as MessageSquare, Target01Icon as Target, AiNetworkIcon as Network, Add01Icon as Plus } from 'hugeicons-react';
import { SessionMeta } from '@/hooks/useAriaSocket';

export type ViewType = 'chat' | 'goals' | 'graph';

interface Props {
  sessions: SessionMeta[];
  activeSessionId: string | null;
  currentView: ViewType;
  onViewChange: (view: ViewType) => void;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
}

const navItems: { id: ViewType; label: string; icon: React.ReactNode }[] = [
  { id: 'chat',  label: 'Chat',            icon: <MessageSquare size={15} /> },
  { id: 'goals', label: 'Goals',           icon: <Target size={15} /> },
  { id: 'graph', label: 'Knowledge Graph', icon: <Network size={15} /> },
];

export default function TopNav({ sessions, activeSessionId, currentView, onViewChange, onSelectSession, onNewChat }: Props) {
  return (
    <header className="w-full flex-shrink-0 flex items-center gap-1 px-4 h-12 border-b border-border bg-background z-40">

      {/* View tabs */}
      <nav className="flex items-center gap-0.5">
        {navItems.map(item => (
          <button
            key={item.id}
            onClick={() => onViewChange(item.id)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-[13px] font-medium transition-colors ${
              currentView === item.id
                ? 'bg-secondary text-foreground'
                : 'text-muted-foreground hover:text-foreground hover:bg-secondary/60'
            }`}
          >
            {item.icon}
            {item.label}
          </button>
        ))}
      </nav>

      {/* Spacer */}
      <div className="flex-1" />

      {/* New Chat */}
      <button
        onClick={onNewChat}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[13px] font-medium text-muted-foreground hover:text-foreground hover:bg-secondary/60 transition-colors"
      >
        <Plus size={15} />
        New Chat
      </button>
    </header>
  );
}
