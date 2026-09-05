export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

export async function runBatch(n = 200) {
  const res = await fetch(`${API_URL}/run-batch?n_events=${n}`, { method: "POST" });
  return res.json();
}

export async function getBatchRuns() {
  const res = await fetch(`${API_URL}/batch-runs`);
  return res.json();
}

export async function getEvents() {
  const res = await fetch(`${API_URL}/events`);
  return res.json();
}

export async function getPosteriors() {
  const res = await fetch(`${API_URL}/bandit/posteriors`);
  return res.json();
}

export async function getDecisions() {
  const res = await fetch(`${API_URL}/decisions?limit=500`);
  return res.json();
}
