# Legacy Mac bridge plan

## Purpose

Use an older, always-on Mac as the preferred Apple-data provider without installing OpenClaw on it. The OpenClaw plugin remains on US1 and routes supported requests to the Mac bridge while it is healthy. pyiCloud provides tested fallback capabilities when the Mac is unavailable.

## Discovery checklist

Record these facts before selecting an implementation language or transport:

- Mac model and year.
- CPU architecture: Intel `x86_64` or Apple Silicon `arm64`.
- Exact macOS version and latest supported security update.
- Installed Python, Swift, Xcode Command Line Tools, Homebrew, SSH, and TLS versions.
- Whether the user can grant Calendar, Reminders, Notes, and Automation privacy permissions.
- Whether the login user remains signed in and applications/data remain available after reboot.
- Sleep, wake-on-network-access, automatic-login, power-recovery, and UPS behavior.
- Network path to US1, including any existing reverse SSH or Tailscale option.

The initial inventory is captured in [Legacy Mac audit](LEGACY_MAC_AUDIT.md). The selected baseline is a native Swift/EventKit helper plus a lightweight supervisor and outbound authenticated transport. Notes will use a separately permissioned native/JXA adapter because EventKit does not expose Notes.

## Minimum daemon contract

The daemon must:

- start at user login with `launchd` and restart after failure;
- establish an outbound authenticated connection to US1;
- publish its version, host identity, supported commands, and permission status;
- send a heartbeat and reconnect with capped exponential backoff;
- accept only structured, schema-validated Apple commands;
- support deadlines, cancellation, request IDs, and mutation idempotency keys;
- return normalized JSON without credentials or unnecessary private content;
- log locally with redaction and rotation;
- expose no generic command execution or filesystem access.

## Provider states

- `healthy`: heartbeat fresh and capability probe succeeds.
- `degraded`: connected but a required macOS privacy permission or application is unavailable.
- `offline`: heartbeat expired or authenticated transport disconnected.
- `unknown`: startup or incompatible-version state; never selected for writes.

## Routing rules

| Operation | Mac healthy | Mac offline | Ambiguous Mac timeout |
| --- | --- | --- | --- |
| Calendar read | Mac | pyiCloud | pyiCloud with source annotation |
| Reminder read | Mac | pyiCloud if compatible | pyiCloud with source annotation |
| Notes read | Mac | unavailable unless fallback passes research gate | report uncertainty; do not retry silently |
| Calendar/reminder write | Mac | pyiCloud only if selected before dispatch | reconcile; never cross-provider retry |

Every response identifies `provider`, `observedAt`, and freshness. Merged results must deduplicate by stable source identifier; fuzzy title/time matching is not sufficient for destructive operations.

## Candidate implementations

### Swift/Foundation daemon — selected baseline

The deployed predecessor proved that macOS 11.7.11 and this Intel Mac can compile and run a small EventKit binary reliably. Use Swift/Foundation for Calendar and Reminders collection and mutation. Keep the deployment target compatible with macOS 11 and avoid new concurrency/runtime features that require newer systems.

### Python supervisor/status service — supporting role

Homebrew Python 3.14.3 is available, while launchd's `/usr/bin/python3` resolves to an older Command Line Tools runtime. If Python is used for transport or the status service, the LaunchAgent must reference the explicit Homebrew interpreter and run a startup preflight. Native Apple data access remains in the Swift helper.

### Reverse-SSH stdio bridge — initial transport candidate

The predecessor used reverse SSH successfully until the remote server was reinstalled and its host key changed. Reverse SSH remains the initial transport candidate because it is available on macOS 11 and requires no inbound Mac port. The new deployment must use one dedicated bridge key, a separately verified US1 host key, a forced server-side command where practical, and one tunnel implementation rather than competing tunnel jobs.

## Status surface direction

Reuse the predecessor's split design:

- a loopback-only lightweight status endpoint;
- a minimal native shell compatible with macOS 11;
- separate provider, transport, permission, sync, and last-error states;
- explicit `Mac primary`, `pyiCloud fallback`, or `unavailable` effective routing;
- no credentials or private Calendar/Notes contents in status output.

The status service must not be a control plane in v1. Mutating controls remain in OpenClaw with approval enforcement.

## Deployment security

- Use a bridge-specific SSH/device key, not the GitHub deploy key.
- Restrict the server-side key to the bridge command where feasible.
- Keep macOS permissions limited to the bridge user.
- Require manual local approval for first access to protected Apple applications.
- Rotate the device key independently and revoke it when the Mac is retired.
- Do not copy the Mac login password, Keychain database, or native account tokens to US1.

## Acceptance tests

- Reboot and login recovery.
- Sleep/wake and network-loss recovery.
- Mac online-to-offline read failover.
- No duplicate write after response loss.
- Permission revoked while connected.
- Old and new schema/version mismatch.
- Clock skew and timezone/DST boundaries.
- Session and bridge key rotation.
