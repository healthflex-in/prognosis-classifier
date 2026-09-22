"""Build recommendation inputs from a validated draft without saving report records."""
import json
from bson import ObjectId
from api.routes.partial_reports import PartialReportPayload, compute_partial_hash


def prepare_recommendation(db, patient_id, partial, report_id=None):
    pid = ObjectId(patient_id)
    if not partial or not partial.get('fields'):
        raise ValueError('Save the assessment draft before generating recommendations')
    fields = PartialReportPayload(**partial['fields']).model_dump()
    draft_report_id = fields.get('report_id')
    if report_id and draft_report_id != report_id:
        raise ValueError('Assessment draft changed. Please generate again.')
    if draft_report_id:
        user = db.users.find_one({'_id': pid, 'userType': 'PATIENT'})
        report = db.reports.find_one({'_id': ObjectId(draft_report_id), 'patient': pid, 'isFirstAssessment': True}, {'_id': 1})
        if not user or not report:
            raise ValueError('Patient or first-assessment report not found')
        from utils.vald_extractor import extract_vald_first_session
        try:
            vald = extract_vald_first_session(db, patient_id)
        except Exception:
            vald = {}
        data = {'patient_id': patient_id, 'source_data': {}, **vald}
    else:
        # Existing clients still send four fields; retain their saved-report context.
        from api.routes.recommendation import build_recommendation_input
        data = build_recommendation_input(db, patient_id)
        if not data:
            raise ValueError('Please refresh the dashboard and submit the complete assessment draft')
    source = data.setdefault('source_data', {})
    for src, dest in [('chief_complaint','chief_complaint'), ('client_history','clinical_history'),
                      ('subjective_assessment','subjective_notes'), ('provisional_diagnosis','provisional_diagnosis_raw')]:
        source[dest] = fields[src]
    if draft_report_id:
        source.update(patient_goals=json.dumps(fields['short_term_goals'], ensure_ascii=False),
                      objective_notes=json.dumps(fields['objective_assessment'], ensure_ascii=False),
                      existing_recommendations=json.dumps(fields['recommendations'], ensure_ascii=False),
                      nprs=fields['nprs'])
    return data, compute_partial_hash({'report_id': draft_report_id, 'input': data})
