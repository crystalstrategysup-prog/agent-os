"""Local POSIX authenticated adapter for the provider-neutral library API."""

from __future__ import annotations

import argparse
import base64
from pathlib import Path

from .handoff import Library, local_principal
from .handoff_index import CONTENT_PAGE_SCHEMA, GENERATION_PAGE_SCHEMA
from .handoff_store import HandoffError, bounded
from .safeio import GateError, read_json_input


def command(argv):
    p = argparse.ArgumentParser(prog="agentos library")
    p.add_argument("--root", type=Path, required=True)
    s = p.add_subparsers(dest="action", required=True)
    s.add_parser("init")
    build = s.add_parser("build")
    build.add_argument(
        "--input", required=True, help="JSON document file, or - for stdin"
    )
    build.add_argument(
        "--assets", required=True, help="JSON document file, or - for stdin"
    )
    build.add_argument("--expected-revision")
    build.add_argument(
        "--profile", choices=["completion", "checkpoint"], default="completion"
    )
    validate = s.add_parser("validate")
    validate.add_argument(
        "--ref", required=True, help="JSON document file, or - for stdin"
    )
    validate.add_argument(
        "--profile", choices=["completion", "checkpoint"], default="completion"
    )
    publish = s.add_parser("publish")
    publish.add_argument(
        "--ref", required=True, help="JSON document file, or - for stdin"
    )
    publish.add_argument("--expected-generation", type=int, required=True)
    publish.add_argument("--idempotency-key", required=True)
    publish.add_argument(
        "--profile", choices=["completion", "checkpoint"], default="completion"
    )
    search = s.add_parser("search")
    search.add_argument(
        "--query",
        required=True,
        help="JSON query document file, or - for stdin; not a JSON literal",
    )
    search.add_argument("--cursor")
    for action in ["resolve", "restore", "evidence"]:
        parser = s.add_parser(action)
        parser.add_argument("--id", required=True)
        parser.add_argument("--revision", default="current")
        if action == "restore":
            parser.add_argument("--destination", type=Path, required=True)
        if action == "evidence":
            parser.add_argument("--evidence-id", required=True)
    rebuild = s.add_parser("rebuild")
    rebuild.add_argument(
        "--registry-ref", required=True, help="JSON document file, or - for stdin"
    )
    rebuild.add_argument(
        "--page-format", choices=("v1", "v2"),
        help="Prepare an explicit format transition. By default retain the current format.",
    )
    repair = s.add_parser("publish-rebuild")
    repair.add_argument(
        "--ref", required=True, help="JSON document file, or - for stdin"
    )
    repair.add_argument("--expected-generation", type=int, required=True)
    reconcile = s.add_parser("reconcile")
    reconcile.add_argument("--idempotency-key", required=True)
    retract = s.add_parser("retract")
    retract.add_argument("--id", required=True)
    retract.add_argument("--reason", required=True)
    topics = s.add_parser("topics")
    topics.add_argument(
        "--input", required=True, help="JSON document file, or - for stdin"
    )
    task = s.add_parser("task")
    task.add_argument(
        "--input", required=True, help="JSON document file, or - for stdin"
    )
    task.add_argument("--expected-revision", type=int, required=True)
    s.add_parser("retirement")
    pack = s.add_parser("pack-build")
    pack.add_argument("--selection", type=Path, required=True)
    pack.add_argument("--directory", type=Path, required=True)
    pack.add_argument("--max-bytes", type=int, required=True)
    pack.add_argument("--reserve-bytes", type=int, required=True)
    attach = s.add_parser("pack-attach")
    attach.add_argument("--directory", type=Path, required=True)
    attach.add_argument("--manifest-sha256", required=True)
    unpack = s.add_parser("pack-restore")
    unpack.add_argument("--reserve-bytes", type=int, required=True)
    args = p.parse_args(argv)
    principal = local_principal()

    def data(path):
        # Caller documents are not immutable library objects. Never turn a
        # malformed argument into a diagnosis of library corruption.
        try:
            return read_json_input(Path(path))
        except (GateError, OSError, ValueError):
            raise HandoffError("INVALID_JSON_INPUT") from None

    if args.action == "init":
        library = Library.create(args.root, principal)
        return {
            "status": "created",
            "library_id": library._authorize(principal)["library_id"],
        }
    library = Library(args.root)
    if args.action.startswith("pack-"):
        try:
            if args.action == "pack-build":
                return library.pack_index_pages(
                    principal, selection=args.selection, directory=args.directory,
                    budget=args.max_bytes, reserve=args.reserve_bytes,
                )
            if args.action == "pack-attach":
                return library.attach_index_pack(
                    principal, directory=args.directory, manifest_sha256=args.manifest_sha256,
                )
            return library.restore_index_pack(principal, reserve=args.reserve_bytes)
        except OSError as exc:
            raise HandoffError("PACK_UNAVAILABLE") from exc
    if args.action == "build":
        assets = {key: bounded(Path(path)) for key, path in data(args.assets).items()}
        return {
            "status": "draft",
            "manifest_ref": library.build_handoff(
                data(args.input),
                args.expected_revision,
                principal,
                assets=assets,
                acceptance_profile=args.profile,
            ),
        }
    if args.action == "validate":
        return library.validate_handoff(data(args.ref), principal, args.profile)
    if args.action == "publish":
        return library.publish_handoff(
            data(args.ref),
            args.expected_generation,
            args.idempotency_key,
            principal,
            acceptance_profile=args.profile,
        )
    if args.action == "search":
        return library.search(data(args.query), principal, cursor=args.cursor)
    if args.action == "resolve":
        return library.resolve(args.id, principal, args.revision)
    if args.action == "restore":
        return library.restore(
            args.id, args.destination, principal, revision=args.revision
        )
    if args.action == "evidence":
        result = library.read_evidence(
            args.id, args.evidence_id, principal, revision=args.revision
        )
        result["bytes_base64"] = base64.b64encode(result.pop("bytes")).decode()
        return result
    if args.action == "rebuild":
        formats = {"v1": GENERATION_PAGE_SCHEMA, "v2": CONTENT_PAGE_SCHEMA}
        return {
            "status": "draft",
            "root_ref": library.rebuild_indexes(
                data(args.registry_ref), principal,
                page_schema=formats.get(args.page_format),
            ),
        }
    if args.action == "publish-rebuild":
        return library.publish_rebuild(
            data(args.ref), args.expected_generation, principal
        )
    if args.action == "reconcile":
        return library.reconcile(args.idempotency_key, principal)
    if args.action == "retract":
        return library.retract(args.id, args.reason, principal)
    if args.action == "topics":
        return library.register_topics(data(args.input), principal)
    if args.action == "task":
        return library.update_task(data(args.input), args.expected_revision, principal)
    return library.retirement_report(principal)
