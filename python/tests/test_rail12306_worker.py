from __future__ import annotations

from typing import Any

from openclaw_apple_bridge.errors import BridgeError
from openclaw_apple_bridge.rail12306_worker import apply_plan, process_message


class FakeProvider:
    def __init__(self, existing: list[dict[str, Any]] | None = None) -> None:
        self.existing = existing or []
        self.created: list[dict[str, Any]] = []
        self.updated: list[dict[str, Any]] = []
        self.deleted: list[dict[str, Any]] = []

    def list_calendars(self) -> list[dict[str, Any]]:
        return [{"id": "cal-1", "readOnly": False, "enabled": True, "isDefault": True}]

    def list_events(self, _params: dict[str, Any]) -> list[dict[str, Any]]:
        return self.existing

    def create_event(self, params: dict[str, Any]) -> dict[str, Any]:
        self.created.append(params)
        return {"action": "created", "committed": True}

    def update_event(self, params: dict[str, Any]) -> dict[str, Any]:
        self.updated.append(params)
        return {"action": "updated", "committed": True}

    def delete_event(self, params: dict[str, Any]) -> dict[str, Any]:
        self.deleted.append(params)
        return {"action": "deleted", "committed": True}


class FakeTimetable:
    def lookup(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            **params,
            "departure": "2026-09-08T12:12:00+08:00",
            "arrival": "2026-09-08T17:45:00+08:00",
        }


class FailingTimetable:
    def lookup(self, _params: dict[str, Any]) -> dict[str, Any]:
        raise BridgeError("TIMETABLE_UNAVAILABLE", "test failure", retryable=True)


def purchase_message() -> dict[str, Any]:
    return {
        "body": '发件人:"12306@rails.com.cn" <12306@rails.com.cn>\n订单号码 AB12345678。测试旅客，2026年09月08日12:12开，武汉站-深圳北站，G395次列车。',
        "headers": {
            "from": "Trusted <trusted@example.com>",
            "subject": "网上购票系统-用户支付通知",
        },
        "message": {"id": "mail-1"},
    }


def test_process_message_dry_run(monkeypatch: Any) -> None:
    monkeypatch.setenv("RAIL12306_TRUSTED_FORWARDERS", "trusted@example.com")
    result = process_message(
        purchase_message(), FakeProvider(), apply=False, timetable=FakeTimetable()  # type: ignore[arg-type]
    )
    assert result["outcomes"] == [{"action": "would-create"}]
    assert result["timetableFailures"] == []


def test_timetable_failure_creates_ten_minute_fallback(monkeypatch: Any) -> None:
    monkeypatch.setenv("RAIL12306_TRUSTED_FORWARDERS", "trusted@example.com")
    provider = FakeProvider()
    result = process_message(
        purchase_message(), provider, apply=True, timetable=FailingTimetable()  # type: ignore[arg-type]
    )
    assert result["timetableFailures"][0]["error"] == "TIMETABLE_UNAVAILABLE"
    event = provider.created[0]
    assert event["start"] == "2026-09-08T12:12:00+08:00"
    assert event["end"] == "2026-09-08T12:22:00+08:00"
    assert "时刻表待补充" in event["notes"]


def test_apply_plan_is_idempotent_update() -> None:
    plan = {
        "operation": "upsert",
        "lookup": {"marker": "[OpenClaw:12306 order=AB passenger=abc]", "passengerKey": "abc"},
        "event": {
            "title": "火车行程：武汉→深圳",
            "start": "2026-09-08T12:12:00+08:00",
            "end": "2026-09-08T14:12:00+08:00",
            "notes": "marker",
        },
    }
    provider = FakeProvider([{"eventId": "event-1", "notes": plan["lookup"]["marker"]}])
    result = apply_plan(provider, plan, "cal-1", apply=True)  # type: ignore[arg-type]
    assert result["action"] == "updated"
    assert provider.updated[0]["eventId"] == "event-1"
