# Connection scenarios

A connection scenario is a versioned unit of public AgentOS knowledge describing
how a person can enable a capability. It supplies a route for a conversational
or graphical setup wizard. A scenario is neither permission to execute a step
nor proof that the capability works for a particular user.

## Storage and boundaries

- `src/agent_os/resources/setup-scenarios/index.json` is the entry index. It
  lists only published scenario cards.
- Each card beside the index describes one goal, alternate flows, actions,
  expected proof, recovery, and primary sources. Its structure is defined by
  `schemas/setup-scenario-v1.schema.json` and the matching packaged schema.
- This document defines how to author and use cards. Link to official external
  API documentation instead of copying it wholesale. Keep deployment-specific
  details in their own projects.
- Personal configuration, credentials, sessions, instance details, and live
  receipts belong in the external user overlay. An executable private provider
  needs its own contract and authority check.

`agentos setup list` reads the index; `agentos setup show <id>` reads one card.
Neither command runs setup steps or performs network checks. A future GUI or
conversational wizard can use the same data without a second instruction set.

For a remote-device request, select `ssh-vnc-tunnel` by goal, then check the
exact user's existing verified device route before asking setup questions. Its
short first flow covers that common case. Otherwise choose one route from the
card: direct SSH, a trusted jump host, or a loopback-bound reverse forward;
add VNC through SSH only if the person asks for a desktop. Keep device identity,
transport, SSH authentication and desktop authentication as separate evidence.
No public card contains a host inventory, grants access or executes a tunnel.

For an exact existing SSH route, the separately invoked
`agentos setup probe ssh-vnc --host ALIAS` returns a network-free plan;
`--apply` performs the bounded SSH/RFB diagnostic. This does not change the
read-only behavior of `setup list/show` or enable automatic setup. Follow the
[SSH/VNC field procedure](SSH_VNC_FIELD_GUIDE.md) for tested commands, layered
results and cleanup. Desktop viewer integration is deferred. A `TRANSPORT_VERIFIED` result leaves
VNC authentication and a desktop frame unverified.

## Authoring a scenario

1. State the goal in the user's language and choose a stable lowercase `id`.
   Do not make separate public cards for each host, person, or provider version.
2. Check primary sources and a reference implementation path. Record the review
   date and evidence level: `documented`, `source_verified`, or `live_verified`.
   Source or live proof applies only to its stated scope; one private success
   does not establish universal support.
3. Describe alternate flows and the minimum user actions. For each step record
   the actor, action, required input, and expected proof. Name sensitive inputs
   by type and storage boundary; never put actual phone numbers, login codes,
   credentials, or session material in a public card.
4. Describe failure, retry, cancellation, and access revocation. Identify steps
   that require separate user confirmation or target authority.
5. Add the card to the index; validate schema, links, packaging, and CLI output.
   Update relevant docs and review the diff before publication.

## Using a scenario

Choose a card from the index based on the user's goal, then read only that card.
Check its prerequisites against current state. `guide_only` provides advice and
a verifiable plan; it does not enable automatic execution. A runnable provider
requires separate implementation, acceptance, and authority. Check the exact
target before any login, rights grant, or message. A JSON card or old screenshot
cannot establish readiness; current identity and capability receipts plus a safe
end-to-end test are needed for the selected instance.

## Keeping scenarios current

Each card names its maintainer and review triggers. A change in an external API,
provider, or user route can mark the card for review. The review procedure checks
primary documentation and the current provider, proposes a diff, and adjusts the
evidence level. A human reviews changes to meaning, permissions, and secret
handling. A separately scheduled audit may check the index and links; an
end-to-end test requires a suitable environment and authority. An automatic
sweep across all scenarios is not implemented yet.

If drift is found, report it and stop describing the old route as current.
`reviewed_on` records review of text and sources, not a successful live login.
A specific user's connection state is stored separately from the public card.
For SSH/VNC, a saved route also needs the exact target, source and date of the
last authenticated check, requested capability, and a review trigger such as a
changed host key, device, broker, user, credential or failed connection. Reuse
that record for fast discovery, then verify it against current state before
action. Do not copy its addresses or credentials into public source.
