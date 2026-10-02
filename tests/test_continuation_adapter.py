"""These are contract fixtures, not real provider acceptance."""
from __future__ import annotations

import pytest
from test_continuation_dispatch import accepted, move, queued, rejected
from test_foundation import setup as foundation_setup

from agent_os import continuation_adapter as a
from agent_os.safeio import GateError, filemap

setup = foundation_setup


def mapping():
    return {'schema': 'agentos.continuation-adapter-binding/v1', 'provider': 'synthetic-parent-adapter',
            'target_owner': 'independent-reviewer', 'target_id': 'fixture-target',
            'workstream_id': 'fixture-workstream', 'parent_owner': 'parent'}


def item(setup):
    return move(setup[1], move(setup[1], queued(setup), 'claim'), 'begin-delivery')


def test_request_propagates_exact_committed_operation_generation_nonce_and_target(setup):
    unknown = item(setup); before = filemap(setup[1]); result = a.request(unknown, mapping())
    assert result['operation_key'] == unknown['attempt_id']
    assert result['delivery_generation'] == unknown['delivery_generation'] and result['delivery_nonce'] == unknown['delivery_nonce']
    assert result['target_id'] == 'fixture-target' and result['provider_invocation_performed'] is False
    assert result['target_authority_proven'] is False and filemap(setup[1]) == before


@pytest.mark.parametrize('action', ['acknowledge', 'not-sent'])
def test_receipt_check_does_not_authenticate_or_transition_fixture(setup, action):
    unknown = item(setup); before = filemap(setup[1])
    receipt = accepted(unknown) if action == 'acknowledge' else rejected(unknown)
    result = a.check_receipt(unknown, mapping(), receipt, action)
    assert result['status'] == 'STRUCTURE_MATCHES'
    assert result['external_provenance_proven'] is False and result['delivery_acceptance_proven'] is False
    assert result['ledger_transition_performed'] is False and filemap(setup[1]) == before


@pytest.mark.parametrize('field,value', [('provider','relabeled-provider'),('delivery_nonce','unrelated-call'),('delivery_generation',2)])
def test_relabel_or_unrelated_generation_is_refused(setup, field, value):
    unknown = item(setup); before = filemap(setup[1]); receipt = accepted(unknown); receipt[field] = value
    with pytest.raises(GateError): a.check_receipt(unknown, mapping(), receipt, 'acknowledge')
    assert filemap(setup[1]) == before


@pytest.mark.parametrize('field', ['target_owner', 'parent_owner', 'schema'])
def test_mapping_conflicts_cannot_be_admitted(setup, field):
    unknown = item(setup); bound = mapping(); bound[field] = 'wrong'
    with pytest.raises(GateError): a.request(unknown, bound)


def test_request_requires_committed_unknown(setup):
    with pytest.raises(GateError, match='committed_v2_unknown'):
        a.request(queued(setup), mapping())
