# Stage F15B — live SSH/VNC field validation

Task: `task-4e547aee82124ba2`

Status: transport candidate checks passed; original viewer requirement deferred
by the owner in [STAGE-F15C](STAGE-F15C.md).
This stage follows the published `v0.5.2` scenario and the
owner's request to test and debug it on one actual host before calling it a
reference procedure.

## Objective and observed baseline

Make the public SSH/VNC route actionable and repeatable while preserving its
authority boundary. On 2026-09-26, one already authorized macOS host was reached
through its existing SSH alias with strict host-key checking and batch
authentication. A bounded remote identity command succeeded. Its loopback VNC
endpoint returned `RFB 003.889`; a local loopback SSH forward returned the same
banner and RFB security types. A first test invocation with
`ClearAllForwardings=yes` left SSH connected but suppressed the explicit local
forward. Omitting that option restored the forward. No VNC authentication or
desktop frame was observed. The temporary forward was closed and verified gone.
The host alias, address, account and credentials stay outside public source.

## Change boundary

Add one bounded, opt-in diagnostic for an exact existing SSH alias. It must
perform an authenticated identity probe, open an OpenSSH stdio VNC channel when
requested, inspect the RFB protocol greeting, and return structured evidence
that distinguishes SSH, VNC transport, VNC login and an actual frame. It may
report the latter two as unverified; it must never infer them from a banner.
Use fixed SSH arguments, strict host-key checking, no password prompts, short
timeouts, no shell interpolation of user input, and cleanup on supported normal,
error and keyboard-interrupt paths. Abrupt force-kill cleanup is not proven.
The diagnostic does not enable services, configure a host, grant access, scan
networks or read credentials. Keep the scenario `guide_only` for setup.

Update the public card and field guide with tested command patterns, including
the `ClearAllForwardings` trap, the limits of `ExitOnForwardFailure`, a local
loopback binding, native VNC viewer authentication and teardown. Package and
test the diagnostic as a versioned public patch. Review source, wheel and
release assets, then plan a managed Mac update against exact installed 0.5.2.
No Remote Access Helper change or private route publication is authorized.

## Acceptance

- A single exact-alias invocation returns bounded, machine-readable SSH and
  optional RFB evidence; it never reports a usable desktop without a real
  authenticated frame.
- Negative tests cover an invalid alias, failed SSH authentication, closed
  SSH/VNC channel, malformed RFB greeting, timeout and
  cleanup after failure or interruption.
- The same diagnostic succeeds through the selected live host's existing route
  at the SSH and RFB layers. Desktop login/frame remains explicitly pending if
  no authorized viewer session can be completed.
- Public card, docs, CLI contracts, package and tests agree on the exact
  behavior. Privacy/export and local install fixture checks pass.
- A versioned release and Mac update are read back separately. No native hooks
  or private user data enter the public package.

## Scope amendment — desktop proof deferred

On 2026-09-26 the owner requested removing Screen Sharing for now. F15C
supersedes the original viewer requirement: current acceptance ends at SSH/RFB
transport. VNC authentication and a frame remain unverified; they do not block
this narrowed scope and no native login is required from the owner now.
Public release and managed installation still need their own delivery proof.

## Rollback

Temporary SSH forwards are stopped by the diagnostic in all normal and error
paths. Keep the existing 0.5.2 release and managed installation immutable. A
new patch can be reverted by the managed installer to verified 0.5.2 without
restoring AgentOS hooks or changing the user overlay.

## Candidate evidence

The final diagnostic uses standard OpenSSH `-W` and opens no local listener or
temporary filesystem socket. The exact selected host passed this implementation
with `TRANSPORT_VERIFIED`, `ssh_authenticated=true`, `rfb_transport=true`,
`RFB 003.889`, security types 30/33/36/35, and `forward_closed=true`.
`vnc_authenticated` and `desktop_frame_verified` remained false.

On 2026-09-26, 278 local tests and Ruff passed. A clean export passed public
privacy/version validation and source/resource parity. The candidate wheel
`crystal_agent_os-0.5.3-py3-none-any.whl` is 169576 bytes, SHA-256
`382f3eacb7c859c9c305e49b20ac5c558ccbda0a7bde9b4f492c326ca7825180`;
all 110 packaged `agent_os` files match source bytes. The Darwin arm64 Python
3.14.6 offline install/update/rollback fixture passed and preserved its
synthetic user tree. No v0.5.3 tag, release or managed owner-Mac update was
performed. Stable public and installed 0.5.2 remains the current target.

The owner was asked to complete the native viewer login without sharing a
password in chat. The current session has no callable Mac-app control tool.
The owner subsequently deferred this viewer step in F15C.

Registered checks all passed against source inventory
`37ea9d0d2022d71fcae9d6207e07db7219bcd69caca05bd7fc2247968d15cda3`:
probe tests `f973ee13f8f347c8809e4c5c1748d8ca`, live transport probe
`26faa8f921c340ff9135bfaf0f569e93`, full tests
`b1fa811dbc994f27aa5f5ba1bdedbd52`, and installation fixture
`e4deb51bc71f4ea38191487a588a996d`. These are local-process receipts;
they do not establish VNC authentication or a frame. Final self-review found no
blocking source defect. These receipts predate the F15C documentation amendment.
