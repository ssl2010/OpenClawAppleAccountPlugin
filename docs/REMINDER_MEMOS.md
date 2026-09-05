# InkBoard reminder memos

OpenClaw writes directly to iCloud Reminders; InkBoard remains an independent
read-only consumer and refreshes from its existing `任务` list polling loop.

The plugin exposes bounded list/get/create/update/complete/delete tools. Mutations
use exact stable IDs and require read-back. An unknown mutation result is fenced:
the agent must inspect before retrying because Apple may already have committed it.

`time` is always the actual occurrence/due time. `remindMinutesBefore` creates a
native CloudKit `Alarm` plus a `Date` `AlarmTrigger` at the calculated earlier time.
Urgent reminders use Apple priority 1 and always keep `flagged=false`. Normal
priority with an explicitly requested advance alarm is also supported. All-day
items reject minute-based advance alarms.

The date-alarm adapter is intentionally pinned to the CloudKit schema observed in
pyicloud 2.6.5. It submits the reminder link, alarm and trigger atomically, then
reads back both the reminder alarm ID and trigger date components. A schema or
read-back mismatch is reported as an unknown outcome and is never auto-replayed.
