"""Synthetic waitlist/invoice/HTML fixtures and complete message-search contract."""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import pytest
from test_rail_causal_regressions import harness, mail
from test_rail_safety_regressions import params, ticket

from openclaw_apple_bridge import rail12306_worker as worker
from openclaw_apple_bridge.errors import BridgeError
from openclaw_apple_bridge.rail12306 import plan_email


def test_waitlist_fulfillment_is_purchase() -> None:
    assert plan_email(params("候补订单兑现成功通知"))["mailAction"] == "book"


@pytest.mark.parametrize("subject", ["候补订单退单通知", "用户支付通知 电子发票", "铁路电子客票报销凭证"])
def test_nontransaction_subject_never_uses_quoted_purchase(subject: str) -> None:
    with pytest.raises(BridgeError):
        plan_email(params(subject, "用户支付通知\n" + params()["body"]))


def test_html_ticket_parses_seat_and_no_seat() -> None:
    for seat in ["9车10F号，一等座", "无座"]:
        body = "<html><body><p>订单号码 ZZ12345678。</p><p>" + ticket().replace("9车10F号，一等座", seat) + "</p></body></html>"
        result = plan_email(params(body=body))["plans"][0]
        assert ("一等座 9车10F号" if seat != "无座" else "无座") in result["event"]["notes"]


def test_html_forward_uses_same_text_for_trust_time_and_parse(monkeypatch: Any) -> None:
    monkeypatch.setenv("RAIL12306_TRUSTED_FORWARDERS", "trusted@example.com")
    message = mail("html-forward", 9999999999999)
    message["headers"]["from"] = "trusted@example.com"
    message["body"] = ("<html><body><div>From: " + html.escape("12306 <12306@rails.com.cn>")
                       + "</div><div>Date: Fri, 04 Sep 2026 10:00:00 +0800</div><p>"
                       + params()["body"] + "</p></body></html>")
    assert worker._trusted_message(message)
    assert worker._transaction_timestamp(message) == 1788487200000
    assert plan_email(params(body=message["body"]))["orderId"] == "ZZ12345678"


@pytest.mark.parametrize("response", [
    {"messages": [{"id": "a"}], "nextPageToken": "more"},
    {"messages": [{"id": str(i)} for i in range(100)]},
    [{"id": "envelope-was-dropped"}],
    {"threads": [{"id": "thread-not-message"}]},
])
def test_incomplete_search_never_fetches_or_writes(monkeypatch: Any, tmp_path: Path, response: Any) -> None:
    _, calls = harness(monkeypatch, tmp_path, [])
    def gog(args: list[str]) -> Any:
        assert args[:3] == ["gmail", "messages", "search"]
        assert args[-2:] == ["--max", "100"]
        return response
    monkeypatch.setattr(worker, "_gog_json", gog)
    with pytest.raises(BridgeError, match=".*") as exc:
        worker.run(apply=True)
    assert exc.value.code == "MAILBOX_INCOMPLETE"
    assert calls == []


def test_max_messages_is_safety_limit_not_silent_slice(monkeypatch: Any, tmp_path: Path) -> None:
    _, calls = harness(monkeypatch, tmp_path, [mail("old", 1000), mail("new", 2000)])
    with pytest.raises(BridgeError):
        worker.run(apply=True, max_messages=1)
    assert calls == []


def naive_forward() -> dict[str, Any]:
    message = mail("naive-forward", 9999999999999)
    message["headers"]["from"] = "trusted@example.com"
    message["body"] += "\n发送时间:2026-09-02 15:29:55 (星期三)"
    return message


def test_naive_forward_requires_explicit_timezone(monkeypatch: Any) -> None:
    monkeypatch.delenv("RAIL12306_FORWARD_TIMEZONE", raising=False)
    with pytest.raises(BridgeError):
        worker._transaction_timestamp(naive_forward())


def test_naive_forward_uses_configured_china_timezone(monkeypatch: Any) -> None:
    monkeypatch.setenv("RAIL12306_FORWARD_TIMEZONE", "Asia/Shanghai")
    assert worker._transaction_timestamp(naive_forward()) == 1788334195000


def test_forward_multiple_times_refused(monkeypatch: Any) -> None:
    monkeypatch.setenv("RAIL12306_FORWARD_TIMEZONE", "Asia/Shanghai")
    message = naive_forward()
    message["body"] += "\n发送时间:2026-09-01 15:29:55 (星期二)"
    with pytest.raises(BridgeError):
        worker._transaction_timestamp(message)


def test_forward_invalid_timezone_refused(monkeypatch: Any) -> None:
    monkeypatch.setenv("RAIL12306_FORWARD_TIMEZONE", "Wrong/Timezone")
    with pytest.raises(BridgeError):
        worker._transaction_timestamp(naive_forward())
