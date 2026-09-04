from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import Any
from zoneinfo import ZoneInfo

from .errors import BridgeError

CITY_ALIASES = {
    "温州南": "温州",
    "温州北": "温州",
    "平阳": "温州",
    "鳌江": "温州",
    "苍南": "温州",
    "龙港": "温州",
    "瑞安": "温州",
    "乐清": "温州",
    "雁荡山": "温州",
    "武汉": "武汉",
    "汉口": "武汉",
    "武昌": "武汉",
    "武汉东": "武汉",
    "上海": "上海",
    "上海虹桥": "上海",
    "上海南": "上海",
    "上海西": "上海",
    "南京": "南京",
    "南京南": "南京",
    "江宁": "南京",
    "溧水": "南京",
    "高淳": "南京",
    "苏州": "苏州",
    "苏州北": "苏州",
    "苏州新区": "苏州",
    "苏州园区": "苏州",
    "深圳": "深圳",
    "深圳北": "深圳",
    "深圳东": "深圳",
    "福田": "深圳",
    "北京": "北京",
    "北京南": "北京",
    "北京西": "北京",
    "北京北": "北京",
    "北京朝阳": "北京",
    "广州": "广州",
    "广州南": "广州",
    "广州东": "广州",
    "广州北": "广州",
    "杭州": "杭州",
    "杭州东": "杭州",
    "杭州西": "杭州",
    "杭州南": "杭州",
    "宁波": "宁波",
    "宁波东": "宁波",
    "余姚": "宁波",
    "余姚北": "宁波",
    "成都": "成都",
    "成都东": "成都",
    "成都南": "成都",
    "成都西": "成都",
    "重庆": "重庆",
    "重庆北": "重庆",
    "重庆西": "重庆",
    "沙坪坝": "重庆",
}

TICKET_RE = re.compile(
    r"(?P<passenger>[\u4e00-\u9fff·]{2,20})[，,]\s*"
    r"(?P<year>20\d{2})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})开[，,]\s*"
    r"(?P<origin>[\u4e00-\u9fffA-Za-z0-9]+?)站?\s*[-—至到>]\s*"
    r"(?P<destination>[\u4e00-\u9fffA-Za-z0-9]+?)站?[，,]\s*"
    r"(?P<train>[A-Z]?[0-9]{1,5})次(?P<details>[^。\r\n]*)"
)
ORDER_RE = re.compile(r"订单(?:号码|号)?\s*[:：]?\s*([A-Z0-9]{8,20})", re.IGNORECASE)


class _MailText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"br", "p", "div", "tr", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "tr", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def email_text(body: str) -> str:
    body = unwrap_external(body)
    if re.search(r"<(?:html|body|div|p|table|br)\b", body, re.IGNORECASE):
        parser = _MailText()
        parser.feed(body)
        body = "".join(parser.parts)
    return body.replace("\xa0", " ")


def station_city(station: str, aliases: dict[str, str] | None = None) -> str:
    value = re.sub(r"(?:火车)?站$", "", station.strip())
    merged = {**CITY_ALIASES, **(aliases or {})}
    if value in merged:
        return merged[value]
    for suffix in ("东", "西", "南", "北"):
        if value.endswith(suffix) and value[:-1] in merged:
            return merged[value[:-1]]
    return value


def classify_mail(subject: str, body: str) -> str:
    # Only an explicit notification subject defines the operation. Footer policy,
    # quoted history and conditional text must never authorize a deletion.
    text = unwrap_external(subject).strip()
    if re.search(r"失败|申请|须知|说明|规则|提醒|未成功|待支付|取消订单|发票|报销|凭证|候补订单退单|12306历史邮件|OpenClaw测试", text):
        raise BridgeError("UNSUPPORTED_EMAIL", "Not a confirmed ticket transaction notice.")
    actions = set()
    if re.search(r"退票(?:成功|通知)|退款成功|用户退票", text):
        actions.add("cancel")
    if re.search(r"改签(?:成功|通知)|变更到站(?:成功|通知)|用户改签", text):
        actions.add("change")
    if re.search(r"支付通知|购票成功|成功购买|出票成功|候补订单兑现成功通知", text):
        actions.add("book")
    if len(actions) == 1:
        return actions.pop()
    if len(actions) > 1:
        raise BridgeError("CONFLICT", "The notification subject has conflicting operations.")
    raise BridgeError("UNSUPPORTED_EMAIL", "The email is not a recognized 12306 itinerary notice.")


def unwrap_external(value: str) -> str:
    """Remove gog's transport wrapper, not arbitrary text inside the email."""
    match = re.fullmatch(
        r'<<<EXTERNAL_UNTRUSTED_CONTENT id="([^"]+)">>>\nSource: [^\n]+\n---\n'
        r'(.*)\n<<<END_EXTERNAL_UNTRUSTED_CONTENT id="\1">>>',
        value.strip(), re.DOTALL,
    )
    return match.group(2) if match else value


def parse_ticket_details(details: str) -> dict[str, str]:
    tokens = [item.strip(" ，,") for item in re.split(r"[，,]", details) if item.strip(" ，,")]
    position = next(
        (item for item in tokens if re.fullmatch(r"\d{1,2}车(?:[A-Z0-9]+号|无座)", item)),
        "",
    )
    seat_class = next(
        (
            item
            for item in tokens
            if re.fullmatch(r"(?:商务座|特等座|优选一等座|一等座|二等座|软卧|硬卧|动卧|软座|硬座|无座)", item)
        ),
        "",
    )
    gate_token = next((item for item in tokens if item.startswith("检票口")), "")
    gate = gate_token.removeprefix("检票口").strip()
    if seat_class == "无座" and not position:
        position = "无座"
    return {"seatClass": seat_class, "seatPosition": position, "gate": gate}


def parse_segments(body: str, aliases: dict[str, str] | None = None) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    timezone = ZoneInfo("Asia/Shanghai")
    for match in TICKET_RE.finditer(body):
        raw = match.groupdict()
        try:
            departure = datetime(
                int(raw["year"]), int(raw["month"]), int(raw["day"]),
                int(raw["hour"]), int(raw["minute"]), tzinfo=timezone,
            )
        except ValueError as exc:
            raise BridgeError("PARSE_FAILED", "The ticket date or time is invalid.") from exc
        origin_station = raw["origin"].removesuffix("站")
        destination_station = raw["destination"].removesuffix("站")
        details = parse_ticket_details(raw.get("details") or "")
        segments.append(
            {
                "passenger": raw["passenger"],
                "departure": departure,
                "originStation": origin_station,
                "destinationStation": destination_station,
                "originCity": station_city(origin_station, aliases),
                "destinationCity": station_city(destination_station, aliases),
                "train": raw["train"].upper(),
                **details,
            }
        )
    if len(re.findall(r"20\d{2}年\d{1,2}月\d{1,2}日[^\n。]*?开", body)) > len(segments):
        raise BridgeError("PARSE_FAILED", "At least one ticket segment could not be parsed.")
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for segment in segments:
        key = tuple(segment[field] for field in (
            "passenger", "departure", "originStation", "destinationStation", "train"
        ))
        if key in unique and unique[key] != segment:
            raise BridgeError("CONFLICT", "Conflicting copies of a ticket were found.")
        unique[key] = segment
    return list(unique.values())


def merge_segments(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for segment in segments:
        groups.setdefault(segment["passenger"], []).append(segment)
    itineraries: list[dict[str, Any]] = []
    for passenger, items in groups.items():
        items.sort(key=lambda item: item["departure"])
        current: list[dict[str, Any]] = []
        for item in items:
            if current:
                previous = current[-1]
                connected = (
                    previous["destinationStation"] == item["originStation"]
                    or previous["destinationCity"] == item["originCity"]
                )
                plausible = (
                    timedelta(0) <= item["departure"] - previous["departure"] <= timedelta(hours=24)
                )
                if not (connected and plausible):
                    itineraries.append(_itinerary(passenger, current))
                    current = []
            current.append(item)
        if current:
            itineraries.append(_itinerary(passenger, current))
    return itineraries


def _itinerary(passenger: str, segments: list[dict[str, Any]]) -> dict[str, Any]:
    first, last = segments[0], segments[-1]
    return {
        "passenger": passenger,
        "originCity": first["originCity"],
        "destinationCity": last["destinationCity"],
        "start": first["departure"],
        "end": last["departure"] + timedelta(minutes=10),
        "segments": segments,
    }


def format_itinerary_notes(
    itinerary: dict[str, Any], marker: str, *, timetable_status: str
) -> str:
    lines = [marker]
    for index, segment in enumerate(itinerary["segments"], start=1):
        seat = " ".join(
            value for value in (segment.get("seatClass"), segment.get("seatPosition")) if value
        ) or "座位待定"
        gate = segment.get("gate") or "待定"
        departure = segment["departure"]
        arrival = segment.get("arrival") or departure + timedelta(minutes=10)
        time_range = (
            f"{departure.strftime('%Y-%m-%d %H:%M')}–"
            f"{arrival.strftime('%Y-%m-%d %H:%M')}"
        )
        if timetable_status != "resolved":
            time_range += "（时刻表待补充）"
        lines.append(
            f"{index}. {segment['train']}｜{segment['originStation']}→"
            f"{segment['destinationStation']}｜{seat}｜检票口 {gate}｜{time_range}"
        )
    lines.append("from OpenClaw US1")
    return "\n".join(lines)


def plan_email(params: dict[str, Any]) -> dict[str, Any]:
    subject = str(params.get("subject") or "")
    body = str(params.get("body") or "")
    message_id = str(params.get("messageId") or "")
    if not message_id or not body or len(body) > 200_000:
        raise BridgeError("INVALID_REQUEST", "messageId and a bounded email body are required.")
    action = classify_mail(subject, body)
    body = email_text(body)
    segments = parse_segments(body, params.get("stationCityAliases"))
    if not segments:
        raise BridgeError("PARSE_FAILED", "No complete 12306 ticket segment was found.")
    orders = {match.group(1).upper() for match in ORDER_RE.finditer(body)}
    if len(orders) != 1:
        raise BridgeError("PARSE_FAILED", "Exactly one unambiguous order ID is required.")
    order_id = orders.pop()
    plans: list[dict[str, Any]] = []
    itineraries = merge_segments(segments)
    passengers = [item["passenger"] for item in itineraries]
    if len(passengers) != len(set(passengers)):
        raise BridgeError("CONFLICT", "Disconnected journeys in one order require review.")
    for itinerary in itineraries:
        passenger_key = hashlib.sha256(itinerary["passenger"].encode()).hexdigest()[:12]
        marker = f"[OpenClaw:12306 order={order_id} passenger={passenger_key}]"
        route = f"{itinerary['originCity']}→{itinerary['destinationCity']}"
        operation = (
            "delete"
            if action == "cancel"
            else ("reconcile-update" if action == "change" else "upsert")
        )
        plans.append(
            {
                "operation": operation,
                "lookup": {"marker": marker, "orderId": order_id, "passengerKey": passenger_key},
                "event": {
                    "title": f"火车行程：{route}",
                    "start": itinerary["start"].isoformat(),
                    "end": itinerary["end"].isoformat(),
                    "timezone": "Asia/Shanghai",
                    "location": route,
                    "notes": format_itinerary_notes(
                        itinerary, marker, timetable_status="pending"
                    ),
                },
                "segments": len(itinerary["segments"]),
                "segmentDetails": [
                    {**segment, "departure": segment["departure"].isoformat()}
                    for segment in itinerary["segments"]
                ],
                "timetableStatus": "pending",
            }
        )
    return {
        "source": "12306",
        "messageId": message_id,
        "mailAction": action,
        "orderId": order_id,
        "plans": plans,
    }
