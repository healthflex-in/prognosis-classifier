import asyncio
import logging
import traceback
from typing import Optional
from datetime import datetime

from .websocket_manager import manager
from LLM.prognosis.prognosis_agent import ClinicalPrognosisAgent
from LLM.prognosis.push_prognosis_to_mongo import save_to_mongo, build_patient_data_from_reports
from pymongo import MongoClient
import os

logger = logging.getLogger(__name__)

class PrognosisQueue:
    """
    Singleton queue for managing prognosis generation tasks.
    Handles both automated daily runs and manual WebSocket triggers.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PrognosisQueue, cls).__new__(cls)
            cls._instance.queue = asyncio.Queue()
            cls._instance.worker_task = None
            cls._instance.agent = ClinicalPrognosisAgent()
        return cls._instance

    async def add_task(self, patient_id: str, client_id: Optional[str] = None, request_id: Optional[str] = None):
        """Add a patient to the prognosis generation queue."""
        await self.queue.put({
            "patient_id": patient_id,
            "client_id": client_id,
            "request_id": request_id,
            "timestamp": datetime.now().isoformat()
        })
        logger.info(f"📥 Added patient {patient_id} to prognosis queue (Client: {client_id})")

    async def start_worker(self):
        """Start the background worker task."""
        if self.worker_task is None or self.worker_task.done():
            self.worker_task = asyncio.create_task(self._worker_loop())
            logger.info("🚀 Prognosis background worker started")

    async def _worker_loop(self):
        """Main worker loop that processes tasks from the queue."""
        while True:
            task = await self.queue.get()
            patient_id = task["patient_id"]
            client_id = task["client_id"]
            request_id = task["request_id"]

            try:
                logger.info(f"🔄 Processing prognosis for patient: {patient_id}")

                if client_id:
                    await manager.send_progress(
                        client_id,
                        "prognosis_started",
                        f"Generating clinical prognosis for patient {patient_id}...",
                        request_id
                    )

                # 1. Build patient data from the first-assessment report + VALD.
                # Same report-based path the change-stream listener uses, so cron
                # and manual triggers produce identical, VALD-aware input.
                db = await asyncio.to_thread(self._get_db)
                patient_data = await asyncio.to_thread(build_patient_data_from_reports, db, patient_id)

                if not patient_data:
                    error_msg = f"No usable first-assessment report found for patient {patient_id}."
                    logger.error(f"❌ {error_msg}")
                    if client_id:
                        await manager.send_error(client_id, error_msg, request_id)
                    continue

                # 2. Run prognosis agent (wrapped in thread as it makes synchronous LLM/API calls)
                if client_id:
                    await manager.send_progress(
                        client_id,
                        "analyzing_prognosis",
                        "AI agent is analyzing clinical reports and VALD data...",
                        request_id
                    )

                result = await asyncio.to_thread(self.agent.analyze_patient_prognosis, patient_data)

                # 3. Persist to the prognosis collection (upsert) — the whole point.
                await asyncio.to_thread(save_to_mongo, db, patient_data["patient_id"], result)
                logger.info(f"✅ Prognosis generated and saved for {patient_id}")

                if client_id:
                    await manager.send_progress(
                        client_id,
                        "prognosis_ready",
                        "Clinical prognosis has been generated and saved.",
                        request_id
                    )

                    # Push the actual data to the dashboard
                    await manager.send_message(client_id, {
                        "type": "prognosis_result",
                        "patient_id": patient_id,
                        "request_id": request_id,
                        "data": result if isinstance(result, dict) else result.model_dump() if hasattr(result, "model_dump") else str(result)
                    })

            except Exception as e:
                logger.error(f"❌ Error in prognosis worker for {patient_id}: {e}")
                logger.error(traceback.format_exc())
                if client_id:
                    await manager.send_error(client_id, f"Prognosis generation failed: {str(e)}", request_id)
            finally:
                self.queue.task_done()

    def _get_db(self):
        """Open a MongoDB handle for the prognosis database."""
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017/"
        db_name = os.getenv("MONGO_DB", "stance-dashboard")
        client = MongoClient(mongo_uri, tlsAllowInvalidCertificates=True, tlsAllowInvalidHostnames=True)
        return client[db_name]

# Global instance
prognosis_queue = PrognosisQueue()
