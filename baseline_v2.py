"""
Baseline agent for V2: Inspect → Filter → Fix
"""

import sys
import os
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from env_v2 import RepairEnvV2, COMPONENTS
from models_v2 import Action, ActionType, ComponentTarget, SymptomObservation

class BaselineAgent:
    def __init__(self):
        self.diagnosed_roots = set()
        self.inspected = set()
        self.fixed_roots = set()
        self.wait_ticks = 0
        self._rng = random.Random(42)  # For deterministic flaws

    def pick_action(self, obs: SymptomObservation) -> Action:
        import random
        
        # Flaw: 20% of the time it just randomly restarts something, wasting a turn and cost
        if self._rng.random() < 0.20:
            target = self._rng.choice(["api", "queue", "cache"])
            return Action(action_type=ActionType.restart_service, target=ComponentTarget(target))

        # 1. If we know any root causes we haven't fixed yet, fix them.
        pending_roots = self.diagnosed_roots - self.fixed_roots
        if pending_roots:
            target = list(pending_roots)[0]
            self.fixed_roots.add(target)
            self.wait_ticks = 2 # Add cooldown ticks
            
            if target == "database":
                return Action(action_type=ActionType.repair_database, target=ComponentTarget.database)
            elif target == "cache":
                return Action(action_type=ActionType.clear_cache, target=ComponentTarget.cache)
            else:
                return Action(action_type=ActionType.restart_service, target=ComponentTarget(target))
                
        # If we fixed the root, clean up any remaining high-error symptoms wait...
        # Wait for cooldown to finish first
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
        # Find component with highest error_rate among uninspected
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
            
        # 3. We've exhausted inspections or found nothing obvious (all healthy?). 
        # If we have a diagnosed root from a previous step's info (we don't, agent only sees obs).
        # Wait, the observation doesn't contain the InspectResult!
        # Ah! The inspect result is in 'info', which the agent shouldn't rely on for pure observation, 
        # but in OpenAI Gym, agents receive 'info'. Let's assume the agent can read `info["inspect_result"]` 
        # from the previous step, or we just randomly fix degraded things.
        
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


def run_task(task_id: str, config: dict) -> dict:
    env = RepairEnvV2()
    obs = env.reset(config, task_id)
    agent = BaselineAgent()
    
    step = 0
    print(f"\n=== Task: {task_id.upper()} ===")
    while True:
        action = agent.pick_action(obs)
        obs, reward, done, info = env.step(action)
        step += 1
        
        root_list = info.get("root_causes")
        res = info.get("inspect_result")
        
        if res and res["is_likely_root_cause"] and res["confidence"] >= 0.7:
            agent.diagnosed_roots.add(res["component"])
            
        print(f"Step {step:02d} | Action: {action.action_type}({action.target}) | Reward: {reward.value:+.2f}")
        for l in obs.logs:
            print(f"  [LOG] {l.message}")
            
        if done:
            break
            
    result = env.get_episode_result()
    print(f"Success: {result.success} | Score: {result.score:.4f} | Steps: {result.steps_taken}")
    return result.model_dump()


if __name__ == "__main__":
    from tasks_v2 import TASKS
    for tid, cfg in TASKS.items():
        run_task(tid, cfg)
