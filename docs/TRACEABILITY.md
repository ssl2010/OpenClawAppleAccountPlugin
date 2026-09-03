# Requirements traceability

Status values: `specified`, `phase-1`, `later-v1`, and `verified`.

| Requirement | Delivery | Primary verification |
| --- | --- | --- |
| FR-001–004 provider/account state | Phase 1 | pyiCloud auth/service state and typed-failure tests |
| FR-100–102 Calendar reads | Phase 1 | pyiCloud fixture, live, pagination, timezone, and schema tests |
| FR-103–108 Calendar mutations | Phase 3 | preview, approval, idempotency, recurrence, ambiguous-timeout tests |
| FR-200–202 Reminder reads | Phase 2 | EventKit/CloudKit fixtures and live reads |
| FR-203–206 Reminder mutations | Phase 3 | approval, version, idempotency, duplicate tests |
| FR-300–304 Notes read-only | Conditional Phase 4 | provider research gate, parser, size-limit, unavailable behavior |
| FR-400–406 pre-approved automations | Phase 3 | policy match, quota, expiry, revocation, live-automation tests |
| PR-001–008 routing | Phase 1 pyiCloud-only; later conditional routing | failure injection, stabilization report, decision record |
| SR-001–010 security | Every phase | secret scan, log/result redaction, permission and negative tests |
| NFR-001–009 operations | Phase 1 foundation | US1 restart, auth recovery, network fault, load and deadline tests |

## Phase 1 test IDs

- `CT-001`: TypeScript/Python envelope compatibility.
- `CT-002`: timestamps retain explicit timezone and normalized UTC.
- `AUTH-001`: status check does not trigger 2FA.
- `AUTH-002`: expired pyiCloud session returns `AUTH_REQUIRED` once.
- `PYI-001`: valid pyiCloud session reads normalized Calendar data.
- `PYI-002`: rate limit, timeout, schema drift, and network loss produce typed errors without retry storms.
- `PYI-003`: session reuse and reauthentication recovery survive US1 process and host restarts.
- `ROUTE-001`: pyiCloud is the sole eligible Phase 1 provider.
- `ROUTE-002`: no hidden Mac fallback occurs during stabilization.
- `ROUTE-003`: Notes without a qualified provider returns `CAPABILITY_UNAVAILABLE`.
- `SOAK-001`: the stabilization window meets the documented availability, latency, auth, and correctness thresholds.
- `SEC-001`: repository/package/fixtures contain no known secret shapes.
- `SEC-002`: event content attempting prompt injection remains plain data.
- `OPS-001`: US1 Gateway and Feishu remain healthy after plugin restart.

## Baseline evidence already collected

- `ENV-MAC-001` verified macOS 11.7.11, x86_64, Swift 5.5.2, EventKit/TCC access, GUI session, AC no-sleep, and four-event/four-reminder synthetic-count-only smoke evidence.
- `ENV-US1-001` verified Node 24.19.0, Python 3.11.2, OpenClaw 2026.8.2, required directories, and active Gateway.
- `NET-001` verified a restricted bridge key can create only the planned loopback reverse-forward target using a strictly verified US1 Ed25519 host key.
- `RETIRE-001` verified all five obsolete LaunchAgents, processes, and port 18999 listener are absent while source and recovery plist files remain preserved.
