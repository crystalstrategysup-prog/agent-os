# Foundation architecture

## Context and boundaries

An ordinary authorized read leads directly to an answer. A real project change
follows inspection, documentation, entry and READY, implementation, checks, then
closeout or checkpoint. External effects require their own target authority.
MCP provides bounded read-only discovery and planning, not a shell. Native hooks
are excluded. Project governance needs no network; optional Telegram, update,
and speech features are not prerequisites for this route.

| Component | Responsibility | Boundary |
| --- | --- | --- |
| `workflow` | Optional stateless route from declared kind and effects | Does not interpret natural language, execute work, or grant capability |
| `project` / `doc_catalog` | Applicable docs, answer reuse, readiness, checks, current closeout | Does not intercept every tool or prove live deployment |
| `turns` | Explicit project entry and terminal transitions | Does not receive native prompt events or reset a task for an ordinary question |
| Observation store | Optional separate audit receipts | Is not a prerequisite for reading or project entry |
| Retired hooks | No-op compatibility for old callback entrypoints | Do not read input/config, write state, deny, allow, or complete a task |
| `integration` | Managed AGENTS and nine namespaced skills with conflict checks and backup | Does not edit hooks, client config, auth, model, or trust settings |
| `safeio` | Path containment, bounded JSON/stdin, locks, atomic writes | Does not defend against a malicious process with the same user ID |
| Overlay / config / profile adapter | Separate user data and optional verified profiles | Grants no authority and does not replace runtime proof |
| `dispatch_gate` | One-time legacy dispatch binding | Is not a network sandbox |
| `mcp_server` | Six bounded planning and status tools | Exposes no arbitrary file, shell, or write tool |
| `tools/install` | Offline wheel, venv, probe, atomic current switch, rollback | Makes no service or production change |
| Connection scenarios | Versioned public goals, flows, and checks | Do not run a private provider, read secrets, or prove live readiness |

## Architecture decisions

**ADR-001–007.** The public core is separate from private runtime. Source and
wheel comparison does not prove publication or installation. Core, user overlay,
and project docs have distinct physical roots; config v5 and overlay v1 are
validated independently. Task state uses JSON and Markdown, local locks, and one
active task, not a distributed database. Releases are immutable and `current`
switches only after a probe. Profiles are optional and selected by exact IDs,
hashes, host bindings, and conflict decisions. Schemas, hashes, and checks prove
structure and traceability; a semantic reviewer and target executor must still
judge meaning and authority. Private executable providers require separate
contracts and must not enter the public package disguised as settings.

**ADR-008 (F09).** Separate direct reading from the documentation-first change
process. Remove global callback interception instead of expanding a shell/tool
allowlist. Retired entrypoints return compatible no-ops and gain no new
registrations. Explicit turn helpers live in `turns.py`; observations are stored
separately. Bounded stdin supports bootstrap without weakening path checks.
Same-scope answer reuse never inherits authority. Project gates and target
controls remain distinct. AgentOS does not claim to be a global runtime
interceptor: Markdown and CLI do not replace a client sandbox, ACL, or scoped
connector. Such isolation needs a separate host-specific stage, not hooks.

**ADR-009 (F10).** Root and inherited `AGENTS.md` files are short routing maps:
scope, universal limits, and topical links. Full incident history, long runtime
snapshots, and unrelated product rules belong elsewhere. Load only relevant
material and verify dated status against current source or runtime. Public core
defines this method; owner/host facts stay in the overlay and product details in
the project. A length target is editorial guidance, not a blocking gate.

**ADR-010 (F11).** Multi-file integration and project entry use a local lock and
a log of expected hashes and prior bytes. Normal failure rolls back; an
interrupted operation is recovered before a new attempt. Concurrent edits block
recovery rather than being overwritten. Project checks use a bounded POSIX
process group and pass only after all children exit and source is read back. The
installer compares installed package files and entrypoints with the verified
wheel before import and pointer switch. These controls provide local integrity,
not protection from a malicious same-user process.

**ADR-011 (F12).** A connection scenario is typed public knowledge, not an
executable module or a user's integration instance. The index lists available
cards and honest implementation status. Each card records goal, flows, user and
agent actions, expected proof, and official sources. CLI only reads packaged
resources. Personal settings, session material, secrets, and executable
providers stay in the external overlay or private component. A card does not
establish adapter availability or successful connection. See
`docs/SETUP_SCENARIOS.md`.

**ADR-012 (F13).** English is the language of public documentation, CLI copy,
packaged resources, templates, skills, and scenario content. Machine identifiers,
schema keys, commands, and historical facts remain stable. A user's language
preference belongs in the external overlay. Source docs and their packaged
copies must match. See `docs/LOCALIZATION.md`.

**ADR-013 (F14).** Work continuity is a public guide and reusable passport
template, not a connection scenario or an automatic backup service. The guide
defines a small index of projects, current verified handoffs, source and data
pointers, uncertainty and restore checks. A filled passport is user-owned
knowledge in the external overlay; source repositories, databases, media and
credentials remain in their own systems. The public package carries no user's
paths or snapshots. A local file in a sync folder does not prove remote
availability or restore. See `docs/WORK_CONTINUITY.md`.

**ADR-014 (F15).** The public SSH/VNC card is a connection scenario under
ADR-011. It first reuses an exact verified user route, then selects direct SSH,
a trusted jump host or a loopback-bound reverse route. VNC is optional and
forwarded through authenticated SSH. The public card records proof layers and
maintenance triggers but does not initiate connections, keep credentials, scan
hosts or install a private Remote Access Helper. Per-device routes and current
authorization remain external to the public core. See `docs/SETUP_SCENARIOS.md`.

**ADR-015 (F15B).** A separate opt-in diagnostic may verify one existing SSH
alias and optional VNC transport. It plans without network access by default;
`--apply` performs bounded authenticated SSH command execution and a VNC stdio
channel with OpenSSH `-W`, without a local listener. It returns layered JSON
proof and closes the channel on supported normal, error and interrupt paths.
The diagnostic accepts no raw host address, username, key path or
arbitrary remote command, and never handles VNC credentials or infers a desktop
frame from an RFB greeting. The setup card remains `guide_only`. The selected
alias and host-specific results stay outside the public package. See
`docs/agentos/STAGE-F15B.md` and `docs/SETUP_SCENARIOS.md`.
