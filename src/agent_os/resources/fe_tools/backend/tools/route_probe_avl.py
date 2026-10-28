"""Explicit synthetic boundaries for unmodified 233f AVL transport replay.

No credentials, database, network or production settings are loaded here. The
engine installs the returned stubs before importing the pinned source bundle.
The selected callable is never replaced, wrapped, or compiled from edited AST.
"""
import json
from types import ModuleType, SimpleNamespace


CASES = frozenset({"success", "timeout", "connect", "proxy", "tls",
                   "malformed_json", "telegram400", "bridge_only_failure", "db_exception",
                   "db_commit_exception", "telegram403", "telegram429", "telegram5xx",
                   "dns", "broken_stream", "missing_receipt", "owner_loss",
                   "duplicate", "duplicate_conflict", "group_unknown", "preclaim_db",
                   "tcp", "wrapper_classification"})
TOKEN = "123456789:route_probe_synthetic"
BOT_ID = 123456789
GROUP_ID = -10012345
RESIDENT_ID = 12345
PARENT_ID = 700


def _case(fixture):
    if isinstance(fixture, dict) and fixture.get("stack_variant") == "canonical_v3":
        if (fixture.get("case") not in {"echo_unknown_primary_sent",
                "primary_post_timeout_no_retry", "binding_revoked_before_post"}
                or fixture.get("route", "platform_group") != "platform_group"):
            raise ValueError("route_probe_canonical_v3_fixture_invalid")
        return fixture["case"]
    if isinstance(fixture, dict) and fixture.get("stack_variant") == "canonical_v2":
        if fixture.get("case") not in CANONICAL_CASES or fixture.get("route", "platform_group") != "platform_group":
            raise ValueError("route_probe_canonical_fixture_invalid")
        return fixture["case"]
    if isinstance(fixture, dict) and fixture.get("stack_variant") == "requests_http":
        if fixture.get("case") not in HTTP_STACK_CASES or fixture.get("route", "platform_group") != "platform_group":
            raise ValueError("route_probe_http_fixture_invalid")
        return fixture["case"]
    if not isinstance(fixture, dict) or fixture.get("case") not in CASES:
        raise ValueError("route_probe_fixture_case_invalid")
    if fixture.get("route", "platform_group") != "platform_group":
        raise ValueError("route_probe_fixture_route_invalid")
    return fixture["case"]


def bootstrap(fixture, context):
    """Three declared, synthetic import boundaries; no target-function stub."""
    _case(fixture)
    config = ModuleType("app.core.config")
    config.settings = SimpleNamespace(external_effects_disabled=False,
        app_read_only_mode=False, telegram_basic_bot_enabled=True,
        database_url="sqlite:///:memory:", tenant_id="fixture_tenant")
    subscription = ModuleType("app.ingest.telegram_basic_subscription")

    def unused_subscription(*args, **kwargs):
        raise AssertionError("route_probe_subscription_path_not_selected")

    subscription.normalize_subscription = unused_subscription
    media = ModuleType("app.ingest.telegram_basic_media_policy")
    media.MAX_FILE_BYTES = 20 * 1024 * 1024
    context.emit("fixture_import_boundaries", "installed", evidence="SIMULATED",
                 module_count=2 if fixture.get("stack_variant") in {"canonical_v2", "canonical_v3"} else 3, production_settings=False)
    if fixture.get("stack_variant") in {"canonical_v2", "canonical_v3"}:
        config.settings.environment = "dev"
        config.settings.service_name = "route-probe-synthetic"
        config.settings.telegram_basic_case_tasks_enabled = False
        return {config.__name__: config, subscription.__name__: subscription}
    return {config.__name__: config, subscription.__name__: subscription, media.__name__: media}


class FixtureDatabaseError(RuntimeError):
    """Synthetic guard-read/commit error, not an observed PostgreSQL subtype."""


class FixtureClassificationError(RuntimeError):
    """Synthetic classifier fault inside the real one-attempt bridge wrapper."""


class FakeTransaction:
    """Test-only storage boundary. Never mistaken for the actual worker footer."""
    def __init__(self, context, *, fail=False):
        self.context, self.fail = context, fail
        self.commits = self.rollbacks = 0

    def commit(self):
        self.context.emit("database_commit", "attempted", evidence="SIMULATED")
        if self.fail:
            raise FixtureDatabaseError()
        self.commits += 1
        self.context.emit("database_commit", "completed", evidence="SIMULATED")

    def rollback(self):
        self.rollbacks += 1
        self.context.emit("database_rollback", "completed", evidence="SIMULATED")


class _Response:
    def __init__(self, case, context):
        self.case, self.context = case, context
        self.status_code = {"telegram400": 400, "telegram403": 403,
                            "telegram429": 429, "telegram5xx": 500}.get(case, 200)
        self.closed = False

    def iter_content(self, chunk_size):
        if chunk_size != 1:
            raise AssertionError("route_probe_response_chunk_changed")
        self.context.emit("provider_body", "streamed", evidence="SIMULATED")
        if self.case == "malformed_json":
            data = b"{"
        elif self.case == "broken_stream":
            yield b'{"ok":'
            import requests.exceptions as errors
            raise errors.ChunkedEncodingError()
        elif self.case == "telegram403":
            data = json.dumps({"ok": False, "error_code": 403,
                               "description": "Forbidden: bot was blocked by the user"}).encode()
        elif self.case == "telegram429":
            data = json.dumps({"ok": False, "error_code": 429,
                               "parameters": {"retry_after": 7}}).encode()
        elif self.case == "telegram5xx":
            data = json.dumps({"ok": False, "error_code": 500}).encode()
        elif self.case == "missing_receipt":
            data = json.dumps({"ok": True, "result": {}}).encode()
        elif self.case == "telegram400":
            data = json.dumps({"ok": False, "error_code": 400,
                               "description": "Bad Request: message to be replied not found"}).encode()
        else:
            # bool is deliberately invalid as MID: BNT strips payload but the
            # real bridge receipt validator must refuse this apparent success.
            mid = True if self.case == "bridge_only_failure" else 900
            data = json.dumps({"ok": True, "result": {"message_id": mid}}).encode()
        for byte in data:
            yield bytes([byte])

    def close(self):
        self.closed = True
        self.context.emit("provider_response_close", "completed", evidence="SIMULATED")


class _Session:
    """No requests.Session/socket is constructed; only HTTPAdapter is real."""
    def __init__(self, case, context):
        self.case, self.context = case, context
        self.proxies = {}
        self.cookies = {}
        self.trust_env = True
        self.auth = None
        self.posts = 0
        self.closed = False
        self.retry_total = None
        observer = getattr(context, "observe_http_session", None)
        if callable(observer):
            observer(self)

    def mount(self, prefix, adapter):
        if prefix != "https://" or adapter.max_retries.total != 0:
            raise AssertionError("route_probe_retry_policy_changed")
        self.retry_total = adapter.max_retries.total
        self.context.emit("http_adapter", "configured", evidence="SIMULATED", retries=0)

    def post(self, url, **kwargs):
        # Inspect only synthetic wiring, never emit URL/body/token/headers.
        if (url != "https://api.telegram.org/bot" + TOKEN + "/sendMessage"
                or self.trust_env is not False or self.auth is not None
                or kwargs.get("allow_redirects") is not False
                or kwargs.get("stream") is not True or kwargs.get("verify") is not True
                or kwargs.get("timeout") != (5.0, 15.0) or self.retry_total != 0):
            raise AssertionError("route_probe_http_contract_changed")
        self.posts += 1
        if self.posts != 1:
            raise AssertionError("route_probe_repeated_post")
        self.context.emit("http_post", "attempted", evidence="SIMULATED", count=self.posts)
        import requests.exceptions as errors
        kinds = {"timeout": errors.ReadTimeout, "connect": errors.ConnectTimeout,
                 "proxy": errors.ProxyError, "tls": errors.SSLError, "dns": errors.ConnectionError, "tcp": errors.ConnectionError}
        if self.case in kinds:
            self.context.emit("provider_fault", self.case, evidence="SIMULATED")
            raise kinds[self.case]()
        return _Response(self.case, self.context)

    def close(self):
        self.closed = True
        self.context.emit("http_session_close", "completed", evidence="SIMULATED", count=self.posts)


def prepare(target, fixture, context):
    """Supply args to real BNT.__call__ or real private_transport.deliver.

    Authority, claim/ledger checks, credential reader and current route are
    synthetic. Native decoding, ownership wrapping and bridge receipt mapping
    execute the selected pinned source without edits. DB exception is before
    first I/O in the synthetic current-route read, not a receipt-commit failure.
    """
    if fixture.get("stack_variant") == "canonical_v3":
        return _prepare_canonical_v3(target, fixture, context)
    if fixture.get("stack_variant") == "canonical_v2":
        return _prepare_canonical(target, fixture, context)
    if fixture.get("stack_variant") == "requests_http":
        return _prepare_real_http(target, fixture, context)
    case = _case(fixture)
    if case in {"duplicate", "duplicate_conflict", "group_unknown", "preclaim_db"}:
        return _prepare_ledger(target, fixture, context)
    native = context.load_module("app.ingest.telegram_basic_native_transport")
    observer = getattr(context, "observe_native_transport", None)
    if callable(observer):
        observer(native)
    bridge = context.load_module("app.ingest.bot_bridge_core")
    binding_module = context.load_module("app.ingest.telegram_private_binding")
    session = _Session(case, context)

    def authority():
        admitted = case != "owner_loss"
        context.emit("owner_guard", "admitted" if admitted else "refused", evidence="SIMULATED")
        return admitted

    transport = native.BasicNativeTransport("socks5h://fixture.invalid:1080",
        session_factory=lambda: session, authority_check=authority)
    context.avl_state = {"session": session, "transport": transport}
    arguments = {"chat_id": GROUP_ID, "text": "Synthetic route probe",
                 "parse_mode": "HTML", "reply_parameters": {
                     "message_id": PARENT_ID, "allow_sending_without_reply": False}}
    context.emit("fixture_scope", "configured", evidence="SIMULATED",
                 group_destination=True, resident_destination=False,
                 production_claim_guard=False, actual_worker=False)
    if target is native.BasicNativeTransport.__call__:
        if case == "db_exception":
            raise ValueError("route_probe_db_case_requires_bridge")
        return {"args": [transport, TOKEN, "sendMessage", arguments], "kwargs": {}}
    if target is bridge.invoke_once and case == "wrapper_classification":
        def send_real():
            return transport(TOKEN, "sendMessage", arguments)
        def invalid_classification(response):
            context.emit("wrapper_classification", "failed", evidence="SIMULATED")
            raise FixtureClassificationError()
        return {"args": [], "kwargs": {"send": send_real, "classify": invalid_classification,
            "guard": lambda: True, "enabled": lambda: True}}
    private = context.load_module("app.ingest.telegram_private_transport")
    if target is not private.deliver:
        raise ValueError("route_probe_target_not_supported")
    binding = binding_module.PrivateBotBinding("fixture_tenant", BOT_ID, 1,
        GROUP_ID, "supergroup", frozenset({RESIDENT_ID}), frozenset({42}),
        "fixture-token-reference", "fixture-secret-reference", enabled=True,
        purpose="basic", identity_verified=True, group_verified=True)
    route = bridge.BridgeRoute("telegram", binding.tenant_id, str(BOT_ID), str(RESIDENT_ID),
        str(GROUP_ID), str(RESIDENT_ID), "600", "ui_to_group", str(PARENT_ID),
        binding.fingerprint(), "42", True)

    def current_route():
        context.emit("current_route_read", "attempted", evidence="SIMULATED")
        if case == "db_exception":
            context.emit("database_read", "failed", evidence="SIMULATED")
            raise FixtureDatabaseError()
        return route

    def effect_check():
        context.emit("claim_guard", "admitted", evidence="SIMULATED")
        return True

    def token_reader(ref):
        if ref != "fixture-token-reference":
            raise AssertionError("route_probe_credential_ref_changed")
        context.emit("credential_reader", "returned_synthetic", evidence="SIMULATED")
        return TOKEN

    intended = dict(arguments, method="sendMessage", origin="platform_ui",
                    platform_route_version=2, platform_stage="group", platform_actor_user_id=42)
    return {"args": [binding, intended], "kwargs": {"api_call": transport,
        "token_reader": token_reader, "effect_check": effect_check,
        "route_scope": route, "current_route": current_route}}


def observe_outcome(result, exception, fixture, context):
    """Optional engine hook: simulated storage AFTER the real target returns.

    A hook failure is reported separately by the engine. It cannot rewrite the
    original returned receipt/exception or claim the actual worker committed.
    """
    if fixture.get("stack_variant") == "canonical_v3":
        return _observe_canonical_v3(result, exception, fixture, context)
    if fixture.get("stack_variant") == "canonical_v2":
        return _observe_canonical(result, exception, fixture, context)
    if fixture.get("stack_variant") == "requests_http":
        return _observe_real_http(result, exception, fixture, context)
    case = _case(fixture)
    if case in {"duplicate", "duplicate_conflict", "group_unknown", "preclaim_db"}:
        return _observe_ledger(result, exception, fixture, context)
    bridge = context.load_module("app.ingest.bot_bridge_core")
    transport = context.avl_state["transport"]
    session = context.avl_state["session"]
    if exception is not None:
        owned = transport.owns_send_error(exception)
        context.emit("native_exception", "observed", evidence="SIMULATED",
                     owned_send_error=owned,
                     effect_started=(exception.effect_started if owned else None))
        return
    if case == "wrapper_classification":
        receipt = result[0]
    elif type(result) is bridge.DeliveryReceipt:
        receipt = result
    else:
        private = context.load_module("app.ingest.telegram_private_transport")
        receipt = private.classify_receipt(result)
    # Emit only enums admitted by the actual bridge and selected fixture matrix.
    states = {"sent", "failed", "retry_wait", "unknown"}
    categories = {None, "transport_or_receipt_unknown", "partial_or_invalid_receipt",
        "binding_changed_before_effect", "provider_rejected_400_parent_not_found",
        "provider_rejected_403_recipient_blocked", "flood_control", "provider_indeterminate",
        "native_pre_runtime_owner_not_admitted", "native_post_transport_or_receipt_unknown",
        "partial_or_invalid_receipt"}
    if receipt.state not in states or receipt.error_category not in categories:
        raise ValueError("route_probe_outcome_not_admitted")
    context.emit("bridge_receipt", receipt.state, evidence="SIMULATED",
                 category=receipt.error_category, native_id_count=len(receipt.native_ids),
                 count=session.posts, actual_worker=False)
    context.emit("receipt_category", receipt.error_category or "NONE", evidence="SIMULATED")
    transaction = FakeTransaction(context, fail=case == "db_commit_exception")
    context.avl_state["transaction"] = transaction
    try:
        transaction.commit()
    except FixtureDatabaseError:
        transaction.rollback()
        context.emit("receipt_persistence", "unverified", evidence="SIMULATED",
                     original_receipt_state=receipt.state, native_repeated=False)
        raise
    context.emit("receipt_committed_fixture", "completed", evidence="SIMULATED",
                 actual_worker=False, native_repeated=False)


def _fixture_binding(context):
    binding_module = context.load_module("app.ingest.telegram_private_binding")
    return binding_module.PrivateBotBinding("fixture_tenant", BOT_ID, 1,
        GROUP_ID, "supergroup", frozenset({RESIDENT_ID}), frozenset({42}),
        "fixture-token-reference", "fixture-secret-reference", enabled=True,
        purpose="basic", identity_verified=True, group_verified=True)


def _prepare_ledger(target, fixture, context):
    """Real ledger/worker functions; in-memory SQLite only, no source patches."""
    from sqlalchemy.orm import sessionmaker
    ledger = context.load_module("app.ingest.telegram_private_inbox")
    db_module = context.load_module("app.core.db")
    engine = db_module.engine  # Actual original SQLite-only configuration above.
    ledger.TelegramPrivateBotOperation.__table__.create(engine, checkfirst=True)
    ledger.TelegramPrivateBotBinding.__table__.create(engine, checkfirst=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    binding = _fixture_binding(context)
    case = _case(fixture)
    context.avl_state = {"engine": engine, "factory": factory, "posts": 0,
                         "case": case, "binding": binding}
    if case in {"duplicate", "duplicate_conflict"}:
        if target is not ledger.enqueue_operation:
            raise ValueError("route_probe_target_not_supported")
        db = factory()
        context.avl_state["db"] = db
        update = SimpleNamespace(id=1, bot_id=BOT_ID, tenant_id=binding.tenant_id,
                                 binding_fingerprint=binding.ingress_fingerprint())
        intended = {"method": "sendMessage", "chat_id": GROUP_ID, "text": "Synthetic route probe"}
        original = ledger.enqueue_operation(db, binding, update, "fixture-action", "platform_group", GROUP_ID, intended)
        db.commit()
        context.avl_state["original_id"] = original.id
        if case == "duplicate_conflict":
            intended = dict(intended, text="Different synthetic reply")
        context.emit("existing_action_seed", "committed_sqlite", evidence="SIMULATED", count=1)
        return {"args": [db, binding, update, "fixture-action", "platform_group", GROUP_ID, intended], "kwargs": {}}
    worker = context.load_module("app.ingest.telegram_private_worker")
    if target is not worker.process_delivery_once:
        raise ValueError("route_probe_target_not_supported")
    with factory() as db:
        db.add(ledger.TelegramPrivateBotBinding(bot_id=BOT_ID, tenant_id=binding.tenant_id,
            generation=1, purpose="basic", enabled=True, identity_verified=True,
            group_verified=True, group_id=GROUP_ID, group_type="supergroup",
            principal_ids=[RESIDENT_ID], staff_user_ids=[42],
            token_ref=binding.token_ref, secret_ref=binding.secret_ref))
        if case == "group_unknown":
            for key, kind, state, destination, intended in [
                    ("fixture-group", "platform_group", "unknown", GROUP_ID, {"method": "sendMessage", "chat_id": GROUP_ID}),
                    ("fixture-primary", "platform_reply", "queued", RESIDENT_ID,
                     {"method": "sendMessage", "chat_id": RESIDENT_ID, "platform_route_version": 2,
                      "platform_group_operation_key": "fixture-group"})]:
                db.add(ledger.TelegramPrivateBotOperation(operation_key=key, update_row_id=1,
                    bot_id=BOT_ID, tenant_id=binding.tenant_id, binding_generation=1,
                    binding_fingerprint=binding.fingerprint(), kind=kind, destination_chat_id=destination,
                    intended=intended, intended_digest=ledger.canonical_digest(intended), state=state))
        db.commit()
    def forbidden_native(*args, **kwargs):
        context.avl_state["posts"] += 1
        raise AssertionError("route_probe_worker_should_not_send")
    def selected_factory():
        if case == "preclaim_db":
            context.emit("database_before_claim", "failed", evidence="SIMULATED")
            raise FixtureDatabaseError()
        return factory()
    context.emit("worker_fixture", "prepared", evidence="SIMULATED",
                 actual_worker=True, production_owner_guard=False)
    return {"args": [BOT_ID, selected_factory], "kwargs": {"api_call": forbidden_native,
        "token_reader": lambda ref: TOKEN, "effect_authority_check": lambda: True}}


def _observe_ledger(result, exception, fixture, context):
    ledger = context.load_module("app.ingest.telegram_private_inbox")
    state = context.avl_state
    db = state.get("db") or state["factory"]()
    try:
        count = db.query(ledger.TelegramPrivateBotOperation).count()
        if exception is not None:
            context.emit("ledger_result", "refused", evidence="SIMULATED", count=count)
        elif _case(fixture) == "group_unknown":
            context.emit("worker_result", result, evidence="SIMULATED", count=state["posts"])
        else:
            context.emit("ledger_result", "existing_action_reused", evidence="SIMULATED", count=count)
        state["row_count"] = count
    finally:
        db.rollback()
        db.close()
        state["engine"].dispose()


HTTP_STACK_CASES = frozenset({'success', 'http401', 'ok_false', 'empty_body',
    'reset', 'bad_shape', 'config_missing', 'dns', 'proxy', 'tls',
    'connect_timeout', 'read_timeout'})


class _HttpBytes:
    """BytesIO factory with body faults, never a socket or provider payload."""
    @staticmethod
    def wire(case):
        status = 401 if case == 'http401' else 200
        if case == 'http401':
            body = b'{"ok":false,"error_code":401}'
        elif case == 'ok_false':
            body = b'{"ok":false,"error_code":400,"description":"Bad Request: message to be replied not found"}'
        elif case == 'empty_body':
            body = b''
        elif case == 'bad_shape':
            body = b'{"ok":"invalid"}'
        else:
            body = json.dumps({'ok': True, 'result': {'message_id': 900,
                'date': 0, 'chat': {'id': GROUP_ID, 'type': 'supergroup'}}},
                separators=(',', ':')).encode()
        headers = ('HTTP/1.1 ' + str(status) + ' Synthetic\r\nContent-Type: application/json\r\n'
                   'Content-Length: ' + str(len(body)) + '\r\nConnection: close\r\n\r\n').encode()
        return status, headers + body


class _FakeHttpSocket:
    """Only the TCP/TLS socket boundary is synthetic; HTTP parsing is real."""
    def __init__(self, state, context, case):
        self.state, self.context, self.case = state, context, case
        self.timeout, self.closed = None, False

    def sendall(self, data):
        # Count request starts without retaining/printing token-bearing headers.
        if bytes(data).startswith(b'POST '):
            self.state['post_count'] += 1
            if self.state['post_count'] != 1:
                raise AssertionError('route_probe_real_http_repeated_post')
            self.context.emit('real_http_request', 'written', evidence='SIMULATED', count=1)
        self.state['wire_write_count'] += 1

    def makefile(self, mode):
        if mode != 'rb':
            raise AssertionError('route_probe_http_stream_mode')
        import io
        import socket
        state, context, case = self.state, self.context, self.case
        status, wire = _HttpBytes.wire(case)
        state['wire_status'] = status
        context.emit('http_response_wire', 'provided', evidence='SIMULATED', status_code=status)

        class BodyStream(io.BytesIO):
            def read(self, size=-1):
                if case == 'reset':
                    state['fault_phase'] = 'response_body'
                    context.emit('socket_fault', 'RESET', evidence='SIMULATED')
                    raise ConnectionResetError()
                if case == 'read_timeout':
                    state['fault_phase'] = 'response_body'
                    context.emit('socket_fault', 'READ_TIMEOUT', evidence='SIMULATED')
                    raise socket.timeout()
                return super().read(size)
        stream = BodyStream(wire)
        state['streams'].append(stream)
        return stream

    def settimeout(self, value):
        self.timeout = value

    def gettimeout(self):
        return self.timeout

    def close(self):
        self.closed = True
        self.state['socket_closed'] = True



def _prepare_real_http(target, fixture, context):
    """Install one per-invocation connect boundary, never a Session/send stub."""
    case = _case(fixture)
    import requests
    import socket
    import ssl
    from urllib3.connection import HTTPSConnection
    from urllib3.exceptions import ConnectTimeoutError, NameResolutionError, ProxyError
    # Load real SOCKS definitions BEFORE patching. No proxy or socket is opened.
    from urllib3.contrib.socks import SOCKSHTTPSConnection
    if 'connect' in SOCKSHTTPSConnection.__dict__:
        raise ValueError('route_probe_socks_connect_shape_changed')
    native = context.load_module('app.ingest.telegram_basic_native_transport')
    observer = getattr(context, 'observe_native_transport', None)
    if callable(observer):
        observer(native)
    private = context.load_module('app.ingest.telegram_private_transport')
    bridge = context.load_module('app.ingest.bot_bridge_core')
    if target not in {native.BasicNativeTransport.__call__, private.deliver}:
        raise ValueError('route_probe_http_target_not_supported')
    state = {'session_count': 0, 'connect_count': 0, 'post_count': 0,
             'wire_write_count': 0, 'streams': [], 'sockets': [], 'sessions': [],
             'socket_closed': False, 'fault_phase': None, 'case': case,
             'original_connect': HTTPSConnection.connect, 'connection_class': HTTPSConnection}
    context.avl_http_state = state

    def real_session():
        session = requests.Session()
        state['session_count'] += 1
        state['sessions'].append(session)
        context.emit('requests_session', 'constructed', evidence='REAL_CODE', count=state['session_count'])
        observer = getattr(context, 'observe_http_session', None)
        if callable(observer):
            observer(session)
        return session

    transport = native.BasicNativeTransport('socks5h://fixture.invalid:1080',
        session_factory=real_session, authority_check=lambda: True)
    state['transport'] = transport
    binding = _fixture_binding(context)
    arguments = {'chat_id': GROUP_ID, 'text': 'Synthetic route probe', 'parse_mode': 'HTML',
                 'reply_parameters': {'message_id': PARENT_ID, 'allow_sending_without_reply': False}}
    route = bridge.BridgeRoute('telegram', binding.tenant_id, str(BOT_ID), str(RESIDENT_ID),
        str(GROUP_ID), str(RESIDENT_ID), '600', 'ui_to_group', str(PARENT_ID), binding.fingerprint(), '42', True)

    def simulated_connect(connection):
        state['connect_count'] += 1
        state['socks_pool_selected'] = type(connection) is SOCKSHTTPSConnection
        if state['connect_count'] != 1:
            raise AssertionError('route_probe_real_http_connect_retry')
        state['fault_phase'] = 'connect'
        context.emit('network_boundary', 'DNS_TCP_SOCKS_TLS_SIMULATED', evidence='SIMULATED', count=1)
        if case == 'dns':
            raise NameResolutionError('fixture.invalid', connection, socket.gaierror())
        if case == 'proxy':
            raise ProxyError('synthetic proxy failure', OSError())
        if case == 'tls':
            raise ssl.SSLError()
        if case == 'connect_timeout':
            raise ConnectTimeoutError()
        connection.sock = _FakeHttpSocket(state, context, case)
        state['sockets'].append(connection.sock)
        # These internal flags suppress warnings about an intentionally absent
        # handshake; they NEVER qualify real TLS or leave this fixture process.
        connection.is_verified = True
        connection.proxy_is_verified = True
        state['fault_phase'] = None
    HTTPSConnection.connect = simulated_connect
    if target is native.BasicNativeTransport.__call__:
        return {'args': [transport, TOKEN, 'sendMessage', arguments], 'kwargs': {}}
    intended = dict(arguments, method='sendMessage', origin='platform_ui',
                    platform_stage='group', platform_route_version=2, platform_actor_user_id=42)
    return {'args': [binding, intended], 'kwargs': {'api_call': transport,
        'token_reader': None if case == 'config_missing' else lambda ref: TOKEN,
        'effect_check': lambda: True, 'route_scope': route, 'current_route': lambda: route}}



def _observe_real_http(result, exception, fixture, context):
    state = context.avl_http_state
    try:
        bridge = context.load_module('app.ingest.bot_bridge_core')
        if exception is not None:
            owned = state['transport'].owns_send_error(exception)
            context.emit('real_http_native_exception', 'observed', evidence='SIMULATED',
                         effect_started=exception.effect_started if owned else None)
            return
        if type(result) is bridge.DeliveryReceipt:
            receipt = result
        else:
            receipt = context.load_module('app.ingest.telegram_private_transport').classify_receipt(result)
        categories = {None, 'provider_rejected', 'provider_rejected_401_unknown_other', 'provider_rejected_400_parent_not_found',
            'native_post_transport_or_receipt_unknown', 'native_post_response_invalid',
            'transport_not_installed'}
        if receipt.error_category not in categories or receipt.state not in {'sent', 'failed', 'unknown'}:
            raise ValueError('route_probe_real_http_outcome_not_admitted')
        context.emit('real_http_receipt', receipt.state, evidence='SIMULATED', count=state['post_count'])
        context.emit('real_http_category', receipt.error_category or 'NONE', evidence='SIMULATED')
        context.emit('real_http_sessions', 'counted', evidence='REAL_CODE', count=state['session_count'])
        context.emit('real_http_connects', 'counted', evidence='SIMULATED', count=state['connect_count'])
    finally:
        state['connection_class'].connect = state['original_connect']
        state['boundary_restored'] = True


CANONICAL_CASES = frozenset({'enqueue', 'group_success', 'private_success',
    'group_unknown', 'private_unknown', 'receipt_commit_failure'})


def _seed_canonical_v2_action(platform, db, record, kwargs, context):
    """SIMULATED historical action, constructed by the retained source kernel.

    Public enqueue intentionally creates v3 for a NEW action. A committed v2
    action is its compatibility selector; never replace that public dispatcher
    or relabel a v3 envelope. This seed is not historical/provider evidence.
    """
    kernel = getattr(platform, '_enqueue_v2', None)
    if not callable(kernel):
        raise ValueError('route_probe_canonical_v2_coverage_unsupported')
    target = platform.prepare_platform_reply(db, record,
        actor_user_id=kwargs['actor_user_id'], action_key=kwargs['action_key'])
    primary = kernel(db, target, kwargs['actor_user_id'], kwargs['action_key'],
        kwargs['text'], (), None)
    intended = primary.intended
    if (not isinstance(intended, dict)
            or type(intended.get('platform_route_version')) is not int
            or intended['platform_route_version'] != 2
            or intended.get('platform_group_operation_key') != primary.operation_key + ':group'
            or primary.state != 'queued' or primary.attempts != 0
            or primary.native_receipts or primary.claim_token is not None):
        raise ValueError('route_probe_canonical_v2_seed_invalid')
    # The selected public enqueue revalidates this committed action, and the
    # worker independently validates before transport. Do not add a redundant
    # seed-time traversal that consumes the bounded recorder's target budget.
    db.commit()
    context.emit('canonical_v2_historical_action', 'seeded_by_retained_kernel',
        evidence='SIMULATED', route_version=2, prior_action_simulated=True,
        fresh_v2_producer=False)
    return primary.id, primary.intended_digest


def _prepare_canonical(target, fixture, context, *, seed_legacy_action=True):
    """Real canonical BASIC source/actor/intent proof; synthetic in-memory data.

    No validator/admission/scope function is replaced. Only config, unused
    subscription, owner callback, credentials and provider crossing are fake.
    SQLite cannot qualify PostgreSQL advisory/row locks or live owner authority.
    """
    from datetime import datetime, timezone
    from sqlalchemy.orm import Session, sessionmaker
    ledger = context.load_module('app.ingest.telegram_private_inbox')
    binding_module = context.load_module('app.ingest.telegram_private_binding')
    materializer = context.load_module('app.ingest.telegram_private_materializer')
    platform = context.load_module('app.ingest.telegram_basic_platform_reply')
    worker = context.load_module('app.ingest.telegram_private_worker')
    models = context.load_module('app.models')
    db_module = context.load_module('app.core.db')
    native = context.load_module('app.ingest.telegram_basic_native_transport')
    observer = getattr(context, 'observe_native_transport', None)
    if callable(observer):
        observer(native)
    if target not in {platform.enqueue_platform_reply, worker.process_delivery_once}:
        raise ValueError('route_probe_canonical_target_invalid')
    case = _case(fixture)
    if (case == 'enqueue') is not (target is platform.enqueue_platform_reply):
        raise ValueError('route_probe_canonical_entry_mismatch')
    engine = db_module.engine
    db_module.Base.metadata.create_all(engine)
    state = {'engine': engine, 'sessions': [], 'commits': 0, 'rollbacks': 0,
             'case': case, 'fail_receipt': False, 'owner_calls': 0}
    context.avl_canonical_state = state

    class RecordedSession(Session):
        def commit(self):
            if state['fail_receipt']:
                state['effect_commit_attempts'] = state.get('effect_commit_attempts', 0) + 1
                # Exact fixture boundary: claim COMMIT succeeds, receipt COMMIT
                # fails even if real projection functions already flushed rows.
                if state['effect_commit_attempts'] == 2:
                    context.emit('canonical_receipt_commit', 'failed', evidence='SIMULATED')
                    raise FixtureDatabaseError()
            super().commit()
            state['commits'] += 1
            # Direct aggregation avoids generator resume frames in the traced
            # fixture bookkeeping; every session and post is still counted.
            post_count = 0
            for session in state['sessions']:
                post_count += session.posts
            context.emit('canonical_database_commit', 'completed_sqlite', evidence='SIMULATED',
                         count=state['commits'], post_count=post_count)
        def rollback(self):
            super().rollback()
            state['rollbacks'] += 1

    factory = sessionmaker(bind=engine, class_=RecordedSession, expire_on_commit=False)
    state['factory'] = factory
    actor = 900001
    with factory() as db:
        db.add(ledger.TelegramPrivateBotBinding(bot_id=BOT_ID, tenant_id='fixture_tenant',
            generation=1, purpose='basic', enabled=True, identity_verified=True,
            group_verified=True, group_id=GROUP_ID, group_type='supergroup',
            principal_ids=[RESIDENT_ID], staff_user_ids=[42],
            token_ref='fixture-token-reference', secret_ref='fixture-secret-reference'))
        db.add(models.User(id=actor, tenant_id='fixture_tenant', username='route-probe-admin',
            first_name='Synthetic', last_name='Operator', email='synthetic@example.invalid',
            role='admin', enabled=True, access_mode='legacy', access_status='active', global_login=False))
        db.commit()
        binding = binding_module.load_binding(db, BOT_ID)
        stamp = int(datetime.now(timezone.utc).timestamp()) - 120
        payload = {'update_id': 1, 'message': {'message_id': PARENT_ID, 'date': stamp,
            'chat': {'id': RESIDENT_ID, 'type': 'private'},
            'from': {'id': RESIDENT_ID, 'is_bot': False, 'first_name': 'Synthetic'},
            'text': 'Synthetic resident source'}}
        row, duplicate = ledger.accept_update(db, binding, payload)
        if duplicate:
            raise AssertionError('route_probe_canonical_seed_duplicate')
        db.commit()
        materializer.materialize(db, binding, row)
        db.commit()
        # Only the PRE-EXISTING resident mirror receipt is seeded. All new
        # platform group/private actions remain queued until actual worker I/O.
        source_ops = db.query(ledger.TelegramPrivateBotOperation).filter_by(update_row_id=row.id).all()
        source = next(op for op in source_ops if op.kind == 'mirror')
        for op in source_ops:
            op.state, op.sent_at, op.attempts = 'sent', datetime.now(timezone.utc), 1
            op.native_receipts = [PARENT_ID + op.id]
        db.add(ledger.TelegramPrivateBotMirrorAlias(tenant_id=binding.tenant_id,
            bot_id=BOT_ID, group_id=GROUP_ID, native_message_id=source.native_receipts[0],
            resident_update_row_id=row.id, origin_operation_id=source.id,
            binding_generation=binding.generation, binding_fingerprint=binding.fingerprint(), group_thread_id=None))
        # Some retained format versions use a separate attribution card.
        for op in source_ops:
            if op.kind == 'attribution':
                db.add(ledger.TelegramPrivateBotMirrorAlias(tenant_id=binding.tenant_id,
                    bot_id=BOT_ID, group_id=GROUP_ID, native_message_id=op.native_receipts[0],
                    resident_update_row_id=row.id, origin_operation_id=op.id,
                    binding_generation=binding.generation, binding_fingerprint=binding.fingerprint(), group_thread_id=None))
        db.commit()
        state['message_id'], state['raw_id'] = row.message_id, row.id
    context.emit('canonical_source_seed', 'committed_sqlite', evidence='SIMULATED',
                 actual_source_functions=True, prior_mirror_receipt_simulated=True,
                 actual_scope_functions=True, postgres_lock_proof=False)
    db = factory()
    args = [db, db.get(models.Message, state['message_id'])]
    kwargs = {'actor_user_id': actor, 'action_key': 'canonical-new-action', 'text': 'Synthetic platform response'}
    if seed_legacy_action:
        try:
            state['legacy_seed'] = _seed_canonical_v2_action(platform, db, args[1], kwargs, context)
        except BaseException:
            db.rollback()
            db.close()
            engine.dispose()
            raise
    if target is platform.enqueue_platform_reply:
        state['db'] = db
        return {'args': args, 'kwargs': kwargs}
    try:
        primary = platform.enqueue_platform_reply(*args, **kwargs)
        state['primary_id'] = primary.id
        state['group_key'] = primary.intended['platform_group_operation_key']
        db.commit()
    finally:
        db.close()

    def authority():
        state['owner_calls'] += 1
        return True

    def new_session():
        selected = 'timeout' if state.get('provider_unknown') else 'success'
        session = _Session(selected, context)
        state['sessions'].append(session)
        return session

    transport = native.BasicNativeTransport('socks5h://fixture.invalid:1080',
        session_factory=new_session, authority_check=authority)
    call_kwargs = {'api_call': transport, 'token_reader': lambda ref: TOKEN,
                   'effect_authority_check': authority}
    if case in {'private_success', 'private_unknown'}:
        first = worker.process_delivery_once(BOT_ID, factory, **call_kwargs)
        state['prior_worker_result'] = first
        if first != 'sent':
            raise AssertionError('route_probe_canonical_group_not_sent')
        context.emit('canonical_group_transaction', first, evidence='SIMULATED',
                     actual_worker=True, receipt_commit=True)
    state['provider_unknown'] = case in {'group_unknown', 'private_unknown'}
    state['fail_receipt'] = case == 'receipt_commit_failure'
    return {'args': [BOT_ID, factory], 'kwargs': call_kwargs}


def _observe_canonical(result, exception, fixture, context):
    state = context.avl_canonical_state
    ledger = context.load_module('app.ingest.telegram_private_inbox')
    db = state.get('db') or state['factory']()
    try:
        case = _case(fixture)
        if case == 'enqueue' and exception is None:
            state['primary_id'] = result.id
            state['group_key'] = result.intended['platform_group_operation_key']
            db.commit()
        rows = db.query(ledger.TelegramPrivateBotOperation).filter(
            ledger.TelegramPrivateBotOperation.kind.in_(['platform_group', 'platform_reply'])).order_by(ledger.TelegramPrivateBotOperation.id).all()
        state['operations'] = [dict(id=row.id, kind=row.kind, state=row.state,
            attempts=row.attempts, native_count=len(row.native_receipts),
            claimed=row.claim_token is not None, error_category=row.error_category) for row in rows]
        state['post_count'] = 0
        for session in state['sessions']:
            state['post_count'] += session.posts
        context.emit('canonical_ledger_readback', 'observed_sqlite', evidence='SIMULATED',
                     count=len(rows), post_count=state['post_count'], actual_worker=case != 'enqueue',
                     live_actor_proof=False, production_db=False)
        # Closed diagnostics only; no row IDs, native IDs, claim values or
        # provider/category text cross this fixture observation boundary.
        for observed in state['operations']:
            kind = observed['kind'] if type(observed['kind']) is str and observed['kind'] in {
                'platform_group', 'platform_reply'} else 'UNVERIFIED'
            outcome = observed['state'] if type(observed['state']) is str and observed['state'] in {
                'queued', 'retry_wait', 'sending', 'sent', 'unknown', 'failed'} else 'UNVERIFIED'
            context.emit('canonical_operation', kind + '.' + outcome, evidence='SIMULATED',
                         attempts=observed['attempts'], count=observed['native_count'])
            context.emit('canonical_claim', 'PRESENT' if observed['claimed'] else 'ABSENT',
                         evidence='SIMULATED', symbol=kind)
        context.emit('canonical_posts', 'counted', evidence='SIMULATED', count=state['post_count'])
    finally:
        db.rollback()
        db.close()
        state['engine'].dispose()


def _canonical_v3_row_digest(row, ledger):
    """Full synthetic row comparison in memory; never exported as telemetry."""
    return ledger.canonical_digest({column.name: value.isoformat() if hasattr(value, 'isoformat') else value
        for column in row.__table__.columns for value in [getattr(row, column.name)]})


def _canonical_v3_alias_digest(db, ledger):
    rows = db.query(ledger.TelegramPrivateBotMirrorAlias).filter_by(
        tenant_id='fixture_tenant', bot_id=BOT_ID).order_by(ledger.TelegramPrivateBotMirrorAlias.id).all()
    return ledger.canonical_digest([_canonical_v3_row_digest(row, ledger) for row in rows])


def _prepare_canonical_v3(target, fixture, context):
    """Original v3 enqueue/worker; only newly synthetic echo uncertainty is seeded."""
    case = _case(fixture)
    platform = context.load_module('app.ingest.telegram_basic_platform_reply')
    worker = context.load_module('app.ingest.telegram_private_worker')
    ledger = context.load_module('app.ingest.telegram_private_inbox')
    native = context.load_module('app.ingest.telegram_basic_native_transport')
    if target is not worker.process_delivery_once:
        raise ValueError('route_probe_canonical_v3_entry_mismatch')
    # Reuse the retained fixture's source/actor setup, stopping BEFORE enqueue.
    # Its historical v2 label does not execute a v2 producer or change app code.
    prepared = _prepare_canonical(platform.enqueue_platform_reply,
        {**fixture, 'stack_variant': 'canonical_v2', 'case': 'enqueue'}, context,
        seed_legacy_action=False)
    state = context.avl_canonical_state
    state['case'] = fixture['case']
    db = state['db']
    try:
        primary = platform.enqueue_platform_reply(*prepared['args'], **{
            **prepared['kwargs'], 'action_key': 'canonical-v3-new-action'})
        echo = db.query(ledger.TelegramPrivateBotOperation).filter_by(
            tenant_id='fixture_tenant', bot_id=BOT_ID, kind='platform_group',
            operation_key=primary.operation_key + ':group').one()
        if (type(primary.intended.get('platform_route_version')) is not int
                or primary.intended['platform_route_version'] != 3
                or 'platform_group_operation_key' in primary.intended
                or primary.state != 'queued' or echo.state != 'queued'
                or primary.attempts != 0 or echo.attempts != 0):
            raise AssertionError('route_probe_canonical_v3_new_action_invalid')
        state['primary_id'], state['echo_id'] = primary.id, echo.id
        state['source_parent'] = primary.intended['reply_parameters']['message_id']
        state['resident_id'] = primary.destination_chat_id
        db.commit()
        context.emit('canonical_v3_enqueue', 'committed_sqlite', evidence='SIMULATED', count=2)
    finally:
        db.close()
        state['db'] = None
    with state['factory']() as db:
        binding = context.load_module('app.ingest.telegram_private_binding').load_binding(db, BOT_ID)
        echo = db.get(ledger.TelegramPrivateBotOperation, state['echo_id'])
        platform.validate_platform_group(db, binding, echo)
        echo.state, echo.attempts = 'unknown', 1
        echo.error_category = 'transport_or_receipt_unknown'
        echo.native_receipts, echo.sent_at = [], None
        echo.claim_token, echo.sending_at = 'a' * 32, ledger.utcnow()
        db.commit()
    with state['factory']() as db:
        state['echo_baseline'] = _canonical_v3_row_digest(
            db.get(ledger.TelegramPrivateBotOperation, state['echo_id']), ledger)
        state['alias_baseline'] = _canonical_v3_alias_digest(db, ledger)
    context.emit('canonical_v3_echo_fixture', 'unknown_seeded', evidence='SIMULATED', count=1)

    if case == 'binding_revoked_before_post':
        with state['factory']() as db:
            state['primary_baseline'] = _canonical_v3_row_digest(
                db.get(ledger.TelegramPrivateBotOperation, state['primary_id']), ledger)
            db.get(ledger.TelegramPrivateBotBinding, BOT_ID).enabled = False
            db.commit()
        context.emit('canonical_v3_binding_fixture', 'disabled', evidence='SIMULATED', count=1)

    class ResidentSession(_Session):
        def post(self, url, **kwargs):
            # This is the fake HTTP boundary, not a replacement business guard.
            arguments = json.loads(kwargs['data'])
            if (arguments.get('chat_id') != state['resident_id']
                    or arguments.get('reply_parameters') != {'message_id': state['source_parent'],
                        'allow_sending_without_reply': False}):
                raise AssertionError('route_probe_canonical_v3_wire_destination')
            state['resident_request_verified'] = True
            context.emit('canonical_v3_wire', 'resident_parent_verified', evidence='SIMULATED', count=1)
            return super().post(url, **kwargs)

    def authority():
        state['owner_calls'] += 1
        return True

    def new_session():
        session = ResidentSession('timeout' if case == 'primary_post_timeout_no_retry' else 'success', context)
        state['sessions'].append(session)
        return session

    transport = native.BasicNativeTransport('socks5h://fixture.invalid:1080',
        session_factory=new_session, authority_check=authority)
    context.emit('canonical_v3_worker_ready', 'prepared', evidence='SIMULATED')
    prepared_worker = {'args': [BOT_ID, state['factory']], 'kwargs': {'api_call': transport,
        'token_reader': lambda ref: TOKEN, 'effect_authority_check': authority}}
    if case == 'primary_post_timeout_no_retry':
        state['worker_call'] = (worker.process_delivery_once, prepared_worker)
    return prepared_worker


def _observe_canonical_v3(result, exception, fixture, context):
    """Fresh committed ledger/status proof, distinct from the target's return."""
    case = _case(fixture)
    if case in {'primary_post_timeout_no_retry', 'binding_revoked_before_post'}:
        return _observe_canonical_v3_negative(result, exception, fixture, context)
    state = context.avl_canonical_state
    ledger = context.load_module('app.ingest.telegram_private_inbox')
    platform = context.load_module('app.ingest.telegram_basic_platform_reply')
    binding_module = context.load_module('app.ingest.telegram_private_binding')
    try:
        if exception is not None or result != 'sent':
            raise AssertionError('route_probe_canonical_v3_worker_not_sent')
        with state['factory']() as db:
            primary = db.get(ledger.TelegramPrivateBotOperation, state['primary_id'])
            echo = db.get(ledger.TelegramPrivateBotOperation, state['echo_id'])
            if (primary.state != 'sent' or primary.attempts != 1 or primary.sent_at is None
                    or len(primary.native_receipts) != 1 or type(primary.native_receipts[0]) is not int
                    or primary.native_receipts[0] <= 0 or echo.state != 'unknown'
                    or _canonical_v3_row_digest(echo, ledger) != state['echo_baseline']
                    or _canonical_v3_alias_digest(db, ledger) != state['alias_baseline']):
                raise AssertionError('route_probe_canonical_v3_ledger_difference')
            status = platform.platform_action_status(db, binding_module.load_binding(db, BOT_ID), primary)
            if (status['platform_route_version'] != 3 or status['delivery_state'] != 'delivered'
                    or status['resident_delivery_state'] != 'delivered' or status['sender_confirmed'] is not True
                    or status['group_echo']['state'] != 'unknown' or status['group_delivery_state'] != 'unknown'
                    or _canonical_v3_row_digest(echo, ledger) != state['echo_baseline']
                    or _canonical_v3_alias_digest(db, ledger) != state['alias_baseline']):
                raise AssertionError('route_probe_canonical_v3_status_difference')
            state['post_count'] = sum(session.posts for session in state['sessions'])
            if state['post_count'] != 1 or state.get('resident_request_verified') is not True:
                raise AssertionError('route_probe_canonical_v3_post_count')
            state['status'] = status
            for row in (primary, echo):
                context.emit('canonical_operation', row.kind + '.' + row.state, evidence='SIMULATED',
                    attempts=row.attempts, count=len(row.native_receipts))
                context.emit('canonical_claim', 'PRESENT' if row.claim_token else 'ABSENT',
                    evidence='SIMULATED', symbol=row.kind)
            context.emit('canonical_v3_echo_preservation', 'UNCHANGED', evidence='SIMULATED', count=1)
            context.emit('canonical_v3_alias_preservation', 'UNCHANGED', evidence='SIMULATED', count=1)
            context.emit('canonical_v3_resident_status', 'delivered', evidence='SIMULATED', count=1)
            context.emit('canonical_v3_echo_status', 'unknown', evidence='SIMULATED', count=1)
            context.emit('canonical_posts', 'counted', evidence='SIMULATED', count=state['post_count'])
    finally:
        state['engine'].dispose()


def _observe_canonical_v3_negative(result, exception, fixture, context):
    """Original transactions, distinct first outcome and explicit second tick."""
    case = _case(fixture)
    state = context.avl_canonical_state
    ledger = context.load_module('app.ingest.telegram_private_inbox')
    bindings = context.load_module('app.ingest.telegram_private_binding')
    try:
        if case == 'binding_revoked_before_post':
            if (result is not None or type(exception) is not bindings.PrivateBotRejected
                    or exception.args != ('binding_not_qualified',)):
                raise AssertionError('route_probe_canonical_v3_refusal_not_verified')
            with state['factory']() as db:
                primary = db.get(ledger.TelegramPrivateBotOperation, state['primary_id'])
                echo = db.get(ledger.TelegramPrivateBotOperation, state['echo_id'])
                current = db.get(ledger.TelegramPrivateBotBinding, BOT_ID)
                if (current.enabled is not False or state['sessions']
                        or primary.state != 'queued' or primary.attempts != 0
                        or primary.claim_token is not None or primary.sending_at is not None
                        or primary.native_receipts != [] or primary.sent_at is not None
                        or _canonical_v3_row_digest(primary, ledger) != state['primary_baseline']
                        or _canonical_v3_row_digest(echo, ledger) != state['echo_baseline']
                        or _canonical_v3_alias_digest(db, ledger) != state['alias_baseline']):
                    raise AssertionError('route_probe_canonical_v3_refusal_ledger_difference')
            state['binding_refusal_verified'], state['post_count'] = True, 0
            context.emit('canonical_v3_admission', 'binding_refused_before_post', evidence='SIMULATED', count=1)
        elif case == 'primary_post_timeout_no_retry':
            if exception is not None or result != 'unknown':
                raise AssertionError('route_probe_canonical_v3_first_unknown_not_verified')
            if (len(state['sessions']) != 1 or state['sessions'][0].posts != 1
                    or state['sessions'][0].retry_total != 0
                    or state.get('resident_request_verified') is not True):
                raise AssertionError('route_probe_canonical_v3_first_post_not_verified')
            with state['factory']() as db:
                primary = db.get(ledger.TelegramPrivateBotOperation, state['primary_id'])
                echo = db.get(ledger.TelegramPrivateBotOperation, state['echo_id'])
                if (primary.state != 'unknown' or primary.attempts != 1
                        or primary.native_receipts != [] or primary.sent_at is not None
                        or not primary.claim_token or primary.sending_at is None
                        or primary.error_category != 'native_post_transport_or_receipt_unknown'
                        or _canonical_v3_row_digest(echo, ledger) != state['echo_baseline']
                        or _canonical_v3_alias_digest(db, ledger) != state['alias_baseline']):
                    raise AssertionError('route_probe_canonical_v3_first_unknown_ledger_difference')
                uncertain_before = [_canonical_v3_row_digest(row, ledger) for row in (primary, echo)]
                aliases_before = _canonical_v3_alias_digest(db, ledger)
            worker = context.load_module('app.ingest.telegram_private_worker')
            original, prepared = state['worker_call']
            if (original is not worker.process_delivery_once or prepared['args'] != [BOT_ID, state['factory']]):
                raise AssertionError('route_probe_canonical_v3_second_callable_invalid')
            commits_before = state['commits']
            context.emit('canonical_v3_first_tick', 'unknown', evidence='SIMULATED', count=1)
            context.emit('canonical_v3_second_tick', 'BEGIN', evidence='SIMULATED')
            second = original(*prepared['args'], **prepared['kwargs'])
            if (second != 'idle' or state['commits'] != commits_before
                    or len(state['sessions']) != 1 or sum(s.posts for s in state['sessions']) != 1):
                raise AssertionError('route_probe_canonical_v3_second_tick_difference')
            state['second_result'] = second
            context.emit('canonical_v3_second_tick', 'idle', evidence='SIMULATED', count=1)
            with state['factory']() as db:
                primary = db.get(ledger.TelegramPrivateBotOperation, state['primary_id'])
                echo = db.get(ledger.TelegramPrivateBotOperation, state['echo_id'])
                if ([_canonical_v3_row_digest(row, ledger) for row in (primary, echo)] != uncertain_before
                        or _canonical_v3_alias_digest(db, ledger) != aliases_before):
                    raise AssertionError('route_probe_canonical_v3_second_ledger_difference')
                platform = context.load_module('app.ingest.telegram_basic_platform_reply')
                status = platform.platform_action_status(db, bindings.load_binding(db, BOT_ID), primary)
                if (status['resident_delivery_state'] != 'unknown' or status['delivery_state'] != 'unknown'
                        or status['sender_confirmed'] is not False or status['group_echo']['state'] != 'unknown'
                        or [_canonical_v3_row_digest(row, ledger) for row in (primary, echo)] != uncertain_before
                        or _canonical_v3_alias_digest(db, ledger) != aliases_before):
                    raise AssertionError('route_probe_canonical_v3_second_status_difference')
                state['status'] = status
            state['post_count'] = 1
            context.emit('canonical_v3_resident_status', 'unknown', evidence='SIMULATED', count=1)
            context.emit('canonical_v3_echo_status', 'unknown', evidence='SIMULATED', count=1)
        else:
            raise ValueError('route_probe_canonical_v3_negative_case_invalid')
        state['negative_preserved'] = True
        context.emit('canonical_v3_primary_preservation', 'UNCHANGED', evidence='SIMULATED', count=1)
        context.emit('canonical_v3_echo_preservation', 'UNCHANGED', evidence='SIMULATED', count=1)
        context.emit('canonical_v3_alias_preservation', 'UNCHANGED', evidence='SIMULATED', count=1)
        context.emit('canonical_posts', 'counted', evidence='SIMULATED', count=state['post_count'])
    finally:
        state['engine'].dispose()
