# F20 — Telegram owner inbox connection scenario

Task: `task-043f181b72044f6b`

## Objective and evidence

The owner requested on 2026-09-30 that Telegram file intake become a discoverable
AgentOS capability while each host's bot token stays in its private user overlay.
The public 0.5.5 setup index currently has Telegram MTProto and Business cards,
but no owner file inbox card. A standalone private reference receiver has been
source-reviewed and live-checked on one host; instance evidence stays outside
the public repository.

## Change scope and boundaries

Add one English `guide_only` card, an index entry and short discovery guidance.
The card must cover one poller per bot, owner-private identity, durable local
storage, a path-reply receipt, service recovery, token rotation and revocation.
It must distinguish a standalone provider from the public foundation and keep
tokens, owner IDs, hostnames, files and private routes in the external overlay.
No executable provider, native hook, credential migration or live Telegram
effect is added to the public package.

## Acceptance

- `agentos setup list` and `setup show telegram-owner-inbox` expose the card.
- Schema, package resource and public export checks pass locally.
- The card says that a live host requires a separately verified provider and
  receipt; documentation alone is not a working receiver.

## Rollback and next step

Remove this index entry and card in a later reviewed public patch if the guide
is wrong. Such a source rollback does not touch any standalone receiver,
its state or the owner overlay. A future adapter implementation is a separate
stage with its own host acceptance and credentials boundary.

## Local result

The catalog schema/CLI tests and clean public export verifier passed. A clean
export wheel contains the new scenario card. The public source review found no
credentials or host-specific values in the card. This stage does not prove a
general inbox adapter or an installed public release; publication and target
installation require separate receipts.
