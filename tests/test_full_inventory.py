from __future__ import annotations

import json

import pytest

from agent_os.full_inventory import FullInventoryError, collect, select, write_result


def write_catalog(path, root):
    path.write_text(
        json.dumps(
            {
                "schema": "agent-os.full-inventory-catalog/v1",
                "catalog_id": "test",
                "projects": [
                    {
                        "project_id": "demo",
                        "host_id": "local",
                        "root": str(root.resolve()),
                        "policy_paths": ["AGENTS.md"],
                        "roadmap_paths": ["ROADMAP.json"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_collect_and_select_are_content_free_and_history_is_opt_in(tmp_path):
    root = (tmp_path / "project").resolve()
    root.mkdir()
    (root / "AGENTS.md").write_text("policy", encoding="utf-8")
    (root / "ROADMAP.json").write_text("{}", encoding="utf-8")
    (root / "knowledge" / "problems").mkdir(parents=True)
    (root / "knowledge" / "problems" / "known.md").write_text("problem", encoding="utf-8")
    (root / "history").mkdir()
    (root / "history" / "old.md").write_text("history", encoding="utf-8")
    catalog = (tmp_path / "catalog.json").resolve()
    write_catalog(catalog, root)

    inventory = collect(catalog)
    assert inventory["status"] == "PASS"
    assert inventory["contents_included"] is False
    assert inventory["history_auto_loaded"] is False
    inventory_path = (tmp_path / "inventory.json").resolve()
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")

    chosen = select(inventory_path, project_id="demo")
    assert chosen["status"] == "PASS"
    assert "history" not in chosen["classes"]
    assert all(item["class"] != "history" for item in chosen["artifacts"])
    assert all("content" not in item and "contents" not in item for item in chosen["artifacts"])
    assert all(item["sha256"] != "policy" for item in chosen["artifacts"])


def test_missing_policy_is_visible(tmp_path):
    root = (tmp_path / "project").resolve()
    root.mkdir()
    catalog = (tmp_path / "catalog.json").resolve()
    write_catalog(catalog, root)
    result = collect(catalog)
    assert result["status"] == "PARTIAL"
    assert result["projects"][0]["missing_required"] == ["AGENTS.md"]


def test_symlinked_knowledge_is_rejected(tmp_path):
    root = (tmp_path / "project").resolve()
    root.mkdir()
    (root / "AGENTS.md").write_text("policy", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    (root / "knowledge").mkdir()
    (root / "knowledge" / "problems").symlink_to(outside.parent, target_is_directory=True)
    catalog = (tmp_path / "catalog.json").resolve()
    write_catalog(catalog, root)
    with pytest.raises(FullInventoryError):
        collect(catalog)


def test_tampered_inventory_is_rejected(tmp_path):
    root = (tmp_path / "project").resolve()
    root.mkdir()
    (root / "AGENTS.md").write_text("policy", encoding="utf-8")
    catalog = (tmp_path / "catalog.json").resolve()
    write_catalog(catalog, root)
    inventory = collect(catalog)
    inventory["file_count"] = 999
    inventory_path = (tmp_path / "inventory.json").resolve()
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    with pytest.raises(FullInventoryError):
        select(inventory_path, project_id="demo")


def test_inventory_output_does_not_follow_symlink(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("untouched", encoding="utf-8")
    output = tmp_path / "output.json"
    output.symlink_to(outside)
    with pytest.raises(FullInventoryError):
        write_result(output, {"status": "PASS"})
    assert outside.read_text(encoding="utf-8") == "untouched"
