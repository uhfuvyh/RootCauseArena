"""
inference.py — OpenEnv standard inference entry point for Repair Strategy System V2.
Produces structured output required by the OpenEnv validator.

Tags used for validation:
[START] task=NAME
[STEP] step=N reward=R
[END] task=NAME score=S steps=N
"""

from __future__ import annotations

import sys
import os
import argparse
import random
import copy

# Ensure the repo root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from env_v2 import RepairEnvV2, COMPONENTS
from models_v2 import Action, ActionType, ComponentTarget
from tasks_v2 import TASKS

# ---------------------------------------------------------------------------
# Self-contained Baseline Agent (to avoid import issues)
# ---------------------------------------------------------------------------

class InferenceAgent:
    def __init__(self):
        self.diagnosed_roots = set()
        self.inspected = set()
        self.fixed_roots = set()
        self.wait_ticks = 0
        self._rng = random.Random(42)

    def pick_action(self, obs) -> Action:
        # Flaw: 20% of the time it just randomly restarts something
        if self._rng.random() < 0.20:
            target = self._rng.choice(["api", "queue", "cache"])
            return Action(action_type=ActionType.restart_service, target=ComponentTarget(target))

        # 1. If we know any root causes we haven't fixed yet, fix them.
        pending_roots = self.diagnosed_roots - self.fixed_roots
        if pending_roots:
            target = list(pending_roots)[0]
            self.fixed_roots.add(target)
            self.wait_ticks = 2
            
            if target == "database":
                return Action(action_type=ActionType.repair_database, target=ComponentTarget.database)
            elif target == "cache":
                return Action(action_type=ActionType.clear_cache, target=ComponentTarget.cache)
            else:
                return Action(action_type=ActionType.restart_service, target=ComponentTarget(target))
                
        # Cooldown period
        if not pending_roots and self.fixed_roots:
            if self.wait_ticks > 0:
                self.wait_ticks -= 1
                return Action(action_type=ActionType.no_op, target=ComponentTarget.api)
            
            worst = max(obs.metrics.items(), key=lambda x: x[1].error_rate)
            if worst[1].error_rate > 0.0:
                if worst[0] == "database":
                    return Action(action_type=ActionType.repair_database, target=ComponentTarget.database)
                elif worst[0] == "cache":
                    return Action(action_type=ActionType.clear_cache, target=ComponentTarget.cache)
                else:
                    return Action(action_type=ActionType.restart_service, target=ComponentTarget(worst[0]))
            return Action(action_type=ActionType.no_op, target=ComponentTarget.api) 
                
        # 2. Pick most suspicious component to inspect
        suspicious = None
        highest_err = -1.0
        
        for comp, m in obs.metrics.items():
            if comp not in self.inspected and m.error_rate > highest_err:
                highest_err = m.error_rate
                suspicious = comp
                
        if suspicious and highest_err > 0.1:
            self.inspected.add(suspicious)
            action_map = {
                "database": ActionType.inspect_database,
                "api": ActionType.inspect_api,
                "cache": ActionType.inspect_cache,
                "queue": ActionType.inspect_queue
            }
            return Action(action_type=action_map[suspicious], target=ComponentTarget(suspicious))
            
        # Fallback: just restart highest error rate
        worst = max(obs.metrics.items(), key=lambda x: x[1].error_rate)
        if worst[1].error_rate > 0.1:
            if worst[0] == "database":
                return Action(action_type=ActionType.repair_database, target=ComponentTarget.database)
            elif worst[0] == "cache":
                return Action(action_type=ActionType.clear_cache, target=ComponentTarget.cache)
            else:
                return Action(action_type=ActionType.restart_service, target=ComponentTarget(worst[0]))
                
        return Action(action_type=ActionType.no_op, target=ComponentTarget.api)

# ---------------------------------------------------------------------------
# Runner logic
# ---------------------------------------------------------------------------

def run_task(task_id: str):
    """Run a single task and print structured output for the validator."""
    if task_id not in TASKS:
        return

    config = TASKS[task_id]
    
    # 1. Start tag
    print(f"[START] task={task_id}", flush=True)
    
    env = RepairEnvV2()
    obs = env.reset(task_config=config, task_id=task_id)
    agent = InferenceAgent()
    
    done = False
    step = 0
    
    while not done:
        action = agent.pick_action(obs)
        obs, reward, done, info = env.step(action)
        step += 1
        
        # Update agent state
        res = info.get("inspect_result")
        if res and res["is_likely_root_cause"] and res["confidence"] >= 0.7:
            agent.diagnosed_roots.add(res["component"])
            
        # 2. Step tag
        print(f"[STEP] step={step} reward={reward.value:.3f}", flush=True)

    # 3. End tag
    result = env.get_episode_result()
    print(f"[END] task={task_id} score={result.score:.4f} steps={result.steps_taken}", flush=True)

def main():
    parser = argparse.ArgumentParser(description="OpenEnv inference runner")
    parser.add_argument("--task", help="Run specific task (easy, medium, hard, multi_root)")
    args = parser.parse_args()

    if args.task:
        tasks_to_run = [args.task]
    else:
        tasks_to_run = ["easy", "medium", "hard", "multi_root"]

    for tid in tasks_to_run:
        run_task(tid)

if __name__ == "__main__":
    main()
