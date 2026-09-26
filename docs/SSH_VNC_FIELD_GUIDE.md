# SSH and VNC: field procedure

Use one exact, authorized device route. Reuse its reviewed SSH alias and host
key before discovering another path. Keep addresses, accounts, keys and live
receipts in the external user overlay. The public scenario is setup guidance;
the opt-in probe verifies an existing route without configuring the device.

## Fast preflight

```sh
# Network-free plan:
agentos setup probe ssh-vnc --host MY_SSH_ALIAS

# Authorized read of that exact device:
agentos setup probe ssh-vnc --host MY_SSH_ALIAS --apply

# Shell access only; no VNC connection:
agentos setup probe ssh-vnc --host MY_SSH_ALIAS --ssh-only --apply
```

The POSIX probe requires OpenSSH and an already verified host key. It uses
batch authentication, disables agent forwarding and host-key updates, and
accepts an alias rather than a raw address, key, username or remote command.
The selected SSH configuration remains user-owned and must be reviewed,
including its ProxyCommand, jump host and configured forwards. The command
accepts an ASCII alias starting with a letter and containing only letters,
digits, hyphens or underscores. It does not accept a password or enroll an
unknown host key.

For VNC, it uses OpenSSH `-W` to forward standard input/output to the device's
loopback endpoint. It opens no local TCP listener or filesystem socket and
clears inherited forwards. It reads the RFB greeting and security-method offer,
then closes the SSH channel. It never selects an authentication method or
requests a frame. The SSH identity check is bounded to 18 seconds and the RFB
channel to 12 seconds. No raw SSH error, alias, account or address is printed
in its JSON result. Supported normal, error and keyboard-interrupt paths stop
the child process; abrupt forced termination of the probe is not cleanup proof.

| Result | Proven | Still required |
| --- | --- | --- |
| `PLANNED` | No network operation ran | Exact target authority and `--apply` |
| `SSH_VERIFIED` | Host-key policy and authenticated command execution | VNC if requested |
| `TRANSPORT_VERIFIED` | SSH plus an RFB greeting and security-method offer through the forward | VNC login and a current frame |
| `FAIL` | Only fields explicitly marked true | Repair the reported layer and retry |

`vnc_authenticated` and `desktop_frame_verified` remain false in every result.
Exit code 0 covers a plan or the requested transport proof, 1 a failed probe,
and 2 invalid input or an unsupported environment. Result schema:
`schemas/ssh-vnc-probe-v1.schema.json`. Windows execution is not implemented
for this diagnostic; the connection guide itself remains platform-neutral.

## Complete the desktop test

After a transport pass, start one reviewed viewer forward. The following
pattern was exercised against one existing macOS SSH route. Choose a free
local port and leave the process visible so it can be stopped precisely.

```sh
ssh -N -T \
  -o BatchMode=yes -o StrictHostKeyChecking=yes -o UpdateHostKeys=no \
  -o ExitOnForwardFailure=yes -o ClearAllForwardings=no \
  -L 127.0.0.1:45900:127.0.0.1:5900 MY_SSH_ALIAS
```

Connect the approved VNC viewer to `127.0.0.1`, port `45900`. On a Mac, use
Screen Sharing and a **Standard** connection for this single RFB tunnel; a High
Performance connection may require additional transport and is not established
by this procedure. Authenticate with the approved device account in the viewer,
without sending its password to chat or putting it in a URL. Confirm a current
desktop frame and the intended device. A login dialog, RFB banner, black frame
or stale screenshot is not usable-desktop proof. Do not alter the remote
workspace merely to obtain a screenshot. Record the result and date privately.

Disconnect the viewer, then stop the exact SSH process with Ctrl-C. Verify that
its local listener has closed. Do not use a broad `pkill ssh`, stop a shared
master connection or remove someone else's access.

## Select a route only when the known one fails

| Network situation | Shortest suitable route |
| --- | --- |
| Target SSH is reachable | Direct SSH alias |
| Target is reachable only from an existing trusted broker | Alias with `ProxyJump` or reviewed `ProxyCommand` |
| Target cannot accept inbound connections | Target-originated reverse SSH forward to an authorized broker, bound to broker loopback |

For a new reverse route, an authorized device can forward its SSH service with
`ssh -N -o ExitOnForwardFailure=yes -R 127.0.0.1:BROKER_PORT:127.0.0.1:22
BROKER_ALIAS`. Broker policy must permit only the intended listener and keep it
off public interfaces. The operator's device alias then reaches that loopback
port through the broker and verifies the **device's** host key. Broker login,
device login and VNC permissions are distinct. Route setup and access grants
retain separate authority; this probe creates none of them.

## Traps found during validation

- `ClearAllForwardings=yes` cancels explicit `-L` forwards too. SSH can remain
  connected while the requested listener is absent. Use it only for the
  command-only or `-W` probe; a viewer's `-L` forward explicitly uses `no`.
- `ExitOnForwardFailure=yes` checks forward setup and binding. It does not prove
  that the final VNC endpoint accepts a connection; require the RFB response.
- A process-table or `lsof` query without sufficient visibility can show no
  listener even when a socket-activated macOS service responds. A bounded
  connection to the exact endpoint is the transport check.
- A changed or unknown host key is an identity problem. Verify it through a
  trusted source; do not replace strict checking with `accept-new` or `no` to
  make the test green.
- A transport pass does not establish VNC account permission or a desktop.
  Finish the native viewer test and keep incomplete layers visible.

## Evidence and maintenance

On 2026-09-26, one owner-authorized macOS 26.6.2 host passed authenticated SSH
and RFB transport through this diagnostic, returning `RFB 003.889`. The
temporary forward was closed. VNC authentication and a desktop frame were not
verified in that run; this is not universal device support or complete desktop
acceptance. Private route details and receipts are excluded from publication.

Recheck on host-key, account, device, broker or credential changes, a failed
connection, and changes to platform guidance. Keep the last successful proof
for each layer, its date and its invalidation trigger in the user's record.

Primary references: [OpenSSH client](https://man.openbsd.org/ssh),
[client configuration](https://man.openbsd.org/ssh_config),
[server configuration](https://man.openbsd.org/sshd_config),
[RFB protocol](https://www.rfc-editor.org/info/rfc6143/),
[Apple Screen Sharing](https://support.apple.com/guide/mac-help/mh14066/mac),
and [Apple connection settings](https://support.apple.com/guide/mac-help/mchl67d5398b/mac).
