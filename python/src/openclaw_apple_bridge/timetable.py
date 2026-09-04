from __future__ import annotations

import re
from datetime import date as date_type
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests

from .errors import BridgeError

STATIONS_URL = "https://kyfw.12306.cn/otn/resources/js/framework/station_name.js"
LEFT_TICKET_INIT_URL = "https://kyfw.12306.cn/otn/leftTicket/init"
LEFT_TICKET_QUERY_URL = "https://kyfw.12306.cn/otn/leftTicket/query"
STATION_RE = re.compile(r"@[^|]*\|(?P<name>[^|]+)\|(?P<code>[A-Z0-9]+)\|")


class RailwayTimetable:
    """Bounded, read-only access to the official 12306 public query pages."""

    def __init__(self, *, timeout_seconds: float = 20, session: Any | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (compatible; OpenClawAppleAccountPlugin/0.1)",
                "Referer": LEFT_TICKET_INIT_URL,
            }
        )
        self._stations: dict[str, str] | None = None
        self._initialized = False

    def _initialize(self) -> None:
        if self._initialized:
            return
        response = self.session.get(LEFT_TICKET_INIT_URL, timeout=self.timeout_seconds)
        response.raise_for_status()
        self._initialized = True

    def _station_codes(self) -> dict[str, str]:
        if self._stations is not None:
            return self._stations
        response = self.session.get(STATIONS_URL, timeout=self.timeout_seconds)
        response.raise_for_status()
        stations = {
            match.group("name"): match.group("code") for match in STATION_RE.finditer(response.text)
        }
        if len(stations) < 100:
            raise BridgeError("TIMETABLE_UNAVAILABLE", "The official station list was incomplete.")
        self._stations = stations
        return stations

    def lookup(self, params: dict[str, Any]) -> dict[str, Any]:
        travel_date = str(params.get("travelDate") or "")
        train_number = str(params.get("trainNumber") or "").strip().upper()
        origin = str(params.get("originStation") or "").removesuffix("站").strip()
        destination = str(params.get("destinationStation") or "").removesuffix("站").strip()
        try:
            date = date_type.fromisoformat(travel_date)
        except ValueError as exc:
            raise BridgeError("INVALID_REQUEST", "travelDate must use YYYY-MM-DD.") from exc
        if not re.fullmatch(r"[A-Z]?[0-9]{1,5}", train_number):
            raise BridgeError("INVALID_REQUEST", "trainNumber is invalid.")
        try:
            stations = self._station_codes()
            from_code, to_code = stations[origin], stations[destination]
            self._initialize()
            response = self.session.get(
                LEFT_TICKET_QUERY_URL,
                params={
                    "leftTicketDTO.train_date": travel_date,
                    "leftTicketDTO.from_station": from_code,
                    "leftTicketDTO.to_station": to_code,
                    "purpose_codes": "ADULT",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("data", {}).get("result", [])
        except KeyError as exc:
            raise BridgeError("TIMETABLE_NOT_FOUND", "A station was not found by 12306.") from exc
        except BridgeError:
            raise
        except Exception as exc:
            raise BridgeError(
                "TIMETABLE_UNAVAILABLE",
                "The official 12306 timetable query failed.",
                retryable=True,
            ) from exc

        for encoded in rows:
            fields = str(encoded).split("|")
            if len(fields) < 14:
                continue
            if fields[3].upper() != train_number or fields[6] != from_code or fields[7] != to_code:
                continue
            try:
                depart_clock = time.fromisoformat(fields[8])
                hours, minutes = (int(value) for value in fields[10].split(":"))
            except (ValueError, IndexError) as exc:
                raise BridgeError(
                    "TIMETABLE_UNAVAILABLE", "12306 returned an invalid timetable row."
                ) from exc
            departure = datetime.combine(date, depart_clock, ZoneInfo("Asia/Shanghai"))
            arrival = departure + timedelta(hours=hours, minutes=minutes)
            return {
                "source": "12306-official",
                "travelDate": travel_date,
                "trainNumber": train_number,
                "originStation": origin,
                "destinationStation": destination,
                "departure": departure.isoformat(),
                "arrival": arrival.isoformat(),
                "durationMinutes": hours * 60 + minutes,
                "confidence": "official-schedule",
            }
        raise BridgeError("TIMETABLE_NOT_FOUND", "No exact official timetable match was found.")
