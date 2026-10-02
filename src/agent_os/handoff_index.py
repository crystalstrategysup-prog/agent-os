"""Bounded sorted page trees and exact posting lists. Ordinary reads never walk files."""

from __future__ import annotations

import re
import unicodedata

from .handoff_store import NORMALIZER, PAGE_BYTES, Store, encoded, require

DIMENSIONS = (
    "handoff_id",
    "entity_id",
    "project_id",
    "stage_id",
    "topic_id",
    "related_entity_id",
    "decision_id",
    "task_id",
    "result_type",
    "state",
    "updated_at",
    "lexical",
)


def normalize(value: str) -> str:
    require(isinstance(value, str), "INVALID_QUERY")
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFC", value).casefold()))


def words(value: str):
    return sorted(set(normalize(value).split()))


class Tree:
    def __init__(self, store: Store, generation: int, seq: int):
        self.store, self.generation, self.seq = store, generation, seq
        self.cache = {}

    def _page(self, kind, entries):
        return {
            "schema": "aos.index-page/v1",
            "generation": self.generation,
            "indexed_through_seq": self.seq,
            "normalizer": NORMALIZER,
            "kind": kind,
            "entries": entries,
        }

    def build(self, items):
        """Items must be unique and sorted; split by encoded size, not counts."""
        items = list(items)
        require(
            items == sorted(items, key=lambda item: item[0])
            and len({key for key, _ in items}) == len(items),
            "INDEX_STALE",
        )

        def layer(kind, values):
            pages = []
            batch = []
            size = len(encoded(self._page(kind, [])))
            for item in values:
                item_size = len(encoded(item)) + 1
                require(item_size + 256 <= PAGE_BYTES, "INDEX_ENTRY_LIMIT")
                if batch and size + item_size > PAGE_BYTES - 128:
                    ref = self.store.put_json(self._page(kind, batch), limit=PAGE_BYTES)
                    pages.append((batch[-1][0], ref))
                    batch = []
                    size = 256
                batch.append(item)
                size += item_size
            if batch or not pages:
                ref = self.store.put_json(self._page(kind, batch), limit=PAGE_BYTES)
                pages.append((batch[-1][0] if batch else "", ref))
            return pages

        pages = layer("leaf", items)
        while len(pages) > 1:
            pages = layer("branch", pages)
        return pages[0][1]

    def read(self, ref):
        oid = ref["object_id"]
        if oid not in self.cache:
            page = self.store.json(ref, limit=PAGE_BYTES)
            require(page.get("schema") == "aos.index-page/v1", "UNSUPPORTED_SCHEMA")
            require(
                page.get("generation") == self.generation
                and page.get("indexed_through_seq") == self.seq
                and page.get("normalizer") == NORMALIZER,
                "INDEX_STALE",
            )
            require(
                page.get("kind") in {"leaf", "branch"}
                and isinstance(page.get("entries"), list),
                "INDEX_STALE",
            )
            entries = page["entries"]
            require(
                all(
                    isinstance(row, list) and len(row) == 2 and isinstance(row[0], str)
                    for row in entries
                ),
                "INDEX_STALE",
            )
            keys = [row[0] for row in entries]
            require(keys == sorted(set(keys)), "INDEX_STALE")
            self.cache[oid] = page
            self.store.metrics["index_pages"] += 1
        return self.cache[oid]

    def find(self, ref, key):
        page = self.read(ref)
        if page["kind"] == "leaf":
            for name, value in page["entries"]:
                if name == key:
                    return value
            return None
        for maximum, child in page["entries"]:
            if key <= maximum:
                return self.find(child, key)
        return None

    def posting_rows(self, posting, *, after=""):
        if "keys" in posting:
            yield from ((key, True) for key in posting["keys"] if key > after)
        else:
            yield from self.rows(posting["root_ref"], after=after)

    def posting_has(self, posting, key):
        return (
            key in posting["keys"]
            if "keys" in posting
            else self.find(posting["root_ref"], key) is not None
        )

    def rows(self, ref, *, after=""):
        page = self.read(ref)
        if page["kind"] == "leaf":
            yield from ((key, value) for key, value in page["entries"] if key > after)
        else:
            for maximum, child in page["entries"]:
                if maximum > after:
                    yield from self.rows(child, after=after)


def facets(manifest):
    entity = manifest["entity"]
    f = manifest["facets"]
    mapping = {
        key: list(f.get(key, []))
        for key in ("project_id", "stage_id", "topic_id", "related_entity_id")
    }
    mapping.update(
        handoff_id=[manifest["handoff_id"]],
        entity_id=[entity["entity_id"]],
        decision_id=[item["decision_id"] for item in manifest["decisions"]["items"]],
        task_id=[item["task_id"] for item in manifest["open_items"]["items"]],
        result_type=[f["result_type"]],
        state=[entity["state"]],
        updated_at=[manifest["created_at"]],
    )
    mapping["lexical"] = words(
        f["title"] + " " + f["summary"] + " " + " ".join(f.get("aliases", []))
    )
    return {key: sorted(set(values)) for key, values in mapping.items()}


def build_indexes(tree: Tree, rows: dict, *, history=False):
    inverted = {dimension: {} for dimension in DIMENSIONS if dimension != "handoff_id"}
    for key, row in rows.items():
        for dimension, values in row["facets"].items():
            if dimension == "handoff_id":
                continue
            for value in values:
                inverted[dimension].setdefault(value, []).append((key, True))
    roots = {"handoff_id": tree.build(sorted(rows.items()))}
    coverage = {"handoff_id": len(rows)}
    for dimension, values in inverted.items():
        entries = []
        for value, postings in sorted(values.items()):
            postings = sorted(postings)
            posting = (
                {"keys": [key for key, _ in postings], "count": len(postings)}
                if len(postings) <= 8
                else {"root_ref": tree.build(postings), "count": len(postings)}
            )
            entries.append((value, posting))
        roots[dimension] = tree.build(entries)
        coverage[dimension] = sum(len(items) for items in values.values())
    return roots, coverage


def verify_indexes(tree: Tree, roots: dict, rows: dict):
    require(set(roots) == set(DIMENSIONS), "INDEX_STALE")
    require(dict(tree.rows(roots["handoff_id"])) == rows, "INDEX_STALE")
    expected = {dim: {} for dim in DIMENSIONS if dim != "handoff_id"}
    for key, row in rows.items():
        for dim, values in row["facets"].items():
            if dim != "handoff_id":
                for value in values:
                    expected[dim].setdefault(value, set()).add(key)
    for dim, mapping in expected.items():
        actual = {}
        for value, posting in tree.rows(roots[dim]):
            keys = {key for key, _ in tree.posting_rows(posting)}
            require(len(keys) == posting["count"], "INDEX_STALE")
            actual[value] = keys
        require(actual == mapping, "INDEX_STALE")
