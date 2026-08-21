"""
FastAPI backend for Clinical Dashboard.
Serves triage and clinical LLM data to the frontend (HTTP + WebSocket).
"""
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.routes import patients, stats, performance, matrix, triage, clinical, change_stream, query_widgets, prognosis, recommendation
from api.websocket_manager import websocket_endpoint
from api.queue_manager import PrognosisQueue
from api.scheduler import setup_scheduler
from LLM.prognosis.push_prognosis_to_mongo import save_to_mongo, build_patient_data_from_reports
from api.routes.recommendation import build_recommendation_input, save_recommendation

app = FastAPI(
    title="Clinical Dashboard API",
    description="API for serving patient triage and clinical analysis data",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",
        "http://localhost:8082",
        "http://localhost:8013",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:8082",
        "http://127.0.0.1:8013",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include routers
app.include_router(patients.router, prefix="/api")
app.include_router(stats.router, prefix="/api/stats")
app.include_router(performance.router, prefix="/api/performance")
app.include_router(matrix.router, prefix="/api/matrix")
app.include_router(triage.router, prefix="/api")
app.include_router(clinical.router, prefix="/api")
app.include_router(change_stream.router, prefix="/api")
app.include_router(query_widgets.router, prefix="/api")
app.include_router(prognosis.router, prefix="/api")
app.include_router(recommendation.router, prefix="/api")

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "Clinical Dashboard API"}

@app.get("/")
async def root():
    """Root endpoint."""
    # Get processing progress
    from api.progress_tracker import get_progress
    from api.data_loader import get_all_patients
    
    progress = get_progress()
    patients = get_all_patients()
    
    return {
        "message": "Clinical Dashboard API",
        "version": "1.0.0",
        "processing": {
            "status": progress.get("status", "idle"),
            "current": progress.get("current", 0),
            "total": progress.get("total", 0),
            "started_at": progress.get("started_at"),
            "completed_at": progress.get("completed_at")
        },
        "patients": {
            "total_classified": len(patients),
            "in_classification_file": len(patients)
        },
        "endpoints": {
            "websocket": "/ws",
            "patients": "/api/patients",
            "stats": "/api/stats/*",
            "performance": "/api/performance/*",
            "matrix": "/api/matrix/*",
            "triage_progress": "/api/triage/progress"
        }
    }
    

@app.on_event("startup")
async def startup_event():
    """
    Startup event handler.
    Initializes prognosis worker and daily scheduler.
    """
    # Start prognosis background worker
    prognosis_queue = PrognosisQueue()
    await prognosis_queue.start_worker()

    # Setup daily prognosis scheduler
    setup_scheduler()

    import os
    auto_start = os.getenv("AUTO_START_CHANGE_STREAM", "false").lower() == "true"
    
    if auto_start:
        try:
            from services.change_stream_listener import start_listener
            listener = start_listener()
            print(f"✅ Change stream listener auto-started on startup")
            print(f"   Watching collections: {listener.collections_to_watch}")
        except Exception as e:
            print(f"⚠️  Failed to auto-start change stream listener: {e}")
            print("   You can start it manually via POST /api/change-stream/start")


@app.on_event("shutdown")
async def shutdown_event():
    """
    Shutdown event handler.
    Stops the change stream listener gracefully.
    """
    try:
        from services.change_stream_listener import stop_listener
        stop_listener()
        print("✅ Change stream listener stopped on shutdown")
    except Exception as e:
        print(f"⚠️  Error stopping change stream listener: {e}")


@app.websocket("/ws/query")
async def websocket_query_widgets(websocket: WebSocket):
    """
    WebSocket endpoint for real-time query processing with ReAct agent.
    
    Protocol:
      - Client connects to: ws://<host>:8013/ws/query?client_id=<unique_id>
      - Client sends: {"type": "query_widgets", "query": "...", "request_id": "..."}
      - Server streams progress updates and final widget results
    """
    # Extract client_id from query parameters
    client_id = websocket.query_params.get("client_id", "anonymous")
    await websocket_endpoint(websocket, client_id)


@app.websocket("/ws")
async def websocket_manual_prognosis(websocket: WebSocket):
    """
    Manual prognosis trigger over a simple WebSocket (plain ws://).

    Protocol:
      1. Client connects to: ws://<host>:8013/ws
      2. Client sends JSON: {"patient_id": "<id>"}
      3. Server generates the clinical prognosis (first-assessment report + VALD),
         persists it to the `prognosis` collection, and sends back the result
      4. Server closes the connection

    Same generation + persistence path as the daily cron and the queue worker.
    """
    await websocket.accept()
    print("📥 /ws manual prognosis: connection accepted, waiting for message...")
    try:
        msg = await websocket.receive_json()
        print(f"📥 /ws received message: {msg}")
        patient_id = msg.get("patient_id")
        if not patient_id:
            print("⚠️  /ws: no patient_id in message")
            await websocket.send_json({"error": "patient_id is required"})
            await websocket.close()
            return

        print(f"🔄 /ws manual prognosis for patient: {patient_id}")
        # Reuse the queue singleton's agent + db handle (agent is expensive to build)
        queue = PrognosisQueue()
        db = await asyncio.to_thread(queue._get_db)
        patient_data = await asyncio.to_thread(build_patient_data_from_reports, db, patient_id)
        if not patient_data:
            print(f"⚠️  /ws: no usable first-assessment report for {patient_id}")
            await websocket.send_json({"error": f"No usable first-assessment report for patient {patient_id}"})
            await websocket.close()
            return

        vald_n = len(patient_data.get("vald_exercises") or {})
        print(f"   👤 {patient_data.get('patient_name')} | VALD exercises: {vald_n} | 🧠 generating prognosis...")
        analysis = await asyncio.to_thread(queue.agent.analyze_patient_prognosis, patient_data)
        await asyncio.to_thread(save_to_mongo, db, patient_data["patient_id"], analysis)
        print(f"✅ /ws prognosis saved for {patient_id}: "
              f"T{analysis.probability_tier.tier} — {analysis.provisional_diagnosis[:60]}")

        await websocket.send_json(analysis.model_dump() if hasattr(analysis, "model_dump") else analysis)
        await websocket.close()
    except WebSocketDisconnect:
        print("⚠️  /ws: client disconnected before completion")
        return
    except Exception as e:
        import traceback
        print(f"❌ /ws prognosis error: {e}")
        traceback.print_exc()
        try:
            await websocket.send_json({"error": str(e)})
            await websocket.close()
        except Exception:
            pass


@app.websocket("/ws/recommendation")
async def websocket_recommendation(websocket: WebSocket):
    """
    Manual recommendation trigger over WebSocket.

    Protocol:
      1. Client connects to: ws://<host>:8013/ws/recommendation
      2. Client sends JSON: {"patient_id": "<id>"}
      3. Server generates recommendation, persists to `recommendation-data`, sends back result
      4. Server closes the connection
    """
    await websocket.accept()
    try:
        msg = await websocket.receive_json()
        patient_id = msg.get("patient_id")
        if not patient_id:
            await websocket.send_json({"error": "patient_id is required"})
            await websocket.close()
            return

        from utils.mongo_connection import get_mongo_db
        _, db = await asyncio.to_thread(get_mongo_db)

        patient_data = await asyncio.to_thread(build_recommendation_input, db, patient_id)
        if not patient_data:
            await websocket.send_json({"error": f"No usable first-assessment report for patient {patient_id}"})
            await websocket.close()
            return

        from LLM.recommendation.recommendation_agent import RecommendationAgent
        agent = RecommendationAgent()
        output = await asyncio.to_thread(agent.generate, patient_data)
        await asyncio.to_thread(save_recommendation, db, patient_id, output)

        await websocket.send_json({
            "top_3_action_areas": output.top_3_action_areas,
            "next_session_plan": output.next_session_plan,
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


@app.websocket("/ws/triage")
async def websocket_triage_progress(websocket: WebSocket):
    """
    WebSocket endpoint for triage progress and refresh hints.

    Protocol:
      - Client connects to: ws://<host>:8013/ws/triage
      - Server pushes:
          { "type": "progress", "data": { ...progress_tracker payload... } }
        whenever progress changes, and
          { "type": "refresh_patients", "completed": int, "total": int, "status": str }
        roughly after every batch of completed patients (aligned with Mongo saves),
        so the frontend can refetch /api/patients and stats.
    """
    await websocket.accept()
    from api.progress_tracker import get_progress

    last_progress = None
    last_completed = None

    try:
        while True:
            progress = get_progress()

            # Always send on first loop, then only when changed
            if progress != last_progress:
                await websocket.send_json({"type": "progress", "data": progress})

                current = int(progress.get("current") or 0)
                total = int(progress.get("total") or 0)
                status = progress.get("status") or "idle"

                if last_completed is None:
                    last_completed = current

                # When completed count moves forward, hint the frontend to refresh
                if current != last_completed:
                    # Our Mongo writer saves in batches (currently every 10 patients),
                    # so send a refresh hint at those boundaries and on completion.
                    if current % 10 == 0 or status in ("completed", "error"):
                        await websocket.send_json(
                            {
                                "type": "refresh_patients",
                                "completed": current,
                                "total": total,
                                "status": status,
                            }
                        )
                    last_completed = current

                last_progress = progress

            # Poll progress file every 2 seconds
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        # Client disconnected; nothing else to do
        return
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "error": str(e)})
            await websocket.close()
        except Exception:
            pass
