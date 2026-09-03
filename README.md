# OpenClaw Apple Account Plugin

A security-focused OpenClaw tool plugin for accessing personal Apple account data through a Linux-hosted OpenClaw Gateway, using pyiCloud first and an optional legacy macOS bridge only if evidence shows it is needed.

> Project status: architecture and build scaffold. No Apple account data is accessed yet.

## Goals

- Read, create, update, and cancel calendar events.
- Read, create, update, complete, and delete reminders.
- Investigate reliable read-only Apple Notes access without claiming unsupported behavior.
- Later evaluate contacts and narrowly scoped iCloud Drive access.
- Reuse the proven authentication and CloudKit experience from the private `InkBoard` project.

## Architecture

The plugin uses two initial layers and one conditional extension:

1. A TypeScript OpenClaw tool plugin owns typed tool contracts, permission boundaries, validation, and model-visible results.
2. A private Python bridge on US1 is the initial and preferred provider. It owns pyiCloud authentication, session reuse, response normalization, and Apple network calls.
3. A lightweight bridge on the legacy Mac is a deferred, optional provider for capabilities or reliability gaps that pyiCloud cannot satisfy.

Phase 1 deliberately runs without the Mac provider so pyiCloud defects cannot be hidden by fallback. Mac development starts only after the pyiCloud stabilization gate and an explicit evidence-based decision. Mutations never fail over after an ambiguous result.

See [Requirements](docs/REQUIREMENTS.md), [traceability](docs/TRACEABILITY.md), [tool contracts](docs/TOOL_CONTRACTS.md), [Architecture](docs/ARCHITECTURE.md), [pyiCloud stabilization gate](docs/PYICLOUD_STABILIZATION.md), [Approval policies](docs/APPROVAL_POLICIES.md), [conditional Mac bridge plan](docs/MAC_BRIDGE.md), [Legacy Mac audit](docs/LEGACY_MAC_AUDIT.md), [Phase 1 execution](docs/PHASE1_EXECUTION.md), [operations](docs/OPERATIONS.md), [Security](SECURITY.md), and [Roadmap](docs/ROADMAP.md).

## Repository layout

```text
src/                         OpenClaw TypeScript plugin
python/                      pyiCloud bridge package
skills/apple-account/        Agent workflow and safety guidance
docs/                        Product, architecture, decisions, and roadmap
openclaw.plugin.json         OpenClaw manifest
```

## Current scaffold

The only registered tool is `apple_account_capabilities`. It reports the planned surface and never reads credentials. Runtime tools will be introduced one capability at a time, starting with account status and calendar reads.

## Development prerequisites

- Node.js 24.15 or newer
- OpenClaw 2026.8.2 or newer
- Python 3.11 or newer

Build commands are documented now and will become executable after dependencies are installed:

```bash
npm install
npm run check
python3 -m venv .venv
.venv/bin/pip install -e './python[dev]'
.venv/bin/pytest python/tests
```

## Credential policy

Never commit Apple IDs, passwords, 2FA codes, cookies, session files, raw account responses, or production data fixtures. Authentication will be an explicit operator setup flow and runtime sessions will live outside the repository.

## License

Licensed under the [Apache License 2.0](LICENSE).
