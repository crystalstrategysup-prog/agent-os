"""New pure contract-witness tests; no product import or sandbox execution."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tools.function_extractor import contract_engine as ce
from tools.function_extractor import wire_contract as wc

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = 'e' * 64
RUNNER = 'f' * 64


def inputs():
    selected = json.loads((ROOT / 'tools/function_extractor/contracts/telegram_sendmessage.rules.json').read_text())
    source = {'source_id':'independent-rules','kind':'rules','path':'public.rules.json','sha256':'c'*64,
              'provenance':'APPROVED_INTERNAL','authority_ref':'synthetic-test-approval',
              'metadata':{'retrieved_at':None,'version':None,'primary_ref':None,'primary_sha256':None,
                          'official_schema':False,'machine_adapter':True}}
    pins = [{'path':'sample.py','sha256':'a'*64,'bytes':120}]
    manifest = {'schema':'route-probe.bundle/v1','entry':'sample:run','files':pins,'graph_sha256':'b'*64}
    rules = [{**rule,'source_id':source['source_id'],'provenance':source['provenance'],'conflicts':[]} for rule in selected['rules']]
    contract = {'schema':'contract-map/v1','version':1,'status':'RESOLVED',
                'route':{'route_id':'sample-route','entry':manifest['entry'],'graph_sha256':manifest['graph_sha256'],
                         'source_pins':[{'path':p['path'],'sha256':p['sha256']} for p in pins]},
                'revision':'synthetic-test','sources':[source],'boundaries':selected['boundaries'],'rules':rules,'unresolved':[]}
    contract['content_digest'] = ce.content_digest(contract)
    bindings = [dict(binding_id='request',boundary_id='telegram.sendMessage.plain',direction='input',phase='REQUEST',applicability='PLAIN_TEXT_ONLY',
                     file='sample.py',sha256='a'*64,symbol='run',line=1),
                dict(binding_id='response',boundary_id='telegram.response.envelope',direction='output',phase='RESPONSE',
                     file='sample.py',sha256='a'*64,symbol='run',line=2)]
    return contract, manifest, bindings


def compile_plan(contract=None, manifest=None, bindings=None):
    original, original_manifest, original_bindings = inputs()
    contract = contract if contract is not None else original
    return wc.compile_contract_observation_plan(contract, manifest if manifest is not None else original_manifest,
        rule_ids=[r['rule_id'] for r in original['rules']], bindings=bindings if bindings is not None else original_bindings)


def observe(plan, name='request', value=None, invocation=1):
    binding = next(b for b in plan['bindings'] if b['binding_id'] == name)
    if value is None:
        value = {'chat_id':123,'text':'private test sentinel'} if name == 'request' else {'ok':True,'result':{'message_id':987,'chat':{}}}
    return wc.evaluate_contract_observation(plan,binding_id=name,value=value,phase=binding['phase'],
        anchor={k:binding[k] for k in ('file','sha256','symbol','line')},invocation_id=invocation)


def packet(plan, rows, **changes):
    value = {'schema':wc.OBSERVATIONS_SCHEMA,'version':1,'plan':plan,'fixture_sha256':FIXTURE,
             'runner_sha256':RUNNER,'observations':rows,'complete':True,'dropped_observations':0}
    value.update(changes)
    value['content_digest'] = wc.observation_content_digest(value)
    return value


def admit(value, plan, **kwargs):
    return wc.validate_contract_observations(value,plan,manifest=inputs()[1],fixture_sha256=FIXTURE,runner_sha256=RUNNER,**kwargs)


class WireContractTests(unittest.TestCase):
    def test_actual_selected_schema_request_response_privacy(self):
        plan = compile_plan()
        self.assertEqual(plan['status'],'COMPILED')
        request = observe(plan,value={'chat_id':123456789,'text':'RESIDENT_SECRET_SENTINEL'})
        response = observe(plan,'response',{'ok':True,'result':{'message_id':987,'chat':{},'text':'PROVIDER_PRIVATE_SENTINEL'}})
        envelope = packet(plan,[request,response])
        self.assertEqual(admit(envelope,plan)['status'],'VALID')
        self.assertEqual(admit(envelope,plan)['admission_scope'],'VERIFIED_MANIFEST_BINDING')
        serialized = json.dumps(envelope)
        for forbidden in ('RESIDENT_SECRET_SENTINEL','PROVIDER_PRIVATE_SENTINEL','123456789','987'):
            self.assertNotIn(forbidden,serialized)
        # A public schema property is permitted in the pinned plan. Neither
        # native values nor result objects may enter the observation channel.
        self.assertNotIn('message_id', json.dumps(envelope['observations']))
        self.assertEqual(request['checks'][0]['test_verdict'],'PASS')
        self.assertEqual(response['checks'][0]['test_verdict'],'PASS')
        self.assertEqual(response['evidence_scope'],wc.EVIDENCE_SCOPE)

    def test_fixture_declaration_cannot_replace_actual_value(self):
        plan = compile_plan()
        self.assertEqual(observe(plan,value={'chat_id':123})['checks'][0]['test_verdict'],'FAIL')
        self.assertEqual(observe(plan,'response',{'ok':'true'})['checks'][0]['test_verdict'],'FAIL')
        self.assertEqual(observe(plan,value={'chat_id':123,'text':''})['checks'][0]['reason_code'],'SCHEMA_INVALID')
        self.assertNotIn('expected',plan)

    def test_map_tamper_and_non_schema_rule_refuse(self):
        contract, manifest, bindings = inputs()
        bad = copy.deepcopy(contract);bad['rules'][0]['constraint']['required']=[]
        self.assertEqual(compile_plan(bad)['status'],'REFUSED')
        bad['content_digest']=ce.content_digest(bad);bad['rules'][0]['kind']='semantic';bad['content_digest']=ce.content_digest(bad)
        self.assertEqual(compile_plan(bad)['status'],'REFUSED')
        for change in ({'entry':'foreign:run'},{'graph_sha256':'1'*64},{'files':[{'path':'sample.py','sha256':'2'*64,'bytes':120}]}):
            with self.subTest(change=change):
                self.assertEqual(compile_plan(manifest={**manifest,**change})['status'],'REFUSED')

    def test_binding_anchor_source_phase_and_uniqueness(self):
        _,_,bindings=inputs()
        for key,value in [('sha256','1'*64),('file','other.py'),('line',True),('phase','RESPONSE'),('symbol','run;payload')]:
            bad=copy.deepcopy(bindings);bad[0][key]=value
            self.assertEqual(compile_plan(bindings=bad)['status'],'REFUSED',key)
        self.assertEqual(compile_plan(bindings=bindings+[bindings[0]])['status'],'REFUSED')
        plan=compile_plan();anchor={'file':'sample.py','sha256':'a'*64,'symbol':'run','line':True}
        result=wc.evaluate_contract_observation(plan,binding_id='request',value={},phase='REQUEST',anchor=anchor,invocation_id=1)
        self.assertEqual(result['status'],'REFUSED')

    def test_unsupported_bounded_and_hostile_values_unknown(self):
        contract,_,_=inputs();contract['rules'][0]['constraint']['pattern']='private-pattern'
        contract['content_digest']=ce.content_digest(contract);plan=compile_plan(contract)
        self.assertEqual(observe(plan)['checks'][0]['reason_code'],'SCHEMA_UNSUPPORTED_OR_BOUNDED')
        plan=compile_plan()
        class Hostile:
            def __repr__(self):raise AssertionError('must not repr')
            def __str__(self):raise AssertionError('must not str')
        cycle=[];cycle.append(cycle)
        for value in (Hostile(), {'chat_id':float('nan'),'text':'x'}, {'chat_id':1,'text':'x'*524289},cycle):
            result=observe(plan,value=value)
            self.assertEqual(result['status'],'EVALUATED')
            self.assertEqual(result['checks'][0]['test_verdict'],'UNKNOWN')
            self.assertEqual(result['checks'][0]['reason_code'],'SCHEMA_UNSUPPORTED_OR_BOUNDED')

    def test_evaluator_failure_is_closed_unknown(self):
        plan=compile_plan()
        with patch.object(wc.ce,'validate_schema',side_effect=RuntimeError('TOKEN_PRIVATE_ERROR')):
            record=observe(plan)
        self.assertEqual(record['checks'][0]['reason_code'],'EVALUATOR_FAILURE')
        self.assertNotIn('TOKEN_PRIVATE_ERROR',json.dumps(record))

    def test_missing_observation_and_missing_response_stay_unproved(self):
        plan=compile_plan()
        self.assertEqual(admit(None,plan)['status'],'UNKNOWN')
        envelope=packet(plan,[observe(plan)])
        self.assertEqual(admit(envelope,plan)['status'],'VALID')
        self.assertFalse(any(r['direction']=='output' for r in envelope['observations']))
        self.assertEqual(admit(packet(plan,[]),plan)['status'],'VALID')

    def test_record_foreign_pins_and_anchor_refuse(self):
        plan=compile_plan()
        for key,value in [('source_id','foreign'),('source_sha256','1'*64),('schema_sha256','2'*64),('rule_id','foreign'),('test_verdict','FORGED')]:
            record=observe(plan);record['checks'][0][key]=value
            self.assertEqual(admit(packet(plan,[record]),plan)['status'],'REFUSED',key)
        for key,value in [('phase','RESPONSE'),('direction','output'),('plan_sha256','3'*64),('evidence_scope','PROVIDER_PROOF')]:
            record=observe(plan);record[key]=value
            self.assertEqual(admit(packet(plan,[record]),plan)['status'],'REFUSED',key)
        record=observe(plan);record['anchor']['line']=2
        self.assertEqual(admit(packet(plan,[record]),plan)['status'],'REFUSED')

    def test_fixture_runner_and_packet_tamper_refuse(self):
        plan=compile_plan();record=observe(plan)
        for key,value in [('fixture_sha256','1'*64),('runner_sha256','2'*64),('version',True),('complete','yes')]:
            self.assertEqual(admit(packet(plan,[record],**{key:value}),plan)['status'],'REFUSED',key)
        envelope=packet(plan,[record]);envelope['observations']=[]
        self.assertEqual(admit(envelope,plan)['status'],'REFUSED')
        envelope=packet(plan,[record]);envelope['payload']={'token':'PRIVATE'}
        self.assertEqual(admit(envelope,plan)['status'],'REFUSED')

    def test_duplicates_pair_order_and_drop_consistency(self):
        plan=compile_plan();request=observe(plan);response=observe(plan,'response')
        for rows in ([request,request],[response,request],[request,observe(plan,'response',invocation=2)]):
            self.assertEqual(admit(packet(plan,rows),plan)['status'],'REFUSED')
        self.assertEqual(admit(packet(plan,[request],dropped_observations=1),plan)['status'],'REFUSED')
        self.assertEqual(admit(packet(plan,[request],complete=False,dropped_observations=1),plan)['status'],'VALID')

    def test_structural_scope_explicit_and_manifest_rebind_refuses(self):
        plan=compile_plan()
        self.assertEqual(wc.validate_contract_observation_plan(plan)['status'],'REFUSED')
        self.assertEqual(wc.validate_contract_observation_plan(plan,structural_only=True)['admission_scope'],'STRUCTURAL_ONLY')
        envelope=packet(plan,[observe(plan)])
        result=wc.validate_contract_observations(envelope,plan,fixture_sha256=FIXTURE,runner_sha256=RUNNER,structural_only=True)
        self.assertEqual(result['status'],'VALID');self.assertEqual(result['admission_scope'],'STRUCTURAL_ONLY')
        bad=copy.deepcopy(plan);bad['source_pins'][0]['sha256']='1'*64;bad['content_digest']=wc.observation_content_digest(bad)
        self.assertEqual(wc.validate_contract_observation_plan(bad,inputs()[1])['status'],'REFUSED')

    def test_plan_rule_binding_and_observation_caps(self):
        _,_,bindings=inputs()
        too_many=[{**bindings[0],'binding_id':'b'+str(i)} for i in range(33)]
        self.assertEqual(compile_plan(bindings=too_many)['status'],'REFUSED')
        contract,_,_=inputs();contract['rules'][0]['constraint']['enum']=['x'*65536]
        contract['content_digest']=ce.content_digest(contract)
        self.assertEqual(compile_plan(contract)['status'],'REFUSED')
        plan=compile_plan();rows=[observe(plan,invocation=i) for i in range(1,129)]
        self.assertEqual(admit(packet(plan,rows),plan)['status'],'VALID')
        self.assertEqual(admit(packet(plan,rows+[rows[0]]),plan)['status'],'REFUSED')

    def test_same_priority_conflicts_preserved_unknown(self):
        contract,_,_=inputs();original=contract['rules'][0]
        peer=copy.deepcopy(original);peer['rule_id']='competing';peer['constraint']['required']=[]
        peer['conflicts']=[original['rule_id']];original['conflicts']=[peer['rule_id']]
        contract['rules'].append(peer);contract['content_digest']=ce.content_digest(contract)
        plan=compile_plan(contract)
        self.assertEqual(plan['status'],'COMPILED')
        record=observe(plan)
        self.assertEqual({x['reason_code'] for x in record['checks']},{'CONTRACT_CONFLICT'})
        forged=copy.deepcopy(record);forged['checks'][0].update(test_verdict='PASS',reason_code='SCHEMA_MATCH')
        self.assertEqual(admit(packet(plan,[forged]),plan)['status'],'REFUSED')

    def test_maintained_capture_bindings_match_exact_public_source(self):
        wrapper=json.loads((ROOT/'tools/function_extractor/contracts/telegram_sendmessage.observation-bindings.json').read_text())
        self.assertEqual(set(wrapper),{'schema','version','bindings'})
        self.assertEqual(wrapper['schema'],'function-extractor.contract-capture-bindings/v1')
        self.assertEqual(wrapper['version'],1)
        self.assertEqual(len(wrapper['bindings']),2)
        relative='app/ingest/telegram_basic_native_transport.py'
        raw=(ROOT/'backend'/relative).read_bytes()
        tree=ast.parse(raw)
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='BasicNativeTransport')
        function=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_request_once')
        calls={}
        for node in ast.walk(function):
            if isinstance(node,ast.Call):calls.setdefault(node.lineno,set()).add(ast.unparse(node.func))
        for row,callee in zip(wrapper['bindings'],['session.post','json.loads']):
            self.assertEqual(row['file'],relative)
            self.assertEqual(row['sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(row['symbol'],'BasicNativeTransport._request_once')
            self.assertIn(callee,calls[row['line']])
        # Several json.loads calls exist here. The response must be the decoded
        # peer body, never the sendMediaGroup request-body decoder.
        decoded = [n for n in ast.walk(function) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'decoded' for t in n.targets)
                   and isinstance(n.value, ast.Call) and ast.unparse(n.value.func) == 'json.loads']
        self.assertEqual(len(decoded), 1)
        self.assertEqual(wrapper['bindings'][1]['line'], decoded[0].value.lineno)
        # Independent review: assignment name alone does not establish response
        # semantics. Pin the decoder argument to accumulated response bytes.
        self.assertEqual(ast.unparse(decoded[0].value.args[0]),
                         "b''.join(chunks).decode('utf-8')")
        readers = [n for n in ast.walk(function) if isinstance(n, ast.For)
                   and isinstance(n.iter, ast.Call)
                   and ast.unparse(n.iter.func) == 'response.iter_content']
        self.assertEqual(len(readers), 1)
        self.assertTrue(any(isinstance(n, ast.Call) and ast.unparse(n.func) == 'chunks.append'
                            for n in ast.walk(readers[0])))
        html = json.loads((ROOT/'tools/function_extractor/contracts/telegram_sendmessage_html.observation-bindings.json').read_text())
        for left, right in zip(wrapper['bindings'], html['bindings']):
            self.assertEqual({k:left[k] for k in ('file','sha256','symbol','line')},
                             {k:right[k] for k in ('file','sha256','symbol','line')})
        self.assertEqual({r['direction'] for r in wrapper['bindings']},{'input','output'})

    def test_rehashed_plan_rejects_unselected_rule_insertion(self):
        plan=compile_plan()
        extra=copy.deepcopy(next(r for r in plan['rules'] if r['kind']=='input_schema'))
        extra['rule_id']='unrelated-unselected'
        plan['rules']=sorted(plan['rules']+[extra],key=lambda r:r['rule_id'])
        plan['content_digest']=wc.observation_content_digest(plan)
        self.assertEqual(wc.validate_contract_observation_plan(plan,inputs()[1])['status'],'REFUSED')

    def test_partial_response_without_request_is_not_complete_proof(self):
        plan=compile_plan();response=observe(plan,'response')
        incomplete=packet(plan,[response],complete=False,dropped_observations=1)
        result=admit(incomplete,plan)
        self.assertEqual(result['status'],'VALID')
        self.assertEqual(result['admission_scope'],'VERIFIED_MANIFEST_BINDING')
        self.assertFalse(incomplete['complete'])
        self.assertEqual(admit(packet(plan,[response]),plan)['status'],'REFUSED')
        # Metadata admission contains no aggregate PASS/cache claim. The parent
        # evidence reader must keep every incomplete packet UNKNOWN/ineligible.
        self.assertNotIn('test_verdict',result)
        self.assertNotIn('cache_eligible',result)

    def test_public_metadata_rejects_foreign_object_callbacks(self):
        calls=[]
        class Trap:
            def __hash__(self):
                calls.append('hash');raise AssertionError('foreign hash called')
            def __eq__(self,other):
                calls.append('eq');raise AssertionError('foreign equality called')
        contract,manifest,bindings=inputs()
        result=wc.compile_contract_observation_plan(contract,manifest,rule_ids=[Trap()],bindings=bindings)
        self.assertEqual(result['status'],'REFUSED')
        plan=compile_plan();binding=plan['bindings'][0]
        result=wc.evaluate_contract_observation(plan,binding_id=binding['binding_id'],value={},phase=Trap(),
            anchor={k:binding[k] for k in ('file','sha256','symbol','line')},invocation_id=1)
        self.assertEqual(result['status'],'REFUSED')
        self.assertEqual(calls,[])

    def test_partial_message_schema_pass_is_not_delivery_or_full_message(self):
        plan=compile_plan();record=observe(plan,'response',{'ok':True,'result':{'message_id':7,'chat':{}}})
        self.assertEqual(record['checks'][0]['test_verdict'],'PASS')
        self.assertNotIn('delivery',record)
        self.assertIn('NOT_PROVIDER_PROOF',record['evidence_scope'])


if __name__=='__main__':
    unittest.main()
