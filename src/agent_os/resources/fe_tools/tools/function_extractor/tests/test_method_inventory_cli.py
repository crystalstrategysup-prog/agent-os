"""New inventory CLI boundaries only; no target execution/container/network/DB."""
import hashlib
import json
from pathlib import Path

import pytest

from tools.function_extractor import cli
from tools.function_extractor.contract_engine import content_digest
from tools.function_extractor.runner.bundle import pack_bundle
from tools.function_extractor.runner.loader import load_engine


def _write(path, value):
    path.write_text(json.dumps(value) + '\n')
    return path


@pytest.fixture
def selected(tmp_path):
    source = tmp_path / 'source'
    (source / 'app').mkdir(parents=True)
    (source / 'app/__init__.py').write_text('')
    marker = tmp_path / 'SOURCE_MUST_NOT_EXECUTE'
    (source / 'app/bridge.py').write_text(
        'from pathlib import Path\n'
        f'Path({str(marker)!r}).write_text("unexpected execution")\n'
        'CAPABILITIES = {"getWebhookInfo"}\n'
        'def reply(client, selected_method):\n'
        '    client.request("SYNTHETIC_PRIVATE_CANARY", "sendMessage", {})\n'
        '    client.request("SYNTHETIC_PRIVATE_CANARY", method=selected_method)\n')
    frozen = tmp_path / 'frozen'
    load_engine('route_probe').freeze_bundle(source, 'app.bridge:reply', frozen)
    bundle = frozen / 'route_bundle.json'
    pack_bundle(frozen, bundle)
    policy = {'schema': 'function-extractor.method-policy/v1', 'version': 1,
        'include_prefixes': ['app/'],
        'dispatches': [{'id': 'fixture-dispatch', 'provider': 'telegram', 'protocol': 'BotAPI',
            'paths': ['app/bridge.py'], 'callee': 'client.request', 'method_arg': 1,
            'method_kw': 'method', 'fixed_method': None}],
        'declarations': [{'id': 'fixture-capability', 'provider': 'telegram', 'protocol': 'BotAPI',
            'paths': ['app/bridge.py'], 'symbol': 'CAPABILITIES'}]}
    catalog = {'schema': 'function-extractor.method-catalog/v1', 'version': 1,
               'sources': [], 'methods': []}
    return {'bundle': bundle, 'policy': _write(tmp_path / 'policy.json', policy),
            'catalog': _write(tmp_path / 'catalog.json', catalog), 'marker': marker}


def _run(selected, out, extra=()):
    return cli.main(['methods', 'inventory', '--bundle', str(selected['bundle']),
        '--policy', str(selected['policy']), '--catalog', str(selected['catalog']),
        '--out', str(out), *extra])


def test_actual_portable_inventory_does_not_import_source_and_separates_capabilities(selected, tmp_path, capsys, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('inventory must not execute a route')
    monkeypatch.setattr(cli, '_execute', forbidden)
    out = tmp_path / 'METHOD_INVENTORY.json'
    assert _run(selected, out) == 0
    summary = json.loads(capsys.readouterr().out)
    value = json.loads(out.read_bytes())
    assert value['schema'] == 'function-extractor.method-inventory/v1'
    assert value['status'] == 'PARTIAL'
    assert [row['method'] for row in value['methods']] == ['sendMessage']
    assert value['methods'][0]['contract_status'] == 'CONTRACT_GAP'
    assert value['capabilities'][0]['methods'] == ['getWebhookInfo']
    assert len(value['proposals']) == 1
    assert value['coverage']['matched_callsites'] == 2
    assert value['coverage']['resolved_callsites'] == 1
    assert value['coverage']['whole_program_denominator'] is None
    assert not selected['marker'].exists()
    assert 'SYNTHETIC_PRIVATE_CANARY' not in out.read_text()
    assert content_digest(value) == value['content_digest']
    assert set(value['engine']['file_pins']) == {'cli.py', 'contract_engine.py', 'method_inventory.py'}
    root = Path(cli.__file__).parent
    for name, sha in value['engine']['file_pins'].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == sha
    assert value['production_effects'] == 0 and value['runtime_acceptance'] is False
    assert value['live_provider_observed'] is False and summary['runtime_acceptance'] is False
    assert out.stat().st_mode & 0o777 == 0o600


def test_inventory_is_deterministic_and_source_checkout_independent(selected, tmp_path, capsys):
    first, second = tmp_path / 'first.json', tmp_path / 'second.json'
    assert _run(selected, first) == 0
    capsys.readouterr()
    # Move the original public source: the portable bundle must be sufficient.
    (tmp_path / 'source').rename(tmp_path / 'source-unavailable')
    assert _run(selected, second) == 0
    capsys.readouterr()
    assert first.read_bytes() == second.read_bytes()
    assert not selected['marker'].exists()


@pytest.mark.parametrize('fault', ['symlink_bundle', 'secret_policy_path', 'existing_output', 'tampered_bundle'])
def test_cli_refuses_unsafe_inputs_and_existing_output_without_execution(selected, tmp_path, capsys, fault):
    selected = dict(selected)
    out = tmp_path / 'out.json'
    if fault == 'symlink_bundle':
        link = tmp_path / 'bundle-link.json'
        link.symlink_to(selected['bundle'])
        selected['bundle'] = link
    elif fault == 'secret_policy_path':
        secret = tmp_path / 'credentials.json'
        secret.write_bytes(selected['policy'].read_bytes())
        selected['policy'] = secret
    elif fault == 'existing_output':
        out.write_bytes(b'preserve-existing-evidence\n')
    else:
        bad = json.loads(selected['bundle'].read_bytes())
        row = bad['manifest']['files'][0]
        row['sha256'] = '0' * 64
        selected['bundle'] = _write(tmp_path / 'tampered.json', bad)
    assert _run(selected, out) == 2
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'REFUSED'
    if fault == 'existing_output':
        assert out.read_bytes() == b'preserve-existing-evidence\n'
    else:
        assert not out.exists()
    assert not selected['marker'].exists()


def test_invalid_ce_map_is_persisted_as_typed_refusal(selected, tmp_path, capsys):
    malformed = _write(tmp_path / 'bad-contract-map.json', {'schema': 'untrusted'})
    out = tmp_path / 'refusal.json'
    assert _run(selected, out, ['--contracts', str(malformed)]) == 2
    result = json.loads(capsys.readouterr().out)
    saved = json.loads(out.read_bytes())
    assert result['status'] == saved['status'] == 'REFUSED'
    assert saved['errors'] == ['CONTRACT_MAP_INVALID']
    assert content_digest(saved) == saved['content_digest']
    assert saved['production_effects'] == 0 and saved['runtime_acceptance'] is False
    assert not selected['marker'].exists()


def test_inventory_policy_catalog_and_actual_output_formal_schemas(selected, tmp_path, capsys):
    import subprocess
    folder = Path(cli.__file__).parent / 'contracts'
    names = ['method_policy.schema.json', 'method_catalog.schema.json', 'method_inventory.schema.json']
    schemas = {name: json.loads((folder / name).read_bytes()) for name in names}
    out = tmp_path / 'actual-formal.json'
    assert _run(selected, out) == 0
    capsys.readouterr()
    actual = json.loads(out.read_bytes())
    actual_policy = json.loads((folder / 'method_discovery.policy.json').read_bytes())
    actual_catalog = json.loads((folder / 'telegram_methods.catalog.json').read_bytes())
    valid = [['method_inventory.schema.json', actual],
             ['method_policy.schema.json', actual_policy], ['method_catalog.schema.json', actual_catalog],
             ['method_inventory.schema.json', {'schema': 'function-extractor.method-inventory/v1',
                'version': 1, 'status': 'REFUSED', 'errors': ['CONTRACT_MAP_INVALID'],
                'production_effects': 0, 'live_provider_observed': False, 'runtime_acceptance': False}]]
    def clone(value):
        return json.loads(json.dumps(value))
    invalid = []
    changed = clone(actual); changed['runtime_acceptance'] = True
    invalid.append(['method_inventory.schema.json', changed])
    changed = clone(actual); changed['methods'][0]['wire_proof'] = 'PASS'
    invalid.append(['method_inventory.schema.json', changed])
    changed = clone(actual); changed['delivery_state'] = 'SENT'
    invalid.append(['method_inventory.schema.json', changed])
    changed = clone(actual); changed['engine']['file_pins']['cli.py'] = 'not-a-pin'
    invalid.append(['method_inventory.schema.json', changed])
    changed = clone(actual_policy); changed['dispatches'][0]['method_arg'] = -1
    invalid.append(['method_policy.schema.json', changed])
    changed = clone(actual_policy); changed['version'] = True
    invalid.append(['method_policy.schema.json', changed])
    changed = clone(actual_catalog); changed['methods'][0]['status'] = 'BUSINESS_ACCEPTED'
    invalid.append(['method_catalog.schema.json', changed])
    changed = clone(actual_catalog); changed['sources'][0]['representation_sha256'] = 'not-a-pin'
    invalid.append(['method_catalog.schema.json', changed])
    script = '''import json,sys
from jsonschema import Draft202012Validator
d=json.load(sys.stdin)
for s in d['schemas'].values(): Draft202012Validator.check_schema(s)
for name,value in d['valid']: Draft202012Validator(d['schemas'][name]).validate(value)
for name,value in d['invalid']:
 if Draft202012Validator(d['schemas'][name]).is_valid(value): raise SystemExit(2)
print(json.dumps({'schemas':len(d['schemas']),'valid':len(d['valid']),'malformed_refused':len(d['invalid'])}))
'''
    result = subprocess.run(['/usr/bin/python3', '-I', '-c', script],
        input=json.dumps({'schemas': schemas, 'valid': valid, 'invalid': invalid}),
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    assert result.returncode == 0, {'category': 'FORMAL_INVENTORY_SCHEMA_FAILED', 'exit': result.returncode}
    assert json.loads(result.stdout) == {'schemas': 3, 'valid': 4, 'malformed_refused': 8}
    assert result.stderr == '' and not selected['marker'].exists()
