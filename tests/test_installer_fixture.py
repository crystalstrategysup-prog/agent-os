"""The installer self-test must not copy Python headers into legacy fixtures."""

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "agentos_installer_self_test", Path(__file__).resolve().parents[1] / "tools/test_installation.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
launcher_prefix = _MODULE.launcher_prefix


@pytest.mark.parametrize(
    "prefix",
    [
        "#!/tmp/venv/bin/python\n",
        "#!/bin/sh\n'''exec' \"/tmp/with space/venv/bin/python\" \"$0\" \"$@\"\n' '''\n",
        "#!/bin/sh\n'''exec' /tmp/venv/bin/python \"$0\" \"$@\"\n' '''\n",
    ],
)
@pytest.mark.parametrize(
    "header",
    [
        "import sys\n",
        "# -*- coding: utf-8 -*-\nimport re\nimport sys\n",
    ],
)
def test_launcher_prefix_discards_python_header(prefix: str, header: str) -> None:
    body = prefix + header + "from agent_os.cli import main\n"
    assert launcher_prefix(body) == prefix


@pytest.mark.parametrize(
    "body",
    [
        "import sys\nfrom agent_os.cli import main\n",
        "#!/bin/sh\n'''exec' /tmp/venv/bin/python \"$0\" \"$@\"\nimport sys\n",
    ],
)
def test_launcher_prefix_rejects_missing_or_partial_shebang(body: str) -> None:
    with pytest.raises(ValueError):
        launcher_prefix(body)
