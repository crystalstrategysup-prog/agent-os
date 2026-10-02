"""Queue-reader compatibility guards data and activation, never downgrades ledgers."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from test_continuation_causal import begun, queued_causal, receipt
from test_continuation_dispatch import accepted, move, queued
from test_continuation_migration import legacy
from test_foundation import setup as foundation_setup

from agent_os import continuation as c
from agent_os import continuation_causal as v3
from agent_os.safeio import filemap

setup = foundation_setup
spec = importlib.util.spec_from_file_location('continuation_installer', Path(__file__).resolve().parents[1] / 'tools/install.py')
assert spec and spec.loader
installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)


def manifest(supported):
    return {'overlay_schema': 1, 'config_schema': 'agent-os.community-config/v5', 'continuation_schemas': supported}


@pytest.mark.parametrize('schema,state', [('v1','DELIVERY_UNKNOWN'),('v1','ACKNOWLEDGED'),('v2','DELIVERY_UNKNOWN'),('v2','ACKNOWLEDGED')])
def test_unsupported_old_reader_holds_each_unknown_ack_without_data_loss(setup, schema, state):
    if schema == 'v1': legacy(setup, state)
    else:
        item = move(setup[1], move(setup[1], queued(setup), 'claim'), 'begin-delivery')
        if state == 'ACKNOWLEDGED': move(setup[1], item, 'acknowledge', accepted(item))
    before = filemap(setup[1])
    with pytest.raises(installer.InstallError, match='preserve_and_hold'):
        installer.check_user_compatibility(setup[1], manifest([]))
    installer.check_user_compatibility(setup[1], manifest(['agentos.continuation-item/v1','agentos.continuation-item/v2']))
    assert filemap(setup[1]) == before


def test_active_continuation_lock_blocks_activation_lock(setup):
    queued(setup); marker = setup[1] / 'state/continuations.lock'; marker.mkdir(); before = filemap(setup[1])
    with pytest.raises(installer.InstallError, match='manual_review'), installer.continuation_lock(setup[1]):
        pytest.fail('should not acquire existing lock')
    assert filemap(setup[1]) == before and marker.is_dir()


def test_activation_lock_serializes_protocol_writers_and_is_removed_without_state_loss(setup):
    item = queued(setup); before = filemap(setup[1])
    with installer.continuation_lock(setup[1]), pytest.raises(ValueError, match='busy_or_stale_lock'):
        move(setup[1], item, 'claim')
    assert filemap(setup[1]) == before


def test_queue_symlink_is_refused_before_reading_target(setup, tmp_path):
    home = setup[1]; home.mkdir(); outside = tmp_path / 'outside'; outside.mkdir(); (home / 'state').symlink_to(outside)
    with pytest.raises(installer.InstallError, match='symlink'):
        installer.check_user_compatibility(home, manifest([]))


@pytest.mark.parametrize('state', ['PENDING', 'CLAIMED', 'DELIVERY_UNKNOWN', 'RECEIVED', 'RECEIVED_REFUSED'])
def test_v3_queue_blocks_old_release_activation_and_preserves_exact_bytes(setup, state):
    item = queued_causal(setup) if state in {'PENDING', 'CLAIMED'} else begun(setup)
    if state == 'CLAIMED': item = move(setup[1], item, 'claim')
    if state in v3.TERMINAL:
        item = move(setup[1], item, 'record-receipt', receipt(item, 'received' if state == 'RECEIVED' else 'received_refused'))
    before = filemap(setup[1])
    with pytest.raises(installer.InstallError, match='incompatible_preserve_and_hold'):
        installer.check_user_compatibility(setup[1], manifest([c.LEGACY_ITEM_SCHEMA, c.ITEM_SCHEMA]))
    installer.check_user_compatibility(setup[1], manifest([c.LEGACY_ITEM_SCHEMA, c.ITEM_SCHEMA, v3.ITEM_SCHEMA]))
    assert filemap(setup[1]) == before


def test_versioned_capability_is_explicit_and_old_v1_declaration_stays_unchanged(tmp_path):
    root = Path(__file__).resolve().parents[1]
    wheel = tmp_path / 'synthetic-capabilities.whl'
    old = (root / 'schemas/continuation-capabilities-v1.json').read_bytes()
    new = (root / 'schemas/continuation-capabilities-v2.json').read_bytes()
    with ZipFile(wheel, 'w') as archive:
        archive.writestr('agent_os/resources/contracts/continuation-capabilities-v1.json', old)
    assert installer.wheel_continuation_schemas(wheel) == [c.LEGACY_ITEM_SCHEMA, c.ITEM_SCHEMA]
    with ZipFile(wheel, 'a') as archive:
        archive.writestr('agent_os/resources/contracts/continuation-capabilities-v2.json', new)
    assert installer.wheel_continuation_schemas(wheel) == [c.LEGACY_ITEM_SCHEMA, c.ITEM_SCHEMA, v3.ITEM_SCHEMA]
    value = json.loads(new); value['causal_acceptance_scope'] = 'successful_work'
    with ZipFile(wheel, 'w') as archive:
        archive.writestr('agent_os/resources/contracts/continuation-capabilities-v2.json', json.dumps(value))
    with pytest.raises(installer.InstallError, match='capabilities_invalid'):
        installer.wheel_continuation_schemas(wheel)
