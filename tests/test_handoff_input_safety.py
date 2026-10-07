"""Synthetic scanner and CLI-input checks; no real credentials or owner data."""

import io
import json
import sys

import pytest

from agent_os.handoff import Library, local_principal
from agent_os.handoff_cli import command
from agent_os.handoff_store import HandoffError, scan_secrets
from agent_os.safeio import MAX_JSON, GateError


@pytest.mark.parametrize(
    "source",
    [
        '{"AUTH_FIELD": "Bearer " + generated_token}',
        '{"AUTH_FIELD": "Bearer " + token["access_token"]}',
        'token = os.environ["TOKEN"]\nheaders = {"AUTH_FIELD": "Bearer " + token}',
        '_, token, _ = self.token("scope")\nheaders = {"AUTH_FIELD": "Bearer " + token["access_token"]}',
        '{"AUTH_FIELD": "Bearer " + self.token}',
        'label = "\u03bb"\nheaders = {"AUTH_FIELD": ("Bearer " + token)}',
        'type:C&&"PWD_FIELD"===C?"PWD_FIELD":"text",value:userValue',
        "type:format&&'PWD_FIELD'===format?'PWD_FIELD':'text',value:v",
    ],
)
def test_proven_noncredential_source_literals(source):
    scan_secrets(
        source.replace("AUTH_FIELD", "Authorization")
        .replace("PWD_FIELD", "password")
        .replace("ACCESS_FIELD", "access_token")
        .encode()
    )


@pytest.mark.parametrize(
    "field",
    ["password", "access_token", "refresh_token", "api_key", "cookie", "authorization"],
)
def test_literal_sensitive_values_still_rejected(field):
    value = json.dumps({field: "synthetic-credential-value"}).encode()
    with pytest.raises(HandoffError, match="SECRET_DETECTED"):
        scan_secrets(value)


@pytest.mark.parametrize(
    "source",
    [
        '{"AUTH_FIELD": "Bearer " + "synthetic-static-value"}',
        '{"AUTH_FIELD": "Bearer " + generated_token()}',
        'token = str("synthetic-static-value")\nheaders = {"AUTH_FIELD": "Bearer " + token}',
        'token = "{}".format("synthetic-static-value")\nheaders = {"AUTH_FIELD": "Bearer " + token}',
        'token = {"other": "synthetic-static-value"}.get()\nheaders = {"AUTH_FIELD": "Bearer " + token}',
        'self.token = "synthetic-value"\nheaders = {"AUTH_FIELD": "Bearer " + self.token}',
        'cfg["token"] = "synthetic-value"\nheaders = {"AUTH_FIELD": "Bearer " + cfg["token"]}',
        'token = runtime_value\ntoken += "synthetic-value"\nheaders = {"AUTH_FIELD": "Bearer " + token}',
        'cfg.api_key = "synthetic-value"\nheaders = {"AUTH_FIELD": "Bearer " + cfg.api_key}',
        'def token():\n    return "synthetic-value"\nheaders = {"AUTH_FIELD": "Bearer " + token()}',
        'token = lambda: "synthetic-value"\nheaders = {"AUTH_FIELD": "Bearer " + token()}',
        '_, token, _ = ("a", "synthetic-value", "b")\nheaders = {"AUTH_FIELD": "Bearer " + token}',
        'helper=lambda: ("a", "synthetic-value", "b")\ndef token():\n    return helper()\n_, token, _ = self.token()\nheaders = {"AUTH_FIELD": "Bearer " + token}',
        'def helper():\n    return ("a", "synthetic-value", "b")\ndef token():\n    return helper()\n_, token, _ = self.token()\nheaders = {"AUTH_FIELD": "Bearer " + token}',
        'def token():\n    yield "a"\n    yield "synthetic-value"\n    yield "b"\n_, token, _ = self.token()\nheaders = {"AUTH_FIELD": "Bearer " + token}',
        'def token():\n    yield from ("a", "synthetic-value", "b")\n_, token, _ = self.token()\nheaders = {"AUTH_FIELD": "Bearer " + token}',
        'def token():\n    return "a", "synthetic-value", "b"\n_, token, _ = self.token()\nheaders = {"AUTH_FIELD": "Bearer " + token}',
        '{"AUTH_FIELD": "Bearer " + (token + "literal-tail")}',
        '{"AUTH_FIELD": "Bearer synthetic-value"}',
        '{"AUTH_FIELD": ("Bearer synthetic-value")}',
        '{"AUTH_FIELD": (("Bearer synthetic-value"))}',
        'generated_token = "synthetic-value"\nheaders = {"AUTH_FIELD": "Bearer " + generated_token}',
        'token = {"ACCESS_FIELD": "synthetic-value"}\nheaders = {"AUTH_FIELD": "Bearer " + token["access_token"]}',
        'value = "synthetic-value"\nheaders = {"AUTH_FIELD": value}',
        '{"AUTH_FIELD": "Bearer "}',
        '{"AUTH_FIELD": "Bearer " + f"{token}"}',
        '{"PWD_FIELD": "text"}',
        'type:C&&"PWD_FIELD"===other?"PWD_FIELD":"text",value:v',
        'type:C&&"PWD_FIELD"===C?"PWD_FIELD":"credential",value:v',
        'type:C&&"PWD_FIELD"===C?"PWD_FIELD":"text"+"credential",value:v',
        'headers = {"AUTH_FIELD": "Bearer " + token',
    ],
)
def test_ambiguous_or_static_source_values_fail_closed(source):
    with pytest.raises(HandoffError, match="SECRET_DETECTED"):
        scan_secrets(
            source.replace("AUTH_FIELD", "Authorization")
            .replace("PWD_FIELD", "password")
            .replace("ACCESS_FIELD", "access_token")
            .encode()
        )


def test_safe_span_never_masks_another_secret_or_key():
    safe = '{"AUTH_FIELD": "Bearer " + generated_token}\n'.replace(
        "AUTH_FIELD", "Authorization"
    )
    for extra in [
        json.dumps({"PWD_FIELD": "synthetic-value"})
        .replace("PWD_FIELD", "password")
        .replace("ACCESS_FIELD", "access_token"),
        "# " + "sk-" + "a" * 32,
    ]:
        with pytest.raises(HandoffError, match="SECRET_DETECTED"):
            scan_secrets((safe + extra).encode())


def stdin(monkeypatch, payload):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(payload)))


@pytest.fixture
def cli_library(tmp_path):
    root = tmp_path / "library"
    Library.create(root, local_principal())
    return root


def search(root, query):
    return command(["--root", str(root), "search", "--query", str(query)])


def test_cli_query_file_and_stdin_work(cli_library, tmp_path, monkeypatch):
    value = {"filters": {"entity_id": "synthetic-missing-task"}}
    path = tmp_path / "query.json"
    path.write_text(json.dumps(value))
    assert search(cli_library, path)["results"] == []
    stdin(monkeypatch, json.dumps(value).encode())
    assert search(cli_library, "-")["results"] == []


@pytest.mark.parametrize(
    "argument", ['{"entity_id":"synthetic-task"}', "synthetic-task", "missing.json"]
)
def test_bad_cli_argument_is_input_error(cli_library, argument):
    with pytest.raises(HandoffError, match="^INVALID_JSON_INPUT$"):
        search(cli_library, argument)


@pytest.mark.parametrize(
    "payload",
    [b"{invalid", b'{"x":1,"x":2}', b"[]", b'"scalar"', b"\xff", b"x" * (MAX_JSON + 1)],
)
def test_bad_cli_stdin_is_input_error(cli_library, monkeypatch, payload):
    stdin(monkeypatch, payload)
    with pytest.raises(HandoffError, match="^INVALID_JSON_INPUT$"):
        search(cli_library, "-")


def test_cli_symlink_directory_and_corrupt_root_distinction(
    cli_library, tmp_path, monkeypatch
):
    file = tmp_path / "input.json"
    file.write_text("{}")
    link = tmp_path / "linked.json"
    link.symlink_to(file)
    for bad in (link, tmp_path):
        with pytest.raises(HandoffError, match="^INVALID_JSON_INPUT$"):
            search(cli_library, bad)
    root = json.loads((cli_library / "ROOT.json").read_text())
    digest = root["routes_ref"]["object_id"].split(":")[1]
    (cli_library / "objects/sha256" / digest[:2] / digest).write_text("corrupted")
    stdin(monkeypatch, b"{}")
    with pytest.raises(HandoffError, match="^INTEGRITY_FAILED$"):
        search(cli_library, "-")


def test_terminal_checkpoint_preserves_safe_code_and_blocks_real_secret(tmp_path):
    from test_foundation import documents, start
    from test_foundation import setup as setup_fixture

    from agent_os import project

    root, home, _answers = fixture = setup_fixture.__wrapped__(tmp_path)
    task = start(fixture)
    documents(fixture, task)
    source = '{"AUTH_FIELD": "Bearer " + generated_token}\n'.replace(
        "AUTH_FIELD", "Authorization"
    )
    (root / "code.py").write_text(source)
    result = project.checkpoint(
        root, task, "Synthetic implementation incomplete", "Continue safe work"
    )
    assert result["complete"] is False
    restored = tmp_path / "restored"
    Library(home / "results-library").restore(
        "handoff:" + task, restored, local_principal()
    )
    assert (restored / "source/code.py").read_text() == source

    other = tmp_path / "negative"
    other.mkdir()
    r, _home, _answers = f = setup_fixture.__wrapped__(other)
    t = start(f)
    documents(f, t)
    (r / "code.py").write_text(
        json.dumps({"PWD_FIELD": "synthetic-credential"}).replace(
            "PWD_FIELD", "password"
        )
    )
    with pytest.raises(GateError, match="SECRET_DETECTED"):
        project.checkpoint(r, t, "Synthetic unfinished", "Continue")
    assert project.load_task(r, t)["status"] != "CHECKPOINT"


def test_alias_graph_is_bounded_and_fails_closed():
    source = (
        "x0 = runtime_token\n"
        + "\n".join(f"x{i} = x{i - 1}\nx{i} = x{i - 1}" for i in range(1, 24))
        + '\nheaders = {"AUTH_FIELD": "Bearer " + x23}'
    )
    with pytest.raises(HandoffError, match="SECRET_DETECTED"):
        scan_secrets(source.replace("AUTH_FIELD", "Authorization").encode())


def test_tuple_runtime_component_uses_its_own_function_scope():
    source = """
class Fixture:
    def token(self):
        client = self.register()
        token = external.exchange_token(self.db, {"scope": "read"})
        query = external.query()
        return client, token, query
    def unrelated(self):
        token = "synthetic-unrelated-value"
    def run(self):
        _, token, _ = self.token("scope")
        headers = {"AUTH_FIELD": "Bearer " + token["access_token"]}
"""
    scan_secrets(source.replace("AUTH_FIELD", "Authorization").encode())
