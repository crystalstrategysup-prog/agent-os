"""Small, deterministic task normalization boundary."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TaskBrief:
    task_id: str
    objective: str
    target: str
    risk: str

    def as_dict(self) -> dict[str, str]:
        return {
            "schema": "agent-os.task-brief/v1",
            "task_id": self.task_id,
            "objective": self.objective,
            "target": self.target,
            "risk": self.risk,
        }


def normalize_task(objective: str, target: str = "local", risk: str = "R0") -> TaskBrief:
    clean = " ".join(objective.split())
    if not 1 <= len(clean) <= 2_000:
        raise ValueError("objective_length_invalid")
    if target not in {"local", "remote", "custom"}:
        raise ValueError("target_not_allowed")
    if risk not in {"R0", "R1", "R2", "R3", "R4", "R5"}:
        raise ValueError("risk_not_allowed")
    material = json.dumps([clean, target, risk], ensure_ascii=False, separators=(",", ":"))
    task_id = "task_" + hashlib.sha256(material.encode()).hexdigest()[:16]
    return TaskBrief(task_id, clean, target, risk)
