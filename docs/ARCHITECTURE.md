# Architecture

## Components

```text
Feishu / automation
        |
OpenClaw Gateway on US1
        |
TypeScript tool plugin
  - TypeBox input/output schemas
  - tool policy and confirmation boundary
  - capability routing and provider health
  - timeout, idempotency, cancellation, redaction
        |
        |
Python bridge on US1
  - pyiCloud session handling
  - Calendar/CloudKit adapters
  - sole provider during stabilization
        |
Apple private web services

Conditional after stabilization gate:
TypeScript tool plugin -> authenticated Mac bridge -> macOS frameworks
```

The pyiCloud bridge is the sole initial provider. This intentionally prevents a native Mac path from masking pyiCloud failures. The Mac design remains available as a contingency, but no Mac runtime is implemented or enabled until measured evidence passes the decision gate.

The pyiCloud implementation uses one short-lived Python subprocess per invocation. This keeps failure isolation simple and avoids another local network port. A persistent pyiCloud sidecar may be considered only if measured latency justifies it.

## Mac bridge transport

The default design is an outbound connection from the Mac to US1 so no inbound Mac port must be exposed. Final transport selection follows an inventory of the Mac's OS, CPU, TLS support, Python/Swift availability, and network location. Required properties are:

- Mutual device authentication with a separately revocable key.
- Capability advertisement and health heartbeat.
- Request IDs, deadlines, idempotency keys, and signed responses.
- A strict command allowlist; no generic shell execution.
- Credentials remain in the macOS user context and are never copied to US1.
- Automatic reconnect with bounded backoff.

Possible implementations are a small Swift agent, a compatible Python agent, or a reverse-SSH stdio service. The oldest supportable and least privileged option will be selected after hardware inventory.

## Provider routing and failover

- Route all Phase 1 operations to pyiCloud and expose its errors directly as typed results.
- Do not silently route around pyiCloud during the stabilization window.
- After the stabilization report, keep pyiCloud-only routing if it meets the service objectives.
- Add a Mac provider only for explicitly documented gaps, and define routing separately when that decision is made.
- For writes, choose exactly one provider before dispatch.
- Never retry a timed-out write through the other provider unless the first provider proves it did not commit.
- Reconcile by stable identifier after reconnect and report conflicts instead of silently overwriting.
- Notes may be Mac-only if no reliable pyiCloud adapter passes the research gate.

## Protocol

- One JSON request on stdin and one JSON response on stdout.
- Logs go to stderr and pass through redaction.
- Every message contains `protocolVersion`.
- Mutations contain an idempotency key.
- Requests identify the selected provider and approval-policy reference.
- Responses contain normalized data only; raw Apple headers, cookies, URLs with tokens, and account bootstrap payloads are forbidden.

Initial error codes:

- `AUTH_REQUIRED`
- `TWO_FACTOR_REQUIRED`
- `ACCOUNT_LOCKED`
- `SERVICE_UNAVAILABLE`
- `NOT_FOUND`
- `CONFLICT`
- `RATE_LIMITED`
- `INVALID_REQUEST`
- `UPSTREAM_CHANGED`

## Source reuse from InkBoard

Candidate modules:

- `icloud_client.py`: service construction, trusted-session checks, Calendar response normalization.
- `cloudkit_reminders.py`: CloudKit zone discovery, pagination, list resolution, text-document decoding.
- Authentication assistant: two-phase 2FA flow and operational knowledge for stale-process cleanup and account lock errors.

Required changes before reuse:

- Remove dashboard-specific `AgendaItem` coupling.
- Replace console printing with structured errors and redacted logging.
- Separate auth from service operations.
- Add timezone-aware datetime handling.
- Add request deadlines, response validation, pagination limits, and rate-limit behavior.
- Add write-path contracts and idempotency tests; existing InkBoard use is primarily read-oriented.
- Reimplement rather than copy code if repository license provenance is not compatible.

## Tool rollout

Tools are introduced in risk order:

1. `apple_account_status`
2. `apple_calendar_list_calendars`
3. `apple_calendar_list_events`
4. `apple_calendar_get_event`
5. `apple_reminders_list_lists`
6. `apple_reminders_list`
7. `apple_reminders_get`
8. Create/update tools with confirmation or a matching stored approval and idempotency
9. Delete-by-default and explicit soft-cancel tools with stricter confirmation
10. Notes read-only tool only after the research gate passes

Read and write tools should be separately controllable by OpenClaw tool policy.

## Pre-approved automation writes

An approval is data, not a prompt phrase. Each stored approval is revocable and constrains:

- tool/action names;
- target calendars or reminder lists;
- allowed field patterns and maximum item count;
- schedule or expiry;
- channel/requester identity;
- selected provider behavior;
- audit-log destination.

Any request outside the exact policy returns `APPROVAL_REQUIRED`. Account content cannot create or broaden an approval.

## Time and identity

- Transport timestamps as RFC 3339 with explicit offsets.
- Preserve Apple's stable record identifiers but never ask the model to invent them.
- Return both source timezone and normalized UTC timestamps.
- For recurring events, require an explicit mutation scope.

## Compatibility policy

Apple endpoints used by pyiCloud are private and may change without notice. Pin tested dependency versions, keep sanitized response fixtures, detect schema drift, and fail closed on unknown destructive-operation responses.
