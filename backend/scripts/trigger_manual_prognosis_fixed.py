import sys
import os
import asyncio
import logging
from pathlib import Path

# Setup logging to see what's happening
logging.basicConfig(level=logging.INFO)

# Add current directory to sys.path
sys.path.insert(0, os.getcwd())

# Import queue manager
try:
    from api.queue_manager import PrognosisQueue
    print("✅ Successfully imported PrognosisQueue")
except ImportError as e:
    print(f"❌ Failed to import PrognosisQueue: {e}")
    sys.exit(1)

async def main():
    patient_id = "6a02da4701012c75bf7fda03"
    print(f"🚀 Manually triggering prognosis for patient: {patient_id}")

    queue = PrognosisQueue()

    # We need to mock the websocket manager or ensure it doesn't break
    # Since we're running this as a standalone script, we don't have active connections

    # Directly call the internal processing logic to bypass the queue loop if needed
    # but using the queue is safer to ensure all logic (fetching data, etc.) is used.

    # 1. Fetch data
    print(f"🔍 Fetching data for {patient_id}...")
    patient_data = queue._fetch_patient_data(patient_id)

    if not patient_data:
        print(f"❌ Patient {patient_id} not found in database.")
        return

    print(f"✅ Found patient data for {patient_data.get('patient_name', 'Unknown')}")

    # 2. Run analysis
    print("🧠 Running AI analysis (this may take a minute)...")
    try:
        # Wrap the synchronous agent call
        result = await asyncio.to_thread(queue.agent.analyze_patient_prognosis, patient_data)
        print("✅ Analysis complete!")

        # 3. Output a summary
        if hasattr(result, "provisional_diagnosis"):
            print(f"\n--- PROGNOSIS RESULT ---")
            print(f"Diagnosis: {result.provisional_diagnosis}")
            print(f"Tier: {result.probability_tier.tier} ({result.probability_tier.label})")
            print(f"Timeline: {result.expected_recovery_timeline}")
            print(f"------------------------\n")
        else:
            print(f"Result: {result}")

    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
