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

Every managed event includes a marker containing the 12306 order and a one-way hash prefix for the passenger. The raw passenger name is not placed in the marker.

## Deployment modes

Run without `--apply` for dry-run validation. Production uses `--apply` only after purchase, refund, and change fixtures plus one real operator-approved round trip have passed.

The worker stores only message ID, action, status, and safe error code in its `0600` state file. It does not store email bodies.

## Known boundary

12306 purchase notices usually provide departure times but not reliable arrival times. Until a separately verified timetable source is added, a merged itinerary ends two hours after the final segment's departure. The exact segment departure details remain in notes; this estimate must be made visible during validation.
