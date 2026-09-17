# Result evidence

AgentOS separates process completion from outcome acceptance.

Use `agentos assess-result --file evidence.json` with this host-neutral shape:

```json
{
  "acceptance": ["tests", "user-flow"],
  "now": "2026-09-18T00:00:00Z",
  "max_age_seconds": 900,
  "evidence": [
    {
      "criterion": "tests",
      "status": "PASS",
      "current": true,
      "observed_at": "2026-09-17T23:59:00Z",
      "source": "local pytest",
      "subject_sha256": "replace-with-the-current-subject-sha256"
    }
  ]
}
```

Every acceptance criterion needs evidence. The newest observation for a
criterion wins. `current=true` means that the evidence is bound to the exact
current subject or runtime, not copied from a previous report. Use a freshness
window appropriate to the product; a monitor and a release generally require
different windows.

The gate is deliberately small. It does not execute tests, inspect production,
or decide that an external side effect is safe. It only prevents a caller from
turning incomplete or stale evidence into a successful completion claim.
