"""Deterministic applicability selection; no checklist requires every format."""

from __future__ import annotations

from .safeio import GateError

TYPES = (
    "general",
    "backend",
    "frontend",
    "mobile",
    "data-ml",
    "platform",
    "embedded",
    "legacy",
)
FEATURES = (
    "http-api",
    "events",
    "database",
    "pii",
    "public",
    "deployment",
    "ui",
    "ml",
    "external-send",
    "safety-critical",
)
# Document ID -> (title, required headings). Alternative tools/formats are in catalog.json.
DOCS = {
    "dossier": ("Project dossier", ("Purpose", "Current state", "Boundaries", "Constraints")),
    "roadmap": ("Roadmap", ("Stages", "Dependencies", "Next stage")),
    "stage": ("Current stage contract", ("Objective", "Change scope", "Acceptance", "Rollback")),
    "quality": ("Verification strategy", ("Checks", "Evidence", "Limitations")),
    "architecture": ("Architecture", ("Context", "Components", "Trust boundaries", "Decisions")),
    "requirements": ("Requirements", ("Functions", "Nonfunctional requirements", "Rules")),
    "contracts": ("Interfaces and contracts", ("Interfaces", "Schemas", "Compatibility", "Errors")),
    "http-api": ("HTTP API", ("Operations", "Authorization", "OpenAPI", "Versioning")),
    "events": ("Event contracts", ("Channels", "Schemas", "Delivery", "Compatibility")),
    "data": ("Data model", ("Entities", "Storage", "Migrations", "Deletion")),
    "security": ("Security", ("Assets", "Threats", "Authority", "Secrets")),
    "privacy": ("Personal data", ("Categories", "Legal basis", "Retention", "Access")),
    "operations": ("Operations", ("Installation", "Verification", "Update", "Rollback", "Recovery")),
    "release": ("Release", ("Versions", "Contents", "Checks", "Publication")),
    "onboarding": ("Developer onboarding", ("Getting started", "Navigation", "Commands", "Troubleshooting")),
    "ux": ("User journeys", ("Users", "Scenarios", "Accessibility", "Acceptance")),
    "model-card": ("ML model and data", ("Purpose", "Data", "Evaluation", "Limitations")),
    "safety": ("Operational safety analysis", ("Hazards", "Controls", "Verification", "Responsibility")),
    "incident": ("Incident review", ("Impact", "Timeline", "Cause", "Actions")),
}
BASE = {"dossier", "roadmap", "stage", "quality"}
TYPE_DOCS = {
    "general": set(),
    "backend": {"architecture", "contracts", "security"},
    "frontend": {"requirements", "architecture", "ux"},
    "mobile": {"requirements", "architecture", "ux", "release"},
    "data-ml": {"requirements", "data", "model-card"},
    "platform": {"architecture", "contracts", "security", "operations", "onboarding"},
    "embedded": {"requirements", "architecture", "contracts", "operations"},
    "legacy": {
        "requirements",
        "architecture",
        "contracts",
        "data",
        "operations",
        "onboarding",
    },
}
FEATURE_DOCS = {
    "http-api": {"http-api", "contracts", "security"},
    "events": {"events", "contracts"},
    "database": {"data"},
    "pii": {"privacy", "security", "data"},
    "public": {"release", "security", "onboarding"},
    "deployment": {"operations", "release"},
    "ui": {"ux"},
    "ml": {"model-card", "data"},
    "external-send": {"security", "contracts"},
    "safety-critical": {"safety", "security"},
}


def select(
    types: list[str], features: list[str], change_kind: str = "implementation"
) -> dict:
    if not types or any(t not in TYPES for t in types):
        raise GateError("unknown_project_type")
    if any(f not in FEATURES for f in features):
        raise GateError("unknown_project_feature")
    reasons = {d: ["every_project"] for d in BASE}
    for typ in types:
        for d in TYPE_DOCS[typ]:
            reasons.setdefault(d, []).append("type:" + typ)
    for feature in features:
        for d in FEATURE_DOCS[feature]:
            reasons.setdefault(d, []).append("feature:" + feature)
    if change_kind == "incident":
        reasons["incident"] = ["change:incident"]
    return {
        "schema": "agentos.docs-selection/v1",
        "required": sorted(reasons),
        "reasons": reasons,
        "not_applicable": sorted(set(DOCS) - set(reasons)),
    }
