import React, { useState, useEffect } from 'react';
import { getPosteriors } from '../api/client';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

export default function ConvergenceView() {
  const [posteriors, setPosteriors] = useState({});
  const [contexts, setContexts] = useState([]);
  const [selectedContext, setSelectedContext] = useState('');
  const [loading, setLoading] = useState(false);

  const fetchPosteriors = async () => {
    setLoading(true);
    try {
      const data = await getPosteriors();
      setPosteriors(data);
      const keys = Object.keys(data);
      setContexts(keys);
      if (keys.length > 0 && !selectedContext) {
        setSelectedContext(keys[0]);
      }
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchPosteriors();
    // Poll every 3 seconds for live convergence demo
    const interval = setInterval(fetchPosteriors, 3000);
    return () => clearInterval(interval);
  }, []);

  const data = posteriors[selectedContext] || [];
  const chartData = data.map(item => ({
    name: item.arm.replace('retry_', '').replace('send_', '').replace('_', ' '),
    successProb: (item.alpha / (item.alpha + item.beta)).toFixed(3),
    samples: item.alpha + item.beta - 2 // -2 for prior
  }));

  // Sort by success prob
  chartData.sort((a, b) => b.successProb - a.successProb);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <div>
          <h2>Bandit Convergence</h2>
          <p style={{ color: 'var(--text-2)' }}>Watch the Thompson Sampling policy learn the best action per context.</p>
        </div>
        <select 
          value={selectedContext} 
          onChange={(e) => setSelectedContext(e.target.value)}
          style={{ padding: '0.5rem', borderRadius: '0.25rem', backgroundColor: 'var(--bg-2)', color: 'var(--text-1)', border: '1px solid var(--border)' }}
        >
          <option value="" disabled>Select Context</option>
          {contexts.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      <div className="card" style={{ height: '500px' }}>
        <h3 style={{ marginBottom: '1.5rem' }}>Posterior Mean Success Probability by Arm</h3>
        {data.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} layout="vertical" margin={{ left: 120 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={true} vertical={false} />
              <XAxis type="number" domain={[0, 1]} stroke="var(--text-2)" />
              <YAxis type="category" dataKey="name" stroke="var(--text-2)" width={120} />
              <Tooltip cursor={{fill: 'rgba(255,255,255,0.05)'}} contentStyle={{ backgroundColor: 'var(--bg-1)', border: '1px solid var(--border)' }} />
              <Bar dataKey="successProb" fill="var(--accent)" name="Expected Probability" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p>Run a batch to see convergence data.</p>
        )}
      </div>
    </div>
  );
}
