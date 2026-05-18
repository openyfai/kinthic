import { Target01Icon as Target, Clock01Icon as Clock, Alert01Icon as AlertCircle, CheckmarkCircle01Icon as CheckCircle, Cancel01Icon as XCircle } from 'hugeicons-react';
import { useEffect, useState } from 'react';
import { apiUrl, getAuthHeaders } from '@/lib/api';

interface Goal {
  id: string;
  description: string;
  priority: string;
  status: string;
  created_at: string;
}

type Filter = 'all' | 'active' | 'completed' | 'abandoned';

function priorityColor(priority: string) {
  if (priority === 'critical') return 'bg-red-100 text-red-600';
  if (priority === 'high') return 'bg-orange-100 text-orange-600';
  if (priority === 'medium') return 'bg-blue-100 text-blue-600';
  return 'bg-zinc-100 text-zinc-500';
}

function statusIcon(status: string) {
  if (status === 'completed') return <CheckCircle size={16} />;
  if (status === 'abandoned') return <XCircle size={16} />;
  return <AlertCircle size={16} />;
}

function statusBadge(status: string) {
  if (status === 'completed') return 'bg-emerald-900/40 text-emerald-300 border border-emerald-800/40';
  if (status === 'abandoned') return 'bg-zinc-800/60 text-zinc-400 border border-zinc-700/40';
  return 'bg-amber-900/30 text-amber-300 border border-amber-800/30';
}

export default function GoalsView() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>('active');

  useEffect(() => {
    fetch(apiUrl('/api/goals/all'), { headers: getAuthHeaders() })
      .then(res => {
        if (!res.ok) throw new Error("Failed to load goals");
        return res.json();
      })
      .then(data => {
        setGoals(data);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  const filtered = goals.filter(g => {
    if (filter === 'all') return true;
    if (filter === 'active') return g.status === 'active' || g.status === 'pending';
    return g.status === filter;
  });

  const counts = {
    all: goals.length,
    active: goals.filter(g => g.status === 'active' || g.status === 'pending').length,
    completed: goals.filter(g => g.status === 'completed').length,
    abandoned: goals.filter(g => g.status === 'abandoned').length,
  };

  const filters: { id: Filter; label: string }[] = [
    { id: 'active', label: `Active (${counts.active})` },
    { id: 'completed', label: `Completed (${counts.completed})` },
    { id: 'abandoned', label: `Abandoned (${counts.abandoned})` },
    { id: 'all', label: `All (${counts.all})` },
  ];

  return (
    <div className="flex-1 overflow-y-auto px-4 py-8">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <Target size={24} className="text-foreground" />
          <h1 className="text-2xl font-semibold tracking-tight">Goals</h1>
        </div>

        {/* Filter tabs */}
        <div className="flex flex-wrap gap-2 mb-6">
          {filters.map(f => (
            <button
              key={f.id}
              type="button"
              onClick={() => setFilter(f.id)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                filter === f.id
                  ? 'bg-white text-black'
                  : 'border border-white/10 bg-white/[0.04] text-white/60 hover:bg-white/[0.08]'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="text-center py-8 text-muted-foreground">Loading goals...</div>
        ) : filtered.length === 0 ? (
          <div className="bg-sidebar rounded-2xl p-8 text-center">
            <Clock size={32} className="mx-auto text-muted-foreground mb-3" />
            <p className="text-muted-foreground text-sm font-medium">
              {filter === 'active' ? 'No active goals yet.' : `No ${filter} goals.`}
            </p>
            {filter === 'active' && (
              <p className="text-muted-foreground text-xs mt-1">Start chatting with VYN to generate goals automatically.</p>
            )}
          </div>
        ) : (
          <div className="grid gap-3">
            {filtered.map(goal => (
              <div key={goal.id} className="flex items-start gap-4 p-5 bg-sidebar rounded-xl border border-border">
                <div className={`mt-0.5 p-1.5 rounded-full ${priorityColor(goal.priority)}`}>
                  {statusIcon(goal.status)}
                </div>
                <div className="flex-1 min-w-0">
                  <p className={`text-[15px] leading-relaxed font-medium mb-2 ${
                    goal.status === 'abandoned' ? 'line-through text-muted-foreground' : 'text-foreground'
                  }`}>
                    {goal.description}
                  </p>
                  <div className="flex flex-wrap items-center gap-2 text-xs font-medium">
                    <span className={`rounded-full px-2 py-0.5 uppercase tracking-wide ${statusBadge(goal.status)}`}>
                      {goal.status}
                    </span>
                    <span className="text-muted-foreground uppercase tracking-wider">{goal.priority} priority</span>
                    <span className="text-muted-foreground">•</span>
                    <span className="text-muted-foreground">{new Date(goal.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
