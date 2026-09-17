from __future__ import annotations

import pytest

from agent_os.config import default_config
from agent_os.model_routing import route_task


@pytest.mark.parametrize(
    ("mode", "complexity", "role", "profile"),
    [
        ("implementation", "medium", "root", "coordinator"),
        ("implementation", "medium", "worker", "worker"),
        ("classification", "low", "worker", "fast"),
        ("review", "medium", "verifier", "reviewer"),
        ("anything", "high", "worker", "coordinator"),
        ("anything", "critical", "root", "critical"),
    ],
)
def test_model_route_matrix(mode, complexity, role, profile):
    result = route_task(default_config(), mode=mode, complexity=complexity, role=role)
    assert result["profile"] == profile
    assert result["runtime_proof_required"] is True
    assert result["delegate_by_default"] is False


def test_critical_profile_is_root_only():
    with pytest.raises(ValueError, match="root_only"):
        route_task(default_config(), mode="analysis", complexity="critical", role="worker")
