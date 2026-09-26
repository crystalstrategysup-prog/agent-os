# Security and threat model

Protected assets include private knowledge and credentials, product source,
truthful evidence, target authority, and release provenance. Text in a document
or profile and old receipts grant no new permission. Removing native AgentOS
hooks does not disable unrelated client sandboxes or target access controls.

| Risk | Control | Limit |
| --- | --- | --- |
| Question blocked by intake or Stop | Direct read path, retired no-op callbacks, no hook registration | Verify each client's effective behavior separately |
| Product change without docs | AGENTS workflow and explicit READY/check/close | Python cannot intercept arbitrary external shell work |
| Old or fabricated PASS | Task/revision/policy/source/log binding, latest receipt, age limit, verify-closeout | A same-user writer can forge local files |
| READY mistaken for deployment authority | Target-specific capability checks | Declared effects cannot reveal every hidden effect |
| User settings lost on update | Disjoint roots, immutable releases, create-only import, backups | Host I/O, ACL, and restore need separate proof |
| Traversal, symlinks, unbounded stdin | Containment, regular JSON files, bounded object stdin | Hostile filesystem races remain possible |
| Unwanted instruction or client config edits | Managed AGENTS block, skill conflicts and backups; hooks/config untouched | Conflicting owner rules need separate resolution |
| Large AGENTS text truncated | Short routing index, topical links, fresh-session readback | Size and Markdown cannot prove client comprehension |
| Profile text used as authority | Exact IDs/hashes, host binding, conflict checks, `profile_authority=false` | Prompt injection remains a risk |
| Secret or release substitution | Separate public tree, manifests, exact-current comparison | Hashes are unsigned; scanning is heuristic |
| Unverified launcher or bytecode | Compare installed wheel payload and script hashes, clear package caches before probe | Same-user malicious races remain possible |
| Interrupted entry accepted as READY | Entry journal blocks dependent lifecycle until recovery | Read-only questions continue |
| Check leaves descendants | Own process group and cleanup after launch | Runner is not a sandbox for checked code |
| Public guide leaks a user's continuity passport | Generic packaged template; filled passport in external overlay; public export review | A template does not make private files safe to publish |
| Local sync path mistaken for a backup | Require independent read-back and sample restore before device clearance | Cloud server state cannot be inferred from a local directory |

Read-only inspection and needed bootstrap/document preparation are permitted.
Write paths are assessed, not enforced by an OS ACL. Registered `project check`
uses exact argv without shell interpolation, but the program can still reach a
network or mutate an external host. Verify those effects and authority first.
Stronger isolation needs a separate user or container with scoped mounts,
network, and credentials.

A target capability must identify actor, account/host/object, operation,
validity or lease, limits, and whether it grants read, write, send, or
destructive effects. If it is absent, stop that target action while continuing
allowed investigation. There is no universal `--authorized` switch, inherited
profile power, or authority from READY. Direct reading also requires lawful,
existing read access; the fast path is not blanket access to mail or databases.

Retired callbacks return `{}`, not an allow decision or COMPLETE. They are not
registered or run as a guard. Preserve unrelated client, connector, and host
security controls. Editorial advice about AGENTS length creates no read gate
and does not remove target capability checks.

Public overlay exports exclude authentication files, SSH keys, cookies, and
Telegram sessions. Redaction is an additional heuristic control. Local history
and receipts are not externally signed. This project does not claim a security
certification, penetration test, or general compliance approval.
