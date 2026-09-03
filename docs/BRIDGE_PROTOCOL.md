# Mac bridge protocol v1

## Transport

The Mac daemon listens on `127.0.0.1:19090`. A dedicated SSH client creates:

```text
US1 127.0.0.1:19091 -> SSH reverse forward -> Mac 127.0.0.1:19090
```

The SSH key is restricted with `restrict`, `port-forwarding`, `permitlisten="127.0.0.1:19091"`, and `command="/usr/bin/false"`. It can establish only the approved reverse listener and cannot open a PTY or execute a remote command. It is independent from management and GitHub keys. US1's Ed25519 host key is stored in a dedicated known-hosts file on the Mac with strict checking.

The provisioning acceptance test confirmed all three properties: remote command execution is rejected, the loopback-only reverse forward carries application traffic successfully, and the US1 listener disappears after the SSH client exits.

The application protocol is HTTP/1.1 with JSON because both macOS 11 Foundation and US1 Node/Python support it without a heavy runtime. It remains loopback-only on both hosts and is additionally authenticated.

## Authentication

- A random 256-bit bridge secret is generated during provisioning and stored as a `0600` file on each host.
- Every request contains timestamp, nonce, request ID, body SHA-256, and HMAC-SHA256 signature.
- The Mac rejects clock skew over 120 seconds, reused nonces, invalid signatures, unknown protocol versions, and oversized bodies.
- Secret rotation supports current and next key for a short overlap, then removes the old key.

## Endpoints

- `GET /v1/health`: process, version, uptime, and transport-safe health.
- `GET /v1/capabilities`: supported operations and permission state.
- `POST /v1/invoke`: one typed operation.
- `GET /v1/requests/{id}`: mutation reconciliation by request/idempotency ID.

There is no generic command, filesystem, script, or proxy endpoint.

## Request

```json
{
  "protocolVersion": 1,
  "requestId": "uuid",
  "idempotencyKey": "uuid-or-null",
  "deadline": "2026-09-03T07:30:30Z",
  "operation": "calendar.listEvents",
  "parameters": {},
  "approval": {
    "mode": "interactive",
    "policyId": null
  }
}
```

The Mac validates the operation against a compiled allowlist and applies a hard local deadline. Approval is enforced on US1 and carried as audit context; the Mac still refuses mutations missing an idempotency key.

## Response

```json
{
  "protocolVersion": 1,
  "requestId": "uuid",
  "ok": true,
  "provider": "mac",
  "startedAt": "2026-09-03T07:30:01Z",
  "completedAt": "2026-09-03T07:30:02Z",
  "data": {},
  "mutationState": "not-applicable"
}
```

Mutation state is one of `not-applicable`, `not-started`, `committed`, or `unknown`. An `unknown` result blocks automatic fallback and requires reconciliation.

## Limits

- Maximum request body: 256 KiB.
- Maximum response body: 2 MiB.
- Default read deadline: 10 seconds.
- Default write deadline: 30 seconds.
- Maximum page size: 200 records.
- Notes bodies are truncated at a configurable safe limit, default 256 KiB.

## Version negotiation

US1 calls `/v1/capabilities` before selecting the Mac. Major protocol mismatch makes the provider unavailable. Minor capability additions are ignored unless both sides advertise them.

## State files

The Mac stores only operational state under:

```text
~/Library/Application Support/OpenClawAppleBridge/
```

Request receipts use atomic replace and bounded retention. Logs live under `~/Library/Logs/OpenClawAppleBridge/` and contain no private item bodies by default.
