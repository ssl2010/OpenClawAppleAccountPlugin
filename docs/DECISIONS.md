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

## ADR-005: Apache-2.0 license

**Status:** accepted.

The project is licensed under Apache-2.0.

## ADR-006: Mac-primary, pyiCloud-fallback routing

**Status:** accepted.

A custom daemon on an older always-on Mac is the preferred provider when healthy. US1 pyiCloud adapters provide capability-specific fallback. The Mac does not need to run OpenClaw. Reads may fail over automatically; ambiguous writes may not.

## ADR-007: Calendar cancellation semantics

**Status:** accepted.

Calendar cancellation deletes the event by default. The caller may explicitly request soft cancellation to preserve it. The exact soft-cancel marker will be finalized with the Calendar contract.

## ADR-008: V1 excludes Contacts and iCloud Drive

**Status:** accepted.

Contacts and iCloud Drive remain post-v1 candidates. V1 focuses on account/session, Calendar, Reminders, and Mac-backed read-only Notes.

## ADR-009: Pre-approved automated writes

**Status:** accepted.

An operator may create a bounded, revocable approval policy for recurring automation writes. Prompt text cannot create or widen a policy, and every use is audited.

## ADR-010: macOS 11-compatible native bridge

**Status:** accepted after host audit.

The primary bridge targets an Intel MacBook Air running macOS 11.7.11 with 4 GB RAM. Calendar and Reminders use a small Swift/EventKit helper, proven by the predecessor deployment. A lightweight supervisor, outbound reverse-SSH-style transport, and loopback-only status surface may reuse the predecessor's operational patterns. Notes uses a separate native/JXA adapter. OpenClaw, containers, browser automation, and model inference remain off this Mac.

## Decisions still needed from the owner

1. Soft-cancel representation: title prefix, dedicated calendar, note/status marker, or another convention.
2. Default pre-approval limits: maximum writes per run/day and approval expiry.
3. Whether the Mac will normally remain logged in after reboot, which is required for user-context TCC access.
