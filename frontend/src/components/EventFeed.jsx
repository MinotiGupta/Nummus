import React, { useState, useEffect } from 'react';
import { getEvents } from '../api/client';
import { RefreshCw } from 'lucide-react';

export default function EventFeed() {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchEvents = async () => {
    setLoading(true);
    try {
      const data = await getEvents();
      // Show latest 100 for feed
      setEvents(data.sort((a,b) => new Date(b.timestamp) - new Date(a.timestamp)).slice(0, 100));
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchEvents();
  }, []);

  const formatMoney = (val) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(val);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <div>
          <h2>Live Event Feed</h2>
          <p style={{ color: 'var(--text-2)' }}>Recent payment failures and agent actions.</p>
        </div>
        <button className="btn" onClick={fetchEvents} disabled={loading} style={{ backgroundColor: 'var(--bg-2)', color: 'var(--text-1)' }}>
          <RefreshCw size={18} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <table>
          <thead style={{ backgroundColor: 'var(--bg-2)' }}>
            <tr>
              <th>Account</th>
              <th>Root Cause</th>
              <th>Action Chosen</th>
              <th>EV Predicted</th>
              <th>Outcome</th>
              <th>Amount</th>
            </tr>
          </thead>
          <tbody>
            {events.map(e => (
              <tr key={e.event_id}>
                <td style={{ fontFamily: 'monospace' }}>{e.account_id}</td>
                <td><span className="badge neutral">{e.root_cause || e.decline_code}</span></td>
                <td><span className="badge neutral" style={{ backgroundColor: 'rgba(99, 102, 241, 0.1)', color: 'var(--accent)' }}>{e.chosen_arm || 'pending'}</span></td>
                <td>{e.predicted_ev !== null ? `₹${e.predicted_ev.toFixed(2)}` : '-'}</td>
                <td>
                  {e.budget_selected === 0 ? <span className="badge warning">Deferred</span> : 
                   e.actual_outcome === 1 ? <span className="badge success">Recovered</span> : 
                   e.actual_outcome === 0 ? <span className="badge danger">Lost</span> : '-'}
                </td>
                <td style={{ fontWeight: 600 }}>{formatMoney(e.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
