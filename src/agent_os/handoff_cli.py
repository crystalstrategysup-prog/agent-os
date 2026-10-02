"""Local POSIX authenticated adapter for the provider-neutral library API."""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

from .handoff import Library, local_principal
from .handoff_store import bounded, parse


def command(argv):
    p = argparse.ArgumentParser(prog="agentos library")
    p.add_argument("--root", type=Path, required=True)
    s = p.add_subparsers(dest="action", required=True)
    s.add_parser("init")
    build = s.add_parser("build")
    build.add_argument("--input", required=True)
    build.add_argument("--assets", required=True)
    build.add_argument("--expected-revision")
    build.add_argument(
        "--profile", choices=["completion", "checkpoint"], default="completion"
    )
    validate = s.add_parser("validate")
    validate.add_argument("--ref", required=True)
    validate.add_argument(
        "--profile", choices=["completion", "checkpoint"], default="completion"
    )
    publish = s.add_parser("publish")
    publish.add_argument("--ref", required=True)
    publish.add_argument("--expected-generation", type=int, required=True)
    publish.add_argument("--idempotency-key", required=True)
    publish.add_argument(
        "--profile", choices=["completion", "checkpoint"], default="completion"
    )
    search = s.add_parser("search")
    search.add_argument("--query", required=True)
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
    rebuild.add_argument("--registry-ref", required=True)
    repair = s.add_parser("publish-rebuild")
    repair.add_argument("--ref", required=True)
    repair.add_argument("--expected-generation", type=int, required=True)
    reconcile = s.add_parser("reconcile")
    reconcile.add_argument("--idempotency-key", required=True)
    retract = s.add_parser("retract")
    retract.add_argument("--id", required=True)
    retract.add_argument("--reason", required=True)
    topics = s.add_parser("topics")
    topics.add_argument("--input", required=True)
    task = s.add_parser("task")
    task.add_argument("--input", required=True)
    task.add_argument("--expected-revision", type=int, required=True)
    s.add_parser("retirement")
    args = p.parse_args(argv)
    principal = local_principal()

    def data(path):
        return (
            parse(sys.stdin.buffer.read(16 * 1024 * 1024 + 1))
            if path == "-"
            else parse(bounded(Path(path)))
        )

    if args.action == "init":
        library = Library.create(args.root, principal)
        return {
            "status": "created",
            "library_id": library._authorize(principal)["library_id"],
        }
    library = Library(args.root)
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
        return {
            "status": "draft",
            "root_ref": library.rebuild_indexes(data(args.registry_ref), principal),
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
