import asyncio
import json
import logging
from typing import Dict, Any

# Mock manager to capture sent messages
class MockManager:
    def __init__(self):
        self.sent_messages = []
        self.active_connections = {"test_client": "mock_websocket"}

    async def send_message(self, client_id, message):
        print(f"DEBUG: Sending to {client_id}: {message.get('type')} - {message.get('step') or message.get('details') or ''}")
        self.sent_messages.append(message)

    async def send_progress(self, client_id, step, details, request_id=None):
        await self.send_message(client_id, {"type": "progress", "step": step, "details": details, "request_id": request_id})

    async def send_error(self, client_id, error, request_id=None):
        await self.send_message(client_id, {"type": "error", "error": error, "request_id": request_id})

# Mock Agent
class MockAgent:
    def analyze_patient_prognosis(self, patient_data):
        return {"prognosis": "Good", "summary": "Test prognosis for " + patient_data.get("patient_name", "Unknown")}

# Mock data loader helper
def mock_fetch(self, patient_id):
    return {"patient_id": patient_id, "patient_name": "Test Patient"}

async def test_queue_processing():
    print("Starting Queue processing test...")

    # 1. Setup mocks in queue_manager
    import api.queue_manager as qm
    original_manager = qm.manager
    original_agent = qm.PrognosisQueue().agent
    original_fetch = qm.PrognosisQueue._fetch_patient_data

    mock_mgr = MockManager()
    qm.manager = mock_mgr
    qm.PrognosisQueue().agent = MockAgent()
    qm.PrognosisQueue()._fetch_patient_data = lambda pid: {"patient_id": pid, "patient_name": "Test Patient " + pid}

    # 2. Add a task
    queue = qm.prognosis_queue
    await queue.add_task("patient_123", "test_client", "req_001")

    # 3. Start worker briefly
    worker_task = asyncio.create_task(queue._worker_loop())

    # Give it some time to process
    await asyncio.sleep(2)

    # 4. Verify results
    print(f"\nCaptured {len(mock_mgr.sent_messages)} messages")
    for msg in mock_mgr.sent_messages:
        print(f" - {msg.get('type')}: {msg.get('step') or msg.get('details') or msg.get('patient_id')}")

    worker_task.cancel()

    # Check if we got the result
    has_result = any(msg.get("type") == "prognosis_result" for msg in mock_mgr.sent_messages)
    print(f"\nSuccess: {has_result}")

    # Cleanup
    qm.manager = original_manager
    qm.PrognosisQueue().agent = original_agent
    qm.PrognosisQueue()._fetch_patient_data = original_fetch

if __name__ == "__main__":
    asyncio.run(test_queue_processing())
