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

No implementation choice is final until this inventory is captured.

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

### Swift/Foundation daemon

Preferred if the installed macOS/Xcode toolchain can compile and run the required EventKit and Notes automation interfaces. It offers native frameworks and privacy prompts but may be constrained by the old OS.

### Python daemon

Preferred if a maintained Python runtime already exists and native access can be implemented through stable bridges. It is easier to share schemas with the pyiCloud adapter but must not depend on obsolete TLS or unmaintained binary packages.

### Reverse-SSH stdio bridge

Useful as an initial transport or recovery mechanism. It reuses mature SSH authentication and requires no inbound Mac port, but application-level schemas, timeouts, idempotency, and audit controls are still required.

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
