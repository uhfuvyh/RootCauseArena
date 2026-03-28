"""
RepairEnv V2 — Main OpenEnv-compliant environment class.

HARD CONSTRAINTS ENFORCED:
- Hidden state: Observations only contain symptoms (logs + metrics).
- Strict step order: Action → Cascade → Degrade → Recovery Ticks → Symptoms → Reward
- Delayed recovery: repair_root_cause takes 2 steps to fully heal.
- Inspection cost: 3 free, then -0.1 reward per inspect.
"""

from __future__ import annotations

import copy
import random
from typing import Any, Dict, List, Optional, Tuple

from models_v2 import (
    Action,
    ActionType,
    ComponentMetrics,
    ComponentStatus,
    ComponentTarget,
    EpisodeResultV2,
    InspectResult,
    SymptomObservation,
    Reward,
    ACTION_COSTS
)
from symptom_engine import SymptomEngine

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEED = 42
STEP_PENALTY = -0.2
INSPECT_PENALTY = -0.1
MAX_FREE_INSPECTIONS = 3

COMPONENTS = ["database", "api", "cache", "queue"]

# ---------------------------------------------------------------------------
# RepairEnvV2
# ---------------------------------------------------------------------------

class RepairEnvV2:
    def __init__(self) -> None:
        self._task_config: Optional[Dict[str, Any]] = None
        
        # Hidden State
        self._true_state: Dict[str, Dict] = {}
        self._root_causes: List[str] = []
        self._recovery_cooldowns: Dict[str, int] = {}
        
        self._step_count: int = 0
        self._max_steps: int = 0
        self._task_id: str = ""
        self._done: bool = False
        
        self._total_reward: float = 0.0
        self._inspections_used: int = 0
        self._fixed_symptom_before_root: bool = False
        self._root_cause_fixed: bool = False
        
        self._rng: random.Random = random.Random(SEED)
        self._symptom_engine: SymptomEngine = SymptomEngine(SEED)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self, task_config: Dict[str, Any], task_id: str) -> SymptomObservation:
        """Reset the environment using a provided task configuration."""
        self._task_config = copy.deepcopy(task_config)
        self._task_id = task_id
        
        self._max_steps = self._task_config["max_steps"]
        self._step_count = 0
        self._done = False
        self._total_reward = 0.0
        self._inspections_used = 0
        self._fixed_symptom_before_root = False
        self._root_causes_fixed: Dict[str, bool] = {}
        
        # Initialize Hidden State
        root = self._task_config["root_cause"]
        self._root_causes = root if isinstance(root, list) else [root]
        self._root_causes_fixed = {r: False for r in self._root_causes}
        self._true_state = copy.deepcopy(self._task_config["initial_state"])
        self._recovery_cooldowns = {c: 0 for c in COMPONENTS}
        
        # Ensures rng is deterministic per run
        seed = self._task_config.get("seed", SEED)
        self._rng.seed(seed)
        self._symptom_engine = SymptomEngine(seed)

        return self._generate_symptoms()

    def step(self, action: Action) -> Tuple[SymptomObservation, Reward, bool, Dict[str, Any]]:
        """
        Hard Rule #4: Strict Step Order
        1. Action
        2. Cascading
        3. Degradation
        4. Recovery Ticks
        5. Symptoms (Metrics + Logs)
        6. Reward computation
        """
        if self._done:
            raise RuntimeError("Episode is done. Call reset().")

        # Snapshot for reward computation
        old_health = sum(1 for c in self._true_state.values() if c["status"] == "healthy")
        
        # 1. Action
        action_reward_modifier, inspect_info = self._apply_action(action)

        # 2. Cascading (Side effects driven by root cause)
        self._apply_cascading_effects()

        # 3. Degradation (Passive worsening)
        self._apply_degradation()

        # 4. Recovery Ticks
        self._tick_recovery_cooldowns(action)

        # 5. Generate Symptoms
        obs = self._generate_symptoms()
        self._step_count += 1

        # Check terminal condition
        all_healthy = all(c["status"] == "healthy" for c in self._true_state.values())
        if all_healthy or self._step_count >= self._max_steps:
            self._done = True

        # 6. Compute Reward
        new_health = sum(1 for c in self._true_state.values() if c["status"] == "healthy")
        
        reward = self._compute_reward(
            action, old_health, new_health, 
            all_healthy, action_reward_modifier
        )
        self._total_reward = round(self._total_reward + reward.value, 4)

        # Info dict (transparency for grading, completely hidden from agent observation)
        info = {
            "step": self._step_count,
            "true_state_snapshot": copy.deepcopy(self._true_state),
            "root_causes": self._root_causes,
            "cooldowns": self._recovery_cooldowns.copy(),
            "inspect_result": inspect_info.model_dump() if inspect_info else None,
            "reward_reason": reward.reason
        }

        return obs, reward, self._done, info

    def get_episode_result(self) -> EpisodeResultV2:
        final_health = sum(1 for c in self._true_state.values() if c["status"] == "healthy")
        health_ratio = final_health / 4.0
        
        steps = self._step_count
        optimal = self._task_config.get("optimal_steps", 5)
        efficiency = max(0.0, min(1.0, 1.0 - (steps - optimal) * 0.05))
        
        all_roots_fixed = all(self._root_causes_fixed.values())
        correct_root_fix_ratio = 1.0 if (all_roots_fixed and not self._fixed_symptom_before_root) else 0.0
        
        score = (0.5 * health_ratio) + (0.3 * efficiency) + (0.2 * correct_root_fix_ratio)
        
        return EpisodeResultV2(
            task_id=self._task_id,
            steps_taken=steps,
            total_reward=self._total_reward,
            score=round(score, 4),
            success=(health_ratio == 1.0),
            final_health_ratio=health_ratio,
            efficiency=efficiency,
            correct_root_fix_ratio=correct_root_fix_ratio
        )

    # ------------------------------------------------------------------
    # Private Implementation 
    # ------------------------------------------------------------------

    def _apply_action(self, action: Action) -> Tuple[float, Optional[InspectResult]]:
        """Handles both repair and inspect actions. Returns (reward_mod, inspect_result)."""
        target = action.target
        atype = action.action_type
        
        # Apply strict action costs
        reward_modifier = ACTION_COSTS.get(atype, 0.0)
        inspect_res = None
        
        if atype.startswith("inspect_"):
            self._inspections_used += 1
            if self._inspections_used > MAX_FREE_INSPECTIONS:
                reward_modifier += INSPECT_PENALTY
                
            investigating_root = (target in self._root_causes)
            
            # If it's the root cause, high confidence.
            if investigating_root:
                conf = round(self._rng.uniform(0.75, 1.0), 2)
                hint = f"Critical failures traced back to {target}. High correlation with active symptoms."
                is_likely = True
            else:
                # Symptom. Low confidence, but might randomly say True (false positive).
                conf = round(self._rng.uniform(0.2, 0.55), 2)
                is_likely = self._rng.random() < 0.2 # 20% false positive
                hint = f"Anomalies detected in {target}, but could be upstream cascade."
                
            if self._true_state[target]["status"] == "healthy":
                conf = round(self._rng.uniform(0.8, 1.0), 2)
                is_likely = False
                hint = f"{target} appears healthy. No immediate faults found."
                
            inspect_res = InspectResult(
                component=target,
                hint=hint,
                confidence=conf,
                is_likely_root_cause=is_likely
            )
            
        elif atype == ActionType.repair_database and target == "database":
            # Delayed recovery logic.
            if self._true_state["database"]["status"] != "healthy":
                if "database" in self._root_causes:
                    self._recovery_cooldowns["database"] = 2
                else:
                    self._recovery_cooldowns["database"] = 1
                    
        elif atype == ActionType.restart_service:
            # Short term symptom fix. Will be overwritten by cascade if root still broken.
            if self._true_state[target]["status"] == "down":
                self._true_state[target]["status"] = "degraded"
            elif self._true_state[target]["status"] == "degraded":
                self._true_state[target]["status"] = "healthy"
                
            active_roots = [r for r in self._root_causes if self._true_state[r]["status"] != "healthy"]
            if target not in self._root_causes and active_roots:
                # They are fixing a symptom before the root cause
                self._fixed_symptom_before_root = True
                
            if target in self._root_causes:
                self._recovery_cooldowns[target] = 1 # Restarts are slightly faster but less reliable than dedicated tools
                
        # Other actions omitted for brevity, mapping easily to V1 equivalents where needed.
        elif atype == ActionType.clear_cache and target == "cache":
            if self._true_state["cache"]["status"] != "healthy":
                self._true_state["cache"]["status"] = "healthy"
                
        return reward_modifier, inspect_res

    def _apply_cascading_effects(self):
        """Root-cause driven cascades. Overwrites temporary symptom fixes."""
        if "database" in self._root_causes and self._true_state["database"]["status"] != "healthy":
            # DB brings down the API
            self._true_state["api"]["status"] = "degraded"
            self._true_state["queue"]["status"] = "degraded"
            
        if "cache" in self._root_causes and self._true_state["cache"]["status"] != "healthy":
            # Cache pressure ruins queue
            self._true_state["queue"]["status"] = "degraded"
            
    def _apply_degradation(self):
        """Passive worsening."""
        pass # Currently handled implicitly by SymptomEngine metric generation, but placeholder for hard state drops

    def _tick_recovery_cooldowns(self, action: Action):
        for c in COMPONENTS:
            if self._recovery_cooldowns[c] > 0:
                # Don't tick the cooldown if we *just* started it this exact step.
                if action.target == c and action.action_type in [ActionType.repair_database, ActionType.restart_service]:
                    continue
                self._recovery_cooldowns[c] -= 1
                if self._recovery_cooldowns[c] == 0:
                    self._true_state[c]["status"] = "healthy"
                    if c in self._root_causes:
                        self._root_causes_fixed[c] = True

    def _generate_symptoms(self) -> SymptomObservation:
        metrics = self._symptom_engine.generate_metrics(self._true_state)
        logs = self._symptom_engine.generate_logs(self._true_state, self._step_count)
        inspections = max(0, MAX_FREE_INSPECTIONS - self._inspections_used)
        
        return SymptomObservation(
            metrics=metrics,
            logs=logs,
            step_count=self._step_count,
            max_steps=self._max_steps,
            inspections_remaining=inspections
        )

    def _compute_reward(self, 
                        action: Action, 
                        old_health: int, new_health: int,
                        all_healthy: bool,
                        modifier: float) -> Reward:
        
        base = STEP_PENALTY + modifier
        reason = []
        
        if modifier < 0:
            reason.append(f"Inspection cost ({modifier})")
            
        if action.action_type == ActionType.no_op:
            return Reward(value=base - 0.5, reason="Useless actions: no_op")
            
        # Root cause fix detection is delayed by cooldown, so we check if cooldown was just set 
        # (meaning the correct action was taken this turn)
        root_cooldown_started = (
            action.target in self._root_causes 
            and self._recovery_cooldowns[action.target] > 0
            and action.action_type in [ActionType.repair_database, ActionType.restart_service, ActionType.clear_cache]
        )
            
        if root_cooldown_started:
            base += 1.5
            reason.append(f"Root cause addressed ({action.target})")
        elif new_health > old_health:
            base += 0.5
            reason.append("Symptom improved")
        elif action.target not in self._root_causes and not action.action_type.startswith("inspect"):
            # They tried to fix a symptom that is immediately cascaded away (or just wrong)
            active_roots = [r for r in self._root_causes if self._true_state[r]["status"] != "healthy"]
            if active_roots:
                base -= 1.0
                reason.append("Wrong component targeted (root cause still active)")
            else:
                base -= 0.5
                reason.append("Component action had no net effect")
                
        if all_healthy:
            base += 5.0
            reason.append("Terminal Bonus: All healthy")
            
        return Reward(value=round(base, 4), reason=" | ".join(reason) if reason else "Step tick")
