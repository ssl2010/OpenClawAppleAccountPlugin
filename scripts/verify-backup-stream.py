#!/usr/bin/env python3
"""Read a DECRYPTED bundle on stdin; verify in memory without extracting secrets."""
import hashlib
import io
import json
import sys
import tarfile

hashes = {}
with tarfile.open(fileobj=sys.stdin.buffer, mode="r|") as outer:
    for member in outer:
        if member.name not in {"openclaw.tar.gz", "external.tar.gz", "manifest.json"}:
            raise ValueError("Unexpected bundle member")
        data = outer.extractfile(member).read()
        if member.name == "manifest.json":
            manifest = json.loads(data)
            continue
        hashes[member.name] = hashlib.sha256(data).hexdigest()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as inner:
            count = 0
            for item in inner:
                if item.isfile():
                    with inner.extractfile(item) as source:
                        while source.read(1024 * 1024):
                            pass
                    count += 1
            print(f"{member.name}: {count} files readable")
if hashes != manifest["archives"]:
    raise ValueError("Inner archive checksum mismatch")
print("PASS: decrypted bundle, inner checksums and archive readability")
