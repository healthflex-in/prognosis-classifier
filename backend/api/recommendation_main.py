"""
Standalone recommendation service.
Exposes only the recommendation + partial-reports REST routes and the
/ws/recommendation WebSocket — runs on port 8014 independently of the
main prognosis API (port 8013).
"""
import asyncio
from pathlib import Path
import sys

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.routes import recommendation, partial_reports

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


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "Recommendation Service"}


@app.websocket("/ws/recommendation")
async def websocket_recommendation(websocket: WebSocket):
    await websocket.accept()
    try:
        msg = await websocket.receive_json()
        patient_id = msg.get("patient_id")
        if not patient_id:
            await websocket.send_json({"error": "patient_id is required"})
            await websocket.close()
            return

        from utils.mongo_connection import get_mongo_db
        from bson import ObjectId
        _, db = await asyncio.to_thread(get_mongo_db)

        try:
            pid_obj = ObjectId(patient_id) if len(str(patient_id)) == 24 else patient_id
        except Exception:
            pid_obj = patient_id

        partial = await asyncio.to_thread(
            lambda: db["partial-reports"].find_one({"patient_id": pid_obj})
        )
        current_hash = partial.get("hash") if partial else None

        rec_doc = await asyncio.to_thread(
            lambda: db["recommendation-data"].find_one({"patient_id": pid_obj})
        )
        if rec_doc and current_hash and rec_doc.get("input_hash") == current_hash:
            await websocket.send_json({
                "top_3_action_areas": rec_doc["top_3_action_areas"],
                "next_session_plan":  rec_doc["next_session_plan"],
                "cached": True,
            })
            await websocket.close()
            return

        from api.routes.recommendation import build_recommendation_input, save_recommendation
        patient_data = await asyncio.to_thread(build_recommendation_input, db, patient_id)
        if not patient_data:
            await websocket.send_json({"error": f"No usable first-assessment report for patient {patient_id}"})
            await websocket.close()
            return

        if partial and partial.get("fields"):
            pf = partial["fields"]
            sd = patient_data.setdefault("source_data", {})
            if pf.get("chief_complaint"):       sd["chief_complaint"]           = pf["chief_complaint"]
            if pf.get("client_history"):        sd["clinical_history"]          = pf["client_history"]
            if pf.get("subjective_assessment"): sd["subjective_notes"]          = pf["subjective_assessment"]
            if pf.get("provisional_diagnosis"): sd["provisional_diagnosis_raw"] = pf["provisional_diagnosis"]

        from LLM.recommendation.recommendation_agent import RecommendationAgent
        agent = RecommendationAgent()
        output = await asyncio.to_thread(agent.generate, patient_data)
        await asyncio.to_thread(save_recommendation, db, patient_id, output, current_hash)

        await websocket.send_json({
            "top_3_action_areas": output.top_3_action_areas,
            "next_session_plan":  output.next_session_plan,
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
