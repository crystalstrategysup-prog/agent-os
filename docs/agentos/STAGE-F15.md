# Stage F15 — standard SSH and VNC tunnel scenario

Task: `task-5792c3cf0c1846ad`

Status: local 0.5.2 source candidate passed; publication and live Mac update pending.

## Objective

Give a person and an AgentOS agent one fast, reusable path for connecting to an
authorized remote device by SSH and, when requested, VNC carried through SSH.
Reuse a verified existing route before asking for setup. Select the shortest
safe route that fits the network: direct SSH, a known jump host, or a trusted
reverse tunnel when inbound access is unavailable. Keep Remote Access Helper,
CrystalStrategy infrastructure and owner device data outside the public card.

## Architecture and scope

Add one English `guide_only` connection card to the existing indexed setup
catalog. The card is the wizard's knowledge route, not an SSH/VNC adapter. Its
first flow is a short known-route check; alternate flows cover direct SSH,
jump/reverse forwarding and optional VNC over a loopback-only SSH forward. Each
step names its actor and a verifiable result. Separate device identity,
transport liveness, authenticated SSH and authenticated desktop proof. A port
banner alone never proves login. Record what is known, which route was tested,
when, and what invalidates it in the user's external overlay, not public source.

The public setup protocol and documentation index will name this scenario and
its maintenance triggers. Update catalog tests so they accept reviewed primary
sources beyond Telegram while checking exact index/card parity, packaging and
read-only CLI behavior. Version and release metadata move together to 0.5.2.
Publish only after clean local checks and asset read-back. Plan and verify the
managed Mac update separately against exact installed 0.5.1. Native hooks stay
disabled.

No service-host Helper/API/runtime modification, client install, credential
issue, access grant, live remote login, VNC session, firewall change, website
deployment, or private profile copy is in this stage. Actual connections keep
their own owner, device and host authority checks. The existing Remote Access
Helper was read only as a reference for proof-layer and failure lessons.

The owner's follow-up idea is **private scenarios** in the user overlay. Design
that as a separate stage after the public SSH/VNC route is stable: user-owned
cards with explicit private IDs, no shadowing of public cards, local-only
discovery, provenance and review dates, and a distinct authorization boundary
for any executable adapter. Do not add private card loading or import behavior
to this release.

## Source basis and risks

OpenSSH documents direct, jump and reverse forwarding and server-side listen
restrictions. Microsoft documents Windows OpenSSH Server setup; Apple documents
Remote Login and Screen Sharing. The private reference showed why a fresh
heartbeat, an actual listener and authenticated access must be checked
separately. The generic route cannot promise that a device, broker, display,
account or provider is available. A reverse listener exposed beyond loopback,
an unverified host key, or raw VNC exposed to the network is unacceptable.

## Acceptance and checks

- Public card is short on the common path, English, indexed, schema-valid,
  packaged and discoverable with `agentos setup list/show` without network or
  user configuration.
- The route choice and proof levels are explicit. SSH-only devices never need
  desktop proof; VNC is optional and uses an authenticated, loopback-bound SSH
  path. Authorization and secrets remain outside the card.
- Official sources and a review date are recorded, along with triggers for
  rechecking platform guidance, tunnel behavior and stale user routes.
- Local catalog, full test, Ruff, public export, wheel/package and offline
  install fixture checks pass; reviewed assets match the published release.
- The managed Mac pointer and CLI read back 0.5.2, with the external overlay
  unchanged by the core installer and AgentOS hooks still disabled.

## Rollback

Keep v0.5.1 and its managed installation immutable. Correct a published defect
in a later version. If activation fails after switching, plan exact installer
rollback to verified 0.5.1 without restoring hooks or overwriting the overlay.

## Local source evidence

On 2026-09-26, the public card and index passed schema/CLI and English-surface
checks. The full Python suite passed 267 tests, Ruff passed, and a clean export
passed `tools/verify_public.py`. All seven listed primary-source URLs returned
HTTP 200. The clean-export wheel
`crystal_agent_os-0.5.2-py3-none-any.whl` is 160816 bytes, SHA-256
`44fd238dfbc0452e8bb4dad880376572d210c10e82d2a2a822fc69a9df3e443e`;
its 107 `agent_os` files match the current source bytes exactly. A Darwin
arm64 Python 3.14.6 offline fixture passed install, update, rollback,
reactivation, package integrity and unchanged synthetic user-tree checks.
It is not live device access or target Mac activation proof. Publication and
installation require their own read-back below.
