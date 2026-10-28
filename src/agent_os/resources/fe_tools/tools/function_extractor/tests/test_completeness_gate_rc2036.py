"""Owner-independent FE diagnostic gate tests, new for integrated rc2036."""
import copy
import pytest
from tools.function_extractor.diagnostic_attribution import attribute_unknown

CONTRACT={'rules':[{'boundary_id':'AVL-H06'}]}
PROVIDER={'method':'sendMessage','facts':{'success_result':'Message'}}
GOOD={'status':'RETURNED','result_summary':{'state':'unknown'},
      'trace_recording':{'complete':True,'recorded_events':1,'dropped_events':0,'selected_modules':[]},
      'spans':[{'phase':'socket_fault','event':'READ_TIMEOUT','evidence':'SIMULATED'}]}

@pytest.mark.parametrize('broken',[None,[], 'complete',True,0, {},
    {'complete':False,'recorded_events':1,'dropped_events':0,'selected_modules':[]},
    {'complete':1,'recorded_events':1,'dropped_events':0,'selected_modules':[]},
    {'complete':'true','recorded_events':1,'dropped_events':0,'selected_modules':[]},
    {'complete':True,'recorded_events':1,'dropped_events':1,'selected_modules':[]},
    {'complete':True,'recorded_events':1,'dropped_events':True,'selected_modules':[]},
    {'complete':True,'recorded_events':1,'dropped_events':-1,'selected_modules':[]},
    {'complete':True,'recorded_events':1,'dropped_events':'0','selected_modules':[]},
    {'complete':True,'recorded_events':False,'dropped_events':0,'selected_modules':[]},
    {'complete':True,'recorded_events':0,'dropped_events':0,'selected_modules':[]},
    {'complete':True,'recorded_events':1,'dropped_events':0,'selected_modules':None},
    {'complete':True,'recorded_events':1,'dropped_events':0,'selected_modules':'app'},
    {'complete':True,'recorded_events':1,'dropped_events':0,'selected_modules':['']},
    {'complete':True,'recorded_events':1,'dropped_events':0,'selected_modules':[True]},
])
def test_completeness_requires_typed_exact_proof(broken):
    case=copy.deepcopy(GOOD)
    case['trace_recording']=broken
    result=attribute_unknown(case,CONTRACT,PROVIDER)
    assert result['status']=='UNKNOWN_CAUSE' and result['receipt_state']=='unknown'
    assert result['reason_code']=='TRACE_INCOMPLETE'

@pytest.mark.parametrize('bad',[{'event':'READ_TIMEOUT','evidence':'SIMULATED'},
   {'phase':'request','event':'READ_TIMEOUT','evidence':'SIMULATED'},
   {'phase':'socket_fault','event':'CONNECT_TIMEOUT','evidence':'SIMULATED'},
   {'phase':'socket_fault','event':'READ_TIMEOUT','evidence':'REAL_CODE'},
   {'phase':'socket_fault','event':'READ_TIMEOUT','evidence':'HISTORICAL'}])
def test_wrong_fault_marker_is_not_attributed(bad):
    case=copy.deepcopy(GOOD);case['spans']=[bad]
    result=attribute_unknown(case,CONTRACT,PROVIDER)
    assert result['status']=='UNKNOWN_CAUSE'


def test_complete_synthetic_fault_still_distinguishes_provider_receipt():
    result=attribute_unknown(GOOD,CONTRACT,PROVIDER)
    assert result['status']=='ATTRIBUTED_SIMULATED'
    assert result['receipt_state']=='unknown'
    assert result['retry_safe_to_assume'] is False
    assert result['telegram_delivery_confirmed'] is False
    assert result['telegram_delivery_denied'] is False
