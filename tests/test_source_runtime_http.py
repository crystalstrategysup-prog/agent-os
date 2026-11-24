"""Public, synthetic HTTP provenance regressions; no requests are executed."""

import pytest

from agent_os.handoff_store import scan_secrets


def encode_source(text):
    return (text.replace("AUTH_FIELD", "Authorization")
            .replace("COOKIE_FIELD", "Cookie")
            .replace("PASS_FIELD", "password").encode())


SOURCE = '''import gzip
from http.client import HTTPConnection
import json
from http.cookies import SimpleCookie

def request():
    connection = HTTPConnection("example.invalid")
    response = connection.getresponse()
    wire = response.read()
    headers = dict((name.lower(), value) for name, value in response.getheaders())
    data = json.loads(wire)
    return response.status, headers, data, wire

def credentials():
    def call():
        return request()[:3]
    status, headers, native = call()
    jar = SimpleCookie()
    jar.load(headers["set-cookie"])
    return {"AUTH_FIELD": "Bearer " + native["token"],
            "COOKIE_FIELD": "session=" + jar["session"].value}
'''


def changed(before, after):
    assert SOURCE.count(before) == 1
    return SOURCE.replace(before, after)


@pytest.mark.parametrize("source", [
    SOURCE,
    "# Кириллица сохраняет точные позиции литералов.\n" + SOURCE,
    changed("data = json.loads(wire)", "data = json.loads(gzip.decompress(wire))"),
    changed("return request()[:3]", "status, headers, data, wire = request()\n        return status, headers, data"),
    changed("    return {\"AUTH_FIELD\":", "    alias = native\n    return {\"AUTH_FIELD\":").replace('native["token"]', 'alias["token"]'),
    SOURCE + '\nraise RuntimeError("Scanning source must not execute it")\n',
], ids=["local-helper-tuple-slice", "unicode-offset", "gzip-json", "explicit-unpack", "readonly-alias", "never-execute"])
def test_response_derived_header_prefixes_are_accepted(source):
    scan_secrets(encode_source(source))


@pytest.mark.parametrize(("before", "after"), [
    ('native["token"]', '"SYNTHETIC_LITERAL_ONLY"'),
    ('"Bearer " + native["token"]', '"Bearer SYNTHETIC_LITERAL_ONLY" + native["token"]'),
    ('jar["session"].value', '"SYNTHETIC_LITERAL_ONLY"'),
    ('"session=" + jar["session"].value', '"session=SYNTHETIC_LITERAL_ONLY" + jar["session"].value'),
    ('wire = response.read()', 'wire = b"SYNTHETIC_LITERAL_ONLY"'),
    ('wire = response.read()', 'wire = response.read() if condition else b"SYNTHETIC_LITERAL_ONLY"'),
    ('return response.status, headers, data, wire', 'return response.status, headers, {"token": "SYNTHETIC_LITERAL_ONLY"}, wire'),
    ('return response.status, headers, data, wire', 'return response.status, headers, unknown(), wire'),
    ('    data = json.loads(wire)', '    json.loads = unknown\n    data = json.loads(wire)'),
    ('    data = json.loads(wire)', '    decoder = json\n    decoder.loads = unknown\n    data = json.loads(wire)'),
    ('    wire = response.read()', '    response.read = unknown\n    wire = response.read()'),
    ('    response = connection.getresponse()', '    connection.getresponse = unknown\n    response = connection.getresponse()'),
    ('    status, headers, native = call()', '    call = unknown\n    status, headers, native = call()'),
    ('    def call():', '    @unknown\n    def call():'),
    ('    return {"AUTH_FIELD":', '    native["token"] = "SYNTHETIC_LITERAL_ONLY"\n    return {"AUTH_FIELD":'),
    ('    return {"AUTH_FIELD":', '    alias = native\n    alias["token"] = "SYNTHETIC_LITERAL_ONLY"\n    return {"AUTH_FIELD":'),
    ('    return {"AUTH_FIELD":', '    native.update(other)\n    return {"AUTH_FIELD":'),
    ('    return {"AUTH_FIELD":', '    def mutate(value):\n        value["token"] = "SYNTHETIC_LITERAL_ONLY"\n    mutate(native)\n    return {"AUTH_FIELD":'),
    ('jar.load(headers["set-cookie"])', 'jar.load("SYNTHETIC_LITERAL_ONLY")'),
    ('jar.load(headers["set-cookie"])', 'jar.load(headers["set-cookie"])\n    jar.load(other)'),
    ('jar.load(headers["set-cookie"])', 'jar.load(headers["set-cookie"])\n    jar["session"] = "SYNTHETIC_LITERAL_ONLY"'),
    ('jar.load(headers["set-cookie"])', 'jar.load(headers["set-cookie"])\n    alias = jar\n    alias["session"] = "SYNTHETIC_LITERAL_ONLY"'),
    ('jar.load(headers["set-cookie"])', 'headers["set-cookie"] = "SYNTHETIC_LITERAL_ONLY"\n    jar.load(headers["set-cookie"])'),
    ('    jar = SimpleCookie()', '    SimpleCookie = unknown\n    jar = SimpleCookie()'),
    ('native["token"]', 'unknown()'),
], ids=[
    "literal-token", "bearer-payload", "literal-cookie", "cookie-payload",
    "literal-body", "mixed-body", "literal-wrapper-result", "unknown-wrapper-result",
    "decoder-shadow", "decoder-alias-shadow", "response-method-shadow", "connection-method-shadow",
    "helper-shadow", "decorated-helper", "token-write", "token-alias-write", "token-update",
    "local-mutator", "static-cookie-input", "extra-cookie-input", "cookie-write", "cookie-alias-write",
    "header-write", "parser-shadow", "unknown-token",
])
def test_literal_ambiguous_and_mutated_origins_remain_refused(before, after):
    with pytest.raises(ValueError, match="SECRET_DETECTED"):
        scan_secrets(encode_source(changed(before, after)))


def test_safe_prefix_does_not_exempt_an_unrelated_secret():
    with pytest.raises(ValueError, match="SECRET_DETECTED"):
        scan_secrets(encode_source(SOURCE + '\nother = {"PASS_FIELD": "SYNTHETIC_LITERAL_ONLY"}\n'))


@pytest.mark.parametrize("mutation", [
    'alias = json\nalias.load = lambda stream: {"value": "SYNTHETIC_LITERAL_ONLY"}',
    'alias = sys\nalias.stdin = unknown',
    'mapping = json.__dict__\nmapping["load"] = lambda stream: {"value": "SYNTHETIC_LITERAL_ONLY"}',
    'loader = json.load\nloader.__code__ = (lambda stream: {"value": "SYNTHETIC_LITERAL_ONLY"}).__code__',
    'import json as decoder\ndecoder.load = lambda stream: {"value": "SYNTHETIC_LITERAL_ONLY"}',
    'from json import load as loader\nloader.__code__ = (lambda stream: {"value": "SYNTHETIC_LITERAL_ONLY"}).__code__',
    'mapping = sys.modules["json"].__dict__\nmapping["load"] = lambda stream: {"value": "SYNTHETIC_LITERAL_ONLY"}',
], ids=["json-loader-alias", "stdin-stream-alias", "module-dictionary-alias", "loader-code-alias",
        "module-import-alias", "loader-import-alias", "module-registry-alias"])
def test_stdin_module_alias_mutation_cannot_launder_a_cookie_literal(mutation):
    source = (
        "import json, sys\n" + mutation + "\n"
        'values = json.load(sys.stdin)\n'
        'headers = {"COOKIE_FIELD": "session=" + values["value"]}\n'
    )
    with pytest.raises(ValueError, match="SECRET_DETECTED"):
        scan_secrets(encode_source(source))


@pytest.mark.parametrize("headers", [
    '{"COOKIE_FIELD": "session=" + values["value"]}',
    '{"AUTH_FIELD": "Bearer " + values["value"]}',
], ids=["cookie", "bearer"])
def test_canonical_stdin_with_regular_json_calls_remains_supported(headers):
    source = (
        "import json, sys\n"
        "values = json.load(sys.stdin)\n"
        'roundtrip = json.loads(json.dumps(values["value"]))\n'
        "headers = " + headers + "\n"
    )
    scan_secrets(encode_source(source))
