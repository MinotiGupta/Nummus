import React, { useState, useEffect, useCallback } from 'react';
import { getBanditContexts, getBanditStats } from '../api/client';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, ErrorBar, Cell, ReferenceLine,
} from 'recharts';
import { RefreshCw, TrendingUp, Info } from 'lucide-react';

const ARM_COLORS = {
  retry_immediate:           '#6366f1',
  retry_delayed_2h:          '#818cf8',
  retry_delayed_24h:         '#a5b4fc',
  offer_alt_payment_method:  '#22d3ee',
  send_reminder_email:       '#34d399',
  send_reminder_sms:         '#10b981',
  escalate_human_call:       '#f59e0b',
  hold_no_action:            '#475569',
};

function ArmTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <p style={{ fontWeight: 700, marginBottom: '0.5rem' }}>{d.arm.replace(/_/g, ' ')}</p>
      <p style={{ color: payload[0].color }}>Posterior Mean: <strong>{(d.posterior_mean * 100).toFixed(1)}%</strong></p>
      <p style={{ color: 'var(--text-2)', fontSize: '0.8rem' }}>
        90% CI: [{(d.ci_lower * 100).toFixed(1)}%, {(d.ci_upper * 100).toFixed(1)}%]
      </p>
      <p style={{ color: 'var(--text-2)', fontSize: '0.8rem' }}>
        Observations: <strong>{d.n_trials}</strong> (α={d.alpha?.toFixed(0)}, β={d.beta?.toFixed(0)})
      </p>
    </div>
  );
}

export default function ConvergenceView() {
  const [contexts, setContexts]     = useState([]);
  const [selected, setSelected]     = useState('');
  const [stats, setStats]           = useState(null);
  const [loading, setLoading]       = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [showBaseline, setShowBaseline] = useState(false);

  const fetchContexts = useCallback(async () => {
    try {
      const data = await getBanditContexts();
      setContexts(data);
      if (data.length > 0 && !selected) {
        setSelected(data[0].context_key);
      }
    } catch { /* ignore */ }
  }, [selected]);

  const fetchStats = useCallback(async (ctx) => {
    if (!ctx) return;
    setLoading(true);
    try {
      const data = await getBanditStats(ctx);
      setStats(data);
    } catch {
      setStats(null);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load + context list refresh
  useEffect(() => { fetchContexts(); }, []);

  // Stats refresh when selected changes
  useEffect(() => { fetchStats(selected); }, [selected, fetchStats]);

  // Auto-poll every 3s for live convergence demo
  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(() => {
      fetchContexts();
      fetchStats(selected);
    }, 3000);
    return () => clearInterval(id);
  }, [autoRefresh, selected, fetchContexts, fetchStats]);

  const arms = stats?.arms ?? [];
  const chartData = arms.map((a) => ({
    ...a,
    label: a.arm.replace(/_/g, ' '),
    pct:   parseFloat((a.posterior_mean * 100).toFixed(2)),
    ciErr: [
      parseFloat(((a.posterior_mean - a.ci_lower) * 100).toFixed(2)),
      parseFloat(((a.ci_upper - a.posterior_mean) * 100).toFixed(2)),
    ],
  }));

  const bestArm  = chartData[0];
  const totalObs = arms.reduce((s, a) => s + a.n_trials, 0);

  return (
    <div>
      <div className="section-header">
        <div>
          <h2>Bandit Convergence</h2>
          <p className="subtitle">
            Thompson Sampling posterior means per arm. Watch the agent learn which
            action maximises recovery for each customer context.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <label className="toggle-label" style={{ marginRight: '1rem' }}>
            <input
              type="checkbox"
              checked={showBaseline}
              onChange={(e) => setShowBaseline(e.target.checked)}
              style={{ marginRight: '0.4rem' }}
            />
            Show Baseline
          </label>
          <label className="toggle-label">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              style={{ marginRight: '0.4rem' }}
            />
            Live (3s)
          </label>
          <button className="btn btn-ghost" onClick={() => fetchStats(selected)} disabled={loading}>
            <RefreshCw size={16} className={loading ? 'spin' : ''} />
          </button>
        </div>
      </div>

      {/* Context selector */}
      <div className="card" style={{ marginBottom: '1.5rem', padding: '1rem 1.5rem' }}>
        <label className="select-label">Customer Context</label>
        <select
          id="context-select"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          className="context-select"
        >
          <option value="" disabled>Select a context…</option>
          {contexts.map((c) => (
            <option key={c.context_key} value={c.context_key}>{c.label}</option>
          ))}
        </select>
        {stats?.decoded && (
          <div className="context-chips">
            {Object.entries(stats.decoded).map(([k, v]) => (
              <span key={k} className="chip">{k.replace(/_/g, ' ')}: <strong>{v}</strong></span>
            ))}
          </div>
        )}
      </div>

      {/* Stats summary */}
      {stats && (
        <div className="grid grid-3" style={{ marginBottom: '1.5rem' }}>
          <div className="card metric-card">
            <div className="metric-label">Best Arm (current)</div>
            <div className="metric-value" style={{ fontSize: '1.1rem', color: 'var(--accent)' }}>
              {bestArm?.arm.replace(/_/g, ' ') ?? '—'}
            </div>
            <div className="metric-sub">{bestArm ? `p̂ = ${(bestArm.posterior_mean * 100).toFixed(1)}%` : ''}</div>
          </div>
          <div className="card metric-card">
            <div className="metric-label">Total Observations</div>
            <div className="metric-value">{totalObs.toLocaleString()}</div>
            <div className="metric-sub">across {arms.length} arms</div>
          </div>
          <div className="card metric-card">
            <div className="metric-label">Uncertainty Spread</div>
            <div className="metric-value" style={{ color: 'var(--accent-2)' }}>
              {bestArm ? `${((bestArm.ci_upper - bestArm.ci_lower) * 100).toFixed(1)}pp` : '—'}
            </div>
            <div className="metric-sub">90% CI width on best arm</div>
          </div>
        </div>
      )}

      {/* Main bar chart */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem' }}>
          <h3>Posterior Success Probability by Arm</h3>
          <div className="info-pill">
            <Info size={12} /> Error bars = 90% credible interval
          </div>
        </div>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={400}>
            <BarChart data={chartData} layout="vertical" margin={{ left: 40, right: 40, top: 5, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} vertical={true} />
              <XAxis type="number" domain={[0, 100]} tickFormatter={(v) => `${v}%`} stroke="var(--text-2)" tick={{ fontSize: 12 }} />
              <YAxis type="category" dataKey="label" stroke="var(--text-2)" width={170} tick={{ fontSize: 12 }} />
              <Tooltip content={<ArmTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
              <ReferenceLine x={50} stroke="var(--border)" strokeDasharray="4 4" label={{ value: '50%', fill: 'var(--text-2)', fontSize: 11 }} />
              {showBaseline && chartData.find(a => a.arm === 'hold_no_action') && (
                <ReferenceLine 
                  x={chartData.find(a => a.arm === 'hold_no_action').pct} 
                  stroke="var(--warning)" 
                  strokeDasharray="3 3" 
                  label={{ value: 'Baseline', fill: 'var(--warning)', fontSize: 11, position: 'top' }} 
                />
              )}
              <Bar dataKey="pct" name="Success Probability %" radius={[0, 4, 4, 0]}>
                {chartData.map((entry) => (
                  <Cell key={entry.arm} fill={ARM_COLORS[entry.arm] ?? 'var(--accent)'} />
                ))}
                <ErrorBar dataKey="ciErr" width={4} strokeWidth={2} stroke="rgba(255,255,255,0.4)" direction="x" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="empty-state">
            <TrendingUp size={40} className="empty-icon" />
            <p>Run a few batches, then select a context to see convergence.</p>
          </div>
        )}
      </div>
    </div>
  );
}
