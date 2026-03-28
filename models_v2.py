"""
Pydantic models for the Repair Strategy System V2 OpenEnv environment.
"""

from __future__ import annotations
from enum import Enum
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class ComponentStatus(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    down = "down"


class ActionType(str, Enum):
    restart_service = "restart_service"
    scale_up = "scale_up"
    clear_cache = "clear_cache"
    repair_database = "repair_database"
    inspect_database = "inspect_database"
    inspect_api = "inspect_api"
    inspect_cache = "inspect_cache"
    inspect_queue = "inspect_queue"
    no_op = "no_op"


class ComponentTarget(str, Enum):
    database = "database"
    api = "api"
    cache = "cache"
    queue = "queue"


class LogSeverity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class LogEntry(BaseModel):
    timestamp: int
    message: str
    severity: LogSeverity
    
    model_config = {"use_enum_values": True}


class ComponentMetrics(BaseModel):
    latency: int = Field(..., ge=0)
    error_rate: float = Field(..., ge=0.0, le=1.0)
    queue_load: float = Field(..., ge=0.0)
    cpu_usage: float = Field(..., ge=0.0, le=100.0)


class SymptomObservation(BaseModel):
    """V2 Observation: True state is hidden. The agent only sees symptoms."""
    metrics: Dict[str, ComponentMetrics]
    logs: List[LogEntry]
    step_count: int = Field(..., ge=0)
    max_steps: int = Field(..., ge=1)
    inspections_remaining: int = Field(..., ge=0)

    model_config = {"use_enum_values": True}


class InspectResult(BaseModel):
    component: ComponentTarget
    hint: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    is_likely_root_cause: bool
    
    model_config = {"use_enum_values": True}


class Action(BaseModel):
    action_type: ActionType
    target: ComponentTarget

    model_config = {"use_enum_values": True}


class Diagnosis(BaseModel):
    root_causes: List[ComponentTarget]
    confidence: float = Field(..., ge=0.0, le=1.0)
    
    model_config = {"use_enum_values": True}


class Reward(BaseModel):
    value: float
    reason: str


class EpisodeResultV2(BaseModel):
    task_id: str
    steps_taken: int
    total_reward: float
    score: float
    success: bool
    final_health_ratio: float
    efficiency: float
    correct_root_fix_ratio: float

    model_config = {"use_enum_values": True}

# V3 Action Costs
ACTION_COSTS = {
    ActionType.repair_database: -0.5,
    ActionType.restart_service: -0.2,
    ActionType.clear_cache: -0.2,
    ActionType.scale_up: -0.5,
    ActionType.inspect_database: 0.0, # Handled dynamically (free vs paid)
    ActionType.inspect_api: 0.0,
    ActionType.inspect_cache: 0.0,
    ActionType.inspect_queue: 0.0,
    ActionType.no_op: 0.0
}
