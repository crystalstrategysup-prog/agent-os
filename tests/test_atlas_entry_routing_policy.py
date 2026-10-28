"""Current-source routing preservation and existing selective catalog behavior."""
import hashlib
import importlib
import json
from pathlib import Path
import pytest
from agent_os import atlas_module

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / 'modules/atlas/skills/atlas'
BUNDLED = ROOT / 'src/agent_os/resources/skills/atlas'
ORIGINAL_POLICY_SHA = 'ba76fc464267e1668939c427f06ddfe9070e2c3c02951eedfbceb4c2644a1609'


def test_original_policy_preserved_byte_for_byte_and_packaged():
    raw = (ROOT / 'docs/ATLAS_SOURCE_POLICY.md').read_bytes()
    original = raw.split(b'## Original policy, verbatim\n\n', 1)[1]
    assert hashlib.sha256(original).hexdigest() == ORIGINAL_POLICY_SHA
    assert raw == (ROOT / 'src/agent_os/resources/docs/ATLAS_SOURCE_POLICY.md').read_bytes()


def test_router_resolves_real_skill_and_policy_without_size_gate():
    router = (ROOT / 'AGENTS.md').read_text()
    assert 'modules/atlas/skills/atlas/SKILL.md' in router
    assert 'docs/ATLAS_SOURCE_POLICY.md' in router
    assert 'maximum' not in router.lower()
    assert 'resolve and READ' in (ATLAS / 'SKILL.md').read_text()


@pytest.mark.parametrize('rel', ['SKILL.md', 'references/operating-modes.md',
                               'scripts/work_profile.py', 'scripts/WORKSPACE_OPERATIONS.json'])
def test_packaged_and_standalone_mirrors_identical(rel):
    assert (ATLAS / rel).read_bytes() == (BUNDLED / rel).read_bytes()


def test_function_card_pins_code_in_existing_registry():
    registry = json.loads((ATLAS / 'scripts/WORKSPACE_OPERATIONS.json').read_text())
    matches = [x for x in registry['methods'] if x['id'] == 'profile']
    assert len(matches) == 1
    card = matches[0]
    assert card['source']['sha256'] == hashlib.sha256((ATLAS / card['source']['path']).read_bytes()).hexdigest()
    assert card['effect'] == 'read_only' and card['contract_version'] == '1.0.0'
    assert card['rollback'] and card['tests'] and card['unknowns']


def test_existing_catalog_reads_only_selected_source_and_keeps_unknown(tmp_path, monkeypatch):
    selected = {'contracts': [{'id': 'C1', 'component': 'One',
                 'authorization': {'state': 'unknown', 'reason': 'owner must qualify'},
                 'execution_status': 'NOT_RUN', 'results': [{'state': 'unknown', 'reason': 'no runtime proof'}]}]}
    (tmp_path / 'selected.json').write_text(json.dumps(selected))
    (tmp_path / 'unrelated.json').write_text('THIS FILE MUST NOT BE READ')
    with atlas_module._workspace():
        catalog = importlib.import_module('catalog')
        original, reads = catalog.nav.read_selected, []
        def observe(root, path, *args):
            reads.append(path)
            return original(root, path, *args)
        monkeypatch.setattr(catalog.nav, 'read_selected', observe)
        cards, pin = catalog.compile_catalog(tmp_path, {'schema': 'atlas.catalog-source/v1',
                    'format': 'record-catalog', 'path': 'selected.json', 'document_id': 'DOC-ONE'})
    assert reads == ['selected.json']
    assert pin['sha256'] == hashlib.sha256((tmp_path / 'selected.json').read_bytes()).hexdigest()
    assert len(cards['contracts']) == 1
    assert cards['contracts'][0]['execution'] == 'NOT_RUN'
    assert json.loads(cards['contracts'][0]['auth']) == {'reason': 'owner must qualify', 'state': 'unknown'}


def test_existing_source_pin_refuses_stale_content(tmp_path):
    (tmp_path / 'one.txt').write_text('current')
    with atlas_module._workspace():
        engine = importlib.import_module('atlas')
        with pytest.raises(engine.nav.Invalid):
            engine.pinned(tmp_path, {'path': 'one.txt', 'bytes': 7, 'sha256': '0' * 64}, {}, 'test')


def test_home_migration_stays_unqualified():
    text = (ATLAS / 'references/operating-modes.md').read_text()
    assert 'unqualified proposal' in text
    assert 'do not install it or shorten home AGENTS' in text
    assert 'does not lower' in text and 'READY' in text
