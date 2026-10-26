"""Read-only, exact-source display translations from a current pinned Markdown body."""
import re
import navigator as nav

BEGIN = "<!-- ATLAS_DISPLAY_FIELDS_BEGIN -->"
END = "<!-- ATLAS_DISPLAY_FIELDS_END -->"
SCHEMA = "atlas.localized-display-fields/v1"
FIELDS = frozenset(("work.title", "work.objective", "work.scope_note",
                    "project.objective", "project.scope_note"))
MAX_DOCUMENT = 2 * 1024 * 1024
MAX_RECORDS = 2000


def original_value(project, works, steps, target, field):
    if field.startswith("project."):
        return project.get(field.split(".")[1]) if target == project["id"] else None
    work = works.get(target)
    if work is None:
        return None
    name = field.split(".")[1]
    return steps.get(target, {}).get(name) if name == "scope_note" else work.get(name)


def project_overlay(works, project, documents, pins, presentation):
    result = {"schema": SCHEMA, "language": "ru", "project_id": project["id"],
              "status": "UNAVAILABLE", "records": [], "invalid": []}
    pinset = {(p["path"], p["sha256"], p["bytes"]) for p in pins}
    by_work = {w["id"]: w for w in works}
    steps = {}
    source = next((d for d in documents if d["id"] == presentation.get("source_matrix_doc_id")), None)
    if source and presentation.get("source_matrix_status") == "PINNED":
        raw = source["content"].encode("utf-8")
        if (len(raw) == source["bytes"] and nav.digest(raw) == source["sha256"]
                and (source["path"], source["sha256"], source["bytes"]) in pinset
                and source["sha256"] == presentation.get("source_matrix_sha256")):
            try:
                matrix = nav.parse(raw)
                steps = {s["id"]: s for s in matrix["steps"]}
            except (nav.Invalid, KeyError, TypeError):
                pass
    candidates = []
    seen = {}
    for doc in documents:
        body = doc.get("content")
        if not isinstance(body, str) or BEGIN not in body:
            continue
        reason = None
        try:
            raw = body.encode("utf-8")
            if (doc.get("kind") not in ("md", "markdown") or doc.get("lifecycle") != "current"
                    or len(raw) > MAX_DOCUMENT or type(doc.get("bytes")) is not int
                    or len(raw) != doc["bytes"] or nav.digest(raw) != doc.get("sha256")
                    or (doc["path"], doc["sha256"], doc["bytes"]) not in pinset):
                raise ValueError("CURRENT_DOCUMENT_PIN_MISMATCH")
            if body.count(BEGIN) != 1 or body.count(END) != 1:
                raise ValueError("AMBIGUOUS_DISPLAY_SECTION")
            section = body.split(BEGIN, 1)[1].split(END, 1)[0]
            match = re.fullmatch(r"\s*```json\r?\n([\s\S]*?)\r?\n```\s*", section)
            if not match:
                raise ValueError("DISPLAY_SECTION_FORMAT")
            data = nav.parse(match[1].encode("utf-8"))
            if (not isinstance(data, dict) or set(data) != {"schema", "language", "project_id", "records"}
                    or data["schema"] != SCHEMA or data["language"] != "ru"
                    or data["project_id"] != project["id"] or not isinstance(data["records"], list)
                    or len(data["records"]) > MAX_RECORDS):
                raise ValueError("DISPLAY_SECTION_SCHEMA")
        except (ValueError, TypeError, KeyError, nav.Invalid) as exc:
            result["invalid"].append({"document_id": doc["id"], "status": "UNKNOWN", "reason": str(exc)})
            continue
        for index, rec in enumerate(data["records"]):
            target = rec.get("target_id") if isinstance(rec, dict) else None
            field = rec.get("field") if isinstance(rec, dict) else None
            key = (target, field) if isinstance(target, str) and isinstance(field, str) else None
            if key is not None:
                seen[key] = seen.get(key, 0) + 1
            reason = None
            if (not isinstance(rec, dict) or set(rec) != {"target_id", "field", "original_value", "original_sha256", "translated_value"}
                    or not isinstance(field, str) or field not in FIELDS or not isinstance(target, str)):
                reason = "UNSUPPORTED_DISPLAY_RECORD"
            else:
                original = original_value(project, by_work, steps, target, field)
                translated = rec["translated_value"]
                if (not isinstance(original, str) or rec["original_value"] != original
                        or rec["original_sha256"] != nav.digest(original.encode("utf-8"))):
                    reason = "ORIGINAL_VALUE_MISMATCH"
                elif (not isinstance(translated, str) or not translated.strip() or len(translated) > 20000
                      or any(ord(c) < 32 and c not in "\n\t\r" for c in translated)):
                    reason = "INVALID_DISPLAY_VALUE"
            if reason:
                result["invalid"].append({"target_id": target, "field": field,
                                          "document_id": doc["id"], "status": "UNKNOWN", "reason": reason})
            else:
                candidates.append({**rec, "document_id": doc["id"], "document_path": doc["path"],
                                   "document_sha256": doc["sha256"], "document_bytes": doc["bytes"],
                                   "source_ref": doc.get("source_ref"), "json_pointer": "#/records/" + str(index)})
    for rec in candidates:
        if seen[(rec["target_id"], rec["field"])] != 1:
            result["invalid"].append({"target_id": rec["target_id"], "field": rec["field"],
                                      "status": "UNKNOWN", "reason": "DUPLICATE_DISPLAY_FIELD"})
        else:
            result["records"].append(rec)
    if result["records"]:
        result["status"] = "PARTIAL" if result["invalid"] else "PINNED"
    elif result["invalid"]:
        result["status"] = "UNKNOWN"
    return result
