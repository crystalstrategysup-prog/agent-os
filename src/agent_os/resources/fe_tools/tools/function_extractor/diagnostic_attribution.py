"""Evidence-preserving error attribution: cause certainty != provider receipt certainty."""
def attribute_unknown(trace, contracts, provider, boundary_id="AVL-H06"):
    if trace.get('status') != 'RETURNED' or trace.get('result_summary',{}).get('state') != 'unknown':
        return {'status':'NOT_APPLICABLE'}
    if not any(x.get('boundary_id')==boundary_id for x in contracts.get('rules',[])):
        return {'status':'CONTRACT_MISSING', 'missing':boundary_id}
    facts=provider.get('facts',{})
    if provider.get('method') not in (None, 'sendMessage'):
        return {'status':'PROVIDER_CONTRACT_MISSING'}
    # Both retained legacy selected-lines and maintained method-specific
    # snapshots are readable. A different method must not acquire these facts.
    success = facts.get('sendMessage',{}).get('success_result')
    if provider.get('method') == 'sendMessage':
        success = facts.get('success_result')
    if success != 'Message':
        return {'status':'PROVIDER_CONTRACT_MISSING'}
    recording = trace.get('trace_recording')
    spans = trace.get('spans')
    # A simulated fault is not causal evidence unless its complete recording
    # is authenticated by the retained typed event-count metadata.
    if (type(recording) is not dict or recording.get('complete') is not True
            or type(recording.get('dropped_events')) is not int
            or recording['dropped_events'] != 0
            or type(recording.get('recorded_events')) is not int
            or type(spans) is not list or not spans
            or recording['recorded_events'] < len(spans)
            or type(recording.get('selected_modules')) is not list
            or any(type(module) is not str or not module for module in recording['selected_modules'])):
        return {'status':'UNKNOWN_CAUSE', 'receipt_state':'unknown', 'reason_code':'TRACE_INCOMPLETE'}
    fault=next((x for x in spans if type(x) is dict
                and x.get('phase') == 'socket_fault' and x.get('event') == 'READ_TIMEOUT'
                and x.get('evidence') == 'SIMULATED'),None)
    if fault is None:
        return {'status':'UNKNOWN_CAUSE', 'receipt_state':'unknown'}
    exceptions=[{'file':x.get('file'),'line':x.get('line'),'class':x.get('exception',{}).get('class')} for x in spans if x.get('event')=='exception' and isinstance(x.get('exception'),dict)]
    return {'status':'ATTRIBUTED_SIMULATED', 'diagnostic_cause':'READ_TIMEOUT',
            'cause_evidence':'SIMULATED_SOCKET_FAULT', 'receipt_state':'unknown',
            'telegram_delivery_confirmed':False, 'telegram_delivery_denied':False,
            'provider_success_requires':'Message', 'retry_safe_to_assume':False,
            'exceptions':exceptions[:30],
            'provider_contract_ref':provider.get('canonical_reference', provider.get('url')),
            'internal_rule':boundary_id}
