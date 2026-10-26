"""Pay the cold-start costs of the recommendation path before a user clicks Generate.

A fresh process pays for new MongoDB connections and the first Vertex call (channel and
auth setup) on its first request. This module does that work ahead of time with a
synthetic prompt, so no patient data is read or sent. Failures are swallowed: warming
is an optimisation and must never affect a request.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

# Collections the recommendation request reads; one find each opens a pooled connection.
_COLLECTIONS = ("partial-reports", "recommendation-data", "users", "reports", "vald-exercise-data")

# Skip repeat warm-ups while the connections are still hot.
WARM_TTL_S = 120.0

_lock = threading.Lock()
_last_warm = 0.0


def _timed(stats: Dict[str, int], label: str, fn) -> None:
    started = time.monotonic()
    try:
        fn()
        stats[label] = round((time.monotonic() - started) * 1000)
    except Exception as exc:
        stats[label] = -1
        print(f"[warmup] {label} failed: {type(exc).__name__}")


def _warm_mongo() -> None:
    from utils.mongo_connection import get_mongo_db
    _, db = get_mongo_db()
    db.command("ping")
    with ThreadPoolExecutor(max_workers=len(_COLLECTIONS)) as pool:
        list(pool.map(lambda name: db[name].find_one({}, {"_id": 1}), _COLLECTIONS))


def _warm_model() -> None:
    from langchain_core.messages import HumanMessage, SystemMessage
    from LLM.recommendation.recommendation_agent import SYSTEM_PROMPT, get_shared_agent
    agent = get_shared_agent()
    # Same system prompt and a tiny made-up assessment, so the real call finds a hot channel.
    agent.llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content="Chief Complaint: Right knee pain on stairs\nReturn ONLY the JSON object."),
    ])


def warm_recommendation_path(force: bool = False) -> Dict[str, object]:
    """Warm Mongo and the recommendation model. Returns stage durations in ms."""
    global _last_warm
    with _lock:
        now = time.monotonic()
        if not force and _last_warm and now - _last_warm < WARM_TTL_S:
            return {"skipped": True}
        _last_warm = now
    stats: Dict[str, object] = {}
    started = time.monotonic()
    _timed(stats, "mongo_ms", _warm_mongo)
    _timed(stats, "model_ms", _warm_model)
    stats["total_ms"] = round((time.monotonic() - started) * 1000)
    print("[warmup] " + " ".join(f"{k}={v}" for k, v in stats.items()))
    return stats
