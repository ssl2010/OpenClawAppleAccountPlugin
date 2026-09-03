# Phase 1 execution plan

Phase 1 originally targeted read-only Calendar. The operator subsequently
approved Calendar mutations and pre-approved automation, so the deployed MVP
also includes create, update, and delete plus the fixed-scope 12306 worker. It
still intentionally does not implement or enable the Mac provider.

## Workstream A — shared contracts

- [x] Add TypeScript provider, envelope, error, calendar, and health types.
- [x] Add equivalent Python bridge models.
- [ ] Add JSON fixtures that contain only synthetic data.
- [ ] Add cross-language contract tests.
- [x] Add canonical timestamp, timezone, and stable-ID normalization.

## Workstream B — pyiCloud provider on US1

- [ ] Refactor the proven InkBoard authentication state machine.
- [ ] Store password input and reusable sessions outside repository/model context.
- [x] Implement bounded `account.status` without triggering new 2FA prompts.
- [x] Implement Calendar list, event list, and event get.
- [x] Add typed errors for authentication, timeout, rate limit, and upstream changes.
- [x] Add synthetic fixtures and unit tests.

## Workstream C — pyiCloud observability and resilience

- [ ] Add redacted structured metrics for calls, latency, typed errors, schema fingerprints, and session age.
- [ ] Add bounded retry with jitter only for demonstrably safe reads.
- [ ] Add circuit breaking and retry-storm protection.
- [ ] Add operator-visible auth-required notification deduplication.
- [ ] Add a sanitized daily reliability summary and stabilization report generator.

## Workstream D — OpenClaw integration

- [x] Replace scaffold capability tool with `apple_account_status`.
- [x] Add Calendar read and mutation tools with strict schemas.
- [ ] Implement pyiCloud health/cache state with no fallback provider.
- [ ] Annotate results with provider and freshness.
- [x] Preserve typed pyiCloud failures instead of hiding them with fallback.
- [x] Add plugin tool allowlist documentation.

## Workstream E — validation and deployment

- [x] TypeScript unit and plugin contract tests.
- [x] Python unit and fixture tests.
- [ ] pyiCloud valid, expired, 2FA-required, and upstream-schema-change tests.
- [ ] pyiCloud timeout, rate-limit, pagination, network-loss, process-restart, and US1-reboot tests.
- [x] Install the plugin on US1 and inspect runtime.
- [ ] Query upcoming events through Feishu using pyiCloud and verify provider/error annotations.
- [ ] Run OpenClaw security audit and confirm no new critical findings.

## Phase 1 exit criteria

- `apple_account_status` reports pyiCloud authentication and service health accurately.
- Calendar list/get returns normalized, bounded results through pyiCloud.
- No Mac runtime or hidden fallback is enabled.
- Mutation tools are registered only because the operator explicitly approved
  interactive writes and pre-approved fixed-scope automation.
- No secret appears in source, logs, tool results, status UI, or fixtures.
- US1 Gateway and Feishu remain healthy through plugin restart.

## Phase 1S stabilization criteria

- At least 30 consecutive days and 500 representative read operations, whichever takes longer.
- At least 99% successful eligible reads, excluding confirmed Apple outages and operator-deferred reauthentication.
- p95 eligible-read latency under 15 seconds.
- Zero silent truncation/corruption, secret leakage, retry storms, or duplicate mutations.
- Auth expiry produces one actionable notification and recovers through the documented operator flow.
- Schema drift fails closed and records only a redacted diagnostic fingerprint.
- A reviewed report explicitly decides either `pyicloud-only` or `approve-conditional-mac`.

## Prepared environments

- Local development repository: `OpenClawAppleAccountPlugin` in the current Codex workspace.
- US1 repository: `/home/Daniel/work/OpenClawAppleAccountPlugin`.
- US1 config/state roots: `~/.config/openclaw-apple-account` and `~/.local/state/openclaw-apple-account`.
- Mac paths and SSH assets are retained as dormant contingency preparation; they are not Phase 1 deployment targets.
- Mac deployment root: `~/work/openclaw-apple-bridge`.
- Mac state root: `~/Library/Application Support/OpenClawAppleBridge`.
- Mac log root: `~/Library/Logs/OpenClawAppleBridge`.
- Local SSH alias: `OLD-MAC-APPLE-BRIDGE`.
