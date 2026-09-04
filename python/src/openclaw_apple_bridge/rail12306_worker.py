from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timedelta
from email.utils import getaddresses, parsedate_to_datetime
from itertools import pairwise
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import BridgeError
from .icloud import ICloudProvider
from .models import parse_rfc3339
from .rail12306 import ORDER_RE, email_text, format_itinerary_notes, plan_email, unwrap_external
from .timetable import RailwayTimetable


def _gog_json(args: list[str]) -> Any:
    executable = os.environ.get("GOG_PATH", "/usr/local/bin/gog")
    command = [executable, *args, "--json", "--no-input", "--wrap-untrusted"]
    if args[:3] != ["gmail", "messages", "search"]:
        command.append("--results-only")
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
    return json.loads(result.stdout)


def _trusted_message(message: dict[str, Any]) -> bool:
    headers = message.get("headers") or {}
    sender = unwrap_external(str(headers.get("from") or "")).casefold()
    senders = {address for _, address in getaddresses([sender])}
    body = email_text(str(message.get("body") or "")).casefold()
    if senders == {"12306@rails.com.cn"}:
        return True
    trusted_forwarders = {
        value.strip().casefold()
        for value in os.environ.get("RAIL12306_TRUSTED_FORWARDERS", "").split(",")
        if value.strip()
    }
    if len(senders) != 1 or not senders.issubset(trusted_forwarders):
        return False
    for line in body.splitlines():
        match = re.match(r"\s*(?:发件人|from)\s*[:：]\s*(.*)", line)
        if match and {address for _, address in getaddresses([match.group(1)])} == {
            "12306@rails.com.cn"
        }:
            return True
    return False


def _provider_config() -> dict[str, Any]:
    return {
        "sessionDirectory": os.environ.get(
            "ICLOUD_SESSION_DIRECTORY", "~/.local/state/openclaw-apple-account/session"
        ),
        "passwordFile": os.environ.get("ICLOUD_PASSWORD_FILE"),
        "region": os.environ.get("ICLOUD_REGION", "global"),
        "requestTimeoutSeconds": int(os.environ.get("ICLOUD_REQUEST_TIMEOUT_SECONDS", "20")),
    }


def _calendar_id(provider: ICloudProvider) -> str:
    configured = os.environ.get("ICLOUD_CALENDAR_ID", "").strip()
    if configured:
        return configured
    calendars = provider.list_calendars()
    candidates = [item for item in calendars if not item["readOnly"] and item["enabled"]]
    defaults = [item for item in candidates if item["isDefault"]]
    if not (defaults or candidates):
        raise BridgeError("CAPABILITY_UNAVAILABLE", "No writable Apple calendar is available.")
    return str((defaults or candidates)[0]["id"])


def apply_plan(
    provider: ICloudProvider, plan: dict[str, Any], calendar_id: str, *, apply: bool
) -> dict[str, Any]:
    event = plan["event"]
    if plan["operation"] not in {"upsert", "delete", "reconcile-update"}:
        raise BridgeError("INVALID_REQUEST", "Unsupported calendar operation.")
    start = parse_rfc3339(event["start"])
    end = parse_rfc3339(event["end"])
    existing = provider.list_events(
        {
            "start": (start - timedelta(days=7)).isoformat(),
            "end": (end + timedelta(days=7)).isoformat(),
            "calendarIds": [calendar_id],
            "limit": 500,
        }
    )
    tracking_url = event.get("url")
    exact = [item for item in existing if (
        (tracking_url and item.get("url") == tracking_url)
        or plan["lookup"]["marker"] in item["notes"]
    )]
    if len(existing) >= 500:
        raise BridgeError("CONFLICT", "Calendar query may be truncated; review is required.")
    if plan["operation"] == "reconcile-update" and not exact:
        raise BridgeError("CONFLICT", "No exact managed order found for a change notice.")
    if len(exact) > 1:
        raise BridgeError(
            "CONFLICT", "Multiple managed calendar events match this 12306 itinerary."
        )
    if exact and plan["operation"] == "reconcile-update":
        managed_lines = [line for line in exact[0]["notes"].splitlines()
                         if re.match(r"\d+\. ", line)]
        if len(managed_lines) != len(plan.get("segmentDetails", [])) or not managed_lines:
            raise BridgeError("CONFLICT", "A partial or legacy itinerary change requires review.")
    if plan["operation"] == "delete":
        if not exact:
            return {"action": "noop", "reason": "no-managed-event"}
        segments = plan.get("segmentDetails", [])
        managed_lines = [line for line in exact[0]["notes"].splitlines()
                         if re.match(r"\d+\. ", line)]
        if len(segments) != 1 or len(managed_lines) != 1:
            raise BridgeError("CONFLICT", "Partial or legacy itinerary refund requires review.")
        segment = segments[0]
        identity = f"{segment['train']}｜{segment['originStation']}→{segment['destinationStation']}｜"
        departure = parse_rfc3339(str(segment["departure"])).strftime("%Y-%m-%d %H:%M")
        if identity not in managed_lines[0] or departure not in managed_lines[0]:
            raise BridgeError("CONFLICT", "Refund segment does not match the managed event.")
        if not apply:
            return {"action": "would-delete", "count": len(exact)}
        receipts = [
            _committed(provider.delete_event({"calendarId": calendar_id, "eventId": item["eventId"]}))
            for item in exact
        ]
        return {"action": "deleted", "receipts": receipts}
    payload = {"calendarId": calendar_id, **event}
    if exact:
        if not apply:
            return {"action": "would-update", "eventId": exact[0]["eventId"]}
        return _committed(provider.update_event({**payload, "eventId": exact[0]["eventId"]}))
    if not apply:
        return {"action": "would-create"}
    payload["eventId"] = str(uuid5(NAMESPACE_URL, plan["lookup"]["marker"]))
    return _committed(provider.create_event(payload))


def _committed(receipt: dict[str, Any]) -> dict[str, Any]:
    if receipt.get("committed") is not True:
        raise BridgeError("MUTATION_UNKNOWN", "Calendar write needs read-back reconciliation.")
    return receipt


def process_message(
    message: dict[str, Any],
    provider: ICloudProvider,
    *,
    apply: bool,
    timetable: RailwayTimetable | None = None,
) -> dict[str, Any]:
    message_id = str((message.get("message") or {}).get("id") or message.get("id") or "")
    if not message_id or not _trusted_message(message):
        raise BridgeError(
            "UNTRUSTED_EMAIL", "The message is not a trusted direct or forwarded 12306 notice."
        )
    plan = plan_email(
        {
            "messageId": message_id,
            "subject": str((message.get("headers") or {}).get("subject") or ""),
            "body": str(message.get("body") or ""),
        }
    )
    timetable_failures: list[dict[str, str]] = []
    if plan["mailAction"] != "cancel":
        resolver = timetable or RailwayTimetable(
            timeout_seconds=float(os.environ.get("RAIL12306_TIMEOUT_SECONDS", "20"))
        )
        for item in plan["plans"]:
            segment_details = item["segmentDetails"]
            for segment in segment_details:
                segment["departure"] = parse_rfc3339(segment["departure"])
            for segment in segment_details:
                try:
                    result = resolver.lookup(
                        {
                            "travelDate": segment["departure"].strftime("%Y-%m-%d"),
                            "trainNumber": segment["train"],
                            "originStation": segment["originStation"],
                            "destinationStation": segment["destinationStation"],
                        }
                    )
                    official_departure = parse_rfc3339(result["departure"])
                    if official_departure != segment["departure"]:
                        raise BridgeError(
                            "TIMETABLE_MISMATCH",
                            "The official departure differs from the ticket notice.",
                        )
                    arrival = parse_rfc3339(result["arrival"])
                    if arrival <= official_departure:
                        raise BridgeError("TIMETABLE_MISMATCH", "Arrival must follow departure.")
                    segment["arrival"] = arrival
                except BridgeError as exc:
                    timetable_failures.append(
                        {
                            "train": segment["train"],
                            "route": (
                                f"{segment['originStation']}→{segment['destinationStation']}"
                            ),
                            "error": exc.code,
                        }
                    )
            failed_trains = {failure["train"] for failure in timetable_failures}
            item["timetableStatus"] = (
                "fallback" if any(x["train"] in failed_trains for x in segment_details) else "resolved"
            )
            last = segment_details[-1]
            for earlier, later in pairwise(segment_details):
                if earlier.get("arrival") and earlier["arrival"] >= later["departure"]:
                    raise BridgeError("CONFLICT", "Transfer departs before the prior arrival.")
            item["event"]["end"] = (
                last.get("arrival") or last["departure"] + timedelta(minutes=10)
            ).isoformat()
            itinerary = {"segments": segment_details}
            item["event"]["notes"] = format_itinerary_notes(
                itinerary, item["lookup"]["marker"], timetable_status=item["timetableStatus"]
            )
    calendar_id = _calendar_id(provider)
    if apply:
        # Preflight every plan before permitting any write in a multi-passenger message.
        for item in plan["plans"]:
            apply_plan(provider, item, calendar_id, apply=False)
    outcomes = [apply_plan(provider, item, calendar_id, apply=apply) for item in plan["plans"]]
    return {
        "messageId": message_id,
        "mailAction": plan["mailAction"],
        "outcomes": outcomes,
        "timetableFailures": timetable_failures,
    }


def _notify_timetable_failure(failures: list[dict[str, str]]) -> bool:
    target = os.environ.get("RAIL12306_FEISHU_TARGET", "").strip()
    executable = str(
        Path(os.environ.get("OPENCLAW_PATH", "~/.openclaw/bin/openclaw")).expanduser()
    )
    if not target:
        try:
            configured = subprocess.run(
                [executable, "config", "get", "channels.feishu.allowFrom", "--json"],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            allowed = json.loads(configured.stdout)
            target = str(allowed[0]).strip() if allowed else ""
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, IndexError, TypeError):
            return False
    if not target:
        return False
    details = "；".join(f"{item['train']} {item['route']}" for item in failures[:5])
    message = (
        "⚠️ 12306 官方时刻表查询失败："
        f"{details}。日历暂按发车后 10 分钟结束；系统会每 10 分钟重试，成功后自动更新。"
    )
    try:
        subprocess.run(
            [
                executable,
                "message",
                "send",
                "--channel",
                "feishu",
                "--target",
                target,
                "--message",
                message,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "messages": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(path: Path, state: dict[str, Any]) -> None:
    if not path.parent.exists():
        path.parent.mkdir(parents=True, mode=0o700)
        path.parent.chmod(0o700)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    temporary.replace(path)


def run(*, apply: bool, max_messages: int = 100) -> dict[str, Any]:
    state_path = Path(
        os.environ.get(
            "RAIL12306_STATE_FILE", "~/.local/state/openclaw-apple-account/rail12306.json"
        )
    ).expanduser()
    state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with state_path.with_suffix(".lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BridgeError("WORKER_BUSY", "Another mail worker owns the state lock.") from exc
        return _run_locked(state_path, apply=apply, max_messages=max_messages)


def _run_locked(state_path: Path, *, apply: bool, max_messages: int) -> dict[str, Any]:
    state = _load_state(state_path)
    search_query = os.environ.get("RAIL12306_GMAIL_QUERY", "12306 newer_than:30d")
    search = _gog_json(["gmail", "messages", "search", search_query, "--max", "100"])
    # Preserve the pagination envelope: --results-only would hide truncation.
    if not isinstance(search, dict) or not isinstance(search.get("messages"), list):
        raise BridgeError("MAILBOX_INCOMPLETE", "Unexpected message-search envelope; no writes allowed.")
    summaries = search["messages"]
    if (search.get("nextPageToken") or search.get("next_page_token")
            or len(summaries) >= 100 or len(summaries) > max(1, min(max_messages, 100))):
        raise BridgeError("MAILBOX_INCOMPLETE", "Mailbox result exceeds safe complete batch; narrow query or review.")
    provider = ICloudProvider(_provider_config())
    outcomes: list[dict[str, Any]] = []
    orders = state.setdefault("orders", {})
    candidates: list[tuple[int, str, str, dict[str, Any]]] = []
    for summary in summaries:
        message_id = str(summary.get("id") or "")
        if not message_id or state["messages"].get(message_id, {}).get("status") in {
            "test-excluded", "superseded", "ignored",
        }:
            continue
        try:
            message = _gog_json(["gmail", "get", message_id])
            subject = unwrap_external(str((message.get("headers") or {}).get("subject") or ""))
            if "OpenClaw测试" in subject or "12306历史邮件" in subject or "样本包" in subject:
                state["messages"][message_id] = {"status": "test-excluded"}
                continue
            if not _trusted_message(message):
                raise BridgeError("UNTRUSTED_EMAIL", "Untrusted transaction sender.")
            parsed = plan_email({"messageId": message_id, "subject": subject,
                                 "body": str(message.get("body") or "")})
            order_id = str(parsed["orderId"])
            timestamp = _transaction_timestamp(message)
            previous = state["messages"].get(message_id, {})
            if previous.get("status") in {"in-progress", "reconciliation-required"}:
                orders[order_id] = {"blocked": True, "messageId": message_id,
                                    "timestamp": timestamp}
                continue
            if previous.get("status") == "applied":
                watermark = orders.get(order_id, {})
                if not watermark.get("blocked") and timestamp > watermark.get("timestamp", 0):
                    orders[order_id] = {"timestamp": timestamp, "messageId": message_id}
                continue
            candidates.append((timestamp, message_id, order_id, message))
        except BridgeError as exc:
            if exc.code not in {"UNTRUSTED_EMAIL", "UNSUPPORTED_EMAIL"}:
                # A malformed later transaction may still identify affected orders.
                # Fence those orders rather than let an older retry overwrite them.
                for match in ORDER_RE.finditer(email_text(str(message.get("body") or ""))):
                    orders[match.group(1).upper()] = {"blocked": True, "messageId": message_id}
            state["messages"][message_id] = {
                "status": "ignored" if exc.code in {"UNTRUSTED_EMAIL", "UNSUPPORTED_EMAIL"}
                else "reconciliation-required", "error": exc.code,
            }
            outcomes.append({"messageId": message_id, "error": exc.code})
    # A mailbox search is commonly newest-first. Never execute in delivery order.
    candidates.sort(key=lambda item: (item[0], item[1]))
    duplicate_times: set[tuple[str, int]] = set()
    seen_times: set[tuple[str, int]] = set()
    for timestamp, _, order_id, _ in candidates:
        key = (order_id, timestamp)
        if key in seen_times:
            duplicate_times.add(key)
        seen_times.add(key)
    for timestamp, message_id, order_id, message in candidates:
        previous = state["messages"].get(message_id, {})
        watermark = orders.get(order_id, {})
        try:
            if watermark.get("blocked") or (order_id, timestamp) in duplicate_times:
                raise BridgeError("CAUSAL_CONFLICT", "Order chronology requires manual review.")
            if timestamp < watermark.get("timestamp", 0):
                state["messages"][message_id] = {"status": "superseded", "orderId": order_id,
                                                "timestamp": timestamp}
                continue
            if timestamp == watermark.get("timestamp") and watermark.get("messageId") != message_id:
                raise BridgeError("CAUSAL_CONFLICT", "Equal-time transactions require review.")
            if apply:
                # Persist before the first possible side effect. A killed worker must
                # not blindly replay a request whose server outcome is unknown.
                state["messages"][message_id] = {**previous, "status": "in-progress",
                                                "orderId": order_id, "timestamp": timestamp}
                orders[order_id] = {"blocked": True, "timestamp": timestamp,
                                    "messageId": message_id}
                _save_state(state_path, state)
            outcome = process_message(message, provider, apply=apply)
            failures = outcome["timetableFailures"]
            status = "applied" if apply and not failures else (
                "timetable-pending" if apply else "dry-run"
            )
            notified = bool(previous.get("timetableFailureNotified"))
            if apply and failures and not notified:
                notified = _notify_timetable_failure(failures)
            state["messages"][message_id] = {
                "status": status,
                "mailAction": outcome["mailAction"],
                "timetableFailureNotified": notified,
                "orderId": order_id,
                "timestamp": timestamp,
            }
            if apply:
                orders[order_id] = {"timestamp": timestamp, "messageId": message_id}
            outcomes.append(outcome)
            if apply:
                _save_state(state_path, state)
        except BridgeError as exc:
            state["messages"][message_id] = {
                "status": "ignored"
                if exc.code in {"UNTRUSTED_EMAIL", "UNSUPPORTED_EMAIL"}
                else ("reconciliation-required" if apply else "failed"),
                "error": exc.code,
                "orderId": order_id,
                "timestamp": timestamp,
            }
            if apply:
                orders[order_id] = {"blocked": True, "timestamp": timestamp,
                                    "messageId": message_id}
            outcomes.append({"messageId": message_id, "error": exc.code})
            if apply:
                _save_state(state_path, state)
    _save_state(state_path, state)
    return {
        "mode": "apply" if apply else "dry-run",
        "processed": len(outcomes),
        "outcomes": outcomes,
    }


def _transaction_timestamp(message: dict[str, Any]) -> int:
    """Original notification time, never the time an old email was forwarded."""
    headers = message.get("headers") or {}
    sender = unwrap_external(str(headers.get("from") or ""))
    direct = {address.casefold() for _, address in getaddresses([sender])} == {
        "12306@rails.com.cn"
    }
    if direct:
        raw = (message.get("message") or {}).get("internalDate") or message.get("internalDate")
        if raw is not None:
            try:
                milliseconds = int(raw)
                if milliseconds > 0:
                    return milliseconds
            except (ValueError, TypeError):
                pass
        dates = [unwrap_external(str(headers.get("date") or ""))]
    else:
        body = email_text(str(message.get("body") or ""))
        dates = re.findall(r"(?im)^\s*(?:发送时间|发送日期|日期|Date|Sent)\s*[:：]\s*(.+)$", body)
    timestamps: set[int] = set()
    for value in dates:
        value = re.sub(r"\s*[（(]星期[一二三四五六日天][）)]\s*$", "", value.strip())
        try:
            parsed = parsedate_to_datetime(value.strip())
        except (ValueError, TypeError, IndexError):
            try:
                parsed = datetime.fromisoformat(value.strip())
            except ValueError:
                continue
        if parsed.tzinfo is None and not direct:
            configured_timezone = os.environ.get("RAIL12306_FORWARD_TIMEZONE", "").strip()
            if configured_timezone:
                try:
                    parsed = parsed.replace(tzinfo=ZoneInfo(configured_timezone))
                except (ZoneInfoNotFoundError, ValueError) as exc:
                    raise BridgeError("CAUSAL_DATE_REQUIRED", "Invalid configured forwarding timezone.") from exc
        if parsed.tzinfo is not None:
            timestamps.add(int(parsed.timestamp() * 1000))
    if len(timestamps) != 1:
        raise BridgeError("CAUSAL_DATE_REQUIRED", "An unambiguous original email timestamp is required.")
    return timestamps.pop()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process trusted 12306 Gmail notices into Apple Calendar"
    )
    parser.add_argument("--apply", action="store_true", help="Execute planned calendar mutations")
    parser.add_argument("--max-messages", type=int, default=100)
    args = parser.parse_args()
    print(json.dumps(run(apply=args.apply, max_messages=args.max_messages), ensure_ascii=False))


if __name__ == "__main__":
    main()
