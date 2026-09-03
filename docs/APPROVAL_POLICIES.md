# Approval policies

## Interactive writes

All mutation tools are optional and hidden until explicitly allowlisted. A `before_tool_call` hook requests an OpenClaw plugin approval after the model selects a tool and before execution.

Approval preview includes:

- exact action and provider;
- target calendar/list and item ID;
- changed fields and recurrence scope;
- whether data will be deleted;
- idempotency key and request expiry.

## Durable pre-approval

OpenClaw's generic `allow-always` decision is not itself durable authorization. The plugin owns a policy record and revalidates it for every call.

Required fields:

```json
{
  "policyVersion": 1,
  "id": "uuid",
  "enabled": true,
  "agentId": "main",
  "automationId": "exact-openclaw-automation-id",
  "channel": "feishu",
  "requesterId": "exact-allowlisted-open-id",
  "actions": ["calendar.create"],
  "resourceIds": ["calendar-stable-id"],
  "fieldRules": {},
  "maxWritesPerRun": 10,
  "maxWritesPer24Hours": 50,
  "expiresAt": "RFC3339",
  "createdBy": "operator",
  "createdAt": "RFC3339"
}
```

Default expiry is 30 days. Policies without an exact automation ID, explicit actions, resource IDs, quotas, or expiry are invalid.

## Evaluation order

1. Mutation tool must be visible through OpenClaw tool policy.
2. Requester and channel must match the owner boundary.
3. Parameters are schema-validated and exact target/version resolved.
4. A live policy is loaded by ID.
5. Agent, automation, requester, action, resource, fields, quota, and expiry all match.
6. The live OpenClaw automation record is revalidated.
7. An audit reservation is recorded atomically.
8. One provider is selected and the mutation is dispatched.
9. Receipt commits or releases the reservation according to the outcome.

Any failure falls back to interactive approval when available; otherwise it denies.

## Revocation and audit

- Revocation is immediate and does not wait for Gateway restart.
- In-flight work that has not crossed the provider dispatch boundary is cancelled.
- Audit records retain policy ID, operation, resource ID, provider, timestamps, request ID, decision, and mutation outcome.
- Audit records do not retain note bodies, event/reminder descriptions, credentials, or raw upstream responses.

## Initial defaults

- 10 writes per automation run.
- 50 writes per rolling 24 hours.
- 30-day maximum default lifetime.
- Delete and soft-cancel are separate actions; approval for one never grants the other.
- Recurring-series mutations require a distinct action from single-occurrence mutations.
