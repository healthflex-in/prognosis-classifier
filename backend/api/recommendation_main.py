"""
Standalone recommendation service.
Exposes only the recommendation + partial-reports REST routes and the
/ws/recommendation WebSocket — runs on port 8014 independently of the
main prognosis API (port 8013).
"""
import asyncio
import time
import uuid
from pathlib import Path
import sys

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.routes import recommendation, partial_reports
from utils.recommendation_output import valid_cached_recommendation

app = FastAPI(
    title="Recommendation Service",
    description="User-message recommendation generation and storage",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(recommendation.router, prefix="/api")
app.include_router(partial_reports.router, prefix="/api")


@app.on_event("startup")
async def warm_on_startup():
    """Pay the cold-start costs now instead of on the first click."""
    from services.recommendation_warmup import warm_recommendation_path
    asyncio.get_running_loop().run_in_executor(None, lambda: warm_recommendation_path(force=True))


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "Recommendation Service"}


def _log_timing(correlation_id, stage, started, **fields):
    """Emit safe timing data without allowing logging failures to affect requests."""
    try:
        details = " ".join(f"{key}={value}" for key, value in fields.items())
        print(
            f"[timing] endpoint=/ws/recommendation correlation_id={correlation_id} "
            f"stage={stage} duration_ms={(time.monotonic() - started) * 1000:.1f} {details}".rstrip()
        )
    except Exception:
        pass


@app.websocket("/ws/recommendation")
async def websocket_recommendation(websocket: WebSocket):
    correlation_id = uuid.uuid4().hex[:12]
    request_started = time.monotonic()
    await websocket.accept()
    try:
        msg = await websocket.receive_json()
        correlation_id = str(msg.get("request_id") or correlation_id)
        _log_timing(correlation_id, "request_start", request_started)
        patient_id = msg.get("patient_id")
        if not patient_id:
            await websocket.send_json({"error": "patient_id is required"})
            await websocket.close()
            return

        from utils.mongo_connection import get_mongo_db
        from bson import ObjectId
        mongo_started = time.monotonic()
        _, db = await asyncio.to_thread(get_mongo_db)
        pid_obj = ObjectId(patient_id) if len(str(patient_id)) == 24 else patient_id
        # A draft sent inline spares the wait for the draft POST to be stored; clients
        # that do not send one keep reading the stored draft as before.
        inline_draft = msg.get("draft")
        if isinstance(inline_draft, dict):
            from api.routes.partial_reports import build_inline_partial
            try:
                partial = build_inline_partial(inline_draft)
            except ValueError as error:
                await websocket.send_json({"error": "Assessment draft is incomplete or invalid. Please check the form and generate again."})
                await websocket.close()
                return
            rec_doc = await asyncio.to_thread(
                lambda: db["recommendation-data"].find_one({"patient_id": pid_obj})
            )
        else:
            partial, rec_doc = await asyncio.gather(
                asyncio.to_thread(lambda: db["partial-reports"].find_one({"patient_id": pid_obj})),
                asyncio.to_thread(lambda: db["recommendation-data"].find_one({"patient_id": pid_obj})),
            )
        from api.recommendation_draft import prepare_recommendation
        try:
            patient_data, current_hash = await asyncio.to_thread(
                prepare_recommendation, db, patient_id, partial, msg.get("report_id")
            )
        except ValueError as error:
            _log_timing(correlation_id, "data_preparation", mongo_started, outcome="error")
            await websocket.send_json({"error": str(error)})
            await websocket.close()
            return
        _log_timing(correlation_id, "mongo_data_preparation", mongo_started)

        cache_started = time.monotonic()
        cache_hit = bool(rec_doc and current_hash and rec_doc.get("input_hash") == current_hash and valid_cached_recommendation(rec_doc))
        _log_timing(correlation_id, "cache_hash_lookup", cache_started, cache="hit" if cache_hit else "miss")
        if cache_hit:
            await websocket.send_json({
                "top_3_action_areas": rec_doc["top_3_action_areas"],
                "next_session_plan": rec_doc["next_session_plan"],
                "cached": True,
            })
            await websocket.close()
            return

        from api.routes.recommendation import save_recommendation
        from LLM.recommendation.recommendation_agent import get_shared_agent
        construction_started = time.monotonic()
        agent = get_shared_agent()
        _log_timing(correlation_id, "recommendation_agent_construction", construction_started)
        generation_started = time.monotonic()
        output = await asyncio.to_thread(
            agent.generate, patient_data,
            lambda stage, started, **fields: _log_timing(correlation_id, stage, started, **fields),
        )
        _log_timing(correlation_id, "recommendation_generation", generation_started)
        persistence_started = time.monotonic()
        await asyncio.to_thread(save_recommendation, db, patient_id, output, current_hash, partial.get("hash"))
        _log_timing(correlation_id, "recommendation_persistence", persistence_started)

        await websocket.send_json({
            "top_3_action_areas": output.top_3_action_areas,
            "next_session_plan": output.next_session_plan,
            "cached": False,
        })
        await websocket.close()
    except WebSocketDisconnect:
        return
    except Exception as e:
        import traceback
        traceback.print_exc()
        try:
            await websocket.send_json({"error": str(e)})
            await websocket.close()
        except Exception:
            pass
    finally:
        _log_timing(correlation_id, "request_total", request_started)
