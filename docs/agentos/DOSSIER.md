# AgentOS engineering dossier

## Purpose
AgentOS supplies explicit, reviewable project workflows and portable engineering tools. Atlas connects existing project documents, work, owners, contracts and evidence. The ordinary workflow must let a new worker find the exact current source and the next justified action without replaying a previous conversation.

## Current state
The verified installed source baseline is commit b157dbfe557dc6c43fb45ff7be7dc36512ac110d, version 0.8.0rc2041+scoped2. Canonical main at 159037d680124cd0906a23c4310e99cfe5c9b5d7 adds recovery v3 on a sibling branch and does not contain scoped admission. Their common ancestor is b2f40def57b881b9cefc772910ad5ca0c584a549. The integration must preserve both capabilities. Source identity, a built artifact, installation and actual project adoption are separate facts.

## Boundaries
The public package owns reusable validators, commands, schemas and templates. The user overlay owns private identity, hosts, configuration and bindings. Each project owns its documents, domain state and diagnostic evidence. Generated Atlas views are derived projections. This change adds bounded diagnostic inspection and repairs established build/entry interfaces; it does not create a fleet daemon or substitute project database.

## Constraints
Preserve existing writers, protected effects, unknown-operation reconciliation, historical receipts and disabled native hooks. Never include credentials, private routes, raw session transcripts or project evidence in public source. Existing live services remain under their own deployment contracts. All implementation is made in an isolated checkout and reviewed before managed release activation.
