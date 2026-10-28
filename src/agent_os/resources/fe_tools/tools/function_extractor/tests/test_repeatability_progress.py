"""New observed progress-byte normalization regression, not a route re-run."""
from copy import deepcopy
from tools.function_extractor.api import verify_repeatability


def test_only_top_level_progress_size_is_volatile_real_outcomes_remain_compared():
    a={'schema':'route-probe.trace/v1','status':'RETURNED','source_entry':'worker:run',
       'result_summary':{'type':'DeliveryReceipt','state':'unknown'},'stderr_bytes_suppressed':976,
       'spans':[{'phase':'post','event':'written','count':1,'evidence':'SIMULATED'}]}
    b=deepcopy(a);b['stderr_bytes_suppressed']=979
    assert verify_repeatability([a,b])['status']=='REPEATABLE'
    c=deepcopy(b);c['result_summary']['state']='sent'
    assert verify_repeatability([a,c])['status']=='MISMATCH'
    c=deepcopy(b);c['spans'][0]['count']=2
    assert verify_repeatability([a,c])['status']=='MISMATCH'
