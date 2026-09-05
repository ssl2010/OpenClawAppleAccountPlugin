# Reminder fields and decisions

- `listId`: discover with `apple_reminders_list_lists`; choose title `任务` only
  when it is unique.
- `title`: required, 1–500 characters.
- `notes`: optional user text, stored without hidden markers.
- `time`: actual occurrence time as RFC 3339. Preserve the user's timezone when
  given; otherwise use Asia/Shanghai. Never silently invent a date for “几点”.
- `urgent`: high Apple priority (`1`) when true, no priority (`0`) when false;
  `flagged` remains false in both cases.
- `remindMinutesBefore`: 0–10080. It controls a native Apple Date AlarmTrigger,
  while `time` remains the occurrence/due time. Minute advance is invalid for an
  all-day reminder.
- `allDay`: use only when the user explicitly asks for an all-day reminder. It
  cannot carry minute-based advance notice.

Examples of accepted advance values include 0, 5, 10, 15, 30, 60, 1440, and any
other integer within the supported range. Do not restrict the user to a preset.

If the user says “紧急” without an advance value, use zero-minute native alarm at
the occurrence time. If the user requests an advance without saying “紧急”, keep
normal priority and still create the requested native alarm.
