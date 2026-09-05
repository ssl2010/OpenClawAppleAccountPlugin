"""Atomic local materialization and confirmed Nextcloud synchronization."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .expense_receipts import ReceiptFact
from .expense_trip import TripPlan, reconcile_trips
from .rail12306 import station_city

CATEGORIES = {
    "rail_ticket": "交通", "air_invoice": "交通", "hotel": "住宿",
    "rail_refund": "退票费", "air_refund": "退票费", "boarding_pass": "登机凭证",
}


def _load_facts(database: sqlite3.Connection) -> tuple[list[ReceiptFact], dict[int, tuple[str, ReceiptFact]]]:
    facts = []
    indexed = {}
    for rowid, artifact, raw in database.execute(
        "SELECT f.rowid,f.artifact_sha256,f.fact_json FROM facts f ORDER BY f.rowid"
    ):
        data = json.loads(raw)
        if data.get("travel_date"):
            data["travel_date"] = date.fromisoformat(data["travel_date"])
        fact = ReceiptFact(**data)
        facts.append(fact)
        indexed[rowid] = (artifact, fact)
    return facts, indexed


def _fact_key(fact: ReceiptFact) -> tuple[Any, ...]:
    return (fact.kind, fact.travel_date, station_city(fact.origin),
            station_city(fact.destination), fact.service_number)


def _plan_artifacts(database: sqlite3.Connection, plan: TripPlan,
                    indexed: dict[int, tuple[str, ReceiptFact]]) -> dict[str, str]:
    wanted = {
        (item.kind, item.travel_date, item.origin, item.destination, item.service_number)
        for item in plan.segments
    }
    wanted.update(_fact_key(item) for item in plan.refunds)
    chosen: dict[str, str] = {}
    document_categories: dict[str, str] = {}
    for artifact, fact in indexed.values():
        key = _fact_key(fact)
        category = CATEGORIES.get(fact.kind)
        if key in wanted and category:
            chosen[artifact] = category
            if fact.document_id:
                document_categories[fact.document_id] = category
        if (
            fact.kind == "hotel"
            and fact.travel_date
            and plan.start_date <= fact.travel_date <= plan.end_date
            and _hotel_city(fact) in plan.destinations
        ):
            chosen[artifact] = "住宿"
        if (
            fact.kind == "boarding_pass"
            and fact.travel_date
            and any(
                fact.travel_date == item.travel_date
                and (not fact.service_number or fact.service_number == item.service_number)
                and (not fact.origin or fact.origin == item.origin)
                and (not fact.destination or fact.destination == item.destination)
                for item in plan.segments
            )
        ):
            chosen[artifact] = "登机凭证"
    if document_categories:
        for sha256, name in database.execute("SELECT sha256,name FROM artifacts"):
            for document_id, category in document_categories.items():
                if document_id in name:
                    chosen[sha256] = category
    return chosen


def _hotel_city(fact: ReceiptFact) -> str:
    return station_city(fact.destination or fact.origin)


def _trip_key(plan: TripPlan) -> str:
    material = "|".join((plan.start_date.isoformat(), plan.end_date.isoformat(),
                         *plan.destinations,
                         *(f"{item.travel_date}:{item.service_number}:{item.origin}:{item.destination}"
                           for item in plan.segments)))
    return hashlib.sha256(material.encode()).hexdigest()


def _write_trip(database: sqlite3.Connection, root: Path, plan: TripPlan,
                indexed: dict[int, tuple[str, ReceiptFact]]) -> tuple[str, str] | None:
    key = _trip_key(plan)
    existing = database.execute(
        "SELECT folder_path FROM trip_commits WHERE trip_key=?", (key,)
    ).fetchone()
    year = root / str(plan.start_date.year)
    final = year / plan.folder_name
    if existing:
        final = Path(existing[0])
        if not final.is_dir() or not (final / "manifest.json").is_file():
            raise FileNotFoundError("Committed expense trip directory is incomplete")
        manifest = json.loads((final / "manifest.json").read_text())
        known = {item["sha256"] for item in manifest.get("files", [])}
        changed = False
        for sha256, category in sorted(_plan_artifacts(database, plan, indexed).items()):
            if sha256 in known:
                continue
            row = database.execute("SELECT name,blob_path FROM artifacts WHERE sha256=?", (sha256,)).fetchone()
            if not row or hashlib.sha256(Path(row[1]).read_bytes()).hexdigest() != sha256:
                raise ValueError("Artifact hash verification failed")
            name = Path(row[0]).name
            destination = final / category / f"{Path(name).stem}-{sha256[:8]}{Path(name).suffix.lower()}"
            destination.parent.mkdir(exist_ok=True, mode=0o700)
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            shutil.copyfile(row[1], temporary)
            os.chmod(temporary, 0o600)
            temporary.replace(destination)
            manifest.setdefault("files", []).append(
                {"category": category, "name": str(destination.relative_to(final)), "sha256": sha256}
            )
            changed = True
        refunds = json.loads(json.dumps([asdict(item) for item in plan.refunds], default=str))
        missing = [item.service_number for item in plan.missing_boarding]
        if manifest.get("refunds") != refunds or manifest.get("missingBoarding") != missing:
            manifest["refunds"] = refunds
            manifest["missingBoarding"] = missing
            changed = True
        if not changed:
            return None
        encoded = json.dumps(manifest, ensure_ascii=False, indent=2, default=str).encode() + b"\n"
        temporary_manifest = final / ".manifest.json.tmp"
        temporary_manifest.write_bytes(encoded)
        os.chmod(temporary_manifest, 0o600)
        temporary_manifest.replace(final / "manifest.json")
        manifest_hash = hashlib.sha256(encoded).hexdigest()
        with database:
            database.execute(
                "UPDATE trip_commits SET manifest_hash=?,sync_state='pending' WHERE trip_key=?",
                (manifest_hash, key),
            )
        return key, str(final)
    if final.exists():
        raise FileExistsError("Untracked expense trip directory already exists")
    year.mkdir(parents=True, exist_ok=True, mode=0o700)
    stage = year / ("." + plan.folder_name + ".partial-" + key[:8])
    if stage.exists():
        raise FileExistsError("Stale expense staging directory requires review")
    stage.mkdir(mode=0o700)
    selected = _plan_artifacts(database, plan, indexed)
    files = []
    try:
        for sha256, category in sorted(selected.items()):
            row = database.execute(
                "SELECT name,blob_path FROM artifacts WHERE sha256=?", (sha256,)
            ).fetchone()
            if not row:
                raise ValueError("Artifact disappeared during materialization")
            if hashlib.sha256(Path(row[1]).read_bytes()).hexdigest() != sha256:
                raise ValueError("Artifact hash verification failed")
            name = Path(row[0]).name
            destination = stage / category / f"{Path(name).stem}-{sha256[:8]}{Path(name).suffix.lower()}"
            destination.parent.mkdir(exist_ok=True, mode=0o700)
            shutil.copyfile(row[1], destination)
            os.chmod(destination, 0o600)
            files.append({"category": category, "name": str(destination.relative_to(stage)),
                          "sha256": sha256})
        manifest = {
            "schema": 1, "tripKey": key, "startDate": plan.start_date.isoformat(),
            "endDate": plan.end_date.isoformat(), "destinations": plan.destinations,
            "segments": [asdict(item) for item in plan.segments],
            "refunds": [asdict(item) for item in plan.refunds],
            "missingBoarding": [item.service_number for item in plan.missing_boarding],
            "files": files,
        }
        encoded = json.dumps(manifest, ensure_ascii=False, indent=2, default=str).encode() + b"\n"
        manifest_path = stage / "manifest.json"
        fd = os.open(manifest_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        stage.rename(final)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    manifest_hash = hashlib.sha256(encoded).hexdigest()
    with database:
        database.execute(
            "INSERT INTO trip_commits(trip_key,folder_path,manifest_hash,sync_state) VALUES(?,?,?,'pending')",
            (key, str(final), manifest_hash),
        )
    return key, str(final)


def materialize(config: dict[str, Any], database: sqlite3.Connection,
                *, today: date | None = None, sync: bool = True) -> dict[str, Any]:
    facts, indexed = _load_facts(database)
    plans, unresolved = reconcile_trips(facts, max_trip_days=int(config.get("maxTripDays", 30)))
    today = today or datetime.now(ZoneInfo(config.get("timezone", "Asia/Shanghai"))).date()
    grace = timedelta(hours=int(config.get("closureGraceHours", 72)))
    eligible = [
        plan for plan in plans
        if not plan.needs_review and today > plan.end_date + grace
    ]
    root = Path(config["nextcloudRoot"]).expanduser()
    committed = [result for plan in eligible if (result := _write_trip(database, root, plan, indexed))]
    pending_sync = database.execute(
        "SELECT trip_key FROM trip_commits WHERE sync_state='pending'"
    ).fetchall()
    synced = False
    if sync and pending_sync:
        subprocess.run([str(Path(config["syncCommand"]).expanduser())], check=True,
                       capture_output=True, text=True, timeout=1800)
        with database:
            database.executemany(
                "UPDATE trip_commits SET sync_state='confirmed' WHERE trip_key=?", pending_sync
            )
        synced = True
    return {
        "committed": [{"tripKey": item[0], "folder": item[1]} for item in committed],
        "synced": synced, "unresolved": len(unresolved),
        "missingBoarding": sum(len(plan.missing_boarding) for plan in plans),
        "missingBoardingTrips": [
            {
                "startDate": plan.start_date.isoformat(),
                "destinations": list(plan.destinations),
                "services": [item.service_number for item in plan.missing_boarding],
            }
            for plan in plans if plan.missing_boarding
        ],
    }
