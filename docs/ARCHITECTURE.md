# Architecture

Crystal AgentOS Community Edition is split into four boundaries:

```text
MCP client / CLI
       ↓
safe public tools
       ↓
task and onboarding contracts
       ↓
private local configuration and connector adapters
```

The public core never assumes access to a maintainer's infrastructure. Private
deployments belong in overlays that are not committed to this repository.

## Invariants

- No credential values in ordinary MCP responses.
- No arbitrary shell, SSH, recipient, path or URL tool.
- Configuration and secrets are local by default.
- Tasks are normalized before a connector executes them.
- Production mutations require a deployment-specific authority and rollback path.
- Telegram QR is the primary MTProto onboarding method.
- A credential bundle is an explicit, owner-approved output and is handled like a password.

## Public versus private

The public repository owns reusable contracts and reference implementations.
A private overlay owns host inventories, account IDs, credentials, business
rules, production routes and incident history. The public package must work
without the private overlay.
