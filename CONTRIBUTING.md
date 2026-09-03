# Contributing

This repository is currently a private, owner-operated project.

Before proposing code:

1. Do not include credentials, sessions, private Apple data, or unsanitized fixtures.
2. Keep TypeScript tool contracts separate from Python Apple adapters.
3. Add tests for every response-normalization or mutation behavior.
4. Document any newly observed private Apple endpoint or schema field without including tokens or personal data.
5. Run the TypeScript, Python, contract, and secret checks relevant to the change.

Changes that add write, delete, Find My, account-security, or device-control capabilities require an explicit threat-model update and owner approval.
