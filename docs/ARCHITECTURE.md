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
  - timeout, cancellation, redaction
        |
JSON request/response over subprocess stdio
        |
Python bridge
  - pyiCloud session handling
  - Apple/CloudKit adapters
  - normalization and typed errors
        |
Apple private web services
```

The first implementation uses one short-lived Python subprocess per tool invocation. This keeps failure isolation simple and avoids opening a local network port. A persistent sidecar may be considered only if measured latency justifies the additional lifecycle and security complexity.

## Protocol

- One JSON request on stdin and one JSON response on stdout.
- Logs go to stderr and pass through redaction.
- Every message contains `protocolVersion`.
- Mutations contain an idempotency key.
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
8. Create/update tools with confirmation and idempotency
9. Cancel/complete/delete tools with stricter confirmation
10. Notes read-only tool only after the research gate passes

Read and write tools should be separately controllable by OpenClaw tool policy.

## Time and identity

- Transport timestamps as RFC 3339 with explicit offsets.
- Preserve Apple's stable record identifiers but never ask the model to invent them.
- Return both source timezone and normalized UTC timestamps.
- For recurring events, require an explicit mutation scope.

## Compatibility policy

Apple endpoints used by pyiCloud are private and may change without notice. Pin tested dependency versions, keep sanitized response fixtures, detect schema drift, and fail closed on unknown destructive-operation responses.
