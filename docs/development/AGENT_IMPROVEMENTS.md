# Improving AgentOS and publishing changes

Agents using AgentOS may propose verified improvements to AgentOS and its dependencies within their current task authority and existing repository access. A complete blocker is not required, and repeated permission for each in-scope pull request is not required.

## Reuse the owner's instruction, without another approval gate

Already assigned ordinary AgentOS engineering includes diagnosing and designing
the necessary owning source/dependency repair, preparing its bounded candidate
and synthetic checks, and reviewing it through the existing source writer and
repository access. Do not ask the owner or the AgentOS maintainer to approve that
same work again merely because a new file, module, turn or blocker is involved.
The maintainer is an executor and technical reviewer, not a second owner approver.

Revalidate the existing instruction's actual scope, target, validity and
revocation. Full answers/entry for changed technical scope remain required;
they record the work and do not imply a new human-approval round when the owner
has already authorized it. Ask only for a genuinely missing material decision or
a protected effect outside that authorization, naming its exact current source.

Distinguish an unavailable supported target method from missing source authority.
Prepare the allowed source repair instead of seeking the same permission again.
Its patch, tests and publication never admit held product files, grant target
installation/runtime/production/data/authentication permissions, override a
protective refusal, authorize another message, or permit UNKNOWN replay. Those
existing controls and separately required target receipts retain their force.

## Grounds for a pull request

| Category | Evidence appropriate to the change |
| --- | --- |
| Bug fix | Reproduce incorrect behavior and demonstrate the corrected scenario with relevant regressions. |
| Performance | Compare equivalent workloads for latency, throughput or resources while retaining required behavior. |
| Quality | Demonstrate improved correctness, completeness, reliability, diagnostics or usability. |
| Loop prevention | Show useful progress or a precise owned checkpoint without duplicate effects or UNKNOWN replay. |
| Bottleneck removal | Identify the limiting component and demonstrate that the constraint is removed without hiding it elsewhere. |

If an AgentOS limitation prevents the authorized task, diagnose and patch the owning module or dependency instead of reporting the same blocker repeatedly. Prefer an existing supported correction when sufficient. Preserve contracts, current authority, data protection, one writer and target controls. Removing a protective check or inventing permission is not a valid fix.

## Required delivery

1. Preserve the original goal and a minimal reproduction or baseline.
2. Follow prototype -> acceptance -> integration -> regression in proportion to risk. Integrated checks call the canonical module, not a prototype copy.
3. Pin dependency changes and document compatibility and rollback.
4. Review the actual diff and public-data boundary. Never include credentials, private overlays, transcripts or operational host data.
5. Commit and push the verified change to an authorized branch of the canonical repository, then create or update its pull request. Do not leave accepted improvements only in a local installation or archive.
6. Include the category, problem, resulting behavior, validation and remaining limitations. Read back the remote commit and PR base/head; retain URL and SHA.
7. Follow repository review, branch protection, version and release policies. A PR is not a merge; source publication, package release, installation and semantic acceptance are separate.

Canonical repository: https://github.com/crystalstrategysup-prog/agent-os . Public core changes and shipped guidance are version-controlled here. Release artifacts identify source commit and checksums. Future package changes use an appropriate version before publication. Installation does not prove an already-running client loaded new instructions.

If publication fails, preserve the prepared commit and exact evidence, continue independent authorized work, and report delivery as incomplete. Do not change credentials or permissions to bypass a refusal. Opening an authorized PR does not grant permission to merge, deploy or replay unknown operations.
