from __future__ import annotations

import json
from typing import Any


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
    print(json.dumps(capabilities(), ensure_ascii=False))


if __name__ == "__main__":
    main()
