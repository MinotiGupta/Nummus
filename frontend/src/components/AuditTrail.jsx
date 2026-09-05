import React, { useState, useEffect, useCallback } from 'react';
import { getDecisions, getBatchRuns, getCycleAudit } from '../api/client';
import { Search, List, ShieldAlert, CheckCircle, Clock, Download } from 'lucide-react';

export default function AuditTrail() {
  const [runs, setRuns]             = useState([]);
  const [selectedRun, setSelectedRun] = useState('');
  const [summary, setSummary]       = useState(null);
  const [decisions, setDecisions]   = useState([]);
  const [loading, setLoading]       = useState(false);

  const fetchRuns = useCallback(async () => {
    try {
      const data = await getBatchRuns(20);
      setRuns(data);
      if (data.length > 0 && !selectedRun) {
        setSelectedRun(data[0].cycle_id);
      }
    } catch { /* ignore */ }
  }, [selectedRun]);

  const fetchRunDetails = useCallback(async (cycleId) => {
    if (!cycleId) return;
    setLoading(true);
    try {
      const [sumData, decData] = await Promise.all([
        getCycleAudit(cycleId),
        getDecisions({ cycleId, limit: 100 }),
      ]);
      setSummary(sumData);
      setDecisions(decData);
    } catch {
      setSummary(null);
      setDecisions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchRuns(); }, []);
  useEffect(() => { fetchRunDetails(selectedRun); }, [selectedRun, fetchRunDetails]);

  const handleExport = () => {
    const json = JSON.stringify(decisions, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `decisions_${selectedRun || 'all'}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div>
      <div className="section-header">
        <div>
          <h2>Audit Trail & Compliance</h2>
          <p className="subtitle">
            Immutable log of every decision, EV calculation, and stopping rule application.
          </p>
        </div>
      </div>

      <div className="card" style={{ marginBottom: '1.5rem', padding: '1rem 1.5rem' }}>
        <label className="select-label">Select Batch Cycle</label>
        <select
          value={selectedRun}
          onChange={(e) => setSelectedRun(e.target.value)}
          className="context-select"
          style={{ width: '100%', maxWidth: '400px' }}
        >
          <option value="" disabled>Select a run…</option>
          {runs.map((r, i) => (
            <option key={r.cycle_id} value={r.cycle_id}>
              Batch {runs.length - i} — {new Date(r.run_at).toLocaleString()}
            </option>
          ))}
        </select>
      </div>

      {summary && (
        <div className="grid grid-4" style={{ marginBottom: '1.5rem' }}>
          <div className="card metric-card">
            <div className="metric-label">Decisions Logged</div>
            <div className="metric-value">{summary.total_decisions}</div>
          </div>
          <div className="card metric-card">
            <div className="metric-label">Deferred by Budget</div>
            <div className="metric-value" style={{ color: 'var(--warning)' }}>{summary.deferred_by_budget}</div>
            <div className="metric-sub">Knapsack filtered</div>
          </div>
          <div className="card metric-card">
            <div className="metric-label">Held by Gate</div>
            <div className="metric-value" style={{ color: 'var(--text-2)' }}>{summary.held_by_gate}</div>
            <div className="metric-sub">Survival stopping rule</div>
          </div>
          <div className="card metric-card">
            <div className="metric-label">Force Escalated</div>
            <div className="metric-value" style={{ color: 'var(--danger)' }}>{summary.forced_escalations}</div>
            <div className="metric-sub">Compliance threshold met</div>
          </div>
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '1.25rem 1.5rem', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', margin: 0 }}>
            <List size={18} /> Detailed Decision Log
          </h3>
          <button className="btn btn-ghost" onClick={handleExport} disabled={decisions.length === 0} style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem' }}>
            <Download size={14} /> Export JSON
          </button>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Decision ID</th>
                <th>Context Key</th>
                <th>Stopping Rule</th>
                <th>Budget / EV</th>
                <th>Chosen Arm</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {decisions.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-2)' }}>
                    No decisions found for this cycle.
                  </td>
                </tr>
              )}
              {decisions.map((d) => (
                <tr key={d.decision_id} style={{ fontSize: '0.85rem' }}>
                  <td className="mono" style={{ color: 'var(--text-2)' }}>
                    {d.decision_id.split('-')[0]}…
                  </td>
                  <td className="mono" style={{ color: 'var(--accent-2)' }}>
                    {d.context_key.split('|').slice(1).join(' · ')}
                  </td>
                  <td>
                    {d.stopping_rule_reason ? (
                      <span className="badge warning" style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', width: 'fit-content' }}>
                        <ShieldAlert size={12} /> {d.stopping_rule_reason.split(':')[0]}
                      </span>
                    ) : (
                      <span className="badge success">Passed Gate</span>
                    )}
                  </td>
                  <td>
                    {d.budget_selected ? (
                      <span className="badge success">₹{Number(d.predicted_ev).toFixed(1)} EV</span>
                    ) : (
                      <span className="badge danger" style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', width: 'fit-content' }}>
                        <Clock size={12} /> Deferred
                      </span>
                    )}
                  </td>
                  <td style={{ fontWeight: 500 }}>{d.chosen_arm.replace(/_/g, ' ')}</td>
                  <td>
                    {d.actual_outcome ? (
                      <span className="badge success">Recovered</span>
                    ) : (
                      <span className="badge neutral">Failed</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {decisions.length > 0 && (
          <div style={{ padding: '0.75rem 1.5rem', color: 'var(--text-2)', fontSize: '0.8rem' }}>
            Showing 100 most recent decisions. Database contains {summary?.total_decisions ?? 0} total.
          </div>
        )}
      </div>
    </div>
  );
}
