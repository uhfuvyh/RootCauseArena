"""
Test script to run the baseline agent across 10 different seeds to verify stability.
"""
import sys
import os
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from env_v2 import RepairEnvV2
from baseline_v2 import BaselineAgent, run_task
from tasks_v2 import TASKS

def run_multi_seed_tests(num_runs=20):
    env = RepairEnvV2()
    task_config = TASKS["hard"]
    
    results = []
    print(f"{'Seed':<6} | {'Success':<8} | {'Score':<8} | {'Steps':<6}")
    print("-" * 35)
    
    for seed in range(42, 42 + num_runs):
        # We inject the seed into the task config for reset
        config = task_config.copy()
        config["seed"] = seed
        
        # We manually run because run_task in baseline_v2 prints too much
        env = RepairEnvV2()
        obs = env.reset(config, "multi_root")
        agent = BaselineAgent()
        
        # Override baseline agent's private RNG with this seed too for consistency
        agent._rng = random.Random(seed)
        
        done = False
        while not done:
            action = agent.pick_action(obs)
            obs, reward, done, info = env.step(action)
            
            res = info.get("inspect_result")
            if res and res["is_likely_root_cause"] and res["confidence"] >= 0.7:
                agent.diagnosed_roots.add(res["component"])
        
        res = env.get_episode_result()
        results.append(res)
        print(f"{seed:<6} | {str(res.success):<8} | {res.score:<8.4f} | {res.steps_taken:<6}")

    avg_score = sum(r.score for r in results) / len(results)
    avg_steps = sum(r.steps_taken for r in results) / len(results)
    success_rate = sum(1 for r in results if r.success) / len(results)
    
    print("-" * 35)
    print(f"SUMMARY ({len(results)} runs):")
    print(f"Success Rate: {success_rate:.2%}")
    print(f"Average Score: {avg_score:.4f}")
    print(f"Average Steps: {avg_steps:.1f}")

if __name__ == "__main__":
    run_multi_seed_tests(20)
