"""Finite OVL admission fixture; original application functions are unmodified.

Only private SQLite/configuration/qualification data are SIMULATED. No provider,
credential reader, runtime owner, production schema or native receipt is used.
"""
import json
from types import ModuleType, SimpleNamespace


ENTRY = 'app.ingest.telegram_owner_private_composition:accept_webhook'
CASES = frozenset({'resident_admission_to_owner_queue', 'conflicting_update_identity',
                   'spoofed_private_actor', 'stale_caller_generation', 'wrong_caller_tenant'})
REFUSALS = {'conflicting_update_identity': 'owner_update_identity_conflict',
            'spoofed_private_actor': 'owner_private_sender_invalid',
            'stale_caller_generation': 'owner_private_route_changed',
            'wrong_caller_tenant': 'owner_private_route_not_qualified'}
ACCEPTED = dict(status='accepted', duplicate=False, role='RESIDENT', state='projected')


def _case(fixture):
    keys = {'schema', 'case', 'route', 'evidence', 'entry', 'opaque_modules',
            'include_modules', 'include_entries', 'capture_mode', 'trace_modules',
            'max_trace_events'}
    if (type(fixture) is not dict or set(fixture) not in (keys, keys | {'expected_result'})
            or fixture.get('schema') != 'route-probe.ovl-admission-fixture/v1'
            or fixture.get('case') not in CASES or fixture.get('route') != 'owner_private'
            or fixture.get('evidence') != 'SIMULATED' or fixture.get('entry') != ENTRY
            or fixture.get('opaque_modules') != ['app.core.config']
            or fixture.get('max_trace_events') != 5000):
        raise ValueError('ovl_fixture_invalid')
    if 'expected_result' in fixture and (fixture['case'] != 'resident_admission_to_owner_queue'
                                       or fixture['expected_result'] != ACCEPTED):
        raise ValueError('ovl_fixture_expectation_invalid')
    return fixture['case']


def bootstrap(fixture, context):
    if type(fixture) is dict and fixture.get('schema') == PLATFORM_SCHEMA:
        return _bootstrap_platform(fixture, context)
    if type(fixture) is dict and fixture.get('schema') == OWNER_REPLY_SCHEMA:
        return _bootstrap_owner_reply(fixture, context)
    if type(fixture) is dict and fixture.get('schema') == FORWARD_SCHEMA:
        return _bootstrap_forward(fixture, context)
    _case(fixture)
    config = ModuleType('app.core.config')
    config.settings = SimpleNamespace(database_url='sqlite:///:memory:', tenant_id='vladivostok',
        environment='dev', telegram_owner_private_enabled=True,
        app_read_only_mode=False, external_effects_disabled=False)
    context.emit('ovl_import_boundary', 'CONFIG_ONLY', evidence='SIMULATED', count=1)
    return {config.__name__: config}


def _install_uuid(state):
    # This exact DBAPI slot is module-wide; dedicated offline child/serial tests only.
    import sqlite3
    from uuid import UUID
    if type(sqlite3.adapters) is not dict:
        raise ValueError('ovl_uuid_registry_unsupported')
    key = (UUID, sqlite3.PrepareProtocol)
    present = key in sqlite3.adapters
    previous = sqlite3.adapters.get(key)
    if present and not callable(previous):
        raise ValueError('ovl_uuid_registry_unsupported')
    state['uuid_slot'] = (sqlite3.adapters, key, present, previous)
    sqlite3.register_adapter(UUID, str)
    state['uuid_installed'] = True


def _restore_uuid(state):
    if not state.get('uuid_installed'):
        return
    registry, key, present, previous = state['uuid_slot']
    if registry.get(key) is not str:
        raise ValueError('ovl_uuid_slot_changed')
    if present:
        registry[key] = previous
    else:
        del registry[key]
    state['uuid_installed'] = False


def _cleanup(state):
    try:
        if state.get('db') is not None:
            try:
                state['db'].rollback()
            finally:
                state['db'].close()
    finally:
        try:
            if state.get('engine') is not None:
                state['engine'].dispose()
        finally:
            _restore_uuid(state)


def _snapshot(state):
    from sqlalchemy import select
    with state['factory']() as db:
        return {table.name: [dict(row) for row in db.execute(select(table).order_by(*table.primary_key.columns)).mappings()]
                for table in state['tables']}


def _persisted_proof(state):
    from sqlalchemy import select
    composition, ledger, route_module = state['composition'], state['ledger'], state['route_module']
    with state['factory']() as db:
        messages = db.execute(select(state['message'])).mappings().all()
        facts = db.execute(select(ledger.facts)).mappings().all()
        operations = db.execute(select(ledger.effects)).mappings().all()
        admissions = db.execute(select(composition.inbox)).mappings().all()
        assert len(messages) == len(facts) == len(operations) == len(admissions) == 1
        assert db.execute(select(ledger.aliases)).first() is None
        message, fact_row, operation, admission = messages[0], facts[0], operations[0], admissions[0]
        fact = ledger._fact(json.loads(fact_row['fact_json']))
        plan = ledger._plan(json.loads(operation['plan_json']))
        forwarding = state['context'].load_module('app.ingest.telegram_owner_private_forwarding')
        assert type(plan) is forwarding.ForwardMirrorPlan
        assert route_module.validate_plan(state['current_route'], plan) is True
        ref = fact.physical
        assert ref is not None and plan.resident == fact
        assert (ref.tenant_id, ref.message_id, composition.utc(ref.source_created_at), ref.message_uid) == (
            message['tenant_id'], message['id'], composition.utc(message['source_created_at']), message['message_uid'])
        assert (fact_row['message_id'], composition.utc(fact_row['message_created_at']), fact_row['message_uid']) == (
            ref.message_id, composition.utc(ref.source_created_at), ref.message_uid)
        assert admission['source_key'] == fact.key == operation['source_key'] == ref.message_uid
        assert fact.native_digest == route_module.digest(state['original_event']['message'])
        assert admission['payload_digest'] == route_module.digest(state['original_event'])
        assert admission['payload_json'] == ledger.dumps(state['original_event'])
        assert admission['state'] == 'projected' and admission['role'] == 'RESIDENT'
        assert operation['intended_digest'] == plan.intended_digest
        assert operation['state'] == 'queued' and operation['attempts'] == 0
        assert operation['receipt_json'] is None and operation['claim_owner_id'] is None and operation['claim_epoch'] is None
        assert plan.kind == 'owner_mirror' and plan.destination_user_id == composition.OWNER > 0
        assert plan.wire == {'method': 'forwardMessage', 'chat_id': composition.OWNER,
            'from_chat_id': state['original_event']['message']['chat']['id'],
            'message_id': state['original_event']['message']['message_id']}
        assert message['source_instance'] == composition.INSTANCE and message['private_chat'] is True
        assert message['metadata']['owner_private_role'] == 'RESIDENT'
        assert message['metadata']['owner_private_bot_id'] == composition.BOT
        assert composition.read_physical(db, ref)['id'] == message['id']


def prepare(target, fixture, context):
    if type(fixture) is dict and fixture.get('schema') == PLATFORM_SCHEMA:
        return _prepare_platform(target, fixture, context)
    if type(fixture) is dict and fixture.get('schema') == OWNER_REPLY_SCHEMA:
        return _prepare_owner_reply(target, fixture, context)
    if type(fixture) is dict and fixture.get('schema') == FORWARD_SCHEMA:
        return _prepare_forward(target, fixture, context)
    case = _case(fixture)
    composition = context.load_module('app.ingest.telegram_owner_private_composition')
    if target is not composition.accept_webhook:
        raise ValueError('ovl_target_invalid')
    from sqlalchemy import create_engine, insert
    from sqlalchemy.orm import sessionmaker
    from dataclasses import replace
    ledger = context.load_module('app.ingest.telegram_owner_private_state')
    route_module = context.load_module('app.ingest.telegram_owner_private_route')
    models = context.load_module('app.models')
    base = context.load_module('app.core.db').Base
    state = dict(context=context, composition=composition, ledger=ledger, route_module=route_module,
                 engine=None, db=None, uuid_installed=False)
    context.ovl_state = state
    try:
        engine = state['engine'] = create_engine('sqlite:///:memory:')
        base.metadata.create_all(engine)
        ledger.metadata.create_all(engine)
        state['factory'] = sessionmaker(bind=engine, autoflush=False)
        generation = 2 if case == 'stale_caller_generation' else 1
        current = route_module.OwnerPrivateRoute.from_dict(dict(schema='telegram.owner-private-route/v1',
            tenant_id=composition.TENANT, bot_id=composition.BOT, generation=generation, enabled=True,
            target=dict(kind='owner_private', peer_type='private', user_id=composition.OWNER)))
        current.validate()
        state['current_route'] = current
        qualification = dict(schema='telegram.owner-private-qualification/v1', bot_id=composition.BOT,
            owner_user_id=composition.OWNER, tenant_id=composition.TENANT, generation=generation,
            route_fingerprint=current.fingerprint(), target_kind='owner_private',
            get_me=dict(id=composition.BOT, is_bot=True), owner_chat=dict(id=composition.OWNER, type='private'),
            checked_at='2026-01-01T00:00:00+00:00', native_receipt_ref='SIMULATED_NOT_PROVIDER_PROOF',
            cutover_ref='SIMULATED_NOT_CURRENT_AUTHORITY', owner_approval_ref='SIMULATED_NOT_OWNER_AUTHORITY')
        with state['factory']() as db:
            db.execute(insert(composition.bindings).values(bot_id=str(composition.BOT), tenant_id=composition.TENANT,
                owner_user_id=composition.OWNER, generation=generation, enabled=True,
                identity_verified=True, owner_verified=True, token_ref=composition.TOKEN_REF,
                secret_ref=composition.SECRET_REF, qualification_json=ledger.dumps(qualification)))
            db.commit()
            assert composition.load_route(db) == current
        event = dict(update_id=900001, message=dict(message_id=700, date=1767225600,
            chat=dict(id=900002, type='private'),
            **{'from': dict(id=900002, is_bot=False, first_name='Synthetic resident')},
            text='Synthetic isolated OVL admission'))
        state['original_event'] = json.loads(json.dumps(event))
        state['message'] = models.Message.__table__
        state['tables'] = (composition.inbox, ledger.facts, state['message'], ledger.effects, ledger.aliases)
        _install_uuid(state)
        if case == 'conflicting_update_identity':
            with state['factory']() as db:
                assert target(db, current, state['original_event']) == ACCEPTED
                db.commit()
            _persisted_proof(state)
            context.emit('ovl_prior_admission', 'COMMITTED', evidence='SIMULATED', count=1)
            event['message']['text'] = 'Different synthetic identity at the same key'
        elif case == 'spoofed_private_actor':
            event['message']['from']['id'] = 900003
        caller = replace(current, generation=1) if case == 'stale_caller_generation' else current
        if case == 'wrong_caller_tenant':
            caller = replace(current, tenant_id='fixture_other_tenant')
        state['before'] = _snapshot(state)
        state['target'] = target
        state['db'] = state['factory']()
        state['prepared'] = dict(args=[state['db'], caller, event], kwargs={})
        context.emit('ovl_fixture_ready', 'SIMULATED_QUALIFICATION', evidence='SIMULATED',
                     generation=generation, native_calls=0)
        return state['prepared']
    except BaseException:
        _cleanup(state)
        raise


def observe_outcome(result, exception, fixture, context):
    if type(fixture) is dict and fixture.get('schema') == PLATFORM_SCHEMA:
        return _observe_platform(result, exception, fixture, context)
    if type(fixture) is dict and fixture.get('schema') == OWNER_REPLY_SCHEMA:
        return _observe_owner_reply(result, exception, fixture, context)
    if type(fixture) is dict and fixture.get('schema') == FORWARD_SCHEMA:
        return _observe_forward(result, exception, fixture, context)
    case, state = _case(fixture), context.ovl_state
    try:
        if case == 'resident_admission_to_owner_queue':
            assert exception is None and result == ACCEPTED
            context.emit('ovl_target', 'accepted', evidence='SIMULATED')
            state['db'].commit()
            context.emit('ovl_caller_commit', 'COMMITTED', evidence='SIMULATED', count=1)
            _persisted_proof(state)
            before = _snapshot(state)
            context.emit('ovl_fullref', 'PROVEN', evidence='SIMULATED', count=1)
            context.emit('ovl_operation', 'owner_mirror.queued', evidence='SIMULATED', attempts=0, count=0)
            context.emit('ovl_duplicate_call', 'BEGIN', evidence='SIMULATED')
            with state['factory']() as db:
                duplicate = state['target'](db, state['current_route'], state['original_event'])
                assert duplicate == dict(ACCEPTED, duplicate=True)
                db.commit()
            assert before == _snapshot(state)
            context.emit('ovl_duplicate', 'UNCHANGED', evidence='SIMULATED', count=1)
        else:
            assert type(exception) is state['route_module'].OwnerPrivateRejected
            assert exception.args == (REFUSALS[case],)
            state['db'].rollback()
            assert state['before'] == _snapshot(state)
            context.emit('ovl_refusal', REFUSALS[case], evidence='SIMULATED')
            context.emit('ovl_preservation', 'UNCHANGED', evidence='SIMULATED')
        context.emit('ovl_native', 'NOT_ATTEMPTED', evidence='SIMULATED', count=0)
    finally:
        _cleanup(state)
    context.emit('ovl_cleanup', 'RESTORED', evidence='SIMULATED')


FORWARD_SCHEMA = 'route-probe.ovl-forward-fixture/v1'
FORWARD_ENTRY = 'app.ingest.telegram_owner_private_runtime:dispatch_once'
FORWARD_CASES = frozenset({'forward_success', 'forward_timeout_no_retry'})
_SYNTHETIC_FORWARD_TOKEN = '6732031795:ovl_offline_synthetic'


def _forward_case(fixture):
    keys = {'schema', 'case', 'route', 'evidence', 'entry', 'opaque_modules',
            'include_modules', 'include_entries', 'capture_mode', 'trace_modules', 'max_trace_events'}
    if (type(fixture) is not dict or set(fixture) != keys
            or fixture.get('schema') != FORWARD_SCHEMA or type(fixture.get('case')) is not str
            or fixture['case'] not in FORWARD_CASES or fixture.get('route') != 'owner_private'
            or fixture.get('evidence') != 'SIMULATED' or fixture.get('entry') != FORWARD_ENTRY
            or fixture.get('opaque_modules') != ['app.core.config']
            or fixture.get('max_trace_events') != 5000):
        raise ValueError('ovl_forward_fixture_invalid')
    return fixture['case']


def _admission_precondition():
    # Internal fixed input only; no file/env/config or arbitrary event interface.
    return dict(schema='route-probe.ovl-admission-fixture/v1',
        case='resident_admission_to_owner_queue', route='owner_private', evidence='SIMULATED',
        entry=ENTRY, opaque_modules=['app.core.config'], include_modules=[], include_entries=[],
        capture_mode='PARTIAL_STATIC', trace_modules=[], max_trace_events=5000)


def _bootstrap_forward(fixture, context):
    _forward_case(fixture)
    return bootstrap(_admission_precondition(), context)


class _SimulatedForwardOwner:
    """Injected offline precondition, NOT original RuntimeOwner qualification."""
    def __init__(self, state):
        import threading
        self.route = state['current_route']
        self.dispatch_lock = threading.Lock()
        self.inflight = False
        self.owner_id, self.epoch = 'SIMULATED_OVL_OWNER', 1
        self.check_count = self.reader_count = 0
        self._state = state

    def check(self):
        self.check_count += 1
        return True  # Explicit SIMULATED process/FLOCK/credential/epoch boundary.

    def reader(self, reference):
        if reference != self._state['composition'].TOKEN_REF:
            raise ValueError('ovl_forward_reader_scope')
        self.reader_count += 1
        return _SYNTHETIC_FORWARD_TOKEN


class _ForwardResponse:
    status_code = 200

    def __init__(self, state):
        self.state, self.closed = state, False

    def iter_content(self, chunk_size=1):
        assert chunk_size == 1
        self.state['context'].emit('ovl_forward_response', 'STREAMED', evidence='SIMULATED')
        raw = json.dumps(dict(ok=True, result=dict(message_id=800,
            chat=dict(id=self.state['composition'].OWNER, type='private')))).encode()
        for index in range(len(raw)):
            yield raw[index:index+1]

    def close(self):
        self.closed = True


class _ForwardSession:
    def __init__(self, state):
        self.state, self.closed = state, False
        self.trust_env, self.auth = True, 'SIMULATED_INITIAL_AUTH'
        self.proxies = {}
        self.cookies = SimpleNamespace(clear=lambda: None)
        self.retry_total = None
        self.response = None

    def mount(self, prefix, adapter):
        assert prefix == 'https://'
        self.retry_total = adapter.max_retries.total
        assert self.retry_total == 0

    def post(self, url, **kwargs):
        state = self.state
        assert url == 'https://api.telegram.org/bot' + _SYNTHETIC_FORWARD_TOKEN + '/forwardMessage'
        assert set(kwargs) == {'data', 'headers', 'timeout', 'allow_redirects', 'stream', 'verify'}
        assert type(kwargs['data']) is bytes
        event = state['original_event']['message']
        assert json.loads(kwargs['data']) == dict(chat_id=state['composition'].OWNER,
            from_chat_id=event['chat']['id'], message_id=event['message_id'])
        assert kwargs['headers'] == {'Content-Type': 'application/json', 'Accept': 'application/json'}
        assert kwargs['timeout'] == (5.0, 15.0)
        assert kwargs['allow_redirects'] is False and kwargs['stream'] is True and kwargs['verify'] is True
        assert self.trust_env is False and self.auth is None and self.proxies == {}
        assert self.retry_total == 0 and state['owner'].inflight is True
        from sqlalchemy import select
        with state['factory']() as db:
            row = db.execute(select(state['ledger'].effects)).mappings().one()
            assert row['state'] == 'sending' and row['attempts'] == 1
            assert row['claim_owner_id'] == state['owner'].owner_id and row['claim_epoch'] == state['owner'].epoch
        assert state['commits'][-1] == dict(state='sending', attempts=1, receipt=False, aliases=0)
        state['post_count'] += 1
        assert state['post_count'] == 1
        state['context'].emit('ovl_forward_post', 'ATTEMPTED', evidence='SIMULATED', count=state['post_count'])
        if state['forward_case'] == 'forward_timeout_no_retry':
            from requests import ReadTimeout
            state['http_failure'] = ReadTimeout()
            raise state['http_failure']
        self.response = _ForwardResponse(state)
        return self.response

    def close(self):
        self.closed = True


def _prepare_forward(target, fixture, context):
    case = _forward_case(fixture)
    runtime = context.load_module('app.ingest.telegram_owner_private_runtime')
    if target is not runtime.dispatch_once:
        raise ValueError('ovl_forward_target_invalid')
    composition = context.load_module('app.ingest.telegram_owner_private_composition')
    state = None
    try:
        args = prepare(composition.accept_webhook, _admission_precondition(), context)
        state = context.ovl_state
        assert composition.accept_webhook(*args['args'], **args['kwargs']) == ACCEPTED
        state['db'].commit()
        _persisted_proof(state)
        state['db'].close()
        state['db'] = None
        state['before_forward'] = _snapshot(state)
        state.update(forward_case=case, post_count=0, sessions=[], commits=[], forward_target=target)
        owner = state['owner'] = _SimulatedForwardOwner(state)
        from sqlalchemy import event, select
        def record_commit(connection):
            row = connection.execute(select(state['ledger'].effects)).mappings().one()
            aliases = connection.execute(select(state['ledger'].aliases)).mappings().all()
            state['commits'].append(dict(state=row['state'], attempts=row['attempts'],
                receipt=row['receipt_json'] is not None, aliases=len(aliases)))
            context.emit('ovl_forward_commit', row['state'], evidence='SIMULATED',
                         attempts=row['attempts'], count=len(aliases))
        event.listen(state['engine'], 'commit', record_commit)
        native = context.load_module('app.ingest.telegram_basic_native_transport')
        def session_factory():
            session = _ForwardSession(state)
            state['sessions'].append(session)
            return session
        transport = state['transport'] = native.BasicNativeTransport(None,
            session_factory=session_factory, authority_check=owner.check)
        state['forward_prepared'] = dict(args=[state['factory'], owner, transport], kwargs={})
        context.emit('ovl_forward_ready', 'SIMULATED_OWNER', evidence='SIMULATED', count=1)
        return state['forward_prepared']
    except BaseException:
        if state is not None:
            _cleanup(state)
        raise


def _forward_persisted_proof(state, expected):
    from sqlalchemy import select
    snapshot = _snapshot(state)
    ledger = state['ledger']
    for table in (state['composition'].inbox, ledger.facts, state['message']):
        assert snapshot[table.name] == state['before_forward'][table.name]
    with state['factory']() as db:
        row = dict(db.execute(select(ledger.effects)).mappings().one())
        before = state['before_forward'][ledger.effects.name][0]
        changed = {'state', 'attempts', 'receipt_json', 'claim_owner_id', 'claim_epoch'}
        assert {k:v for k,v in row.items() if k not in changed} == {k:v for k,v in before.items() if k not in changed}
        assert row['state'] == expected and row['attempts'] == 1
        assert row['claim_owner_id'] == state['owner'].owner_id and row['claim_epoch'] == state['owner'].epoch
        receipt = json.loads(row['receipt_json'])
        aliases = db.execute(select(ledger.aliases)).mappings().all()
        plan = ledger._plan(json.loads(row['plan_json']))
        if expected == 'sent':
            assert receipt == dict(state='sent', native_ids=[800], category=None)
            assert len(aliases) == 1
            alias_row = aliases[0]
            alias = ledger._alias(json.loads(alias_row['alias_json']))
            assert alias == state['route_module'].mirror_alias(state['current_route'], plan,
                dict(ok=True, result=dict(message_id=800)), attempt_state='sending')
            assert (alias_row['tenant_id'], alias_row['bot_id'], alias_row['target_kind'], alias_row['owner_user_id'],
                    alias_row['native_message_id'], alias_row['operation_key'], alias_row['source_key']) == (
                plan.tenant_id, str(plan.bot_id), 'owner_private', str(plan.destination_user_id), '800', plan.operation_key, plan.resident.key)
            assert state['commits'][-1] == dict(state='sent', attempts=1, receipt=True, aliases=1)
        else:
            assert receipt == dict(state='unknown', native_ids=[], category='response_invalid')
            from requests import ReadTimeout
            assert type(state.get('http_failure')) is ReadTimeout
            assert aliases == []
            assert state['commits'][-1] == dict(state='unknown', attempts=1, receipt=True, aliases=0)
        return snapshot, row


def _observe_forward(result, exception, fixture, context):
    case, state = _forward_case(fixture), context.ovl_state
    expected = 'sent' if case == 'forward_success' else 'unknown'
    try:
        assert exception is None
        rows = _snapshot(state)[state['ledger'].effects.name]
        assert len(rows) == 1
        assert result == dict(state=expected, operation_key=rows[0]['operation_key'], native_receipt_saved=True)
        assert state['post_count'] == len(state['sessions']) == 1
        assert state['sessions'][0].closed and state['sessions'][0].retry_total == 0
        if case == 'forward_success':
            assert state['sessions'][0].response.closed
        assert state['owner'].inflight is False and not state['owner'].dispatch_lock.locked()
        before_second, row = _forward_persisted_proof(state, expected)
        context.emit('ovl_forward_outcome', expected, evidence='SIMULATED', attempts=1)
        context.emit('ovl_forward_receipt', 'POSITIVE' if expected == 'sent' else 'UNKNOWN', evidence='SIMULATED',
                     count=1 if expected == 'sent' else 0)
        context.emit('ovl_forward_alias', 'PROVEN' if expected == 'sent' else 'ABSENT', evidence='SIMULATED',
                     count=1 if expected == 'sent' else 0)
        if case == 'forward_timeout_no_retry':
            context.emit('ovl_forward_second_tick', 'BEGIN', evidence='SIMULATED')
            second = state['forward_target'](*state['forward_prepared']['args'], **state['forward_prepared']['kwargs'])
            assert second == {'state': 'idle'}
            assert state['post_count'] == len(state['sessions']) == 1
            assert before_second == _snapshot(state)
            assert state['owner'].inflight is False and not state['owner'].dispatch_lock.locked()
            context.emit('ovl_forward_second_tick', 'idle', evidence='SIMULATED')
        context.emit('ovl_forward_preservation', 'UNCHANGED', evidence='SIMULATED')
        context.emit('ovl_forward_posts', 'COUNTED', evidence='SIMULATED', count=state['post_count'])
        context.emit('ovl_forward_native', 'SIMULATED_ONLY', evidence='SIMULATED', count=0)
    finally:
        _cleanup(state)
    context.emit('ovl_forward_cleanup', 'RESTORED', evidence='SIMULATED')


OWNER_REPLY_SCHEMA = 'route-probe.ovl-owner-reply-fixture/v1'
OWNER_REPLY_CASES = frozenset({'owner_reply_success', 'owner_reply_timeout_no_retry'})


def _owner_reply_case(fixture):
    keys = {'schema', 'case', 'route', 'evidence', 'entry', 'opaque_modules',
            'include_modules', 'include_entries', 'capture_mode', 'trace_modules', 'max_trace_events'}
    if (type(fixture) is not dict or set(fixture) != keys
            or fixture.get('schema') != OWNER_REPLY_SCHEMA or type(fixture.get('case')) is not str
            or fixture['case'] not in OWNER_REPLY_CASES or fixture.get('route') != 'owner_private'
            or fixture.get('evidence') != 'SIMULATED' or fixture.get('entry') != FORWARD_ENTRY
            or fixture.get('opaque_modules') != ['app.core.config']
            or fixture.get('max_trace_events') != 5000):
        raise ValueError('ovl_owner_reply_fixture_invalid')
    return fixture['case']


def _bootstrap_owner_reply(fixture, context):
    _owner_reply_case(fixture)
    return bootstrap(_admission_precondition(), context)


def _cleanup_owner_reply(state):
    try:
        if state.get('owner_reply_listener_installed'):
            from sqlalchemy import event
            event.remove(state['engine'], 'commit', state['owner_reply_listener'])
            state['owner_reply_listener_installed'] = False
    finally:
        try:
            for session in state.get('reply_sessions', []):
                if session.response is not None:
                    session.response.close()
                session.close()
        finally:
            _cleanup(state)


class _OwnerReplyResponse:
    status_code = 200

    def __init__(self, state, phase):
        self.state, self.phase, self.closed = state, phase, False

    def iter_content(self, chunk_size=1):
        assert chunk_size == 1
        self.state['context'].emit('ovl_owner_reply_response', self.phase + '.STREAMED', evidence='SIMULATED')
        raw = json.dumps(dict(ok=True, result=dict(message_id=800 if self.phase == 'seed' else 801,
            chat=dict(id=self.state['composition'].OWNER if self.phase == 'seed' else
                      self.state['original_event']['message']['chat']['id'], type='private')))).encode()
        for index in range(len(raw)):
            yield raw[index:index+1]

    def close(self):
        self.closed = True


class _OwnerReplySession:
    def __init__(self, state):
        self.state, self.phase, self.closed = state, state['reply_phase'], False
        assert self.phase in {'seed', 'selected'}
        self.trust_env, self.auth = True, 'SIMULATED_INITIAL_AUTH'
        self.proxies = {}
        self.cookies = SimpleNamespace(clear=lambda: None)
        self.retry_total, self.response = None, None

    def mount(self, prefix, adapter):
        assert prefix == 'https://'
        self.retry_total = adapter.max_retries.total
        assert self.retry_total == 0

    def post(self, url, **kwargs):
        state, phase = self.state, self.phase
        method = 'forwardMessage' if phase == 'seed' else 'sendMessage'
        assert url == 'https://api.telegram.org/bot' + _SYNTHETIC_FORWARD_TOKEN + '/' + method
        assert set(kwargs) == {'data', 'headers', 'timeout', 'allow_redirects', 'stream', 'verify'}
        assert type(kwargs['data']) is bytes
        resident = state['original_event']['message']
        expected_wire = (dict(chat_id=state['composition'].OWNER, from_chat_id=resident['chat']['id'],
                              message_id=resident['message_id']) if phase == 'seed' else
            dict(chat_id=resident['chat']['id'], text=state['owner_event']['message']['text'],
                 reply_parameters=dict(message_id=resident['message_id'], allow_sending_without_reply=False)))
        assert json.loads(kwargs['data']) == expected_wire
        assert kwargs['headers'] == {'Content-Type': 'application/json', 'Accept': 'application/json'}
        assert kwargs['timeout'] == (5.0, 15.0) and kwargs['allow_redirects'] is False
        assert kwargs['stream'] is True and kwargs['verify'] is True
        assert self.trust_env is False and self.auth is None and self.proxies == {} and self.retry_total == 0
        assert state['owner'].inflight is True
        key = state['seed_key'] if phase == 'seed' else state['selected_key']
        from sqlalchemy import select
        with state['factory']() as db:
            row = db.execute(select(state['ledger'].effects).where(
                state['ledger'].effects.c.operation_key == key)).mappings().one()
            assert row['state'] == 'sending' and row['attempts'] == 1
            assert row['claim_owner_id'] == state['owner'].owner_id and row['claim_epoch'] == state['owner'].epoch
        committed = state['reply_commits'][-1]['effects'][key]
        assert committed == dict(state='sending', attempts=1, receipt=False, projection='pending' if phase == 'selected' else None)
        state['reply_posts'][phase] += 1
        state['reply_post_total'] += 1
        assert state['reply_posts'][phase] == 1 and state['reply_post_total'] <= 2
        state['context'].emit('ovl_owner_reply_post', phase + '.ATTEMPTED', evidence='SIMULATED',
                              count=state['reply_post_total'])
        if phase == 'selected' and state['owner_reply_case'] == 'owner_reply_timeout_no_retry':
            from requests import ReadTimeout
            state['reply_http_failure'] = ReadTimeout()
            raise state['reply_http_failure']
        self.response = _OwnerReplyResponse(state, phase)
        return self.response

    def close(self):
        self.closed = True


def _prepare_owner_reply_prerequisite(target, fixture, context):
    case = _owner_reply_case(fixture)
    runtime = context.load_module('app.ingest.telegram_owner_private_runtime')
    if target is not runtime.dispatch_once:
        raise ValueError('ovl_owner_reply_target_invalid')
    composition = context.load_module('app.ingest.telegram_owner_private_composition')
    state = None
    try:
        args = prepare(composition.accept_webhook, _admission_precondition(), context)
        state = context.ovl_state
        assert composition.accept_webhook(*args['args'], **args['kwargs']) == ACCEPTED
        state['db'].commit()
        _persisted_proof(state)
        state['db'].close()
        state['db'] = None
        before = _snapshot(state)
        state.update(owner_reply_case=case, reply_phase='seed', reply_posts=dict(seed=0, selected=0),
            reply_post_total=0, reply_sessions=[], reply_commits=[], owner_reply_listener_installed=False,
            resident_before_seed=before, seed_key=before[state['ledger'].effects.name][0]['operation_key'],
            selected_key=None, reply_target=target)
        state['owner'] = _SimulatedForwardOwner(state)
        from sqlalchemy import event, select
        def record_commit(connection):
            rows = connection.execute(select(state['ledger'].effects)).mappings().all()
            aliases = connection.execute(select(state['ledger'].aliases)).mappings().all()
            assert 1 <= len(rows) <= 2 and len(aliases) <= 1
            summary = {row['operation_key']: dict(state=row['state'], attempts=row['attempts'],
                       receipt=row['receipt_json'] is not None, projection=row['projection_state']) for row in rows}
            state['reply_commits'].append(dict(phase=state['reply_phase'], effects=summary, aliases=len(aliases)))
            key = state['selected_key'] if state['reply_phase'] != 'seed' else state['seed_key']
            selected = summary.get(key)
            if selected is None:
                code = 'NO_SELECTED'
            else:
                assert selected['state'] in {'queued', 'sending', 'sent', 'unknown'}
                assert selected['projection'] in {None, 'pending', 'done'}
                code = selected['state'] + '.' + (selected['projection'] or 'none')
            context.emit('ovl_owner_reply_commit', state['reply_phase'] + '.' + code,
                         evidence='SIMULATED', count=len(aliases))
        state['owner_reply_listener'] = record_commit
        event.listen(state['engine'], 'commit', record_commit)
        state['owner_reply_listener_installed'] = True
        native = context.load_module('app.ingest.telegram_basic_native_transport')
        def session_factory():
            session = _OwnerReplySession(state)
            state['reply_sessions'].append(session)
            return session
        state['transport'] = native.BasicNativeTransport(None, session_factory=session_factory,
            authority_check=state['owner'].check)
        state['reply_prepared'] = dict(args=[state['factory'], state['owner'], state['transport']], kwargs={})
        result = target(*state['reply_prepared']['args'], **state['reply_prepared']['kwargs'])
        assert result == dict(state='sent', operation_key=state['seed_key'], native_receipt_saved=True)
        state['seed_snapshot'] = _snapshot(state)
        _prove_owner_reply_seed_bridge(state)
        ledger = state['ledger']
        with state['factory']() as db:
            alias_row = db.execute(select(ledger.aliases)).mappings().one()
            state['seed_parent'] = int(alias_row['native_message_id'])
            parent = dict(message_id=state['seed_parent'], **{'from': dict(id=composition.BOT, is_bot=True)})
            alias = context.load_module('app.ingest.telegram_owner_private_forwarding').prove_owner_alias(
                db, state['current_route'], parent)
            assert alias.operation_key == state['seed_key']
        assert state['reply_posts'] == dict(seed=1, selected=0) and state['reply_post_total'] == 1
        assert len(state['reply_sessions']) == 1 and state['reply_sessions'][0].closed
        context.emit('ovl_owner_reply_seed', 'SENT_ALIAS_PROVEN', evidence='SIMULATED', count=1)
        return state
    except BaseException:
        if state is not None:
            _cleanup_owner_reply(state)
        raise


def _native_owner_reply_event(state):
    composition = state['composition']
    return dict(update_id=900004, message=dict(message_id=701, date=1767225660,
        chat=dict(id=composition.OWNER, type='private'),
        **{'from': dict(id=composition.OWNER, is_bot=False, first_name='Synthetic owner')},
        text='Synthetic native owner response',
        reply_to_message=dict(message_id=state['seed_parent'],
                              **{'from': dict(id=composition.BOT, is_bot=True)})))


def _admit_native_owner_reply(state, event):
    from sqlalchemy import select
    state['reply_phase'] = 'admission'
    with state['factory']() as db:
        result = state['composition'].accept_webhook(db, state['current_route'], event)
        keys = db.execute(select(state['ledger'].effects.c.operation_key).where(
            state['ledger'].effects.c.operation_key != state['seed_key'])).scalars().all()
        assert len(keys) <= 1
        state['selected_key'] = keys[0] if keys else None
        db.commit()
    return result


def _owner_reply_admission_proof(state):
    from sqlalchemy import select
    ledger, composition = state['ledger'], state['composition']
    presentation = state['context'].load_module('app.ingest.telegram_owner_private_presentation')
    snapshot = _snapshot(state)
    assert len(snapshot[composition.inbox.name]) == len(snapshot[state['message'].name]) == len(snapshot[ledger.effects.name]) == 2
    assert len(snapshot[ledger.facts.name]) == len(snapshot[ledger.aliases.name]) == 1
    added = _prove_owner_reply_admission_bridge(state, snapshot)
    with state['factory']() as db:
        row = dict(db.execute(select(ledger.effects).where(ledger.effects.c.operation_key == state['selected_key'])).mappings().one())
        plan = ledger._plan(json.loads(row['plan_json']))
        assert type(plan) is presentation.VersionedEffectPlan and plan.kind == 'owner_reply'
        meta = presentation.presentation(plan)
        assert meta['version'] == 2 and meta['body_field'] == 'text' and meta['actor_namespace'] == 'telegram_user'
        assert meta['actor_snapshot']['id'] == composition.OWNER and meta['owner_native_message_id'] == 701
        assert plan.wire == dict(method='sendMessage', chat_id=state['original_event']['message']['chat']['id'],
            text=state['owner_event']['message']['text'], reply_parameters=dict(
                message_id=state['original_event']['message']['message_id'], allow_sending_without_reply=False))
        assert row['state'] == 'queued' and row['attempts'] == 0 and row['receipt_json'] is None
        assert row['projection_state'] == 'pending' and row['actor_user_id'] is None
        ref = state['route_module'].PhysicalRef(**json.loads(row['projection_ref_json']))
        projected = composition.read_physical(db, ref)
        assert added[ledger.effects.name][0] == row
        assert added[state['message'].name][0] == projected
        presentation.validate_projection_source(state['current_route'], plan, row, ref, projected,
                                                owner_event=state['owner_event'])
        assert composition.OwnerPrivateStore(db).owner_reply(state['current_route'], state['owner_event']) == plan
        owner_rows = [r for r in snapshot[composition.inbox.name] if r['role'] == 'OWNER_REPLY']
        assert len(owner_rows) == 1 and owner_rows[0]['state'] == 'projected'
        assert owner_rows[0]['payload_json'] == ledger.dumps(state['owner_event'])
        assert owner_rows[0]['payload_digest'] == state['route_module'].digest(state['owner_event'])
        assert added[composition.inbox.name] == owner_rows
        return ref


def _prepare_owner_reply(target, fixture, context):
    state = _prepare_owner_reply_prerequisite(target, fixture, context)
    try:
        state['owner_event'] = _native_owner_reply_event(state)
        result = _admit_native_owner_reply(state, state['owner_event'])
        assert result == dict(status='accepted', duplicate=False, role='OWNER_REPLY', state='projected')
        state['reply_projection_ref'] = _owner_reply_admission_proof(state)
        state['reply_before_selected'] = _snapshot(state)
        state['reply_phase'] = 'selected'
        context.emit('ovl_owner_reply_ready', 'QUEUED_PROJECTION_PROVEN', evidence='SIMULATED', count=1)
        return state['reply_prepared']
    except BaseException:
        _cleanup_owner_reply(state)
        raise


def _owner_reply_delivery_proof(state, expected):
    from sqlalchemy import select
    ledger, composition = state['ledger'], state['composition']
    snapshot = _snapshot(state)
    before = state['reply_before_selected']
    for table in (composition.inbox, ledger.facts, ledger.aliases):
        assert snapshot[table.name] == before[table.name]
    effects_by_key = {row['operation_key']: row for row in snapshot[ledger.effects.name]}
    baseline_by_key = {row['operation_key']: row for row in before[ledger.effects.name]}
    assert set(effects_by_key) == set(baseline_by_key) == {state['seed_key'], state['selected_key']}
    assert effects_by_key[state['seed_key']] == baseline_by_key[state['seed_key']]
    row, baseline = effects_by_key[state['selected_key']], baseline_by_key[state['selected_key']]
    allowed = {'state', 'attempts', 'receipt_json', 'claim_owner_id', 'claim_epoch', 'projection_state'}
    assert {k:v for k,v in row.items() if k not in allowed} == {k:v for k,v in baseline.items() if k not in allowed}
    assert row['state'] == expected and row['attempts'] == 1 and row['projection_state'] == 'done'
    assert row['claim_owner_id'] == state['owner'].owner_id and row['claim_epoch'] == state['owner'].epoch
    receipt = json.loads(row['receipt_json'])
    assert receipt == dict(state=expected, native_ids=[801] if expected == 'sent' else [],
                           category=None if expected == 'sent' else 'response_invalid')
    if expected == 'unknown':
        from requests import ReadTimeout
        assert type(state.get('reply_http_failure')) is ReadTimeout
    ref = state['reply_projection_ref']
    old_messages = {r['id']: r for r in before[state['message'].name]}
    new_messages = {r['id']: r for r in snapshot[state['message'].name]}
    assert set(old_messages) == set(new_messages)
    for key in old_messages:
        old, new = old_messages[key], new_messages[key]
        if key != ref.message_id:
            assert old == new
            continue
        assert {k:v for k,v in old.items() if k not in {'metadata', 'updated_at'}} == {
            k:v for k,v in new.items() if k not in {'metadata', 'updated_at'}}
        if new['updated_at'] != old['updated_at']:
            assert state['message'].c.updated_at.onupdate is not None
            assert str(state['message'].c.updated_at.onupdate.arg) == 'now()'
            assert composition.utc(new['updated_at']) >= composition.utc(old['updated_at'])
        expected_metadata = {**old['metadata'], 'owner_private_delivery_state': expected}
        if expected == 'sent':
            expected_metadata['owner_private_native_receipts'] = [801]
        assert new['metadata'] == expected_metadata
    # Receipt and projection must be separate ORIGINAL transactions.
    selected_commits = [item['effects'][state['selected_key']] for item in state['reply_commits']
                       if item['phase'] == 'selected']
    assert selected_commits == [dict(state='queued', attempts=0, receipt=False, projection='pending'),
        dict(state='sending', attempts=1, receipt=False, projection='pending'),
        dict(state=expected, attempts=1, receipt=True, projection='pending'),
        dict(state=expected, attempts=1, receipt=True, projection='done')]
    with state['factory']() as db:
        assert composition.read_physical(db, ref)['metadata'] == new_messages[ref.message_id]['metadata']
    return snapshot


def _observe_owner_reply(result, exception, fixture, context):
    case, state = _owner_reply_case(fixture), context.ovl_state
    expected = 'sent' if case == 'owner_reply_success' else 'unknown'
    try:
        assert exception is None
        assert result == dict(state=expected, operation_key=state['selected_key'], native_receipt_saved=True)
        assert state['reply_posts'] == dict(seed=1, selected=1) and state['reply_post_total'] == 2
        assert len(state['reply_sessions']) == 2
        assert all(s.closed and s.retry_total == 0 and (s.response is None or s.response.closed)
                   for s in state['reply_sessions'])
        assert state['owner'].inflight is False and not state['owner'].dispatch_lock.locked()
        after = _owner_reply_delivery_proof(state, expected)
        context.emit('ovl_owner_reply_outcome', expected, evidence='SIMULATED', attempts=1)
        context.emit('ovl_owner_reply_receipt', 'POSITIVE' if expected == 'sent' else 'UNKNOWN',
                     evidence='SIMULATED', count=1 if expected == 'sent' else 0)
        context.emit('ovl_owner_reply_projection', expected + '.done', evidence='SIMULATED')
        context.emit('ovl_owner_reply_seed_preservation', 'UNCHANGED', evidence='SIMULATED', count=1)
        if case == 'owner_reply_timeout_no_retry':
            context.emit('ovl_owner_reply_second_tick', 'BEGIN', evidence='SIMULATED')
            state['reply_phase'] = 'second'
            second = state['reply_target'](*state['reply_prepared']['args'], **state['reply_prepared']['kwargs'])
            assert second == {'state': 'idle'}
            assert state['reply_posts'] == dict(seed=1, selected=1) and state['reply_post_total'] == 2
            assert len(state['reply_sessions']) == 2 and after == _snapshot(state)
            assert state['owner'].inflight is False and not state['owner'].dispatch_lock.locked()
            context.emit('ovl_owner_reply_second_tick', 'idle', evidence='SIMULATED')
        context.emit('ovl_owner_reply_preservation', 'UNCHANGED', evidence='SIMULATED')
        context.emit('ovl_owner_reply_posts', 'seed1.selected1', evidence='SIMULATED', count=state['reply_post_total'])
        context.emit('ovl_owner_reply_native', 'SIMULATED_ONLY', evidence='SIMULATED', count=0)
    finally:
        _cleanup_owner_reply(state)
    context.emit('ovl_owner_reply_cleanup', 'RESTORED', evidence='SIMULATED')


def _prove_owner_reply_seed_bridge(state):
    """P08d-only queued resident -> saved seed receipt; no old-row drift."""
    from dataclasses import asdict
    ledger, before, after = state['ledger'], state['resident_before_seed'], state['seed_snapshot']
    for table in (state['composition'].inbox, ledger.facts, state['message']):
        assert after[table.name] == before[table.name]
    assert len(before[ledger.effects.name]) == len(after[ledger.effects.name]) == 1
    old, row = before[ledger.effects.name][0], after[ledger.effects.name][0]
    allowed = {'state', 'attempts', 'receipt_json', 'claim_owner_id', 'claim_epoch'}
    assert {k:v for k,v in old.items() if k not in allowed} == {k:v for k,v in row.items() if k not in allowed}
    assert old['operation_key'] == row['operation_key'] == state['seed_key']
    assert row['state'] == 'sent' and row['attempts'] == 1
    assert row['claim_owner_id'] == state['owner'].owner_id and row['claim_epoch'] == state['owner'].epoch
    assert json.loads(row['receipt_json']) == dict(state='sent', native_ids=[800], category=None)
    assert before[ledger.aliases.name] == [] and len(after[ledger.aliases.name]) == 1
    plan = ledger._plan(json.loads(row['plan_json']))
    expected = state['route_module'].mirror_alias(state['current_route'], plan,
        dict(ok=True, result=dict(message_id=800)), attempt_state='sending')
    alias_row = after[ledger.aliases.name][0]
    assert alias_row == dict(tenant_id=plan.tenant_id, bot_id=str(plan.bot_id), target_kind='owner_private',
        owner_user_id=str(plan.destination_user_id), native_message_id='800', operation_key=plan.operation_key,
        source_key=plan.resident.key, alias_json=ledger.dumps(asdict(expected)))
    assert ledger._alias(json.loads(alias_row['alias_json'])) == expected


def _prove_owner_reply_admission_bridge(state, snapshot):
    """P08d-only addition of three owner rows; every previous full row retained."""
    before, ledger = state['seed_snapshot'], state['ledger']
    added = {}
    for table in state['tables']:
        keys = [column.name for column in table.primary_key.columns]
        if table is state['message']:
            keys += [name for name in ('tenant_id', 'source_created_at', 'message_uid') if name not in keys]
        old = {tuple(row[key] for key in keys): row for row in before[table.name]}
        current = {tuple(row[key] for key in keys): row for row in snapshot[table.name]}
        assert len(old) == len(before[table.name]) and len(current) == len(snapshot[table.name])
        assert old.keys() <= current.keys()
        assert all(current[key] == row for key, row in old.items())
        added[table.name] = [row for key, row in current.items() if key not in old]
        expected = 0 if table is ledger.facts or table is ledger.aliases else 1
        assert len(added[table.name]) == expected
    return added


PLATFORM_SCHEMA = 'route-probe.ovl-platform-text-fixture/v1'
PLATFORM_ENTRY = 'app.ingest.telegram_owner_private_platform:enqueue'
PLATFORM_CASES = frozenset({'platform_primary_sent_owner_echo_unknown',
                            'platform_primary_unknown_echo_not_staged'})
_PLATFORM_ACTOR = 9001001
_PLATFORM_TEXT = 'Synthetic platform text response'
_PLATFORM_ACTION = 'route-probe-ovl-platform-v2'


def _platform_case(fixture):
    keys = {'schema', 'case', 'route', 'evidence', 'entry', 'opaque_modules',
            'include_modules', 'include_entries', 'capture_mode', 'trace_modules', 'max_trace_events'}
    if (type(fixture) is not dict or set(fixture) != keys
            or fixture.get('schema') != PLATFORM_SCHEMA or type(fixture.get('case')) is not str
            or fixture['case'] not in PLATFORM_CASES or fixture.get('route') != 'owner_private'
            or fixture.get('evidence') != 'SIMULATED' or fixture.get('entry') != PLATFORM_ENTRY
            or fixture.get('opaque_modules') != ['app.core.config']
            or fixture.get('max_trace_events') != 5000):
        raise ValueError('ovl_platform_fixture_invalid')
    return fixture['case']


def _bootstrap_platform(fixture, context):
    _platform_case(fixture)
    stubs = bootstrap(_admission_precondition(), context)
    # New original ticket-linking logger needs this fixed synthetic name.
    # BasicRoot decision remains its genuine fresh-child default None.
    stubs['app.core.config'].settings.service_name = 'route-probe-ovl-platform-synthetic'
    stubs['app.core.config'].settings.telegram_basic_case_tasks_enabled = False
    return stubs


def _platform_seed_fixture():
    return dict(schema=OWNER_REPLY_SCHEMA, case='owner_reply_success', route='owner_private',
        evidence='SIMULATED', entry=FORWARD_ENTRY, opaque_modules=['app.core.config'],
        include_modules=[], include_entries=[], capture_mode='PARTIAL_STATIC',
        trace_modules=[], max_trace_events=5000)


def _platform_acl_snapshot(state):
    from sqlalchemy import select
    with state['factory']() as db:
        return {table.name: [dict(row) for row in db.execute(select(table).order_by(*table.primary_key.columns)).mappings()]
                for table in state['platform_acl_tables']}


def _platform_effects(state, connection=None):
    from sqlalchemy import select
    if connection is not None:
        return [dict(row) for row in connection.execute(select(state['ledger'].effects)).mappings()]
    with state['factory']() as db:
        return [dict(row) for row in db.execute(select(state['ledger'].effects)).mappings()]


def _cleanup_platform(state):
    try:
        if state.get('platform_listener_installed'):
            from sqlalchemy import event
            event.remove(state['engine'], 'commit', state['platform_listener'])
            state['platform_listener_installed'] = False
    finally:
        try:
            for session in state.get('platform_sessions', []):
                if session.response is not None:
                    session.response.close()
                session.close()
        finally:
            _cleanup_owner_reply(state)


class _PlatformResponse:
    status_code = 200

    def __init__(self, state):
        self.state, self.closed = state, False

    def iter_content(self, chunk_size=1):
        assert chunk_size == 1
        self.state['context'].emit('ovl_platform_response', 'primary.STREAMED', evidence='SIMULATED')
        raw = json.dumps(dict(ok=True, result=dict(message_id=801))).encode()
        for index in range(len(raw)):
            yield raw[index:index+1]

    def close(self):
        self.closed = True


class _PlatformSession:
    def __init__(self, state):
        self.state, self.phase, self.closed = state, state['platform_phase'], False
        assert self.phase in {'primary', 'echo'}
        self.trust_env, self.auth = True, 'SIMULATED_INITIAL_AUTH'
        self.proxies = {}
        self.cookies = SimpleNamespace(clear=lambda: None)
        self.retry_total, self.response = None, None

    def mount(self, prefix, adapter):
        assert prefix == 'https://'
        self.retry_total = adapter.max_retries.total
        assert self.retry_total == 0

    def post(self, url, **kwargs):
        state, phase = self.state, self.phase
        assert url == 'https://api.telegram.org/bot' + _SYNTHETIC_FORWARD_TOKEN + '/sendMessage'
        assert set(kwargs) == {'data', 'headers', 'timeout', 'allow_redirects', 'stream', 'verify'}
        assert type(kwargs['data']) is bytes
        resident = state['original_event']['message']
        if phase == 'primary':
            expected = dict(chat_id=resident['chat']['id'], text=_PLATFORM_TEXT,
                reply_parameters=dict(message_id=resident['message_id'], allow_sending_without_reply=False))
            key = state['platform_primary_key']
        else:
            expected = {k:v for k,v in state['platform_expected_echo'].wire.items() if k != 'method'}
            assert expected['chat_id'] == state['composition'].OWNER and expected['parse_mode'] == 'HTML'
            assert expected['reply_parameters'] == dict(message_id=state['seed_parent'], allow_sending_without_reply=False)
            key = state['platform_echo_key']
        assert json.loads(kwargs['data']) == expected
        assert kwargs['headers'] == {'Content-Type': 'application/json', 'Accept': 'application/json'}
        assert kwargs['timeout'] == (5.0, 15.0) and kwargs['allow_redirects'] is False
        assert kwargs['stream'] is True and kwargs['verify'] is True
        assert self.trust_env is False and self.auth is None and self.proxies == {} and self.retry_total == 0
        assert state['owner'].inflight is True
        row = next(row for row in _platform_effects(state) if row['operation_key'] == key)
        assert row['state'] == 'sending' and row['attempts'] == 1
        assert row['claim_owner_id'] == state['owner'].owner_id and row['claim_epoch'] == state['owner'].epoch
        committed = state['platform_commits'][-1]['effects'][key]
        assert committed == dict(state='sending', attempts=1, receipt=False, projection='pending')
        state['platform_posts'][phase] += 1
        state['reply_post_total'] += 1  # Keep the genuine prerequisite seed POST in global count.
        assert state['platform_posts'][phase] == 1
        assert state['reply_post_total'] == sum(state['platform_posts'].values())
        state['context'].emit('ovl_platform_post', phase + '.ATTEMPTED', evidence='SIMULATED', count=state['reply_post_total'])
        if phase == 'echo' or state['platform_case'] == 'platform_primary_unknown_echo_not_staged':
            from requests import ReadTimeout
            state['platform_http_failure'] = ReadTimeout()
            raise state['platform_http_failure']
        self.response = _PlatformResponse(state)
        return self.response

    def close(self):
        self.closed = True


def _prepare_platform(target, fixture, context):
    case = _platform_case(fixture)
    platform = context.load_module('app.ingest.telegram_owner_private_platform')
    if target is not platform.enqueue:
        raise ValueError('ovl_platform_target_invalid')
    runtime = context.load_module('app.ingest.telegram_owner_private_runtime')
    state = _prepare_owner_reply_prerequisite(runtime.dispatch_once, _platform_seed_fixture(), context)
    try:
        from sqlalchemy import event, select
        # The accepted two-effect listener is removed by exact owned identity.
        event.remove(state['engine'], 'commit', state['owner_reply_listener'])
        state['owner_reply_listener_installed'] = False
        state.update(platform_case=case, platform=platform, platform_phase='enqueue',
            platform_posts=dict(seed=state['reply_posts']['seed'], primary=0, echo=0),
            platform_sessions=[], platform_commits=[], platform_listener_installed=False,
            platform_dispatches=['seed'], platform_primary_key=None, platform_echo_key=None,
            platform_projection_cuts=[])
        assert state['platform_posts'] == dict(seed=1, primary=0, echo=0) and state['reply_post_total'] == 1
        models = context.load_module('app.models')
        state['platform_acl_tables'] = (models.User.__table__, models.Ticket.__table__, models.TicketMessage.__table__)
        with state['factory']() as db:
            db.add(models.User(id=_PLATFORM_ACTOR, tenant_id='vladivostok', username='route-probe-ovl-operator',
                first_name='Synthetic', last_name='Operator', email='synthetic-ovl-operator@example.invalid',
                role='operator', enabled=True, access_mode='legacy', access_status='active',
                global_login=False, external_ids={}))
            db.commit()
            actor = db.get(models.User, _PLATFORM_ACTOR)
            assert not any(name in actor.__dict__ for name in (
                '_resolved_access_scope', '_active_workspace_key', '_active_workspace_management_company_id',
                '_active_contour_id', '_root_legacy_account', '_root_legacy_tenant_id', '_root_legacy_contour_ids'))
        state['platform_acl_before'] = _platform_acl_snapshot(state)
        assert len(state['platform_acl_before'][models.User.__table__.name]) == 1
        assert state['platform_acl_before'][models.Ticket.__table__.name] == []
        assert state['platform_acl_before'][models.TicketMessage.__table__.name] == []
        state['platform_before_enqueue'] = _snapshot(state)
        assert state['platform_before_enqueue'] == state['seed_snapshot']
        def record_commit(connection):
            rows = _platform_effects(state, connection)
            assert 1 <= len(rows) <= 3
            summary = {row['operation_key']: dict(state=row['state'], attempts=row['attempts'],
                receipt=row['receipt_json'] is not None, projection=row['projection_state']) for row in rows}
            state['platform_commits'].append(dict(phase=state['platform_phase'], effects=summary))
            key = state['platform_echo_key'] if state['platform_phase'] == 'echo' else state['platform_primary_key']
            item = summary.get(key)
            if item is not None:
                assert item['state'] in {'queued', 'sending', 'sent', 'unknown'} and item['projection'] in {'pending', 'done'}
                context.emit('ovl_platform_commit', state['platform_phase'] + '.' + item['state'] + '.' + item['projection'],
                             evidence='SIMULATED', count=len(rows))
            if (state['platform_phase'] == 'primary' and item is not None and item['projection'] == 'done'
                    and state['platform_echo_key'] not in summary):
                ref = state['platform_projection_ref']
                projected = connection.execute(select(state['message']).where(
                    state['message'].c.id == ref.message_id)).mappings().one()
                state['platform_projection_cuts'].append(dict(projected))
        state['platform_listener'] = record_commit
        event.listen(state['engine'], 'commit', record_commit)
        state['platform_listener_installed'] = True
        native = context.load_module('app.ingest.telegram_basic_native_transport')
        def session_factory():
            session = _PlatformSession(state)
            state['platform_sessions'].append(session)
            return session
        state['platform_transport'] = native.BasicNativeTransport(None, session_factory=session_factory,
            authority_check=state['owner'].check)
        state['platform_runtime'] = runtime
        state['db'] = state['factory']()
        root = next(iter(state['seed_snapshot'][state['ledger'].facts.name]))
        fact = state['ledger']._fact(json.loads(root['fact_json']))
        state['platform_root_ref'] = fact.physical
        record = state['db'].get(models.Message, fact.physical.message_id)
        assert record.message_uid == fact.physical.message_uid
        assert state['composition'].utc(record.source_created_at) == state['composition'].utc(fact.physical.source_created_at)
        prepared = dict(args=[state['db'], record], kwargs=dict(actor_id=_PLATFORM_ACTOR,
            key=_PLATFORM_ACTION, text=_PLATFORM_TEXT, linked_ticket_ids=[], presentation_version=2))
        context.emit('ovl_platform_ready', 'ORM_OPERATOR_SEED_PROVEN', evidence='SIMULATED', count=1)
        return prepared
    except BaseException:
        _cleanup_platform(state)
        raise


def _platform_creation_proof(state):
    from sqlalchemy import select
    ledger, composition = state['ledger'], state['composition']
    snapshot, before = _snapshot(state), state['platform_before_enqueue']
    added = {}
    for table in state['tables']:
        keys = [column.name for column in table.primary_key.columns]
        if table is state['message']:
            keys += [name for name in ('tenant_id', 'source_created_at', 'message_uid') if name not in keys]
        old = {tuple(row[key] for key in keys): row for row in before[table.name]}
        current = {tuple(row[key] for key in keys): row for row in snapshot[table.name]}
        assert len(old) == len(before[table.name]) and len(current) == len(snapshot[table.name])
        assert old.keys() <= current.keys() and all(current[key] == row for key,row in old.items())
        added[table.name] = [row for key,row in current.items() if key not in old]
        assert len(added[table.name]) == (1 if table is ledger.effects or table is state['message'] else 0)
    assert _platform_acl_snapshot(state) == state['platform_acl_before']
    row = added[ledger.effects.name][0]
    assert row['operation_key'] == state['platform_primary_key']
    presentation = state['context'].load_module('app.ingest.telegram_owner_private_presentation')
    plan = ledger._plan(json.loads(row['plan_json']))
    assert type(plan) is presentation.VersionedEffectPlan and plan.kind == 'platform_reply'
    meta = presentation.presentation(plan)
    assert meta['version'] == 2 and meta['actor_namespace'] == 'platform_user'
    assert meta['actor_snapshot']['id'] == _PLATFORM_ACTOR and meta['original_body'] == _PLATFORM_TEXT
    resident = state['original_event']['message']
    assert plan.wire == dict(method='sendMessage', chat_id=resident['chat']['id'], text=_PLATFORM_TEXT,
        reply_parameters=dict(message_id=resident['message_id'], allow_sending_without_reply=False))
    assert row['actor_user_id'] == _PLATFORM_ACTOR and row['linked_ticket_ids_json'] == '[]'
    assert json.loads(row['selected_ref_json']) == dict(tenant_id=state['platform_root_ref'].tenant_id,
        message_id=state['platform_root_ref'].message_id, source_created_at=state['platform_root_ref'].source_created_at,
        message_uid=state['platform_root_ref'].message_uid)
    assert row['state'] == 'queued' and row['attempts'] == 0 and row['receipt_json'] is None
    assert row['projection_state'] == 'pending' and row['claim_owner_id'] is None and row['claim_epoch'] is None
    ref = state['route_module'].PhysicalRef(**json.loads(row['projection_ref_json']))
    with state['factory']() as db:
        projected = composition.read_physical(db, ref)
        assert added[state['message'].name] == [projected]
        presentation.validate_projection_source(state['current_route'], plan, row, ref, projected)
    state['platform_primary_plan'], state['platform_projection_ref'] = plan, ref
    state['platform_operator_initial'] = added[state['message'].name][0]
    state['platform_after_enqueue'] = snapshot
    return snapshot


def _platform_fresh_status(state):
    from sqlalchemy import select
    before, acl = _snapshot(state), _platform_acl_snapshot(state)
    models = state['context'].load_module('app.models')
    with state['factory']() as db:
        record = db.get(models.Message, state['platform_root_ref'].message_id)
        result = state['platform'].status(db, record, state['platform_operation_id'],
            actor_id=_PLATFORM_ACTOR, operation_key=state['platform_primary_key'])
    assert before == _snapshot(state) and acl == _platform_acl_snapshot(state)
    return result


def _platform_status_proof(status, resident, owner, overall):
    assert status['delivery_contract_version'] == 1
    assert status['delivery_state'] == status['status'] == resident
    assert status['sender_confirmed'] is (resident == 'delivered')
    assert status['overall_delivery_state'] == overall
    assert status['recipient_deliveries']['resident']['delivery_state'] == resident
    assert status['recipient_deliveries']['owner']['delivery_state'] == owner
    assert status['recipient_deliveries']['resident']['confirmed'] is (resident == 'delivered')
    assert status['recipient_deliveries']['owner']['confirmed'] is False
    if owner == 'pending':
        assert status['recipient_deliveries']['owner']['reason'] == 'not_staged'


def _platform_dispatch(state, phase):
    state['platform_phase'] = phase
    state['platform_dispatches'].append(phase)
    result = state['platform_runtime'].dispatch_once(state['factory'], state['owner'], state['platform_transport'])
    assert state['owner'].inflight is False and not state['owner'].dispatch_lock.locked()
    return result


def _platform_projection_metadata(state, row, summary):
    base = state['platform_operator_initial']
    assert {k:v for k,v in row.items() if k not in {'metadata', 'updated_at'}} == {
        k:v for k,v in base.items() if k not in {'metadata', 'updated_at'}}
    if row['updated_at'] != base['updated_at']:
        assert state['message'].c.updated_at.onupdate is not None
        assert str(state['message'].c.updated_at.onupdate.arg) == 'now()'
        assert state['composition'].utc(row['updated_at']) >= state['composition'].utc(base['updated_at'])
    resident = summary['recipient_deliveries']['resident']['delivery_state']
    expected = {**base['metadata'], 'owner_private_delivery_state': resident,
                'owner_private_delivery_summary': summary,
                'owner_private_native_receipts': [801] if resident == 'delivered' else []}
    assert row['metadata'] == expected


def _platform_saved_phase_proof(state, primary_state, echo_state):
    from dataclasses import asdict
    ledger, composition = state['ledger'], state['composition']
    snapshot, baseline = _snapshot(state), state['platform_after_enqueue']
    assert _platform_acl_snapshot(state) == state['platform_acl_before']
    for table in (composition.inbox, ledger.facts, ledger.aliases):
        assert snapshot[table.name] == baseline[table.name]
    rows = {row['operation_key']: row for row in snapshot[ledger.effects.name]}
    old = {row['operation_key']: row for row in baseline[ledger.effects.name]}
    required = {state['seed_key'], state['platform_primary_key']}
    if echo_state is not None:
        required.add(state['platform_echo_key'])
    assert set(rows) == required and rows[state['seed_key']] == old[state['seed_key']]
    primary, before = rows[state['platform_primary_key']], old[state['platform_primary_key']]
    allowed = {'state', 'attempts', 'receipt_json', 'claim_owner_id', 'claim_epoch', 'projection_state'}
    assert {k:v for k,v in primary.items() if k not in allowed} == {k:v for k,v in before.items() if k not in allowed}
    assert primary['state'] == primary_state and primary['attempts'] == 1 and primary['projection_state'] == 'done'
    assert primary['claim_owner_id'] == state['owner'].owner_id and primary['claim_epoch'] == state['owner'].epoch
    assert json.loads(primary['receipt_json']) == dict(state=primary_state,
        native_ids=[801] if primary_state == 'sent' else [], category=None if primary_state == 'sent' else 'response_invalid')
    alias = ledger._alias(json.loads(snapshot[ledger.aliases.name][0]['alias_json']))
    expected_echo = state['route_module'].plan_platform_owner_echo(state['current_route'], state['platform_primary_plan'], alias)
    state['platform_expected_echo'] = expected_echo
    if echo_state is not None:
        echo = rows[state['platform_echo_key']]
        fixed = dict(operation_key=expected_echo.operation_key, source_key=expected_echo.resident.key,
            tenant_id=expected_echo.tenant_id, bot_id=str(expected_echo.bot_id),
            plan_json=ledger.dumps(asdict(expected_echo)), intended_digest=expected_echo.intended_digest,
            generation=expected_echo.generation, route_fingerprint=expected_echo.route_fingerprint,
            projection_ref_json=primary['projection_ref_json'], projection_message_id=primary['projection_message_id'],
            projection_message_created_at=primary['projection_message_created_at'], projection_message_uid=primary['projection_message_uid'],
            actor_user_id=None, selected_ref_json=None, linked_ticket_ids_json=None)
        assert all(echo[key] == value for key,value in fixed.items())
        assert echo['state'] == echo_state and echo['created_at'] is not None
        assert echo['attempts'] == (0 if echo_state == 'queued' else 1)
        assert echo['projection_state'] == ('pending' if echo_state == 'queued' else 'done')
        assert echo['claim_owner_id'] == (None if echo_state == 'queued' else state['owner'].owner_id)
        assert echo['claim_epoch'] == (None if echo_state == 'queued' else state['owner'].epoch)
        assert echo['receipt_json'] is None if echo_state == 'queued' else json.loads(echo['receipt_json']) == dict(
            state='unknown', native_ids=[], category='response_invalid')
        if echo_state == 'unknown':
            allowed_echo = {'state', 'attempts', 'receipt_json', 'claim_owner_id', 'claim_epoch', 'projection_state'}
            assert {k:v for k,v in echo.items() if k not in allowed_echo} == {
                k:v for k,v in state['platform_echo_initial'].items() if k not in allowed_echo}
        else:
            state['platform_echo_initial'] = dict(echo)
    status = _platform_fresh_status(state)
    _platform_status_proof(status, 'delivered' if primary_state == 'sent' else 'unknown',
        'queued' if echo_state == 'queued' else 'unknown' if echo_state == 'unknown' else 'pending',
        'partial' if primary_state == 'sent' else 'unknown')
    messages = {row['id']: row for row in snapshot[state['message'].name]}
    originals = {row['id']: row for row in baseline[state['message'].name]}
    assert set(messages) == set(originals)
    for key in originals:
        if key != state['platform_projection_ref'].message_id:
            assert messages[key] == originals[key]
    assert len(state['platform_projection_cuts']) == 1
    cut = state['platform_projection_cuts'][0]
    outcomes = state['context'].load_module('app.ingest.telegram_owner_private_delivery_status')
    # Immediately after PRIMARY projection there was no echo row yet.
    projection_summary = outcomes.delivery_snapshot(state['current_route'], state['platform_primary_plan'], primary, alias, None)
    _platform_projection_metadata(state, cut, projection_summary)
    expected_summary = (outcomes.delivery_snapshot(state['current_route'], state['platform_primary_plan'], primary, alias,
        rows[state['platform_echo_key']]) if echo_state == 'unknown' else projection_summary)
    _platform_projection_metadata(state, messages[state['platform_projection_ref'].message_id], expected_summary)
    state['platform_status_cuts'].append(status)
    return snapshot


def _observe_platform(result, exception, fixture, context):
    case, state = _platform_case(fixture), context.ovl_state
    try:
        assert exception is None and type(result) is dict
        assert result['delivery_state'] == 'queued' and result['sender_confirmed'] is False
        assert result['recipient_deliveries']['resident']['delivery_state'] == 'queued'
        assert result['recipient_deliveries']['owner']['reason'] == 'not_staged'
        from sqlalchemy import select
        rows = state['db'].execute(select(state['ledger'].effects).where(
            state['ledger'].effects.c.operation_key != state['seed_key'])).mappings().all()
        assert len(rows) == 1
        state['platform_primary_key'] = rows[0]['operation_key']
        state['platform_echo_key'] = state['platform_primary_key'] + ':owner-echo'
        state['platform_operation_id'] = result['operation_id']
        state['db'].commit()
        state['db'].close()
        state['db'] = None
        _platform_creation_proof(state)
        state['platform_status_cuts'] = []
        context.emit('ovl_platform_enqueue', 'COMMITTED_TYPED_PRIMARY', evidence='SIMULATED', count=1)
        sent = case == 'platform_primary_sent_owner_echo_unknown'
        expected = 'sent' if sent else 'unknown'
        primary = _platform_dispatch(state, 'primary')
        assert primary == dict(state=expected, operation_key=state['platform_primary_key'], native_receipt_saved=True)
        after_primary = _platform_saved_phase_proof(state, expected, 'queued' if sent else None)
        context.emit('ovl_platform_primary', expected, evidence='SIMULATED', attempts=1)
        context.emit('ovl_platform_echo', 'queued' if sent else 'NOT_STAGED', evidence='SIMULATED')
        if sent:
            echo = _platform_dispatch(state, 'echo')
            assert echo == dict(state='unknown', operation_key=state['platform_echo_key'], native_receipt_saved=True)
            after = _platform_saved_phase_proof(state, 'sent', 'unknown')
            context.emit('ovl_platform_echo', 'unknown', evidence='SIMULATED', attempts=1)
        else:
            after = after_primary
        from requests import ReadTimeout
        assert type(state['platform_http_failure']) is ReadTimeout
        sessions = len(state['platform_sessions'])
        context.emit('ovl_platform_idle', 'BEGIN', evidence='SIMULATED')
        idle = _platform_dispatch(state, 'idle')
        assert idle == {'state': 'idle'} and after == _snapshot(state)
        assert _platform_acl_snapshot(state) == state['platform_acl_before']
        assert len(state['platform_sessions']) == sessions
        assert state['platform_dispatches'] == (['seed','primary','echo','idle'] if sent else ['seed','primary','idle'])
        assert state['platform_posts'] == dict(seed=1, primary=1, echo=1 if sent else 0)
        assert state['reply_post_total'] == (3 if sent else 2)
        assert all(session.closed and session.retry_total == 0 and (session.response is None or session.response.closed)
                   for session in state['platform_sessions'])
        final = _platform_fresh_status(state)
        _platform_status_proof(final, 'delivered' if sent else 'unknown', 'unknown' if sent else 'pending', 'partial' if sent else 'unknown')
        context.emit('ovl_platform_idle', 'idle', evidence='SIMULATED', count=len(state['platform_dispatches']))
        context.emit('ovl_platform_resident', final['delivery_state'], evidence='SIMULATED')
        context.emit('ovl_platform_owner', final['recipient_deliveries']['owner']['delivery_state'], evidence='SIMULATED')
        context.emit('ovl_platform_overall', final['overall_delivery_state'], evidence='SIMULATED')
        context.emit('ovl_platform_preservation', 'UNCHANGED', evidence='SIMULATED')
        context.emit('ovl_platform_posts', 'COUNTED', evidence='SIMULATED', count=state['reply_post_total'])
        context.emit('ovl_platform_native', 'SIMULATED_ONLY', evidence='SIMULATED', count=0)
    finally:
        _cleanup_platform(state)
    context.emit('ovl_platform_cleanup', 'RESTORED', evidence='SIMULATED')
