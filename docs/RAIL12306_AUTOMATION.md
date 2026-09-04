# 12306 email automation

## Design

The implementation is split deliberately:

- The `apple-account` plugin exposes deterministic parsing and Apple Calendar tools.
- The `rail12306-calendar` skill controls interactive OpenClaw behavior.
- A restricted systemd timer reads Gmail with `gog`, validates direct or configured forwarded 12306 notices, and invokes the same deterministic Python code.

Email content is untrusted data. It cannot authorize commands or broaden the worker's fixed scope.

## Semantics

- Purchase: create the marked itinerary, or update the same marked itinerary idempotently.
- Refund: delete only an exact marked single-segment event whose train, stations and departure match. Partial/legacy refunds require review.
- Change: update one exact marked itinerary. If reconciliation produces multiple candidates, stop with `CONFLICT`.
- Transfers: connected segments in one notification/order for the same passenger within 24 hours are represented by one event. Cross-order merging and partial transfer changes require review; do not silently remove unrelated legs.
- Fulfilled waitlists count as purchases. Waitlist withdrawals and invoice/reimbursement notices do not change calendars. Subjects, not policy footers, determine the transaction.
- Stations: titles and locations use prefecture-level city aliases. Operator overrides are supported for unmapped stations.
- Notes: one stable line per segment contains train, station interval, seat (including no-seat), gate, and scheduled time interval, followed by `from OpenClaw US1`.
- Timetable: each non-cancellation segment is matched against the dated official 12306 public query by train and exact station codes. The first departure and final arrival bound a merged itinerary.

Every managed event includes a marker containing the 12306 order and a one-way hash prefix for the passenger. The raw passenger name is not placed in the marker.

## Deployment modes

Run without `--apply` for dry-run validation. Production uses `--apply` only after purchase, refund, and change fixtures plus one real operator-approved round trip have passed.

The `0600` state stores message IDs, order IDs, original timestamps, action/status, notification flags and safe errors, not bodies. Per-order watermarks prevent stale purchases/retries from overwriting changes/refunds. A lock and write-ahead blocked state prevent crash replay. Unknown writes require reconciliation.

Set `ICLOUD_CALENDAR_ID` explicitly to the railway calendar. Do not depend on calendar ordering. Forwarded mail with timezone-less Chinese timestamps requires explicit `RAIL12306_FORWARD_TIMEZONE=Asia/Shanghai`; ambiguous dates fail closed. Message search must return a complete bounded result with no omitted pages, otherwise no writes occur.

Create/update success requires exact identity, content and time read-back. Delete requires confirmed absence; a detail 404 alone is insufficient, and must be corroborated by the readable calendar and original event-range listing.

## 2026-09-04 regression validation

- 103 Python tests passed; source mypy and ruff passed.
- Private corpus: 54 attached EMLs. 29 purchase + 3 waitlist fulfillment + 3 refund + 6 change notices parsed; 11 invoices + 2 waitlist withdrawals excluded. All ticket dates predate the test cutoff. Raw samples are not committed.
- Live temporary event create/update/delete completed with exact read-back and cleanup.
- Target forwarded purchase passed the real CLI JSON boundary and updated the existing railway event in place; official dated timetable supplied the arrival.
- `scripts/audit-rail-corpus.py ACCOUNT MESSAGE_ID` downloads EML only into a private temporary directory. `scripts/validate-rail-corpus.py CORPUS_JSON YYYY-MM-DD` performs read-only fixture checks. `scripts/rail-live-lifecycle.py --apply` requires explicit authorization for its temporary event lifecycle.

## Timetable failure behavior

The official public web query is not a documented third-party API and may be unavailable, rate-limited, or changed. On any missing or mismatched segment, the worker creates or updates the event with a clearly marked ten-minute fallback, sends one Feishu warning, and leaves the message in `timetable-pending`. The ten-minute systemd schedule retries the same idempotent event; an exact later match replaces the fallback with the official scheduled arrival.

Scheduled arrival is not live running status. Delays and temporary operational changes require a separate real-time source and must never silently overwrite the published schedule.
