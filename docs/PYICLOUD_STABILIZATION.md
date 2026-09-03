# pyiCloud stabilization gate

## Purpose

Validate pyiCloud as the only production Apple-data provider before spending energy and maintenance effort on a legacy Mac bridge. No Mac fallback may be enabled during this gate.

## Entry criteria

- Account status and read-only Calendar tools pass unit, fixture, contract, live opt-in, and OpenClaw plugin validation tests.
- Credentials and reusable sessions are stored outside the repository and model-visible configuration.
- Structured redacted metrics, bounded retries, circuit breaking, and notification deduplication are deployed on US1.
- Feishu can request Calendar reads through the allowlisted OpenClaw path.

## Observation window

The gate runs until both conditions are satisfied:

- at least 30 consecutive calendar days in production-like operation;
- at least 500 representative eligible read operations.

A release that materially changes authentication, session handling, response parsing, or the pinned pyiCloud dependency restarts the observation window. Planned configuration-only changes do not.

## Required measurements

Record daily aggregates only; never store item bodies, credentials, cookies, tokens, raw Apple responses, or full stable identifiers.

| Metric | Passing threshold |
| --- | --- |
| Eligible-read success rate | at least 99% |
| Eligible-read p95 latency | under 15 seconds |
| Silent truncation or incorrect normalization | zero confirmed cases |
| Credential/session leakage | zero cases |
| Retry storms | zero cases |
| Duplicate mutations | zero cases once writes enter testing |
| Auth-expiry notifications | one actionable notification per incident |
| Unplanned operator intervention | recorded and root-caused |

Confirmed Apple-wide outages and operator-deferred interactive reauthentication are reported separately and excluded from the eligible-read numerator/denominator. They must not be silently discarded.

## Mandatory fault exercises

- Expired and invalid reusable session.
- Two-factor-required state without prompt loops.
- DNS failure, connection timeout, connection reset, and temporary Apple service failure.
- Rate-limit response with bounded backoff.
- Unknown or missing response fields and schema fingerprint change.
- Pagination boundary, empty result, large bounded result, all-day event, DST change, and mixed timezones.
- Python subprocess crash, OpenClaw plugin restart, and planned US1 reboot.

## Decision record

At exit, publish one of these decisions in `docs/DECISIONS.md`:

- `pyicloud-only`: every required capability and service objective passes; keep the Mac retired.
- `approve-conditional-mac`: identify each failed capability/objective, user impact, evidence, and the smallest Mac scope that addresses it.
- `extend-stabilization`: evidence is insufficient or a material pyiCloud change reset the window.

Mac implementation is not permitted merely as a precaution. It requires the reviewed `approve-conditional-mac` decision.
