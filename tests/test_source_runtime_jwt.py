"""Static preservation fixtures, never execute JWT/source or read credentials."""
from __future__ import annotations

import hashlib
import sys

import pytest

from agent_os.handoff import Library, local_principal
from agent_os.handoff_store import HandoffError, _source_literal_spans, scan_secrets

BASE = '''import jwt
from external_config import settings
token = jwt.encode({"sub": str(user_id)}, settings.jwt_secret, algorithm="HS256")
headers = {"AUTH_FIELD": "Bearer " + token}
'''


def source(text):
    return text.replace("AUTH_FIELD", "Authorization").replace("PASS_FIELD", "password").encode()


@pytest.mark.parametrize("text", [
    BASE,
    BASE.replace("import jwt", "import jwt as signer").replace("jwt.encode", "signer.encode"),
    BASE.replace('algorithm="HS256"', "algorithm=settings.jwt_algorithm"),
    BASE.replace('"Bearer " + token', '"Bearer " + (token)'),
    BASE.replace("headers =", "alias = token\nheaders =").replace('"Bearer " + token', '"Bearer " + alias'),
    'label = "λ"\n' + BASE,
    BASE.replace("token =", "def make_headers():\n    token =").replace("\nheaders =", "\n    headers ="),
    BASE.replace('"sub": str(user_id)', '"sub": str(user_id), "exp": clock.now()'),
])
def test_proven_runtime_jwt_source_preserved(text):
    scan_secrets(source(text))


@pytest.mark.parametrize("text", [
    BASE.replace("import jwt\n", ""),
    BASE.replace("import jwt", "import foreign_module as jwt"),
    BASE.replace("import jwt", "from foreign_module import jwt"),
    BASE.replace("import jwt", "from . import jwt"),
    BASE.replace("import jwt", "from jwt import *"),
    BASE.replace("from external_config import settings\n", ""),
    BASE.replace("settings.jwt_secret", '"synthetic-signing-key"'),
    BASE.replace("settings.jwt_secret", 'str("synthetic-signing-key")'),
    BASE.replace("settings.jwt_secret", "get_key()"),
    BASE.replace("settings.jwt_secret", "signing_key"),
    BASE.replace("token =", 'signing_key = "synthetic-signing-key"\ntoken =').replace("settings.jwt_secret", "signing_key"),
    BASE.replace("token =", 'settings.jwt_secret = "synthetic-signing-key"\ntoken ='),
    BASE.replace("token =", 'cfg = settings\ncfg.jwt_secret = "synthetic-signing-key"\ntoken ='),
    BASE.replace("token =", 'jwt = fake_module\ntoken ='),
    BASE.replace("token =", 'jwt.encode = lambda *a, **k: "synthetic-value"\ntoken ='),
    BASE.replace("token =", 'jwt.__dict__["encode"] = fake_encoder\ntoken ='),
    BASE.replace("token =", 'alias = jwt\nalias.encode = fake_encoder\ntoken ='),
    BASE.replace("token =", 'encoder = jwt.encode\ntoken =').replace('token = jwt.encode', 'token = encoder'),
    BASE.replace("token =", 'setattr(jwt, "encode", fake_encoder)\ntoken ='),
    BASE.replace("token =", 'setattr(settings, "jwt_secret", "synthetic-signing-key")\ntoken ='),
    BASE.replace("token =", 'monkeypatch.setattr("jwt.encode", fake_encoder)\ntoken ='),
    BASE.replace("token =", 'monkeypatch.setattr("external_config.settings.jwt_secret", "synthetic-signing-key")\ntoken ='),
    BASE.replace("token =", 'globals()["jwt"] = fake_module\ntoken ='),
    BASE.replace("token =", 'def f(jwt):\n    return jwt\ntoken ='),
    BASE.replace("token =", 'def f(settings):\n    return settings\ntoken ='),
    BASE.replace("token =", 'def mutate():\n    jwt.encode = fake_encoder\ntoken ='),
    BASE.replace("token =", 'token = "synthetic-value"\ntoken ='),
    BASE.replace("headers =", 'token += "synthetic-tail"\nheaders ='),
    BASE.replace("headers =", 'alias = "synthetic-value"\nheaders =').replace('"Bearer " + token', '"Bearer " + alias'),
    BASE.replace('"Bearer " + token', '"Bearer " + (token + "synthetic-tail")'),
    BASE.replace('"Bearer " + token', '"Bearer " + generate_token()'),
    BASE.replace('"Bearer " + token', '"Bearer " + (lambda: "synthetic-value")()'),
    BASE.replace('"Bearer " + token', '"Bearer " + f"{token}"'),
    BASE.replace('"Bearer " + token', '"Bearer synthetic-value"'),
    BASE.replace('algorithm="HS256"', 'algorithm="none"'),
    BASE.replace('algorithm="HS256"', 'algorithm=get_algorithm()'),
    BASE.replace(', algorithm="HS256"', ''),
    BASE.replace('algorithm="HS256"', 'algorithm="HS256", extra=unknown'),
    BASE.replace('{"sub": str(user_id)}', '"synthetic-value"'),
    BASE.replace('{"sub": str(user_id)}', '{**payload}'),
    BASE.replace('{"sub": str(user_id)}', '{"PASS_FIELD": "synthetic-value"}'),
    BASE.replace('headers =', 'jwt.decode(data, settings.jwt_secret)\nheaders ='),
    BASE + 'jwt = fake_module\n',
    BASE + 'settings.jwt_secret = "synthetic-signing-key"\n',
    BASE + 'headers2 = {"PASS_FIELD": "synthetic-value"}\n',
    BASE + 'headers2 = {"AUTH_FIELD": "Bearer synthetic-other"}\n',
    BASE.replace("token =", 'from unittest.mock import patch\npatch("jwt.encode", return_value="synthetic-value")\ntoken ='),
    BASE.replace("token =", 'mocker.patch("jw" + "t.encode", return_value="synthetic-value")\ntoken ='),
    BASE.replace("token =", 'import importlib\nimportlib.import_module("jw" + "t").encode = fake_encoder\ntoken ='),
    BASE.replace("token =", 'monkeypatch.setattr("jw" + "t.encode", fake_encoder)\ntoken ='),
    BASE.replace("token =", 'target_name="jwt.encode"\nunknown_replace(target_name, fake_encoder)\ntoken ='),
    BASE.replace("token =", 'match incoming:\n    case jwt:\n        pass\ntoken ='),
    BASE.replace("token =", 'match incoming:\n    case [*jwt]:\n        pass\ntoken ='),
    BASE.replace("token =", 'match incoming:\n    case {"item": item, **jwt}:\n        pass\ntoken ='),
    BASE.replace("token =", 'match incoming:\n    case settings:\n        pass\ntoken ='),
    BASE.replace("token =", 'class Generic[jwt]:\n    pass\ntoken ='),
    BASE.replace("token =", 'type Alias[**settings] = object\ntoken ='),
    BASE.replace("token =", 'type Alias[*jwt] = tuple\ntoken ='),
    BASE.replace("token =", 'settings.encode("synthetic-signing-key")\ntoken ='),
    BASE.replace("settings", "config").replace("token =", 'config.encode("synthetic-signing-key")\ntoken ='),
    BASE.replace("from external_config import settings", "import jwt as settings").replace("token =", 'settings.encode("synthetic-signing-key")\ntoken ='),
    BASE.replace("token =", 'from builtins import exec as run\nrun("jw" + "t=substitute")\ntoken ='),
    BASE.replace("token =", 'import builtins as b\nb.exec("jw" + "t=substitute")\ntoken ='),
    BASE.replace("token =", 'run=exec\nrun("jw" + "t=substitute")\ntoken ='),
    BASE.replace("token =", 'import sys\nsys.modules[name].encode = substitute\ntoken =').replace('import sys\n', 'import sys\nregistry=sys._getframe().f_globals\n'),
    BASE.replace('"Bearer " + token}', '"Bearer " + token'),
])
def test_ambiguous_or_literal_origins_remain_refused(text):
    with pytest.raises(HandoffError, match="SECRET_DETECTED"):
        scan_secrets(source(text))


def test_only_exact_public_prefix_span_is_recognized():
    raw = source(BASE)
    spans = _source_literal_spans(raw)
    assert len(spans) == 1
    start, end = next(iter(spans))
    assert raw[start:end] == b'"Bearer "'
    assert "jwt_secret" in raw.decode() and not any(start <= raw.index(b"jwt_secret") < end for start, end in spans)


def test_raw_recognizable_key_is_never_masked_even_with_proven_origin():
    raw = source(BASE) + b"\n# " + b"sk-" + b"x" * 24
    with pytest.raises(HandoffError, match="SECRET_DETECTED"):
        scan_secrets(raw)


def test_import_call_and_source_budgets_fail_closed():
    imports = "".join(f"import module{i}\n" for i in range(65))
    calls = "".join(f't{i}=jwt.encode({{}}, settings.jwt_secret, algorithm="HS256")\n' for i in range(65))
    for text in [imports + BASE, BASE.replace("headers =", calls + "headers ="), BASE + "#" * (2 * 1024 * 1024), BASE + "x=0\n" * 25000]:
        with pytest.raises(HandoffError, match="SECRET_DETECTED"):
            scan_secrets(source(text))


def test_source_is_never_imported_or_executed():
    marker = "runtime_jwt_source_must_not_execute"
    before = set(sys.modules)
    scan_secrets(source(f'raise RuntimeError("{marker}")\n' + BASE))
    assert set(sys.modules) - before <= {"agent_os.source_runtime_jwt"}


def test_unrelated_imported_target_patch_does_not_reclassify_encoder():
    text = BASE.replace("token =", 'import external_api as api\nmonkeypatch.setattr(api, "handler", replacement)\ntoken =')
    scan_secrets(source(text))


def test_actual_indexed_checkpoint_preserves_and_restores_exact_source(tmp_path):
    from test_foundation import documents, start, setup as fixture_setup
    from agent_os import project
    root, home, answers = fixture = fixture_setup.__wrapped__(tmp_path)
    task = start(fixture)
    documents(fixture, task)
    raw = source(BASE)
    (root / "code.py").write_bytes(raw)
    before = hashlib.sha256(raw).hexdigest()
    result = project.checkpoint(root, task, "Synthetic source incomplete", "Continue original authorized work")
    assert result["complete"] is False
    library = Library(home / "results-library")
    resolved = library.resolve("handoff:" + task, local_principal())
    assert resolved["manifest"]["facets"]["result_type"] == "checkpoint"
    restored = tmp_path / "restored"
    library.restore("handoff:" + task, restored, local_principal())
    assert (restored / "source/code.py").read_bytes() == raw
    assert hashlib.sha256((root / "code.py").read_bytes()).hexdigest() == before


@pytest.mark.parametrize("key,allowed", [
    ("settings.jwt_secret", True),
    ('"synthetic-signing-key"', False),
    ("get_key()", False),
])
def test_local_helper_return_cannot_launder_a_literal_jwt_key(key, allowed):
    text = f'''import jwt
from external_config import settings
class Factory:
    def token(self):
        token = jwt.encode({{"sub": str(user_id)}}, {key}, algorithm="HS256")
        return 1, token, 2
_, token, _ = Factory().token()
headers = {{"AUTH_FIELD": "Bearer " + token}}
'''
    if allowed:
        scan_secrets(source(text))
    else:
        with pytest.raises(HandoffError, match="SECRET_DETECTED"):
            scan_secrets(source(text))


def test_alternate_encoding_cannot_shift_prefix_span_over_another_field():
    # Construct a fake field in a comment. Latin-1 and AST UTF-8 offsets differ
    # by exactly the count of accented characters preceding the public prefix.
    intro = BASE.split("headers =", 1)[0]
    def sample(count):
        return source('# coding: latin-1\n' + intro + 'label="' + 'é' * count
                      + '"; headers={"AUTH_FIELD":u"Bearer "+token} # "PASS_FIELD": "p4ssw0rd"\n').decode().encode("latin-1")
    raw = sample(0)
    count = raw.index(b'"p4ssw0rd"') - raw.index(b'u"Bearer "')
    with pytest.raises(HandoffError, match="SECRET_DETECTED"):
        scan_secrets(sample(count))
