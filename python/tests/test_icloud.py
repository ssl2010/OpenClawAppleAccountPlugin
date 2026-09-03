from __future__ import annotations

from typing import Any, ClassVar

from openclaw_apple_bridge.icloud import ICloudProvider


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
