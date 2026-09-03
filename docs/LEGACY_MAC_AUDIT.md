# Legacy Mac audit and old bridge retirement

Audit date: 2026-09-03

## Host inventory

- Hostname: `ShileideAir`
- Model: MacBook Air (`MacBookAir6,2`, 2013 generation)
- CPU: dual-core Intel Core i5, `x86_64`
- Memory: 4 GB
- macOS: 11.7.11 (20G1443)
- Xcode Command Line Tools: installed
- Homebrew: 5.1.0
- Homebrew Python: 3.14.3
- Apple/system Python: 2.7.16; Command Line Tools also provide Python 3.8
- SSH remote login: available on the local network

The hardware is constrained but sufficient for a small EventKit collector, an outbound connection, and a lightweight status surface. It should not run OpenClaw, a browser automation stack, containers, or model inference.

## Retired services

The following user LaunchAgents belonged to the obsolete e-ink Calendar/Reminders bridge and status dashboard:

- `com.calendar.sync-reverse-ssh`
- `com.calendar.sync-runner`
- `com.calendar.sync-tunnel`
- `com.shileisun.statustool`
- `com.shileisun.statustool.app`

They were booted out of the `gui/501` launchd domain and moved out of `~/Library/LaunchAgents` to:

```text
~/Library/LaunchAgents.retired/20260903-150603-old-eink-bridge/
```

The StatusTool Python process was terminated and its loopback listener on port 18999 was verified closed. No matching launchd jobs or old bridge processes remained after retirement.

The following source directories were intentionally preserved for reference:

```text
~/work/calendar
~/work/statustool
```

The unrelated `com.codex.keepawake` job remains active because a future always-on bridge may need the same power behavior.

## Why the old bridge was no longer healthy

- Its tunnel targets referenced the reinstalled `106.54.13.11` host with a stale SSH host key.
- The Calendar sync runner continued to produce local snapshots but could no longer reach its former loopback tunnel endpoint.
- The status backend remained available locally but reported an obsolete pipeline.

No stale host key was automatically replaced because host-key changes require independent verification.

## Proven design patterns worth reusing

### Native data access

- A small Swift binary linked directly to EventKit successfully read Calendar and Reminders.
- A JXA path existed as a fallback and permission diagnostic.
- Access ran in the logged-in GUI user context so macOS TCC permissions applied correctly.

### Launch and recovery

- User LaunchAgents used `RunAtLoad` for login recovery.
- Long-lived tunnel/status jobs used `KeepAlive`.
- Periodic collection used `StartInterval=300`, avoiding a permanently busy collector.
- A separate keep-awake service prevented a closed or idle machine from silently stopping the pipeline.

### State and observability

- Runtime state was persisted independently from generated snapshots.
- Event, reminder, and combined snapshot outputs were separate and inspectable.
- A loopback-only status service exposed a concise dashboard.
- A tiny native macOS shell displayed status without requiring a modern framework.
- stdout and stderr had dedicated rotating-friendly paths.

### Concurrency and correctness

- A lock directory prevented overlapping periodic sync runs.
- Sequence/batch identifiers made progress visible and reduced duplicate processing.
- Local snapshot creation continued even when transport failed, which preserved diagnostic evidence.

## Patterns to improve in the new bridge

- Replace fixed remote host keys and endpoints with provisioned, verified configuration.
- Separate provider health from last successful data collection.
- Use structured error codes instead of inferring state from log text.
- Use atomic state writes and bounded retention.
- Advertise capabilities and TCC permission status explicitly.
- Add signed request IDs, deadlines, idempotency keys, and mutation reconciliation.
- Do not run duplicate tunnel mechanisms simultaneously.
- Make the dashboard report Mac provider, pyiCloud fallback, and effective routing separately.
