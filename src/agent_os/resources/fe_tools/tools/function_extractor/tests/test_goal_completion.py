"""Public CLI completion checks: synthetic files only, no providers/runtime writes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / '.agents/skills/function-extractor/scripts/fe-goal-check'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def ledger(tmp_path):
    task, skill = tmp_path/'task.txt', tmp_path/'skill.md'
    task.write_text('Original neutral request')
    skill.write_text('Generic operational procedure')
    proof = tmp_path/'proof.json'
    proof.write_text('{"passed":true,"delivery":"unknown"}')
    ref = {'path':proof.name,'sha256':sha(proof)}
    doc = {'schema':'function-extractor.goal-acceptance/v1','task_sha256':sha(task),
           'skill_sha256':sha(skill),'source_ref':'revision-one',
           'conditions':[{'id':'required-goal','required':True,'status':'PASS','evidence':[ref]}],
           'gaps':[], 'review':{'status':'REVIEWED','evidence':[ref]}}
    return tmp_path, task, skill, proof, ref, doc


def run(data):
    root, task, skill, proof, ref, doc = data
    path = root/'ledger.json'
    path.write_text(json.dumps(doc))
    before = {p.name:sha(p) for p in root.iterdir() if p.is_file()}
    cp = subprocess.run([sys.executable,'-B',str(CHECKER),'--ledger',str(path),
        '--evidence-root',str(root),'--task',str(task),'--skill',str(skill),
        '--source-ref','revision-one'],capture_output=True,text=True,timeout=5)
    after = {p.name:sha(p) for p in root.iterdir() if p.is_file()}
    assert before == after, 'checker must not write inputs'
    result = json.loads(cp.stdout)
    assert result['grants_authority'] is False
    return cp.returncode,result


def gap(ref, classification='ACTIONABLE_IN_SCOPE', required=True, resolution='OPEN'):
    return {'id':'coverage','classification':classification,'required':required,
            'resolution':resolution,'reason':'Evidence missing','next_action':'Inspect exact boundary',
            'evidence':[ref]}


def test_complete_is_only_eligible_not_semantic_authority(ledger):
    code,result = run(ledger)
    assert code == 0 and result['status'] == 'ELIGIBLE_FOR_FINAL_REVIEW'
    assert result['semantic_acceptance_proven'] is False


@pytest.mark.parametrize('status',['FAIL','UNKNOWN','BLOCKED'])
def test_required_condition_prevents_close(ledger,status):
    ledger[-1]['conditions'][0]['status'] = status
    assert run(ledger)[0] == 3


@pytest.mark.parametrize('classification',sorted(['ACTIONABLE_IN_SCOPE','REQUIRES_AUTHORITY','EXTERNAL_UNVERIFIABLE','OUT_OF_SCOPE']))
def test_required_gap_blocks_even_when_tests_green(ledger,classification):
    ledger[-1]['gaps'] = [gap(ledger[-2],classification)]
    assert run(ledger)[0] == 3


def test_optional_but_actionable_gap_still_blocks(ledger):
    ledger[-1]['gaps'] = [gap(ledger[-2],required=False)]
    assert run(ledger)[0] == 3


def test_known_handling_does_not_invent_external_delivery(ledger):
    ledger[-1]['gaps'] = [gap(ledger[-2],'EXTERNAL_UNVERIFIABLE',False)]
    assert run(ledger)[0] == 0
    assert json.loads(ledger[3].read_text())['delivery'] == 'unknown'


@pytest.mark.parametrize('field',['task_sha256','skill_sha256','source_ref'])
def test_wrong_pins_refuse(ledger,field):
    ledger[-1][field] = 'wrong'
    assert run(ledger)[0] == 2


def test_modified_evidence_refuses(ledger):
    ledger[3].write_text('changed successor')
    assert run(ledger)[0] == 2


def test_pass_without_receipt_refuses(ledger):
    ledger[-1]['conditions'][0]['evidence'] = []
    assert run(ledger)[0] == 2


def test_missing_required_conditions_refuses(ledger):
    ledger[-1]['conditions'][0]['required'] = False
    assert run(ledger)[0] == 2


def test_duplicate_condition_refuses(ledger):
    ledger[-1]['conditions'] *= 2
    assert run(ledger)[0] == 2


def test_review_pending_is_not_complete(ledger):
    ledger[-1]['review']['status'] = 'PENDING'
    assert run(ledger)[0] == 3


@pytest.mark.parametrize('path',['../proof.json','/tmp/proof.json','./proof.json'])
def test_escaping_evidence_refuses(ledger,path):
    ledger[-2]['path'] = path
    assert run(ledger)[0] == 2


def test_symlink_evidence_refuses(ledger):
    (ledger[0]/'alias').symlink_to(ledger[3])
    ledger[-2]['path'] = 'alias'
    assert run(ledger)[0] == 2


def test_resolved_gap_requires_proof(ledger):
    g = gap(ledger[-2],resolution='RESOLVED');g['evidence'] = []
    ledger[-1]['gaps'] = [g]
    assert run(ledger)[0] == 2


def test_resolution_with_evidence_is_checkable(ledger):
    ledger[-1]['gaps'] = [gap(ledger[-2],resolution='RESOLVED')]
    assert run(ledger)[0] == 0


def test_missing_reason_refuses(ledger):
    g = gap(ledger[-2]);g['reason'] = ''
    ledger[-1]['gaps'] = [g]
    assert run(ledger)[0] == 2
