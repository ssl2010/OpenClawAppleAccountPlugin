---
name: apple-reminder-memos
description: Create and manage iCloud Reminders from Feishu so they appear on the InkBoard e-ink dashboard. Use for reminder memos with a title, notes, actual time, urgency, and native Apple advance-notice timing.
---

# Apple reminder memos

Use the deterministic `apple_reminders_*` tools. The InkBoard reads the iCloud
Reminder list named `任务` every two minutes; do not write directly to the display
or its Raspberry Pi.

Before a create or update, resolve relative dates in `Asia/Shanghai`, then show the
owner one compact confirmation containing the list, title, notes, actual time,
urgent state and advance minutes. Ask only for a genuinely missing field. A title
is required; notes, time, urgent and advance notice are optional. Default list is
the unique list titled `任务`, timezone is `Asia/Shanghai`, urgent is false, and
advance is 0 minutes.

Urgent means Apple priority `high` but never sets the flag. The reminder due time
is always the actual occurrence time. When urgent is true, or an advance value was
explicitly requested, the plugin creates a native Apple date alarm at occurrence
time minus the advance. Do not emulate advance notice by changing the due time or
creating a second visible reminder.

After a mutation, require `committed: true` from exact Apple read-back. If the
outcome is unknown, do not retry automatically because a reminder may already
exist. List matching reminders and ask the owner to reconcile. Completion and
deletion require an exact reminder ID; deletion also requires explicit confirmation.

Read [references/fields.md](references/fields.md) when translating a natural-language
request, handling an ambiguous time, or explaining alarm behavior.
