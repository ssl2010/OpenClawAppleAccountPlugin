from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import date
from pathlib import Path

from openclaw_apple_bridge.expense_materialize import materialize
from openclaw_apple_bridge.expense_receipts import ReceiptFact
from openclaw_apple_bridge.expense_worker import connect


def add(database: sqlite3.Connection, root: Path, fact: ReceiptFact, content: bytes) -> str:
    import hashlib

    sha = hashlib.sha256(content).hexdigest()
    blob = root / sha
    blob.write_bytes(content)
    database.execute("INSERT OR IGNORE INTO messages VALUES('m',1,'s','travel_candidate','raw',CURRENT_TIMESTAMP)")
    database.execute("INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)",
                     (sha, "m", sha + ".pdf", "application/pdf", "message", "classified", str(blob)))
    database.execute("INSERT INTO facts(artifact_sha256,ordinal,fact_json) VALUES(?,?,?)",
                     (sha, 0, json.dumps(asdict(fact), default=str)))
    database.commit()
    return sha


def test_atomic_materialization_and_no_repeat(tmp_path, monkeypatch) -> None:
    database = connect(tmp_path / "state.sqlite")
    outbound = ReceiptFact("rail_ticket", "i1", date(2026, 8, 12), "武汉", "温州", "G1", "100")
    inbound = ReceiptFact("rail_ticket", "i2", date(2026, 8, 14), "温州", "武汉", "G2", "100")
    add(database, tmp_path, outbound, b"outbound")
    add(database, tmp_path, inbound, b"inbound")
    add(database, tmp_path,
        ReceiptFact("hotel", "h1", date(2026, 8, 13), "", "温州", "", "300"),
        b"hotel")
    calls = []
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: calls.append(args) or None)
    config = {"nextcloudRoot": str(tmp_path / "cloud"), "syncCommand": "/bin/sync",
              "closureGraceHours": 72, "maxTripDays": 30}
    result = materialize(config, database, today=date(2026, 8, 20))
    folder = tmp_path / "cloud/2026/08月12日温州"
    assert folder.is_dir() and (folder / "manifest.json").is_file()
    assert len(list((folder / "交通").iterdir())) == 2
    assert len(list((folder / "住宿").iterdir())) == 1
    assert result["synced"] and len(calls) == 1
    add(database, tmp_path,
        ReceiptFact("air_refund", "r1", date(2026, 8, 12), "武汉", "温州", "CZ1", "50"),
        b"late-refund")
    updated = materialize(config, database, today=date(2026, 8, 21))
    assert updated["committed"] and len(list((folder / "退票费").iterdir())) == 1
    assert materialize(config, database, today=date(2026, 8, 20))["committed"] == []


def test_incomplete_and_multi_city_never_write(tmp_path) -> None:
    database = connect(tmp_path / "state.sqlite")
    add(database, tmp_path, ReceiptFact("rail_ticket", "i", date(2026, 8, 12),
                                       "武汉", "上海", "G1", "100"), b"one-way")
    result = materialize({"nextcloudRoot": str(tmp_path / "cloud"),
                          "syncCommand": "/bin/false"}, database,
                         today=date(2026, 8, 20), sync=False)
    assert result["committed"] == [] and not (tmp_path / "cloud").exists()
