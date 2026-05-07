import { Target01Icon as Target, Clock01Icon as Clock, Alert01Icon as AlertCircle } from 'hugeicons-react';
import { useEffect, useState } from 'react';
import { apiUrl, getAuthHeaders } from '@/lib/api';

interface Goal {
  id: string;
  description: string;
  priority: string;
  created_at: string;
}

export default function GoalsView() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(apiUrl('/api/goals'), { headers: getAuthHeaders() })
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

  return (
    <div className="flex-1 overflow-y-auto px-4 py-8">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center gap-3 mb-8">
          <Target size={24} className="text-foreground" />
          <h1 className="text-2xl font-semibold tracking-tight">Active Goals</h1>
          <span className="ml-auto text-xs text-muted-foreground font-medium">{goals.length} active</span>
        </div>
        
        {loading ? (
          <div className="text-center py-8 text-muted-foreground">Loading goals...</div>
        ) : goals.length === 0 ? (
          <div className="bg-sidebar rounded-2xl p-8 text-center">
            <Clock size={32} className="mx-auto text-muted-foreground mb-3" />
            <p className="text-muted-foreground text-sm font-medium">No active goals yet.</p>
            <p className="text-muted-foreground text-xs mt-1">Start chatting with ARIA to generate goals automatically.</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {goals.map(goal => (
              <div key={goal.id} className="flex items-start gap-4 p-5 bg-sidebar rounded-xl border border-border">
                <div className={`mt-0.5 p-1.5 rounded-full ${
                  goal.priority === 'critical' ? 'bg-red-100 text-red-600' :
                  goal.priority === 'high' ? 'bg-orange-100 text-orange-600' :
                  'bg-blue-100 text-blue-600'
                }`}>
                  <AlertCircle size={16} />
                </div>
                <div className="flex-1">
                  <p className="text-[15px] text-foreground leading-relaxed font-medium mb-1">
                    {goal.description}
                  </p>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground font-medium uppercase tracking-wider">
                    <span>{goal.priority} PRIORITY</span>
                    <span>•</span>
                    <span>{new Date(goal.created_at).toLocaleDateString()}</span>
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
