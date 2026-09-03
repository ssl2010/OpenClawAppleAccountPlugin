from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pyicloud import PyiCloudService
from pyicloud.services.calendar import EventObject

from .errors import BridgeError, classify_exception
from .models import normalize_calendar, normalize_event, parse_rfc3339


class ICloudProvider:
    def __init__(
        self, config: dict[str, Any], service_factory: Callable[..., Any] = PyiCloudService
    ) -> None:
        self.config = config
        self.service_factory = service_factory

    def _service(self) -> Any:
        apple_id = os.environ.get(str(self.config.get("appleIdEnv", "ICLOUD_APPLE_ID")), "").strip()
        password_file = self.config.get("passwordFile") or os.environ.get("ICLOUD_PASSWORD_FILE")
        password = ""
        if password_file:
            path = Path(str(password_file)).expanduser()
            if not path.is_file():
                raise BridgeError("AUTH_REQUIRED", "Configured Apple password file is unavailable.")
            password = path.read_text(encoding="utf-8").rstrip("\r\n")
        if not apple_id:
            raise BridgeError("AUTH_REQUIRED", "Apple account is not configured.")
        session_dir = Path(
            str(
                self.config.get("sessionDirectory")
                or "~/.local/state/openclaw-apple-account/session"
            )
        ).expanduser()
        session_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        session_dir.chmod(0o700)
        try:
            service = self.service_factory(
                apple_id,
                password,
                cookie_directory=str(session_dir),
                china_mainland=self.config.get("region") == "china",
            )
            # pyiCloud leaves many request timeouts unset.  Bound every request on
            # this service instance so a transient Apple endpoint cannot hang the
            # OpenClaw gateway or the mail worker indefinitely.
            session = getattr(service, "session", None)
            if session is not None and callable(getattr(session, "request", None)):
                original_request = session.request
                request_timeout = float(self.config.get("requestTimeoutSeconds", 20))

                def bounded_request(method: str, url: str, **kwargs: Any) -> Any:
                    if kwargs.get("timeout") is None:
                        kwargs["timeout"] = request_timeout
                    return original_request(method, url, **kwargs)

                session.request = bounded_request
            if getattr(service, "requires_2fa", False):
                raise BridgeError(
                    "TWO_FACTOR_REQUIRED", "Apple two-factor authentication is required."
                )
            if getattr(service, "requires_2sa", False):
                raise BridgeError("TWO_STEP_REQUIRED", "Apple two-step authentication is required.")
            return service
        except BridgeError:
            raise
        except Exception as exc:
            raise classify_exception(exc) from exc

    def status(self) -> dict[str, Any]:
        service = self._service()
        return {
            "provider": "pyicloud",
            "status": "healthy",
            "authenticated": bool(getattr(service, "is_trusted_session", True)),
            "capabilities": [
                "calendar.read",
                "calendar.create",
                "calendar.update",
                "calendar.delete",
            ],
        }

    def list_calendars(self) -> list[dict[str, Any]]:
        return [
            normalize_calendar(item)
            for item in self._service().calendar.get_calendars(as_objs=False)
        ]

    def list_events(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        start = parse_rfc3339(str(params["start"]))
        end = parse_rfc3339(str(params["end"]))
        if start >= end:
            raise BridgeError("INVALID_REQUEST", "start must be before end.")
        limit = min(max(int(params.get("limit", 100)), 1), 500)
        events = self._service().calendar.get_events(start, end, as_objs=False)
        calendar_ids = {str(x) for x in params.get("calendarIds", [])}
        normalized = [normalize_event(item) for item in events]
        if calendar_ids:
            normalized = [item for item in normalized if item["calendarId"] in calendar_ids]
        query = str(params.get("query", "")).casefold().strip()
        if query:
            normalized = [
                item
                for item in normalized
                if query in (item["title"] + "\n" + item["notes"]).casefold()
            ]
        return normalized[:limit]

    def get_event(self, params: dict[str, Any]) -> dict[str, Any]:
        raw = self._service().calendar.get_event_detail(
            str(params["calendarId"]), str(params["eventId"]), as_obj=False
        )
        return normalize_event(raw)

    def create_event(self, params: dict[str, Any]) -> dict[str, Any]:
        service = self._service()
        event = EventObject(
            pguid=str(params["calendarId"]),
            title=str(params["title"]),
            start_date=parse_rfc3339(str(params["start"])),
            end_date=parse_rfc3339(str(params["end"])),
            tz=str(params.get("timezone") or "Asia/Shanghai"),
            all_day=bool(params.get("allDay", False)),
            location=str(params.get("location") or ""),
            guid=str(params.get("eventId") or ""),
        )
        response = self._save_event(service.calendar, event, params)
        return self._mutation_result("created", event, response)

    def update_event(self, params: dict[str, Any]) -> dict[str, Any]:
        service = self._service()
        raw = service.calendar.get_event_detail(
            str(params["calendarId"]), str(params["eventId"]), as_obj=False
        )
        current = normalize_event(raw)
        start = parse_rfc3339(str(params.get("start") or current["start"]))
        end = parse_rfc3339(str(params.get("end") or current["end"]))
        event = EventObject(
            pguid=current["calendarId"],
            guid=current["eventId"],
            etag=current["etag"] or None,
            title=str(params.get("title") or current["title"]),
            start_date=start,
            end_date=end,
            tz=str(params.get("timezone") or current["timezone"] or "Asia/Shanghai"),
            all_day=bool(params.get("allDay", current["allDay"])),
            location=str(params.get("location", current["location"])),
        )
        merged = {**current, **params}
        response = self._save_event(service.calendar, event, merged)
        return self._mutation_result("updated", event, response)

    def delete_event(self, params: dict[str, Any]) -> dict[str, Any]:
        service = self._service()
        raw = service.calendar.get_event_detail(
            str(params["calendarId"]), str(params["eventId"]), as_obj=False
        )
        current = normalize_event(raw)
        event = EventObject(
            pguid=current["calendarId"],
            guid=current["eventId"],
            etag=current["etag"] or None,
            title=current["title"],
        )
        response = service.calendar.remove_event(event)
        return self._mutation_result("deleted", event, response)

    @staticmethod
    def _save_event(calendar: Any, event: EventObject, params: dict[str, Any]) -> dict[str, Any]:
        data = event.request_data
        data["ClientState"]["Collection"][0]["ctag"] = calendar.get_ctag(event.pguid)
        data["Event"]["description"] = str(params.get("notes") or "")
        data["Event"]["url"] = str(params.get("url") or "")
        request_params = calendar.default_params
        response = calendar.session.post(
            f"{calendar._calendar_refresh_url}/{event.pguid}/{event.guid}",
            params=request_params,
            json=data,
        )
        result = response.json()
        if result.get("serviceErrors"):
            raise BridgeError("UPSTREAM_CHANGED", "Apple rejected the calendar mutation.")
        return result

    @staticmethod
    def _mutation_result(
        action: str, event: EventObject, response: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "action": action,
            "provider": "pyicloud",
            "calendarId": event.pguid,
            "eventId": event.guid,
            "committed": True,
        }
