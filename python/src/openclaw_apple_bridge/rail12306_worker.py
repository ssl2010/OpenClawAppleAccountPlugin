from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any

from .errors import BridgeError
from .icloud import ICloudProvider
from .models import parse_rfc3339
from .rail12306 import plan_email


def _gog_json(args: list[str]) -> Any:
    executable = os.environ.get("GOG_PATH", "/usr/local/bin/gog")
    command = [executable, *args, "--json", "--results-only", "--no-input", "--wrap-untrusted"]
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
    return json.loads(result.stdout)


def _trusted_message(message: dict[str, Any]) -> bool:
    headers = message.get("headers") or {}
    sender = str(headers.get("from") or "").casefold()
    body = str(message.get("body") or "").casefold()
    if "12306@rails.com.cn" in sender:
        return True
    trusted_forwarders = {
        value.strip().casefold()
        for value in os.environ.get("RAIL12306_TRUSTED_FORWARDERS", "").split(",")
        if value.strip()
    }
    return any(address in sender for address in trusted_forwarders) and bool(
        __import__("re").search(r"发件人\s*[:：].*12306@rails\.com\.cn", body)
    )


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
    exact = [item for item in existing if plan["lookup"]["marker"] in item["notes"]]
    if plan["operation"] == "reconcile-update" and not exact:
        passenger = f"passenger={plan['lookup']['passengerKey']}"
        exact = [
            item
            for item in existing
            if "[OpenClaw:12306 " in item["notes"] and passenger in item["notes"]
        ]
    if len(exact) > 1 and plan["operation"] != "delete":
        raise BridgeError(
            "CONFLICT", "Multiple managed calendar events match this 12306 itinerary."
        )
    if plan["operation"] == "delete":
        if not exact:
            return {"action": "noop", "reason": "no-managed-event"}
        if not apply:
            return {"action": "would-delete", "count": len(exact)}
        receipts = [
            provider.delete_event({"calendarId": calendar_id, "eventId": item["eventId"]})
            for item in exact
        ]
        return {"action": "deleted", "receipts": receipts}
    payload = {"calendarId": calendar_id, **event}
    if exact:
        if not apply:
            return {"action": "would-update", "eventId": exact[0]["eventId"]}
        return provider.update_event({**payload, "eventId": exact[0]["eventId"]})
    if not apply:
        return {"action": "would-create"}
    return provider.create_event(payload)


def process_message(
    message: dict[str, Any], provider: ICloudProvider, *, apply: bool
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
    calendar_id = _calendar_id(provider)
    outcomes = [apply_plan(provider, item, calendar_id, apply=apply) for item in plan["plans"]]
    return {"messageId": message_id, "mailAction": plan["mailAction"], "outcomes": outcomes}


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
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    temporary.replace(path)


def run(*, apply: bool, max_messages: int = 20) -> dict[str, Any]:
    state_path = Path(
        os.environ.get(
            "RAIL12306_STATE_FILE", "~/.local/state/openclaw-apple-account/rail12306.json"
        )
    ).expanduser()
    state = _load_state(state_path)
    search_query = os.environ.get("RAIL12306_GMAIL_QUERY", "12306 newer_than:30d")
    summaries = _gog_json(["gmail", "search", search_query])
    provider = ICloudProvider(_provider_config())
    outcomes: list[dict[str, Any]] = []
    for summary in list(summaries)[: max(1, min(max_messages, 100))]:
        message_id = str(summary.get("id") or "")
        if not message_id or state["messages"].get(message_id, {}).get("status") == "applied":
            continue
        try:
            message = _gog_json(["gmail", "get", message_id])
            outcome = process_message(message, provider, apply=apply)
            status = "applied" if apply else "dry-run"
            state["messages"][message_id] = {"status": status, "mailAction": outcome["mailAction"]}
            outcomes.append(outcome)
        except BridgeError as exc:
            state["messages"][message_id] = {
                "status": "ignored"
                if exc.code in {"UNTRUSTED_EMAIL", "UNSUPPORTED_EMAIL"}
                else "failed",
                "error": exc.code,
            }
            outcomes.append({"messageId": message_id, "error": exc.code})
    _save_state(state_path, state)
    return {
        "mode": "apply" if apply else "dry-run",
        "processed": len(outcomes),
        "outcomes": outcomes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process trusted 12306 Gmail notices into Apple Calendar"
    )
    parser.add_argument("--apply", action="store_true", help="Execute planned calendar mutations")
    parser.add_argument("--max-messages", type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(run(apply=args.apply, max_messages=args.max_messages), ensure_ascii=False))


if __name__ == "__main__":
    main()
