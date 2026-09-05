from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest
from pyicloud.services.calendar import EventObject

from openclaw_apple_bridge.errors import BridgeError
from openclaw_apple_bridge.icloud import ICloudProvider
from openclaw_apple_bridge.models import normalize_event, parse_rfc3339


class FakeResponse:
    def __init__(self, value: dict[str, Any]) -> None:
        self.value = value

    def json(self) -> dict[str, Any]:
        return self.value


class FakeSession:
    def __init__(self) -> None:
        self.last_json: dict[str, Any] | None = None

    def post(self, _url: str, *, params: dict[str, Any], json: dict[str, Any]) -> FakeResponse:
        assert params
        self.last_json = json
        return FakeResponse({"Event": [json.get("Event", {})]})


class FakeCalendar:
    _calendar_refresh_url = "https://example.invalid/ca/events"
    default_params: ClassVar[dict[str, str]] = {"lang": "en-us"}

    def __init__(self) -> None:
        self.session = FakeSession()

    def get_ctag(self, _calendar_id: str) -> str:
        return "ctag-1"

    def get_event_detail(self, _calendar: str, _event: str, *, as_obj: bool) -> dict[str, Any]:
        assert not as_obj
        assert self.session.last_json
        return self.session.last_json["Event"]

    def get_calendars(self, *, as_objs: bool) -> list[dict[str, Any]]:
        assert not as_objs
        return [{"guid": "cal-1", "title": "Calendar", "readOnly": False}]

    def get_events(self, _start: Any, _end: Any, *, as_objs: bool) -> list[dict[str, Any]]:
        assert not as_objs
        return [
            {
                "pGuid": "cal-1",
                "guid": "event-1",
                "title": "Trip",
                "localStartDate": [20260908, 2026, 9, 8, 12, 12, 0],
                "localEndDate": [20260908, 2026, 9, 8, 14, 0, 0],
            }
        ]


class FakeService:
    requires_2fa = False
    requires_2sa = False
    is_trusted_session = True

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.calendar = FakeCalendar()
        self.reminders = FakeReminders()


class FakeReminders:
    def __init__(self) -> None:
        self.items: dict[str, Any] = {}

    def lists(self) -> list[Any]:
        return [SimpleNamespace(id="List/tasks", title="任务", count=len(self.items), is_group=False)]

    def create(self, **kwargs: Any) -> Any:
        item = SimpleNamespace(
            id="Reminder/test", list_id=kwargs["list_id"], title=kwargs["title"],
            desc=kwargs["desc"], completed=False, deleted=False, due_date=kwargs["due_date"],
            priority=kwargs["priority"], flagged=kwargs["flagged"],
            all_day=kwargs["all_day"], time_zone=kwargs["time_zone"],
        )
        self.items[item.id] = item
        return deepcopy(item)

    def get(self, reminder_id: str) -> Any:
        return deepcopy(self.items[reminder_id])

    def update(self, reminder: Any) -> None:
        self.items[reminder.id] = deepcopy(reminder)

    def delete(self, reminder: Any) -> None:
        self.items.pop(reminder.id)

    def list_reminders(self, **_kwargs: Any) -> Any:
        return SimpleNamespace(reminders=[deepcopy(item) for item in self.items.values()])


def provider(monkeypatch: Any, tmp_path: Any) -> ICloudProvider:
    monkeypatch.setenv("ICLOUD_APPLE_ID", "test@example.invalid")
    return ICloudProvider({"sessionDirectory": str(tmp_path)}, service_factory=FakeService)


def test_lists_normalized_calendars_and_events(monkeypatch: Any, tmp_path: Any) -> None:
    client = provider(monkeypatch, tmp_path)
    assert client.list_calendars()[0]["id"] == "cal-1"
    events = client.list_events(
        {"start": "2026-09-01T00:00:00+08:00", "end": "2026-10-01T00:00:00+08:00"}
    )
    assert events[0]["eventId"] == "event-1"
    assert events[0]["start"] == "2026-09-08T12:12:00+08:00"


def test_create_preserves_notes_and_url(monkeypatch: Any, tmp_path: Any) -> None:
    client = provider(monkeypatch, tmp_path)
    result = client.create_event(
        {
            "calendarId": "cal-1",
            "title": "Trip",
            "start": "2026-09-08T12:12:00+08:00",
            "end": "2026-09-08T14:00:00+08:00",
            "notes": "marker",
            "url": "https://example.invalid/trip",
        }
    )
    assert result["committed"] is True


def test_reminder_create_maps_urgency_and_advance_notice(monkeypatch: Any, tmp_path: Any) -> None:
    alarms = []
    monkeypatch.setattr(
        "openclaw_apple_bridge.icloud.add_date_alarm",
        lambda _service, _reminder, trigger, timezone: alarms.append((trigger, timezone)),
    )
    client = provider(monkeypatch, tmp_path)
    result = client.create_reminder({
        "listId": "List/tasks", "title": "提交报告", "notes": "附数据表",
        "time": "2026-09-08T10:00:00+08:00", "urgent": True,
        "remindMinutesBefore": 30, "timezone": "Asia/Shanghai",
    })
    assert result["committed"] is True
    assert result["actualTime"] == "2026-09-08T10:00:00+08:00"
    assert result["reminderTime"] == "2026-09-08T10:00:00+08:00"
    assert result["remindMinutesBefore"] == 30
    assert alarms == [(parse_rfc3339("2026-09-08T09:30:00+08:00"), "Asia/Shanghai")]


def test_advance_notice_requires_explicit_actual_time() -> None:
    with pytest.raises(BridgeError, match="time is required"):
        ICloudProvider._reminder_schedule(
            {"remindMinutesBefore": 15},
            default_actual=parse_rfc3339("2026-09-08T10:00:00+08:00"),
        )


def test_all_day_rejects_minute_advance_notice() -> None:
    with pytest.raises(BridgeError, match="All-day"):
        ICloudProvider._reminder_schedule({
            "time": "2026-09-08T00:00:00+08:00", "allDay": True,
            "remindMinutesBefore": 15,
        })


def test_urgent_requires_actual_time() -> None:
    with pytest.raises(BridgeError, match="urgent alarm"):
        ICloudProvider._reminder_schedule({"urgent": True})


def test_real_pyicloud_date_arrays_are_minutes_not_seconds() -> None:
    event = EventObject(
        pguid="cal-1", start_date=parse_rfc3339("2026-09-08T12:12:00+08:00"),
        end_date=parse_rfc3339("2026-09-08T14:00:00+08:00"),
    )
    actual = normalize_event(event.request_data["Event"])
    assert actual["start"] == "2026-09-08T12:12:00+08:00"
    assert actual["end"] == "2026-09-08T14:00:00+08:00"


@pytest.mark.parametrize("response", [{"status": "pending"}, {"Event": [{}]}, {}])
def test_response_alone_never_proves_commit(response: dict[str, Any]) -> None:
    with pytest.raises(BridgeError, match="read-back reconciliation"):
        ICloudProvider._mutation_result("created", EventObject(pguid="cal-1"), response)


@pytest.mark.parametrize("field,value", [
    ("guid", "other"), ("pGuid", "other"), ("description", "lost notes"),
    ("title", "different"), ("location", "different"), ("url", "different"),
    ("allDay", True), ("localStartDate", [20260908, 2026, 9, 8, 13, 0, 780]),
    ("localEndDate", [20260908, 2026, 9, 8, 15, 0, 600]),
])
def test_stale_or_mismatched_readback_is_unknown(field: str, value: Any) -> None:
    event = EventObject(
        pguid="cal-1", start_date=parse_rfc3339("2026-09-08T12:12:00+08:00"),
        end_date=parse_rfc3339("2026-09-08T14:00:00+08:00"),
    )
    calendar = FakeCalendar()
    calendar.session.last_json = event.request_data
    calendar.session.last_json["Event"][field] = value
    with pytest.raises(BridgeError, match="read-back reconciliation"):
        ICloudProvider._mutation_result("updated", event, {"ok": True}, calendar, {})


def test_identity_mismatch_refuses_before_write() -> None:
    with pytest.raises(BridgeError, match="different calendar event"):
        ICloudProvider._assert_identity(
            {"calendarId": "c", "eventId": "wrong"}, {"calendarId": "c", "eventId": "e"}
        )


@pytest.mark.parametrize("reply,success", [
    ({"Event": []}, True), ({}, False), ({"status": "pending"}, False),
    ({"Event": [{}]}, False), ({"Event": [], "serviceErrors": ["denied"]}, False),
])
def test_delete_requires_exact_resource_absence(reply: dict[str, Any], success: bool) -> None:
    from types import SimpleNamespace

    class ReadResponse(FakeResponse):
        def raise_for_status(self) -> None:
            pass

    event = EventObject(pguid="cal-1", guid="event-1")

    def get(url: str, *, params: dict[str, Any]) -> ReadResponse:
        assert url == "https://example.invalid/detail/cal-1/event-1"
        assert params["dsid"] == "test"
        return ReadResponse(reply)

    calendar = SimpleNamespace(
        params={}, _calendar_event_detail_url="https://example.invalid/detail",
        session=SimpleNamespace(
            get=get, service=SimpleNamespace(data={"dsInfo": {"dsid": "test"}})
        ),
    )
    if success:
        assert ICloudProvider._mutation_result(
            "deleted", event, {"ack": True}, calendar, {}
        )["committed"] is True
    else:
        with pytest.raises(BridgeError, match="read-back reconciliation"):
            ICloudProvider._mutation_result("deleted", event, {"ack": True}, calendar, {})


@pytest.mark.parametrize("code,reason,collections,events,success", [
    (404, "Not Found", [{"guid": "cal-1"}], [], True),
    (403, "Not Authorized", [{"guid": "cal-1"}], [], False),
    (401, "Not Found", [{"guid": "cal-1"}], [], False),
    (404, "Not Authorized", [{"guid": "cal-1"}], [], False),
    (404, "Not Found", [{"guid": "wrong-calendar"}], [], False),
    (404, "Not Found", [], [], False),
    (404, "Not Found", [{"guid": "cal-1"}], [{"guid": "event-1", "pGuid": "cal-1"}], False),
    (404, "Not Found", [{"guid": "cal-1"}], [{}], False),
    (404, "Not Found", [{"guid": "cal-1"}], None, False),
])
def test_delete_404_needs_readable_same_calendar_and_absent_guid(
    code: int, reason: str, collections: Any, events: Any, success: bool,
) -> None:
    from types import SimpleNamespace

    from pyicloud.exceptions import PyiCloudAPIResponseException

    event = EventObject(
        pguid="cal-1", guid="event-1",
        start_date=parse_rfc3339("2026-09-08T12:12:00+08:00"),
        end_date=parse_rfc3339("2026-09-08T14:00:00+08:00"),
    )

    def get(url: str, *, params: dict[str, Any]) -> None:
        assert url == "https://example.invalid/detail/cal-1/event-1"
        raise PyiCloudAPIResponseException(reason, code)

    def get_events(start: Any, end: Any, *, as_objs: bool) -> Any:
        assert start.isoformat() == "2026-09-07T12:12:00+08:00"
        assert end.isoformat() == "2026-09-09T14:00:00+08:00"
        assert not as_objs
        return events

    calendar = SimpleNamespace(
        params={}, _calendar_event_detail_url="https://example.invalid/detail",
        session=SimpleNamespace(
            get=get, service=SimpleNamespace(data={"dsInfo": {"dsid": "test"}})
        ),
        get_calendars=lambda **kwargs: collections, get_events=get_events,
    )
    if success:
        assert ICloudProvider._mutation_result(
            "deleted", event, {"ack": True}, calendar, {}
        )["committed"] is True
    else:
        with pytest.raises(BridgeError, match="read-back reconciliation"):
            ICloudProvider._mutation_result("deleted", event, {"ack": True}, calendar, {})
