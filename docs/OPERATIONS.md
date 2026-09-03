# Operations baseline

## Host roles

- US1 owns OpenClaw, plugin policy, approvals, the primary pyiCloud provider, audit metadata, and operator notifications.
- ShileideAir is a dormant contingency host. It owns native Apple access and tunnel state only if Conditional Phase M is approved.
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

### Legacy Mac (dormant contingency)

```text
~/work/openclaw-apple-bridge/                         deployment
~/Library/Application Support/OpenClawAppleBridge/   state and receipts
~/Library/Logs/OpenClawAppleBridge/                   redacted logs
```

## Health model

Expose these states separately:

- process: stopped, starting, healthy, degraded;
- authentication: authenticated, reauthentication-required, two-factor-required, locked;
- pyiCloud services: individually healthy, degraded, unavailable, or schema-incompatible;
- session: age, last validated timestamp, and redacted schema fingerprint;
- effective route: pyiCloud during Phase 1/1S;
- last successful read/write and last safe error code.

Mac transport, permissions, and provider health are added only if Conditional Phase M is approved.

Do not display item bodies, credentials, session paths, tokens, signatures, or full identifiers in the status UI.

## pyiCloud startup order

1. US1 starts OpenClaw Gateway and loads the plugin.
2. The plugin validates non-secret configuration and protected session-directory permissions.
3. A bounded status probe classifies authentication without triggering repeated 2FA.
4. The plugin advertises only pyiCloud capabilities that passed compatibility checks.
5. Metrics and redacted schema fingerprints begin recording for the stabilization report.

The retired Mac jobs remain disabled throughout Phase 1 and Phase 1S.

If Conditional Phase M is approved, its separate startup sequence is defined in the Mac bridge runbook before deployment. Automatic macOS login remains disabled.

## Failure behavior

- pyiCloud auth expiry: mark the provider unavailable and request operator reauthentication once.
- network/Apple outage: use bounded safe-read retries and circuit breaking; expose a typed error when exhausted.
- rate limiting: honor retry guidance with a hard attempt/deadline cap and no retry storm.
- provider schema drift: fail closed and retain a redacted diagnostic fingerprint.
- ambiguous mutation: block retry and require reconciliation.

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

Run before conditional Mac development or deployment, not before pyiCloud Phase 1:

```bash
scripts/check-mac-prereqs.sh
scripts/check-us1-prereqs.sh
```

Both scripts are read-only and fail nonzero when a required dependency or baseline is absent.
