# Nummus: AI Revenue Recovery Agent

Nummus is an autonomous agent designed to detect, diagnose, and recover revenue at risk from payment failures and checkout abandonments. Instead of relying on static retry rules, the system employs Contextual Bandits and Knapsack Optimization to dynamically learn the optimal intervention strategy for each specific customer context, balancing Expected Value (EV) against strict operational budgets.

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