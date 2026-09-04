from __future__ import annotations

from typing import Any

from openclaw_apple_bridge.timetable import RailwayTimetable


class FakeResponse:
    def __init__(self, *, text: str = "", payload: dict[str, Any] | None = None) -> None:
        self.text = text
        self.payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeSession:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}

    def get(self, url: str, **_kwargs: Any) -> FakeResponse:
        if url.endswith("station_name.js"):
            stations = "".join(f"@x|站{i}|X{i:03}|x|x|0|" for i in range(101))
            stations += "@wh|武汉|WHN|wuhan|wh|0|@szb|深圳北|IOQ|shenzhenbei|szb|0|"
            return FakeResponse(text=stations)
        if url.endswith("/init"):
            return FakeResponse(text="ok")
        row = [""] * 14
        row[3], row[6], row[7] = "G395", "WHN", "IOQ"
        row[8], row[9], row[10] = "12:12", "17:45", "05:33"
        return FakeResponse(payload={"data": {"result": ["|".join(row)]}})


def test_lookup_returns_official_arrival() -> None:
    result = RailwayTimetable(session=FakeSession()).lookup(
        {
            "travelDate": "2026-09-08",
            "trainNumber": "G395",
            "originStation": "武汉",
            "destinationStation": "深圳北",
        }
    )
    assert result["arrival"] == "2026-09-08T17:45:00+08:00"
    assert result["durationMinutes"] == 333
