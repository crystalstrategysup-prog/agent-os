# Work continuity passport

Owner: [name or role]
Updated: [ISO date and timezone]
Maintainer: [person or role]
Passport destination: [user-controlled location]
Independent copy: [location, last verified date, or unknown]

## Purpose and boundary

[What work must be resumable, and what device or workspace could be lost?]
This file is an index and handoff. Code, databases, media, credentials and
private records remain in their own systems.

## Project index

| Project | Owner goal | Canonical source | Last verified result and date | Status | Next safe step |
| --- | --- | --- | --- | --- | --- |
| [project] | [goal] | [repository or primary document] | [evidence and date] | unknown | [verification step] |

Status is `verified`, `documented`, `unknown` or `stale`. A path or chat title
alone is not proof that the source, runtime or data is available.

## Current handoffs

### [Project name]

- Owner request and intended outcome: [summary]
- Canonical source and primary documents: [references]
- Accepted decisions: [decision, source and date]
- Last checked source or runtime: [identity, evidence, date and status]
- Open blocker or uncertainty: [fact or unknown]
- Concurrent work: [task or branch reference, status and check date]
- Next safe action: [first bounded verification or implementation step]

## Data and recovery map

| Data class | Actual holder | Local-only exception | Independent copy or live read-back | Sample restore | Status and date |
| --- | --- | --- | --- | --- | --- |
| [code/database/media/settings] | [system or unknown] | [item or none verified] | [receipt or unknown] | [test or not run] | unknown |

List credential **types and recovery owner** only. Never store passwords,
tokens, session material, private keys or raw personal data here.

## Passport-copy proof

- Exact source file and SHA-256: [path/reference and digest]
- Destination file and SHA-256: [path/reference and digest]
- Opened from destination on: [date or not verified]
- Remote or separate-device availability: [evidence or unknown]
- Recovery sample: [what was restored, where, when, result or not run]

Matching local hashes do not prove a cloud copy or recoverability. Do not
declare device clearance from this passport alone.

## Maintenance log and outstanding checks

| Date | Trigger | Evidence checked | Change | Reviewer | Next review |
| --- | --- | --- | --- | --- | --- |
| [date] | [handoff/release/move/recovery] | [source] | [summary] | [role] | [date/trigger] |

Outstanding checks: [unknowns, owner decisions, missing backups or restore tests]
