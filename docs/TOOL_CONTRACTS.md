# OpenClaw tool contracts

All schemas are strict: unknown input fields are rejected. Stable identifiers come from a prior list/get result and must never be invented by the model.

## Common result envelope

```json
{
  "ok": true,
  "provider": "mac",
  "observedAt": "2026-09-03T07:30:00Z",
  "freshnessSeconds": 1,
  "requestId": "uuid",
  "data": {}
}
```

Errors use `ok: false`, a stable `code`, a safe message, `retryable`, and optional `reauthenticationRequired`. Raw upstream messages are logged only after redaction and are not returned to the model.

## Required read tools

### `apple_account_status`

Input: none.

Returns provider health, authentication state, permissions, advertised capabilities, effective routing, and version compatibility. It never tests credentials by triggering 2FA.

### `apple_calendar_list_calendars`

Input: optional provider preference (`auto`, `mac`, `pyicloud`).

Returns calendar ID, title, color when available, writable state, and source account label.

### `apple_calendar_list_events`

Required input: `start`, `end`. Optional: `calendarIds`, `query`, `limit`, `cursor`, provider preference.

Defaults: `limit=50`; maximum `200`; maximum time span `366 days` for an interactive call and `31 days` for unattended automation unless its policy grants more.

### `apple_calendar_get_event`

Required input: `eventId`. Optional: provider hint from a previous result.

### `apple_reminders_list_lists`

Input: optional provider preference.

### `apple_reminders_list`

Optional input: `listIds`, `completed`, `dueStart`, `dueEnd`, `query`, `limit`, `cursor`, provider preference.

Defaults: incomplete reminders, `limit=50`; maximum `200`.

### `apple_reminders_get`

Required input: `reminderId`.

### `apple_notes_list`

Mac-only. Optional input: folder ID, query, limit, cursor. Returns metadata and a bounded preview, not the full body.

### `apple_notes_get`

Mac-only. Required input: `noteId`. Returns a size-bounded plain-text representation and metadata. Attachments and embedded active content are not executed.

## Optional mutation tools

Mutation tools are optional OpenClaw tools and require explicit `tools.allow`. Each requires `idempotencyKey`; unattended calls additionally require `approvalPolicyId` and `automationId`.

### `apple_calendar_create_event`

Requires `calendarId`, `title`, `start`, `end`, and explicit timezone/all-day semantics.

### `apple_calendar_update_event`

Requires `eventId`, a non-empty patch, and `expectedVersion` from the prior read to prevent lost updates.

### `apple_calendar_cancel_event`

Requires `eventId`, `mode` (`delete` or `soft`), and recurring scope when applicable. `mode` defaults to `delete` only after the model has presented that consequence to the operator or a stored policy explicitly permits it.

Soft mode prefixes `[已取消]` and appends:

```text
[OpenClaw:soft-cancelled timestamp=<RFC3339> request=<requestId>]
```

### `apple_reminders_create`

Requires `listId` and `title`; other fields are optional and capability-checked.

### `apple_reminders_update`

Requires `reminderId`, a non-empty patch, and `expectedVersion`.

### `apple_reminders_complete`

Requires `reminderId`; already-complete is a successful no-op.

### `apple_reminders_delete`

Requires `reminderId` and an exact prior read/version.

## Mutation preview and receipt

Before approval, the plugin produces a bounded preview with action, provider, exact target, changed fields, recurrence scope, and deletion consequence. After execution it returns a receipt and persists only non-secret audit metadata.

## Approval behavior

- Interactive writes offer `allow-once`, `allow-always`, and `deny` only where a connected approval route exists.
- `allow-always` becomes durable only after the plugin creates a bounded policy record; OpenClaw's generic decision alone is not treated as future authorization.
- No approval route, timeout, malformed decision, stale target version, or policy mismatch fails closed.
