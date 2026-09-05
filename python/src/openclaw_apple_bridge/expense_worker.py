"""Durable Gmail collector for travel expense receipts."""
from __future__ import annotations

import argparse
import base64
import fcntl
import json
import os
import sqlite3
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .expense_materialize import materialize
from .expense_receipts import (
    artifact_ocr_text,
    artifact_text,
    inventory_rfc822,
    mail_disposition,
    parse_receipt_text,
    parse_receipt_xml,
)

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS messages (
 id TEXT PRIMARY KEY, internal_ms INTEGER NOT NULL, subject TEXT NOT NULL,
 disposition TEXT NOT NULL, raw_sha256 TEXT NOT NULL, ingested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS artifacts (
 sha256 TEXT PRIMARY KEY, message_id TEXT NOT NULL REFERENCES messages(id),
 name TEXT NOT NULL, media_type TEXT NOT NULL, source TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('classified','preserved','needs_review')),
 blob_path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
 artifact_sha256 TEXT NOT NULL REFERENCES artifacts(sha256), ordinal INTEGER NOT NULL,
 fact_json TEXT NOT NULL, PRIMARY KEY(artifact_sha256, ordinal)
);
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trip_commits (
 trip_key TEXT PRIMARY KEY, folder_path TEXT NOT NULL, manifest_hash TEXT NOT NULL,
 committed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 sync_state TEXT NOT NULL CHECK(sync_state IN ('pending','confirmed'))
);
CREATE TABLE IF NOT EXISTS notices (
 notice_key TEXT PRIMARY KEY, status TEXT NOT NULL CHECK(status IN ('sending','sent')),
 receipt TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class Gmail:
    def __init__(self, config: dict[str, Any]) -> None:
        self.account = config["account"]
        self.gog = config.get("gog", "/usr/local/bin/gog")

    def call(self, args: list[str]) -> Any:
        result = subprocess.run(
            [self.gog, *args, "--account", self.account, "--json", "--no-input"],
            check=True, capture_output=True, text=True, timeout=120,
        )
        return json.loads(result.stdout)

    def search(self, query: str, maximum: int) -> list[dict[str, Any]]:
        response = self.call(["gmail", "messages", "search", query, "--max", str(maximum)])
        messages = response.get("messages")
        if not isinstance(messages, list) or response.get("nextPageToken"):
            raise ValueError("Expense discovery result is incomplete or exceeds its bound")
        return messages

    def raw(self, message_id: str) -> tuple[bytes, int]:
        response = self.call(["gmail", "raw", message_id, "--format", "raw"])
        encoded = response.get("raw") or response.get("message", {}).get("raw")
        internal = response.get("internalDate") or response.get("message", {}).get("internalDate")
        if not encoded or not internal:
            raise ValueError("Incomplete raw Gmail message")
        return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)), int(internal)


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    database = sqlite3.connect(path)
    database.executescript(SCHEMA)
    return database


def send_notice(config: dict[str, Any], database: sqlite3.Connection,
                notice_key: str, message: str) -> str | None:
    existing = database.execute("SELECT status FROM notices WHERE notice_key=?", (notice_key,)).fetchone()
    if existing:
        if existing[0] == "sending":
            raise ValueError("Expense notice outcome requires reconciliation")
        return None
    with database:
        database.execute("INSERT INTO notices(notice_key,status) VALUES(?,'sending')", (notice_key,))
    cli = str(Path(config.get("openclaw", "~/.openclaw/bin/openclaw")).expanduser())
    result = subprocess.run(
        [cli, "message", "send", "--channel", "feishu", "--target", config["feishuTarget"],
         "--message", message, "--json"],
        check=True, capture_output=True, text=True, timeout=90,
    )
    raw = result.stdout
    response = json.loads(raw[raw.index("{\n"):] if "{\n" in raw else raw)
    receipt = response.get("messageId") or response.get("payload", {}).get("messageId")
    if not receipt or response.get("payload", {}).get("ok") is False:
        raise ValueError("Expense notice delivery was not confirmed")
    with database:
        database.execute(
            "UPDATE notices SET status='sent',receipt=? WHERE notice_key=?", (str(receipt), notice_key)
        )
    return str(receipt)


def ingest_message(database: sqlite3.Connection, blob_root: Path, message_id: str,
                   internal_ms: int, raw: bytes, *, allow_test: bool = False) -> dict[str, Any]:
    import hashlib

    inventory = inventory_rfc822(raw)
    outer = inventory.evidence[0]
    disposition = mail_disposition(outer.subject, outer.sender, outer.body,
                                   (artifact.name for artifact in inventory.artifacts))
    raw_hash = hashlib.sha256(raw).hexdigest()
    if disposition == "test_bundle" and not allow_test:
        with database:
            database.execute(
                "INSERT OR IGNORE INTO messages(id,internal_ms,subject,disposition,raw_sha256) VALUES(?,?,?,?,?)",
                (message_id, internal_ms, outer.subject, disposition, raw_hash),
            )
        return {"id": message_id, "status": "test-skipped"}
    if disposition not in {"travel_candidate", "test_bundle"}:
        with database:
            database.execute(
                "INSERT OR IGNORE INTO messages(id,internal_ms,subject,disposition,raw_sha256) VALUES(?,?,?,?,?)",
                (message_id, internal_ms, outer.subject, disposition, raw_hash),
            )
        return {"id": message_id, "status": "not-travel", "disposition": disposition}
    blob_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    useful = {".pdf", ".ofd", ".xml"}
    inserted = 0
    review = 0
    with database:
        database.execute(
            "INSERT OR IGNORE INTO messages(id,internal_ms,subject,disposition,raw_sha256) VALUES(?,?,?,?,?)",
            (message_id, internal_ms, outer.subject, disposition, raw_hash),
        )
        for artifact in inventory.artifacts:
            if Path(artifact.name).suffix.casefold() not in useful:
                continue
            if database.execute("SELECT 1 FROM artifacts WHERE sha256=?", (artifact.sha256,)).fetchone():
                continue
            text = artifact_text(artifact)
            if ("登机" in artifact.source or "乘机凭证" in artifact.source) and len(text.strip()) < 100:
                text = artifact_ocr_text(artifact)
            facts = parse_receipt_xml(artifact.content) if artifact.name.casefold().endswith(".xml") else parse_receipt_text(text)
            if facts:
                state = "classified" if all(not fact.needs_review for fact in facts) else "needs_review"
            else:
                state = "preserved" if artifact.name.casefold().endswith(".ofd") else "needs_review"
            destination = blob_root / artifact.sha256[:2] / artifact.sha256
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not destination.exists():
                temporary = destination.with_suffix(".tmp")
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(artifact.content)
                    handle.flush()
                    os.fsync(handle.fileno())
                temporary.replace(destination)
            before = database.total_changes
            database.execute(
                "INSERT OR IGNORE INTO artifacts(sha256,message_id,name,media_type,source,state,blob_path) VALUES(?,?,?,?,?,?,?)",
                (artifact.sha256, message_id, artifact.name, artifact.media_type,
                 artifact.source, state, str(destination)),
            )
            if database.total_changes > before:
                inserted += 1
                review += state == "needs_review"
                for ordinal, fact in enumerate(facts):
                    database.execute(
                        "INSERT INTO facts(artifact_sha256,ordinal,fact_json) VALUES(?,?,?)",
                        (artifact.sha256, ordinal, json.dumps(asdict(fact), ensure_ascii=False, default=str)),
                    )
    return {"id": message_id, "status": "ingested", "artifacts": inserted, "needsReview": review}


def run(config: dict[str, Any], *, preview: bool = False,
        test_ids: list[str] | None = None, collect: bool = True,
        reconcile: bool = True) -> dict[str, Any]:
    state = Path(config["stateDir"]).expanduser()
    database = connect(state / "expense.sqlite")
    gmail = Gmail(config)
    maximum = int(config.get("maxMessages", 100))
    if not collect:
        listed = []
    elif test_ids:
        listed = [{"id": value} for value in test_ids]
    else:
        cursor = database.execute("SELECT value FROM metadata WHERE key='gmail_cursor_ms'").fetchone()
        after = max(0, int(cursor[0]) // 1000 - 1) if cursor else 0
        query = f"after:{after} -in:trash -in:spam -in:drafts"
        listed = gmail.search(query, maximum)
    results = []
    newest = 0
    for item in listed:
        message_id = str(item["id"])
        if not test_ids and database.execute("SELECT 1 FROM messages WHERE id=?", (message_id,)).fetchone():
            continue
        raw, internal_ms = gmail.raw(message_id)
        newest = max(newest, internal_ms)
        if preview:
            evidence = inventory_rfc822(raw).evidence[0]
            results.append({"id": message_id, "subject": evidence.subject,
                            "disposition": mail_disposition(evidence.subject, evidence.sender, evidence.body)})
        else:
            results.append(ingest_message(database, state / "blobs", message_id, internal_ms,
                                          raw, allow_test=bool(test_ids)))
    materialized = None
    if not preview and not test_ids:
        if newest:
            with database:
                database.execute(
                    "INSERT INTO metadata(key,value) VALUES('gmail_cursor_ms',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(newest),),
                )
        materialized = materialize(config, database) if reconcile else None
        review_count = sum(int(item.get("needsReview", 0)) for item in results)
        missing_count = int(materialized.get("missingBoarding", 0)) if materialized else 0
        if review_count or missing_count:
            issue_rows = database.execute(
                "SELECT sha256,state FROM artifacts WHERE state='needs_review' ORDER BY sha256"
            ).fetchall()
            key_material = json.dumps(
                {"review": issue_rows,
                 "missing": materialized.get("missingBoardingTrips", []) if materialized else []},
                ensure_ascii=False,
            )
            notice_key = "issues:" + __import__("hashlib").sha256(key_material.encode()).hexdigest()
            text = (
                "差旅票据后台发现需要处理的事项："
                f"待确认票据 {review_count} 项，缺少登机凭证的航班 {missing_count} 个。"
                "未强行分类或删除文件，请在飞书中让我查看差旅票据待确认列表。"
            )
            send_notice(config, database, notice_key, text)
    database.close()
    return {"status": "preview" if preview else "ok", "messages": results,
            "materialize": materialized}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="~/.config/openclaw-expense-receipts/config.json")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--test-message", action="append", default=[])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--collect-only", action="store_true")
    mode.add_argument("--reconcile-only", action="store_true")
    parser.add_argument("--initialize-cursor-now", action="store_true")
    args = parser.parse_args()
    config = json.loads(Path(args.config).expanduser().read_text())
    lock_path = Path(config["stateDir"]).expanduser() / "worker.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with lock_path.open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.initialize_cursor_now:
            database = connect(Path(config["stateDir"]).expanduser() / "expense.sqlite")
            with database:
                database.execute(
                    "INSERT INTO metadata(key,value) VALUES('gmail_cursor_ms',?) "
                    "ON CONFLICT(key) DO NOTHING", (str(time.time_ns() // 1_000_000),),
                )
            value = database.execute(
                "SELECT value FROM metadata WHERE key='gmail_cursor_ms'"
            ).fetchone()[0]
            database.close()
            print(json.dumps({"status": "initialized", "gmailCursorMs": value}))
            return
        print(json.dumps(run(
            config, preview=args.preview, test_ids=args.test_message,
            collect=not args.reconcile_only, reconcile=not args.collect_only,
        ), ensure_ascii=False))


if __name__ == "__main__":
    main()
