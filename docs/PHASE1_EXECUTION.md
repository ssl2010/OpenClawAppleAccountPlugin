# Phase 1 execution plan

Phase 1 delivers account/provider status plus read-only Calendar through Mac primary and pyiCloud fallback. It performs no Apple mutations.

## Workstream A — shared contracts

- [ ] Add TypeScript provider, envelope, error, calendar, and health types.
- [ ] Add equivalent Python bridge models.
- [ ] Add JSON fixtures that contain only synthetic data.
- [ ] Add cross-language contract tests.
- [ ] Add canonical timestamp, timezone, and stable-ID normalization.

## Workstream B — pyiCloud provider on US1

- [ ] Refactor the proven InkBoard authentication state machine.
- [ ] Store password input and reusable sessions outside repository/model context.
- [ ] Implement bounded `account.status` without triggering new 2FA prompts.
- [ ] Implement Calendar list, event list, and event get.
- [ ] Add typed errors for 2FA, locked account, expired session, schema drift, timeout, and rate limit.
- [ ] Add sanitized fixtures and unit tests.

## Workstream C — Mac bridge

- [x] Confirm Swift/EventKit read access with real data.
- [x] Establish dedicated administration and restricted tunnel keys.
- [x] Verify strict US1 host-key checking and loopback reverse forwarding.
- [ ] Extract/refactor the predecessor EventKit reader into this repository.
- [ ] Implement `/v1/health`, `/v1/capabilities`, and Calendar read invocation.
- [ ] Add HMAC request authentication and replay protection.
- [ ] Add `launchd` service and tunnel definitions using absolute paths.
- [ ] Add a loopback-only status endpoint with no control actions.

## Workstream D — OpenClaw routing

- [ ] Replace scaffold capability tool with `apple_account_status`.
- [ ] Add Calendar read tools and strict TypeBox schemas.
- [ ] Implement provider health cache and capability-aware selection.
- [ ] Annotate results with provider and freshness.
- [ ] Implement safe read fallback and conflict reporting.
- [ ] Add plugin tool allowlist documentation.

## Workstream E — validation and deployment

- [ ] TypeScript unit and plugin contract tests.
- [ ] Python unit and fixture tests.
- [ ] Mac bridge protocol and auth tests.
- [ ] Mac online, degraded, offline, reconnect, sleep/wake, and reboot tests.
- [ ] pyiCloud valid, expired, 2FA-required, and upstream-schema-change tests.
- [ ] Install packed plugin on US1 and inspect runtime.
- [ ] Query upcoming events through Feishu with Mac online.
- [ ] Stop the Mac bridge and repeat through pyiCloud fallback.
- [ ] Run OpenClaw security audit and confirm no new critical findings.

## Phase 1 exit criteria

- `apple_account_status` reports both providers accurately.
- Calendar list/get returns normalized, bounded results through each provider.
- Automatic read fallback is visible and tested.
- No mutation tool is registered.
- No secret appears in source, logs, tool results, status UI, or fixtures.
- Mac services recover after login/reboot and tolerate network loss.
- US1 Gateway and Feishu remain healthy through plugin restart.

## Prepared environments

- Local development repository: `OpenClawAppleAccountPlugin` in the current Codex workspace.
- US1 repository: `/home/Daniel/work/OpenClawAppleAccountPlugin`.
- US1 config/state roots: `~/.config/openclaw-apple-account` and `~/.local/state/openclaw-apple-account`.
- Mac deployment root: `~/work/openclaw-apple-bridge`.
- Mac state root: `~/Library/Application Support/OpenClawAppleBridge`.
- Mac log root: `~/Library/Logs/OpenClawAppleBridge`.
- Local SSH alias: `OLD-MAC-APPLE-BRIDGE`.
