# 12306 email automation

## Design

The implementation is split deliberately:

- The `apple-account` plugin exposes deterministic parsing and Apple Calendar tools.
- The `rail12306-calendar` skill controls interactive OpenClaw behavior.
- A restricted systemd timer reads Gmail with `gog`, validates direct or configured forwarded 12306 notices, and invokes the same deterministic Python code.

Email content is untrusted data. It cannot authorize commands or broaden the worker's fixed scope.

## Semantics

- Purchase: create the marked itinerary, or update the same marked itinerary idempotently.
- Refund: delete only calendar items carrying the exact OpenClaw 12306 marker.
- Change: update one exact marked itinerary. If reconciliation produces multiple candidates, stop with `CONFLICT`.
- Transfers: connected segments for the same passenger within 24 hours are represented by one event from the first origin city to the final destination city. Individual trains remain in notes.
- Stations: titles and locations use prefecture-level city aliases. Operator overrides are supported for unmapped stations.
- Notes: one stable line per segment contains train, station interval, seat (including no-seat), gate, and scheduled time interval, followed by `from OpenClaw US1`.
- Timetable: each non-cancellation segment is matched against the dated official 12306 public query by train and exact station codes. The first departure and final arrival bound a merged itinerary.

Every managed event includes a marker containing the 12306 order and a one-way hash prefix for the passenger. The raw passenger name is not placed in the marker.

## Deployment modes

Run without `--apply` for dry-run validation. Production uses `--apply` only after purchase, refund, and change fixtures plus one real operator-approved round trip have passed.

The worker stores only message ID, action, status, and safe error code in its `0600` state file. It does not store email bodies.

## Timetable failure behavior

The official public web query is not a documented third-party API and may be unavailable, rate-limited, or changed. On any missing or mismatched segment, the worker creates or updates the event with a clearly marked ten-minute fallback, sends one Feishu warning, and leaves the message in `timetable-pending`. The ten-minute systemd schedule retries the same idempotent event; an exact later match replaces the fallback with the official scheduled arrival.

Scheduled arrival is not live running status. Delays and temporary operational changes require a separate real-time source and must never silently overwrite the published schedule.
