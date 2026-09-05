"""Deterministic, bounded discovery primitives for travel expense receipts."""
from __future__ import annotations

import hashlib
import io
import re
import subprocess
import tempfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from email import policy
from email.message import Message
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Any, cast
from xml.etree import ElementTree

MAX_MESSAGE_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_FILES = 200
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_EXPANSION_RATIO = 100
MAX_NESTING = 5
ARCHIVE_EVIDENCE_SUFFIXES = {".pdf", ".ofd", ".xml"}

TEST_SUBJECT = re.compile(r"^openclaw票据报销测试\d*$", re.IGNORECASE)
TRAVEL_TERMS = (
    "铁路电子客票", "网上购票系统-电子发票", "12306", "行程乘机凭证",
    "行程报销校验单", "电子登机牌", "登机牌", "机票电子报销凭证",
    "酒店订单电子发票", "入住", "住宿费", "住宿服务", "退票费",
)
INVOICE_TERMS = ("电子发票", "报销凭证", "发票号码", "发票下载")
NON_TRAVEL_TERMS = ("中国计算机学会", "保险产品电子发票", "餐饮", "餐费")
CTRIP_AIR_SENDERS = ("a_rsv@trip.com", "a_rsv@ctrip.com")
AIRPORT_CITIES = {
    "WUH": "武汉", "WNZ": "温州", "CTU": "成都", "TFU": "成都",
    "PEK": "北京", "PKX": "北京", "PVG": "上海", "SHA": "上海",
    "SZX": "深圳", "CAN": "广州", "SHE": "沈阳", "DLC": "大连",
    "NNG": "南宁", "NGB": "宁波",
}


class UnsafeArtifact(ValueError):
    """An untrusted attachment violates a resource or path boundary."""


@dataclass(frozen=True)
class Artifact:
    name: str
    media_type: str
    content: bytes
    source: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class MailEvidence:
    subject: str
    sender: str
    body: str


@dataclass(frozen=True)
class Inventory:
    evidence: tuple[MailEvidence, ...]
    artifacts: tuple[Artifact, ...]


@dataclass(frozen=True)
class ReceiptFact:
    kind: str
    document_id: str
    travel_date: date | None
    origin: str
    destination: str
    service_number: str
    amount: str
    needs_review: bool = False


def _text(message: Message) -> str:
    chunks: list[str] = []
    for part in message.walk():
        if part.get_content_type() != "text/plain" or part.get_filename():
            continue
        try:
            chunks.append(str(cast(Any, part).get_content()))
        except (LookupError, UnicodeError, KeyError):
            payload = part.get_payload(decode=True) or b""
            chunks.append(cast(bytes, payload).decode("utf-8", "replace"))
    return "\n".join(chunks)[:100_000]


def _safe_name(name: str) -> str:
    value = name.replace("\\", "/").strip()
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or len(value) > 240:
        raise UnsafeArtifact("Unsafe attachment path")
    return path.name


def _looks_like_message(name: str, content: bytes) -> bool:
    if name.casefold().endswith(('.eml', '.rfc822')):
        return True
    head = content[:4096]
    return bool(re.search(br"(?im)^(?:from|subject|date|mime-version):\s*.+$", head))


def _archive_members(artifact: Artifact) -> Iterable[Artifact]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(artifact.content))
    except zipfile.BadZipFile:
        return ()
    entries = archive.infolist()
    if len(entries) > MAX_ARCHIVE_FILES:
        raise UnsafeArtifact("Archive has too many entries")
    total = 0
    output = []
    for entry in entries:
        name = _safe_name(entry.filename)
        mode = entry.external_attr >> 16
        if entry.flag_bits & 1 or (mode & 0o170000) == 0o120000:
            raise UnsafeArtifact("Encrypted or linked archive entry")
        if entry.is_dir():
            continue
        total += entry.file_size
        if total > MAX_ARCHIVE_BYTES:
            raise UnsafeArtifact("Archive expands beyond size limit")
        if entry.compress_size == 0 and entry.file_size:
            raise UnsafeArtifact("Invalid archive compression")
        if entry.compress_size and entry.file_size / entry.compress_size > MAX_EXPANSION_RATIO:
            raise UnsafeArtifact("Archive expansion ratio is unsafe")
        if PurePosixPath(name).suffix.casefold() not in ARCHIVE_EVIDENCE_SUFFIXES:
            continue
        if artifact.name.casefold().endswith(".ofd") and "/attachs/" not in entry.filename.casefold():
            continue
        content = archive.read(entry)
        output.append(Artifact(name, "application/octet-stream", content,
                               artifact.source + "!" + entry.filename))
    return output


def inventory_rfc822(raw: bytes) -> Inventory:
    """Recursively inventory RFC822, forwarded .eml and bounded ZIP/OFD content."""
    if len(raw) > MAX_MESSAGE_BYTES:
        raise UnsafeArtifact("Message exceeds size limit")
    parser = BytesParser(policy=policy.default)
    evidence: list[MailEvidence] = []
    artifacts: list[Artifact] = []
    count = 0

    def visit_message(message: Message, source: str, depth: int) -> None:
        nonlocal count
        if depth > MAX_NESTING:
            raise UnsafeArtifact("Nested message depth exceeded")
        evidence.append(MailEvidence(str(message.get("Subject", "")),
                                     str(message.get("From", "")), _text(message)))
        def visit_part(part: Message) -> None:
            nonlocal count
            if part.get_content_type() == "message/rfc822":
                payload = part.get_payload()
                if isinstance(payload, list):
                    for nested in payload:
                        if isinstance(nested, Message):
                            visit_message(nested, source + "!" + (part.get_filename() or "message.eml"), depth + 1)
                return
            payload = part.get_payload()
            if part.is_multipart() and isinstance(payload, list):
                for child in payload:
                    if isinstance(child, Message):
                        visit_part(child)
                return
            name = part.get_filename()
            if not name:
                return
            count += 1
            if count > MAX_ARCHIVE_FILES:
                raise UnsafeArtifact("Message has too many attachments")
            safe = _safe_name(name)
            content = cast(bytes, part.get_payload(decode=True) or b"")
            if _looks_like_message(safe, content):
                visit_message(parser.parsebytes(content), source + "!" + safe, depth + 1)
                return
            artifact = Artifact(safe, part.get_content_type(), content, source)
            artifacts.append(artifact)
            if safe.casefold().endswith((".zip", ".ofd")):
                artifacts.extend(_archive_members(artifact))

        visit_part(message)

    visit_message(parser.parsebytes(raw), "message", 0)
    return Inventory(tuple(evidence), tuple(artifacts))


def mail_disposition(subject: str, sender: str = "", body: str = "",
                     attachment_names: Iterable[str] = ()) -> str:
    """Route a mail without pretending sender/filename proves trip membership."""
    if TEST_SUBJECT.fullmatch(subject.strip()):
        return "test_bundle"
    text = "\n".join((subject, sender, body[:20_000], *attachment_names)).casefold()
    if any(term.casefold() in text for term in NON_TRAVEL_TERMS):
        return "non_travel_invoice"
    if any(address in sender.casefold() for address in CTRIP_AIR_SENDERS):
        return "travel_candidate"
    if any(term.casefold() in text for term in TRAVEL_TERMS):
        return "travel_candidate"
    if any(term.casefold() in text for term in INVOICE_TERMS):
        return "invoice_needs_review"
    return "ordinary"


def artifact_text(artifact: Artifact, *, timeout: int = 20) -> str:
    """Extract bounded document text. OCR is an explicit caller-controlled fallback."""
    suffix = PurePosixPath(artifact.name).suffix.casefold()
    if suffix == ".xml":
        return artifact.content.decode("utf-8", "replace")[:500_000]
    if suffix != ".pdf":
        return ""
    with tempfile.TemporaryDirectory() as directory:
        source = f"{directory}/document.pdf"
        with open(source, "wb") as handle:
            handle.write(artifact.content)
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", "-f", "1", "-l", "5", source, "-"],
                check=True, capture_output=True, timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
    return result.stdout.decode("utf-8", "replace")[:500_000]


def artifact_ocr_text(artifact: Artifact, *, timeout: int = 30) -> str:
    """Render only the first two PDF pages and OCR them with bounded subprocesses."""
    if not artifact.name.casefold().endswith(".pdf"):
        return ""
    with tempfile.TemporaryDirectory() as directory:
        source = f"{directory}/document.pdf"
        prefix = f"{directory}/page"
        with open(source, "wb") as handle:
            handle.write(artifact.content)
        try:
            subprocess.run(
                ["pdftoppm", "-png", "-r", "240", "-f", "1", "-l", "2", source, prefix],
                check=True, capture_output=True, timeout=timeout,
            )
            chunks = []
            for page in sorted(Path(directory).glob("page-*.png")):
                result = subprocess.run(
                    ["tesseract", str(page), "stdout", "-l", "chi_sim+eng", "--psm", "6"],
                    check=True, capture_output=True, timeout=timeout,
                )
                chunks.append(result.stdout.decode("utf-8", "replace"))
        except (OSError, subprocess.SubprocessError):
            return ""
    return "\n".join(chunks)[:500_000]


def _iso_date(year: str, month: str, day: str) -> date:
    return date(int(year), int(month), int(day))


def parse_receipt_text(text: str) -> list[ReceiptFact]:
    """Parse stable rail/air invoice text; incomplete facts are marked for review."""
    compact = re.sub(r"\s+", " ", text).strip()
    invoice = re.search(r"发票号码\s*[:：]?(?:[^0-9]{0,160})(\d{8,20})", compact)
    document_id = invoice.group(1) if invoice else ""
    amount_match = re.search(r"(?:票价|退票费)\s*[:：]?\s*￥?\s*([0-9]+(?:\.[0-9]{1,2})?)", compact)
    amount = amount_match.group(1) if amount_match else ""
    facts: list[ReceiptFact] = []
    if "登机" in compact or "BOARDING PASS" in compact.upper():
        flight = re.search(r"(?:航班号|Flight)\s*[:：]?\s*([A-Z0-9]{2}\d{2,4})", compact, re.IGNORECASE)
        travel_date_match = re.search(
            r"(?:航班日期|Flight Date|Date)\s*[:：]?\s*(20\d{2})[-/.]([01]?\d)[-/.]([0-3]?\d)", compact, re.IGNORECASE,
        )
        origin_match = re.search(r"\bFrom\s*[:：]?\s*([A-Z]{3})\b", compact, re.IGNORECASE)
        destination_match = re.search(r"\bTo\s*[:：]?\s*([A-Z]{3})\b", compact, re.IGNORECASE)
        origin_code = origin_match.group(1) if origin_match else ""
        destination_code = destination_match.group(1) if destination_match else ""
        facts.append(ReceiptFact(
            "boarding_pass", "", _iso_date(*travel_date_match.groups()) if travel_date_match else None,
            AIRPORT_CITIES.get(origin_code.upper(), origin_code.upper()),
            AIRPORT_CITIES.get(destination_code.upper(), destination_code.upper()),
            flight.group(1).upper() if flight else "", "",
            not all((travel_date_match, origin_match, destination_match, flight)),
        ))
        return facts
    if "铁路电子客票" in compact:
        route = re.search(
            r"([\u4e00-\u9fff]{1,12})\s*站\s*([\u4e00-\u9fff]{1,12})\s*站\s*([A-Z]\d{1,5})",
            compact,
        )
        train = route.group(3) if route else ""
        dates = re.findall(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", compact)
        travel_date = _iso_date(*dates[-1]) if dates else None
        is_refund = "退票费" in compact or re.search(r"\b退票\b", compact) is not None
        facts.append(ReceiptFact(
            "rail_refund" if is_refund else "rail_ticket", document_id, travel_date,
            route.group(1) if route else "", route.group(2) if route else "", train,
            amount, not all((travel_date, route, train)),
        ))
        return facts
    # Ctrip remarks may contain multiple numbered flight legs.
    flights = re.findall(
        r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})\s*"
        r"([\u4e00-\u9fff]{2,12})\s*[-—]\s*([\u4e00-\u9fff]{2,12})\s*([A-Z0-9]{2}\d{2,4})",
        compact,
    )
    if flights:
        is_refund = "退票费" in compact and "代订机票" not in compact
        for year, month, day, origin, destination, flight in flights:
            facts.append(ReceiptFact(
                "air_refund" if is_refund else "air_invoice", document_id,
                _iso_date(year, month, day), origin, destination, flight, amount,
                False,
            ))
        return facts
    if "住宿" in compact or "酒店" in compact:
        facts.append(ReceiptFact("hotel", document_id, None, "", "", "", amount, True))
    elif any(term in compact for term in NON_TRAVEL_TERMS):
        facts.append(ReceiptFact("non_travel_invoice", document_id, None, "", "", "", amount))
    elif invoice:
        facts.append(ReceiptFact("invoice_needs_review", document_id, None, "", "", "", amount, True))
    return facts


def parse_receipt_xml(content: bytes) -> list[ReceiptFact]:
    """Prefer the structured XBRL embedded in Chinese railway OFD documents."""
    if len(content) > 2 * 1024 * 1024:
        raise UnsafeArtifact("Invoice XML exceeds size limit")
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError:
        return parse_receipt_text(content.decode("utf-8", "replace"))
    values = {
        element.tag.rsplit("}", 1)[-1]: (element.text or "").strip()
        for element in root.iter()
        if (element.text or "").strip()
    }
    if values.get("TypeOfVoucher") == "电子发票（铁路电子客票）":
        date_value = values.get("TravelDate", "")
        try:
            travel_date = date.fromisoformat(date_value)
        except ValueError:
            travel_date = None
        kind = "rail_refund" if values.get("TypeOfBusiness") == "退" else "rail_ticket"
        fact = ReceiptFact(
            kind,
            values.get("ElectronicInvoiceRailwayETicketNumber", ""),
            travel_date,
            values.get("DepartureStation", ""),
            values.get("DestinationStation", ""),
            values.get("TrainNumber", ""),
            values.get("Fare", ""),
            not all((values.get("ElectronicInvoiceRailwayETicketNumber"), travel_date,
                     values.get("DepartureStation"), values.get("DestinationStation"),
                     values.get("TrainNumber"))),
        )
        return [fact]
    text = " ".join(values.values())
    return parse_receipt_text(text)
