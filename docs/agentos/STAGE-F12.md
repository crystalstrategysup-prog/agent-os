# Stage F12 — connection scenario catalog

Task: `task-3b59bda36a0547a0`

Status: public source candidate; local source acceptance completed.

## Objective

Add indexed connection scenarios, a common card format, and read-only
discovery to public AgentOS. The owner requested this on 2026-09-26. The earlier
Telegram onboarding list in `src/agent_os/onboarding.py` had no verifiable
alternate flows or evidence level.

## Scope

Changes cover public `docs/`, `schemas/`, `src/agent_os/`, `tests/`, and
`README.md`. Format, documentation, and index precede a small loader and CLI.
A working private MTProto route informed the generic pattern but its code,
secrets, host data, live Telegram state, and the user overlay were excluded.
Publishing or activating a release was a separate operation. See
`docs/ARCHITECTURE.md`, `docs/FOUNDATION_OVERLAY.md`, and
`docs/SETUP_SCENARIOS.md`.

## Acceptance

Index and cards validate against the packaged schemas. CLI reads only
registered cards, returns the truthful `guide_only` status, and needs neither
configuration nor network access. MTProto and Business examples contain no
private identifiers and make no claim of a ready adapter. Focused checks cover
`tests/test_setup_scenarios.py` and `tests/test_cli.py`; final diff review is
required.

## Rollback and next stage

Before publication, revert the branch change while preserving work separately.
After a direct source push, use a reverse commit or new versioned patch. The
installed public `v0.5.0` is unaffected by this branch. No live listener or
credentials were changed. An interactive wizard and private adapter need their
own implementation and acceptance.
