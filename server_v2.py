"""
FastAPI server for Repair Strategy System V3.
Serves the premium web dashboard + JSON API.
"""

from __future__ import annotations

import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from env_v2 import RepairEnvV2
from models_v2 import ActionType, ComponentTarget, Diagnosis
from tasks_v2 import TASKS
from graders_v2 import GRADERS
import baseline_v2

app = FastAPI(
    title="RootCauseArena — Repair Strategy System V3",
    description="Interactive web dashboard + API for multi-component system repair with hidden state and root-cause inference.",
    version="3.0.0",
)

# Serve static assets (CSS, JS)
_static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# In-memory session store: session_id -> {env, total_reward}
_sessions: Dict[str, Dict] = {}

# ---------------------------------------------------------------------------
# Request/Response schemas
# ---------------------------------------------------------------------------

class GraderRequestV2(BaseModel):
    task_id: str
    final_state: Dict[str, Dict[str, Any]]
    steps_taken: int
    correct_root_fix_ratio: float


class GraderResponseV2(BaseModel):
    task_id: str
    score: float
    steps_taken: int


class BaselineResultV2(BaseModel):
    task_id: str
    steps_taken: int
    total_reward: float
    score: float
    success: bool
    final_health_ratio: float
    efficiency: float
    correct_root_fix_ratio: float


class BaselineResponseV2(BaseModel):
    results: List[BaselineResultV2]
    all_scores_in_range: bool


class DiagnoseRequest(BaseModel):
    task_id: str
    diagnosis: Diagnosis
    
class DiagnoseResponse(BaseModel):
    correct: bool
    actual_root_cause: str

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

# Global env for OpenEnv runner
_global_env = RepairEnvV2(seed=42)

@app.post("/reset")
def reset():
    """Standard OpenEnv reset endpoint."""
    obs = _global_env.reset()
    return {
        "observation": _obs_to_dict(obs),
        "info": {}
    }

from fastapi import Request
@app.post("/step")
async def step_standard(request: Request):
    """Standard OpenEnv step endpoint."""
    data = await request.json()
    from models_v2 import Action, ActionType, ComponentTarget
    action_type = data.get("action_type")
    target = data.get("target")
    act = Action(action_type=ActionType(action_type), target=ComponentTarget(target))
    obs, reward, done, info = _global_env.step(act)
    return {
        "observation": _obs_to_dict(obs),
        "reward": float(reward.value) if hasattr(reward, "value") else float(reward),
        "done": done,
        "info": info
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "repair-strategy-system-v2"}


@app.get("/tasks")
async def get_tasks():
    """Return all task definitions along with the action schema."""
    task_list = []
    for task_id, config in TASKS.items():
        task_list.append({
            "task_id": task_id,
            "description": config["description"],
            "difficulty": config.get("difficulty", task_id),
            "max_steps": config["max_steps"],
            "optimal_steps": config["optimal_steps"],
            # In V2, initial state is HIDDEN. Only returning structural info.
        })

    action_schema = {
        "action_type": {
            "type": "enum",
            "values": [e.value for e in ActionType],
        },
        "target": {
            "type": "enum",
            "values": [e.value for e in ComponentTarget],
        },
    }

    return {
        "tasks": task_list,
        "action_schema": action_schema,
        "observation_fields": ["metrics", "logs", "step_count", "max_steps", "inspections_remaining"],
        "seed": 42,
    }

@app.post("/grader", response_model=GraderResponseV2)
async def grade_episode(request: GraderRequestV2):
    """
    Grade a completed V2 episode.
    """
    if request.task_id not in GRADERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown task_id '{request.task_id}'",
        )

    grader_fn = GRADERS[request.task_id]
    
    # Needs optimal steps from task config
    optimal_steps = TASKS.get(request.task_id, {}).get("optimal_steps", 5)
    
    score = grader_fn(
        final_state=request.final_state,
        steps_taken=request.steps_taken,
        task_optimal_steps=optimal_steps,
        correct_root_fix_ratio=request.correct_root_fix_ratio
    )

    return GraderResponseV2(
        task_id=request.task_id,
        score=score,
        steps_taken=request.steps_taken,
    )


@app.post("/diagnose", response_model=DiagnoseResponse)
async def submit_diagnosis(request: DiagnoseRequest):
    """
    Allow an agent to submit a root cause diagnosis.
    Reveals whether they were right or wrong.
    """
    if request.task_id not in TASKS:
        raise HTTPException(status_code=400, detail="Unknown task_id")
        
    actual = TASKS[request.task_id]["root_cause"]
    correct = (request.diagnosis.root_cause == actual)
    
    return DiagnoseResponse(
        correct=correct,
        actual_root_cause=actual if correct else "HIDDEN (Incorrect Diagnosis)"
    )


@app.get("/baseline", response_model=BaselineResponseV2)
async def run_baseline():
    """Run the deterministic inspect-then-fix baseline agent on all tasks."""
    results = []
    for task_id, config in TASKS.items():
        raw = baseline_v2.run_task(task_id, config)
        results.append(BaselineResultV2(**raw))

    scores = [r.score for r in results]
    all_in_range = all(0.0 <= s <= 1.0 for s in scores)

    return BaselineResponseV2(
        results=results,
        all_scores_in_range=all_in_range,
    )


# ---------------------------------------------------------------------------
# Dashboard root
# ---------------------------------------------------------------------------

@app.get("/")
async def serve_dashboard():
    """Serve the interactive web dashboard."""
    index_path = os.path.join(_static_dir, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path, media_type="text/html")
    return {"message": "RootCauseArena V3 API — static dashboard not found. Check the /static folder."}


# ---------------------------------------------------------------------------
# Interactive Session Endpoints
# ---------------------------------------------------------------------------

class SessionStartRequest(BaseModel):
    task_id: str

class SessionStepRequest(BaseModel):
    session_id: str
    action_type: str
    target: str


def _obs_to_dict(obs) -> Dict:
    """Convert SymptomObservation to a JSON-serialisable dict."""
    return {
        "metrics": {
            comp: {
                "latency":    m.latency,
                "error_rate": m.error_rate,
                "queue_load": m.queue_load,
                "cpu_usage":  m.cpu_usage,
            }
            for comp, m in obs.metrics.items()
        },
        "logs": [
            {"timestamp": l.timestamp, "message": l.message, "severity": l.severity}
            for l in obs.logs
        ],
        "step_count":           obs.step_count,
        "max_steps":            obs.max_steps,
        "inspections_remaining":obs.inspections_remaining,
    }


@app.post("/session/start")
async def session_start(req: SessionStartRequest):
    """
    Start a new interactive episode. Returns a session_id and the initial observation.
    """
    if req.task_id not in TASKS:
        raise HTTPException(status_code=400, detail=f"Unknown task_id '{req.task_id}'")

    config = TASKS[req.task_id]
    env = RepairEnvV2(seed=42)
    obs = env.reset(task_config=config, task_id=req.task_id)

    sid = str(uuid.uuid4())
    _sessions[sid] = {"env": env, "total_reward": 0.0, "task_id": req.task_id}

    return {
        "session_id": sid,
        "task_id": req.task_id,
        "observation": _obs_to_dict(obs),
    }


@app.post("/session/step")
async def session_step(req: SessionStepRequest):
    """
    Advance the session by one step. Returns new observation, reward, done, and success.
    """
    if req.session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found. Start a new session first.")

    session = _sessions[req.session_id]
    env: RepairEnvV2 = session["env"]

    # Validate action & target
    try:
        action_type = ActionType(req.action_type)
        target      = ComponentTarget(req.target)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    from models_v2 import Action
    action = Action(action_type=action_type, target=target)

    obs, reward, done, info = env.step(action)
    session["total_reward"] += reward

    result = {
        "observation": _obs_to_dict(obs),
        "reward":      reward,
        "done":        done,
        "success":     info.get("success", False),
        "info":        str(info.get("reason", "")),
    }

    if done:
        # Clean up session
        del _sessions[req.session_id]

    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server_v2:app", host="0.0.0.0", port=7860, reload=False)

