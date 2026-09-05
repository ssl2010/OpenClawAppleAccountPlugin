"""Version-pinned CloudKit date alarms for pyicloud Reminders 2.6.x."""
from __future__ import annotations

import base64
import json
import time
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pyicloud.common.cloudkit import CKModifyOperation
from pyicloud.services.reminders._constants import _REMINDERS_ZONE_REQ
from pyicloud.services.reminders._protocol import (
    _as_raw_id,
    _as_record_name,
    _generate_resolution_token_map,
)
from pyicloud.services.reminders._support import (
    _assert_modify_success,
    _refresh_record_change_tag,
)


def add_date_alarm(service: Any, reminder: Any, trigger_at: datetime, timezone: str) -> str:
    """Attach one native Apple Date AlarmTrigger and verify its exact payload."""
    if trigger_at.tzinfo is None:
        raise ValueError("Alarm trigger must be timezone-aware")
    components = _date_components(trigger_at, timezone)
    alarm_uuid = str(uuid.uuid4()).upper()
    trigger_uuid = str(uuid.uuid4()).upper()
    alarm_name = f"Alarm/{alarm_uuid}"
    trigger_name = f"AlarmTrigger/{trigger_uuid}"
    reminder_name = _as_record_name(reminder.id, "Reminder")
    existing = [_as_raw_id(value, "Alarm") for value in reminder.alarm_ids]
    existing.append(alarm_uuid)
    now_ms = int(time.time() * 1000)
    record = service._writes._write_record
    reminder_op = CKModifyOperation(
        operationType="update",
        record=record(
            record_name=reminder_name, record_type="Reminder",
            record_change_tag=reminder.record_change_tag,
            fields={
                "AlarmIDs": {"type": "STRING_LIST", "value": existing},
                "ResolutionTokenMap": {
                    "type": "STRING",
                    "value": _generate_resolution_token_map(["alarmIDs", "lastModifiedDate"]),
                },
                "LastModifiedDate": {"type": "TIMESTAMP", "value": now_ms},
            },
        ),
    )
    alarm_op = CKModifyOperation(
        operationType="create",
        record=record(
            record_name=alarm_name, record_type="Alarm", parent_record_name=reminder_name,
            fields={
                "AlarmUID": {"type": "STRING", "value": alarm_uuid},
                "Deleted": {"type": "INT64", "value": 0},
                "Imported": {"type": "INT64", "value": 0},
                "Reminder": {"type": "REFERENCE", "value": {
                    "recordName": reminder_name, "action": "VALIDATE",
                }},
                "TriggerID": {"type": "STRING", "value": trigger_uuid},
                "DueDateResolutionTokenAsNonce": {
                    "type": "DOUBLE", "value": 100_000_000_000 + time.time() - 978_307_200,
                },
            },
        ),
    )
    trigger_op = CKModifyOperation(
        operationType="create",
        record=record(
            record_name=trigger_name, record_type="AlarmTrigger", parent_record_name=alarm_name,
            fields={
                "DateComponentsData": {
                    "type": "BYTES",
                    "value": _encoded_date_components(components),
                },
                "Type": {"type": "STRING", "value": "Date"},
                "Alarm": {"type": "REFERENCE", "value": {
                    "recordName": alarm_name, "action": "VALIDATE",
                }},
            },
        ),
    )
    response = service._raw.modify(
        operations=[reminder_op, alarm_op, trigger_op],
        zone_id=_REMINDERS_ZONE_REQ, atomic=True,
    )
    _assert_modify_success(response, "Add date reminder alarm")
    reminder.alarm_ids = existing
    _refresh_record_change_tag(response, reminder, reminder_name)

    fresh = service.get(reminder.id)
    if alarm_uuid not in [_as_raw_id(value, "Alarm") for value in fresh.alarm_ids]:
        raise ValueError("Reminder alarm link was not visible after write")
    lookup = service._raw.lookup(record_names=[trigger_name], zone_id=_REMINDERS_ZONE_REQ)
    records = [item for item in lookup.records if getattr(item, "recordName", None) == trigger_name]
    if len(records) != 1 or records[0].fields.get_value("Type") != "Date":
        raise ValueError("Date alarm trigger was not visible after write")
    actual = json.loads(bytes(records[0].fields.get_value("DateComponentsData")))
    if any(actual.get(key) != value for key, value in components.items()):
        raise ValueError("Date alarm trigger differs after write")
    return alarm_name


def _date_components(trigger_at: datetime, timezone: str) -> dict[str, Any]:
    if trigger_at.tzinfo is None:
        raise ValueError("Alarm trigger must be timezone-aware")
    local = trigger_at.astimezone(ZoneInfo(timezone))
    return {
        "minute": local.minute, "timeZone": {"identifier": timezone},
        "hour": local.hour, "second": local.second, "day": local.day,
        "month": local.month, "era": 1, "year": local.year,
    }


def _encoded_date_components(components: dict[str, Any]) -> str:
    raw = json.dumps(components, separators=(",", ":")).encode()
    return base64.b64encode(raw).decode("ascii")
