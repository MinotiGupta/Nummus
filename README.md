# AI Revenue Recovery Agent (Nummus)

An AI-driven autonomous agent built to detect, diagnose, and recover revenue at risk from payment failures and checkout abandonments. 

Instead of static retry rules, this system uses **Agentic AI** (Contextual Bandits + Knapsack Optimization) to dynamically learn the best intervention for each specific context, balancing Expected Value (EV) against strict contact and spend budgets.

## 🚀 Live Demos
- **Frontend Dashboard:** [Your Vercel/Netlify URL Here]
- **FastAPI Backend:** [Your Railway/Render URL Here]

## ⚡ Quick Start (Local)

You need two terminals to run the system locally.

**1. Start the Backend (FastAPI)**
```bash
cd backend
python -m venv venv
.\venv\Scripts\activate   # (Windows)
# source venv/bin/activate # (Mac/Linux)
pip install -r requirements.txt
uvicorn main:app --reload
```

**2. Start the Frontend (Vite + React)**
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## 🎤 30-Second Demo Script for Judges

*Start on the **Batch Summary** tab.*
1. **"The Problem"**: "Revenue recovery isn't a one-size-fits-all problem. Static rules leave money on the table. We built an AI agent that learns the optimal recovery action for every unique customer context."
2. **"The Dashboard"**: "Here you can see our AI actively recovering money. The blue line is our agent's recovery rate; the dashed line is the traditional static baseline. Watch the green line—that's our absolute efficiency gain. Over time, as the AI learns, it surpasses the baseline."
3. **"Run a Batch"**: *(Click 'Run Next Batch')* "When we trigger a batch, the agent evaluates hundreds of events, applying Thompson Sampling to choose actions, and a greedy Knapsack scheduler to ensure we never breach our contact or spend budgets."
4. **"The Brain"**: *(Switch to **Bandit Convergence** tab)* "This is the brain of the agent. For an 'Insufficient Funds' error on a loyal customer, the agent has empirically learned that a delayed retry works best. The 90% credible intervals show its confidence."
5. **"The Audit"**: *(Switch to **Live Event Feed**, click a row)* "We don't just act blindly. Clicking any decision opens the Inspector. You can see the exact Expected Value math used, why it passed the compliance Survival Gate, and exactly which budget it consumed."

---

## 🧠 Architecture Highlights

1. **Contextual Bandit (`bandit.py`)**: Uses Beta-Binomial Thompson Sampling. It balances exploration (trying new actions) with exploitation (using the best known action) to maximize recovery probability.
2. **Knapsack Scheduler (`knapsack.py`)**: Recovery isn't free. The scheduler calculates the exact Expected Value in INR and packs the most profitable actions into bounded daily budgets (e.g., max 50 human calls, max ₹5,000 spend).
3. **Survival Gate (`survival_gate.py`)**: Ensures compliance. If a payment is highly likely to self-resolve, it holds the action. If a customer is spammed, it forces a human escalation.
4. **Immutable Audit Trail (`executor.py`)**: Every decision, probability sample, and EV calculation is permanently logged to SQLite for regulatory compliance.