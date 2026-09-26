# Current AgentOS public project handoff

Status: CURRENT; F17 completed on 2026-09-26.

## Identity and primary documents

Canonical source: https://github.com/crystalstrategysup-prog/agent-os.
Start at AGENTS.md, README.md, docs/agentos/DOSSIER.md, ROADMAP.md and STAGE-F17.md.
This is the framework development project's handoff, not a global index of
user projects. The installed runtime is separate from this checkout.

## Last verified result

v0.5.4 was published from 2aacd7893f3b643223e194b13ab5689b62e9ae33;
source/wheel downloads matched reviewed hashes. Managed owner-Mac core reads
back 0.5.4; installed-process workflow smoke passed. See STAGE-F17.md.
F15B verified authenticated SSH and RFB transport on one authorized macOS host.
F15C deferred Screen Sharing/viewer login/frame; do not revive that requirement.

## Current work and limits

F17 repaired handoff lookup/routing and verified the public 0.5.4 release and
managed Mac update. Other devices and a fresh Codex chat were not tested.
F16 private scenario discovery remains planned, not implemented.
No hooks, private Helper/provider migrations, website or PyPI publication.
Per-user paths, account/host facts and service authority stay external.

## Next safe step and rollback

Read the current F17 evidence and exact source/runtime state before resuming.
Do not infer task completion from an old result report. Preserve previous
releases and the external user overlay; use verified managed rollback only.
