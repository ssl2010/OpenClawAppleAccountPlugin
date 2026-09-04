"""Independent safety regressions: synthetic mail only, never production access."""
from __future__ import annotations

import fcntl
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from test_rail12306_worker import FailingTimetable, FakeProvider

from openclaw_apple_bridge import rail12306_worker as worker
from openclaw_apple_bridge.errors import BridgeError
from openclaw_apple_bridge.rail12306 import classify_mail, plan_email
from openclaw_apple_bridge.rail12306_worker import apply_plan, process_message


def ticket(origin: str = "武汉", destination: str = "深圳北", train: str = "G395",
           time: str = "12:12", passenger: str = "测试旅客") -> str:
    return (f"{passenger}，2026年09月08日{time}开，{origin}站-{destination}站，"
            f"{train}次，9车10F号，一等座，检票口A5。")


def params(subject: str = "网上购票系统-用户支付通知", body: str = "") -> dict[str, Any]:
    return {"messageId": "synthetic-mail", "subject": subject,
            "body": body or "订单号码 ZZ12345678。" + ticket()}


@pytest.mark.parametrize("footer", ["如需退票、改签请登录网站", "退票规则：开车前可申请", "改签说明"])
def test_purchase_footer_never_authorizes_cancel(footer: str) -> None:
    assert classify_mail("网上购票系统-用户支付通知", ticket() + footer) == "book"


@pytest.mark.parametrize("subject", ["退票申请", "退票失败", "取消订单提醒", "改签须知", "待支付通知", "通知"])
def test_noncommitted_or_ambiguous_subject_fails_closed(subject: str) -> None:
    with pytest.raises(BridgeError):
        plan_email(params(subject))


@pytest.mark.parametrize("subject,expected", [("用户退票通知", "cancel"), ("用户改签通知", "change"), ("用户支付通知", "book")])
def test_explicit_transaction_subjects(subject: str, expected: str) -> None:
    assert plan_email(params(subject))["mailAction"] == expected


def test_complete_cli_json_boundary() -> None:
    request = {"requestId": "regression-json", "operation": "rail12306.plan", "params": params()}
    result = subprocess.run([sys.executable, "-m", "openclaw_apple_bridge.cli"],
                            input=json.dumps(request), text=True, capture_output=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response["ok"] is True
    assert response["data"]["plans"][0]["segmentDetails"][0]["departure"].endswith("+08:00")


def test_multiple_order_ids_fail_closed() -> None:
    with pytest.raises(BridgeError):
        plan_email(params(body="订单号码 ZZ12345678。订单号码 ZZ87654321。" + ticket()))


def test_transfer_merge_and_layout() -> None:
    body = "订单号码 ZZ12345678。" + ticket("武汉", "南京", "G1", "08:00")
    body += ticket("南京", "苏州", "G2", "12:00") + ticket("苏州", "上海", "G3", "14:00")
    plan = plan_email(params(body=body))["plans"]
    assert len(plan) == 1
    assert plan[0]["event"]["title"] == "火车行程：武汉→上海"
    lines = plan[0]["event"]["notes"].splitlines()
    assert [line[:2] for line in lines[:3]] == ["1.", "2.", "3."]
    assert lines[-1] == "from OpenClaw US1"


@pytest.mark.parametrize("station", ["温州南", "平阳", "瑞安"])
def test_prefecture_city_normalization(station: str) -> None:
    plan = plan_email(params(body="订单号码 ZZ12345678。" + ticket(destination=station)))
    assert plan["plans"][0]["event"]["title"] == "火车行程：武汉→温州"


def test_no_seat_preserved() -> None:
    plan = plan_email(params(body="订单号码 ZZ12345678。" + ticket().replace("9车10F号，一等座", "无座")))
    assert "无座" in plan["plans"][0]["event"]["notes"]


def test_refund_never_deletes_unmanaged_event() -> None:
    plan = plan_email(params("用户退票通知"))["plans"][0]
    provider = FakeProvider([{"eventId": "personal", "notes": "普通私人日程"}])
    apply_plan(provider, plan, "cal-1", apply=True)  # type: ignore[arg-type]
    assert provider.deleted == []


def test_refund_ambiguous_duplicate_markers_fail_closed() -> None:
    plan = plan_email(params("用户退票通知"))["plans"][0]
    provider = FakeProvider([{"eventId": str(i), **plan["event"]} for i in range(2)])
    with pytest.raises(BridgeError):
        apply_plan(provider, plan, "cal-1", apply=True)  # type: ignore[arg-type]
    assert provider.deleted == []


def test_refund_exact_single_segment_deletes_once() -> None:
    plan = plan_email(params("用户退票通知"))["plans"][0]
    provider = FakeProvider([{"eventId": "managed", **plan["event"]}])
    apply_plan(provider, plan, "cal-1", apply=True)  # type: ignore[arg-type]
    assert provider.deleted == [{"calendarId": "cal-1", "eventId": "managed"}]


def test_partial_transfer_refund_requires_review() -> None:
    body = "订单号码 ZZ12345678。" + ticket("武汉", "南京", "G1", "08:00")
    complete = plan_email(params(body=body + ticket("南京", "上海", "G2", "12:00")))["plans"][0]
    refund = plan_email(params("用户退票通知", body))["plans"][0]
    provider = FakeProvider([{"eventId": "managed", **complete["event"]}])
    with pytest.raises(BridgeError):
        apply_plan(provider, refund, "cal-1", apply=True)  # type: ignore[arg-type]
    assert provider.deleted == []


def test_change_must_not_match_different_order_same_passenger() -> None:
    plan = plan_email(params("用户改签通知"))["plans"][0]
    other = plan_email(params(body=params()["body"].replace("ZZ12345678", "ZZ87654321")))["plans"][0]
    provider = FakeProvider([{"eventId": "unrelated", **other["event"]}])
    with pytest.raises(BridgeError):
        apply_plan(provider, plan, "cal-1", apply=True)  # type: ignore[arg-type]
    assert provider.updated == []


@pytest.mark.parametrize("sender", ["12306@rails.com.cn.evil.example", '"12306@rails.com.cn" <evil@example.com>', "12306@rails.com.cn, evil@example.com"])
def test_sender_substring_spoof_rejected(sender: str) -> None:
    message = {"id": "spoof", "headers": {"from": sender, "subject": "用户支付通知"}, "body": params()["body"]}
    provider = FakeProvider()
    with pytest.raises(BridgeError):
        process_message(message, provider, apply=True, timetable=FailingTimetable())  # type: ignore[arg-type]
    assert provider.created == []


def test_disconnected_same_order_same_passenger_requires_review() -> None:
    body = "订单号码 ZZ12345678。" + ticket("武汉", "南京", "G1", "08:00")
    body += ticket("广州南", "深圳北", "G2", "14:00")
    with pytest.raises(BridgeError):
        plan_email(params(body=body))


def test_old_refund_with_different_departure_time_cannot_delete() -> None:
    current = plan_email(params())["plans"][0]
    refund = plan_email(params("用户退票通知", params()["body"].replace("12:12", "11:12")))["plans"][0]
    provider = FakeProvider([{"eventId": "managed", **current["event"]}])
    with pytest.raises(BridgeError):
        apply_plan(provider, refund, "cal-1", apply=True)  # type: ignore[arg-type]
    assert provider.deleted == []


def test_single_leg_change_cannot_replace_existing_transfer() -> None:
    body = "订单号码 ZZ12345678。" + ticket("武汉", "南京", "G1", "08:00")
    complete = plan_email(params(body=body + ticket("南京", "上海", "G2", "12:00")))["plans"][0]
    change = plan_email(params("用户改签通知", body))["plans"][0]
    provider = FakeProvider([{"eventId": "managed", **complete["event"]}])
    with pytest.raises(BridgeError):
        apply_plan(provider, change, "cal-1", apply=True)  # type: ignore[arg-type]
    assert provider.updated == []


def setup_worker(monkeypatch: Any, tmp_path: Path) -> Path:
    state_path = tmp_path / "state.json"
    monkeypatch.setenv("RAIL12306_STATE_FILE", str(state_path))
    monkeypatch.setattr(worker, "ICloudProvider", lambda _: FakeProvider())
    message = {"id": "synthetic-mail", "internalDate": "1788508800000", "headers": {"from": "12306@rails.com.cn", "subject": "用户支付通知"}, "body": params()["body"]}
    monkeypatch.setattr(worker, "_gog_json", lambda args: {"messages": [{"id": "synthetic-mail"}]} if args[1] == "messages" else message)
    return state_path


def test_worker_crash_persists_in_progress_and_never_replays(monkeypatch: Any, tmp_path: Path) -> None:
    state_path = setup_worker(monkeypatch, tmp_path)
    calls: list[int] = []

    def crash(*args: Any, **kwargs: Any) -> None:
        assert json.loads(state_path.read_text())["messages"]["synthetic-mail"]["status"] == "in-progress"
        calls.append(1)
        raise RuntimeError("simulated connection lost after committed write")

    monkeypatch.setattr(worker, "process_message", crash)
    with pytest.raises(RuntimeError):
        worker.run(apply=True)
    assert worker.run(apply=True)["processed"] == 0
    assert len(calls) == 1


def test_worker_unknown_result_bridge_error_requires_reconciliation(monkeypatch: Any, tmp_path: Path) -> None:
    state_path = setup_worker(monkeypatch, tmp_path)

    def fail(*args: Any, **kwargs: Any) -> None:
        raise BridgeError("UNKNOWN_OUTCOME", "simulated write ambiguity")

    monkeypatch.setattr(worker, "process_message", fail)
    worker.run(apply=True)
    assert json.loads(state_path.read_text())["messages"]["synthetic-mail"]["status"] == "reconciliation-required"
    assert worker.run(apply=True)["processed"] == 0


def test_worker_lock_excludes_concurrent_process(monkeypatch: Any, tmp_path: Path) -> None:
    state_path = setup_worker(monkeypatch, tmp_path)
    with state_path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BridgeError, match="Another mail worker"):
            worker.run(apply=True)
