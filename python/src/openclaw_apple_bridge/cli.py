from __future__ import annotations

import json
import sys
from typing import Any

from .protocol import dispatch


def capabilities() -> dict[str, Any]:
    """Return the planned bridge contract without loading credentials."""
    return {
        "status": "scaffold",
        "protocolVersion": 1,
        "capabilities": [
            "calendar.read",
            "calendar.create",
            "calendar.cancel",
            "reminders.read",
            "reminders.create",
            "reminders.complete",
            "notes.read.research",
        ],
    }


def main() -> None:
    if sys.stdin.isatty():
        print(json.dumps(capabilities(), ensure_ascii=False))
        return
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise TypeError("request must be an object")
        response = dispatch(request)
    except (json.JSONDecodeError, TypeError):
        response = {
            "protocolVersion": 1,
            "requestId": "",
            "ok": False,
            "error": {
                "code": "INVALID_REQUEST",
                "message": "Invalid JSON request.",
                "retryable": False,
            },
        }
    try:
        encoded = json.dumps(response, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        encoded = json.dumps({
            "protocolVersion": 1, "requestId": response.get("requestId", ""), "ok": False,
            "error": {"code": "INVALID_RESPONSE", "message": "Bridge response is not JSON-safe.",
                      "retryable": False},
        })
    print(encoded)


if __name__ == "__main__":
    main()
