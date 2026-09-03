# Product scope

## Product statement

Provide a small, auditable set of OpenClaw tools for the repository owner's Apple account while keeping credentials outside model context and requiring deliberate authorization for mutations.

## Personas and deployment

- One trusted operator.
- OpenClaw Gateway runs continuously on US1 Linux.
- Commands arrive primarily through the allowlisted Feishu channel.
- pyiCloud on US1 is the initial production provider and must be evaluated without fallback.
- A legacy Mac bridge is optional and remains off unless measured gaps justify its energy and maintenance cost.
- Apple authentication is completed interactively by the operator and reused through a protected session.

This is not a multi-tenant service and must not expose one Apple session to multiple unrelated users.

## Version 1 capabilities

### Calendar

- List calendars.
- List events for an explicit time range.
- Read one event by stable identifier.
- Create an event after confirmation.
- Update an event after confirmation.
- Delete an event by default after confirmation.
- Soft-cancel only when the user explicitly requests preservation instead of deletion.

Recurring-event behavior must be explicit: one occurrence versus the entire series. A soft-cancel operation must preserve the item and apply a clearly documented marker instead of pretending Apple provides a universal cancellation state.

### Reminders

- List reminder lists.
- Query incomplete reminders by list and due range.
- Read one reminder by stable identifier.
- Create and update a reminder after confirmation.
- Complete or delete a reminder after confirmation.

CloudKit Reminders support is based on a private Apple interface and requires fixture-driven compatibility tests.

### Account/session

- Report authenticated, reauthentication-required, region, and service-availability states.
- Start an operator-only authentication flow without exposing secrets to the model.
- Notify the operator once when a session expires; avoid repeated 2FA prompts.

## Research capabilities

### Apple Notes

pyiCloud does not currently provide a stable, supported Notes service. Notes work begins as a read-only feasibility spike with three possible outcomes:

1. A maintainable iCloud web adapter with safe parsing and stable identifiers.
2. A macOS-node fallback using a native Notes CLI.
3. Explicitly unsupported if neither approach meets reliability and security requirements.

No write or delete capability will be attempted before read-only reliability is demonstrated.

## Later candidates, outside v1

- Contacts search and read.
- Narrowly scoped iCloud Drive listing and download.
- Photos metadata and explicit download.

## Out of scope by default

- Find My location, play-sound, lost-mode, or device erase actions.
- Password, trusted-device, recovery, or other Apple account-security changes.
- Bulk destructive actions.
- Browser automation against iCloud.com as a production dependency.
- Multi-user credential sharing.

## Success criteria for v1

- Read tools produce stable normalized JSON and never leak raw session data.
- Every mutation is idempotent or protected by a caller-supplied idempotency key.
- Destructive actions require explicit confirmation and precise target identifiers.
- A stored, revocable approval policy may authorize a bounded automation to mutate without per-run confirmation.
- Provider failover never duplicates a mutation after an ambiguous timeout.
- Session expiry produces a typed reauthentication error rather than retry storms.
- Unit, contract, fixture, security, and US1 smoke tests pass.
