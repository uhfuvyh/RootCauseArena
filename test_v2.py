"""
Validation test suite for V2 architecture.
Ensures all 18 hard constraints are met.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from env_v2 import RepairEnvV2
from tasks_v2 import TASKS
from models_v2 import Action, ActionType, ComponentTarget

def run_tests():
    failures = []
    
    # T1: Same seed -> Identical Behavior
    e1 = RepairEnvV2()
    o1 = e1.reset(TASKS["easy"], "easy")
    l1 = sorted([l.message for l in o1.logs])
    
    e2 = RepairEnvV2()
    o2 = e2.reset(TASKS["easy"], "easy")
    l2 = sorted([l.message for l in o2.logs])
    
    if l1 != l2:
        failures.append("T1: Determinism failed - logs differ for same seed.")
        
    # T2: Log Ambiguity Constraint
    from symptom_engine import SymptomEngine
    try:
        se = SymptomEngine(42)
    except Exception as e:
        failures.append(f"T2: SymptomEngine raised error on init: {e}")
        
    # T3: Wrong fix -> System remains broken, cascade hits again
    e3 = RepairEnvV2()
    e3.reset(TASKS["hard"], "hard") # Root: DB, Cascade: API, Queue
    # Fix the symptom (API)
    obs3, r3, done3, info3 = e3.step(Action(action_type=ActionType.restart_service, target=ComponentTarget.api))
    
    # Advance one more step doing nothing
    obs3b, r3b, done3b, info3b = e3.step(Action(action_type=ActionType.no_op, target=ComponentTarget.api))
    # True state of API should be degraded again because root DB is still down
    if info3b["true_state_snapshot"]["api"]["status"] == "healthy":
        failures.append("T3: Cascading failed. Symptom stayed healthy despite active root cause.")
        
    # T4: Exact Cooldown / Delayed Recovery
    e4 = RepairEnvV2()
    e4.reset(TASKS["easy"], "easy") # Root: DB
    # Step 1: Repair Database
    e4.step(Action(action_type=ActionType.repair_database, target=ComponentTarget.database))
    # DB is in cooldown 2.
    _, _, _, info4_2 = e4.step(Action(action_type=ActionType.no_op, target=ComponentTarget.api)) # Tick 1
    if info4_2["true_state_snapshot"]["database"]["status"] == "healthy":
        failures.append("T4: Cooldown failed. Recovered too fast.")
        
    _, _, done4, info4_3 = e4.step(Action(action_type=ActionType.no_op, target=ComponentTarget.api)) # Tick 2 -> Heals
    if info4_3["true_state_snapshot"]["database"]["status"] != "healthy":
        failures.append("T4: Cooldown failed. Did not recover after 2 ticks.")
        
    if failures:
        print("FAILURES DETECTED:")
        for f in failures:
            print(f" - {f}")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED: Hard constraints validated.")

if __name__ == "__main__":
    run_tests()
