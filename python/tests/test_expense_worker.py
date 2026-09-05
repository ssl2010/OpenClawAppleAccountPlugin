from __future__ import annotations

from email.message import EmailMessage

from openclaw_apple_bridge.expense_worker import connect, ingest_message


def message(subject: str, attachment: bytes = b"<x>nothing</x>") -> bytes:
    mail = EmailMessage()
    mail["Subject"] = subject
    mail["From"] = "sender@example.com"
    mail.set_content("body")
    mail.add_attachment(attachment, maintype="application", subtype="xml", filename="invoice.xml")
    return mail.as_bytes()


def test_nontravel_is_recorded_without_blob(tmp_path) -> None:
    database = connect(tmp_path / "state.sqlite")
    result = ingest_message(database, tmp_path / "blobs", "m1", 1,
                            message("保险产品电子发票"))
    assert result["status"] == "not-travel"
    assert database.execute("SELECT disposition FROM messages").fetchone()[0] == "non_travel_invoice"
    assert not (tmp_path / "blobs").exists()


def test_travel_xml_is_durable_and_idempotent(tmp_path) -> None:
    database = connect(tmp_path / "state.sqlite")
    text = "发票号码:26317000000906884501 *退票费* 2026/2/3 武汉-温州 CZ6707"
    raw = message("携程: 机票电子报销凭证", text.encode())
    first = ingest_message(database, tmp_path / "blobs", "m1", 1, raw)
    second = ingest_message(database, tmp_path / "blobs", "m1", 1, raw)
    assert first == {"id": "m1", "status": "ingested", "artifacts": 1, "needsReview": 0}
    assert second["artifacts"] == 0
    fact = database.execute("SELECT fact_json FROM facts").fetchone()[0]
    assert '"kind": "air_refund"' in fact
    blob = database.execute("SELECT blob_path FROM artifacts").fetchone()[0]
    assert __import__("pathlib").Path(blob).read_bytes() == text.encode()


def test_test_bundle_requires_explicit_test_mode(tmp_path) -> None:
    database = connect(tmp_path / "state.sqlite")
    raw = message("openclaw票据报销测试1")
    assert ingest_message(database, tmp_path / "blobs", "m1", 1, raw)["status"] == "test-skipped"
    result = ingest_message(database, tmp_path / "blobs", "m1", 1, raw, allow_test=True)
    assert result["status"] == "ingested" and result["needsReview"] == 1
