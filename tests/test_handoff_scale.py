"""An actual 100k accepted-package fixture, not a label on mocked index rows."""

import copy
import json
import os
import tempfile
import time
from pathlib import Path

from test_indexed_handoff import P, make

from agent_os.handoff import Library
from agent_os.handoff_lifecycle import TOPICS
from agent_os.handoff_store import MAX_ROOT, PAGE_BYTES, bounded


def test_100000_actual_accepted_packages_exact_id_page_budget():
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="agentos-synthetic-100k-") as folder:
        lib = Library.create(Path(folder) / "library", P, topics=TOPICS)
        template, assets = make(lib, 0)

        def works():
            for n in range(100_000):
                m = copy.deepcopy(template)
                m["handoff_id"] = f"handoff:{n:06d}"
                m["entity"]["entity_id"] = f"work:{n:06d}"
                m["evidence"][0]["source_ref"]["source_id"] = m["entity"]["entity_id"]
                m["facets"]["project_id"] = [f"project:{n % 100}"]
                yield m, None

        refs = lib.build_batch(works(), P, assets=assets)
        receipt = lib.publish_batch(refs, 0, "synthetic-100k-publication", P)
        assert receipt["accepted_count"] == 100_000
        samples = []
        for n in [0, 49_999, 99_999]:
            result = Library(lib.path).resolve(f"handoff:{n:06d}", P)
            assert result["row"]["manifest_ref"] == refs[n]
            assert result["metrics"]["entry_files"] <= 3
            assert result["metrics"]["index_pages"] <= 4
            assert result["metrics"]["directory_walks"] == 0
            samples.append(result["metrics"])
        count = 0
        cursor = None
        query = {"filters": {"project_id": "project:37"}, "limit": 200}
        while True:
            page = lib.search(query, P, cursor=cursor)
            assert page["coverage"]["status"] == "complete"
            for row in page["results"]:
                assert int(row["handoff_id"].split(":")[1]) % 100 == 37
            count += len(page["results"])
            cursor = page["next_cursor"]
            if cursor is None:
                break
        assert count == 1000
        root = lib._authorize(P)
        root_bytes = len(bounded(lib.path / "ROOT.json", MAX_ROOT))
        routes_bytes = len(lib.store.get(root["routes_ref"], limit=128 * 1024))
        assert root_bytes <= MAX_ROOT and routes_bytes <= 128 * 1024
        result = {
            "actual_accepted_packages": receipt["accepted_count"],
            "oracle_project_matches": count,
            "root_bytes": root_bytes,
            "routes_bytes": routes_bytes,
            "page_bytes_limit": PAGE_BYTES,
            "samples": samples,
            "seconds": round(time.monotonic() - started, 3),
        }
        evidence = os.environ.get("AGENTOS_HANDOFF_EVIDENCE_DIR")
        if evidence:
            Path(evidence).mkdir(parents=True, exist_ok=True)
            (Path(evidence) / "scale.json").write_text(
                json.dumps(result, indent=2) + "\n"
            )
