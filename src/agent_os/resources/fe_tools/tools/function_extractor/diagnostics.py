"""Bounded comparison of recorded paths. A divergence is not a cause verdict."""
from .api import _trace


def compare_trace_paths(actual, baseline):
    actual, baseline = _trace(actual), _trace(baseline)
    if any(trace["status"] not in {"RETURNED", "RAISED", "DENIED", "TIMEOUT", "REFUSED",
                                   "TRACE_LIMIT", "BLOCKED_LIVE_PROOF"} for trace in (actual, baseline)):
        raise ValueError("unsupported_trace_status")
    selected = [value.get("trace_recording", {}).get("selected_modules", [])
                for value in (actual, baseline)]
    if selected[0] != selected[1]:
        return {"schema": "function-extractor.path-comparison/v1", "status": "UNKNOWN",
                "reason": "recording_scope_differs", "root_cause_proven": False}
    keys = ("phase", "event", "evidence", "symbol", "file", "line", "exception",
            "status_code", "effect_started", "count")
    paths = [[{key: span[key] for key in keys if key in span} for span in trace.get("spans", [])]
             for trace in (actual, baseline)]
    prefix = 0
    for left, right in zip(*paths):
        if left != right:
            break
        prefix += 1
    incomplete_rows = [value.get("status") in {"TRACE_LIMIT", "TIMEOUT", "REFUSED", "BLOCKED_LIVE_PROOF"}
                       or value.get("trace_recording", {}).get("complete") is False
                       for value in (actual, baseline)]
    incomplete = any(incomplete_rows)
    different = prefix < min(map(len, paths))
    length_difference = len(paths[0]) != len(paths[1])
    unobserved_suffix = length_difference and incomplete_rows[0 if len(paths[0]) < len(paths[1]) else 1]
    if length_difference and not unobserved_suffix:
        different = True
    outcomes = []
    for trace in (actual, baseline):
        target = trace.get("target_outcome", {})
        summary = target.get("result_summary", trace.get("result_summary", {}))
        outcome = {"status": target.get("status", trace["status"]), "trace_status": trace["status"]}
        for key in ("state", "category", "error_category"):
            if type(summary.get(key)) is str and summary[key] in {"sent", "unknown", "failed", "retry_wait", "queued",
                                    "transport_or_receipt_unknown", "telegram_rejected"}:
                outcome[key] = summary[key]
        if type(trace.get("result_matches_expected")) is bool:
            outcome["result_matches_expected"] = trace["result_matches_expected"]
        exception = target.get("exception", trace.get("exception"))
        if exception:
            outcome["exception"] = exception
        outcomes.append(outcome)
    outcome_difference = outcomes[0] != outcomes[1] and not incomplete
    result = {"schema": "function-extractor.path-comparison/v1",
              "status": "DIVERGED" if different or outcome_difference else "UNKNOWN" if incomplete else "MATCH",
              "matching_prefix_events": prefix, "recording_incomplete": incomplete,
              "actual_status": actual["status"], "baseline_status": baseline["status"],
              "root_cause_proven": False}
    if outcome_difference:
        result["outcome_difference"] = {"actual": outcomes[0], "baseline": outcomes[1]}
    if unobserved_suffix and not different:
        result["reason"] = "matching_prefix_unobserved_suffix"
    if different:
        result["first_difference"] = {"event_index": prefix,
            "actual": paths[0][prefix] if prefix < len(paths[0]) else None,
            "baseline": paths[1][prefix] if prefix < len(paths[1]) else None}
        for label, trace in (("actual", actual), ("baseline", baseline)):
            preceding = trace.get("spans", [])[:prefix + 1]
            anchor = next((span for span in reversed(preceding) if span.get("file") and span.get("symbol")), None)
            result["first_difference"][label + "_anchor"] = (
                {key: anchor[key] for key in ("span_id", "file", "line", "symbol") if key in anchor}
                if anchor else None)
    return result
