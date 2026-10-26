import pytest
from agent_os.investigation import input_key, repeat_decision, cache_eligible, stage, CLASSES
from agent_os.safeio import GateError


def key(**changes):
    values=dict(artifacts={'program':'a'*64},environment={'python':'3.14','dependencies':'pinned'},contract_sha='b'*64,fixture_sha='c'*64,hypothesis='compiler bug',tool='compiler');values.update(changes);return input_key(**values)


def test_changed_source_environment_contract_fixture_hypothesis_invalidates():
    first=key()
    for delta in [dict(artifacts={'program':'d'*64}),dict(environment={'python':'3.13'}),dict(contract_sha='d'*64),dict(fixture_sha='d'*64),dict(hypothesis='parser bug'),dict(tool='parser')]:assert key(**delta)!=first
    with pytest.raises(GateError):key(artifacts={'program':'main'})


@pytest.mark.parametrize('scenario',['compiler-build','csv-offline-analysis'])
def test_general_repeat_policy_and_required_method_change(scenario):
    k=key(tool=scenario);history=[]
    assert repeat_decision(history,k)['status']=='RUN'
    history.append({'input_key':k,'outcome':'FAIL','new_evidence':[]})
    assert repeat_decision(history,k)['status']=='REUSE'
    assert repeat_decision(history,k,reason='verify intermittent race')['status']=='RUN'
    history.append({'input_key':k,'outcome':'FAIL','new_evidence':[]})
    assert repeat_decision(history,k,reason='again')['status']=='REVISE_METHOD'
    assert repeat_decision(history,key(hypothesis='new explanation'))['status']=='RUN'


def test_no_cache_for_fresh_integrations_or_effects():
    k=key()
    for kind in ['integration','side-effect','external-send']:
        assert not cache_eligible(check_kind=kind,immutable=True,key=k,saved_key=k,outcome='PASS')
    assert cache_eligible(check_kind='static',immutable=True,key=k,saved_key=k,outcome='PASS')
    assert not cache_eligible(check_kind='static',immutable=True,key=k,saved_key=key(hypothesis='different'),outcome='PASS')


def test_stage_timing_failure_and_honest_unknown():
    rows=[]
    with stage(tool='compiler',input_key=key(),versions={'source':'a'*64},emit=rows.append) as row:
        row['outcome']='PASS';row['new_evidence']=['regression result']
    with pytest.raises(RuntimeError):
        with stage(tool='analysis',input_key=key(tool='analysis'),versions={'source':'a'*64},emit=rows.append):raise RuntimeError()
    assert [r['outcome'] for r in rows]==['PASS','FAIL']
    for r in rows:
        assert r['duration_ns']>=0 and r['start_utc']<=r['end_utc']
        assert r['end_monotonic_ns']-r['start_monotonic_ns']==r['duration_ns']
    assert 'HISTORICAL_SUPPORTED' in CLASSES and 'CURRENT_PROVEN' in CLASSES
