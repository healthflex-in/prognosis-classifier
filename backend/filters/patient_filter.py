#!/usr/bin/env python3
"""
Patient Filter
Filters patients based on first-assessment data, with a validated prognosis
fallback when no first assessment is available.
Uses data injectors to fetch data from MongoDB.
"""

import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# Import data injectors
import importlib.util
data_injectors_dir = backend_dir / "data-injectors"

def load_module_from_path(module_name, file_path):
    """Load a module from a file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

mongo_injector_module = load_module_from_path(
    "mongo_reports_injector",
    data_injectors_dir / "mongo_reports_injector.py"
)
MongoReportsInjector = mongo_injector_module.MongoReportsInjector


class PatientFilter:
    """Filter patients based on clinical criteria."""

    _INVALID_PROGNOSIS_LABELS = {
        "unknown",
        "unclear",
        "unknown musculoskeletal condition",
        "musculoskeletal dysfunction",
    }

    def __init__(self, months_back: Optional[int] = 5, current_date: Optional[datetime] = None):
        """
        Initialize the patient filter.

        Args:
            months_back: Number of months to look back (None means no date limit - all patients)
            current_date: Current date for filtering (default: today)
        """
        self.months_back = months_back
        self.current_date = current_date or datetime.now()
        if months_back is None:
            # No date limit - process all patients regardless of date
            self.cutoff_date = None
            self.cutoff_timestamp = None
        else:
            self.cutoff_date = self.current_date - timedelta(days=months_back * 30)
            self.cutoff_timestamp = int(self.cutoff_date.timestamp() * 1000)

    @staticmethod
    def _object_id_candidates(patient_id: str) -> List[Any]:
        """Return ObjectId and string forms used by older prognosis documents."""
        candidates: List[Any] = [patient_id]
        if isinstance(patient_id, str) and len(patient_id) == 24:
            try:
                from bson import ObjectId
                candidates.insert(0, ObjectId(patient_id))
            except Exception:
                pass
        return candidates

    @staticmethod
    def _timestamp(value: Any) -> Optional[int]:
        """Convert supported Mongo timestamps to epoch milliseconds."""
        if isinstance(value, datetime):
            return int(value.timestamp() * 1000)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, dict):
            raw = value.get('$numberLong') or value.get('$date')
            if isinstance(raw, dict):
                raw = raw.get('$numberLong')
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None
        return None

    def _get_valid_prognosis(self, loader: Any, patient_id: str) -> Optional[Dict[str, Any]]:
        """Read a usable prognosis for a patient, accepting ObjectId/string IDs."""
        candidates = self._object_id_candidates(patient_id)
        prognosis_collection = loader.db["prognosis"]
        prognosis = prognosis_collection.find_one(
            {"patient_id": {"$in": candidates}},
            sort=[("updated_at", -1)],
        )
        if not prognosis:
            return None

        diagnosis = str(prognosis.get("provisional_diagnosis") or "").strip()
        if not diagnosis or diagnosis.lower() in self._INVALID_PROGNOSIS_LABELS:
            return None

        sufficiency = prognosis.get("diagnostic_sufficiency") or {}
        if sufficiency.get("is_sufficient") is not True:
            return None

        prognosis_timestamp = self._timestamp(prognosis.get("updated_at"))
        if prognosis_timestamp is None:
            return None
        if self.cutoff_timestamp is not None and prognosis_timestamp < self.cutoff_timestamp:
            return None

        return prognosis

    def _build_prognosis_fallback(self, patient_id: str, loader: Any) -> Optional[Dict[str, Any]]:
        """Build a triage record from a valid existing prognosis when first assessment is absent."""
        prognosis = self._get_valid_prognosis(loader, patient_id)
        if not prognosis:
            return None

        prognosis_timestamp = self._timestamp(prognosis.get("updated_at"))
        patient_name = prognosis.get("patient_name") or "Unknown"
        try:
            from bson import ObjectId
            user_id = ObjectId(patient_id) if len(patient_id) == 24 else patient_id
            user = loader.db["users"].find_one(
                {"_id": user_id},
                {"profileData.firstName": 1, "profileData.lastName": 1},
            )
            profile = (user or {}).get("profileData") or {}
            patient_name = (
                f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip()
                or patient_name
            )
        except Exception:
            pass

        prior_prognosis = {
            "provisional_diagnosis": str(prognosis.get("provisional_diagnosis")).strip(),
            "probability_tier": prognosis.get("probability_tier") or {},
            "diagnostic_sufficiency": prognosis.get("diagnostic_sufficiency") or {},
            "updated_at": prognosis.get("updated_at"),
            "source": "existing_prognosis",
        }
        fallback_record = {
            "isFirstAssessment": False,
            "provenance": "prognosis_fallback",
            "prior_prognosis": prior_prognosis,
        }
        return {
            "patient_id": patient_id,
            "patient_name": patient_name,
            # Keep clinician diagnosis empty; prior prognosis is separate context.
            "diagnosis": "",
            "complaints": "",
            "date": (
                datetime.fromtimestamp(prognosis_timestamp / 1000).strftime('%Y-%m-%d')
                if prognosis_timestamp else "unknown"
            ),
            "timestamp": prognosis_timestamp or 0,
            "first_assessment_data": fallback_record,
            "prior_prognosis": prior_prognosis,
        }

    def get_filtered_patients(self, patient_ids: Optional[List[str]] = None, update_progress: bool = False) -> List[Dict[str, Any]]:
        """
        Filter patients based on first-assessment data, or a validated prognosis
        fallback when no first assessment exists.
        """
        eligible_records = []
        injector = MongoReportsInjector()

        try:
            if patient_ids:
                total = len(patient_ids)
                for idx, patient_id in enumerate(patient_ids, 1):
                    try:
                        if idx % 10 == 0 or idx == 1 or idx == total:
                            print(f"   Processing patient {idx}/{total}...", end='\r')
                            if update_progress:
                                try:
                                    from api.progress_tracker import set_progress
                                    set_progress("running", idx, total, message=f"Filtering patient {idx}/{total}...")
                                except Exception:
                                    pass

                        docs = injector.load_data(patient_id, stance_id=patient_id, max_days_range=7)
                        first_assessment_doc = next(
                            (doc for doc in docs if doc.metadata.get('record_type') == 'first_assessment'),
                            None
                        )

                        if first_assessment_doc:
                            record_data = self._process_patient_record(
                                first_assessment_doc,
                                patient_id,
                                injector.loader,
                            )
                            # The loader may synthesize a first record when the
                            # view has reports but none is truly flagged first.
                            # Fall back only after checking the original raw flag.
                            if not record_data:
                                record_data = self._build_prognosis_fallback(patient_id, injector.loader)
                        else:
                            record_data = self._build_prognosis_fallback(patient_id, injector.loader)

                        if record_data:
                            if record_data.get("first_assessment_data", {}).get("provenance") == "prognosis_fallback":
                                print(f"\n   ℹ️  Using validated prognosis fallback for {patient_id}")
                            eligible_records.append(record_data)
                    except Exception as e:
                        if idx <= 5 or idx % 100 == 0:
                            print(f"⚠️  Error processing patient {patient_id}: {e}")
                        continue
                print()
            else:
                print("ℹ️  No patient IDs provided. Use list_patients() first to get patient IDs.")
        finally:
            injector.close()

        return eligible_records

    def _process_patient_record(
        self,
        first_assessment_doc: Any,
        patient_id: str,
        loader: Any,
    ) -> Optional[Dict[str, Any]]:
        """Process a first-assessment document for triage eligibility."""
        import json

        try:
            record = json.loads(first_assessment_doc.page_content)
        except Exception:
            record = first_assessment_doc.page_content if isinstance(first_assessment_doc.page_content, dict) else {}

        if not record.get('isFirstAssessment'):
            return None

        # The transformed record can contain a synthesized isFirstAssessment
        # flag. Only accept it when the original Mongo report was truly marked
        # as the first assessment.
        raw_data = record.get('raw_data', {}) or {}
        if raw_data and raw_data.get('isFirstAssessment') is not True:
            return None

        ts = self._timestamp(record.get('event_start_time'))
        if ts is None:
            ts = self._timestamp(record.get('createdAt'))

        if self.cutoff_timestamp is not None and (ts is None or ts < self.cutoff_timestamp):
            return None

        diag = record.get('diagnosis', '')
        if not isinstance(diag, str) or not diag.strip():
            raw_data = record.get('raw_data', {}) or {}
            records = raw_data.get('records', {}) or {}
            diag = (records.get('provisionalDiagnosis', {}).get('diagnosis') or '')
        diag = diag.strip() if isinstance(diag, str) else ''
        if not diag:
            return None

        complaints = record.get('chief_complaints', '')
        if not complaints:
            raw_data = record.get('raw_data', {}) or {}
            records = raw_data.get('records', {}) or {}
            complaints = records.get('clinicalDetails', {}).get('chiefComplaints', '') or ''

        patient_name = first_assessment_doc.metadata.get('patient_name')
        if not patient_name or patient_name == 'Unknown':
            try:
                patient_info, _ = loader.get_patient_reports(patient_id)
                if patient_info:
                    patient_name = patient_info.get('patient_name')
            except Exception as e:
                print(f"   ⚠️  Could not fetch patient name: {e}")
        patient_name = patient_name or 'Unknown'

        return {
            "patient_id": patient_id,
            "patient_name": patient_name,
            "diagnosis": diag,
            "complaints": complaints,
            "date": datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d') if ts else "unknown",
            "timestamp": ts or 0,
            "first_assessment_data": record,
        }

    def list_all_patients(self, limit: Optional[int] = None, update_progress: bool = False) -> List[str]:
        """List all patient IDs from MongoDB."""
        injector = MongoReportsInjector()
        patient_ids = []
        try:
            def progress_callback(current: int, total: int):
                if update_progress:
                    try:
                        from api.progress_tracker import set_progress
                        set_progress("running", current, total, message=f"Listing patients from MongoDB... ({current}/{total})")
                    except Exception:
                        pass

            if update_progress:
                try:
                    from api.progress_tracker import set_progress
                    set_progress("running", 0, 0, message="Listing patients from MongoDB...")
                except Exception:
                    pass

            patients = injector.loader.list_patients(
                limit=limit,
                progress_callback=progress_callback if update_progress else None,
            )
            patient_ids = [str(p.get('_id')) for p in patients if p.get('_id')]
            if update_progress:
                try:
                    from api.progress_tracker import set_progress
                    set_progress("running", len(patient_ids), len(patient_ids), message=f"Found {len(patient_ids)} patients. Filtering...")
                except Exception:
                    pass
        except Exception as e:
            print(f"⚠️  Error listing patients: {e}")
            if update_progress:
                try:
                    from api.progress_tracker import set_progress
                    set_progress("error", 0, 0, error=str(e), message="Error listing patients")
                except Exception:
                    pass
        finally:
            injector.close()
        return patient_ids

    def filter_all_patients(self, limit: Optional[int] = None, update_progress: bool = False) -> List[Dict[str, Any]]:
        """Filter all patients in the database."""
        if limit is None or limit == 0:
            print("📋 Listing ALL patients (no limit)...")
        else:
            print(f"📋 Listing patients (limit: {limit})...")

        try:
            patient_ids = self.list_all_patients(limit=limit, update_progress=update_progress)
        except Exception as e:
            print(f"❌ Error listing patients: {e}")
            if update_progress:
                try:
                    from api.progress_tracker import set_progress
                    set_progress("error", 0, 0, error=str(e), message="Error listing patients")
                except Exception:
                    pass
            return []

        if not patient_ids:
            print("⚠️  No patients found")
            if update_progress:
                try:
                    from api.progress_tracker import set_progress
                    set_progress("completed", 0, 0, message="No patients found")
                except Exception:
                    pass
            return []

        print(f"🔍 Filtering {len(patient_ids)} patients...")
        if self.cutoff_date:
            print(f"   Cutoff date: {self.cutoff_date.strftime('%Y-%m-%d')}")
            print(f"   Criteria: FirstAssessment within last {self.months_back} months, or valid prognosis fallback")
        else:
            print("   Criteria: FirstAssessment with diagnosis, or valid prognosis fallback (no date limit)")

        if update_progress:
            try:
                from api.progress_tracker import set_progress
                set_progress("running", 0, len(patient_ids), message=f"Filtering {len(patient_ids)} patients...")
            except Exception:
                pass

        print("   Processing patients in batches...")
        eligible = self.get_filtered_patients(patient_ids, update_progress=update_progress)
        print(f"✅ Found {len(eligible)} eligible patients")
        if update_progress:
            try:
                from api.progress_tracker import set_progress
                set_progress("running", len(eligible), len(eligible), message=f"Found {len(eligible)} eligible patients. Starting classification...")
            except Exception:
                pass
        return eligible


if __name__ == "__main__":
    import sys
    filter_agent = PatientFilter(months_back=5)
    if len(sys.argv) > 1:
        patient_ids = sys.argv[1:]
        print(f"🔍 Filtering specific patients: {patient_ids}")
        results = filter_agent.get_filtered_patients(patient_ids)
    else:
        limit = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 100
        results = filter_agent.filter_all_patients(limit=limit)

    print(f"\n✅ Found {len(results)} eligible patients:\n")
    for record in results:
        print(f"Patient: {record['patient_name']} ({record['patient_id']})")
        print(f"  Diagnosis: {record['diagnosis']}")
        print(f"  Date: {record['date']}")
        complaints = record.get('complaints', '')
        print(f"  Complaints: {complaints[:100]}..." if len(complaints) > 100 else f"  Complaints: {complaints or 'N/A'}")
