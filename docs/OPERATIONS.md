# Operations baseline

## Host roles

- US1 owns OpenClaw, plugin policy, approvals, provider routing, pyiCloud fallback, audit metadata, and operator notifications.
- ShileideAir owns native Apple access, TCC permissions, Mac-local request receipts, and the outbound restricted tunnel.
- The local development Mac owns source editing, signing/release preparation, and administrative SSH access.

## Access paths

- Local to US1: SSH alias `US1-DANIEL`.
- Local to legacy Mac: SSH alias `OLD-MAC-APPLE-BRIDGE` using a dedicated administration key.
- Legacy Mac to US1: dedicated forwarding-only key, forced command rejection, a single permitted loopback listener (`127.0.0.1:19091`), and a dedicated known-hosts file.
- GitHub: repository-specific deploy key; never reuse the bridge transport key.

## Directory layout

### US1

```text
~/work/OpenClawAppleAccountPlugin/       source checkout
~/.config/openclaw-apple-account/        non-secret config and secret references
~/.local/state/openclaw-apple-account/   provider state, approvals, audit metadata
```

### Legacy Mac

```text
~/work/openclaw-apple-bridge/                         deployment
~/Library/Application Support/OpenClawAppleBridge/   state and receipts
~/Library/Logs/OpenClawAppleBridge/                   redacted logs
```

## Health model

Expose these states separately:

- process: stopped, starting, healthy, degraded;
- transport: disconnected, connecting, connected;
- permissions: calendar, reminders, notes individually granted/denied/unknown;
- providers: Mac and pyiCloud individually healthy/degraded/offline;
- effective route: provider per capability;
- last successful read/write and last safe error code.

Do not display item bodies, credentials, session paths, tokens, signatures, or full identifiers in the status UI.

## Startup order

1. User logs into the Mac GUI session.
2. launchd starts the bridge service.
3. Bridge performs local permission/capability probes.
4. Tunnel job starts and verifies remote-forward establishment.
5. US1 health probe sees the Mac and validates HMAC protocol compatibility.
6. Router marks each advertised Mac capability eligible.

Automatic login stays disabled. Before GUI login, pyiCloud provides only its supported fallback capabilities.

## Failure behavior

- Tunnel failure: keep native service local, reconnect with capped backoff, report Mac offline on US1.
- TCC revoked: mark only the affected capability degraded and notify once.
- Mac sleep/offline: reads fall back per capability; no queued Mac writes.
- pyiCloud auth expiry: mark fallback unavailable and request operator reauthentication once.
- provider schema drift: fail closed and retain a redacted diagnostic fingerprint.
- ambiguous mutation: block fallback/retry and require reconciliation.

## Log retention defaults

- Operational logs: 14 days, size bounded.
- Non-secret audit metadata: 90 days.
- Idempotency/mutation receipts: at least the maximum approval lifetime plus 7 days, default 37 days.
- Nonce replay cache: maximum clock-skew window plus margin, default 5 minutes.

## Recovery

The retired predecessor LaunchAgents are stored under:

```text
~/Library/LaunchAgents.retired/20260903-150603-old-eink-bridge/
```

They must not be reloaded alongside the new bridge. Their source is reference-only. Recovery of the new bridge will use its own versioned release directory and launchd definitions.

## Preflight

Run before Phase 1 development or deployment:

```bash
scripts/check-mac-prereqs.sh
scripts/check-us1-prereqs.sh
```

Both scripts are read-only and fail nonzero when a required dependency or baseline is absent.
