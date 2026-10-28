"""Reproduce selected Telegram UNKNOWN boundaries via the maintained FE CLI.

Run with an already installed Python containing Requests/PySocks. Never builds,
downloads, leases containers, loads production settings or contacts a provider.
The existing subprocess runner enforces audit/seccomp in every replay child.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out.absolute()
    if (out.exists() or not out.parent.is_dir() or not out.is_relative_to(root)
            or out.resolve() != out):
        parser.error('new output under this isolated repository required')
    out.mkdir(mode=0o700)
    env = {'PATH': os.defpath, 'LANG': 'C.UTF-8', 'TZ': 'UTC', 'PYTHONDONTWRITEBYTECODE': '1'}

    def write(name, value):
        path = out / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        return path

    def read(path):
        return json.loads(Path(path).read_text())

    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def run(name, *argv, exits=(0,)):
        command = [sys.executable, '-B', '-m', 'tools.function_extractor', *map(str, argv)]
        start, utc = time.monotonic(), datetime.now(timezone.utc).isoformat()
        result = subprocess.run(command, cwd=root, env=env, capture_output=True, timeout=120)
        (out / (name + '.stdout')).write_bytes(result.stdout)
        (out / (name + '.stderr')).write_bytes(result.stderr)
        with (out / 'steps.jsonl').open('a') as stream:
            stream.write(json.dumps({'step':name,'argv':command,'exit':result.returncode,
                'utc_start':utc,'utc_end':datetime.now(timezone.utc).isoformat(),
                'monotonic_seconds':time.monotonic()-start}) + '\n')
        if result.returncode not in exits:
            raise RuntimeError('CLI step failed: ' + name + '; inspect saved output')
        return json.loads(result.stdout)

    entry = 'app.ingest.telegram_private_transport:deliver'
    frozen = out / 'frozen'
    run('discover', 'discover', '--source-root', root/'backend', '--entry', entry,
        '--out', out/'discovery.json')
    extracted = run('extract', 'extract', '--source-root', root/'backend', '--entry', entry,
        '--adapter', 'tools.route_probe_avl:prepare', '--include-entry', 'tools.route_probe_avl:observe_outcome',
        '--include-module', 'app.ingest.telegram_reply_presentation',
        '--include-module', 'app.ingest.telegram_native_fault_family',
        '--opaque-module', 'app.core.config', '--opaque-module', 'app.ingest.telegram_basic_subscription',
        '--opaque-module', 'app.ingest.telegram_basic_media_policy',
        '--capture-mode', 'PARTIAL_STATIC', '--out', frozen)
    bundle = frozen/'route_bundle.json'
    assert extracted['status'] == 'FROZEN_PARTIAL_STATIC'
    assert run('verify','verify','--bundle',bundle)['status'] == 'PINS_VERIFIED'
    manifest = read(frozen/'manifest.json')
    contracts = root/'tools/function_extractor/contracts'
    rules = contracts/'telegram_sendmessage_html.rules.json'
    primary = read(contracts/'telegram_sendmessage_html.primary.json')
    provenance = read(contracts/'telegram_sendmessage_html.provenance.json')
    assert sha(rules) == provenance['adapter_sha256']
    assert sha(contracts/'telegram_sendmessage_html.primary.json') == provenance['primary_sha256']
    inputs = write('inputs.json', {'route':{'route_id':'telegram-offline-review','entry':entry,
        'graph_sha256':manifest['graph_sha256'],
        'source_pins':[{k:p[k] for k in ('path','sha256')} for p in manifest['files']]},
        'sources':[{'source_id':'selected-telegram-html','kind':'rules',
            'path':rules.relative_to(root).as_posix(),'sha256':sha(rules),
            'metadata':{'retrieved_at':primary['retrieved_at'],'version':'HTML_BOLD_TEXT_V1',
                'primary_ref':provenance['primary_ref'],'primary_sha256':provenance['primary_sha256'],
                'official_schema':False,'machine_adapter':True}}],
        'revision':{'id':'selected-offline-source-review','source_root':str(root),'authority_bindings':[
            {'source_id':'selected-telegram-html','sha256':sha(rules),'provenance':'OFFICIAL',
             'authority_ref':'Selected facts from pinned Telegram primary; local reviewed machine adapter, not official schema or runtime authority'}]}})
    cmap = out/'map.json'
    assert run('resolve','contracts','resolve','--inputs',inputs,'--out',cmap)['status'] == 'RESOLVED'
    fixtures, bindings = {}, []
    for case, state in [('success','sent'),('read_timeout','unknown'),('bad_shape','unknown')]:
        # Fixtures supply inputs/faults. Independent expected contracts compare
        # the DeliveryReceipt summary, not equality to an unrelated plain dict.
        fixture = {'case':case,'route':'platform_group','stack_variant':'requests_http',
            'trace_modules':['app.ingest.telegram_basic_native_transport',
                'app.ingest.telegram_private_transport','app.ingest.bot_bridge_core','tools.route_probe_avl']}
        fixtures[case] = write(case+'.fixture.json', fixture)
        expected = {'schema':'function-extractor.contract/v1','version':1,'expected_status':'RETURNED',
            'result_summary':{'type':'DeliveryReceipt','state':state},'guards':{'audit':True,'seccomp':True},
            'phase_events':[{'phase':'real_http_request','event':'written'},
                            {'phase':'real_http_receipt','event':state}]}
        row = {'binding_id':case,'variant':case,'rule_ids':[r['rule_id'] for r in read(cmap)['rules']],
            'fixture':fixture,'expected':expected,'expected_delivery_state':state,
            'evidence_scope':'REAL_CODE_REQUESTS_STACK_SIMULATED_SOCKET_PROVIDER_AND_AUTHORITY_NOT_LIVE'}
        if case == 'bad_shape':
            row['observation_expectations'] = {'telegram.response.ok':'FAIL'}
        bindings.append(row)
        write(case+'.expected.json', expected)
    profile = write('profile.json', {'schema':'function-extractor.scenario-profile/v1','version':1,
        'profile_id':'telegram-selected-offline','route_id':'telegram-offline-review','entry':entry,'bindings':bindings})
    cases = out/'scenarios.json'
    run('generate','scenarios','generate','--contracts',cmap,'--profile',profile,'--seed','534','--out',cases)
    observation = contracts/'telegram_sendmessage_html.observation-bindings.json'
    matrix = out/'matrix'
    run('matrix','matrix','--bundle',bundle,'--contracts',cmap,'--scenarios',cases,
        '--observation-bindings',observation,'--mode','offline','--runner','subprocess',
        '--budget-seconds','180','--registry',out/'generated','--out',matrix, exits=(3,))
    # UNKNOWN is expected for an absent timeout response. It must stay visible
    # through validation/report, with no positive cache admission.
    run('validate','validate','--run',matrix/'run.json','--contracts',cmap,
        '--scenarios',cases,'--out',out/'revalidated.json')
    run('report','report','--run',matrix/'validation.json')
    replay = out/'h06-replay'
    result = run('replay','replay','--bundle',bundle,'--fixture',fixtures['read_timeout'],
        '--scenario','AVL-H06','--contracts',cmap,'--observation-bindings',observation,
        '--mode','offline','--runner','subprocess','--out',replay)
    assert result['diagnosis']['status'] == 'ATTRIBUTED_SIMULATED'
    assert result['diagnosis']['receipt_state'] == 'unknown'
    assert result['diagnosis']['retry_safe_to_assume'] is False
    compared = run('compare','compare','--actual',replay/'trace.json',
        '--expected',out/'read_timeout.expected.json')
    assert compared['status'] == 'MATCH', compared
    validation = read(matrix/'validation.json')
    rows = {c['case_id']:c for c in validation['cases']}
    assert rows['success']['test_verdict'] == 'PASS', rows['success']
    assert rows['bad_shape']['test_verdict'] == 'PASS', rows['bad_shape']
    assert rows['read_timeout']['test_verdict'] == 'UNKNOWN', rows['read_timeout']
    assert rows['read_timeout']['cache_eligible'] is False
    for item in read(matrix/'run.json')['cases']:
        trace = item['trace']
        posts = [s for s in trace['spans'] if s.get('phase') == 'real_http_request'
                 and s.get('event') == 'written']
        assert len(posts) == 1 and posts[0]['count'] == 1
        assert trace['trace_recording']['complete'] is True
        observations = trace['contract_observations']['observations']
        assert trace['contract_observations']['complete'] is True
        directions = {o['direction'] for o in observations}
        assert directions == ({'input'} if item['case_id'] == 'read_timeout' else {'input','output'})
    summary = {'status':'SELECTED_OFFLINE_GOAL_VERIFIED','matrix_status':'UNKNOWN',
        'reason':'read_timeout response unobserved; known simulated cause; delivery unknown',
        'case_verdicts':{k:v['test_verdict'] for k,v in rows.items()},
        'bundle_sha256':sha(bundle),'source_proof':'FILE_HASH_ONLY overlay; not clean commit or loaded runtime',
        'static_scope':'PARTIAL_STATIC','runner':'subprocess; not container dependency closure',
        'production_acceptance':False,'live_provider_observed':False,'external_messages':0}
    write('RESULT.json', summary)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
