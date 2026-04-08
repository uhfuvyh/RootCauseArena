"""
inference.py — OpenEnv standard inference entry point for Repair Strategy System V2.
Produces structured output required by the OpenEnv validator.

Checklist Compliance:
1. Environment variables: API_BASE_URL, MODEL_NAME, HF_TOKEN, LOCAL_IMAGE_NAME
2. OpenAI client configured via these variables.
3. [START], [STEP], [END] tags strictly followed.
"""

from __future__ import annotations

import sys
import os
import argparse
import random
import json
from openai import OpenAI

# Ensure the repo root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from env_v2 import RepairEnvV2, COMPONENTS
from models_v2 import Action, ActionType, ComponentTarget
from tasks_v2 import TASKS

# ---------------------------------------------------------------------------
# OpenEnv Configuration (Pre-Submission Checklist)
# ---------------------------------------------------------------------------

API_BASE_URL = os.getenv("API_BASE_URL", "https://api-inference.huggingface.co/v1/")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o")
HF_TOKEN = os.getenv("HF_TOKEN") # NO DEFAULT
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME")

# Initialize OpenAI client
# Note: If HF_TOKEN is missing, client creation might succeed but calls will fail.
# We handle this by falling back to the baseline agent.
client = OpenAI(base_url=API_BASE_URL, api_key=HF_TOKEN) if HF_TOKEN else None

# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

class InferenceAgent:
    """Baseline deterministic agent for reliable evaluation."""
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

def llm_agent(obs, task_config: dict, step: int) -> Action:
    """LLM-based agent using the OpenAI client."""
    if not client:
        # If no client, we can't call LLM
        return None

    # Logic similar to previous version...
    obs_dict = obs.model_dump() if hasattr(obs, 'model_dump') else obs
    system_prompt = "You are an SRE agent debugging a distributed system. Respond with JSON: {'action_type': '...', 'target': '...'}"
    
    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Step: {step}\\nObservation: {json.dumps(obs_dict)}"}
            ],
            response_format={"type": "json_object"}
        )
        data = json.loads(completion.choices[0].message.content)
        return Action(
            action_type=ActionType(data.get("action_type", "no_op")),
            target=ComponentTarget(data.get("target", "database"))
        )
    except Exception:
        return None

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
    baseline_agent = InferenceAgent()
    
    done = False
    step = 0
    
    while not done:
        # Try LLM agent first, fallback to baseline
        action = llm_agent(obs, config, step)
        if action is None:
            action = baseline_agent.pick_action(obs)
        
        obs, reward, done, info = env.step(action)
        step += 1
        
        # Update baseline agent state
        res = info.get("inspect_result")
        if res and res["is_likely_root_cause"] and res["confidence"] >= 0.7:
            baseline_agent.diagnosed_roots.add(res["component"])
            
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
