import asyncio
import os
import sys
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv

# Current file is in scripts/ so parent is project root
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

async def main():
    patient_id = "6a02da4701012c75bf7fda03"
    print(f"Manual trigger for patient {patient_id}...")
    
    load_dotenv(project_root / ".env")
    
    # Import inside main
    try:
        from LLM.prognosis.prognosis_agent import ClinicalPrognosisAgent
    except ImportError as e:
        print(f"ImportError: {e}")
        return

    agent = ClinicalPrognosisAgent()
    
    mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017/"
    db_name = os.getenv("MONGO_DB", "stance-dashboard")
    client = MongoClient(mongo_uri, tlsAllowInvalidCertificates=True)
    db = client[db_name]
    
    patient_data = db["classification"].find_one({"patient_id": patient_id})
    
    if not patient_data:
        print(f"Error: Patient {patient_id} not found.")
        return
        
    patient_data.pop("_id", None)
    print(f"Analyzing patient: {patient_data.get('patient_name', 'Unknown')}")
    
    try:
        result = await asyncio.to_thread(agent.analyze_patient_prognosis, patient_data)
        print("\n✅ Prognosis Result Generated:")
    except Exception as e:
        print(f"❌ Error during analysis: {e}")

if __name__ == "__main__":
    asyncio.run(main())
