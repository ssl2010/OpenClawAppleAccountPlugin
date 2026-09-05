from datetime import date

from openclaw_apple_bridge.expense_receipts import ReceiptFact
from openclaw_apple_bridge.expense_trip import reconcile_trips


def fact(kind: str, day: int, origin: str, destination: str, service: str) -> ReceiptFact:
    return ReceiptFact(kind, kind + service, date(2026, 8, day), origin, destination, service, "100")


def test_simple_round_trip_and_folder_name() -> None:
    plans, unresolved = reconcile_trips([
        fact("air_invoice", 12, "武汉", "温州", "HU7819"),
        fact("boarding_pass", 12, "武汉", "温州", "HU7819"),
        fact("air_invoice", 14, "温州", "武汉", "HU7820"),
        fact("boarding_pass", 14, "温州", "武汉", "HU7820"),
    ])
    assert not unresolved and len(plans) == 1
    assert plans[0].folder_name == "08月12日温州"
    assert not plans[0].missing_boarding and not plans[0].needs_review


def test_refunded_alternative_does_not_cancel_executed_other_flight() -> None:
    plans, _ = reconcile_trips([
        fact("air_refund", 12, "武汉", "温州", "CZ6707"),
        fact("air_invoice", 12, "武汉", "温州", "HU7819"),
        fact("boarding_pass", 12, "武汉", "温州", "HU7819"),
        fact("air_invoice", 14, "温州", "武汉", "HU7820"),
        fact("boarding_pass", 14, "温州", "武汉", "HU7820"),
    ])
    assert [item.service_number for item in plans[0].segments] == ["HU7819", "HU7820"]
    assert plans[0].refunds[0].service_number == "CZ6707"


def test_missing_boarding_is_reported_but_trip_can_close() -> None:
    plans, _ = reconcile_trips([
        fact("air_invoice", 12, "武汉", "温州", "HU7819"),
        fact("air_invoice", 14, "温州", "武汉", "HU7820"),
        fact("boarding_pass", 14, "温州", "武汉", "HU7820"),
    ])
    assert [item.service_number for item in plans[0].missing_boarding] == ["HU7819"]


def test_incomplete_or_disconnected_route_is_not_closed() -> None:
    plans, unresolved = reconcile_trips([fact("rail_ticket", 12, "武汉", "上海虹桥", "G1738")])
    assert not plans and unresolved


def test_multi_city_requires_destination_review() -> None:
    plans, _ = reconcile_trips([
        fact("rail_ticket", 12, "武汉", "南京南", "G1"),
        fact("rail_ticket", 13, "南京南", "上海虹桥", "G2"),
        fact("rail_ticket", 15, "上海虹桥", "武汉", "G3"),
    ])
    assert plans[0].destinations == ("南京", "上海") and plans[0].needs_review


def test_exact_refund_without_boarding_removes_segment() -> None:
    plans, unresolved = reconcile_trips([
        fact("air_invoice", 12, "武汉", "温州", "CZ6707"),
        fact("air_refund", 12, "武汉", "温州", "CZ6707"),
    ])
    assert not plans and not unresolved


def test_distant_return_does_not_close_old_outbound() -> None:
    plans, unresolved = reconcile_trips([
        fact("air_invoice", 1, "武汉", "温州", "OUT"),
        ReceiptFact("air_invoice", "later", date(2026, 10, 1), "温州", "武汉", "BACK", "100"),
    ])
    assert not plans and len(unresolved) == 2
