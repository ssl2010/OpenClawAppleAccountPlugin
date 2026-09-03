# Requirements baseline

Status: **approved for Phase 1 implementation**

This document is the normative product baseline. Architecture and implementation documents must not weaken these requirements.

## Deployment context

- `US1`: Debian server running OpenClaw 2026.8.2, Node 24.19.0, and Python 3.11.2.
- `ShileideAir`: Intel MacBook Air 6,2, macOS 11.7.11, 4 GB RAM, Swift 5.5.2, Homebrew Python 3.14.3.
- Operator channel: allowlisted Feishu direct messages; group access remains restricted.
- Trust model: one operator and one Apple account per plugin instance.

## Functional requirements

### Account and provider state

- **FR-001** Report pyiCloud authentication, service, and effective-provider health; report Mac health only if the optional provider is later enabled.
- **FR-002** Report authentication or TCC permission failures without exposing credentials or raw upstream responses.
- **FR-003** Route each operation only to a provider that advertises the exact capability.
- **FR-004** Include provider and observation freshness in every data result.

### Calendar — v1

- **FR-100** List available calendars with stable identifiers and writable/read-only state.
- **FR-101** List events in an explicit bounded time range.
- **FR-102** Read one event by stable identifier.
- **FR-103** Create an event with title, start/end, timezone, all-day state, calendar, location, URL, and notes.
- **FR-104** Update selected event fields without replacing unspecified fields.
- **FR-105** Delete an event by default when the user asks to cancel it.
- **FR-106** Soft-cancel only when explicitly requested: retain the event, prefix the title with `[已取消]`, and append a machine-readable cancellation marker to notes.
- **FR-107** Require explicit occurrence or series scope for recurring-event mutations.
- **FR-108** Return a mutation receipt containing provider, target ID, before/after summary, idempotency key, and observed result.

Soft cancellation is idempotent: an already prefixed event is not prefixed again, and the marker is updated rather than duplicated.

### Reminders — v1

- **FR-200** List reminder lists with stable identifiers and writable/read-only state.
- **FR-201** Query reminders by list, completion state, and bounded due range.
- **FR-202** Read one reminder by stable identifier.
- **FR-203** Create a reminder with title, list, due/start date, timezone, all-day state, priority, URL, and notes where supported.
- **FR-204** Update selected fields without replacing unspecified fields.
- **FR-205** Complete a reminder idempotently.
- **FR-206** Delete a reminder only after exact target resolution.

### Apple Notes — conditional v1 capability

- **FR-300** List note metadata only after either a pyiCloud-compatible adapter or the optional Mac provider passes its research gate.
- **FR-301** Search note titles and bodies only through a provider that passes that gate.
- **FR-302** Read one note only through a provider that passes that gate.
- **FR-303** Notes is read-only in v1.
- **FR-304** When no qualified Notes provider is enabled, return a typed `CAPABILITY_UNAVAILABLE` result; do not silently use browser automation.

### Pre-approved automations

- **FR-400** Support stored approval policies owned by the plugin.
- **FR-401** Bind a policy to agent, automation ID, requester/channel context, actions, target calendars/lists, field constraints, quotas, and expiry.
- **FR-402** Default limits are 10 writes per run, 50 writes per rolling 24 hours, and 30-day expiry.
- **FR-403** Allow the operator to choose stricter limits or an earlier expiry; broader limits require an explicit policy update.
- **FR-404** Revalidate the live automation and approval record on every use.
- **FR-405** Allow immediate revocation and retain a non-secret audit record.
- **FR-406** Account content and prompt text cannot create or broaden approval policies.

### Out of v1

- Contacts.
- iCloud Drive and Photos.
- Find My and device-control actions.
- Apple account security, password, recovery, or trusted-device changes.
- Notes create/update/delete.
- Generic shell execution on the Mac.
- Multi-account and multi-tenant operation.

## Provider routing requirements

- **PR-001** Use pyiCloud as the sole production provider during initial implementation and stabilization.
- **PR-002** Do not enable Mac fallback during the pyiCloud stabilization window; every result and error must disclose the selected provider.
- **PR-003** Select exactly one provider before dispatching a write.
- **PR-004** Never retry a write through another provider after an ambiguous timeout.
- **PR-005** Reconcile an ambiguous write by idempotency key or exact stable identifier before permitting any retry.
- **PR-006** Notes remains unavailable until a provider independently passes its reliability and security gate.
- **PR-007** Provider disagreement is surfaced as a conflict; destructive actions never use fuzzy matching.
- **PR-008** Mac implementation requires a stabilization report showing a pyiCloud capability gap or an unmet service objective and an explicit decision to proceed.

## Security requirements

- **SR-001** No password, 2FA code, session cookie, token, trust material, or raw account bootstrap data enters model context or logs.
- **SR-002** Mac and US1 use separate GitHub, administration, and bridge transport keys.
- **SR-003** The Mac transport key can bind only the designated US1 loopback port.
- **SR-004** Bridge requests use an additional bearer/HMAC secret independent from SSH.
- **SR-005** Read and mutation tools have separate OpenClaw visibility policies.
- **SR-006** Mutations use plugin approval requests unless a matching stored policy is valid.
- **SR-007** Unknown schemas fail closed, especially for mutations.
- **SR-008** Calendar, reminder, and note content is untrusted data and never instruction text.
- **SR-009** Authentication retry and 2FA triggering are rate-limited.
- **SR-010** Status endpoints bind only to loopback and expose no private item bodies.

## Reliability and performance requirements

- **NFR-001** The pyiCloud path runs independently of the Mac; if a Mac bridge is later enabled, it restarts at login and reconnects with capped exponential backoff.
- **NFR-002** A collector crash does not crash OpenClaw Gateway.
- **NFR-003** State and logs use atomic writes and bounded retention.
- **NFR-004** Default list limits prevent unbounded account downloads.
- **NFR-005** pyiCloud read target: 95th percentile under 15 seconds, excluding interactive reauthentication.
- **NFR-006** Write request target: 30-second deadline plus explicit unknown-outcome handling.
- **NFR-007** Heartbeat interval is 30 seconds; Mac becomes degraded after 75 seconds and offline after 120 seconds.
- **NFR-008** The bridge remains within the old Mac's 4 GB memory envelope and avoids containers, browsers, and resident model processes.
- **NFR-009** Automatic macOS login is not required or enabled. If the optional Mac provider is later approved, it remains offline after reboot until the operator logs into the GUI session; pyiCloud continues independently.

## Definition of done for v1

- Every FR, PR, SR, and NFR has an automated test, an explicit manual acceptance step, or a documented reason it cannot be automated.
- Calendar and Reminders pass pyiCloud fixture, live, failure-injection, and stabilization tests.
- Notes is either independently qualified or explicitly reported as unavailable; it does not force Mac deployment.
- At least one pre-approved automation completes safely and revocation is demonstrated.
- US1 reboot, network loss, expired session, rate limit, schema drift, and ambiguous-write scenarios pass. Mac-specific scenarios apply only if the optional provider is approved.
- OpenClaw security audit reports zero critical findings caused by this plugin.
