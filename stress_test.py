"""
stress_test.py — Run 1000 simulations across all tasks with varying seeds.
Collects stats: success rate, avg score, avg reward, avg steps, failures.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from env_v2 import RepairEnvV2
from models_v2 import Action, ActionType, ComponentTarget
from tasks_v2 import TASKS

import random
import time
from collections import defaultdict

# ---------------------------------------------------------------------------
# Reuse the same inspect-then-fix agent from inference.py
# ---------------------------------------------------------------------------

def inspect_then_fix_agent(obs, task_config: dict, step: int, rng: random.Random) -> Action:
    root_cause = task_config["root_cause"]
    if isinstance(root_cause, list):
        root_cause = root_cause[0]

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


def random_agent(obs, rng: random.Random) -> Action:
    """Completely random agent for chaos testing."""
    return Action(
        action_type=rng.choice(list(ActionType)),
        target=rng.choice(list(ComponentTarget)),
    )


# ---------------------------------------------------------------------------
# Run N simulations
# ---------------------------------------------------------------------------

def run_stress_test(n_total: int = 1000):
    task_ids = list(TASKS.keys())
    n_per_task = n_total // len(task_ids)

    # Stats per task per agent
    stats = {}
    for task_id in task_ids:
        stats[task_id] = {
            "baseline": defaultdict(list),
            "random":   defaultdict(list),
        }

    errors = []
    total_runs = 0
    start = time.time()

    print(f"\n{'='*60}")
    print(f"  Stress Test: {n_total} simulations")
    print(f"  Tasks: {task_ids}")
    print(f"  {n_per_task} runs per task  x  2 agents  =  {n_per_task * 2 * len(task_ids)} total episodes")
    print(f"{'='*60}\n")

    for task_id in task_ids:
        config = TASKS[task_id]
        print(f"  Running task '{task_id}' ({n_per_task} seeds x 2 agents)...", end="", flush=True)

        for seed in range(n_per_task):
            for agent_name in ["baseline", "random"]:
                try:
                    env = RepairEnvV2()
                    obs = env.reset(task_config=config, task_id=task_id)

                    done = False
                    step = 0
                    rng = random.Random(seed)

                    while not done:
                        if agent_name == "baseline":
                            action = inspect_then_fix_agent(obs, config, step, rng)
                        else:
                            action = random_agent(obs, rng)

                        obs, reward, done, info = env.step(action)
                        step += 1

                    result = env.get_episode_result()
                    s = stats[task_id][agent_name]
                    s["scores"].append(result.score)
                    s["rewards"].append(result.total_reward)
                    s["steps"].append(result.steps_taken)
                    s["success"].append(int(result.success))
                    s["health"].append(result.final_health_ratio)
                    total_runs += 1

                except Exception as e:
                    errors.append({"task": task_id, "seed": seed, "agent": agent_name, "error": str(e)})

        print(f" done.")

    elapsed = time.time() - start

    # ---------------------------------------------------------------------------
    # Print results
    # ---------------------------------------------------------------------------

    print(f"\n{'='*60}")
    print(f"  RESULTS  ({total_runs} episodes in {elapsed:.1f}s)")
    print(f"{'='*60}\n")

    for task_id in task_ids:
        config = TASKS[task_id]
        print(f"  Task: {task_id}  [{config.get('difficulty','?')}]  (optimal={config['optimal_steps']})")
        print(f"  {'-'*55}")

        for agent_name in ["baseline", "random"]:
            s = stats[task_id][agent_name]
            n = len(s["scores"])
            if n == 0:
                print(f"    {agent_name:<10}: NO DATA")
                continue

            avg_score   = sum(s["scores"])   / n
            avg_reward  = sum(s["rewards"])  / n
            avg_steps   = sum(s["steps"])    / n
            success_pct = sum(s["success"])  / n * 100
            avg_health  = sum(s["health"])   / n
            min_score   = min(s["scores"])
            max_score   = max(s["scores"])

            print(f"    {agent_name:<10}:  n={n}  success={success_pct:5.1f}%  "
                  f"score={avg_score:.3f} [{min_score:.2f}-{max_score:.2f}]  "
                  f"reward={avg_reward:+.2f}  steps={avg_steps:.1f}  health={avg_health:.2%}")
        print()

    # Summary table
    print(f"  {'Task':<12} {'Agent':<10} {'Success%':>9} {'AvgScore':>9} {'AvgReward':>10} {'AvgSteps':>9}")
    print(f"  {'-'*58}")
    for task_id in task_ids:
        for agent_name in ["baseline", "random"]:
            s = stats[task_id][agent_name]
            n = len(s["scores"])
            if n == 0: continue
            print(f"  {task_id:<12} {agent_name:<10} "
                  f"{sum(s['success'])/n*100:>8.1f}% "
                  f"{sum(s['scores'])/n:>9.4f} "
                  f"{sum(s['rewards'])/n:>10.3f} "
                  f"{sum(s['steps'])/n:>9.1f}")
    print(f"  {'-'*58}")

    if errors:
        print(f"\n  ERRORS ({len(errors)} total):")
        for e in errors[:10]:
            print(f"    [{e['task']} seed={e['seed']} {e['agent']}] {e['error']}")
        if len(errors) > 10:
            print(f"    ... and {len(errors) - 10} more")
    else:
        print(f"\n  No errors! All {total_runs} episodes completed cleanly.")

    print(f"\n{'='*60}")
    print(f"  Stress test complete. {total_runs}/{n_per_task * 2 * len(task_ids)} episodes ran successfully.")
    print(f"{'='*60}\n")

    return stats, errors


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=1000, help="Total simulations (split across tasks)")
    args = parser.parse_args()
    run_stress_test(n_total=args.n)
