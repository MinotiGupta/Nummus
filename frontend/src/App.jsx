import React, { useState } from 'react';
import { Activity, Zap, Shield, List, BarChart2 } from 'lucide-react';
import BatchSummary from './components/BatchSummary';
import ConvergenceView from './components/ConvergenceView';
import EventFeed from './components/EventFeed';
import AuditTrail from './components/AuditTrail';
import { runBatch } from './api/client';

function App() {
  const [activeTab, setActiveTab] = useState('summary');

  const handleRunBatch = async () => {
    await runBatch(200); // 200 events per batch for demo
  };

  const navItems = [
    { id: 'summary', label: 'Batch Summary', icon: <Activity size={18} /> },
    { id: 'convergence', label: 'Bandit Convergence', icon: <BarChart2 size={18} /> },
    { id: 'feed', label: 'Live Event Feed', icon: <Zap size={18} /> },
    { id: 'audit', label: 'Audit Trail', icon: <List size={18} /> },
  ];

  return (
    <div className="dashboard-layout">
      <div className="sidebar">
        <h2>AI Revenue Agent</h2>
        <ul className="nav-links">
          {navItems.map(item => (
            <li 
              key={item.id} 
              className={`nav-item ${activeTab === item.id ? 'active' : ''}`}
              onClick={() => setActiveTab(item.id)}
            >
              {item.icon} {item.label}
            </li>
          ))}
        </ul>
        <div style={{ marginTop: 'auto', color: 'var(--text-2)', fontSize: '0.75rem' }}>
          <p>Buildathon Demo v1.0</p>
        </div>
      </div>
      
      <div className="main-content">
        {activeTab === 'summary' && <BatchSummary onRunBatch={handleRunBatch} />}
        {activeTab === 'convergence' && <ConvergenceView />}
        {activeTab === 'feed' && <EventFeed />}
        {activeTab === 'audit' && <AuditTrail />}
      </div>
    </div>
  );
}

export default App;
