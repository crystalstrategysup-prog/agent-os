# Current AgentOS public project handoff

Status: CURRENT SOURCE WORK; 2026-09-26.

## Identity and primary documents

Canonical source: https://github.com/crystalstrategysup-prog/agent-os.
Start at AGENTS.md, README.md, docs/agentos/DOSSIER.md, ROADMAP.md and STAGE-F17.md.
This is the framework development project's handoff, not a global index of
user projects. The installed runtime is separate from this checkout.

## Last verified result

v0.5.3 was published from aaf33929db6e17b57a02cc750530bc53e0c1ebc9;
source/wheel downloads matched reviewed hashes. See STAGE-F15D.md.
F15B verified authenticated SSH and RFB transport on one authorized macOS host.
F15C deferred Screen Sharing/viewer login/frame; do not revive that requirement.

## Current work and limits

F17 repairs handoff lookup/routing and prepares a reviewed 0.5.4 patch and
managed Mac update. Publication and installed read-back are recorded in STAGE-F17.
F16 private scenario discovery remains planned, not implemented.
No hooks, private Helper/provider migrations, website or PyPI publication.
Per-user paths, account/host facts and service authority stay external.

## Next safe step and rollback

Read the current F17 evidence and exact source/runtime state before resuming.
Do not infer task completion from an old result report. Preserve previous
releases and the external user overlay; use verified managed rollback only.
