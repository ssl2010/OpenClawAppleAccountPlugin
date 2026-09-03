# Development roadmap

## Phase 0 — foundation

- [x] Create repository and dedicated deploy key.
- [x] Add OpenClaw TypeScript plugin scaffold.
- [x] Add Python bridge scaffold.
- [x] Document scope, architecture, security, and decisions.
- [ ] Install dependencies and validate the scaffold against OpenClaw 2026.8.2 on US1.
- [ ] Choose repository license.

Exit: clean build, plugin validation, unit tests, and local install smoke test.

## Phase 1 — authentication and read-only Calendar

- Extract and refactor the proven InkBoard authentication flow.
- Store password outside OpenClaw configuration and model context.
- Store session cookies under a dedicated `0700` directory.
- Add `apple_account_status` and typed auth errors.
- Add calendar list/get tools with timezone normalization and pagination limits.
- Add sanitized fixture and live opt-in integration tests.

Exit: US1 can answer a Feishu request for upcoming events without leaking credentials or raw upstream data.

## Phase 2 — read-only Reminders

- Adapt CloudKit zone pagination and reminder decoding.
- Add list/query/get tools.
- Detect upgraded Reminders schema drift.
- Add fixture tests for Chinese and English text, all-day items, priorities, and missing due dates.

Exit: stable read-only reminder queries through Feishu.

## Phase 3 — controlled mutations

- Implement calendar create/update/cancel.
- Implement reminder create/update/complete/delete.
- Add preview-before-commit responses.
- Require idempotency keys and precise identifiers.
- Add OpenClaw permission requests and tool-policy separation.
- Test repeated requests, partial failures, recurring events, and stale identifiers.

Exit: approved mutations are reliable and duplicate-safe.

## Phase 4 — Notes feasibility gate

- Document available Notes endpoints and authentication behavior.
- Build a read-only prototype with sanitized fixtures.
- Compare reliability with a macOS-node native fallback.
- Perform a security review before exposing any model-visible Notes tool.

Exit: ship read-only Notes, use a Mac fallback, or explicitly mark Notes unsupported.

## Phase 5 — optional services and release

- Evaluate contacts search and iCloud Drive list/download.
- Add CI, dependency review, SBOM, package contents test, and secret scanning.
- Pin dependencies and validate installation from a packed artifact.
- Prepare private release; consider ClawHub only after code and credential handling audits.

## Testing matrix

- TypeScript: schema, plugin metadata, subprocess cancellation, redaction, tool policy.
- Python: unit, fixtures, normalization, auth state machine, pagination, schema drift.
- Contract: TS-to-Python JSON protocol.
- Integration: optional account-backed tests excluded from default CI.
- Deployment: US1 systemd restart, OpenClaw plugin inspect/validate, Feishu read and mutation approval flows.
