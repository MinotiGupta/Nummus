import React, { useState, useEffect, useCallback } from 'react';
import { runBatch, getBatchRuns } from '../api/client';
import { Activity, Zap, TrendingUp, DollarSign, Target, ChevronUp, ChevronDown, Loader2 } from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend, ReferenceLine,
} from 'recharts';

const fmt = (v) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(v);
const pct = (v, decimals = 1) => `${v >= 0 ? '+' : ''}${Number(v).toFixed(decimals)}%`;

function MetricCard({ label, value, sub, accent, trend }) {
  return (
    <div className="card metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={accent ? { color: accent } : {}}>{value}</div>
      {sub && <div className="metric-sub">{sub}</div>}
      {trend !== undefined && (
        <div className="metric-trend" style={{ color: trend >= 0 ? 'var(--success)' : 'var(--danger)' }}>
          {trend >= 0 ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          {Math.abs(trend).toFixed(1)}pp vs prev
        </div>
      )}
    </div>
  );
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <p className="tooltip-label">{label}</p>
      {payload.map((p) => (
        <p key={p.dataKey} style={{ color: p.color, margin: '0.25rem 0' }}>
          {p.name}: <strong>{typeof p.value === 'number' ? p.value.toFixed(1) : p.value}</strong>
        </p>
      ))}
    </div>
  );
};

export default function BatchSummary({ onRunBatch }) {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchRuns = useCallback(async () => {
    try {
      const data = await getBatchRuns(50);
      setRuns(data);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { fetchRuns(); }, [fetchRuns]);

  const handleRun = async () => {
    setLoading(true);
    setError(null);
    try {
      await onRunBatch();
      await fetchRuns();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const latest = runs[0] || {};
  const prev   = runs[1] || {};

  // Chart data: chronological (oldest first for the trend line)
  const chartData = [...runs].reverse().map((r, i) => ({
    name: `Batch ${i + 1}`,
    'Recovery %': parseFloat(r.recovery_rate?.toFixed(1) ?? 0),
    'Baseline %': parseFloat(r.baseline_recovered_amount / r.total_at_risk_amount * 100).toFixed(1) * 1 || 0,
    'Efficiency pp': parseFloat(r.efficiency_vs_baseline?.toFixed(1) ?? 0),
  }));

  const effTrend = runs.length >= 2
    ? (latest.efficiency_vs_baseline ?? 0) - (prev.efficiency_vs_baseline ?? 0)
    : undefined;

  return (
    <div>
      {/* Header */}
      <div className="section-header">
        <div>
          <h2>Batch Summary</h2>
          <p className="subtitle">Latest batch performance and recovery trend across all cycles.</p>
        </div>
        <button className="btn" onClick={handleRun} disabled={loading} id="run-batch-btn">
          {loading ? <Loader2 size={18} className="spin" /> : <Zap size={18} />}
          {loading ? 'Running…' : 'Run Next Batch'}
        </button>
      </div>

      {error && <div className="alert-error">{error}</div>}

      {/* KPI grid */}
      <div className="grid grid-4" style={{ marginBottom: '1.5rem' }}>
        <MetricCard
          label="Amount at Risk"
          value={latest.total_at_risk_amount ? fmt(latest.total_at_risk_amount) : '—'}
          sub={`${runs.length} batch${runs.length !== 1 ? 'es' : ''} run`}
          accent="var(--text-1)"
        />
        <MetricCard
          label="Recovered (Agent)"
          value={latest.total_recovered_amount ? fmt(latest.total_recovered_amount) : '—'}
          accent="var(--success)"
        />
        <MetricCard
          label="Recovered (Baseline)"
          value={latest.baseline_recovered_amount ? fmt(latest.baseline_recovered_amount) : '—'}
          accent="var(--text-2)"
        />
        <MetricCard
          label="Efficiency vs Baseline"
          value={latest.efficiency_vs_baseline !== undefined ? pct(latest.efficiency_vs_baseline) : '—'}
          accent={latest.efficiency_vs_baseline >= 0 ? 'var(--success)' : 'var(--danger)'}
          trend={effTrend}
          sub="percentage points"
        />
      </div>

      {/* Knapsack budget card */}
      {runs.length > 0 && latest.knapsack && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>Budget Utilisation — Last Batch</h3>
          <div className="grid grid-4">
            {[
              { label: 'Contacts Used', used: latest.knapsack.budget_contacts_used, total: latest.knapsack.budget_contacts, pct: latest.knapsack.contact_utilisation_pct },
              { label: 'Calls Used',    used: latest.knapsack.budget_calls_used,    total: latest.knapsack.budget_calls,    pct: latest.knapsack.call_utilisation_pct },
              { label: 'Spend Used',    used: `₹${latest.knapsack.budget_spend_used}`, total: `₹${latest.knapsack.budget_spend}`, pct: latest.knapsack.spend_utilisation_pct },
              { label: 'EV Captured',  used: `${latest.knapsack.total_ev_selected?.toFixed(0)}`, total: `${latest.knapsack.total_ev_oracle?.toFixed(0)}`, pct: latest.knapsack.ev_capture_pct },
            ].map(({ label, used, total, pct: p }) => (
              <div key={label} className="budget-item">
                <div className="budget-label">{label}</div>
                <div className="budget-bar-wrap">
                  <div className="budget-bar" style={{ width: `${Math.min(p, 100)}%`, backgroundColor: p > 90 ? 'var(--warning)' : 'var(--accent)' }} />
                </div>
                <div className="budget-vals">{used} / {total} <span>({p}%)</span></div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Trend chart */}
      <div className="card">
        <h3 style={{ marginBottom: '1.5rem' }}>Recovery Rate vs Baseline Trend</h3>
        {chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="name" stroke="var(--text-2)" tick={{ fontSize: 12 }} />
              <YAxis stroke="var(--text-2)" tick={{ fontSize: 12 }} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ color: 'var(--text-2)', fontSize: 13 }} />
              <ReferenceLine y={0} stroke="var(--border)" strokeDasharray="4 4" />
              <Line type="monotone" dataKey="Recovery %" stroke="var(--accent)" strokeWidth={2} dot={{ r: 4 }} activeDot={{ r: 6 }} />
              <Line type="monotone" dataKey="Baseline %" stroke="var(--text-2)" strokeWidth={2} strokeDasharray="5 5" dot={{ r: 3 }} />
              <Line type="monotone" dataKey="Efficiency pp" stroke="var(--success)" strokeWidth={2} dot={{ r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="empty-state">
            <Activity size={40} className="empty-icon" />
            <p>Run your first batch to see recovery trends.</p>
          </div>
        )}
      </div>

      {/* Batch run history table */}
      {runs.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '1.25rem 1.5rem', borderBottom: '1px solid var(--border)' }}>
            <h3>Run History</h3>
          </div>
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Events</th>
                <th>At Risk</th>
                <th>Recovered</th>
                <th>Baseline</th>
                <th>Recovery %</th>
                <th>Efficiency</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r, i) => (
                <tr key={r.cycle_id}>
                  <td className="mono text-2">Batch {runs.length - i}</td>
                  <td>{r.total_events}</td>
                  <td>{fmt(r.total_at_risk_amount)}</td>
                  <td style={{ color: 'var(--success)', fontWeight: 600 }}>{fmt(r.total_recovered_amount)}</td>
                  <td style={{ color: 'var(--text-2)' }}>{fmt(r.baseline_recovered_amount)}</td>
                  <td>{r.recovery_rate?.toFixed(1)}%</td>
                  <td style={{ color: r.efficiency_vs_baseline >= 0 ? 'var(--success)' : 'var(--danger)', fontWeight: 600 }}>
                    {pct(r.efficiency_vs_baseline ?? 0)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
