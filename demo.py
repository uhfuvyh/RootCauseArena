"""
inference.py — OpenEnv standard inference entry point for Repair Strategy System V2.

Demonstrates how an external agent interacts with RepairEnvV2:
  1. Pick a task
  2. Reset the environment with that task config
  3. Step through with actions
  4. Grade the final episode via get_episode_result()

Run:
    python inference.py                        # runs 'easy' task
    python inference.py --task medium
    python inference.py --task hard
    python inference.py --task multi_root
    python inference.py --all                  # runs all 4 tasks and prints a summary table
"""

from __future__ import annotations

import sys
import os
import argparse

# Fix Windows console encoding for non-ASCII characters
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Ensure the repo root is on the path regardless of where this is called from
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from env_v2 import RepairEnvV2
from models_v2 import Action, ActionType, ComponentTarget
from tasks_v2 import TASKS


# ---------------------------------------------------------------------------
# Simple deterministic baseline agent (inspect root-cause area, then repair)
# ---------------------------------------------------------------------------

def inspect_then_fix_agent(obs, task_config: dict, step: int) -> Action:
    """
    Minimal deterministic agent:
    - Step 0: inspect the (first) suspected root cause component
    - Step 1+: attempt repair on whichever component has the highest error_rate
    """
    root_cause = task_config["root_cause"]
    if isinstance(root_cause, list):
        root_cause = root_cause[0]

    # Step 0: inspect first
    if step == 0:
        inspect_map = {
            "database": ActionType.inspect_database,
            "api":      ActionType.inspect_api,
            "cache":    ActionType.inspect_cache,
            "queue":    ActionType.inspect_queue,
        }
        return Action(
            action_type=inspect_map.get(root_cause, ActionType.inspect_database),
            target=ComponentTarget(root_cause),
        )

    # Step 1+: pick component with worst error_rate and try to fix it
    worst_comp = max(obs.metrics.items(), key=lambda kv: kv[1].error_rate)[0]
    repair_map = {
        "database": ActionType.repair_database,
        "api":      ActionType.restart_service,
        "cache":    ActionType.clear_cache,
        "queue":    ActionType.restart_service,
    }
    return Action(
        action_type=repair_map.get(worst_comp, ActionType.restart_service),
        target=ComponentTarget(worst_comp),
    )


# ---------------------------------------------------------------------------
# Main inference loop
# ---------------------------------------------------------------------------

def run_inference(task_id: str = "easy", verbose: bool = True) -> dict:
    """
    Run one full episode on the specified task using the inspect-then-fix agent.

    Returns the EpisodeResultV2 as a dict with:
        task_id, steps_taken, total_reward, score, success,
        final_health_ratio, efficiency, correct_root_fix_ratio
    """
    if task_id not in TASKS:
        raise ValueError(
            f"Unknown task_id '{task_id}'. Choose from: {list(TASKS.keys())}"
        )

    config = TASKS[task_id]

    # --- V2 API: __init__() takes no args; reset() takes (task_config, task_id) ---
    env = RepairEnvV2()
    obs = env.reset(task_config=config, task_id=task_id)

    done = False
    step = 0

    if verbose:
        print(f"\n{'='*62}")
        print(f"  Task       : {task_id}")
        print(f"  Difficulty : {config.get('difficulty', task_id)}")
        print(f"  Max steps  : {config['max_steps']}  |  Optimal: {config['optimal_steps']}")
        print(f"  Description: {config['description']}")
        print(f"{'='*62}")

    while not done:
        action = inspect_then_fix_agent(obs, config, step)
        obs, reward, done, info = env.step(action)

        if verbose:
            print(
                f"  Step {step + 1:>2}: {str(action.action_type):<22} > {str(action.target):<10}"
                f"| reward={reward.value:+.2f}  reason={reward.reason}"
            )
        step += 1

    # --- Use the env's built-in result calculation ---
    result = env.get_episode_result()

    if verbose:
        print(f"\n  -- Episode complete ------------------------------------------")
        print(f"  Steps taken        : {result.steps_taken} (optimal: {config['optimal_steps']})")
        print(f"  Total reward       : {result.total_reward:.4f}")
        print(f"  Score              : {result.score:.4f}")
        print(f"  Success            : {result.success}")
        print(f"  Final health ratio : {result.final_health_ratio:.2%}")
        print(f"  Efficiency         : {result.efficiency:.2%}")
        print(f"  Correct root fixes : {result.correct_root_fix_ratio:.2%}")
        print(f"{'='*62}\n")

    return result.model_dump()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="OpenEnv inference runner — Repair Strategy System V2"
    )
    parser.add_argument(
        "--task",
        default="easy",
        choices=list(TASKS.keys()),
        help="Task ID to run (default: easy)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run ALL tasks and print a summary table",
    )
    args = parser.parse_args()

    if args.all:
        print("\nRunning all tasks...\n")
        results = []
        for tid in TASKS:
            r = run_inference(task_id=tid, verbose=True)
            results.append(r)

        # Summary table
        print(f"\n{'-'*70}")
        print(f"{'Task':<12} {'Steps':>6} {'Optimal':>8} {'Reward':>8} {'Score':>7} {'Success':>8} {'Health':>7}")
        print(f"{'-'*70}")
        for r in results:
            optimal = TASKS[r['task_id']]['optimal_steps']
            print(
                f"{r['task_id']:<12} {r['steps_taken']:>6} {optimal:>8} "
                f"{r['total_reward']:>8.3f} {r['score']:>7.3f} "
                f"{str(r['success']):>8} {r['final_health_ratio']:>7.2%}"
            )
        print(f"{'-'*70}\n")
    else:
        run_inference(task_id=args.task, verbose=True)


if __name__ == "__main__":
    main()
