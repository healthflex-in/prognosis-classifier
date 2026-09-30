"""Offline regression tests for draft-based recommendation inputs."""
import sys
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from bson import ObjectId
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.routes.partial_reports import PartialReportPayload, compute_partial_hash
from api.recommendation_draft import prepare_recommendation

PID = '000000000000000000000001'
RID = '000000000000000000000002'

def draft():
    return dict(report_id=RID, chief_complaint='Knee pain', client_history='After running',
                subjective_assessment='Pain on stairs', provisional_diagnosis='Knee pain',
                nprs=0, short_term_goals=[{'goal':'Climb stairs'}],
                objective_assessment={'tests':[{'testName':'Knee flexion','value':90}]},
                recommendations=[{'plans':'Strengthening'}])

def test_empty_saved_report_does_not_block_draft(monkeypatch):
    db = SimpleNamespace(users=SimpleNamespace(find_one=Mock(return_value={'_id':ObjectId(PID)})),
                         reports=SimpleNamespace(find_one=Mock(return_value={'_id':ObjectId(RID)})))
    monkeypatch.setitem(sys.modules, 'utils.vald_extractor', SimpleNamespace(extract_vald_first_session=lambda *_: {}))
    data, hashed = prepare_recommendation(db, PID, {'fields':draft()}, RID)
    assert data['source_data']['nprs'] == 0
    assert 'Climb stairs' in data['source_data']['patient_goals']
    assert 'Knee flexion' in data['source_data']['objective_notes']
    assert len(hashed) == 64
    db.reports.find_one.assert_called_once_with({'_id':ObjectId(RID),'patient':ObjectId(PID),'isFirstAssessment':True},{'_id':1})
    db.reports.find_one.return_value = None
    with pytest.raises(ValueError, match='not found'):
        prepare_recommendation(db, PID, {'fields':draft()}, RID)

@pytest.mark.parametrize('field,value', [('chief_complaint',' '),('nprs',None),('nprs',11),('short_term_goals',[]),('objective_assessment',{'tests':[{}]})])
def test_invalid_draft_rejected(field,value):
    fields=draft(); fields[field]=value
    with pytest.raises(ValueError): PartialReportPayload(**fields)

@pytest.mark.parametrize('field,value', [('nprs',2),('short_term_goals',[{'goal':'Run'}]),('objective_assessment',{'tests':[{'testName':'ROM','value':45}]}),('recommendations',[]),('report_id','000000000000000000000003')])
def test_hash_changes_with_context(field,value):
    original=draft(); changed=deepcopy(original); changed[field]=value
    assert compute_partial_hash(original) != compute_partial_hash(changed)

def test_mismatched_report_rejected():
    with pytest.raises(ValueError, match='draft changed'):
        prepare_recommendation(None,PID,{'fields':draft()},'different')
