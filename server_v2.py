"""
FastAPI server for Repair Strategy System V2.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import Any, Dict, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from env_v2 import RepairEnvV2
from models_v2 import ActionType, ComponentTarget, Diagnosis
from tasks_v2 import TASKS
from graders_v2 import GRADERS
import baseline_v2

app = FastAPI(
    title="Repair Strategy System V2",
    description="Symptom-based OpenEnv environment for multi-component system repair (Hidden State + Root Cause Inference)",
    version="2.0.0",
)

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server_v2:app", host="0.0.0.0", port=8001, reload=False)
