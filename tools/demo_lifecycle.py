#!/usr/bin/env python3
"""Execute a synthetic example in a temporary directory, never in the user's project."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent_os import project


def demonstrate() -> dict:
    with tempfile.TemporaryDirectory(prefix="agentos-demo-") as td:
        root = Path(td) / "project"
        root.mkdir()
        home = Path(td) / "user"
        project.initialize(
            root,
            "Synthetic arithmetic demo",
            ["general"],
            [],
            {
                "purpose": "Demonstrate source-bound project lifecycle with a simple addition function.",
                "current_state": "New temporary directory. No live project is used.",
                "boundaries": "Local maths.py, metadata, documents and checks only.",
                "constraints": "No network, no production, no actual user data.",
            },
        )
        answers = {
            k: "Synthetic local arithmetic fixture; no external authority is implied."
            for k in project.QUESTIONS
        }
        answers.update(
            change_kind="implementation",
            write_paths=["maths.py"],
            acceptance=[
                {
                    "id": "A1",
                    "criterion": "The implementation adds 2 and 3 and returns exactly 5.",
                    "checks": ["addition"],
                }
            ],
            checks=[
                {
                    "id": "addition",
                    "argv": [
                        sys.executable,
                        "-c",
                        'from maths import add; assert add(2, 3) == 5; print("addition: PASS")',
                    ],
                    "timeout": 30,
                }
            ],
        )
        entered = project.enter(
            root,
            answers,
            session_id="demo-session",
            turn_id="demo-turn",
            user_home=home,
        )
        task = entered["task_id"]
        early = project.check_ready(root, task)
        assert early["status"] == "BLOCKED"
        for doc_id in entered["required_documents"]["required"]:
            rel = f"docs/agentos/DEMO-{doc_id}.md"
            text = f"""# Synthetic demo: {doc_id}\n\nTask: {task}\n\nThe only implementation is maths.py:add.
Purpose: add two integers and return their sum. Scope is local arithmetic, not a service.
Verification: execute the addition check on the current source, assert add(2,3)==5.
Rollback: remove the temporary example directory. No existing data is changed.
Next stage: the next real task starts with a new intake. No target deployment is claimed.
"""
            (root / rel).write_text(text)
            project.register_document(
                root,
                doc_id,
                rel,
                "Demo reviewer",
                "This temporary synthetic fixture",
                "Reviewed only the arithmetic example scope.",
                task if doc_id == "stage" else None,
            )
        assert project.ready(root, task, "Demo reviewer")["status"] == "READY"
        (root / "maths.py").write_text("def add(a, b):\n    return a + b\n")
        receipt = project.run_check(root, task, "addition")
        assert receipt["status"] == "PASS"
        result = project.close(
            root,
            task,
            {
                "reviewer": "Demo reviewer",
                "summary": "Exact synthetic addition criterion verified.",
                "next_step": "Start a new intake for any real project work.",
                "limitations": "Only synthetic local fixture, no native client or target device.",
                "scope_reviewed": True,
                "accepted_criteria": ["A1"],
                "reviewed_documents": entered["required_documents"]["required"],
                "deployment_status": "not_requested",
            },
        )
        assert result["status"] == "CLOSED"
        return {
            "status": "PASS",
            "fixture": "synthetic temporary arithmetic project",
            "early_gate": early["status"],
            "check": receipt["status"],
            "closeout": result["status"],
            "external_runtime_proven": False,
        }


if __name__ == "__main__":
    print(json.dumps(demonstrate(), ensure_ascii=False, indent=2))
