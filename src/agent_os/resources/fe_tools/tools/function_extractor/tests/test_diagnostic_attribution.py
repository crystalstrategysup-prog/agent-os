from tools.function_extractor.diagnostic_attribution import attribute_unknown
def test_known_simulated_cause_preserves_unknown_receipt():
    trace={'trace_recording':{'complete':True,'dropped_events':0,'recorded_events':2,'selected_modules':['app.sample']},'status':'RETURNED','result_summary':{'state':'unknown'},'spans':[{'phase':'socket_fault','event':'READ_TIMEOUT','evidence':'SIMULATED'},{'event':'exception','file':'a.py','line':7,'exception':{'class':'TimeoutError'}}]}
    internal={'rules':[{'boundary_id':'AVL-H06'}]}
    provider={'url':'https://core.telegram.org/bots/api','facts':{'sendMessage':{'success_result':'Message'}}}
    out=attribute_unknown(trace,internal,provider)
    assert out['diagnostic_cause']=='READ_TIMEOUT' and out['receipt_state']=='unknown'
    assert out['telegram_delivery_confirmed'] is False and out['retry_safe_to_assume'] is False
    assert attribute_unknown(trace,{},provider)['status']=='CONTRACT_MISSING'
    assert attribute_unknown(trace,internal,{})['status']=='PROVIDER_CONTRACT_MISSING'
    assert attribute_unknown({'status':'RETURNED','result_summary':{'state':'unknown'},'spans':[]},internal,provider)['status']=='UNKNOWN_CAUSE'


def test_general_route_binding():
    from tools.function_extractor.diagnostic_attribution import attribute_unknown
    trace={'trace_recording':{'complete':True,'dropped_events':0,'recorded_events':2,'selected_modules':['app.sample']},'status':'RETURNED','result_summary':{'state':'unknown'},'spans':[{'phase':'socket_fault','event':'READ_TIMEOUT','evidence':'SIMULATED'}]}
    got=attribute_unknown(trace,{'rules':[{'boundary_id':'OTHER-R1'}]}, {'facts':{'sendMessage':{'success_result':'Message'}}}, boundary_id='OTHER-R1')
    assert got['status']=='ATTRIBUTED_SIMULATED' and got['internal_rule']=='OTHER-R1'

def test_standard_cli_auto_contract_resolution(tmp_path):
    import json
    from tools.function_extractor.cli import _automatic_diagnosis
    trace={'trace_recording':{'complete':True,'dropped_events':0,'recorded_events':2,'selected_modules':['app.sample']},'status':'RETURNED','result_summary':{'state':'unknown'},'spans':[{'phase':'socket_fault','event':'READ_TIMEOUT','evidence':'SIMULATED'}]}
    a=tmp_path/'internal.json'; b=tmp_path/'provider.json'
    a.write_text(json.dumps({'rules':[{'boundary_id':'SAMPLE-R1'}]}))
    b.write_text(json.dumps({'facts':{'sendMessage':{'success_result':'Message'}},'url':'https://core.telegram.org/bots/api'}))
    assert _automatic_diagnosis(trace,'SAMPLE-R1',a,b)['status']=='ATTRIBUTED_SIMULATED'
    assert _automatic_diagnosis(trace,'SAMPLE-R1')['status']=='CONTRACT_BINDING_REQUIRED'
    assert _automatic_diagnosis(trace,'SAMPLE-R1',a,None)['status']=='CONTRACT_BINDING_REQUIRED'


def test_maintained_default_works_without_ignored_historical_artifacts():
    from tools.function_extractor.cli import _automatic_diagnosis
    trace={'trace_recording':{'complete':True,'dropped_events':0,'recorded_events':2,'selected_modules':['app.sample']},'status':'RETURNED','result_summary':{'state':'unknown'},
           'spans':[{'phase':'socket_fault','event':'READ_TIMEOUT','evidence':'SIMULATED'}]}
    out=_automatic_diagnosis(trace,'AVL-H06')
    assert out['status']=='ATTRIBUTED_SIMULATED'
    assert out['receipt_state']=='unknown' and out['retry_safe_to_assume'] is False


def test_explicitly_incomplete_trace_cannot_attribute_cause():
    from tools.function_extractor.cli import _automatic_diagnosis
    trace={'status':'RETURNED','result_summary':{'state':'unknown'},
           'trace_recording':{'complete':False,'recorded_events':2,'dropped_events':0,'selected_modules':['app.sample']},
           'spans':[{'phase':'socket_fault','event':'READ_TIMEOUT','evidence':'SIMULATED'}]}
    out=_automatic_diagnosis(trace,'AVL-H06')
    assert out['status']=='UNKNOWN_CAUSE' and out['reason_code']=='TRACE_INCOMPLETE'


def test_other_method_snapshot_never_supplies_sendmessage_contract():
    trace={'trace_recording':{'complete':True,'dropped_events':0,'recorded_events':2,'selected_modules':['app.sample']},'status':'RETURNED','result_summary':{'state':'unknown'},
           'spans':[{'phase':'socket_fault','event':'READ_TIMEOUT','evidence':'SIMULATED'}]}
    got=attribute_unknown(trace,{'rules':[{'boundary_id':'AVL-H06'}]},
        {'method':'deleteMessage','facts':{'sendMessage':{'success_result':'Message'}}})
    assert got['status']=='PROVIDER_CONTRACT_MISSING'


def test_invalid_nested_contract_cannot_crash_cli_after_target_execution(tmp_path):
    import json
    from tools.function_extractor.cli import _automatic_diagnosis
    trace={'trace_recording':{'complete':True,'dropped_events':0,'recorded_events':2,'selected_modules':['app.sample']},'status':'RETURNED','result_summary':{'state':'unknown'},'spans':[]}
    a=tmp_path/'internal.json'; b=tmp_path/'provider.json'
    a.write_text(json.dumps({'rules':[{'boundary_id':'AVL-H06'}]}))
    for facts in (None, [], {'sendMessage':None}):
        b.write_text(json.dumps({'facts':facts}))
        assert _automatic_diagnosis(trace,'AVL-H06',a,b)['status']=='CONTRACT_INVALID'
