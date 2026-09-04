from datetime import datetime

import pytest

from openclaw_apple_bridge.rail12306 import format_itinerary_notes


@pytest.mark.parametrize("start,end,expected", [
    ("2026-09-08T12:12:00+08:00", "2026-09-08T16:20:00+08:00", "12:12–16:20"),
    ("2026-09-08T23:30:00+08:00", "2026-09-09T06:20:00+08:00", "23:30–06:20（次日）"),
    ("2026-09-08T23:30:00+08:00", "2026-09-10T06:20:00+08:00", "23:30–06:20（第3日）"),
    ("2026-09-08T12:12:00+08:00", "2026-09-08T16:20:00+09:00", "12:12–16:20（当地时间）"),
])
def test_concise_note_times(start: str, end: str, expected: str) -> None:
    segment = {"train": "G1", "originStation": "武汉", "destinationStation": "深圳北",
               "departure": datetime.fromisoformat(start), "arrival": datetime.fromisoformat(end)}
    notes = format_itinerary_notes({"segments": [segment]}, "unused", timetable_status="resolved")
    assert notes.splitlines()[0].endswith(expected)
    assert "2026-" not in notes
    assert notes.endswith("from OpenClaw US1")


def test_midnight_fallback_marks_next_day() -> None:
    segment = {"train": "G1", "originStation": "武汉", "destinationStation": "深圳北",
               "departure": datetime.fromisoformat("2026-09-08T23:55:00+08:00")}
    notes = format_itinerary_notes({"segments": [segment]}, "unused", timetable_status="pending")
    assert "23:55–00:05（次日）（时刻表待补充）" in notes


def test_transfer_day_label_is_relative_to_journey_start() -> None:
    first = {"train": "G1", "originStation": "武汉", "destinationStation": "南京",
             "departure": datetime.fromisoformat("2026-09-08T23:00:00+08:00"),
             "arrival": datetime.fromisoformat("2026-09-09T01:00:00+08:00")}
    second = {**first, "train": "G2", "originStation": "南京", "destinationStation": "上海",
              "departure": datetime.fromisoformat("2026-09-09T06:00:00+08:00"),
              "arrival": datetime.fromisoformat("2026-09-09T08:00:00+08:00")}
    notes = format_itinerary_notes({"segments": [first, second]}, "unused", timetable_status="resolved")
    assert "06:00–08:00（次日）" in notes
