from __future__ import annotations

import datetime as dt
import io
import json

from agent_os.config import default_config
from agent_os.update_advisory import check

NOW = dt.datetime(2026, 9, 19, 6, 0, tzinfo=dt.UTC)


class Response(io.BytesIO):
    pass


def opener_for(tags):
    encoded = json.dumps(
        [{"name": name, "commit": {"sha": sha}} for name, sha in tags]
    ).encode()

    def opener(request, timeout):
        assert request.full_url.startswith("https://api.github.com/")
        assert timeout == 10
        return Response(encoded)

    return opener


def test_default_is_two_days_and_never_installs():
    value = default_config()["update_advisory"]
    assert value["enabled"] is True
    assert value["interval_seconds"] == 172800
    assert value["automatic_install"] is False


def test_check_selects_highest_semver_and_persists_private_state(tmp_path):
    result = check(
        tmp_path,
        default_config(),
        "0.3.0",
        opener=opener_for([
            ("v0.3.0", "a" * 40),
            ("v0.4.0-rc.1", "b" * 40),
            ("v0.4.0", "c" * 40),
        ]),
        now=NOW,
    )
    assert result["status"] == "UPDATE_AVAILABLE"
    assert result["latest_version"] == "0.4.0"
    assert result["automatic_install"] is False
    assert result["metadata_authorizes_mutation"] is False
    assert result["state_persisted"] is True
    assert (tmp_path / "update-advisory.json").stat().st_mode & 0o777 == 0o600


def test_fresh_result_is_reused_without_network(tmp_path):
    check(
        tmp_path,
        default_config(),
        "0.4.0",
        opener=opener_for([("v0.4.0", "d" * 40)]),
        now=NOW,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("network must not be called before the two-day deadline")

    result = check(
        tmp_path,
        default_config(),
        "0.4.0",
        opener=forbidden,
        now=NOW + dt.timedelta(seconds=172799),
    )
    assert result["status"] == "CURRENT"
    assert result["check_performed"] is False
    assert result["cache_reused"] is True


def test_deadline_and_force_trigger_a_fresh_check(tmp_path):
    check(
        tmp_path,
        default_config(),
        "0.4.0",
        opener=opener_for([("v0.4.0", "d" * 40)]),
        now=NOW,
    )
    due = check(
        tmp_path,
        default_config(),
        "0.4.0",
        opener=opener_for([("v0.5.0", "e" * 40)]),
        now=NOW + dt.timedelta(seconds=172800),
    )
    assert due["status"] == "UPDATE_AVAILABLE"
    forced = check(
        tmp_path,
        default_config(),
        "0.5.0",
        force=True,
        opener=opener_for([("v0.5.0", "e" * 40)]),
        now=NOW + dt.timedelta(seconds=172801),
    )
    assert forced["status"] == "CURRENT"
    assert forced["check_performed"] is True


def test_failure_is_sanitized_and_retried_earlier(tmp_path):
    def broken(*args, **kwargs):
        raise RuntimeError("secret-looking provider diagnostic")

    result = check(tmp_path, default_config(), "0.4.0", opener=broken, now=NOW)
    assert result["status"] == "UNAVAILABLE"
    assert result["error_class"] == "RuntimeError"
    assert "diagnostic" not in json.dumps(result)
    assert result["next_check_at"] == "2026-09-19T12:00:00Z"


def test_symlinked_state_target_is_not_followed(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("untouched", encoding="utf-8")
    state = tmp_path / "state"
    state.mkdir()
    (state / "update-advisory.json").symlink_to(outside)
    result = check(
        state,
        default_config(),
        "0.4.0",
        opener=opener_for([("v0.4.0", "f" * 40)]),
        now=NOW,
    )
    assert result["status"] == "CURRENT"
    assert result["state_persisted"] is False
    assert outside.read_text(encoding="utf-8") == "untouched"
