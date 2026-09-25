# Security Policy

Please do not open a public issue containing credentials, Telegram sessions,
personal identifiers, private hostnames, private overlay data or exploit details
for a live installation.

Until a dedicated security mailbox is published, use GitHub's private vulnerability
reporting feature for this repository. Include the affected version, impact and a
minimal synthetic reproduction without third-party secrets or raw production logs.

The `0.x` series is beta software. Review connector permissions before production
use. Native hook bypass, same-UID tampering and unverified target execution are
described in the [security model](docs/SECURITY_MODEL.md).

The AI steward may triage a private report and prepare a remediation, but must not
publish confidential report contents or claim a fix before the current release is
independently verified.
