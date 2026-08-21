import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment variables from backend/.env
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(env_path)

def get_db():
    mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017/"
    db_name = os.getenv("MONGO_DB", "stance-dashboard")
    print(f"Connecting to: {mongo_uri.split('@')[-1] if '@' in mongo_uri else mongo_uri}")
    client = MongoClient(mongo_uri, tlsAllowInvalidCertificates=True, tlsAllowInvalidHostnames=True)
    return client[db_name]

def audit():
    db = get_db()
    print(f"Connected to DB: {db.name}")
    collections = db.list_collection_names()

    # 1. Get all patients who have clinical reports
    print("\nChecking 'structured-user-reports' for patients...")
    cursor = db["structured-user-reports"].find({}, {"patient_id": 1, "reports": 1})
    first_assessment_patients = {}
    for doc in cursor:
        pid = str(doc.get("patient_id"))
        reports = doc.get("reports", [])
        if pid and reports:
            # Sort reports by event_start_time to find the first one
            sorted_reports = sorted(reports, key=lambda r: r.get('event_start_time', 0))
            first_report = sorted_reports[0]
            records = first_report.get('records', {})
            diagnosis = records.get('provisionalDiagnosis', {}).get('diagnosis', '')
            first_assessment_patients[pid] = diagnosis

    # 2. Get all patients from 'classification' (triage)
    print("Checking 'classification' for patients...")
    class_cursor = db["classification"].find({}, {"patient_id": 1, "canonical_diagnosis": 1, "status": 1})
    classification_patients = {}
    for doc in class_cursor:
        pid = str(doc.get("patient_id"))
        if pid:
            classification_patients[pid] = {
                "diagnosis": doc.get("canonical_diagnosis"),
                "status": doc.get("status")
            }

    # 3. Get all patients who have a prognosis
    print("Checking 'prognosis' for patients...")
    prognosis_cursor = db["prognosis"].find({}, {"patient_id": 1})
    prognosis_pids = set()
    for doc in prognosis_cursor:
        pid = doc.get("patient_id")
        if pid:
            prognosis_pids.add(str(pid))

    # 4. Get all unique VALD records
    vald_collections = ["objectiveAssessments", "vald-exercise-data", "vald-user-data", "vald_sessions", "sessions", "objectiveAssessment"]
    vald_pids = set()
    for coll in vald_collections:
        if coll in collections:
            print(f"Checking '{coll}' for patients...")
            # Some collections might use 'userId' or 'user_id'
            v_cursor = db[coll].find({}, {"patient_id": 1, "userId": 1, "user_id": 1})
            for doc in v_cursor:
                pid = doc.get("patient_id") or doc.get("userId") or doc.get("user_id")
                if pid:
                    vald_pids.add(str(pid))

    # Combined patients (either clinical or triage)
    all_pids = set(first_assessment_patients.keys()) | set(classification_patients.keys())

    print(f"\n--- Statistics ---")
    print(f"Total unique patients (Clinical/Triage): {len(all_pids)}")
    print(f"Patients with clinical reports: {len(first_assessment_patients)}")
    print(f"Patients with triage classifications: {len(classification_patients)}")
    print(f"Patients with VALD records: {len(vald_pids)}")
    print(f"Total patients with existing prognosis: {len(prognosis_pids)}")

    missing_prognosis = []
    has_assessment_but_no_vald = []

    for pid in all_pids:
        if pid not in prognosis_pids:
            clinical_diag = first_assessment_patients.get(pid)
            triage_data = classification_patients.get(pid, {})
            triage_diag = triage_data.get("diagnosis")
            triage_status = triage_data.get("status")
            has_vald = pid in vald_pids

            has_clinical = clinical_diag and str(clinical_diag).strip().lower() not in ["unknown", "none", ""]
            has_triage = triage_diag and str(triage_diag).strip().lower() not in ["unclear", "none", ""]

            if has_clinical or has_triage:
                if has_vald:
                    missing_prognosis.append({
                        "id": pid,
                        "clinical": clinical_diag if has_clinical else None,
                        "triage": triage_diag if has_triage else None,
                        "status": triage_status,
                        "has_vald": has_vald
                    })
                else:
                    has_assessment_but_no_vald.append({
                        "id": pid,
                        "clinical": clinical_diag if has_clinical else None,
                        "triage": triage_diag if has_triage else None,
                    })

    print(f"\n--- Audit Results ---")
    print(f"Patients with valid assessment AND VALD records, but MISSING prognosis: {len(missing_prognosis)}")
    print(f"Patients with valid assessment but NO VALD records (and missing prognosis): {len(has_assessment_but_no_vald)}")

    if missing_prognosis:
        print("\nExample IDs (Valid assessment + VALD, missing prognosis):")
        for entry in missing_prognosis[:20]:
            diag_str = f"(Clinical: {entry['clinical']}, Triage: {entry['triage']})"
            print(f"  - {entry['id']} {diag_str}")

    if has_assessment_but_no_vald:
        print("\nExample IDs (Valid assessment, NO VALD, missing prognosis):")
        for entry in has_assessment_but_no_vald[:10]:
            diag_str = f"(Clinical: {entry['clinical']}, Triage: {entry['triage']})"
            print(f"  - {entry['id']} {diag_str}")

if __name__ == "__main__":
    audit()
