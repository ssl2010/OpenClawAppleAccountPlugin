# Architecture decisions

## ADR-001: Hybrid TypeScript and Python

**Status:** accepted for initial development.

OpenClaw's native plugin SDK is TypeScript while the proven Apple integration is Python/pyiCloud. Keep the OpenClaw boundary in TypeScript and place Apple-specific behavior in a private Python bridge connected over stdio.

## ADR-002: No local HTTP service initially

**Status:** accepted.

Use subprocess stdio to avoid adding an authenticated network listener and service lifecycle. Revisit only after profiling.

## ADR-003: Read-first rollout

**Status:** accepted.

Ship account status, Calendar reads, and Reminders reads before any mutation. Writes require confirmation, idempotency, and separate tool-policy controls.

## ADR-004: Notes is a research gate

**Status:** accepted.

Do not promise Notes based solely on pyiCloud. Ship only after a reliable read-only adapter passes fixture and live tests, otherwise use a macOS-node fallback.

## Decisions needed from the owner

1. License: private/all-rights-reserved, MIT, Apache-2.0, or another choice.
2. Calendar deletion semantics: hard delete versus cancellation/soft delete where Apple supports it.
3. Whether contacts and iCloud Drive belong in v1 or a later release.
4. Whether a permanently online Mac is available as the Notes fallback.
5. Whether US1 may send write operations automatically for pre-approved recurring workflows, or every mutation must be confirmed.
