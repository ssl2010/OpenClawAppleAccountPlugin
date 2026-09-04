"""Mailbox ordering, crash fences, and historical-forward safety."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_rail_safety_regressions import params

from openclaw_apple_bridge import rail12306_worker as worker
from openclaw_apple_bridge.errors import BridgeError


def mail(identifier: str, timestamp: int, subject: str = "用户支付通知") -> dict[str, Any]:
    return {"id": identifier, "internalDate": str(timestamp),
            "headers": {"from": "12306@rails.com.cn", "subject": subject},
            "body": params()["body"]}


def harness(monkeypatch: Any, tmp_path: Path, messages: list[dict[str, Any]]) -> tuple[Path, list[str]]:
    path = tmp_path / "state.json"
    calls: list[str] = []
    monkeypatch.setenv("RAIL12306_STATE_FILE", str(path))
    monkeypatch.setattr(worker, "ICloudProvider", lambda _: object())
    def gog(args: list[str]) -> Any:
        if args[1] == "messages":
            return {"messages": [{"id": x["id"]} for x in messages]}
        return next(x for x in messages if x["id"] == args[2])
    def process(message: dict[str, Any], *_: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(message["id"])
        return {"messageId": message["id"], "mailAction": "book", "outcomes": [], "timetableFailures": []}
    monkeypatch.setattr(worker, "_gog_json", gog)
    monkeypatch.setattr(worker, "process_message", process)
    return path, calls


def test_newest_first_search_executes_oldest_first(monkeypatch: Any, tmp_path: Path) -> None:
    _, calls = harness(monkeypatch, tmp_path, [mail("cancel", 2000, "用户退票通知"), mail("book", 1000)])
    worker.run(apply=True)
    assert calls == ["book", "cancel"]


def test_old_pending_cannot_overwrite_new_applied_order(monkeypatch: Any, tmp_path: Path) -> None:
    path, calls = harness(monkeypatch, tmp_path, [mail("old", 1000)])
    path.write_text(json.dumps({"version": 1, "messages": {"old": {"status": "timetable-pending"}},
                               "orders": {"ZZ12345678": {"timestamp": 2000, "messageId": "new"}}}))
    worker.run(apply=True)
    assert calls == []
    assert json.loads(path.read_text())["messages"]["old"]["status"] == "superseded"


def test_late_delivery_old_purchase_cannot_recreate_refunded_order(monkeypatch: Any, tmp_path: Path) -> None:
    messages = [mail("refund", 2000, "用户退票通知")]
    _, calls = harness(monkeypatch, tmp_path, messages)
    worker.run(apply=True)
    messages[:] = [mail("old-purchase", 1000)]
    worker.run(apply=True)
    assert calls == ["refund"]


def test_unknown_write_blocks_later_same_order(monkeypatch: Any, tmp_path: Path) -> None:
    path, calls = harness(monkeypatch, tmp_path, [mail("later", 3000)])
    path.write_text(json.dumps({"version": 1, "messages": {}, "orders": {
        "ZZ12345678": {"blocked": True, "timestamp": 2000, "messageId": "crashed"}}}))
    worker.run(apply=True)
    assert calls == []


def test_equal_timestamp_transactions_fail_closed(monkeypatch: Any, tmp_path: Path) -> None:
    _, calls = harness(monkeypatch, tmp_path, [mail("a", 1000), mail("b", 1000, "用户退票通知")])
    worker.run(apply=True)
    assert calls == []


@pytest.mark.parametrize("subject", ["12306历史邮件", "历史票据样本包", "OpenClaw测试 用户支付通知"])
def test_sample_packages_are_excluded(monkeypatch: Any, tmp_path: Path, subject: str) -> None:
    path, calls = harness(monkeypatch, tmp_path, [mail("sample", 1000, subject)])
    worker.run(apply=True)
    assert calls == []
    assert json.loads(path.read_text())["messages"]["sample"]["status"] == "test-excluded"


def test_forward_timestamp_is_original_date_not_delivery() -> None:
    message = mail("forward", 9999999999999)
    message["headers"]["from"] = "trusted@example.com"
    message["body"] += "\nDate: Fri, 04 Sep 2026 10:00:00 +0800"
    assert worker._transaction_timestamp(message) == 1788487200000


def test_forward_missing_original_date_fails_closed() -> None:
    message = mail("forward", 9999999999999)
    message["headers"]["from"] = "trusted@example.com"
    with pytest.raises(BridgeError):
        worker._transaction_timestamp(message)


def test_malformed_later_transaction_fences_pending_old_order(monkeypatch: Any, tmp_path: Path) -> None:
    malformed = mail("bad-change", 2000, "用户改签通知")
    malformed["body"] = "订单号码 ZZ12345678。无法解析的改签信息"
    _, calls = harness(monkeypatch, tmp_path, [mail("old", 1000), malformed])
    worker.run(apply=True)
    assert calls == []
