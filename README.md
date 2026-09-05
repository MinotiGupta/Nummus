# Nummus: AI Revenue Recovery Agent

Nummus is an autonomous agent designed to detect, diagnose, and recover revenue at risk from payment failures and checkout abandonments. Instead of relying on static retry rules, the system employs Contextual Bandits and Knapsack Optimization to dynamically learn the optimal intervention strategy for each specific customer context, balancing Expected Value (EV) against strict operational budgets.

## Live Demo
**[View the Live Dashboard](https://nummus-six.vercel.app/)**

## How to Use and Understand the App

This application is designed to simulate and visualize the decision-making process of an AI agent recovering failed payments. To understand how it works, follow this guided tour through the dashboard:

### 1. Run a Batch (Batch Summary Tab)
- **What to do:** Click the **"Run Next Batch"** button in the top right. 
- **What happens:** The backend instantly generates 200 synthetic payment failures. The AI agent evaluates every single failure, calculates the Expected Value (EV) of all possible recovery actions (like sending an SMS, waiting 24 hours, or escalating to a human), and strictly packs the most profitable actions into daily budgets.
- **What to look for:** Watch the **Efficiency vs Baseline** metric. The blue line represents the AI's recovery rate, and the dashed line represents a traditional "static" ruleset. Over time, as the AI learns, you will see its efficiency outpace the baseline. Note how the **Budget Utilisation** bars fill up, proving the agent is respecting operational constraints.

### 2. Watch the Brain Learn (Bandit Convergence Tab)
- **What to do:** Switch to the **Bandit Convergence** tab and select a **Customer Context** from the dropdown (e.g., `insufficient_funds | high | long | weekday`).
- **What happens:** This screen visualizes the internal Bayesian math of the agent (Beta-Binomial Thompson Sampling).
- **What to look for:** Turn on the **"Show Baseline"** toggle. You will see the agent's expected success probability for every possible action. The Error Bars represent the agent's uncertainty (90% credible intervals). As you run more batches, the error bars shrink as the agent becomes highly confident in which action maximizes revenue for that specific type of failure.

### 3. Inspect a Single Decision (Live Event Feed Tab)
- **What to do:** Switch to the **Live Event Feed** and click on any row in the table to open the **Decision Inspector**.
- **What happens:** The drawer slides out to reveal the exact, immutable logic the agent used to handle that specific payment failure.
- **What to look for:**
  - **Bandit Exploration:** See the exact random probabilities drawn for each eligible action during Thompson Sampling.
  - **EV Calculation:** See the exact mathematical formula used to rank the action (`Probability × Amount - Cost`).
  - **Stopping Rule Engine:** Check if the action was allowed, or if it was blocked by the Survival Gate (e.g., the customer was already contacted 4 times, or the payment is highly likely to self-resolve).

### 4. Verify Compliance (Audit Trail Tab)
- **What to do:** Open the **Audit Trail** tab.
- **What happens:** This is the compliance view. It proves that the AI is not a "black box."
- **What to look for:** Every decision is permanently logged. You can clearly see how many actions were deferred simply because the daily budget was full, and how many were intercepted by compliance rules. You can also export the entire decision matrix to a JSON file.

## Architecture Overview

The system is built on a decoupled architecture featuring a Python/FastAPI backend for algorithmic orchestration and a React/Vite frontend for real-time observability and audit compliance.

### Backend Engine (FastAPI)

The backend operates as an 8-stage processing pipeline for batch event execution:

1. **Synthetic Data Generation (`data_generator.py`)**: Generates realistic payment failure events with log-normal amount distributions and realistic decline codes. Includes a deterministic baseline simulator for performance comparison.
2. **Root Cause Classifier (`root_cause.py`)**: Maps raw payment gateway decline codes to actionable root causes (e.g., mapping code '51' to 'insufficient_funds').
3. **Context Builder (`context_builder.py`)**: Discretizes continuous event data (amount, tenure, time) into finite context vectors necessary for the bandit algorithm.
4. **Survival Gate (`survival_gate.py`)**: A rule-based compliance and hazard scoring engine. It intercepts events that have a high probability of self-resolving (halting unnecessary action) or forces human escalation if strict contact thresholds are breached.
5. **Contextual Bandit (`bandit.py`)**: Implements Beta-Binomial Thompson Sampling. It maintains a posterior probability distribution for each action within every specific context, learning the optimal strategy over time through continuous Bayesian updates.
6. **Knapsack Scheduler (`knapsack.py`)**: A greedy approximation scheduler that ranks candidate actions by EV-density. It packs the highest-value actions into the execution queue while strictly respecting configured daily budgets for total contacts, human escalations, and financial spend.
7. **Executor & Audit (`executor.py`)**: Simulates the outcome of selected actions against a hidden ground-truth probability matrix. It writes immutable, JSON-structured audit records to SQLite for regulatory compliance before updating the bandit posteriors.

### Frontend Dashboard (React / Vite)

The frontend provides full observability into the agent's decision-making process:

1. **Batch Summary**: Displays top-level KPIs including total amount at risk, amount recovered, and absolute efficiency percentage points gained over the traditional static baseline. It also visualizes Knapsack budget utilization per batch.
2. **Bandit Convergence**: A real-time view into the Thompson Sampling algorithm. It renders horizontal bar charts showing the posterior mean success probability and 90% credible intervals for every arm, grouped by context.
3. **Live Event Feed**: A chronological table of processed events, highlighting the classified root cause, the chosen intervention, and the simulated outcome.
4. **Decision Inspector**: A detailed drawer view for any single event. It exposes the raw mathematical Expected Value calculation, the Thompson samples drawn across all eligible arms, and the explicit reasoning provided by the Survival Gate and Knapsack Scheduler.
5. **Audit Trail**: A dedicated compliance view showing immutable decision logs with the ability to export records to JSON.

## Project Structure

```text
razorpay/
├── backend/
│   ├── api/               # FastAPI route definitions
│   ├── db/                # SQLite connection and schema definitions
│   ├── engine/            # Core algorithmic pipeline modules
│   ├── data/              # SQLite database storage (git-ignored)
│   ├── main.py            # FastAPI application entry point
│   ├── seed_demo.py       # Utility script to pre-warm the database
│   └── requirements.txt   # Python dependencies
└── frontend/
    ├── src/
    │   ├── api/           # API client layer for backend communication
    │   ├── components/    # React functional components (Dashboard views)
    │   ├── App.jsx        # Main application layout and routing
    │   └── index.css      # Custom design system and CSS variables
    ├── package.json       # Node.js dependencies
    └── vite.config.js     # Vite configuration
```

## Local Development Setup

The application requires two terminal sessions to run both the backend API and the frontend development server.

### 1. Backend Setup

Navigate to the backend directory, create a virtual environment, install dependencies, and start the FastAPI server.

```bash
cd backend
python -m venv venv

# Windows
.\venv\Scripts\activate
# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt

# Start the server on port 8000
uvicorn main:app --reload
```

### 2. Frontend Setup

In a new terminal window, navigate to the frontend directory, install dependencies, and start the Vite development server.

```bash
cd frontend
npm install

# Start the development server on port 5173
npm run dev
```

Navigate to `http://localhost:5173` in your web browser to view the application.

## Simulation & Testing

The system is designed to be fully verifiable without external API dependencies. The `executor.py` module utilizes a seeded random number generator against a hidden `GROUND_TRUTH` probability matrix. This ensures that the same event and action pair will consistently produce the same outcome, allowing for stable baseline comparisons and demonstrable algorithm convergence during testing.