"""Pure trip reconciliation. It never writes files or calls external services."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .expense_receipts import ReceiptFact
from .rail12306 import station_city


@dataclass(frozen=True)
class TripSegment:
    kind: str
    travel_date: date
    origin: str
    destination: str
    service_number: str
    document_id: str


@dataclass(frozen=True)
class TripPlan:
    start_date: date
    end_date: date
    destinations: tuple[str, ...]
    segments: tuple[TripSegment, ...]
    refunds: tuple[ReceiptFact, ...]
    missing_boarding: tuple[TripSegment, ...]
    needs_review: bool

    @property
    def folder_name(self) -> str:
        return f"{self.start_date:%m月%d日}" + "、".join(self.destinations)


def _city(value: str) -> str:
    return station_city(value).removesuffix("机场")


def _key(fact: ReceiptFact) -> tuple[date | None, str, str, str]:
    return (fact.travel_date, _city(fact.origin), _city(fact.destination), fact.service_number)


def reconcile_trips(facts: list[ReceiptFact], *, max_trip_days: int = 30) -> tuple[list[TripPlan], list[ReceiptFact]]:
    """Build only connected Wuhan round trips; return unresolved evidence separately."""
    unique: dict[tuple[str, date | None, str, str, str, str], ReceiptFact] = {}
    for fact in facts:
        unique_key = (fact.kind, fact.travel_date, _city(fact.origin), _city(fact.destination),
                      fact.service_number, fact.document_id)
        unique[unique_key] = fact
    values = list(unique.values())
    invoices = [fact for fact in values if fact.kind == "air_invoice" and fact.travel_date]
    boarding: set[tuple[date | None, str, str, str]] = set()
    for credential in (fact for fact in values if fact.kind == "boarding_pass"):
        matches = [
            invoice for invoice in invoices
            if (not credential.travel_date or credential.travel_date == invoice.travel_date)
            and (not credential.origin or _city(credential.origin) == _city(invoice.origin))
            and (not credential.destination or _city(credential.destination) == _city(invoice.destination))
            and (not credential.service_number or credential.service_number == invoice.service_number)
        ]
        if len(matches) == 1:
            boarding.add(_key(matches[0]))
        elif not credential.needs_review:
            boarding.add(_key(credential))
    refunds = list({(_key(fact), fact.document_id): fact for fact in values if fact.kind in {"rail_refund", "air_refund"}}.values())
    refunded = {_key(fact) for fact in refunds}
    segment_map: dict[tuple[date | None, str, str, str], TripSegment] = {}
    missing: set[tuple[date | None, str, str, str]] = set()
    for fact in values:
        if fact.kind not in {"rail_ticket", "air_invoice"} or not fact.travel_date:
            continue
        fact_key = _key(fact)
        if fact.kind == "air_invoice" and fact_key in refunded and fact_key not in boarding:
            continue
        segment = TripSegment(fact.kind, fact.travel_date, fact_key[1], fact_key[2],
                              fact.service_number, fact.document_id)
        existing_segment = segment_map.get(fact_key)
        if existing_segment is None or (not existing_segment.document_id and segment.document_id):
            segment_map[fact_key] = segment
        if fact.kind == "air_invoice" and fact_key not in boarding:
            missing.add(fact_key)
    segments = sorted(segment_map.values(), key=lambda item: (
        item.travel_date, item.origin != "武汉", item.origin, item.destination,
        item.service_number,
    ))
    plans: list[TripPlan] = []
    unresolved: list[ReceiptFact] = [
        fact for fact in values
        if fact.needs_review and fact.kind not in {"boarding_pass", "air_invoice"}
    ]
    remaining = list(segments)
    while remaining:
        starts = [item for item in remaining if item.origin == "武汉"]
        if not starts:
            break
        first = min(starts, key=lambda item: item.travel_date)
        chain = [first]
        remaining.remove(first)
        city_cursor = first.destination
        ambiguous = False
        while city_cursor != "武汉":
            choices = [
                item for item in remaining
                if item.origin == city_cursor and chain[-1].travel_date <= item.travel_date
                <= first.travel_date + timedelta(days=max_trip_days)
            ]
            if not choices:
                ambiguous = True
                break
            earliest = min(item.travel_date for item in choices)
            choices = [item for item in choices if item.travel_date == earliest]
            if len(choices) != 1:
                ambiguous = True
                break
            item = choices[0]
            chain.append(item)
            remaining.remove(item)
            city_cursor = item.destination
        if city_cursor != "武汉":
            # Do not emit an incomplete directory; preserve its facts for review.
            for item in chain:
                unresolved.append(ReceiptFact(item.kind, item.document_id, item.travel_date,
                                              item.origin, item.destination, item.service_number,
                                              "", True))
            continue
        destinations = tuple(dict.fromkeys(item.destination for item in chain if item.destination != "武汉"))
        # With date-only evidence, intermediate cities may be transfers; require review.
        multi_city_uncertain = len(destinations) > 1
        related_refunds = tuple(
            fact for fact in refunds
            if fact.travel_date and chain[0].travel_date - timedelta(days=2)
            <= fact.travel_date <= chain[-1].travel_date + timedelta(days=2)
            and ({_city(fact.origin), _city(fact.destination)} & ({"武汉"} | set(destinations)))
        )
        plans.append(TripPlan(
            chain[0].travel_date, chain[-1].travel_date, destinations, tuple(chain),
            related_refunds,
            tuple(item for item in chain if (item.travel_date, item.origin, item.destination,
                                              item.service_number) in missing),
            ambiguous or multi_city_uncertain,
        ))
    for item in remaining:
        unresolved.append(ReceiptFact(item.kind, item.document_id, item.travel_date,
                                      item.origin, item.destination, item.service_number, "", True))
    return plans, unresolved
