# Security policy

## Threat model

This plugin handles highly sensitive personal data through private Apple web interfaces. Its primary risks are credential leakage, prompt injection from account content, excessive tool authority, accidental duplicate writes, upstream API drift, and session theft from the public US1 host.

## Mandatory controls

- Apple credentials and 2FA codes never enter model prompts, tool results, command arguments, source control, or normal logs.
- Passwords are provided only to an operator-owned authentication process.
- Session files live outside the repository in a `0700` directory; files use `0600`.
- Plugin config references secret locations rather than containing secret values.
- Read and mutation tools are separately allowlisted.
- Account content is treated as untrusted input and cannot override system or skill instructions.
- Every mutation validates an exact target and uses an idempotency key.
- Destructive or security-sensitive Apple device actions are not registered.
- Unknown upstream schemas fail closed, especially for writes.
- Authentication retries are bounded to prevent 2FA spam and Apple account lockouts.

## Logging and diagnostics

Never log:

- Apple ID passwords or 2FA codes.
- Cookies, session tokens, trust tokens, `scnt`, session IDs, or authentication headers.
- Raw bootstrap/account payloads.
- Full Notes bodies or private event/reminder content by default.

Diagnostic bundles must use synthetic or explicitly sanitized fixtures.

## Dependency policy

- Pin production dependencies to tested ranges and review updates before deployment.
- Treat pyiCloud and Apple response data as untrusted.
- Run tests and secret scanning before release.
- Keep this repository private until credential handling and package contents are reviewed.

## Reporting

Do not open a public issue containing account data, credentials, session artifacts, or raw Apple responses. Report security concerns privately to the repository owner.
