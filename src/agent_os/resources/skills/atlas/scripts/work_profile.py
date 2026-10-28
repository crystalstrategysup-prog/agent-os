"""Optional pure documentation-depth selection, never authorization or execution."""

VERSION = "1.0.0"
CHANGES = ("source", "docs", "architecture", "contract", "data", "multi-module",
           "multi-actor", "new-project", "instruction-routing")
FULL_CHANGES = set(CHANGES) - {"source", "docs"}
STATES = ("CURRENT", "UNKNOWN", "STALE", "CONFLICT")


def select_profile(route, *, changes=(), bounded=False, context="UNKNOWN",
                   writer="UNKNOWN", full=False):
    """Compose the existing AgentOS workflow route with explicit scope facts.

    Facts are caller declarations, not observed evidence. No file, registry,
    network, credential, lock or task is read or written by this function.
    """
    if (not isinstance(route, dict) or route.get("schema") != "agentos.workflow-route/v1"
            or route.get("mode") not in {"FAST_PATH", "DOCUMENTATION_FIRST", "TARGET_AUTHORITY_REQUIRED"}
            or not isinstance(route.get("effects"), list)):
        raise ValueError("WORK_PROFILE_ROUTE_REQUIRED")
    if (not isinstance(changes, (list, tuple)) or len(changes) > len(CHANGES)
            or any(not isinstance(x, str) or x not in CHANGES for x in changes)
            or len(set(changes)) != len(changes)):
        raise ValueError("WORK_PROFILE_CHANGES")
    if any(type(x) is not bool for x in (bounded, full)):
        raise ValueError("WORK_PROFILE_BOOLEAN")
    if context not in STATES or writer not in STATES:
        raise ValueError("WORK_PROFILE_STATE")
    reasons = []
    direct = route["mode"] == "FAST_PATH" and not route["effects"]
    if direct and changes:
        raise ValueError("WORK_PROFILE_READ_ONLY_WITH_CHANGES")
    if direct:
        mode, status = "READ_ONLY", "FAST_PATH"
    else:
        if full:
            reasons.append("EXPLICIT_FULL")
        reasons.extend(sorted(set(changes) & FULL_CHANGES))
        if not bounded or not changes:
            reasons.append("BOUNDED_KNOWN_CHANGE_NOT_ESTABLISHED")
        if route["mode"] == "TARGET_AUTHORITY_REQUIRED":
            reasons.append("TARGET_AUTHORITY_REQUIRED")
        for name, value in (("context", context), ("writer", writer)):
            if value != "CURRENT":
                reasons.append(name.upper() + "_" + value)
        mode = "FULL" if reasons else "MINIMAL"
        status = ("BLOCKED" if route["mode"] == "TARGET_AUTHORITY_REQUIRED" else
                  "UNKNOWN" if context != "CURRENT" or writer != "CURRENT" else "PROFILE_SELECTED")
    return {"schema": "atlas.work-profile/v1", "version": VERSION,
            "status": status, "mode": mode, "reasons": reasons,
            "basis": "CALLER_DECLARATIONS_NOT_OBSERVED_EVIDENCE",
            "foundation_route": route,
            "documents": ("NONE_FOR_ORDINARY_READING" if direct else
                          "APPLICABLE_EXISTING_DOCUMENTS_ONLY" if mode == "MINIMAL" else
                          "APPLICABLE_ARCHITECTURE_CONTRACTS_EVIDENCE"),
            "policy_loading": "EXPLICIT_EXISTING_CONTEXT_ROUTE_REQUIRED_FOR_DEPENDENT_WORK",
            "ready_granted": False, "product_writes_authorized": False,
            "external_authority_granted": False, "execution": "NOT_RUN",
            "native_hooks": "DISABLED", "writes": [],
            "next_action": ("Answer directly under existing read access" if direct else
                            "Resolve exact unknown/stale/conflicting inputs before dependent writes" if status == "UNKNOWN" else
                            "Use existing task, documents, READY and exact target gates; this result grants none")}
