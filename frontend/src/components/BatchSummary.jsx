import React, { useState, useEffect } from 'react';
import { runBatch, getBatchRuns } from './api/client';
import { Activity, Zap, Shield, List, AlertCircle } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

export default function BatchSummary({ onRunBatch }) {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchRuns = async () => {
    try {
      const data = await getBatchRuns();
      setRuns(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchRuns();
  }, []);

  const handleRun = async () => {
    setLoading(true);
    await onRunBatch();
    await fetchRuns();
    setLoading(false);
  };

  const latest = runs[0] || {
    total_at_risk_amount: 0,
    total_recovered_amount: 0,
    recovery_rate: 0,
    efficiency_vs_baseline: 0
  };

  const formatMoney = (val) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(val);

  const chartData = [...runs].reverse().map((r, i) => ({
    name: `Batch ${i + 1}`,
    recoveryRate: r.recovery_rate.toFixed(1),
    efficiency: r.efficiency_vs_baseline.toFixed(1)
  }));

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <div>
          <h2>Batch Summary</h2>
          <p style={{ color: 'var(--text-2)' }}>Latest batch performance and overall trends.</p>
        </div>
        <button className="btn" onClick={handleRun} disabled={loading}>
          {loading ? <Zap className="animate-spin" /> : <Zap size={18} />}
          {loading ? 'Running...' : 'Run Next Batch'}
        </button>
      </div>

      <div className="grid">
        <div className="card">
          <div className="metric-label">Amount at Risk</div>
          <div className="metric-value">{formatMoney(latest.total_at_risk_amount)}</div>
        </div>
        <div className="card">
          <div className="metric-label">Amount Recovered</div>
          <div className="metric-value" style={{ color: 'var(--success)' }}>
            {formatMoney(latest.total_recovered_amount)}
          </div>
        </div>
        <div className="card">
          <div className="metric-label">Recovery Rate</div>
          <div className="metric-value">{latest.recovery_rate.toFixed(1)}%</div>
        </div>
        <div className="card">
          <div className="metric-label">Efficiency vs Baseline</div>
          <div className="metric-value" style={{ color: latest.efficiency_vs_baseline > 0 ? 'var(--success)' : 'var(--text-1)' }}>
            {latest.efficiency_vs_baseline > 0 ? '+' : ''}{latest.efficiency_vs_baseline.toFixed(1)}%
          </div>
        </div>
      </div>

      <div className="card" style={{ height: '400px' }}>
        <h3 style={{ marginBottom: '1.5rem' }}>Recovery Rate & Efficiency Trend</h3>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="name" stroke="var(--text-2)" />
            <YAxis yAxisId="left" stroke="var(--text-2)" />
            <YAxis yAxisId="right" orientation="right" stroke="var(--text-2)" />
            <Tooltip contentStyle={{ backgroundColor: 'var(--bg-1)', border: '1px solid var(--border)' }} />
            <Line yAxisId="left" type="monotone" dataKey="recoveryRate" stroke="var(--accent)" strokeWidth={2} name="Recovery %" />
            <Line yAxisId="right" type="monotone" dataKey="efficiency" stroke="var(--success)" strokeWidth={2} name="Efficiency (+%)" />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
