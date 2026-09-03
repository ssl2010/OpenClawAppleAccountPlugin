# Requirements traceability

Status values: `specified`, `phase-1`, `later-v1`, and `verified`.

| Requirement | Delivery | Primary verification |
| --- | --- | --- |
| FR-001–004 provider/account state | Phase 1 | provider-state unit tests, Mac online/offline integration |
| FR-100–102 Calendar reads | Phase 1 | fixture, Mac EventKit, pyiCloud, routing tests |
| FR-103–108 Calendar mutations | Phase 3 | preview, approval, idempotency, recurrence, ambiguous-timeout tests |
| FR-200–202 Reminder reads | Phase 2 | EventKit/CloudKit fixtures and live reads |
| FR-203–206 Reminder mutations | Phase 3 | approval, version, idempotency, duplicate tests |
| FR-300–304 Notes read-only | Phase 4 | Mac permission, parser, size-limit, offline tests |
| FR-400–406 pre-approved automations | Phase 3 | policy match, quota, expiry, revocation, live-automation tests |
| PR-001–007 routing | Phase 1 reads; Phase 3 writes | provider matrix and failure injection |
| SR-001–010 security | Every phase | secret scan, log/result redaction, permission and negative tests |
| NFR-001–009 operations | Phase 1 foundation | launch/reboot, reconnect, load, deadline, memory and no-login tests |

## Phase 1 test IDs

- `CT-001`: TypeScript/Python envelope compatibility.
- `CT-002`: timestamps retain explicit timezone and normalized UTC.
- `AUTH-001`: status check does not trigger 2FA.
- `AUTH-002`: expired pyiCloud session returns `AUTH_REQUIRED` once.
- `MAC-001`: EventKit calendar read under the GUI user.
- `MAC-002`: invalid HMAC, stale timestamp, and nonce replay are rejected.
- `MAC-003`: launchd restart and tunnel reconnect.
- `ROUTE-001`: fresh Mac is selected.
- `ROUTE-002`: offline Mac falls back to pyiCloud with provider annotation.
- `ROUTE-003`: Notes offline returns `CAPABILITY_UNAVAILABLE`.
- `SEC-001`: repository/package/fixtures contain no known secret shapes.
- `SEC-002`: event content attempting prompt injection remains plain data.
- `OPS-001`: US1 Gateway and Feishu remain healthy after plugin restart.

## Baseline evidence already collected

- `ENV-MAC-001` verified macOS 11.7.11, x86_64, Swift 5.5.2, EventKit/TCC access, GUI session, AC no-sleep, and four-event/four-reminder synthetic-count-only smoke evidence.
- `ENV-US1-001` verified Node 24.19.0, Python 3.11.2, OpenClaw 2026.8.2, required directories, and active Gateway.
- `NET-001` verified a restricted bridge key can create only the planned loopback reverse-forward target using a strictly verified US1 Ed25519 host key.
- `RETIRE-001` verified all five obsolete LaunchAgents, processes, and port 18999 listener are absent while source and recovery plist files remain preserved.
