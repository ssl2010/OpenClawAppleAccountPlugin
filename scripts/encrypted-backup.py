#!/usr/bin/env python3
"""US1 OpenClaw backup. Public encryption key only; no private key required."""
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

NAME = re.compile(r"us1-openclaw-(\d{8}T\d{6}Z)\.tar\.age$")
UNITS = ("openclaw-mail-digest.timer", "openclaw-rail12306.timer",
         "openclaw-expense-receipts.timer", "openclaw-expense-reconcile.timer")
EXTERNAL = (".config/openclaw", ".config/openclaw-apple-account",
            ".config/openclaw-mail-management", ".config/gogcli",
            ".local/state/openclaw-apple-account",
            ".local/state/openclaw-mail-management", ".config/systemd/user")
EXTERNAL += (".config/openclaw-expense-receipts",
             ".local/state/openclaw-expense-receipts", ".config/nextcloud-sync", ".netrc")


def run(args):
    # Do not log command output: backup tools may include private configuration.
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def active(unit):
    return subprocess.run(["systemctl", "--user", "is-active", "--quiet", unit],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode == 0


@contextlib.contextmanager
def quiesce():
    """Let in-flight workers finish, then briefly pause the gateway for consistency."""
    restart = []
    try:
        for unit in UNITS:
            if active(unit):
                restart.append(unit)
                run(["systemctl", "--user", "stop", unit])
        deadline = time.monotonic() + 1250
        for unit in ("openclaw-mail-digest.service", "openclaw-rail12306.service",
                     "openclaw-expense-receipts.service", "openclaw-expense-reconcile.service"):
            while run(["systemctl", "--user", "show", "-p", "ActiveState", "--value", unit]).strip() in {"active", "activating", "deactivating"}:
                if time.monotonic() > deadline:
                    raise TimeoutError("Worker did not finish; backup cancelled")
                time.sleep(2)
        if active("openclaw-gateway.service"):
            restart.append("openclaw-gateway.service")
            run(["systemctl", "--user", "stop", "openclaw-gateway.service"])
        yield
    finally:
        failures = []
        for unit in reversed(restart):
            try:
                run(["systemctl", "--user", "start", unit])
            except subprocess.CalledProcessError:
                failures.append(unit)
        if failures:
            raise RuntimeError("Could not restore services: " + ", ".join(failures))


def expire(root, now):
    """Only exact owned, regular, timestamped archives older than 7x24h."""
    for path in root.iterdir():
        match = NAME.fullmatch(path.name)
        if not match or path.is_symlink() or not path.is_file():
            continue
        stamp = dt.datetime.strptime(match[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
        if now - stamp > dt.timedelta(days=7):
            path.unlink()
            sidecar = path.with_suffix(path.suffix + ".sha256")
            if sidecar.is_file() and not sidecar.is_symlink():
                sidecar.unlink()


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main():
    os.umask(0o077)
    home = Path.home()
    root = home / "backups/openclaw"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink():
        raise RuntimeError("Backup directory must not be a symlink")
    root.chmod(0o700)
    recipient = home / ".config/openclaw-backup/recipient.txt"
    if not recipient.is_file():
        raise RuntimeError("Missing encryption recipient")
    with (root / ".backup.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        now = dt.datetime.now(dt.timezone.utc)
        name = "us1-openclaw-" + now.strftime("%Y%m%dT%H%M%SZ") + ".tar.age"
        final = root / name
        if final.exists():
            raise RuntimeError("Backup already exists")
        with tempfile.TemporaryDirectory(prefix=".staging-", dir=root) as temp:
            stage = Path(temp)
            native = stage / "openclaw.tar.gz"
            extra = stage / "external.tar.gz"
            with quiesce():
                run([str(home / ".openclaw/bin/openclaw"), "backup", "create",
                     "--output", str(native), "--verify", "--json"])
                with tarfile.open(extra, "w:gz", dereference=False) as archive:
                    for relative in EXTERNAL:
                        path = home / relative
                        if path.exists():
                            archive.add(path, arcname=relative)
                    repo = home / "work/OpenClawAppleAccountPlugin"
                    excluded = {".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
                    archive.add(repo, arcname="work/OpenClawAppleAccountPlugin",
                                filter=lambda item: None if excluded.intersection(Path(item.name).parts) else item)
            # Services are back online before encryption/compression verification.
            with tarfile.open(extra, "r:gz") as archive:
                for member in archive:
                    if member.isfile():
                        with archive.extractfile(member) as source:
                            while source.read(1024 * 1024):
                                pass
            manifest = {"schema": 1, "createdUtc": now.isoformat(), "host": "US1",
                        "archives": {p.name: digest(p) for p in (native, extra)},
                        "externalPaths": EXTERNAL, "retentionDays": 7}
            (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            plain = stage / "bundle.tar"
            with tarfile.open(plain, "w") as archive:
                for filename in ("openclaw.tar.gz", "external.tar.gz", "manifest.json"):
                    archive.add(stage / filename, arcname=filename)
            encrypted = stage / name
            run(["age", "-R", str(recipient), "-o", str(encrypted), str(plain)])
            if encrypted.stat().st_size < 100:
                raise RuntimeError("Encrypted backup unexpectedly small")
            checksum = digest(encrypted)
            with encrypted.open("rb") as stream:
                os.fsync(stream.fileno())
            encrypted.rename(final)
            final.with_suffix(".age.sha256").write_text(checksum + "  " + name + "\n")
            # Re-read persisted ciphertext before retention, not a decrypt claim.
            if digest(final) != checksum:
                raise RuntimeError("Persisted backup checksum mismatch")
        expire(root, now)
        print(json.dumps({"status": "ok", "archive": str(final), "bytes": final.stat().st_size}))


if __name__ == "__main__":
    main()
