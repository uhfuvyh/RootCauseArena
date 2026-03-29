---
title: RootCauseArena
emoji: 🛠️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
app_file: server_v2.py
pinned: false
license: mit
---

# Repair Strategy System V3 (Hidden State & Reasoning)

> A deterministic incident-response simulator where an agent must infer hidden root causes from ambiguous symptoms and repair a distributed system under cascading failures.

Think of this as a "SRE Training Ground." Unlike basic simulations where you see exactly what's broken, V3 implements a **Hidden State** architecture. The agent never sees the true health of a component—only the metrics and logs it produces.

This shifts the challenge from simple state-mapping to **Root-Cause Inference + Sequential Decision-Making.**

---

## 🎯 Why This Matters

In production systems, failures rarely announce themselves with a clear "Down" label. You see latency spikes, 503 errors, and misleading logs that pull you in the wrong direction.

This environment captures the **messiness of real-world debugging**:
- **Cascades**: A database failure *will* cause the API to fail.
- **Ambiguity**: A "Service Unavailable" log could mean the API is dead *or* its upstream dependency is gone.
- **Costs**: Every inspection and repair action has a price. Blindly restarting everything will tank your score.

---

## ⚙️ Environment Loop

```text
       Agent Action (Inspect / Repair)
                  │
                  ▼
       ┌──────────────────────────┐
       │     1. Apply Action      │  ← Repair root or patch symptom
       │   2. Cascade Engine      │  ← DB failure travels to API
       │ 3. Passive Degradation   │  ← System worsens if root is active
       │ 4. Recovery Cooldowns    │  ← Critical repairs take 2 steps
       └──────────┬───────────────┘
                  │
       ┌──────────▼───────────────┐
       │    5. Symptom Engine     │  ← Generates random, ambiguous logs
       │    6. Reward Signal      │  ← Deducts action costs + health
       └──────────┬───────────────┘
                  │
       Agent receives Observation
        (Metrics + Overlapping Logs)
```

---

## 🏗️ Components (Hidden State)

The system models 4 components: **database**, **api**, **cache**, **queue**.
While the agent only sees symptoms, the environment tracks these internal fields:

| Field | Type | Description |
|---|---|---|
| `status` | `healthy | degraded | down` | Operational state (Hidden) |
| `latency` | int (ms) | Response time |
| `error_rate` | float [0.0–1.0] | Probability of request failure |
| `queue_load` | float | Buffer pressure |
| `cpu_usage` | float | Simulated resource consumption |

---

## ⚡ Action Space (With Decision Costs)

Every action carries a cost, forcing the agent to be precise.

### 🔍 Inspection Actions
| Action | Purpose | Cost |
|---|---|---|
| `inspect_[component]` | Gather clues about a specific node | **Free** (First 3) / **-0.1** (After) |

### 🔧 Repair Actions
| Action | Effect | Cost |
|---|---|---|
| `repair_database` | 2-step restore for DB only | **-0.5** |
| `scale_up` | Restores `degraded -> healthy` only | **-0.5** |
| `restart_service` | 2-step restore for any service | **-0.2** |
| `clear_cache` | Immediate `down -> healthy` | **-0.2** |
| `no_op` | Do nothing (waits for cooldowns) | **0** |

---

## 👁️ Observation Space (Symptoms)

Instead of the true state, the agent receives a **SymptomObservation**:

```json
{
  "metrics": {
    "database": {"latency": 9999, "error_rate": 1.0, "cpu_usage": 100},
    "api":      {"latency": 500, "error_rate": 0.9, "cpu_usage": 45},
    "cache":    {"latency": 20, "error_rate": 0.0, "cpu_usage": 10}
  },
  "logs": [
    "Connection timeout on socket 9934...",  // Could be DB or Cache!
    "CRITICAL: Application unresponsive",     // Ambiguous symptom
    "HTTP 503 Service Unavailable"           // Cascade result
  ],
  "step_count": 2,
  "inspections_remaining": 1
}
```

---

## 📏 V3 Grading Strategy

**Composite Health + Efficiency Scoring.** The grader doesn't just check if the system is healthy; it checks *how* you got there.

| Metric | weight | Description |
|---|---|---|
| **Health Ratio** | 50% | Final operational health of all components |
| **Efficiency** | 30% | Steps vs Optimal steps (Penalty for wasted turns) |
| **Root Fix Ratio** | 20% | Successful identification and repair of the true root cause |

---

## 🧪 Tasks

### Task 1 — Easy
- **Initial:** DB down. Simple cascade.
- **Goal:** Identify DB as root via logs and fix it.
- **Optimal steps:** 3 (Inspect + Repair + 2 cooldown steps)

### Task 2 — Hard (Full Cascade)
- **Initial:** DB down. API down. Queue degraded.
- **Rule:** If you fix the API first, it will immediately break again on the next step because the DB is still down.
- **Optimal steps:** 7 (Avg over seeds)

### Task 3 — Multi-Root (V3 Exclusive)
- **Initial:** Database AND Queue have failed independently. 
- **Goal:** The agent must solve both. Terminal rewards only trigger once **all** independent root causes are healthy.
- **Optimal steps:** 10 (Avg over 20-seed stress test)

---

## 📊 Baseline Performance (Deterministic)

Verified stability across **20 distinct random seeds** (42–61).

| Mission | Success Rate | Avg Score | Avg Steps |
|---|---:|---:|---:|
| **All V3 Tasks** | **100%** | **0.8373** | **6.8** |

---

## 🚀 Setup & Running

### Requirements
```bash
pip install fastapi uvicorn pydantic
```

### Start the V3 Server
```bash
python server_v2.py   # Runs on http://localhost:7860
```

### Verify Logic & Constraints
```bash
python test_v2.py     # Verifies 18 hard constraints
```

### API Endpoints
| Endpoint | Method | Result |
|---|---|---|
| `/tasks` | GET | Mission list + V3 Action Schema |
| `/grader`| POST | Composite Health/Efficiency score |
| `/baseline` | GET| Runs Inspect-Filter-Fix agent |
| `/diagnose` | POST| Theoretical root-cause validation |

---

Built for the OpenEnv Hackathon — Strictly deterministic and reasoning-heavy.
