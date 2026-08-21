import os
from pymongo import MongoClient
import json
from bson import json_util

def check_patient():
    mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017/"
    client = MongoClient(mongo_uri, tlsAllowInvalidCertificates=True, tlsAllowInvalidHostnames=True)
    db = client["stance-dashboard"]

    patient_id = "6a02da4701012c75bf7fda03"
    doc = db["structured-user-reports"].find_one({"patient_id": patient_id})

    if doc:
        print(f"Found document for patient {patient_id}")
        if "reports" in doc and doc["reports"]:
            print(f"Number of reports: {len(doc['reports'])}")
            for i, report in enumerate(doc['reports']):
                est = report.get("event_start_time")
                print(f"Report {i} event_start_time: {est} (Type: {type(est)})")
        else:
            print("No reports field found in document")
    else:
        # Let's try to find any document to see the structure
        print(f"Patient {patient_id} not found. Checking one random document...")
        sample = db["structured-user-reports"].find_one()
        if sample:
            print("Sample document structure:")
            print(json.dumps(sample, indent=2, default=json_util.default))
        else:
            print("Collection 'structured-user-reports' is empty or missing.")

if __name__ == "__main__":
    check_patient()
