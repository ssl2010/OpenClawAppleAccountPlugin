"""No production systemctl or data is touched by these tests."""
import datetime as dt
import importlib.util
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "backup", Path(__file__).resolve().parents[2] / "scripts/encrypted-backup.py")
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


def test_retention_boundary_and_ownership(tmp_path):
    now = dt.datetime(2026, 9, 10, tzinfo=dt.UTC)
    expired = tmp_path / "us1-openclaw-20260902T235959Z.tar.age"
    exact = tmp_path / "us1-openclaw-20260903T000000Z.tar.age"
    future = tmp_path / "us1-openclaw-20260911T000000Z.tar.age"
    other = tmp_path / "unrelated.tar.age"
    for path in (expired, exact, future, other):
        path.write_bytes(b"data")
    sidecar = expired.with_suffix(".age.sha256")
    sidecar.write_text("checksum")
    link = tmp_path / "us1-openclaw-20260101T000000Z.tar.age"
    link.symlink_to(other)
    directory = tmp_path / "us1-openclaw-20260102T000000Z.tar.age"
    directory.mkdir()
    backup.expire(tmp_path, now)
    assert not expired.exists() and not sidecar.exists()
    assert all(p.exists() for p in (exact, future, other, link, directory))


def test_failed_snapshot_restores_active_units(monkeypatch):
    calls = []
    monkeypatch.setattr(backup, "active", lambda unit: unit != backup.UNITS[1])
    monkeypatch.setattr(backup, "run", lambda args: calls.append(args) or "inactive\n")
    with pytest.raises(RuntimeError, match="snapshot failed"), backup.quiesce():
        raise RuntimeError("snapshot failed")
    starts = [c[-1] for c in calls if "start" in c]
    expected_active = [unit for unit in backup.UNITS if unit != backup.UNITS[1]]
    assert starts == ["openclaw-gateway.service", *reversed(expected_active)]
    assert backup.UNITS[1] not in starts


def test_restart_failure_still_restores_other_units(monkeypatch):
    calls = []
    monkeypatch.setattr(backup, "active", lambda unit: True)

    def run(args):
        calls.append(args)
        if "start" in args and args[-1] == "openclaw-gateway.service":
            raise subprocess.CalledProcessError(1, args)
        return "inactive\n"

    monkeypatch.setattr(backup, "run", run)
    with pytest.raises(RuntimeError, match="Could not restore"), backup.quiesce():
        pass
    assert [c[-1] for c in calls if "start" in c] == ["openclaw-gateway.service", *reversed(backup.UNITS)]
