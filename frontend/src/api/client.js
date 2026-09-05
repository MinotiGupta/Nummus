const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

async function api(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${path} → ${res.status}: ${text}`);
  }
  return res.json();
}

// ── Batch ──────────────────────────────────────────────────────────────────
export const runBatch       = (n = 200) => api(`/run-batch?n_events=${n}`, { method: 'POST' });
export const getBatchRuns   = (limit = 50) => api(`/batch-runs?limit=${limit}`);
export const getBatchRun    = (cycleId) => api(`/batch-runs/${cycleId}`);
export const getCycleAudit  = (cycleId) => api(`/batch-runs/${cycleId}/audit`);

// ── Events ─────────────────────────────────────────────────────────────────
export const getEvents = ({ batchId, outcome, limit = 200 } = {}) => {
  const params = new URLSearchParams();
  if (batchId)  params.set('batch_id', batchId);
  if (outcome)  params.set('outcome', outcome);
  params.set('limit', limit);
  return api(`/events?${params}`);
};

// ── Decisions ──────────────────────────────────────────────────────────────
export const getDecisions  = ({ limit = 100, cycleId } = {}) => {
  const params = new URLSearchParams({ limit });
  if (cycleId) params.set('cycle_id', cycleId);
  return api(`/decisions?${params}`);
};
export const getDecision   = (id) => api(`/decisions/${id}`);

// ── Bandit ─────────────────────────────────────────────────────────────────
export const getBanditContexts = () => api('/bandit/contexts');
export const getBanditStats    = (contextKey) => api(`/bandit/stats/${encodeURIComponent(contextKey)}`);
export const getPosteriors     = () => api('/bandit/posteriors');

// ── Health ─────────────────────────────────────────────────────────────────
export const getHealth = () => api('/health');
