"""Offline audit of a private JSON email corpus; emits no raw personal data."""
import json
import sys
from pathlib import Path

from openclaw_apple_bridge.errors import BridgeError
from openclaw_apple_bridge.rail12306 import plan_email

records = json.loads(Path(sys.argv[1]).read_text())
cutoff = sys.argv[2]
results = []
expected_actions = {"网上购票系统-用户支付通知": "book", "网上购票系统-候补订单兑现成功通知": "book", "网上购票系统-用户退票通知": "cancel", "网上购票系统-用户改签通知": "change"}
for record in records:
    try:
        plan = plan_email({"messageId": str(record["index"]), **record})
        assert plan["mailAction"] == expected_actions[record["subject"]]
        json.dumps(plan)
        for item in plan["plans"]:
            assert item["event"]["start"] < cutoff
            assert item["event"]["notes"].endswith("from OpenClaw US1")
        result = {"action": plan["mailAction"], "segments": sum(p["segments"] for p in plan["plans"])}
    except BridgeError as exc:
        assert record["subject"] not in expected_actions, (record["index"], exc.code)
        assert exc.code == "UNSUPPORTED_EMAIL"
        result = {"error": exc.code}
    results.append({"index": record["index"], "subject": record["subject"], **result})
print(json.dumps(results, ensure_ascii=False, indent=2))
print(f"PASS: {len(results)} real emails; no calendar/mail mutations")
