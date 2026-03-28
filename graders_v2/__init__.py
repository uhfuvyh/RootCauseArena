"""
Composite grader for V2: Health + Efficiency + Root Fix Ratio
"""

from typing import Dict, Any

def grade_v2(final_state: Dict[str, Dict[str, Any]], steps_taken: int, 
            task_optimal_steps: int, correct_root_fix_ratio: float) -> float:
    """
    Score = 0.5 * final_health + 0.3 * efficiency + 0.2 * root_fix_ratio
    """
    healthy_count = sum(1 for c in final_state.values() if c["status"] == "healthy")
    final_health = healthy_count / 4.0
    
    efficiency = max(0.0, min(1.0, 1.0 - (steps_taken - task_optimal_steps) * 0.05))
    
    score = (0.5 * final_health) + (0.3 * efficiency) + (0.2 * correct_root_fix_ratio)
    
    return round(score, 4)

GRADERS = {
    "easy": grade_v2,
    "medium": grade_v2,
    "hard": grade_v2,
    "random": grade_v2
}
