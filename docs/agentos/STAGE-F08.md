# F08 — внешний протокол профилей и Mac-first интервью

Task: `task-b7f82196dc0e45f1`. Status: PUBLIC_RELEASE_PASS, MAC_TARGET_BLOCKED. Baseline: immutable public `v0.5.0-beta.3` at `f6968c249f8bff1ce571cf92bbd960ba7cc2c1b2`; source worktree starts at `7203fbb86a316ce9ab9813d3ed7cd699fe35ef62`.

## Цель и причина

Public AgentOS currently has one selected user home (`AGENTOS_USER_HOME` / `--home`) with an overlay catalog and bounded knowledge index. It has no protocol for selecting zero, one or several independently removable profiles, no inventory of overlaps, and no verified owner/host context in task interviews. The owner requires immutable public releases plus an external adapter for user-owned profiles. Private Mac knowledge must remain outside public Git.

## Область изменений

Add a versioned, host-neutral profile protocol in the canonical public repository: profile schema, adapter and CLI, selected context for project intake/hook messages, a small interview skill, targeted tests and synchronized docs. The existing single-home overlay remains a supported storage root and compatibility path. External private Mac profile bytes stay in the owner workspace until separately validated and approved. No business host, secret store, private AgentOS runtime or existing beta tag is changed by the public patch.

## Contract and state transitions

1. A public core runs with **no selected profile**. An absent or deleted user profile root cannot corrupt the package or imply external authority; it yields explicit `NONE` or `STALE_SELECTION` context and requires a fresh choice for profile-dependent features.
2. User can select **one exact profile** or **several exact profiles in owner-chosen order**. Selection is stored outside the package and hash-binds the exact profile metadata used during inventory. No broad discovery of home or other hosts.
3. For several profiles, first read only bounded metadata and declared non-secret facts/preferences from exact profile IDs. Inventory duplicate keys and incompatible host bindings. Differing values block activation until the owner supplies an explicit per-key resolution. An ordered list alone is not silent conflict resolution.
4. Re-read selected profile hashes before supplying context. Missing, malformed, changed, symlinked or unsupported profiles are not loaded. Report the reason without returning raw private bodies or credential values. A stale selection never creates privileges.
5. Context exposed to the project interview contains selected facts, provenance, observation date/status, unresolved questions and conflict decisions. Dated documents remain `DOCUMENTED` until live or owner confirmation. Agent asks only unresolved material questions.
6. User profile settings and extensions cannot grant shell, network, deployment, account or host authority. Existing public invariants and external technical gates remain effective. Secret bytes are never profile facts or interview output.
7. A public protocol change requires a new versioned release. Profile content changes or deletion do not mutate the installed release. Keep all previous tags/assets immutable.

## Affected surfaces

`src/agent_os/profile_adapter.py`, `foundation_cli.py`, `config.py`, `project.py`, `hooks.py`, packaged schema/skill, `tests/test_profiles.py`, and the public contracts, onboarding, installation, security, release and project-stage documents. `README.md` and package version surfaces change only as required by the new release.

## Acceptance and checks

- Zero/one/many selection, exact ordering, conflict inventory, explicit resolution, missing/deleted profile handling and hash drift have deterministic tests.
- Symlink/traversal, oversized/unlisted data, secret-like values and attempts to encode authority in profile facts fail closed. A profile cannot write into the core.
- Existing beta.3 overlay import, migration, project lifecycle, hooks and installer tests still pass. Public-tree validator finds no private paths/content or generated state.
- Full suite and Ruff pass locally; wheel is built and installed in a disposable home; existing release remains a rollback anchor. Publish the next beta only with exact source/tag/asset read-back.
- Mac side-by-side install and native hook proof are separately checked against the actual host gate. A disposable fixture cannot establish that live target passed.

## Rollback and limits

Before publication, revert the new source commit. After publication, retain the prior immutable beta.3 and choose its supported package version through the documented installer; external profiles are left byte-for-byte untouched. A profile protocol migration must never rewrite private data implicitly. Windows and multi-host adoption require their own target proofs. The first extracted Mac candidate remains draft until the owner reviews ambiguous instructions and the adapter validates its exact external bytes.

## Local result and evidence

`pytest -q --disable-warnings` passed 179 tests on the Mac fixture; Ruff passed. The new
profile tests cover zero/one/all selection, explicit per-key conflict choice, binding
mismatch, changed/deleted selection, new profile under `all`, broken storage under
`none`, secret-like values, malformed types, CLI dispatch, interview prefill and
packaged schema. A wheel was built as `crystal_agent_os-0.5.0b4-py3-none-any.whl`
with SHA-256 `98eab5889e272c8564e81aac5b45ee34c1516f075f72bf74197c245acdc9d434`.
A clean venv installed that wheel without index/dependencies; `agentos --version`
returned `0.5.0-beta.4`, zero-profile inventory returned PASS, and resource listing
contained the schema and skill. These are local fixture proofs, not live Mac
activation or native hook proof. The export privacy check and exact source/release
read-back remain release gates.

## Publication and target read-back

The public `main` branch and annotated `v0.5.0-beta.4` tag resolve to source commit
`f69a74620a614c2f55c17ceacfe4a9c18dfc0455`. The [GitHub pre-release](https://github.com/crystalstrategysup-prog/agent-os/releases/tag/v0.5.0-beta.4)
shows that exact commit and the wheel asset. A separate download of the published
wheel matched SHA-256 `98eab5889e272c8564e81aac5b45ee34c1516f075f72bf74197c245acdc9d434`.
All four registered F08 checks (`profiles`, `suite`, `lint`, `tree`) passed and
`project assess` returned PASS at source snapshot
`0b767e7e94bee4a76e92a92ea6e0843464540740fe0cb104dc0b578c77b5cd8f`.
No blocking code-review findings remained. Residual limits: same-UID filesystem
races are outside the adapter's guarantee; secret-like detection is heuristic;
actual native hook trust, Windows and live Mac installation require target proof.

The intended live Mac installation remains blocked by an external host gate.
No managed install in the owner runtime or global integration change occurred.
The disposable wheel venv is local test evidence only.
The Mac profile candidate remains an external draft awaiting owner review of
uncertain personal and host choices; neither it nor private host instructions
were put in the public release. Beta.3 remains the release rollback anchor.
