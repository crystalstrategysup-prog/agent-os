# Stage F15C — defer desktop viewer integration

Task: `task-79f1b9047c064ef3`

Status: scoped amendment implemented; local verification and candidate delivery
are recorded in the registered task closeout.

## Objective and authority

On 2026-09-26 the owner requested removing Screen Sharing for now.
Narrow the active SSH/VNC scenario to authenticated SSH and optional RFB
transport. The F15B diagnostic and its one-host transport evidence remain valid.
Viewer authentication, current desktop frames and Screen Sharing integration
are deferred to a separately authorized and verified stage.

## Scope and contracts

Update the public card/index, field guide and packaged copies, changelog,
dossier, roadmap and F15B scope note. Keep the diagnostic, JSON keys and false
VNC-authentication/frame fields unchanged. Do not alter hosts, credentials,
Remote Access Helper or the installed foundation. No tag, release or managed
installation is part of this amendment. Direct candidate-branch Git delivery
uses local checks and diff review; GitHub Actions remains prohibited.

## Acceptance and checks

- Active scenario steps stop at SSH/RFB transport and do not launch or request
  a desktop viewer. Deferred desktop support is explicit.
- Public docs and packaged copies match; the catalog remains valid and English.
- Existing probe tests still enforce that transport never proves login/frame.
- Run registered `docs-check` and inspect the diff before candidate delivery.

## Rollback and remaining work

Revert this bounded amendment if needed. Stable release/installation remains
0.5.2. Candidate 0.5.3 needs a rebuilt wheel and separate publication/read-back;
prior wheel bytes predate this amendment. Desktop login/frame remains untested
and is outside current acceptance, rather than a required owner action.

## Review result

No blocking findings in the scoped diff. Active steps contain no viewer-login
request, and the unchanged diagnostic keeps VNC authentication/frame false.
Source/resource parity passes. Stable installation remains 0.5.2; the earlier
0.5.3 wheel is stale relative to this amendment and must not be delivered.
