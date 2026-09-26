# Stage F13 — English public edition

Task: `task-6f47dda325924fe8`

Status: source candidate; local checks passed. No release or installation performed.

## Objective

Replace Russian-language public source text with accurate English so the public
distribution is usable internationally. The owner explicitly chose full
replacement on 2026-09-26. Baseline: public source branch containing F12 setup
scenarios; current installed 0.5.0 is a separate immutable release.

## Scope and architecture

Translate current and historical public docs, their packaged copies, setup
scenario cards, catalog text, templates, skills and generated CLI/user-facing
strings. Preserve machine-readable identifiers, contracts, source references and
dated meaning. English is the canonical public source language; user and host
preferences stay in the external overlay. No live runtime, credentials, release
activation or Telegram integration changes are included. See
`docs/ARCHITECTURE.md`, `docs/CONTRACTS.md` and `docs/LOCALIZATION.md`.

## Acceptance

The tracked public tree has no Cyrillic copy; source and packaged docs match;
CLI/template behavior and IDs remain compatible; local tests and wheel resource
inspection pass. Review the diff for policy drift and inaccurate translation.
Checks: `tests/test_english_public.py` and the full Python test suite.

## Rollback

Revert the translation commit on the source branch. Existing installed releases
and external user data are unchanged. A future localization layer, if requested,
needs its own contract and tests.

## Local evidence

On 2026-09-26, the source and packaged documents matched; the complete local
suite passed (265 tests), Ruff passed, and `tools/verify_public.py` passed on a
clean export. A wheel built from that clean export contained the English policy,
documentation index, scenarios and skills, and no Cyrillic text. The old
`README.ru.md` appeared only in a stale local `build/lib` directory, not in the
clean source or wheel. The final review must still bind this evidence to the
registered task and record the delivered commit.
