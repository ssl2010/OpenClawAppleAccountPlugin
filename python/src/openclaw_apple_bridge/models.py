from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .errors import BridgeError


def parse_rfc3339(value: str, *, default_timezone: str = "Asia/Shanghai") -> datetime:
    text = value.strip().replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise BridgeError("INVALID_REQUEST", "Timestamp must be RFC 3339.") from exc
    if result.tzinfo is None:
        result = result.replace(tzinfo=ZoneInfo(default_timezone))
    return result


def date_components(value: Any) -> datetime | None:
    timezone = ZoneInfo("Asia/Shanghai")
    if isinstance(value, datetime):
        return value
    if isinstance(value, dict):
        try:
            return datetime(
                int(value["year"]),
                int(value["month"]),
                int(value["day"]),
                int(value.get("hour", 0)),
                int(value.get("minute", 0)),
                int(value.get("second", 0)),
                tzinfo=timezone,
            )
        except (KeyError, TypeError, ValueError):
            return None
    if isinstance(value, list):
        try:
            parts = [int(part) for part in value]
            if len(parts) >= 7 and parts[0] > 9999:
                parts = parts[1:]
            if len(parts) >= 6:
                return datetime(
                    parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], tzinfo=timezone
                )
            if len(parts) >= 3:
                return datetime(parts[0], parts[1], parts[2], tzinfo=timezone)
        except (TypeError, ValueError):
            return None
    return None


def normalize_calendar(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(raw.get("guid") or ""),
        "title": str(raw.get("title") or "Untitled calendar"),
        "readOnly": bool(raw.get("readOnly", False)),
        "enabled": bool(raw.get("enabled", True)),
        "isDefault": bool(raw.get("isDefault", False)),
    }


def normalize_event(raw: dict[str, Any]) -> dict[str, Any]:
    start = date_components(raw.get("localStartDate") or raw.get("startDate"))
    end = date_components(raw.get("localEndDate") or raw.get("endDate"))
    return {
        "calendarId": str(raw.get("pGuid") or raw.get("pguid") or ""),
        "eventId": str(raw.get("guid") or ""),
        "etag": str(raw.get("etag") or ""),
        "title": str(raw.get("title") or "Untitled event"),
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "timezone": str(raw.get("tz") or ""),
        "allDay": bool(raw.get("allDay", False)),
        "location": str(raw.get("location") or ""),
        "url": str(raw.get("url") or ""),
        "notes": str(raw.get("description") or raw.get("notes") or ""),
        "recurrenceMaster": bool(raw.get("recurrenceMaster", False)),
        "recurrenceException": bool(raw.get("recurrenceException", False)),
    }
