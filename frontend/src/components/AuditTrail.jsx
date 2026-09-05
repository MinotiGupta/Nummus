import React, { useState, useEffect } from 'react';
import { getDecisions } from '../api/client';
import { Search } from 'lucide-react';

export default function AuditTrail() {
  const [decisions, setDecisions] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchDecisions = async () => {
    setLoading(true);
    try {
      const data = await getDecisions();
      setDecisions(data);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchDecisions();
  }, []);

  return (
    <div>
      <div style={{ marginBottom: '2rem' }}>
        <h2>Audit Trail & Compliance</h2>
        <p style={{ color: 'var(--text-2)' }}>Immutable log of every decision, EV calculation, and stopping rule application.</p>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <table>
          <thead style={{ backgroundColor: 'var(--bg-2)' }}>
            <tr>
              <th>Timestamp</th>
              <th>Event ID</th>
              <th>Context Key</th>
              <th>Stopping Rule</th>
              <th>Chosen Arm</th>
              <th>Budget Status</th>
            </tr>
          </thead>
          <tbody>
            {decisions.map(d => (
              <tr key={d.decision_id} style={{ fontSize: '0.875rem' }}>
                <td style={{ color: 'var(--text-2)' }}>{new Date(d.created_at).toLocaleString()}</td>
                <td style={{ fontFamily: 'monospace' }}>{d.event_id.substring(0, 8)}...</td>
                <td style={{ color: 'var(--accent-2)' }}>{d.context_key}</td>
                <td>
                  {d.stopping_rule_reason ? 
                    <span className="badge warning">{d.stopping_rule_reason}</span> : 
                    <span className="badge success">Passed</span>
                  }
                </td>
                <td style={{ fontWeight: 500 }}>{d.chosen_arm}</td>
                <td>
                  {d.budget_selected === 1 ? 
                    <span className="badge success">Selected</span> : 
                    <span className="badge danger">Deferred</span>
                  }
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
