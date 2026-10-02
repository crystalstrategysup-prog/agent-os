"""Legacy migration is explicit, bounded and never guesses owned delivery evidence."""
from __future__ import annotations

import copy

import pytest
from test_continuation_dispatch import accepted, move, queued
from test_foundation import setup as foundation_setup

from agent_os import continuation as c
from agent_os import continuation_migration as m
from agent_os.safeio import GateError, atomic_json, filemap, sha

setup = foundation_setup


def legacy(setup, state='PENDING'):
    item = queued(setup)
    if state != 'PENDING':
        item = move(setup[1], item, 'claim')
    if state in {'DELIVERY_UNKNOWN', 'ACKNOWLEDGED'}:
        item = move(setup[1], item, 'begin-delivery')
    if state == 'ACKNOWLEDGED':
        item = move(setup[1], item, 'acknowledge', accepted(item))
    item = copy.deepcopy(item)
    item['schema'] = c.LEGACY_ITEM_SCHEMA
    for key in ['delivery_generation', 'delivery_nonce', 'delivery_started_at', 'consumed_receipt_ids', 'receipt_history']:
        item.pop(key)
    if item['receipt']:
        for key in ['schema', 'delivery_generation', 'delivery_nonce', 'user_event_at', 'later_activity_at']:
            item['receipt'].pop(key)
    atomic_json(c._path(setup[1], item['id']), item)
    return item


def test_pending_plan_is_read_only_and_apply_preserves_exact_original_backup(setup):
    item = legacy(setup); home = setup[1]
    original = c._path(home, item['id']).read_bytes(); before = filemap(home)
    plan = m.migrate(home, item['id'], 'parent', item['revision'])
    assert plan['status'] == 'PLANNED_PROMOTION' and filemap(home) == before
    result = m.migrate(home, item['id'], 'parent', item['revision'], apply=True, expected_sha256=sha(original))
    promoted = c.read(home, item['id'])
    assert result['status'] == 'PROMOTED_PENDING_V2'
    assert (home / result['backup']).read_bytes() == original
    assert promoted['identity'] == item['identity'] and promoted['continuation'] == item['continuation']
    assert promoted['state'] == 'PENDING' and promoted['delivery_generation'] == 0
    assert promoted['attempt_id'] is None and promoted['receipt_history'] == []
    assert promoted['revision'] == item['revision'] + 1
    assert result['dispatch_admitted'] is False
    assert move(home, move(home, promoted, 'claim'), 'begin-delivery')['delivery_generation'] == 1


@pytest.mark.parametrize('state', ['CLAIMED', 'DELIVERY_UNKNOWN', 'ACKNOWLEDGED'])
def test_owned_unknown_ack_plan_hold_and_apply_refuses_without_loss(setup, state):
    item = legacy(setup, state); home = setup[1]; before = filemap(home)
    plan = m.migrate(home, item['id'], 'parent', item['revision'])
    assert plan['status'] == 'HOLD_LEGACY_UNBOUND' and plan['state'] == state
    with pytest.raises(GateError, match='provider_reconciliation'):
        m.migrate(home, item['id'], 'parent', item['revision'], apply=True, expected_sha256=plan['source_sha256'])
    assert filemap(home) == before and c.read(home, item['id']) == item


@pytest.mark.parametrize('case', ['stale-revision', 'wrong-sha', 'wrong-owner', 'bool-revision'])
def test_migration_cas_and_owner_checks_do_not_write(setup, case):
    item = legacy(setup); home = setup[1]; before = filemap(home)
    kwargs = {'actor': 'parent', 'revision': item['revision'], 'expected_sha256': sha(c._path(home, item['id']).read_bytes())}
    if case == 'stale-revision': kwargs['revision'] += 1
    if case == 'wrong-sha': kwargs['expected_sha256'] = '0' * 64
    if case == 'wrong-owner': kwargs['actor'] = 'other'
    if case == 'bool-revision': kwargs['revision'] = True
    with pytest.raises(GateError): m.migrate(home, item['id'], apply=True, **kwargs)
    assert filemap(home) == before


def test_lost_response_after_promotion_is_readable_idempotent_and_backup_preserved(setup, monkeypatch):
    item = legacy(setup); home = setup[1]; original = c._path(home, item['id']).read_bytes()
    real = m.atomic_json
    def commit_then_lose(path, value):
        real(path, value)
        raise OSError('synthetic lost migration response')
    monkeypatch.setattr(m, 'atomic_json', commit_then_lose)
    with pytest.raises(OSError):
        m.migrate(home, item['id'], 'parent', item['revision'], apply=True, expected_sha256=sha(original))
    monkeypatch.setattr(m, 'atomic_json', real)
    promoted = c.read(home, item['id']); before = filemap(home)
    result = m.migrate(home, item['id'], 'parent', promoted['revision'])
    assert result['status'] == 'ALREADY_V2' and filemap(home) == before
    assert (home / promoted['migration']['backup']).read_bytes() == original


def test_pending_with_old_attempt_evidence_cannot_be_promoted(setup):
    item = legacy(setup); item['attempt_id'] = 'historical-operation'
    atomic_json(c._path(setup[1], item['id']), item); before = filemap(setup[1])
    assert m.migrate(setup[1], item['id'], 'parent', item['revision'])['status'] == 'HOLD_LEGACY_UNBOUND'
    assert filemap(setup[1]) == before


def test_conflicting_backup_blocks_migration(setup):
    item = legacy(setup); home = setup[1]; plan = m.migrate(home, item['id'], 'parent', item['revision'])
    backup = home / plan['backup']; backup.parent.mkdir(parents=True); backup.write_bytes(b'unrelated bytes')
    before = filemap(home)
    with pytest.raises(GateError, match='backup_conflict'):
        m.migrate(home, item['id'], 'parent', item['revision'], apply=True, expected_sha256=plan['source_sha256'])
    assert filemap(home) == before


def test_migration_cli_plan_never_applies_implicitly(setup):
    item = legacy(setup); before = filemap(setup[1])
    result, code = c.command(['migrate-legacy', '--id', item['id'], '--actor', 'parent', '--revision', str(item['revision'])], setup[1])
    assert code == 0 and result['status'] == 'PLANNED_PROMOTION' and filemap(setup[1]) == before
