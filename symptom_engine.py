"""
Symptom Engine for Repair Strategy System V2.

HARD RULES ENFORCED:
1. Log ambiguity: No single log message uniquely identifies one root cause.
   Every log maps to >= 2 root causes.
2. Metrics are derived from the cascade-affected symptomatic state.
"""

import random
from typing import Dict, List, Set

from models_v2 import LogEntry, LogSeverity, ComponentMetrics

# Hard Rule #1: Ambiguous overlapping log pool
# Every message MUST appear in the list for >= 2 distinct components.
# The keys represent the 'symptomatic' state of a component (which may be caused by a different root cause)
LOG_POOL: Dict[str, Dict[str, List[str]]] = {
    "database": {
        "down": [
            "Connection timeout",            # Shared with Cache down
            "Service unavailable",           # Shared with API down
            "Upstream dependency failure",   # Shared with Cache down
            "Request queue backing up",      # Shared with Queue overloaded
            "High response time",            # Shared with Queue overloaded
            "Elevated read pressure",        # Shared with Cache down
            "Consumer lag detected",         # Shared with Queue overloaded
            "504 Gateway Timeout",           # Shared with API degraded
            "Slow slow-query log rising",    # Shared with API degraded
            "Cache miss rate critical",      # Shared with Cache down
            "Fatal IO error"                 # Shared with Queue down
        ]
    },
    "api": {
        "down": [
            "Service unavailable",           # Shared with DB down
            "Endpoint unhandled exception",  # Shared with Cache down
            "Process exited unexpectedly"    # Shared with Queue overloaded
        ],
        "degraded": [
            "504 Gateway Timeout",           # Shared with DB down
            "Slow slow-query log rising",    # Shared with DB down
            "Thread pool exhaustion"         # Shared with Queue overloaded
        ]
    },
    "cache": {
        "down": [
            "Connection timeout",            # Shared with DB down
            "Upstream dependency failure",   # Shared with DB down
            "Cache miss rate critical",      # Shared with DB down (read pressure)
            "Elevated read pressure",        # Shared with DB down
            "Memory pool exhausted",         # Shared with Queue overloaded
            "Queue backlog exceeding threshold", # Shared with Queue overloaded
            "Endpoint unhandled exception",  # Shared with API down
            "Broker connection reset"        # Shared with Queue down
        ]
    },
    "queue": {
        "down": [
            "Process exited unexpectedly",   # Shared with API down
            "Broker connection reset",       # Shared with Cache down
            "Fatal IO error"                 # Shared with DB down
        ],
        "degraded": [ # Corresponds to "overloaded"
            "High response time",            # Shared with DB down
            "Request queue backing up",      # Shared with DB down
            "Memory pool exhausted",         # Shared with Cache down
            "Queue backlog exceeding threshold", # Shared with Cache down
            "Consumer lag detected",         # Shared with DB down
            "Thread pool exhaustion"         # Shared with API degraded
        ]
    }
}

# Healthy baseline metrics
BASE_METRICS = {
    "database": {"latency": 30, "error_rate": 0.0, "queue_load": 0.0, "cpu_usage": 15.0},
    "api":      {"latency": 50, "error_rate": 0.0, "queue_load": 0.1, "cpu_usage": 20.0},
    "cache":    {"latency": 10, "error_rate": 0.0, "queue_load": 0.0, "cpu_usage": 30.0},
    "queue":    {"latency": 20, "error_rate": 0.0, "queue_load": 0.2, "cpu_usage": 10.0},
}


class SymptomEngine:
    def __init__(self, seed: int):
        self._rng = random.Random(seed)

    def _get_log_variations(self, base_log: str) -> str:
        variations = {
            "Connection timeout": [
                "Connection timeout on socket {}...",
                "Err: socket hangup {}ms",
                "Timeout Error: Target unreachable"
            ],
            "Service unavailable": [
                "Service unavailable (503) at path /{}",
                "CRITICAL: Application unresponsive",
                "HTTP 503 Service Temporarily Unavailable"
            ],
            "Upstream dependency failure": [
                "[DependencyError] Upstream failed to respond",
                "Upstream dependency failure: {} retry",
                "Failed to ping upstream node {}"
            ],
            "Request queue backing up": [
                "Request queue backing up, count: {}",
                "WARNING: Queue depth exceeding safe limits",
                "High request buffering ({})"
            ],
            "High response time": [
                "High response time > {}ms",
                "Latency spike detected in APM: {}",
                "Slow response: {}ms avg"
            ],
            "Elevated read pressure": [
                "Elevated read pressure on node {}",
                "High read IOPS detected ({})",
                "Warning: Read volume approaching limit"
            ],
            "Consumer lag detected": [
                "Consumer lag detected: {} units",
                "Processing delay on consumer group {}",
                "Lag spike: {} offset difference"
            ],
            "504 Gateway Timeout": [
                "504 Gateway Timeout on {}",
                "Gateway timeout contacting upstream",
                "Nginx 504: Target took too long"
            ],
            "Slow slow-query log rising": [
                "Slow slow-query log rising",
                "Slow query detected: {} sec",
                "DB Query execution time > {}ms"
            ],
            "Cache miss rate critical": [
                "Cache miss rate critical ({}%)",
                "Warning: Cache hit/miss ratio inverted",
                "Excessive cache misses on key prefix {}"
            ],
            "Fatal IO error": [
                "Fatal IO error at block {}",
                "Disk IO exception volume mounted at {}",
                "IOError: operation failed"
            ],
            "Memory pool exhausted": [
                "Memory pool exhausted (alloc: {}MB)",
                "OOM Warning: pool size limit reached",
                "Cannot allocate memory for {}"
            ],
            "Queue backlog exceeding threshold": [
                "Queue backlog exceeding threshold: {} reqs",
                "Backlog critical: {} items",
                "Spooling exceeded maximum partition limit"
            ],
            "Endpoint unhandled exception": [
                "Endpoint unhandled exception in route {}",
                "Unhandled runtime Error at GET /{}",
                "500 Internal Server Error: {}"
            ],
            "Broker connection reset": [
                "Broker connection reset by peer",
                "TCP RST received from broker {}",
                "Connection dropped: Broker unavailable"
            ]
        }
        
        pool = variations.get(base_log, [base_log])
        choice = self._rng.choice(pool)
        
        # Random template filling for realism
        if "{}" in choice:
            filler = self._rng.randint(10, 9999)
            choice = choice.format(filler)
            
        return choice
        self._verify_ambiguity_constraint()

    def _verify_ambiguity_constraint(self):
        """
        Hard Rule verification at startup:
        Ensures NO log exists that maps to exactly 1 root cause.
        (We map to symptomatic components here, but the principle is that
        different root causes trigger these symptoms, making the log ambiguous).
        """
        message_to_sources: Dict[str, Set[str]] = {}
        for comp, statuses in LOG_POOL.items():
            for status, msgs in statuses.items():
                for msg in msgs:
                    if msg not in message_to_sources:
                        message_to_sources[msg] = set()
                    message_to_sources[msg].add(comp)
        
        violations = []
        for msg, sources in message_to_sources.items():
            if len(sources) < 2:
                # Some logs map to different *statuses* of the same component,
                # but to be truly ambiguous across root causes, we need strict overlap.
                # The manual pool defines them carefully, but this safety check ensures
                # future additions don't break the rule.
                violations.append(f"'{msg}' only appears in {sources}")
                
        # If the pool is perfectly designed, violations will be empty.
        if violations:
            raise ValueError(f"Ambiguity Constraint Violation! Logs uniquely identifying a component: {violations}")

    def generate_metrics(self, state: Dict[str, Dict[str, any]]) -> Dict[str, ComponentMetrics]:
        """
        Generate metrics based on the current (cascade-applied) state.
        """
        metrics = {}
        
        # 1. Base translation from status to metrics
        for comp, data in state.items():
            status = data["status"]
            base = BASE_METRICS[comp]
            
            m = {"latency": base["latency"], "error_rate": base["error_rate"], 
                 "queue_load": base["queue_load"], "cpu_usage": base["cpu_usage"]}
                 
            if status == "down":
                m["latency"] = 9999
                m["error_rate"] = 1.0
                m["cpu_usage"] = 0.0 # Process is dead
            elif status == "degraded":
                m["latency"] *= int(3 + self._rng.random() * 2)
                m["error_rate"] = 0.3 + self._rng.random() * 0.2
                m["cpu_usage"] = min(100.0, m["cpu_usage"] * 4)
                
            metrics[comp] = m
            
        # 2. Cross-component metric leaking (Symptoms)
        # If DB is down, API naturally struggles
        if state["database"]["status"] == "down" and state["api"]["status"] != "down":
            metrics["api"]["latency"] += int(300 + self._rng.random() * 100)
            metrics["api"]["error_rate"] = min(1.0, metrics["api"]["error_rate"] + 0.5)
            metrics["api"]["cpu_usage"] = min(100.0, metrics["api"]["cpu_usage"] * 2)
            
        # If Cache is down, Queue load naturally spikes due to DB pressure
        if state["cache"]["status"] == "down":
            metrics["queue"]["queue_load"] += 0.3 + self._rng.random() * 0.2
            
        # Format output
        formatted_metrics = {}
        for comp, m in metrics.items():
            formatted_metrics[comp] = ComponentMetrics(
                latency=int(m["latency"]),
                error_rate=round(m["error_rate"], 2),
                queue_load=round(m["queue_load"], 2),
                cpu_usage=round(m["cpu_usage"], 1)
            )
            
        return formatted_metrics

    def generate_logs(self, state: Dict[str, Dict[str, any]], step: int) -> List[LogEntry]:
        """
        Generate ambiguous logs based on active symptoms.
        Returns 0-3 logs per broken component.
        """
        logs = []
        
        for comp, data in state.items():
            status = data["status"]
            if status == "healthy":
                continue
                
            pool = LOG_POOL.get(comp, {}).get(status, [])
            if not pool:
                # Fallback if specific status pool isn't defined
                pool = LOG_POOL.get(comp, {}).get("down", ["System error"])
                
            # Randomly select 1-2 logs for this symptom
            num_logs = self._rng.randint(1, 2)
            selected_msgs = self._rng.sample(pool, min(num_logs, len(pool)))
            
            for msg in selected_msgs:
                severity = LogSeverity.ERROR if status == "down" else LogSeverity.WARN
                logs.append(LogEntry(
                    timestamp=step * 1000 + self._rng.randint(10, 990),
                    message=msg,
                    severity=severity
                ))
                
        # Shuffle to prevent component ordering from being a tell
        self._rng.shuffle(logs)
        return logs
