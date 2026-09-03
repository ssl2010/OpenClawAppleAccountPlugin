from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from openclaw_apple_bridge.errors import BridgeError
from openclaw_apple_bridge.models import date_components, parse_rfc3339


def test_parse_rfc3339_adds_default_timezone() -> None:
    value = parse_rfc3339("2026-09-08T12:12:00")
    assert value.utcoffset().total_seconds() == 8 * 3600


def test_parse_rfc3339_rejects_bad_timestamp() -> None:
    with pytest.raises(BridgeError, match="RFC 3339"):
        parse_rfc3339("tomorrow")


def test_apple_date_components_skip_calendar_identifier() -> None:
    assert date_components([20260908, 2026, 9, 8, 12, 12, 0]) == datetime(
        2026, 9, 8, 12, 12, tzinfo=ZoneInfo("Asia/Shanghai")
    )
