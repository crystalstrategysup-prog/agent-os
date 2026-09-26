# Stage F17 — current handoff discovery and Mac routing repair

Task: `task-c6506419f28d4cc2`

Status: PUBLIC RELEASE AND MAC READ-BACK PASS.

## Objective and verified problem

Owner requested investigation and repair of a chat that opened legacy global
handoffs as current public AgentOS material. The version observation in that
chat predates v0.5.3 and was correct then; opening an existing archive did not
prove a current handoff. Selected local instruction fragments still point to an
old global runtime and moved handoff directories. Public handoff guidance lacks
an explicit discovery order and distinction between lifecycle results and a
current handoff. Current installed core is 0.5.2; public stable is 0.5.3.

## Scope and architecture

Publish HANDOFF_DISCOVERY.md and link it from the maintained handoff skill and
managed bootstrap. Define core resources, project current handoff, task results,
private cross-project index and legacy archives as distinct surfaces. Add a
current AgentOS project handoff. Keep user paths external and no automatic
provider or directory scanner. Version the reviewed patch as 0.5.4.

Back up and repair only conflicting Mac global instruction fragments and the
private handoff index. Keep archived files intact. Verify the selected owner
and macbook-pro profile hashes and host binding before dependent writes. Plan
and apply a hash-verified offline update against exact installed 0.5.2, then
integrate managed AGENTS/skills without auth/model/hook/security changes.
External release targets canonical public crystalstrategysup-prog/agent-os;
no website, PyPI, private fleet, Telegram, service or database effects.

## Acceptance and checks

- Current lookup uses the explicit selected project/user index; existence or
  timestamps alone do not convert an archive/result into a current handoff.
- Guide, managed bootstrap pointer and template are included in the wheel.
- Public export, resource parity, registered full-tests and install-fixture pass.
- Versioned source/tag/release/assets read back, followed by exact Mac pointer,
  version, doctor and managed integration evidence; no native hooks.
- A fresh isolated installed-process read/project smoke verifies the available
  workflow. Do not claim a newly created Codex chat was tested without proof.

## Rollback and privacy

Keep previous public release and installed 0.5.2 intact. Mac repairs have exact
preimage backups and refuse concurrent edits. Core update preserves the external
user tree; index/integration backups are separately scoped overlay changes.
No private handoff contents, paths or host identifiers enter public artifacts.
No deletion or bulk migration of old handoffs. Revert only reviewed source and
exact changed host fragments; never restore hook trust or unrelated settings.

## Local verification and review

278 tests passed; full-tests receipt `ea2af405c0a448e48576d3cf1ee06c31`.
Ruff lint, clean public export, source/resource parity and diff checks passed.
No blocking findings: the bootstrap only adds a packaged guide pointer, reads
remain task-free, and no global scanning, credentials or private paths are
introduced. Existing integration tests verify guide resolution and preserve
unrelated user policy/security controls. The install fixture requires the guide
in installed resources and tests rollback and user-data preservation.

Wheel `crystal_agent_os-0.5.4-py3-none-any.whl`: 171752 bytes, SHA-256
`c2ae483ea89087e57369f92c41d56a24b3bc88adaa4f3cd813a93325a6028537`.
All 111 packaged agent_os files match source. Darwin arm64 Python 3.14.6 offline
fixture passed; receipt `0ef0c1e3243d4aad9b459acab0b6f235`.
Source inventory `7f6ffd00c379d54403909f7d038af343dc4cee8b7943fff2e2b73b249fb2f928`.

Three exact Mac instruction files were backed up before scoped fragment edits;
a private pointer index was created. Legacy packets and unrelated instructions
were preserved. The current selected profile inventory has no binding mismatch.
Mac core activation still requires its separate plan/apply/read-back receipt.

## Public delivery and target verification

Source `2aacd7893f3b643223e194b13ab5689b62e9ae33` was pushed to canonical
main and annotated `v0.5.4` (tag object
`6b40cb859703aa3fe3e4e5d469016d0fc526abf2`). The stable Latest
[release](https://github.com/crystalstrategysup-prog/agent-os/releases/tag/v0.5.4)
was published by the canonical owner account at `2026-09-26T03:08:46Z`, release
ID `397054110`. Downloaded source ZIP is 353741 bytes, SHA-256
`dd64a44d92fbcb66aa638cf9c8d16aff231c0a1f64a9989fbec938ca75476cdc`.
The downloaded wheel matches the hash above. Both match reviewed local bytes.

The Mac installer planned and applied against exact prior release
`0.5.2-44fd238dfbc0`. Current pointer and CLI read back
`0.5.4-c2ae483ea890` / `0.5.4`; previous 0.5.2 remains intact.
The 71-file external user tree had identical count and SHA-256
`e238d891ef3facae87566b4e0aece982ad87695b99ad5724ea705c4df16d1ef6`
before and after core activation. Separately authorized pointer-index edits
preceded that measurement; managed integration backups and advisory refresh
are separate scoped overlay changes after it.

Managed Codex integration reported no conflicts, auth/model/trust changes or
hook writes. Read-back verifies the new guide path, unchanged owner-adapter
bytes outside the scoped edit, expected instruction hashes, maintained handoff
skill and current private/project pointers. hooks.json remains absent.
The active instruction context now names the 0.5.4 guide. Doctor is PASS.
The first advisory refresh hit a transient URLError; bounded retry succeeded
with CURRENT, installed/latest 0.5.4, checked `2026-09-26T03:12:46Z`.

A new installed interpreter process from an isolated working directory verified
resource reads without creating a project task, then initialize/entry/READY/
check/close in a temporary synthetic project. This is installed-process proof,
not a newly created Codex chat or a guarantee of agent behavior. The inspected
chat was read only; no message was sent. Legacy handoffs remain untouched.
