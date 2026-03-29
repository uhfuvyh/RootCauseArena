"""Quick smoke test: checks all 3 required items for repair_env_v2."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

root = os.path.dirname(os.path.abspath(__file__))

print("=" * 50)
print("  repair_env_v2 — Pre-flight Check")
print("=" * 50)

# --- 1. Dockerfile ---
df = os.path.join(root, "Dockerfile")
ok1 = os.path.isfile(df)
print(f"[{'OK' if ok1 else 'MISSING'}] Dockerfile")

# --- 2. inference.py ---
inf = os.path.join(root, "inference.py")
ok2 = os.path.isfile(inf)
print(f"[{'OK' if ok2 else 'MISSING'}] inference.py")

# --- 3. openenv.yaml ---
yaml_f = os.path.join(root, "openenv.yaml")
ok3 = os.path.isfile(yaml_f)
print(f"[{'OK' if ok3 else 'MISSING'}] openenv.yaml")

# --- 4. inference.py actually runs ---
print("\n--- Running inference on all 4 tasks (verbose=False) ---")
try:
    import inference as inf_mod
    from tasks_v2 import TASKS
    results = []
    for tid in TASKS:
        r = inf_mod.run_inference(task_id=tid, verbose=False)
        results.append(r)

    print(f"\n{'Task':<12} {'Steps':>5} {'Optimal':>7}  {'Reward':>7}  {'Score':>6}  {'Success':>7}  {'Health':>6}")
    print("-" * 60)
    for r in results:
        opt = TASKS[r["task_id"]]["optimal_steps"]
        print(f"{r['task_id']:<12} {r['steps_taken']:>5} {opt:>7}  {r['total_reward']:>7.3f}  {r['score']:>6.3f}  {str(r['success']):>7}  {r['final_health_ratio']:>6.2%}")
    print("\n[OK] inference.py runs cleanly on all tasks")
except Exception as e:
    print(f"[FAIL] inference.py error: {e}")
    import traceback; traceback.print_exc()

print("\n" + "=" * 50)
all_ok = ok1 and ok2 and ok3
print("RESULT:", "ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED")
print("=" * 50)
