import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import List, Set
from pymongo import MongoClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .queue_manager import prognosis_queue

logger = logging.getLogger(__name__)

def get_db():
    mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017/"
    db_name = os.getenv("MONGO_DB", "stance-dashboard")
    client = MongoClient(mongo_uri, tlsAllowInvalidCertificates=True, tlsAllowInvalidHostnames=True)
    return client[db_name]

async def scan_for_new_assessments():
    """
    Scans for patients who had their first assessment yesterday but lack a prognosis.
    Runs daily at 8:00 AM IST (02:30 UTC).
    """
    logger.info("🔍 Starting daily prognosis scan...")
    try:
        db = await asyncio.to_thread(get_db)

        # 1. Define the timeframe: Yesterday (00:00:00 to 23:59:59)
        # We use UTC for calculation
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        start_of_yesterday = datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0)
        end_of_yesterday = datetime(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59)

        # event_start_time in MongoDB is a float representing milliseconds
        start_ms = start_of_yesterday.timestamp() * 1000
        end_ms = end_of_yesterday.timestamp() * 1000

        logger.info(f"Scanning 'structured-user-reports' for timeframe (ms): {start_ms} to {end_ms}")

        # 2. Get all patients who have clinical reports from yesterday
        # We query the view for any report updated or created yesterday
        cursor = db["structured-user-reports"].find({
            "reports.event_start_time": {
                "$gte": start_ms,
                "$lte": end_ms
            }
        }, {"patient_id": 1})

        yesterday_pids = set()
        for doc in cursor:
            pid = doc.get("patient_id")
            if pid:
                yesterday_pids.add(str(pid))

        if not yesterday_pids:
            logger.info("No new assessments found from yesterday.")
            return

        logger.info(f"Found {len(yesterday_pids)} patients with reports from yesterday.")

        # 3. Filter for those who don't have a prognosis yet
        # Ensure we check both string and ObjectId formats for patient_id in existing prognosis collection
        from bson import ObjectId
        query_ids = []
        for pid in yesterday_pids:
            query_ids.append(pid)
            try:
                query_ids.append(ObjectId(pid))
            except Exception:
                pass

        existing_prognosis_cursor = db["prognosis"].find({
            "patient_id": {"$in": query_ids}
        }, {"patient_id": 1})

        pids_with_prognosis = set()
        for doc in existing_prognosis_cursor:
            pid = doc.get("patient_id")
            if pid:
                pids_with_prognosis.add(str(pid))

        to_process = yesterday_pids - pids_with_prognosis

        if not to_process:
            logger.info("All patients from yesterday already have a prognosis.")
            return

        logger.info(f"Adding {len(to_process)} patients to prognosis queue.")

        # 4. Add to queue
        for pid in to_process:
            await prognosis_queue.add_task(pid)

    except Exception as e:
        logger.error(f"❌ Error during daily prognosis scan: {e}")

def setup_scheduler():
    """Initialize and start the daily scheduler."""
    scheduler = AsyncIOScheduler()

    # 8:00 AM IST is 02:30 AM UTC
    trigger = CronTrigger(hour=2, minute=30, timezone='UTC')

    scheduler.add_job(
        scan_for_new_assessments,
        trigger=trigger,
        name="daily_prognosis_scan",
        id="daily_prognosis_scan"
    )

    scheduler.start()
    logger.info("📅 Scheduler started: Daily prognosis scan at 08:00 IST (02:30 UTC)")
    return scheduler
