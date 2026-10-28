"""Atlas 1.0: local, evidence-bound work records and document navigation.

Init creates a previously absent .atlas directory; build/cycle write only to
the explicitly selected output directory. Other commands are read-only.
Nothing in this module executes a task, a receipt command, or a remote action.
"""
import argparse
import copy
import json
import os
import tempfile
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import navigator as nav

VERSION = "ATLAS-1.0.0"
STATES = {"PLANNED", "DOING", "REVIEW", "ACCEPTED", "BLOCKED", "PAUSED", "CANCELLED", "UNKNOWN"}
ACTIVE = {"DOING", "REVIEW"}
SCOPES = {"DOCUMENTARY", "SOURCE", "TEST", "RUNTIME", "DELIVERY", "OWNER_ACCEPTANCE", "ACTIVITY"}
MAX_SELECTED = 32 * 1024 * 1024
MAX_ITEMS = 2000
Invalid = nav.Invalid
require = nav.require


def path_text(value, directory=False):
    require(isinstance(value, str) and value and "\\" not in value and "\x00" not in value, "UNSAFE_PATH")
    rel = value[:-1] if directory and value.endswith("/") else value
    p = PurePosixPath(rel)
    require(not p.is_absolute() and all(x not in ("", ".", "..") for x in rel.split("/")), "UNSAFE_PATH")
    require(not any(c in rel for c in "*?[]"), "PATH_GLOB_NOT_SUPPORTED")
    return rel


def overlaps(a, b):
    """Exact path or explicitly declared directory prefix. No implicit globs."""
    return a == b or (a.endswith("/") and b.startswith(a)) or (b.endswith("/") and a.startswith(b))


def schema_validate(value, filename):
    schema = nav.parse((Path(__file__).parent / filename).read_bytes())
    nav.structural(value, schema, schema.get("$defs", {}))
    # canonical() rejects unencodable text and non-finite data throughout the object.
    nav.canonical(value)


def pinned(root, record, selected, label, *, _source_context=None, work_id=None):
    path_text(record["path"])
    physical = record["path"]
    if "storage" in record:
        from source_relocation import Context
        source_context = _source_context or Context(root)
        raw, physical = source_context.read(record, work_id=work_id)
    else:
        raw = selected.get(physical)
        if raw is None: raw = nav.read_selected(root, physical, 8 * 1024 * 1024)
    require(len(raw) == record["bytes"] and nav.digest(raw) == record["sha256"], "PIN_MISMATCH:" + label)
    if physical in selected:
        require(selected[physical] == raw, "SOURCE_CHANGED_DURING_READ")
    else:
        selected[physical] = raw
        require(sum(map(len, selected.values())) <= MAX_SELECTED, "ATLAS_TOTAL_LIMIT")
    return raw


def basis(work):
    """A decision binds semantics and exact artifacts, not status/clock/journal noise."""
    artifacts = [{k: a[k] for k in ("id", "path", "sha256", "bytes", "role", "entity_ids")} for a in work["artifacts"]]
    for art, source in zip(artifacts, work["artifacts"]):
        if "patch" in source:
            art["patch_basis"] = {k: source["patch"][k] for k in ("target_id", "base_sha256", "selectors")}
    value = {k: work[k] for k in ("id", "objective", "outcome", "criteria")}
    value["artifacts"] = artifacts
    return nav.digest(nav.canonical(value))


def _ids(items, label):
    ids = [x["id"] for x in items]
    require(len(ids) == len(set(ids)), "DUPLICATE_ID:" + label)
    return {x["id"]: x for x in items}


def _refs(values, allowed, label):
    nav.refs(values, allowed, label, limit=MAX_ITEMS)


def _evidence_covers(evidence, artifact_ids, artifacts):
    subjects = {s["artifact_id"]: s["sha256"] for s in evidence["subjects"]}
    return all(subjects.get(i) == artifacts[i]["sha256"] for i in artifact_ids)


def validate_work(work, root, entities, as_of, selected, *, _source_context=None):
    schema_validate(work, "atlas.work.schema.json")
    wid = work["id"]
    for scope in work["write_scope"]:
        path_text(scope, directory=True)
    require(len(work["write_scope"]) == len(set(work["write_scope"])), "DUPLICATE_WRITE_SCOPE:" + wid)
    artifacts = _ids(work["artifacts"], wid + ".artifacts")
    criteria = _ids(work["criteria"], wid + ".criteria")
    evidence = _ids(work["evidence"], wid + ".evidence")
    events = _ids(work["events"], wid + ".events")
    for art in artifacts.values():
        require(art["role"] != "patch" or "patch" in art, "PATCH_METADATA_REQUIRED:" + wid)
        pinned(root, art, selected, wid + "/" + art["id"], _source_context=_source_context, work_id=wid)
        _refs(art["entity_ids"], entities, "artifact.entities")
    for criterion in criteria.values():
        require(criterion["required_scope"] != "ACTIVITY", "ACTIVITY_IS_NOT_ACCEPTANCE:" + wid)
        _refs(criterion["artifact_ids"], artifacts, "criterion.artifacts")
        require(criterion["artifact_ids"], "EMPTY_CRITERION_SUBJECT:" + wid)
    for ev in evidence.values():
        pinned(root, ev["receipt"], selected, wid + "/" + ev["id"])
        require(nav.stamp(ev["at"]) <= as_of, "EVIDENCE_AFTER_SNAPSHOT:" + wid)
        seen = set()
        for subject in ev["subjects"]:
            aid = subject["artifact_id"]
            require(aid in artifacts and aid not in seen, "EVIDENCE_SUBJECT:" + wid)
            seen.add(aid)
            # Historical evidence may target a previous hash; it remains visible but cannot accept current bytes.
    last = None
    for event in events.values():
        when = nav.stamp(event["at"])
        require(when <= as_of and (last is None or when >= last), "WORK_EVENT_TIME_ORDER:" + wid)
        last = when
        _refs(event["evidence_ids"], evidence, "event.evidence")
        for eid in event["evidence_ids"]:
            require(nav.stamp(evidence[eid]["at"]) <= when, "EVENT_BEFORE_EVIDENCE:" + wid)
    require(work["events"], "WORK_EVENT_REQUIRED:" + wid)
    state_events = {"STARTED": "DOING", "RESUMED": "DOING", "ACCEPTED": "ACCEPTED", "REVIEWED": "REVIEW",
                    "BLOCKED": "BLOCKED", "PAUSED": "PAUSED", "CANCELLED": "CANCELLED", "REOPEN": "PLANNED"}
    recorded = [state_events[e["kind"]] for e in work["events"] if e["kind"] in state_events]
    require(not recorded or recorded[-1] == work["state"], "WORK_STATE_EVENT_MISMATCH:" + wid)
    require(recorded or work["state"] in ("PLANNED", "UNKNOWN"), "WORK_STATE_EVENT_REQUIRED:" + wid)
    current_basis = basis(work)
    latest = {}
    for dec in work["acceptance"]:
        cid = dec["criterion_id"]
        require(cid in criteria, "ACCEPTANCE_CRITERION:" + wid)
        when = nav.stamp(dec["at"])
        require(when <= as_of, "ACCEPTANCE_AFTER_SNAPSHOT:" + wid)
        if cid in latest:
            require(nav.stamp(latest[cid]["at"]) <= when, "ACCEPTANCE_TIME_ORDER:" + wid)
        _refs(dec["evidence_ids"], evidence, "acceptance.evidence")
        for eid in dec["evidence_ids"]:
            require(nav.stamp(evidence[eid]["at"]) <= when, "ACCEPTANCE_BEFORE_EVIDENCE:" + wid)
        latest[cid] = dec
    accepted = []
    issues = []
    for cid, criterion in criteria.items():
        dec = latest.get(cid)
        if not dec or dec["decision"] != "ACCEPTED":
            continue
        if dec["basis_sha256"] != current_basis:
            issues.append({"code": "ACCEPTANCE_STALE", "criterion_id": cid})
            continue
        require(dec["actor"].strip().upper() != "UNKNOWN", "ACCEPTANCE_ACTOR_UNKNOWN:" + wid)
        good = [evidence[eid] for eid in dec["evidence_ids"] if evidence[eid]["result"] == "PASS"
                and evidence[eid]["scope"] == criterion["required_scope"]
                and evidence[eid]["actor"].strip().upper() != "UNKNOWN" and evidence[eid]["environment"].strip().upper() != "UNKNOWN"
                and _evidence_covers(evidence[eid], criterion["artifact_ids"], artifacts)]
        require(good, "ACCEPTANCE_SCOPE_OR_SUBJECT:" + wid + "/" + cid)
        normalize = lambda subjects: sorted((s["artifact_id"], s["sha256"]) for s in subjects)
        uncontradicted = []
        for proof in good:
            related = [e for e in work["evidence"] if e["check_id"] == proof["check_id"] and e["scope"] == proof["scope"]
                       and e["environment"] == proof["environment"] and normalize(e["subjects"]) == normalize(proof["subjects"])]
            latest_proof = max(enumerate(related), key=lambda pair: (nav.stamp(pair[1]["at"]), pair[0]))[1]
            if latest_proof["result"] == "PASS":
                uncontradicted.append(proof)
        if not uncontradicted:
            issues.append({"code": "ACCEPTANCE_CONTRADICTED", "criterion_id": cid})
            continue
        accepted.append(cid)
    if work["state"] == "ACCEPTED":
        require(criteria and len(accepted) == len(criteria), "ACCEPTED_WITHOUT_CURRENT_CRITERIA:" + wid)
        require(work["result"] is not None, "ACCEPTED_RESULT_REQUIRED:" + wid)
    if work["state"] in ACTIVE:
        require(work["assigned_to"] != "UNKNOWN" and work["writer"] != "UNKNOWN", "ACTIVE_ACTOR_REQUIRED:" + wid)
        # A read-only review can legitimately have no product write scope.
    if work["state"] == "BLOCKED":
        require(work["blocker"] is not None, "BLOCKER_REQUIRED:" + wid)
    if work["state"] not in ("ACCEPTED", "CANCELLED"):
        require(work["next_action"] is not None, "NEXT_ACTION_REQUIRED:" + wid)
    activity_state = "UNKNOWN"
    activity = work["activity"]
    if activity is not None:
        require(work["state"] == "DOING", "ACTIVITY_REQUIRES_DOING:" + wid)
        require(activity["actor"] == work["assigned_to"], "ACTIVITY_ACTOR_MISMATCH:" + wid)
        eid = activity["evidence_id"]
        require(eid in evidence, "ACTIVITY_EVIDENCE:" + wid)
        ev = evidence[eid]
        observed = nav.stamp(activity["observed_at"]); until = nav.stamp(activity["valid_until"])
        require(observed <= as_of and observed < until, "ACTIVITY_WINDOW:" + wid)
        require((until-observed).total_seconds() <= 3600, "ACTIVITY_WINDOW_TOO_LONG:" + wid)
        require(ev["scope"] == "ACTIVITY" and ev["result"] == "PASS" and ev["actor"] == activity["actor"], "ACTIVITY_PROOF_SCOPE:" + wid)
        require(nav.stamp(ev["at"]) == observed, "ACTIVITY_PROOF_TIME:" + wid)
        require(ev.get("valid_until") == activity["valid_until"], "ACTIVITY_PROOF_EXPIRY:" + wid)
        require(ev.get("work_id") == wid, "ACTIVITY_PROOF_WORK:" + wid)
        boundaries = [nav.stamp(e["at"]) for e in work["events"] if e["kind"] in ("ASSIGNED", "STARTED", "RESUMED", "REOPEN", "HANDOFF")]
        require(not boundaries or observed >= max(boundaries), "ACTIVITY_BEFORE_CURRENT_ATTEMPT:" + wid)
        activity_state = "CURRENT" if as_of < until else "EXPIRED"
    for art in artifacts.values():
        patch = art.get("patch")
        if patch is None:
            continue
        require(art["role"] == "patch", "PATCH_ROLE:" + wid)
        target = patch["target_id"]
        require(target in artifacts and target != art["id"], "PATCH_TARGET:" + wid)
        require(artifacts[target]["sha256"] == patch["base_sha256"], "PATCH_BASE_CHANGED:" + wid)
        require(patch["selectors"] and len(set(patch["selectors"])) == len(patch["selectors"]), "PATCH_SELECTORS:" + wid)
        require(all(s.startswith("/") for s in patch["selectors"]), "PATCH_SELECTOR_POINTER:" + wid)
        _refs(patch["decision_evidence_ids"], evidence, "patch.evidence")
        if patch["state"] in ("ACCEPTED_UNAPPLIED", "APPLIED"):
            good = [evidence[eid] for eid in patch["decision_evidence_ids"]
                    if evidence[eid]["result"] == "PASS" and evidence[eid]["scope"] == "DOCUMENTARY"
                    and _evidence_covers(evidence[eid], [art["id"], target], artifacts)]
            require(good, "PATCH_DECISION_PROOF:" + wid)
        if patch["state"] == "APPLIED":
            rid = patch["result_artifact_id"]
            require(rid in artifacts and rid not in (art["id"], target), "PATCH_RESULT_REQUIRED:" + wid)
            require(artifacts[rid]["role"] == "output", "PATCH_RESULT_ROLE:" + wid)
            good = [evidence[eid] for eid in patch["decision_evidence_ids"]
                    if evidence[eid]["result"] == "PASS" and evidence[eid]["scope"] in ("SOURCE", "RUNTIME")
                    and _evidence_covers(evidence[eid], [art["id"], target, rid], artifacts)]
            require(good, "PATCH_APPLY_READBACK:" + wid)
        else:
            require(patch["result_artifact_id"] is None, "UNAPPLIED_PATCH_HAS_RESULT:" + wid)
    performed = []
    for event in work["events"]:
        if event["kind"] in ("RESULT", "IMPLEMENTED") and event["actor"] not in performed:
            performed.append(event["actor"])
    return {"basis_sha256": current_basis, "activity_state": activity_state,
            "accepted_criteria": len(accepted), "total_criteria": len(criteria),
            "accepted_criterion_ids": accepted, "completed_by": performed, "issues": issues}


def validate_graph(works):
    by_id = _ids(works, "works")
    for work in works:
        children = [w for w in works if w["parent_id"] == work["id"]]
        if children:
            require(work["activity"] is None, "PARENT_ACTIVITY_NOT_LEAF:" + work["id"])
            require(not work["write_scope"], "PARENT_WRITE_SCOPE_NOT_LEAF:" + work["id"])
        _refs(work["depends_on"], by_id, "work.dependencies")
        require(work["id"] not in work["depends_on"], "WORK_SELF_DEPENDENCY")
        parent = work["parent_id"]
        require(parent is None or parent in by_id and parent != work["id"], "WORK_PARENT")
    def acyclic(edge_key, code):
        visiting = set(); visited = set()
        def walk(wid):
            require(wid not in visiting, code)
            if wid in visited:
                return
            visiting.add(wid)
            w = by_id[wid]
            refs = w[edge_key] if edge_key == "depends_on" else ([w[edge_key]] if w[edge_key] else [])
            for rid in refs:
                walk(rid)
            visiting.remove(wid); visited.add(wid)
        for wid in by_id:
            walk(wid)
    acyclic("depends_on", "WORK_DEPENDENCY_CYCLE")
    acyclic("parent_id", "WORK_PARENT_CYCLE")
    for work in works:
        children = [w for w in works if w["parent_id"] == work["id"]]
        if work["state"] in ("DOING", "ACCEPTED"):
            require(all(by_id[x]["state"] == "ACCEPTED" for x in work["depends_on"]), "UNMET_DEPENDENCY:" + work["id"])
        if work["state"] == "ACCEPTED":
            require(all(w["state"] in ("ACCEPTED", "CANCELLED") for w in children), "PARENT_HAS_OPEN_CHILDREN:" + work["id"])
    active = [w for w in works if w["state"] in ACTIVE]
    for i, first in enumerate(active):
        for second in active[i+1:]:
            for a in first["write_scope"]:
                for b in second["write_scope"]:
                    require(not overlaps(a, b), "WRITE_SCOPE_CONFLICT:" + first["id"] + "/" + second["id"])
    # Two accepted patches targeting the same bytes and selector need an explicit composed replacement.
    patches = []
    for work in works:
        for art in work["artifacts"]:
            p = art.get("patch")
            if p and p["state"] in ("ACCEPTED_UNAPPLIED", "APPLIED"):
                target_path = next(a["path"] for a in work["artifacts"] if a["id"] == p["target_id"])
                patches.append((work["id"], art, p, target_path))
    for i, (wa, aa, pa, ta) in enumerate(patches):
        for wb, ab, pb, tb in patches[i+1:]:
            if aa["sha256"] == ab["sha256"]:
                continue  # same immutable patch referenced twice, not a second proposal
            if ta == tb and pa["base_sha256"] == pb["base_sha256"]:
                require(not any(x == "/" or y == "/" or x == y or x.startswith(y.rstrip("/")+"/") or y.startswith(x.rstrip("/")+"/")
                                for x in pa["selectors"] for y in pb["selectors"]), "PATCH_CONFLICT:" + wa + "/" + wb)


def validate_coverage(project, works, entities, root, as_of, selected):
    spec = project.get("coverage")
    required_domains = {"goals", "modules", "contracts", "documents", "source", "works"}
    if spec is None:
        return {"status": "UNKNOWN", "domains": [], "issues": ["NO_FULL_PROJECT_INVENTORY"],
                "claim": "Coverage is not established."}
    inventory = nav.parse(pinned(root, spec["inventory"], selected, "coverage.inventory"))
    schema_validate(inventory, "atlas.inventory.schema.json")
    require(nav.stamp(inventory["observed_at"]) <= as_of, "INVENTORY_AFTER_SNAPSHOT")
    domains = _ids(inventory["domains"], "coverage.domains")
    bound = {}; work_ids = {w["id"] for w in works}
    for binding in spec["bindings"]:
        key = (binding["domain_id"], binding["item_id"])
        require(key not in bound, "DUPLICATE_COVERAGE_BINDING")
        require(key[0] in domains and key[1] in domains[key[0]]["items"], "COVERAGE_UNKNOWN_ITEM")
        _refs(binding["entity_ids"], entities, "coverage.entities")
        _refs(binding["work_ids"], work_ids, "coverage.works")
        require(binding["entity_ids"] or binding["work_ids"], "EMPTY_COVERAGE_BINDING")
        bound[key] = binding
    result = []; issues = []
    for did, domain in domains.items():
        require(len(domain["items"]) == len(set(domain["items"])), "DUPLICATE_INVENTORY_ITEM")
        excluded = _ids(domain["exclusions"], "coverage.exclusions")
        require(not set(excluded).intersection(domain["items"]), "INVENTORY_INCLUDED_AND_EXCLUDED")
        def covered(item):
            binding = bound.get((did, item))
            if not binding:
                return False
            if did == "works":
                return item in work_ids and item in binding["work_ids"]
            return bool(binding["entity_ids"])
        missing = [i for i in domain["items"] if not covered(i)]
        status = "COMPLETE" if domain["exhaustive"] and not missing else "PARTIAL"
        result.append({"id": did, "title": domain["title"], "inventory_count": len(domain["items"]),
                       "documented_count": len(domain["items"])-len(missing), "missing_ids": missing,
                       "status": status, "exclusions": domain["exclusions"],
                       "followup_work_ids": sorted({w for i in missing for w in bound.get((did, i), {}).get("work_ids", [])})})
    for absent in sorted(required_domains-set(domains)):
        issues.append("MISSING_DOMAIN:" + absent)
    coverage_works = domains.get("works")
    if coverage_works:
        listed = set(coverage_works["items"])
        for wid in sorted(work_ids-listed):
            issues.append("WORK_OUTSIDE_INVENTORY:"+wid)
    full = not issues and all(d["status"] == "COMPLETE" for d in result)
    return {"status": "COMPLETE" if full else "PARTIAL", "domains": result, "issues": issues,
            "observed_at": inventory["observed_at"], "scope_note": inventory["scope_note"],
            "source_ref": inventory["source_ref"], "claim": "Complete only against this explicit inventory and its declared exclusions; semantic source coverage requires its owning review."}


def _archive_record(snapshot):
    """Validate archive metadata without following or reading historical sources."""
    a = snapshot.get("atlas")
    require(isinstance(a, dict) and isinstance(a.get("project"), dict), "OUTPUT_FAMILY_CHANGED")
    project = a["project"]
    schema_validate(project, "atlas.project.schema.json")
    require(project["id"] == snapshot["input"]["project"]["id"], "PROJECT_ID_MISMATCH")
    require(a.get("matrix_history", []) == project.get("matrix_history", []), "ARCHIVE_MATRIX_PAGE_BINDING")
    spec = project.get("projection_archive")
    if spec is None:
        require(a.get("projection_archive") is None, "ARCHIVE_METADATA_WITHOUT_SPEC")
        return a, None, len(a.get("matrix_history", []))
    require(project["mode"] == "projection", "ARCHIVE_REQUIRES_PROJECTION")
    meta = a.get("projection_archive")
    require(isinstance(meta, dict) and all(meta.get(k) == v for k, v in spec.items()), "ARCHIVE_METADATA_BINDING")
    require(isinstance(meta.get("previous_snapshot_sha256"), str) and nav.SHA.fullmatch(meta["previous_snapshot_sha256"]), "ARCHIVE_SNAPSHOT_SHA")
    require(type(meta.get("previous_matrix_history_total")) is int and meta["previous_matrix_history_total"] >= 0,
            "ARCHIVE_PREVIOUS_TOTAL")
    require(spec["matrix_history_total"] == meta["previous_matrix_history_total"] + len(a.get("matrix_history", [])),
            "ARCHIVE_HISTORY_TOTAL")
    return a, spec, spec["matrix_history_total"]


def _projection_archive(root, project, as_of):
    """Qualify one immutable parent; previous raw source pins are not re-read.

    The exact snapshot and its HTML are verified now by the output manifest.
    Historical source bytes retain their verification at the original import.
    """
    spec = project.get("projection_archive")
    if spec is None:
        return None
    require(project["mode"] == "projection", "ARCHIVE_REQUIRES_PROJECTION")
    output = nav.safe(root, path_text(spec["output"]), directory=True)
    _, parent = nav.verify_release(output, spec["previous_release"], spec["previous_manifest_sha256"])
    old, old_spec, total = _archive_record(parent)
    require(old["project"]["id"] == project["id"], "ARCHIVE_PROJECT_CHANGED")
    require(old["project"]["mode"] == "projection", "ARCHIVE_REQUIRES_PROJECTION")
    require(old_spec is None or old_spec["output"] == spec["output"], "ARCHIVE_OUTPUT_CHANGED")
    require(nav.stamp(parent["input"]["release"]["created_at"]) <= as_of, "ARCHIVE_PARENT_AFTER_SNAPSHOT")
    page = project.get("matrix_history", [])
    require(spec["matrix_history_total"] == total + len(page), "ARCHIVE_HISTORY_TOTAL")
    old_ids = {row["id"] for row in old.get("matrix_history", [])}
    old_hashes = {row["file"]["sha256"] for row in old.get("matrix_history", [])}
    require(not any(row["id"] in old_ids or row["file"]["sha256"] in old_hashes for row in page), "ARCHIVE_PAGE_ALREADY_RETAINED")
    return {**spec, "previous_snapshot_sha256": nav.digest(nav.canonical(parent)),
            "previous_matrix_history_total": total, "parent_manifest_status": "VERIFIED_AT_SNAPSHOT_LOAD",
            "archived_source_status": "VERIFIED_AT_IMPORT"}


def _archive_output(root, snapshot, output):
    spec = snapshot["atlas"]["project"].get("projection_archive")
    if spec is not None:
        declared = nav.safe(Path(root).resolve(), path_text(spec["output"]), directory=True)
        require(declared.resolve() == Path(output).resolve(), "ARCHIVE_OUTPUT_BINDING")


def _presentation(project, documents):
    """Select an owning matrix only from documents already verified by nav.load.

    This is a presentation binding to source claims, never a work decision or
    activity assessment. The exact marker is emitted by the owning importer.
    """
    result = {"schema": "atlas.presentation/v1", "renderer": "ATLAS-READABLE-1.0.0",
              "sections": ["roadmap", "contracts", "documents", "actors", "history", "relations", "coverage"],
              "source_matrix_status": "UNAVAILABLE", "source_matrix_doc_id": None,
              "source_matrix_sha256": None}
    source = project.get("source_ref")
    if not isinstance(source, str) or source.count(" pointer=") != 1:
        return result
    path, pointer = source.split(" pointer=", 1)
    if not path or pointer and not pointer.startswith("/"):
        return result
    marker = path + " [owning matrix projection source]"
    # The importer emits an explicit empty pointer; earlier projection records
    # can omit it. These two exact spellings identify the same root selection.
    markers = {marker + " pointer=" + pointer} if pointer else {marker, marker + " pointer="}
    candidates = [doc for doc in documents
                  if doc["lifecycle"] == "current" and doc["source_ref"] in markers]
    if len(candidates) != 1:
        if len(candidates) > 1:
            result["source_matrix_status"] = "AMBIGUOUS"
        return result
    doc = candidates[0]
    if doc["kind"] != "json":
        return result
    try:
        matrix = nav.parse(doc["content"].encode("utf-8"))
    except (nav.Invalid, UnicodeError):
        return result
    if not (isinstance(matrix, dict) and isinstance(matrix.get("schema"), str)
            and matrix["schema"] and isinstance(matrix.get("steps"), list)
            and matrix["steps"] and isinstance(matrix.get("events"), list)):
        return result
    ids = []
    for step in matrix["steps"]:
        if not isinstance(step, dict) or not isinstance(step.get("id"), str) or not step["id"]:
            return result
        ids.append(step["id"])
    if len(set(ids)) != len(ids):
        return result
    if any(not isinstance(event, dict) or not isinstance(event.get("id"), str)
           or not event["id"] or event.get("step_id") not in ids for event in matrix["events"]):
        return result
    result.update(source_matrix_status="PINNED", source_matrix_doc_id=doc["id"],
                  source_matrix_sha256=doc["sha256"])
    return result



def _localized_work_titles(works, documents, source_pins, presentation):
    """Extract ru display-only titles exclusively from pinned, work-linked contexts.

    This is an in-memory presentation projection. It cannot change original work
    titles, source events, state, evidence, writer, project or any authority.
    The originating source event must explicitly identify the matching JSON
    pointer and display title; an arbitrary shared document is not sufficient.
    """
    result = {"schema": "atlas.localized-work-titles/v1", "language": "ru",
              "status": "UNAVAILABLE", "records": [], "invalid": []}
    documents_by_id = {d["id"]: d for d in documents}
    pinset = {(p["path"], p["sha256"], p["bytes"]) for p in source_pins}
    doc_contexts = {}
    for doc in documents:
        if doc.get("lifecycle") != "current" or doc.get("kind") != "json":
            continue
        content = doc.get("content")
        if not isinstance(content, str):
            continue
        try:
            data = nav.parse(content.encode("utf-8"))
        except (nav.Invalid, UnicodeError, ValueError):
            continue
        if not isinstance(data, dict) or data.get("language") != "ru" or not (
                isinstance(data.get("schema"), str) and
                data["schema"].endswith(".work-context-language/v1") and
                isinstance(data.get("contexts"), dict)):
            continue
        raw = content.encode("utf-8")
        if (len(raw) != doc.get("bytes") or nav.digest(raw) != doc.get("sha256")
                or (doc["path"], doc["sha256"], doc["bytes"]) not in pinset):
            result["invalid"].append({"document_id": doc["id"], "reason": "DOCUMENT_PIN_MISMATCH"})
            continue
        doc_contexts[doc["id"]] = data["contexts"]
    if not doc_contexts:
        if result["invalid"]:
            result["status"] = "INVALID_CONTEXT_PIN"
        return result
    status = presentation.get("source_matrix_status")
    sd = documents_by_id.get(presentation.get("source_matrix_doc_id"))
    if status != "PINNED" or sd is None or sd.get("sha256") != presentation.get("source_matrix_sha256"):
        result["status"] = "SOURCE_MATRIX_NOT_PINNED"
        return result
    if (sd.get("path"), sd.get("sha256"), sd.get("bytes")) not in pinset:
        result["status"] = "SOURCE_MATRIX_NOT_PINNED"
        return result
    try:
        matrix = nav.parse(sd["content"].encode("utf-8"))
    except (nav.Invalid, UnicodeError, ValueError):
        result["status"] = "INVALID_SOURCE_MATRIX"
        return result
    if not isinstance(matrix.get("events"), list) or not isinstance(matrix.get("steps"), list):
        result["status"] = "INVALID_SOURCE_MATRIX"
        return result
    source_titles = {step["id"]: step.get("title") for step in matrix["steps"]
                     if isinstance(step, dict) and isinstance(step.get("id"), str)}
    source_refs = {}
    for event in matrix["events"]:
        if not isinstance(event, dict) or not isinstance(event.get("step_id"), str):
            continue
        ctx = event.get("handoff_context")
        if isinstance(ctx, dict) and isinstance(ctx.get("full_text_ref"), dict):
            source_refs[event["step_id"]] = (event, ctx)
    for work in works:
        wid = work["id"]
        event_context = source_refs.get(wid)
        if event_context is None:
            continue
        event, source_ctx = event_context
        ref = source_ctx["full_text_ref"]
        pointer = "/contexts/" + wid.replace("~", "~0").replace("/", "~1")
        if not (ref.get("json_pointer") == pointer
                and isinstance(ref.get("document_id"), str) and ref["document_id"].strip()):
            result["invalid"].append({"work_id": wid, "reason": "WRONG_EXPLICIT_JSON_POINTER"})
            continue
        linked = {i for art in work.get("artifacts", []) for i in art.get("entity_ids", [])}
        matches = []
        origin_id = ref["document_id"]
        # The importer, not a title matcher, defines the stable original ID ->
        # published document ID conversion:
        # D-<SHA256(logical ID)[:12]>-<import generation fingerprint[:20]>.
        # Validate both the exact generated ID and its pinned generation path.
        for docid, contexts in doc_contexts.items():
            if docid not in linked:
                continue
            doc = documents_by_id[docid]
            segments = doc.get("path", "").split("/")
            expected = ("D-" + nav.digest(origin_id.encode("utf-8"))[:12] + "-"
                        + segments[2][:20]) if (len(segments) == 5
                        and segments[:2] == [".atlas", "imports"]
                        and segments[3] == "documents"
                        and isinstance(origin_id, str)
                        and origin_id) else None
            if (expected is None or not nav.SHA.fullmatch(segments[2])
                    or docid != expected or segments[4] != docid + ".json"):
                result["invalid"].append({"work_id": wid,
                    "document_id": docid, "reason": "ORIGIN_DOCUMENT_ENTITY_MISMATCH"})
                continue
            value = contexts.get(wid)
            if not isinstance(value, dict):
                continue
            if (value.get("work_id") != wid or value.get("language") != "ru"
                    or not isinstance(value.get("schema"), str)
                    or not value["schema"].endswith(".work-handoff-context/v1")
                    or value.get("original_title") != work["title"]
                    or source_titles.get(wid) != work["title"]
                    or value.get("display_title") != source_ctx.get("display_title")):
                result["invalid"].append({"work_id": wid, "document_id": docid, "reason": "TITLE_OR_SOURCE_REF_MISMATCH"})
                continue
            title = value.get("display_title")
            if not isinstance(title, str) or not title.strip() or len(title) > 400 or any(ord(c) < 32 for c in title):
                result["invalid"].append({"work_id": wid, "document_id": docid, "reason": "INVALID_DISPLAY_TITLE"})
                continue
            doc = documents_by_id[docid]
            matches.append({"work_id":wid,"title":title,"original_title":work["title"],
                "document_id":docid, "document_path":doc["path"],
                "document_sha256":doc["sha256"], "document_bytes":doc["bytes"],
                "source_ref":doc["source_ref"], "json_pointer":"#" + pointer,
                "origin_document_id":ref["document_id"], "origin_event_id":event.get("id","UNKNOWN")})
        if len(matches) == 1:
            result["records"].append(matches[0])
        elif len(matches) > 1:
            result["invalid"].append({"work_id":wid,"reason":"AMBIGUOUS_LINKED_CONTEXT"})
    result["status"] = "PINNED" if result["records"] else ("INVALID_OR_UNLINKED" if result["invalid"] else "UNAVAILABLE")
    return result


def toolchain_digest():
    base = Path(__file__).parent
    files = sorted(p for p in base.iterdir() if p.is_file() and p.suffix in (".py", ".json", ".js", ".css"))
    return nav.digest(nav.canonical({p.name: nav.digest(p.read_bytes()) for p in files}))


def load_project(root, project_path, at=None, validate=True, *, _source_operation=None):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "INVALID_ROOT")
    root = root.resolve()
    from source_relocation import Context
    source_context = Context(root, _source_operation)
    raw = nav.read_selected(root, project_path, 512 * 1024)
    project = nav.parse(raw)
    schema_validate(project, "atlas.project.schema.json")
    selected = {project_path: raw}
    dp = project["documents"]
    doc_raw = pinned(root, dp, selected, "document_manifest")
    documents = nav.load(root, dp["path"], _source_context=source_context)
    require(documents["input_sha256"] == nav.digest(doc_raw), "DOCUMENT_MANIFEST_RACE")
    require(project["id"] == documents["input"]["project"]["id"], "PROJECT_ID_MISMATCH")
    as_of_text = at or datetime.now(timezone.utc).isoformat()
    as_of = nav.stamp(as_of_text)
    require(as_of >= nav.stamp(documents["input"]["release"]["created_at"]), "ATLAS_BEFORE_DOCUMENT_SNAPSHOT")
    entities = {x["id"] for x in documents["documents"] + documents["input"]["modules"] + documents["input"]["contracts"]}
    works = []; work_paths = {}
    for rel in project["work_files"]:
        path_text(rel)
        require(rel not in work_paths.values(), "DUPLICATE_WORK_PATH")
        work_raw = selected.get(rel)
        if work_raw is None:
            work_raw = nav.read_selected(root, rel, 2 * 1024 * 1024)
        require(sum(map(len, selected.values())) + len(work_raw) <= MAX_SELECTED, "ATLAS_TOTAL_LIMIT")
        selected[rel] = work_raw
        work = nav.parse(work_raw)
        schema_validate(work, "atlas.work.schema.json")
        require(work["id"] not in work_paths, "DUPLICATE_WORK_ID")
        work_paths[work["id"]] = rel
        if validate:
            work["derived"] = validate_work(work, root, entities, as_of, selected, _source_context=source_context)
        works.append(work)
    require(works, "NO_WORK_ITEMS")
    if validate:
        validate_graph(works)
    for doc in documents["documents"]:
        raw_doc = doc["content"].encode("utf-8")
        physical = doc.get("storage", {}).get("path", doc["path"])
        if physical in selected:
            require(selected[physical] == raw_doc, "DOCUMENT_READ_INCONSISTENT")
        else:
            selected[physical] = raw_doc
    for rel, raw_control in source_context.source_pins.items():
        require(rel not in selected or selected[rel] == raw_control, "SOURCE_CHANGED_DURING_READ")
        selected[rel] = raw_control
    coverage = validate_coverage(project, works, entities, root, as_of, selected)
    matrix_history = project.get("matrix_history", [])
    _ids(matrix_history, "matrix_history")
    last_matrix = None
    for entry in matrix_history:
        when = nav.stamp(entry["at"])
        require(when <= as_of and (last_matrix is None or when >= last_matrix), "MATRIX_HISTORY_TIME")
        last_matrix = when
        pinned(root, entry["file"], selected, "matrix_history:" + entry["id"])
    archive = _projection_archive(root, project, as_of)
    require(sum(map(len, selected.values())) <= MAX_SELECTED, "ATLAS_TOTAL_LIMIT")
    source_pins = [{"path": p, "sha256": nav.digest(b), "bytes": len(b)} for p, b in sorted(selected.items())]
    data = {"project": project, "as_of": as_of_text, "works": works,
            "source_pins": source_pins, "work_paths": work_paths,
            "document_release": copy.deepcopy(documents["input"]["release"]),
            "document_input_sha256": documents["input_sha256"], "coverage": coverage,
            "matrix_history": matrix_history,
            "matrix_history_total": archive["matrix_history_total"] if archive else len(matrix_history), "issues": []}
    if archive is not None:
        data["projection_archive"] = archive
    counts = {state: sum(w["state"] == state for w in works) for state in sorted(STATES)}
    data["summary"] = {"total": len(works), "states": counts,
                       "activity_current": sum(w.get("derived", {}).get("activity_state") == "CURRENT" for w in works),
                       "accepted_criteria": sum(w.get("derived", {}).get("accepted_criteria", 0) for w in works),
                       "total_criteria": sum(len(w["criteria"]) for w in works)}
    for w in works:
        for issue in w.get("derived", {}).get("issues", []):
            data["issues"].append({"work_id": w["id"], **issue})
    source_digest = nav.digest(nav.canonical({"project": project, "source_pins": source_pins}))
    data["source_sha256"] = source_digest
    data["toolchain_sha256"] = toolchain_digest()
    data["presentation"] = _presentation(project, documents["documents"])
    data["localized_titles"] = _localized_work_titles(
        works, documents["documents"], source_pins, data["presentation"])
    from display_fields import project_overlay
    data["localized_fields"] = project_overlay(works, project, documents["documents"], source_pins, data["presentation"])
    documents["atlas"] = data
    documents["template_version"] = VERSION
    return documents


def _raw_work(work):
    return {k: v for k, v in work.items() if k != "derived"}


def _check_projection_documents(previous, current):
    """Current graph can omit archived cards; surviving versions keep DN semantics."""
    a = previous["input"]; b = current["input"]
    for category in ("documents", "contracts"):
        after = {x["id"]: x for x in b[category]}
        for old in a[category]:
            if old["id"] not in after:
                continue
            newer = copy.deepcopy(after[old["id"]]); older = copy.deepcopy(old)
            require(older["lifecycle"] != "archived" or newer["lifecycle"] == "archived", "ARCHIVE_REACTIVATED")
            older.pop("lifecycle"); newer.pop("lifecycle")
            require(older == newer, "HISTORICAL_MEMBER_REWRITE")
    old_events = {e["id"] for e in a["history"]}
    require(any(e["id"] not in old_events for e in b["history"]), "NEW_HISTORY_EVENT_REQUIRED")


def check_history(previous, current):
    require("atlas" in previous and "atlas" in current, "OUTPUT_FAMILY_CHANGED")
    a = previous["atlas"]; b = current["atlas"]
    require(a["project"]["id"] == b["project"]["id"], "PROJECT_CHANGED")
    require(a["project"]["mode"] == b["project"]["mode"], "PROJECT_MODE_MIGRATION_REQUIRED")
    old_matrices = a.get("matrix_history", [])
    archive = b["project"].get("projection_archive")
    if archive is None:
        require(a["project"].get("projection_archive") is None, "ARCHIVE_CHECKPOINT_REQUIRED")
        require(b.get("matrix_history", [])[:len(old_matrices)] == old_matrices, "MATRIX_VERSION_HISTORY_REWRITE")
    else:
        _, _, total = _archive_record(previous)
        _, _, new_total = _archive_record(current)
        meta = b["projection_archive"]
        require(archive["previous_release"] == previous["input"]["release"]["id"]
                and meta["previous_snapshot_sha256"] == nav.digest(nav.canonical(previous)), "ARCHIVE_PARENT_MISMATCH")
        require(meta["previous_matrix_history_total"] == total and new_total == total + len(b.get("matrix_history", [])), "ARCHIVE_HISTORY_TOTAL")
    require(nav.stamp(previous["input"]["release"]["created_at"]) <= nav.stamp(current["input"]["release"]["created_at"]), "RELEASE_TIME_ORDER")
    if a["document_input_sha256"] != b["document_input_sha256"]:
        if archive is None:
            nav.check_history(previous, current)
        else:
            _check_projection_documents(previous, current)
    else:
        for key in ("documents", "modules", "contracts", "relations", "matrix", "bindings", "history"):
            require(previous["input"][key] == current["input"][key], "DOCUMENT_INPUT_INCONSISTENT")
        require(previous["matrix_snapshot"] == current["matrix_snapshot"], "MATRIX_HISTORY_REWRITE")
    old = {w["id"]: _raw_work(w) for w in a["works"]}; new = {w["id"]: _raw_work(w) for w in b["works"]}
    for wid, before in old.items():
        require(wid in new, "WORK_REMOVED:" + wid)
        after = new[wid]
        require(after["events"][:len(before["events"])] == before["events"], "WORK_EVENT_REWRITE:" + wid)
        require(after["acceptance"][:len(before["acceptance"])] == before["acceptance"], "WORK_ACCEPTANCE_REWRITE:" + wid)
        old_art = {x["id"]:x for x in before["artifacts"]}; new_art = {x["id"]:x for x in after["artifacts"]}
        for aid, older in old_art.items():
            newer = new_art.get(aid)
            if "storage" in older:
                require(newer is not None and older["storage"] == newer.get("storage"), "WORK_STORAGE_REWRITE:" + wid)
            elif newer and "storage" in newer:
                require(older == {k:v for k,v in newer.items() if k != "storage"}, "WORK_STORAGE_SUBJECT_REWRITE:" + wid)
        old_ev = {x["id"]: x for x in before["evidence"]}; new_ev = {x["id"]: x for x in after["evidence"]}
        require(all(new_ev.get(eid) == ev for eid, ev in old_ev.items()), "WORK_EVIDENCE_REWRITE:" + wid)
        if before["activity"] and after["activity"] and before["activity"]["evidence_id"] == after["activity"]["evidence_id"]:
            require(before["activity"] == after["activity"], "ACTIVITY_PROOF_REUSE_CHANGED:" + wid)
        if before != after:
            require(len(after["events"]) > len(before["events"]), "WORK_CHANGE_EVENT_REQUIRED:" + wid)
            new_events = after["events"][len(before["events"]):]
            if before["writer"] != after["writer"] or before["assigned_to"] != after["assigned_to"]:
                require(any(e["kind"] == "HANDOFF" for e in new_events), "OWNERSHIP_HANDOFF_REQUIRED:" + wid)
            if before["state"] in ("ACCEPTED", "CANCELLED") and after["state"] not in ("ACCEPTED", "CANCELLED"):
                require(any(e["kind"] == "REOPEN" for e in new_events), "REOPEN_EVENT_REQUIRED:" + wid)
        for eid, ev in new_ev.items():
            if eid in old_ev:
                continue
            normalize = lambda subjects: sorted((s["artifact_id"], s["sha256"]) for s in subjects)
            same = [e for e in old_ev.values() if e["check_id"] == ev["check_id"] and e["scope"] == ev["scope"] and normalize(e["subjects"]) == normalize(ev["subjects"])
                    and e["environment"] == ev["environment"] and e["result"] == ev["result"] and e["scope"] != "ACTIVITY"]
            require(not same or ev.get("repeat_reason"), "REPEATED_CHECK_REASON_REQUIRED:" + wid + "/" + eid)
    project_fields = ("objective", "authority_ref", "writer", "mode", "source_ref")
    if any(a["project"][k] != b["project"][k] for k in project_fields):
        added = [e for wid, w in new.items() for e in w["events"][len(old.get(wid, {}).get("events", [])):]]
        require(any(e["kind"] in ("PROJECT_CHANGED", "HANDOFF") for e in added), "PROJECT_CHANGE_EVENT_REQUIRED")
    require(a["source_sha256"] != b["source_sha256"] or a.get("toolchain_sha256") != b.get("toolchain_sha256"), "NO_MATERIAL_CHANGE")


def build(root, project_path, output, release, at, previous=None):
    snapshot = load_project(root, project_path, at=at)
    _archive_output(root, snapshot, output)
    nav.ident(release)
    require(previous is None or nav.SHA.fullmatch(previous), "PREVIOUS_SHA")
    snapshot["input"]["release"] = {"id": release, "created_at": at, "previous": previous}
    snapshot["input_sha256"] = nav.digest(nav.canonical({"source_sha256": snapshot["atlas"]["source_sha256"], "toolchain_sha256": snapshot["atlas"]["toolchain_sha256"], "release": snapshot["input"]["release"]}))
    return nav.publish(snapshot, output, render_fn=nav.render, history_fn=check_history, version=VERSION)


def packet(snapshot, work_id):
    a = snapshot["atlas"]
    by_id = {w["id"]: w for w in a["works"]}
    require(work_id in by_id, "UNKNOWN_WORK")
    w = by_id[work_id]
    refs = set(e for art in w["artifacts"] for e in art["entity_ids"])
    docs = [d for d in snapshot["documents"] if d["id"] in refs]
    contracts = [c for c in snapshot["input"]["contracts"] if c["id"] in refs]
    module_ids = {m["id"] for m in snapshot["input"]["modules"] if m["id"] in refs} | {c["module"] for c in contracts}
    modules = [m for m in snapshot["input"]["modules"] if m["id"] in module_ids]
    doc_ids = {d["id"] for d in docs}
    doc_ids.update(x for c in contracts for x in c["docs"])
    doc_ids.update(x for m in modules for x in m["docs"])
    return {"schema": "atlas.packet/v1", "project_id": a["project"]["id"], "objective": a["project"]["objective"],
            "authority_ref": a["project"]["authority_ref"], "mode": a["project"]["mode"], "source_sha256": a["source_sha256"],
            "as_of": a["as_of"], "work_path": a["work_paths"][work_id], "work": w,
            "dependencies": [{"id": i, "state": by_id[i]["state"], "result": by_id[i]["result"]} for i in w["depends_on"]],
            "contracts": contracts, "modules": modules, "documents": [{k: d[k] for k in ("id", "path", "sha256", "bytes", "source_ref", "readback_at") + (("storage",) if "storage" in d else ())} for d in snapshot["documents"] if d["id"] in doc_ids],
            "authority_note": "Context packet is not a new authorization. Preserve the named writer and the existing project permission envelope."}


def impact(root, project_path, changed):
    """Read declarations without requiring old file pins to still match changed files."""
    root = Path(root).resolve()
    project = nav.parse(nav.read_selected(root, project_path, 512 * 1024))
    schema_validate(project, "atlas.project.schema.json")
    for path in changed:
        path_text(path, directory=True)
    works = []; work_paths = {}
    for rel in project["work_files"]:
        w = nav.parse(nav.read_selected(root, rel, 2 * 1024 * 1024)); schema_validate(w, "atlas.work.schema.json"); works.append(w)
        work_paths[w["id"]] = rel
    affected = {}; known = set()
    for w in works:
        artifact_paths = [a["path"] for a in w["artifacts"]]
        paths = artifact_paths + w["write_scope"] + [project_path, project["documents"]["path"], work_paths[w["id"]]] + [e["receipt"]["path"] for e in w["evidence"]]
        hits = sorted({c for c in changed if any(overlaps(c, p) for p in paths)})
        if hits:
            affected[w["id"]] = {"id": w["id"], "reason": "DIRECT_INPUT_OR_SCOPE", "changed": hits,
                                  "criteria": [c["id"] for c in w["criteria"]], "next_owner": w["writer"]}
            known.update(hits)
    again = True
    while again:
        again = False
        for w in works:
            if w["id"] not in affected and any(i in affected for i in w["depends_on"]):
                affected[w["id"]] = {"id": w["id"], "reason": "DEPENDENCY_CHANGED", "changed": [],
                                      "criteria": [c["id"] for c in w["criteria"]], "next_owner": w["writer"]}
                again = True
    return {"schema": "atlas.impact/v1", "status": "DECLARED_IMPACT_ONLY", "affected": list(affected.values()),
            "unmapped": [p for p in changed if p not in known],
            "reuse_rule": "Unaffected evidence stays valid for its recorded scope, subjects, environment and acceptance basis; this command does not run tests or prove semantic completeness."}


def discover(root, project_path, under):
    root = Path(root).resolve()
    project = nav.parse(nav.read_selected(root, project_path, 512 * 1024)); schema_validate(project, "atlas.project.schema.json")
    manifest = nav.parse(nav.read_selected(root, project["documents"]["path"], nav.MAX_INPUT))
    registered = {d["path"]: d for d in manifest["documents"]}
    found = []; seen = set()
    excluded = {".git", "node_modules", ".venv", "venv", "__pycache__", ".ssh", "secrets", ".aws", ".codex"}
    for rel in under:
        path_text(rel, directory=True)
        start = nav.safe(root, rel.rstrip("/"), directory=True)
        require(not any(p in excluded for p in PurePosixPath(rel).parts), "DISCOVERY_EXCLUDED_ROOT")
        for base, dirs, files in os.walk(start, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in excluded and not d.startswith(".") and not (Path(base)/d).is_symlink())
            for name in sorted(files):
                p = Path(base)/name
                if p.is_symlink() or name.startswith(".") or p.suffix.lower() not in (".md", ".json", ".txt", ".yaml", ".yml"):
                    continue
                relative = p.relative_to(root).as_posix()
                if relative in seen:
                    continue
                seen.add(relative); require(len(seen) <= MAX_ITEMS, "DISCOVERY_LIMIT")
                old = registered.get(relative)
                # Discovery only enumerates unknown files; selected known documents can be hashed for drift.
                row = {"path": relative, "bytes": p.stat().st_size, "classification": "UNREGISTERED"}
                if old:
                    raw = nav.read_selected(root, relative)
                    row.update(sha256=nav.digest(raw), classification="UNCHANGED" if nav.digest(raw) == old["sha256"] and len(raw) == old["bytes"] else "CHANGED")
                    row["document_id"] = old["id"]
                found.append(row)
    for relative, doc in registered.items():
        if any(relative == r.rstrip("/") or relative.startswith(r.rstrip("/")+"/") for r in under) and relative not in seen:
            found.append({"path": relative, "document_id": doc["id"], "classification": "MISSING_OR_EXCLUDED"})
    return {"schema": "atlas.discovery/v1", "scope": under, "files": found,
            "note": "Unregistered files are metadata candidates only. Contents, authority, contract role and completion are not inferred."}


def pins(root, paths):
    root = Path(root).resolve(); out = []
    for path in paths:
        path_text(path); raw = nav.read_selected(root, path, 8 * 1024 * 1024)
        out.append({"path": path, "sha256": nav.digest(raw), "bytes": len(raw)})
    return {"schema": "atlas.pins/v1", "files": out}


def initialize(root, project_id, title, objective, writer, authority_ref, mode, at=None):
    """Create a new .atlas control directory exclusively, never overwrite a project.

    Existing documents and matrices are inventoried by the owning bootstrap work;
    their state is not fabricated by this scaffold.
    """
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "INVALID_ROOT")
    root = root.resolve(); target = root/".atlas"
    require(not target.exists() and not target.is_symlink(), "ATLAS_ALREADY_EXISTS_RECONCILE")
    nav.ident(project_id)
    for value in (title, objective, writer, authority_ref):
        nav.text(value, "init parameter")
    require(writer.strip().upper() != "UNKNOWN", "INIT_WRITER_REQUIRED")
    require(mode in ("native", "projection"), "INIT_MODE")
    at = at or datetime.now(timezone.utc).isoformat(); nav.stamp(at)
    files = {}
    def put(path, value):
        files[path] = nav.canonical(value) if isinstance(value, (dict, list)) else value.encode("utf-8")
    def pin(path):
        raw = files[path]
        return {"path": ".atlas/"+path, "sha256": nav.digest(raw), "bytes": len(raw)}
    put("documents/PROJECT.md", f"# {title}\n\n## Owner objective\n\n{objective}\n\n## Authority\n\n{authority_ref}\n\n## State\n\nAtlas control records initialized. Project inventory, architecture, APIs, prior work, and history are still UNKNOWN. Populate them from actual sources in the bootstrap work item.\n")
    doc = {"id": "DOC-PROJECT", "title": "Project objective and state", **pin("documents/PROJECT.md"), "kind": "markdown", "version": "1",
           "lifecycle": "current", "source_ref": authority_ref, "readback_at": at, "evidence_state": "DESIGN", "execution": "NOT_RUN"}
    dn = {"schema": "docs-navigator.input/v1", "project": {"id": project_id, "title": title, "scope_note": "Bootstrap: completeness of documentation and history is not yet established."},
          "release": {"id": "DOCS-BOOTSTRAP-1", "created_at": at, "previous": None}, "documents": [doc], "modules": [], "contracts": [], "relations": [],
          "matrix": {"doc": None}, "bindings": [], "history": [{"id": "DOC-EVENT-1", "at": at, "kind": "created", "summary": "Owner objective recorded; the actual inventory has not yet been compiled", "entity_ids": ["DOC-PROJECT"]}]}
    put("documents/DOCS_INDEX.json", dn)
    work = {"schema": "atlas.work/v1", "id": "ATLAS-BOOTSTRAP", "parent_id": None, "title": "Document the project and connect existing work",
            "objective": objective, "outcome": "The complete actual project inventory is linked to documentation, APIs, all work, and available matrix versions",
            "criteria": [{"id": "BOOTSTRAP-AC", "text": "Completeness is supported by an exact inventory and review by the owner; all gaps are explicitly listed", "required_scope": "DOCUMENTARY", "artifact_ids": ["A-PROJECT"]}],
            "state": "PLANNED", "writer": writer, "write_scope": [".atlas/"], "assigned_to": writer, "depends_on": [],
            "artifacts": [{"id": "A-PROJECT", **pin("documents/PROJECT.md"), "role": "input", "entity_ids": ["DOC-PROJECT"]}],
            "evidence": [], "acceptance": [], "activity": None, "blocker": None, "result": None,
            "remaining": "Inventory, relations, architectural boundaries, contracts, existing work/matrix history, and scoped review",
            "next_action": {"actor": writer, "action": "Read the authoritative instructions; register documents/modules/APIs/work and all available matrices without changing the existing writer"},
            "events": [{"id": "BOOTSTRAP-EVENT-1", "at": at, "actor": writer, "kind": "CREATED", "summary": "Controlled bootstrap created; unknown information has not been filled with guesses", "evidence_ids": []}]}
    put("work/ATLAS-BOOTSTRAP.json", work)
    values = {"goals": ["PROJECT-GOAL"], "modules": [], "contracts": [], "documents": ["DOC-PROJECT"], "source": [], "works": ["ATLAS-BOOTSTRAP"]}
    inventory = {"schema": "atlas.inventory/v1", "id": "INVENTORY-BOOTSTRAP", "scope_note": "Incomplete initial inventory; all original project surfaces still need to be checked", "source_ref": authority_ref, "observed_at": at,
                 "domains": [{"id": k, "title": k, "exhaustive": False, "items": v, "exclusions": []} for k, v in values.items()]}
    put("INVENTORY.json", inventory)
    project = {"schema": "atlas.project/v1", "id": project_id, "title": title, "objective": objective, "scope_note": "Bootstrap. Coverage of documentation, work, and earlier matrices is still partial.",
               "authority_ref": authority_ref, "writer": writer, "mode": mode, "source_ref": authority_ref, "documents": pin("documents/DOCS_INDEX.json"), "work_files": [".atlas/work/ATLAS-BOOTSTRAP.json"],
               "coverage": {"inventory": pin("INVENTORY.json"), "bindings": [{"domain_id": "goals", "item_id": "PROJECT-GOAL", "entity_ids": ["DOC-PROJECT"], "work_ids": ["ATLAS-BOOTSTRAP"]},
                 {"domain_id": "documents", "item_id": "DOC-PROJECT", "entity_ids": ["DOC-PROJECT"], "work_ids": []}, {"domain_id": "works", "item_id": "ATLAS-BOOTSTRAP", "entity_ids": [], "work_ids": ["ATLAS-BOOTSTRAP"]}]}, "matrix_history": []}
    put("project.json", project)
    schema_validate(project, "atlas.project.schema.json"); schema_validate(work, "atlas.work.schema.json"); schema_validate(inventory, "atlas.inventory.schema.json")
    stage = Path(tempfile.mkdtemp(prefix=".atlas-init-", dir=root))
    for rel, raw in files.items():
        p = stage/rel; p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("xb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    nav.sync_directory(stage)
    # A concurrent initializer must not be replaced, including an empty directory.
    lock = root/".atlas-init.lock"
    try:
        fd = os.open(lock, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise Invalid("INIT_LOCK_RECONCILE_REQUIRED") from exc
    try:
        os.close(fd)
        require(not target.exists() and not target.is_symlink(), "ATLAS_ALREADY_EXISTS_RECONCILE")
        os.rename(stage, target); nav.sync_directory(root)
    finally:
        lock.unlink()
    checked = load_project(root, ".atlas/project.json", at=at)
    return {"status": "INITIALIZED_PARTIAL", "project": ".atlas/project.json", "files": [".atlas/"+p for p in files],
            "source_sha256": checked["atlas"]["source_sha256"], "next_action": work["next_action"], "coverage": checked["atlas"]["coverage"]}


def current_output(output):
    """Read one current immutable release; never repair an unknown output state."""
    out = Path(output).absolute()
    for p in (out, *out.parents):
        require(not p.is_symlink(), "OUTPUT_SYMLINK")
    if not out.exists():
        return None, None
    require(out.is_dir(), "INVALID_OUTPUT_ROOT")
    if not (out/"CURRENT.json").exists():
        require(not (out/"CURRENT.json").is_symlink(), "OUTPUT_SYMLINK")
        releases = out/"releases"
        require(not releases.is_symlink(), "OUTPUT_SYMLINK")
        require(not releases.exists() or releases.is_dir() and not any(releases.iterdir()), "MISSING_CURRENT_RECONCILE_REQUIRED")
        return None, None
    pointer = nav.parse(nav.read_selected(out, "CURRENT.json", 16384))
    nav.shape(pointer, "schema release manifest_sha256", "pointer")
    require(pointer["schema"] == "docs-navigator.current/v1", "POINTER_SCHEMA")
    require(isinstance(pointer["manifest_sha256"], str) and nav.SHA.fullmatch(pointer["manifest_sha256"]), "POINTER_SHA")
    sha, snapshot = nav.verify_release(out, pointer["release"], pointer["manifest_sha256"])
    require("atlas" in snapshot, "OUTPUT_FAMILY_CHANGED")
    return {**pointer, "manifest_sha256": sha}, snapshot


def _history_parent(out, snapshot, stats):
    """Direct archive link; a legacy tail may need a manifest-only SHA lookup."""
    _, spec, _ = _archive_record(snapshot)
    expected = snapshot["input"]["release"]["previous"]
    if spec is not None:
        require(expected == spec["previous_manifest_sha256"], "ARCHIVE_RELEASE_LINK")
        return spec["previous_release"], expected
    if expected is None:
        return None
    # Legacy releases recorded only the parent manifest SHA. This compatibility
    # lookup is used solely by an explicit history request, never by refresh.
    found = None
    for path in (out / "releases").iterdir():
        require(path.is_dir() and not path.is_symlink(), "INVALID_RELEASE_ENTRY")
        nav.ident(path.name)
        raw = nav.read_selected(out, f"releases/{path.name}/MANIFEST.json", 512 * 1024)
        stats["legacy_manifest_headers_read"] += 1
        if nav.digest(raw) == expected:
            require(found is None, "DUPLICATE_MANIFEST_SHA")
            found = path.name
    require(found is not None, "BROKEN_RELEASE_CHAIN")
    return found, expected


def _history_archive_link(child, parent):
    """Verify one count and identity link without reopening any source raw file."""
    a, spec, total = _archive_record(child)
    b, _, previous_total = _archive_record(parent)
    require(a["project"]["id"] == b["project"]["id"] and a["project"]["mode"] == b["project"]["mode"], "ARCHIVE_PROJECT_CHANGED")
    if spec is not None:
        require(spec["previous_release"] == parent["input"]["release"]["id"]
                and a["projection_archive"]["previous_snapshot_sha256"] == nav.digest(nav.canonical(parent)), "ARCHIVE_PARENT_MISMATCH")
        require(a["projection_archive"]["previous_matrix_history_total"] == previous_total
                and total == previous_total + len(a.get("matrix_history", [])), "ARCHIVE_HISTORY_TOTAL")
    else:
        old = b.get("matrix_history", [])
        require(a.get("matrix_history", [])[:len(old)] == old, "MATRIX_VERSION_HISTORY_REWRITE")


def _paged_history(out, pointer, current, limit, cursor):
    stats = {"legacy_manifest_headers_read": 0, "release_readbacks": 1}
    _, current_spec, current_total = _archive_record(current)
    root_spec = current_spec
    require(root_spec is not None, "HISTORY_CURSOR_REQUIRES_ARCHIVE")
    parts = PurePosixPath(path_text(root_spec["output"])).parts
    require(tuple(out.parts[-len(parts):]) == parts, "ARCHIVE_OUTPUT_BINDING")
    project_root = out.parents[len(parts)-1]
    child = None; anchor = None
    if cursor is not None:
        require(isinstance(cursor, str) and len(cursor) <= 200 and "/" in cursor, "HISTORY_CURSOR")
        rid, expected = cursor.rsplit("/", 1)
        nav.ident(rid); require(nav.SHA.fullmatch(expected), "HISTORY_CURSOR")
        if rid == pointer["release"] and expected == pointer["manifest_sha256"]:
            child = current
        else:
            _, child = nav.verify_release(out, rid, expected)
            stats["release_readbacks"] += 1
        a, _, _ = _archive_record(child)
        require(a["project"]["id"] == current["atlas"]["project"]["id"], "ARCHIVE_PROJECT_CHANGED")
        anchor = {"release": rid, "manifest_sha256": expected}
        pending = _history_parent(out, child, stats)
        require(pending is not None, "HISTORY_CURSOR_AT_END")
    else:
        pending = (pointer["release"], pointer["manifest_sha256"])
    linked = []; imported = []; seen = set(); matrix_seen = {}; next_cursor = None
    while pending is not None and len(linked) < limit:
        rid, expected = pending
        require(expected not in seen, "BROKEN_RELEASE_CHAIN")
        if rid == pointer["release"] and expected == pointer["manifest_sha256"]:
            snapshot = current; sha = expected
        else:
            sha, snapshot = nav.verify_release(out, rid, expected)
            stats["release_readbacks"] += 1
        a, spec, total = _archive_record(snapshot)
        if child is not None:
            _history_archive_link(child, snapshot)
        entries = a.get("matrix_history", [])
        if linked and len(imported) + len(entries) > MAX_ITEMS:
            break
        seen.add(sha)
        linked.append({"id": rid, "at": snapshot["input"]["release"]["created_at"], "manifest_sha256": sha,
                       "source_sha256": a["source_sha256"], "work_count": len(a["works"]),
                       "snapshot_path": f"releases/{rid}/snapshot.json", "html_path": f"releases/{rid}/index.html",
                       "matrix_history_total": total, "matrix_page_count": len(entries),
                       "matrix_page_kind": "NEW_ARCHIVE_ENTRIES" if spec else "CUMULATIVE_LEGACY"})
        for entry in entries:
            if entry["id"] in matrix_seen:
                require(spec is None and matrix_seen[entry["id"]] == entry, "ARCHIVE_HISTORY_DUPLICATE")
                continue
            matrix_seen[entry["id"]] = entry
            path_text(entry["file"]["path"])
            imported.append({**entry, "retained_in_release": rid, "manifest_sha256": sha,
                             "file_target": str(project_root / entry["file"]["path"]),
                             "source_validation": "VERIFIED_AT_IMPORT", "raw_source_read_now": False})
        child = snapshot
        pending = _history_parent(out, snapshot, stats)
        next_cursor = f"{rid}/{sha}" if pending is not None else None
    complete = pending is None
    if complete and cursor is None:
        require(len(matrix_seen) == current_total, "ARCHIVE_HISTORY_TOTAL")
    return {"schema": "atlas.history/v1", "status": "VERIFIED_CHAIN" if complete and cursor is None else "VERIFIED_PAGE",
            "current": pointer["release"], "current_manifest_sha256": pointer["manifest_sha256"],
            "order": "newest_first", "revisions": linked, "imported_matrix_history": imported,
            "matrix_history_total": current_total, "has_more": not complete, "next_cursor": next_cursor,
            "cursor_anchor": anchor, "ancestry_to_current": "VERIFIED" if cursor is None else "NOT_RETRAVERSED_FOR_CALLER_SUPPLIED_CURSOR",
            "project_root": str(project_root), "source_validation": "VERIFIED_AT_IMPORT",
            "raw_source_reads": 0, "orphan_scan": "NOT_RUN_FOR_PAGED_HISTORY", "readback": stats,
            "history_limit": {"release_limit": limit, "matrix_entry_limit": MAX_ITEMS,
                              "remaining_pages": "NOT_LOADED" if not complete else "NONE_AFTER_PAGE_ANCHOR",
                              "legacy_tail": "Old SHA-only links may require manifest-header lookup on this explicit request; refresh follows one direct parent only."}}


def history(output, limit=50, cursor=None):
    require(type(limit) is int and 1 <= limit <= 100, "HISTORY_PAGE_LIMIT")
    pointer, current = current_output(output)
    if current is None:
        require(cursor is None, "HISTORY_CURSOR_WITHOUT_RELEASES")
        return {"schema": "atlas.history/v1", "status": "NO_RELEASES", "revisions": []}
    if current["atlas"]["project"].get("projection_archive") is not None:
        return _paged_history(Path(output).resolve(), pointer, current, limit, cursor)
    require(cursor is None, "HISTORY_CURSOR_REQUIRES_ARCHIVE")
    out = Path(output).resolve(); all_releases = {}; by_sha = {}
    for p in sorted((out/"releases").iterdir()):
        require(p.is_dir() and not p.is_symlink(), "INVALID_RELEASE_ENTRY")
        sha, snapshot = nav.verify_release(out, p.name)
        require("atlas" in snapshot, "OUTPUT_FAMILY_CHANGED")
        require(sha not in by_sha, "DUPLICATE_MANIFEST_SHA")
        all_releases[p.name] = (sha, snapshot); by_sha[sha] = p.name
    linked = []; key = pointer["manifest_sha256"]; seen = set()
    while key is not None:
        require(key in by_sha and key not in seen, "BROKEN_RELEASE_CHAIN")
        seen.add(key); rid = by_sha[key]; sha, snapshot = all_releases[rid]
        a = snapshot["atlas"]
        linked.append({"id": rid, "at": snapshot["input"]["release"]["created_at"], "manifest_sha256": sha,
                       "source_sha256": a["source_sha256"], "work_count": len(a["works"]),
                       "snapshot_path": f"releases/{rid}/snapshot.json", "html_path": f"releases/{rid}/index.html"})
        key = snapshot["input"]["release"]["previous"]
    linked.reverse()
    return {"schema": "atlas.history/v1", "status": "VERIFIED_CHAIN", "current": pointer["release"], "revisions": linked,
            "unreferenced_releases": [rid for rid, (sha, _) in all_releases.items() if sha not in seen],
            "imported_matrix_history": current["atlas"].get("matrix_history", []),
            "history_limit": "Contains every locally retained release on this verified chain; absent pre-Atlas versions remain an explicit onboarding gap."}


def diff(output, before_id, after_id):
    out = Path(output).resolve()
    _, before = nav.verify_release(out, before_id); _, after = nav.verify_release(out, after_id)
    require("atlas" in before and "atlas" in after, "OUTPUT_FAMILY_CHANGED")
    a = {w["id"]: _raw_work(w) for w in before["atlas"]["works"]}; b = {w["id"]: _raw_work(w) for w in after["atlas"]["works"]}
    require(before["atlas"]["project"]["id"] == after["atlas"]["project"]["id"], "PROJECT_CHANGED")
    changed = []
    for wid in sorted(set(a)|set(b)):
        if a.get(wid) != b.get(wid):
            fields = sorted(k for k in set(a.get(wid, {}))|set(b.get(wid, {})) if a.get(wid, {}).get(k) != b.get(wid, {}).get(k))
            changed.append({"id": wid, "before_state": a.get(wid, {}).get("state"), "after_state": b.get(wid, {}).get("state"),
                            "changed_fields": fields, "new_event_ids": [e["id"] for e in b.get(wid, {}).get("events", []) if e["id"] not in {x["id"] for x in a.get(wid, {}).get("events", [])}]})
    old = {p["path"]: p["sha256"] for p in before["atlas"]["source_pins"]}
    new = {p["path"]: p["sha256"] for p in after["atlas"]["source_pins"]}
    return {"schema": "atlas.diff/v1", "before": before_id, "after": after_id, "works": changed,
            "changed_paths": [p for p in sorted(set(old)|set(new)) if old.get(p) != new.get(p)]}


def cycle(root, project_path, output, release=None, at=None, previous=None, *, _source_operation=None, _writer_lease=None, _source_guard=None, _source_orphan=None):
    """Fixed finish-block pipeline: read once -> validate -> delta -> CAS release -> summary.

    No change means no new release, event or repeated test. An explicit repetition of
    an existing release is reconciled against its original timestamp and full bytes.
    """
    pointer, old = current_output(output)
    chosen_at = at or (old["input"]["release"]["created_at"] if old and release == pointer["release"] else datetime.now(timezone.utc).isoformat())
    s = load_project(root, project_path, at=chosen_at, _source_operation=_source_operation)
    _archive_output(root, s, output)
    if old is not None:
        require(old["atlas"]["project"]["id"] == s["atlas"]["project"]["id"], "PROJECT_CHANGED")
    same = old is not None and old["atlas"]["source_sha256"] == s["atlas"]["source_sha256"] and old["atlas"].get("toolchain_sha256") == s["atlas"]["toolchain_sha256"]
    if same and (release is None or release != pointer["release"]):
        require(previous is None or previous == pointer["manifest_sha256"], "EXPECTED_PREVIOUS_MISMATCH")
        return {"status": "NO_CHANGE", "release": pointer["release"], "manifest_sha256": pointer["manifest_sha256"],
                "as_of": chosen_at, "summary": s["atlas"]["summary"], "coverage": s["atlas"]["coverage"], "next_actions": next_actions(s)}
    old_pins = {p["path"]: p["sha256"] for p in old["atlas"]["source_pins"]} if old else {}
    new_pins = {p["path"]: p["sha256"] for p in s["atlas"]["source_pins"]}
    changed = sorted(p for p in set(old_pins)|set(new_pins) if old_pins.get(p) != new_pins.get(p))
    release = release or "ATLAS-" + nav.digest(nav.canonical([s["atlas"]["source_sha256"], s["atlas"]["toolchain_sha256"]]))[:20]
    nav.ident(release)
    if old and release == pointer["release"]:
        expected = old["input"]["release"]["previous"] if previous is None else previous
    else:
        expected = previous if previous is not None else (pointer["manifest_sha256"] if pointer else None)
    s["input"]["release"] = {"id": release, "created_at": chosen_at, "previous": expected}
    s["input_sha256"] = nav.digest(nav.canonical({"source_sha256": s["atlas"]["source_sha256"], "toolchain_sha256": s["atlas"]["toolchain_sha256"], "release": s["input"]["release"]}))
    result = nav.publish(s, output, render_fn=nav.render, history_fn=check_history, version=VERSION, _lease=_writer_lease, _source_guard=_source_guard, _source_orphan=_source_orphan)
    return {**result, "as_of": chosen_at, "changed_paths": changed, "summary": s["atlas"]["summary"],
            "coverage": s["atlas"]["coverage"], "next_actions": next_actions(s),
            "checks_run": ["local schemas", "declared byte pins", "work invariants", "current release integrity", "history continuity"],
            "product_tests": "NOT_RUN_BY_ATLAS"}


def next_actions(snapshot):
    return [{"work_id": w["id"], "state": w["state"], **w["next_action"]} for w in snapshot["atlas"]["works"] if w["next_action"]]


def run_routine(args):
    if args.routine in ("finish-block", "integrate"):
        require(args.output is not None, "OUTPUT_REQUIRED_FOR_ROUTINE")
        return cycle(args.root, args.project, args.output, args.release, args.at, args.previous)
    if args.routine == "reconcile":
        require(args.output is not None, "OUTPUT_REQUIRED_FOR_ROUTINE")
        pointer, snapshot = current_output(args.output)
        return {"status": "CURRENT_VERIFIED" if pointer else "NO_RELEASES", "current": pointer,
                "source_sha256": snapshot["atlas"]["source_sha256"] if snapshot else None,
                "note": "Read-only reconciliation; orphan releases and locks are never activated or removed automatically."}
    s = load_project(args.root, args.project, at=args.at)
    if args.routine == "session-start":
        return {"status": "CONTEXT_LOADED", "summary": s["atlas"]["summary"], "coverage": s["atlas"]["coverage"],
                "packet": packet(s, args.work) if args.work else None, "next_actions": next_actions(s)}
    return {"status": "PROJECT_CONTROL_REVIEW", "source_sha256": s["atlas"]["source_sha256"],
            "coverage": s["atlas"]["coverage"], "summary": s["atlas"]["summary"], "issues": s["atlas"]["issues"],
            "next_actions": next_actions(s), "product_execution": "NOT_RUN"}


def main():
    if sys.argv[1:2] == ["source-relocate"]:
        import source_relocation
        return source_relocation.main(sys.argv[2:])
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "build", "basis", "packet", "impact", "discover", "pins", "coverage", "cycle"):
        p = subs.add_parser(name); p.add_argument("--root", required=True)
        if name != "pins":
            p.add_argument("--project", default=".atlas/project.json")
        if name in ("validate", "packet", "coverage"):
            p.add_argument("--at")
        if name == "build":
            p.add_argument("--output", required=True); p.add_argument("--release", required=True); p.add_argument("--at", required=True); p.add_argument("--previous")
        if name == "cycle":
            p.add_argument("--output", required=True); p.add_argument("--release"); p.add_argument("--at"); p.add_argument("--previous")
        if name == "packet":
            p.add_argument("--work", required=True)
        if name == "impact":
            p.add_argument("--changed", action="append", required=True)
        if name == "discover":
            p.add_argument("--under", action="append", required=True)
        if name == "pins":
            p.add_argument("--path", action="append", required=True)
    p = subs.add_parser("history"); p.add_argument("--output", required=True); p.add_argument("--limit", type=int, default=50); p.add_argument("--cursor")
    p = subs.add_parser("diff"); p.add_argument("--output", required=True); p.add_argument("--before", required=True); p.add_argument("--after", required=True)
    p = subs.add_parser("run")
    p.add_argument("routine", choices=("session-start", "finish-block", "integrate", "reconcile", "project-audit"))
    p.add_argument("--root", required=True); p.add_argument("--project", default=".atlas/project.json")
    p.add_argument("--output"); p.add_argument("--work"); p.add_argument("--release"); p.add_argument("--at"); p.add_argument("--previous")
    subs.add_parser("methods")
    p = subs.add_parser("init")
    for name in ("root", "project-id", "title", "objective", "writer", "authority-ref"):
        p.add_argument("--"+name, required=True)
    p.add_argument("--mode", choices=("native", "projection"), required=True); p.add_argument("--at")
    args = parser.parse_args()
    try:
        if args.command == "init":
            result = initialize(args.root, args.project_id, args.title, args.objective, args.writer, args.authority_ref, args.mode, args.at)
        elif args.command == "run":
            result = run_routine(args)
        elif args.command == "methods":
            result = nav.parse((Path(__file__).parent/"OPERATIONS.json").read_bytes())
        elif args.command == "history":
            result = history(args.output, args.limit, args.cursor)
        elif args.command == "diff":
            result = diff(args.output, args.before, args.after)
        elif args.command == "cycle":
            result = cycle(args.root, args.project, args.output, args.release, args.at, args.previous)
        elif args.command == "build":
            result = build(args.root, args.project, args.output, args.release, args.at, args.previous)
        elif args.command == "pins":
            result = pins(args.root, args.path)
        elif args.command == "impact":
            result = impact(args.root, args.project, args.changed)
        elif args.command == "discover":
            result = discover(args.root, args.project, args.under)
        else:
            s = load_project(args.root, args.project, at=getattr(args, "at", None), validate=args.command != "basis")
            if args.command == "basis":
                result = {"schema": "atlas.basis/v1", "basis": {w["id"]: basis(w) for w in s["atlas"]["works"]}}
            elif args.command == "packet":
                result = packet(s, args.work)
            elif args.command == "coverage":
                result = s["atlas"]["coverage"]
            else:
                result = {"status": "VALIDATED_LOCAL", "version": VERSION, "source_sha256": s["atlas"]["source_sha256"],
                          "as_of": s["atlas"]["as_of"], "summary": s["atlas"]["summary"], "issues": s["atlas"]["issues"]}
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except (Invalid, OSError, RecursionError, UnicodeError) as exc:
        print(json.dumps({"status": "REFUSED", "code": str(exc) if isinstance(exc, Invalid) else type(exc).__name__}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
