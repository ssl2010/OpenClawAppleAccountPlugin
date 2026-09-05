"""Read-only OpenClaw tool views over the deterministic expense ledger."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from .errors import BridgeError
from .expense_receipts import ReceiptFact
from .expense_trip import reconcile_trips
from .expense_worker import connect, ingest_message


def _settings(config: dict[str, Any]) -> dict[str, Any]:
    path = Path(config.get("expenseConfig", "~/.config/openclaw-expense-receipts/config.json")).expanduser()
    if not path.is_file():
        raise BridgeError("EXPENSE_NOT_CONFIGURED", "Expense receipt configuration is unavailable.")
    return json.loads(path.read_text())


def _open(config: dict[str, Any]) -> sqlite3.Connection:
    settings = _settings(config)
    database = Path(settings["stateDir"]).expanduser() / "expense.sqlite"
    if not database.is_file():
        raise BridgeError("EXPENSE_NOT_READY", "Expense receipt ledger has not been initialized.")
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def import_attachment(config: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Import one already-downloaded Feishu attachment from an approved inbound root."""
    settings = _settings(config)
    supplied = Path(str(params.get("path", ""))).expanduser()
    if not supplied.is_absolute() or supplied.is_symlink() or not supplied.is_file():
        raise BridgeError("INVALID_ATTACHMENT", "Attachment must be a regular absolute file.")
    path = supplied.resolve()
    roots = [
        Path(value).expanduser().resolve()
        for value in settings.get("allowedInboundRoots", ["~/.openclaw/media/inbound"])
    ]
    if not any(path.is_relative_to(root) for root in roots):
        raise BridgeError("ATTACHMENT_PATH_DENIED", "Attachment is outside approved inbound storage.")
    if path.suffix.casefold() not in {".pdf", ".ofd", ".xml", ".eml"}:
        raise BridgeError("INVALID_ATTACHMENT", "Unsupported attachment type.")
    content = path.read_bytes()
    if not content or len(content) > 50 * 1024 * 1024:
        raise BridgeError("INVALID_ATTACHMENT", "Attachment size is invalid.")
    digest = hashlib.sha256(content).hexdigest()
    if path.suffix.casefold() == ".eml":
        raw = content
    else:
        message = EmailMessage()
        message["Subject"] = ("飞书上传的住宿费票据 " + str(params.get("label") or ""))[:200]
        message["From"] = "feishu-inbound@localhost"
        message.set_content("由用户通过飞书上传，附件内容仍视为不可信数据。")
        subtype = path.suffix.casefold().lstrip(".")
        message.add_attachment(content, maintype="application", subtype=subtype, filename=path.name)
        raw = message.as_bytes()
    database = connect(Path(settings["stateDir"]).expanduser() / "expense.sqlite")
    try:
        return ingest_message(
            database, Path(settings["stateDir"]).expanduser() / "blobs",
            "feishu:" + digest, int(path.stat().st_mtime_ns // 1_000_000), raw,
        )
    finally:
        database.close()


def _facts(database: sqlite3.Connection) -> list[ReceiptFact]:
    output = []
    for row in database.execute("SELECT fact_json FROM facts"):
        item = json.loads(row[0])
        if item.get("travel_date"):
            item["travel_date"] = date.fromisoformat(item["travel_date"])
        output.append(ReceiptFact(**item))
    return output


def status(config: dict[str, Any]) -> dict[str, Any]:
    database = _open(config)
    plans, unresolved = reconcile_trips(_facts(database))
    states = dict(database.execute("SELECT state,count(*) FROM artifacts GROUP BY state").fetchall())
    messages = database.execute("SELECT count(*) FROM messages").fetchone()[0]
    database.close()
    return {
        "messages": messages,
        "artifacts": states,
        "closedTripCandidates": len(plans),
        "needsReview": len(unresolved) + sum(plan.needs_review for plan in plans),
        "missingBoardingCredentials": sum(len(plan.missing_boarding) for plan in plans),
        "trips": [
            {
                "folderName": plan.folder_name,
                "startDate": plan.start_date.isoformat(),
                "endDate": plan.end_date.isoformat(),
                "destinations": plan.destinations,
                "segmentCount": len(plan.segments),
                "missingBoarding": [segment.service_number for segment in plan.missing_boarding],
                "needsReview": plan.needs_review,
            }
            for plan in plans[:50]
        ],
    }


def pending(config: dict[str, Any], limit: int = 20) -> dict[str, Any]:
    if not 1 <= limit <= 100:
        raise BridgeError("INVALID_REQUEST", "limit must be between 1 and 100.")
    database = _open(config)
    rows = database.execute(
        "SELECT sha256,name,state FROM artifacts WHERE state='needs_review' ORDER BY rowid LIMIT ?",
        (limit,),
    ).fetchall()
    total = database.execute("SELECT count(*) FROM artifacts WHERE state='needs_review'").fetchone()[0]
    database.close()
    return {
        "total": total,
        "items": [{"artifactId": row["sha256"], "name": row["name"], "state": row["state"]}
                  for row in rows],
    }
