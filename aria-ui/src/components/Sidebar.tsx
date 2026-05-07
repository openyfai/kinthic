import { Message01Icon as MessageSquare, Target01Icon as Target, AiNetworkIcon as Network, Add01Icon as Plus, Settings01Icon as Settings } from 'hugeicons-react';
import { SessionMeta } from '@/hooks/useAriaSocket';

export type ViewType = 'chat' | 'goals' | 'graph' | 'operator';

interface Props {
  isOpen: boolean;
  toggle: () => void;
  sessions: SessionMeta[];
  activeSessionId: string | null;
  currentView: ViewType;
  onViewChange: (view: ViewType) => void;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
}

export default function Sidebar({ isOpen, toggle, sessions, activeSessionId, currentView, onViewChange, onSelectSession, onNewChat }: Props) {
  const navItems: { id: ViewType; label: string; icon: React.ReactNode }[] = [
    { id: 'chat',  label: 'Chat',            icon: <MessageSquare size={15} /> },
    { id: 'goals', label: 'Active Goals',    icon: <Target size={15} /> },
    { id: 'graph', label: 'Knowledge Graph', icon: <Network size={15} /> },
    { id: 'operator', label: 'Operator', icon: <Settings size={15} /> },
  ];

  if (!isOpen) return null;

  return (
    <aside className="w-[220px] h-full flex-shrink-0 flex flex-col py-3 px-2">

      {/* Nav buttons — floating individually */}
      <div className="flex flex-col gap-0.5 flex-shrink-0">
        <button
          onClick={onNewChat}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl
                     text-[13px] font-medium text-foreground
                     hover:bg-white/[0.06] transition-colors"
        >
          <Plus size={15} />
          New Chat
        </button>

        <div className="my-1 mx-1 h-px bg-white/[0.07]" />

        {navItems.map(item => (
          <button
            key={item.id}
            onClick={() => onViewChange(item.id)}
            className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl
                        text-[13px] font-medium transition-colors ${
              currentView === item.id
                ? 'bg-white/[0.08] text-foreground backdrop-blur-xl'
                : 'text-muted-foreground hover:bg-white/[0.05] hover:text-foreground'
            }`}
          >
            {item.icon}
            {item.label}
          </button>
        ))}
      </div>

      {/* Conversation list — floating, scrollable, with bottom blur */}
      <div className="flex-1 min-h-0 mt-4 flex flex-col overflow-hidden relative">
        <div className="flex-1 overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {sessions.length === 0 ? (
            <div className="px-3 py-2 text-[12px] text-muted-foreground italic">
              No conversations yet
            </div>
          ) : (
            sessions.map(s => (
              <button
                key={s.id}
                onClick={() => onSelectSession(s.id)}
                className={`w-full text-left px-3 py-1.5 rounded-xl text-[12px]
                            truncate transition-colors block ${
                  activeSessionId === s.id
                    ? 'bg-white/[0.08] text-foreground font-medium backdrop-blur-xl'
                    : 'text-muted-foreground hover:bg-white/[0.05] hover:text-foreground'
                }`}
              >
                {s.topics && s.topics.length > 0
                  ? s.topics[0]
                  : new Date(s.started_at).toLocaleString()}
              </button>
            ))
          )}
        </div>

        {/* Bottom scroll blur */}
        <div className="pointer-events-none absolute bottom-0 left-0 right-0 h-12
                        bg-gradient-to-t from-background to-transparent" />
      </div>

      {/* Profile — floating at bottom */}
      <div className="flex-shrink-0 mt-2 px-3 py-2.5 flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-full bg-white/[0.10] border border-white/[0.10]
                        flex items-center justify-center text-xs flex-shrink-0">
          👤
        </div>
        <span className="text-[13px] font-medium text-foreground">Admin</span>
      </div>

    </aside>
  );
}
