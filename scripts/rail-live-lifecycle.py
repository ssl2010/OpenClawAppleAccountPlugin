"""Explicit opt-in temporary calendar write/read/delete smoke test."""
import json
import sys
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from openclaw_apple_bridge.icloud import ICloudProvider
from openclaw_apple_bridge.rail12306_worker import _calendar_id, _provider_config

if "--apply" not in sys.argv:
    raise SystemExit("Explicit --apply required: creates, updates and deletes one temporary event.")
provider = ICloudProvider(_provider_config())
calendar = _calendar_id(provider)
event_id = str(uuid4())
start = datetime.now(ZoneInfo("Asia/Shanghai")).replace(second=0, microsecond=0) + timedelta(hours=2)
payload = {"calendarId": calendar, "eventId": event_id, "title": "OpenClaw 临时自检（完成后删除）", "start": start.isoformat(), "end": (start + timedelta(minutes=10)).isoformat(), "notes": "Temporary safety lifecycle test", "timezone": "Asia/Shanghai"}
print("TARGET", calendar, event_id, flush=True)
print("CREATE", json.dumps(provider.create_event(payload)), flush=True)
print("UPDATE", json.dumps(provider.update_event({**payload, "notes": "Verified temporary safety lifecycle test"})), flush=True)
print("DELETE", json.dumps(provider.delete_event({"calendarId": calendar, "eventId": event_id})), flush=True)
