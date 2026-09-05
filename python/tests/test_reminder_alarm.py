from datetime import UTC, datetime

import pytest

from openclaw_apple_bridge.reminder_alarm import _date_components


def test_date_components_preserve_named_local_timezone() -> None:
    trigger = datetime(2026, 9, 8, 1, 30, tzinfo=UTC)
    assert _date_components(trigger, "Asia/Shanghai") == {
        "minute": 30, "timeZone": {"identifier": "Asia/Shanghai"},
        "hour": 9, "second": 0, "day": 8, "month": 9, "era": 1, "year": 2026,
    }


def test_date_components_reject_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _date_components(datetime.fromisoformat("2026-09-08T09:30:00"), "Asia/Shanghai")
