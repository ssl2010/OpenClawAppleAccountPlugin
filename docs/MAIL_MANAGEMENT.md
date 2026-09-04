# Gmail → Feishu mail management

## Architecture and boundaries

`mail_digest.py` runs in the existing Python bridge package. A systemd minute timer
checks configurable briefing slots; scheduling, message selection, source attribution,
delivery accounting and recoverable cleanup are deterministic. The `mail-management`
skill explains how the interactive assistant should inspect/configure it. A separate
OpenClaw `mail-brief` agent summarizes bounded data using an already configured model.
Only the read-only `session_status` tool is exposed to it for runtime compatibility;
no execution, file, mail, browser or messaging tools are available.

This is server-side OpenClaw work, not a Codex-desktop reminder. The Mac need not stay on.

## Configuration

Private config: `~/.config/openclaw-mail-management/config.json`, mode 0600.
Start from `deploy/mail-management.config.example.json`; replace every placeholder.
The reusable summarizer instructions are in `deploy/mail-brief/AGENTS.md`.
Create a dedicated `mail-brief` agent/workspace using the installed OpenClaw CLI,
copy those instructions to its workspace, and configure its tools with profile
`minimal`, allow only `session_status`, and deny runtime, filesystem, web,
messaging and Apple-account tools. Set its skills list empty. Select a working
provider/model already authorized on the host. Verify its actual runtime tools
before enabling the timer: prompt instructions alone are not a security boundary.

- `account`: exact aggregator Gmail account; upstream source mailboxes are never mutated.
- `timezone`: Asia/Shanghai initially.
- `times`: initially 08:30, 11:30, 14:30, 17:30, 21:30, every calendar day.
- `sources`: exact original-account addresses mapped to MSN邮箱、武大邮箱、公司邮箱、谷歌邮箱.
  Do not confuse a differently spelled source Gmail address with the aggregator.
- `feishuTarget`: one explicit owner destination, never a wildcard/broadcast.
- `cleanup.enabled` and `cleanup.approved`: both must be true; default false.
- `cleanup.scope`: inbox, or received (also includes archived received messages).
- `cleanup.maxDelete`: safety ceiling, initially 100; excess requires review.
- `holidays` / `extraWorkdays`: ISO date overrides. Otherwise workdays mean Monday–Friday,
  not a claim to implement the official Chinese holiday/makeup calendar.
- `maxMessages`: bounded paginated query limit, initially 500.

Change `times` in the JSON file to configure the schedule; no timer regeneration is
needed. Deploy the included service with the correct host Node executable PATH.

## Behavior

The first live digest starts at local midnight on the activation day. Subsequent
digests cover `[last confirmed watermark, current snapshot cutoff)`, regardless of
read/unread status. Spam, Trash, drafts and sent-only messages are excluded. Archived
received mail is still summarized. Each Gmail message is processed separately (not
one arbitrary message per thread); pagination and timestamp checks prevent omission.
After downtime, one catch-up digest covers the unsent interval rather than replaying
every missed clock slot. No-new-mail periods still produce a concise notice.

Forwarded sources are recognized from exact header evidence (Resent-From,
Delivered-To, X-Forwarded-For, original recipient), not sender-domain guesses. Unknown
or contradictory forwarding evidence is labeled 来源待确认. Plain direct mail is 本地邮箱.
Only bounded subject/body text is sent to the summarizer; attachments are not executed
or fetched. If summarization fails, list all subjects and explicitly label degraded
output. Long briefings split into bounded Feishu messages without dropping items.

On the first confirmed digest of a day, an approved cleanup policy selects only the
previous working day's received messages within exact local-midnight boundaries.
The same working day is cleaned at most once, including across weekends. Default
cleanup is OFF until the user confirms account, folder scope and workday behavior.
Cleanup is TRASH only, never permanent deletion. It does not touch upstream accounts,
calendar events or today's messages. The title of a message does not authorize deletion.

## Reliability and operations

State is protected by a process lock and atomic fsync writes. A write-ahead outbox
records every receipt; uncertain delivery fences replay and blocks deletion. Message
IDs and per-day cleanup records are audited; bodies are not stored in worker state.
OpenClaw's own agent transcripts may contain the bounded summarized inputs.

`cleanupPending` means inspect that exact Gmail message and audit before clearing the
fence. Never convert uncertain delivery/cleanup into success by resetting state.
Failed runs emit one bounded Feishu error notice per error type/day when possible.

Commands (using the project venv):

```sh
python -m openclaw_apple_bridge.mail_digest --preview
python -m openclaw_apple_bridge.mail_digest --test
systemctl --user status openclaw-mail-digest.timer
journalctl --user -u openclaw-mail-digest.service -n 20 --no-pager
```

Preview never sends or deletes. Test sends a clearly labeled digest but never deletes
or advances the production watermark. Normal invocation checks due slots before acting.

Tests cover all source mappings, local/body-spoof cases, ambiguous headers, day/window
boundaries, workday overrides, full pagination, overflow/loop refusal, excluded folders,
empty/large digests, degraded summary, delivery fencing, cleanup approval/limits and
no repeat after successful delivery.

## Deployment validation (2026-09-04)

136 Python tests passed (30 mail-management tests); ruff, source mypy and skill
validation passed. A real forwarded university message was correctly attributed and
summarized with its stated deadline. Both a labeled test briefing and the initial
live catch-up briefing received confirmed Feishu receipts. Repeated minute checks
returned already-sent without duplicate live delivery. The summary agent's actual
runtime tool inventory contained only session_status. Other source mappings were
verified with synthetic headers, not claims of accessing those upstream accounts.

Cleanup remains disabled pending explicit confirmation of folder/workday scope.
No business mail was deleted during this feature's validation.
