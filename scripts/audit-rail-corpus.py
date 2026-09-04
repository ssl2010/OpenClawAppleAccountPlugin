"""Read-only private attachment corpus audit; never changes mail/calendar."""
import json
import os
import subprocess
import sys
import tempfile
from email import policy
from email.parser import BytesParser
from pathlib import Path

os.umask(0o077)
root = Path(tempfile.mkdtemp(prefix="rail-corpus-"))
if len(sys.argv) != 3:
    raise SystemExit("Usage: audit-rail-corpus.py ACCOUNT PACKAGED_MESSAGE_ID")
base = ["/usr/local/bin/gog", "--account", sys.argv[1]]
message_id = sys.argv[2]
meta = json.loads(subprocess.check_output(base + ["gmail", "get", message_id, "--json", "--results-only", "--no-input"]))
records = []
assert len(meta.get("attachments", [])) <= 150, "Oversized attachment inventory"
for index, attachment in enumerate(meta.get("attachments", [])):
    if attachment.get("mimeType") != "message/rfc822":
        continue
    path = root / f"{index:03}.eml"
    subprocess.run(base + ["gmail", "attachment", message_id, str(index), "--use-indexed-attachment-ids", "--out", str(path), "--no-input"], check=True, capture_output=True)
    mail = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    part = mail.get_body(preferencelist=("plain", "html"))
    body = part.get_content() if part else ""
    records.append({"index": index, "subject": str(mail["subject"]), "date": str(mail["date"]), "body": body, "contentType": part.get_content_type() if part else ""})
(root / "corpus.json").write_text(json.dumps(records, ensure_ascii=False))
print(json.dumps({"directory": str(root), "count": len(records), "subjects": {s: sum(r["subject"] == s for r in records) for s in sorted({r["subject"] for r in records})}}, ensure_ascii=False))
