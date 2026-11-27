# Improving AgentOS and publishing changes

Agents using AgentOS may propose verified improvements to AgentOS and its dependencies within their current task authority and existing repository access. A complete blocker is not required, and repeated permission for each in-scope pull request is not required.

## Grounds for a pull request

| Category | Evidence appropriate to the change |
| --- | --- |
| Feature or policy | State the baseline or intended stage result and check the declared criteria in proportion to risk. |
| Bug fix | Reproduce incorrect behavior and demonstrate the corrected scenario with relevant regressions. |
| Performance | Compare equivalent workloads for latency, throughput or resources while retaining required behavior. |
| Quality | Demonstrate improved correctness, completeness, reliability, diagnostics or usability. |
| Loop prevention | Show useful progress or a precise owned checkpoint without duplicate effects or UNKNOWN replay. |
| Bottleneck removal | Identify the limiting component and demonstrate that the constraint is removed without hiding it elsewhere. |

If an AgentOS limitation prevents the authorized task, diagnose and patch the owning module or dependency instead of reporting the same blocker repeatedly. Prefer an existing supported correction when sufficient. Preserve contracts, current authority, data protection, one writer and target controls. Removing a protective check or inventing permission is not a valid fix.

## Required delivery

1. Preserve the original goal and a baseline or declared stage criteria. Ordinary feature or policy work needs no invented failure or minimal reproduction; use the [project development method](../PROCESS.md#project-development). For a malfunction, retain its relevant reproduction when available and select causal debugging when needed.
2. Use prototype -> acceptance -> integration -> regression as applicable and in proportion to risk. A scaffold or explicit stub can satisfy its declared stage. Integrated checks call the canonical module, not a prototype copy. Stop when the stage criteria and required checks are satisfied; broaden verification for a concrete remaining risk or the planned acceptance stage.
3. Pin dependency changes and document compatibility and rollback.
4. Review the actual diff and public-data boundary. Never include credentials, private overlays, transcripts or operational host data.
5. Commit and push the verified change to an authorized branch of the canonical repository, then create or update its pull request. Do not leave accepted improvements only in a local installation or archive.
6. Include the category, problem, resulting behavior, validation and remaining limitations. Read back the remote commit and PR base/head; retain URL and SHA.
7. Follow repository review, branch protection, version and release policies. A PR is not a merge; source publication, package release, installation and semantic acceptance are separate.

Canonical repository: https://github.com/crystalstrategysup-prog/agent-os . Public core changes and shipped guidance are version-controlled here. Release artifacts identify source commit and checksums. Future package changes use an appropriate version before publication. Installation does not prove an already-running client loaded new instructions.

If publication fails, preserve the prepared commit and exact evidence, continue independent authorized work, and report delivery as incomplete. Do not change credentials or permissions to bypass a refusal. Opening an authorized PR does not grant permission to merge, deploy or replay unknown operations.

## Protected work laws

The Solution integrity section of PROCESS and WORK_ENVIRONMENT are an
owner-approved frozen revision. Agents must not edit, shorten, override or
weaken them, their retained manifest or the validating guard for a task. A
general request to improve a project or AgentOS is not permission to revise
these texts. Record a proposed correction separately with its observed basis.
Only an explicit owner decision about this revision permits a successor; retain
the previous revision and review the exact text and pin change independently.

Current facts, project plans, results and installed-version records remain
editable through their normal owners. Keep these facts outside frozen laws.
The release guard detects changed bytes while its anchor remains trusted; it
does not prove authorization, semantic truth or agent behavior. The ordinary
receipt and review path must still verify the actual result. Do not change a
test oracle, remove a counterexample or redefine acceptance to obtain a PASS.
