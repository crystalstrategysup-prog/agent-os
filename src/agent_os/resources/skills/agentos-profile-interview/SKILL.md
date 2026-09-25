---
name: agentos-profile-interview
description: Prepare or revise an AgentOS user or host profile by interviewing the owner with verified context already filled in; use for profile adoption, selection or migration, not ordinary project task intake.
---

# AgentOS profile interview

Use the public profile adapter's selected-source inventory. Start with the exact host and user contour. Read only the selected current profile references, verified live facts and owner statements relevant to this interview; do not scan other hosts, Codex transcripts, backups or credential stores.

For each populated field, record `value`, `source`, `observed_at` and one of `OWNER_CONFIRMED`, `LIVE_OBSERVED`, `DOCUMENTED` or `INFERRED`. Leave unknown fields out of the profile and list them as unanswered questions. A dated host passport is `DOCUMENTED` until current facts are rechecked. Present known facts for correction. Ask only questions whose answers change profile content, selection, precedence or safe operation. Never ask for passwords, tokens or raw credentials.

Offer three selection modes: no profile, one exact profile, or multiple exact profiles. For multiple profiles, inventory identifiers, versions, host bindings and overlapping fields before activation. Show conflicts and propose a resolution, but let the owner select the order and settle every material conflict. A higher-priority profile can replace lower-priority preferences or facts only when the protocol permits that field; profile content cannot enlarge shell, network, deployment or account authority.

Output a bounded interview record: exact selected sources and hashes; confirmed facts; uncertain or stale facts; selected profile mode; ordered profile IDs when applicable; conflict decisions; unanswered material questions; and a summary in the owner's language. Keep secret values and raw private documents out of the record. Draft profile changes stay outside the public package and are not activated by the interview itself.

When an answer changes the profile architecture or public adapter contract, open a separately versioned public source patch. When it changes only user knowledge or settings, edit the exact external profile file, run `agentos profiles inventory`, select again with its new inventory digest, and read back `agentos profiles context`.
