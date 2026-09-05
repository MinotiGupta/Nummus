import React, { useState, useEffect, useCallback } from 'react';
import { getEvents } from '../api/client';
import DecisionInspector from './DecisionInspector';
import { RefreshCw, CheckCircle, XCircle, Clock, AlertTriangle, Filter } from 'lucide-react';

const fmt = (v) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(v);

const OUTCOME_CONFIG = {
  recovered: { label: 'Recovered', cls: 'badge success',  icon: <CheckCircle size={12} /> },
  lost:      { label: 'Lost',      cls: 'badge danger',   icon: <XCircle size={12} /> },
  deferred:  { label: 'Deferred',  cls: 'badge warning',  icon: <Clock size={12} /> },
  held:      { label: 'Held',      cls: 'badge neutral',  icon: <AlertTriangle size={12} /> },
};

const ROOT_CAUSE_SHORT = {
  insufficient_funds:   'Insuf. Funds',
  expired_card:         'Exp. Card',
  stolen_lost_card:     'Stolen/Lost',
  issuer_decline_soft:  'Issuer Soft',
  processor_error:      'Proc. Error',
  bank_risk_hold:       'Risk Hold',
  unknown:              'Unknown',
};

function OutcomeBadge({ label }) {
  const cfg = OUTCOME_CONFIG[label] ?? { label, cls: 'badge neutral' };
  return (
    <span className={cfg.cls} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem' }}>
      {cfg.icon}{cfg.label}
    </span>
  );
}

export default function EventFeed() {
  const [events, setEvents]     = useState([]);
  const [filter, setFilter]     = useState('all');
  const [causeFilter, setCauseFilter] = useState('');
  const [loading, setLoading]   = useState(false);
  const [counts, setCounts]     = useState({});
  const [inspectDecisionId, setInspectDecisionId] = useState(null);
  const [inspectAmount, setInspectAmount] = useState(0);

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getEvents({ limit: 300 });
      setEvents(data);
      // Compute counts for filter tabs
      const c = { all: data.length };
      data.forEach((e) => { c[e.outcome_label] = (c[e.outcome_label] ?? 0) + 1; });
      setCounts(c);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  const FILTERS = [
    { key: 'all',       label: 'All' },
    { key: 'recovered', label: 'Recovered' },
    { key: 'lost',      label: 'Lost' },
    { key: 'deferred',  label: 'Deferred' },
    { key: 'held',      label: 'Held' },
  ];

  const visible = events.filter((e) => {
    if (filter !== 'all' && e.outcome_label !== filter) return false;
    if (causeFilter && e.root_cause !== causeFilter) return false;
    return true;
  });

  // Summary stats
  const totalAt   = events.reduce((s, e) => s + e.amount, 0);
  const recovered = events.filter((e) => e.outcome_label === 'recovered').reduce((s, e) => s + e.amount, 0);

  return (
    <div>
      <div className="section-header">
        <div>
          <h2>Live Event Feed</h2>
          <p className="subtitle">
            Latest payment failure events, agent actions, and simulated outcomes.
          </p>
        </div>
        <button className="btn btn-ghost" onClick={fetchEvents} disabled={loading}>
          <RefreshCw size={16} className={loading ? 'spin' : ''} /> Refresh
        </button>
      </div>

      {/* Quick stats */}
      {events.length > 0 && (
        <div className="grid grid-4" style={{ marginBottom: '1.5rem' }}>
          <div className="card metric-card">
            <div className="metric-label">Events Loaded</div>
            <div className="metric-value">{events.length}</div>
          </div>
          <div className="card metric-card">
            <div className="metric-label">Total at Risk</div>
            <div className="metric-value" style={{ fontSize: '1.3rem' }}>{fmt(totalAt)}</div>
          </div>
          <div className="card metric-card">
            <div className="metric-label">Amount Recovered</div>
            <div className="metric-value" style={{ fontSize: '1.3rem', color: 'var(--success)' }}>{fmt(recovered)}</div>
          </div>
          <div className="card metric-card">
            <div className="metric-label">Recovered Count</div>
            <div className="metric-value" style={{ color: 'var(--success)' }}>{counts.recovered ?? 0}</div>
            <div className="metric-sub">of {events.length} events</div>
          </div>
        </div>
      )}

      {/* Filter tabs & Root Cause select */}
      <div className="filter-tabs" style={{ marginBottom: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {FILTERS.map(({ key, label }) => (
            <button
              key={key}
              className={`filter-tab ${filter === key ? 'active' : ''}`}
              onClick={() => setFilter(key)}
            >
              {label}
              {counts[key] !== undefined && (
                <span className="tab-count">{counts[key]}</span>
              )}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Filter size={16} color="var(--text-2)" />
          <select 
            className="context-select" 
            style={{ width: 'auto', padding: '0.4rem 2rem 0.4rem 0.75rem' }}
            value={causeFilter}
            onChange={e => setCauseFilter(e.target.value)}
          >
            <option value="">All Root Causes</option>
            {Object.keys(ROOT_CAUSE_SHORT).map(k => (
              <option key={k} value={k}>{ROOT_CAUSE_SHORT[k]}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>Account</th>
                <th>Root Cause</th>
                <th>Context</th>
                <th>Action Chosen</th>
                <th>Pred. EV</th>
                <th>Outcome</th>
                <th>Amount</th>
              </tr>
            </thead>
            <tbody>
              {visible.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-2)', padding: '2rem' }}>
                    {events.length === 0 ? 'Run a batch to see events.' : 'No events match this filter.'}
                  </td>
                </tr>
              )}
              {visible.slice(0, 200).map((e) => (
                <tr 
                  key={e.event_id ?? e.decision_id} 
                  onClick={() => {
                    if (e.decision_id) {
                      setInspectDecisionId(e.decision_id);
                      setInspectAmount(e.amount);
                    }
                  }}
                  style={{ cursor: e.decision_id ? 'pointer' : 'default' }}
                >
                  <td className="mono">{e.account_id}</td>
                  <td>
                    <span className="badge neutral">
                      {ROOT_CAUSE_SHORT[e.root_cause] ?? e.decline_code ?? '—'}
                    </span>
                  </td>
                  <td className="mono text-2 small">{e.context_key?.split('|').slice(1).join(' · ') ?? '—'}</td>
                  <td>
                    {e.chosen_arm ? (
                      <span className="badge" style={{ backgroundColor: 'rgba(99,102,241,0.12)', color: 'var(--accent)' }}>
                        {e.chosen_arm.replace(/_/g, ' ')}
                      </span>
                    ) : '—'}
                  </td>
                  <td className="mono">
                    {e.predicted_ev != null ? `₹${Number(e.predicted_ev).toFixed(0)}` : '—'}
                  </td>
                  <td><OutcomeBadge label={e.outcome_label} /></td>
                  <td style={{ fontWeight: 600 }}>{fmt(e.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {visible.length > 200 && (
          <div style={{ padding: '0.75rem 1.5rem', color: 'var(--text-2)', fontSize: '0.8rem' }}>
            Showing 200 of {visible.length} events. Use filters to narrow down.
          </div>
        )}
      </div>

      {inspectDecisionId && (
        <DecisionInspector 
          decisionId={inspectDecisionId} 
          eventAmount={inspectAmount} 
          onClose={() => setInspectDecisionId(null)} 
        />
      )}
    </div>
  );
}
