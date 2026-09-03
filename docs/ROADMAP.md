# Development roadmap

## Phase 0 — foundation

- [x] Create repository and dedicated deploy key.
- [x] Add OpenClaw TypeScript plugin scaffold.
- [x] Add Python bridge scaffold.
- [x] Document scope, architecture, security, and decisions.
- [ ] Install dependencies and validate the scaffold against OpenClaw 2026.8.2 on US1.
- [x] Adopt Apache-2.0.

Exit: clean build, plugin validation, unit tests, and local install smoke test.

## Phase 1 — pyiCloud authentication and read-only Calendar

- Extract and refactor the proven InkBoard authentication flow.
- Store password outside OpenClaw configuration and model context.
- Store session cookies under a dedicated `0700` directory.
- Add `apple_account_status` and typed auth errors.
- Add calendar list/get tools with timezone normalization and pagination limits.
- Add sanitized fixture and live opt-in integration tests.
- Deploy with pyiCloud as the only eligible provider; do not implement Mac routing yet.

Exit: US1 can answer a Feishu request for upcoming events without leaking credentials or raw upstream data.

## Phase 1S — pyiCloud stabilization gate

- Operate pyiCloud without a Mac fallback for at least 30 consecutive days and 500 representative read operations; extend the window until both conditions are met.
- Exercise session reuse, planned US1 restarts, transient network loss, expired authentication, pagination, timezones, rate limits, and upstream schema fingerprints.
- Record availability, p50/p95 latency, typed-error rate, reauthentication frequency, correctness samples, and operator interventions.
- Require zero credential leaks, zero silent data corruption, zero retry storms, and zero duplicate mutations before advancing.
- Produce a stabilization report mapping every unmet target or missing capability to user impact and mitigation.

Exit: pyiCloud meets the agreed service objectives, or the report contains concrete evidence that an optional Mac provider is necessary.

## Conditional Phase M — legacy Mac provider

Start this phase only after an explicit decision based on the Phase 1S report. If pyiCloud is sufficient, skip it and keep the retired Mac bridge off.

- [x] Inventory macOS version, CPU architecture, available runtimes, local network, and current keep-awake job.
- [x] Retire the obsolete Calendar tunnel/sync and StatusTool LaunchAgents while preserving their source for reference.
- Use a macOS 11-compatible Swift/EventKit helper with a lightweight supervisor/status layer.
- Implement outbound authenticated transport, heartbeat, capability advertisement, and reconnect.
- Implement native Calendar reads and compare normalized results with pyiCloud.
- Add provider health, routing, and reconciliation tests.

Exit: only the documented pyiCloud gaps are filled, routing is capability-specific, and enabling the Mac has a demonstrated benefit greater than its operational and energy cost.

## Phase 2 — read-only Reminders

- Adapt CloudKit zone pagination and reminder decoding.
- Add list/query/get tools.
- Detect upgraded Reminders schema drift.
- Add fixture tests for Chinese and English text, all-day items, priorities, and missing due dates.

Exit: stable read-only reminder queries through Feishu.

## Phase 3 — controlled mutations

- Implement calendar create/update/cancel.
- Make hard deletion the default cancellation behavior; require an explicit `soft` mode to preserve the event.
- Implement reminder create/update/complete/delete.
- Add preview-before-commit responses.
- Require idempotency keys and precise identifiers.
- Add OpenClaw permission requests and tool-policy separation.
- Add revocable, bounded approval policies for explicitly pre-approved automations.
- Prohibit cross-provider write retries after ambiguous outcomes.
- Test repeated requests, partial failures, recurring events, and stale identifiers.

Exit: approved mutations are reliable and duplicate-safe.

## Phase 4 — Notes feasibility gate

- Document available Notes endpoints and authentication behavior.
- Build a read-only prototype with sanitized fixtures.
- Evaluate a pyiCloud-compatible read-only adapter first.
- Implement native read-only Notes through the custom Mac bridge only if Notes remains required and Phase M is approved.
- Perform a security review before exposing any model-visible Notes tool.

Exit: ship Notes only through a provider that independently meets reliability and security gates; otherwise report it as unsupported.

## Phase 5 — optional services and release

- Evaluate contacts search and iCloud Drive list/download for a post-v1 release.
- Add CI, dependency review, SBOM, package contents test, and secret scanning.
- Pin dependencies and validate installation from a packed artifact.
- Prepare private release; consider ClawHub only after code and credential handling audits.

## Testing matrix

- TypeScript: schema, plugin metadata, subprocess cancellation, redaction, tool policy.
- Python: unit, fixtures, normalization, auth state machine, pagination, schema drift.
- Contract: TS-to-Python JSON protocol.
- Integration: optional account-backed tests excluded from default CI.
- Deployment: US1 systemd restart, OpenClaw plugin inspect/validate, Feishu read and mutation approval flows.
