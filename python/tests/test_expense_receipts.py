from __future__ import annotations

import io
import zipfile
from email.message import EmailMessage

import pytest

from openclaw_apple_bridge.expense_receipts import (
    UnsafeArtifact,
    inventory_rfc822,
    mail_disposition,
    parse_receipt_text,
    parse_receipt_xml,
)


def raw_mail(subject: str, attachments: list[tuple[str, bytes]] | None = None) -> bytes:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = "sender@example.com"
    message.set_content("正文")
    for name, content in attachments or []:
        message.add_attachment(content, maintype="application", subtype="octet-stream", filename=name)
    return message.as_bytes()


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return stream.getvalue()


def test_octet_stream_eml_is_recursed() -> None:
    nested = raw_mail("网上购票系统-电子发票通知", [("ticket.pdf", b"pdf")])
    result = inventory_rfc822(raw_mail("forward", [("invoice.eml", nested)]))
    assert [item.subject for item in result.evidence] == ["forward", "网上购票系统-电子发票通知"]
    assert [(item.name, item.content) for item in result.artifacts] == [("ticket.pdf", b"pdf")]


def test_bounded_zip_inventory_and_paths() -> None:
    result = inventory_rfc822(raw_mail("invoice", [("receipt.zip", zip_bytes({"x/ticket.pdf": b"pdf"}))]))
    assert {item.name for item in result.artifacts} == {"receipt.zip", "ticket.pdf"}
    with pytest.raises(UnsafeArtifact, match="path"):
        inventory_rfc822(raw_mail("invoice", [("receipt.zip", zip_bytes({"../escape": b"x"}))]))


@pytest.mark.parametrize(
    ("subject", "sender", "expected"),
    [
        ("openclaw票据报销测试4", "owner", "test_bundle"),
        ("网上购票系统-电子发票通知", "12306@rails.com.cn", "travel_candidate"),
        ("行程乘机凭证", "航旅纵横", "travel_candidate"),
        ("您入住酒店的电子发票", "trip.com", "travel_candidate"),
        ("中国计算机学会电子发票", "conf", "non_travel_invoice"),
        ("保险产品电子发票", "insurer", "non_travel_invoice"),
        ("电子发票下载", "unknown", "invoice_needs_review"),
        ("项目会议", "coworker", "ordinary"),
    ],
)
def test_mail_disposition(subject: str, sender: str, expected: str) -> None:
    assert mail_disposition(subject, sender) == expected


def test_generic_invoice_is_not_suppressed_as_travel() -> None:
    assert mail_disposition("餐饮电子发票", "restaurant") == "non_travel_invoice"


def test_known_ctrip_air_sender_is_travel_without_subject_keyword() -> None:
    assert mail_disposition("携程: 电子报销凭证", "携程 <a_rsv@trip.com>") == "travel_candidate"


def test_nontravel_priority_is_not_contaminated_by_attachment_names() -> None:
    assert mail_disposition("保险产品电子发票", "insurer", attachment_names=["ticket.pdf"]) == "non_travel_invoice"


def test_parse_rail_ticket_and_refund() -> None:
    base = "发票号码:26429121050004148690 汉口站 上海虹桥站 G1738 2026年08月12日 08:13开 票价: ￥547.00 电子发票（铁路电子客票）"
    fact = parse_receipt_text(base)[0]
    assert (fact.kind, fact.origin, fact.destination, fact.service_number) == ("rail_ticket", "汉口", "上海虹桥", "G1738")
    assert fact.travel_date == __import__("datetime").date(2026, 8, 12) and not fact.needs_review
    assert parse_receipt_text(base.replace("票价", "退票费") + " 退票")[0].kind == "rail_refund"


def test_parse_multileg_air_invoice_and_refund() -> None:
    fare = "发票号码:26447000000546202990 *代订机票* 携程订单:1,(1) 2025/12/17 大连-北京 CZ6121 (2) 2025/12/17 北京-武汉 CZ5662"
    facts = parse_receipt_text(fare)
    assert [(x.origin, x.destination, x.service_number) for x in facts] == [("大连", "北京", "CZ6121"), ("北京", "武汉", "CZ5662")]
    refund = "发票号码:26317000000906884501 *退票费* 2026/2/3 武汉-温州 CZ6707"
    assert parse_receipt_text(refund)[0].kind == "air_refund"


def test_unknown_invoice_and_hotel_fail_closed() -> None:
    hotel = parse_receipt_text("发票号码:12345678 *住宿服务*住宿费")[0]
    assert hotel.kind == "hotel" and hotel.needs_review
    assert parse_receipt_text("发票号码:12345678 普通服务")[0].kind == "invoice_needs_review"


def test_parse_boarding_pass_ocr_text() -> None:
    text = "登机牌 BOARDING PASS 航班号 Flight: HU7820 出发地 From WNZ 到达地 To WUH 航班日期 Date: 2026.08.14"
    fact = parse_receipt_text(text)[0]
    assert (fact.kind, fact.origin, fact.destination, fact.service_number) == ("boarding_pass", "温州", "武汉", "HU7820")
    assert not fact.needs_review


def test_parse_structured_rail_xbrl() -> None:
    xml = b'''<x xmlns:rai="urn:rai"><rai:TypeOfVoucher>\xe7\x94\xb5\xe5\xad\x90\xe5\x8f\x91\xe7\xa5\xa8\xef\xbc\x88\xe9\x93\x81\xe8\xb7\xaf\xe7\x94\xb5\xe5\xad\x90\xe5\xae\xa2\xe7\xa5\xa8\xef\xbc\x89</rai:TypeOfVoucher><rai:ElectronicInvoiceRailwayETicketNumber>26429221050000224509</rai:ElectronicInvoiceRailwayETicketNumber><rai:TypeOfBusiness>\xe9\x80\x80</rai:TypeOfBusiness><rai:DepartureStation>\xe6\xb1\x89\xe5\x8f\xa3</rai:DepartureStation><rai:DestinationStation>\xe4\xb8\x8a\xe6\xb5\xb7\xe8\x99\xb9\xe6\xa1\xa5</rai:DestinationStation><rai:TrainNumber>G1738</rai:TrainNumber><rai:TravelDate>2026-08-12</rai:TravelDate><rai:Fare>109.50</rai:Fare></x>'''
    fact = parse_receipt_xml(xml)[0]
    assert (fact.kind, fact.origin, fact.destination, fact.service_number) == ("rail_refund", "\u6c49\u53e3", "\u4e0a\u6d77\u8679\u6865", "G1738")
    assert not fact.needs_review
