"""Task configs for V2. Root cause is explicitly defined."""

TASKS = {
    "easy": {
        "description": "DB down. Clear symptoms. No active misleading cascades.",
        "difficulty": "easy",
        "root_cause": "database",
        "optimal_steps": 2, # 1 inspect + 1 repair (takes 2 steps to heal) -> 3 steps total if repair counted as 1, let's say 3
        "max_steps": 10,
        "initial_state": {
            "database": {"status": "down"},
            "api":      {"status": "healthy"},
            "cache":    {"status": "healthy"},
            "queue":    {"status": "healthy"}
        }
    },
    "medium": {
        "description": "Cache down. Queue is overloaded (passive degradation). API is randomly degraded to mislead.",
        "difficulty": "medium",
        "root_cause": "cache",
        "optimal_steps": 4, # 1 inspect + 1 repair (cache) + wait 2 loops + 1 repair API (since it was pre-existing)
        "max_steps": 15,
        "initial_state": {
            "database": {"status": "healthy"},
            "api":      {"status": "degraded"}, # Misleading symptom, not caused by Cache
            "cache":    {"status": "down"},     # Root cause
            "queue":    {"status": "degraded"}  # Cascade from cache
        }
    },
    "hard": {
        "description": "DB down. Full cascading failure. High queue load, degraded API.",
        "difficulty": "hard",
        "root_cause": "database",
        "optimal_steps": 4, # inspect + repair DB + 2 wait steps
        "max_steps": 20,
        "initial_state": {
            "database": {"status": "down"},
            "api":      {"status": "down"},    # Cascade from DB
            "cache":    {"status": "healthy"},
            "queue":    {"status": "degraded"} # Cascade from DB
        }
    },
    "multi_root": {
        "description": "BOTH Database and Queue failed independently. High complexity.",
        "difficulty": "extreme",
        "root_cause": ["database", "queue"],
        "optimal_steps": 6,
        "max_steps": 25,
        "initial_state": {
            "database": {"status": "down"},
            "api":      {"status": "degraded"}, # Cascade from DB
            "cache":    {"status": "healthy"},
            "queue":    {"status": "down"}      # Independent failure
        }
    }
}
