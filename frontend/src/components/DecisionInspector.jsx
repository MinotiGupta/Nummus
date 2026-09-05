import React, { useState, useEffect } from 'react';
import { getDecision } from '../api/client';
import { X, Calculator, ShieldAlert, CheckCircle, Clock } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';

const ACTION_COSTS = {
  retry_immediate:          0.0,
  retry_delayed_2h:         0.0,
  retry_delayed_24h:        0.0,
  offer_alt_payment_method: 2.0,
  send_reminder_email:      0.5,
  send_reminder_sms:        0.5,
  escalate_human_call:      150.0,
  hold_no_action:           0.0,
};

export default function DecisionInspector({ decisionId, eventAmount, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!decisionId) return;
    setLoading(true);
    getDecision(decisionId).then(d => {
      setData(d);
      setLoading(false);
    }).catch(e => {
      console.error(e);
      setLoading(false);
    });
  }, [decisionId]);

  if (!decisionId) return null;

  return (
    <div className="drawer-overlay" onClick={onClose}>
      <div className="drawer" onClick={e => e.stopPropagation()}>
        <div className="drawer-header">
          <h3>Decision Inspector</h3>
          <button className="btn-icon" onClick={onClose}><X size={20} /></button>
        </div>

        {loading ? (
          <div style={{ padding: '2rem', textAlign: 'center' }}>Loading...</div>
        ) : !data ? (
          <div style={{ padding: '2rem', textAlign: 'center' }}>Error loading decision.</div>
        ) : (
          <div className="drawer-content">
            <div className="inspector-section">
              <h4>Context</h4>
              <div className="mono text-2" style={{ fontSize: '0.85rem' }}>
                {data.context_decoded ? Object.entries(data.context_decoded).map(([k, v]) => (
                  <div key={k}>{k}: <strong style={{ color: 'var(--text-1)' }}>{v}</strong></div>
                )) : data.context_key}
              </div>
            </div>

            <div className="inspector-section">
              <h4>Stopping Rule Engine</h4>
              {data.stopping_rule_reason ? (
                <div className="alert-box warning">
                  <ShieldAlert size={16} />
                  <div>
                    <strong>Action Intercepted</strong>
                    <p>{data.stopping_rule_reason}</p>
                  </div>
                </div>
              ) : (
                <div className="alert-box success">
                  <CheckCircle size={16} />
                  <div>
                    <strong>Passed Gate</strong>
                    <p>No survival or compliance rules triggered.</p>
                  </div>
                </div>
              )}
            </div>

            <div className="inspector-section">
              <h4>Bandit Exploration (Thompson Samples)</h4>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-2)', marginBottom: '1rem' }}>
                Samples drawn from Beta posteriors. Highest sample wins.
              </p>
              <div style={{ height: '250px' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={Object.entries(data.sampled_probabilities || {}).map(([arm, prob]) => ({
                    name: arm.replace(/_/g, ' '),
                    prob: prob,
                    arm: arm
                  })).sort((a,b) => b.prob - a.prob)} layout="vertical" margin={{ left: 140, right: 20 }}>
                    <XAxis type="number" domain={[0, 1]} hide />
                    <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 11, fill: 'var(--text-2)' }} />
                    <Tooltip cursor={{fill: 'rgba(255,255,255,0.05)'}} contentStyle={{ backgroundColor: 'var(--bg-1)', border: '1px solid var(--border)' }} />
                    <Bar dataKey="prob" radius={[0, 4, 4, 0]}>
                      {Object.entries(data.sampled_probabilities || {}).map(([arm], index) => {
                        const isChosen = arm === data.chosen_arm;
                        return <Cell key={arm} fill={isChosen ? 'var(--accent)' : 'var(--border)'} />;
                      })}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="inspector-section">
              <h4>Knapsack Scheduler & EV Calculation</h4>
              <div className="ev-calc-box">
                <Calculator size={18} style={{ color: 'var(--accent-2)' }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: '0.85rem', color: 'var(--text-2)', marginBottom: '0.25rem' }}>Expected Value (EV) Formula</div>
                  <div className="mono" style={{ fontSize: '0.9rem' }}>
                    P({(data.predicted_ev / eventAmount || 0).toFixed(2)}) × ₹{eventAmount.toFixed(0)} − ₹{(ACTION_COSTS[data.chosen_arm] || 0).toFixed(2)} = <strong style={{ color: 'var(--text-1)' }}>₹{Number(data.predicted_ev).toFixed(2)}</strong>
                  </div>
                </div>
              </div>
              
              <div style={{ marginTop: '1rem' }}>
                {data.budget_selected ? (
                  <span className="badge success">Selected for Execution (Within Budget)</span>
                ) : (
                  <span className="badge warning">
                    Deferred (Budget Constrained)
                  </span>
                )}
              </div>
            </div>

            <div className="inspector-section">
              <h4>Outcome</h4>
              <div>
                {data.actual_outcome ? (
                  <span className="badge success">Recovered ₹{data.amount_recovered}</span>
                ) : (
                  <span className="badge danger">Lost / Pending</span>
                )}
              </div>
            </div>

          </div>
        )}
      </div>
    </div>
  );
}
