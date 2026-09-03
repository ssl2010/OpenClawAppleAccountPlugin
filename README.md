# OpenClaw Apple Account Plugin

A security-focused OpenClaw tool plugin for accessing personal Apple account data through a Linux-hosted OpenClaw Gateway and an optional legacy macOS bridge.

> Project status: architecture and build scaffold. No Apple account data is accessed yet.

## Goals

- Read, create, update, and cancel calendar events.
- Read, create, update, complete, and delete reminders.
- Investigate reliable read-only Apple Notes access without claiming unsupported behavior.
- Later evaluate contacts and narrowly scoped iCloud Drive access.
- Reuse the proven authentication and CloudKit experience from the private `InkBoard` project.

## Architecture

The plugin uses three intentionally separate layers:

1. A TypeScript OpenClaw tool plugin owns typed tool contracts, permission boundaries, validation, and model-visible results.
2. A lightweight bridge on an always-on Mac is the preferred provider when healthy and accesses native Apple applications without requiring OpenClaw on that Mac.
3. A private Python bridge on US1 owns pyiCloud authentication, session reuse, response normalization, and fallback network calls.

Provider routing is capability-aware. The Mac is preferred while online; pyiCloud is used only for capabilities that have a tested fallback. Mutations never fail over after an ambiguous result.

See [Architecture](docs/ARCHITECTURE.md), [Mac bridge plan](docs/MAC_BRIDGE.md), [Product scope](docs/PRODUCT_SCOPE.md), [Security](SECURITY.md), and [Roadmap](docs/ROADMAP.md).

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
