from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pyicloud import PyiCloudService
from pyicloud.exceptions import PyiCloudAPIResponseException
from pyicloud.services.calendar import EventObject

from .errors import BridgeError, classify_exception
from .models import normalize_calendar, normalize_event, parse_rfc3339
from .reminder_alarm import add_date_alarm


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
                "reminders.read",
                "reminders.create",
                "reminders.update",
                "reminders.complete",
                "reminders.delete",
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
        return self._mutation_result("created", event, response, service.calendar, params)

    def update_event(self, params: dict[str, Any]) -> dict[str, Any]:
        service = self._service()
        raw = service.calendar.get_event_detail(
            str(params["calendarId"]), str(params["eventId"]), as_obj=False
        )
        current = normalize_event(raw)
        self._assert_identity(current, params)
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
        return self._mutation_result("updated", event, response, service.calendar, merged)

    def delete_event(self, params: dict[str, Any]) -> dict[str, Any]:
        service = self._service()
        raw = service.calendar.get_event_detail(
            str(params["calendarId"]), str(params["eventId"]), as_obj=False
        )
        current = normalize_event(raw)
        self._assert_identity(current, params)
        event = EventObject(
            pguid=current["calendarId"],
            guid=current["eventId"],
            etag=current["etag"] or None,
            title=current["title"],
            start_date=parse_rfc3339(str(current["start"])),
            end_date=parse_rfc3339(str(current["end"])),
        )
        response = service.calendar.remove_event(event)
        return self._mutation_result("deleted", event, response, service.calendar, params)

    def list_reminder_lists(self) -> list[dict[str, Any]]:
        return [
            {"id": item.id, "title": item.title, "count": item.count}
            for item in self._service().reminders.lists()
            if not item.is_group
        ]

    def list_reminders(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        limit = min(max(int(params.get("limit", 50)), 1), 200)
        batch = self._service().reminders.list_reminders(
            list_id=str(params["listId"]),
            include_completed=bool(params.get("includeCompleted", False)),
            results_limit=limit,
        )
        return [self._normalize_reminder(item) for item in batch.reminders[:limit]]

    def get_reminder(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._normalize_reminder(
            self._service().reminders.get(str(params["reminderId"]))
        )

    def create_reminder(self, params: dict[str, Any]) -> dict[str, Any]:
        service = self._service().reminders
        actual_at, due_at, notes = self._reminder_schedule(params)
        reminder = service.create(
            list_id=str(params["listId"]), title=str(params["title"]), desc=notes,
            due_date=due_at, priority=1 if params.get("urgent") else 0,
            flagged=False, all_day=bool(params.get("allDay", False)),
            time_zone=str(params.get("timezone") or "Asia/Shanghai"),
        )
        advance = int(params.get("remindMinutesBefore", 0))
        if actual_at and (params.get("urgent") or "remindMinutesBefore" in params):
            try:
                add_date_alarm(
                    service, reminder, actual_at - timedelta(minutes=advance),
                    str(params.get("timezone") or "Asia/Shanghai"),
                )
            except Exception as exc:
                raise BridgeError(
                    "MUTATION_UNKNOWN",
                    "Reminder exists, but its native Apple alarm needs reconciliation.",
                ) from exc
        expected = {
            "listId": str(params["listId"]), "title": str(params["title"]),
            "notes": notes, "dueAt": due_at.isoformat() if due_at else None,
            "urgent": bool(params.get("urgent")), "flagged": False,
        }
        return self._reminder_mutation_result(
            "created", service, reminder.id, expected,
            actual_at=actual_at, advance=advance,
        )

    def update_reminder(self, params: dict[str, Any]) -> dict[str, Any]:
        service = self._service().reminders
        reminder = service.get(str(params["reminderId"]))
        if reminder.id != str(params["reminderId"]):
            raise BridgeError("CONFLICT", "Apple returned a different reminder.")
        if reminder.alarm_ids and any(
            key in params for key in ("time", "remindMinutesBefore", "urgent", "allDay", "timezone")
        ):
            raise BridgeError(
                "INVALID_REQUEST",
                "Changing the schedule of an existing native alarm is not supported safely; "
                "create a replacement reminder after explicit confirmation.",
            )
        actual_at, due_at, notes = self._reminder_schedule(
            params,
            default_actual=reminder.due_date,
            default_notes=reminder.desc,
        )
        reminder.title = str(params.get("title", reminder.title))
        reminder.desc = notes
        reminder.due_date = due_at
        urgent = bool(params.get("urgent", reminder.priority == 1 or reminder.flagged))
        reminder.priority = 1 if urgent else 0
        reminder.flagged = False
        reminder.all_day = bool(params.get("allDay", reminder.all_day))
        reminder.time_zone = str(params.get("timezone") or reminder.time_zone or "Asia/Shanghai")
        service.update(reminder)
        advance = int(params.get("remindMinutesBefore", 0))
        if actual_at and not reminder.alarm_ids and (
            urgent or "remindMinutesBefore" in params
        ):
            try:
                add_date_alarm(
                    service, reminder, actual_at - timedelta(minutes=advance),
                    reminder.time_zone,
                )
            except Exception as exc:
                raise BridgeError(
                    "MUTATION_UNKNOWN",
                    "Reminder was updated, but its native Apple alarm needs reconciliation.",
                ) from exc
        return self._reminder_mutation_result(
            "updated", service, reminder.id,
            {"listId": reminder.list_id, "title": reminder.title, "notes": notes,
             "dueAt": due_at.isoformat() if due_at else None, "urgent": urgent},
            actual_at=actual_at, advance=advance,
        )

    def complete_reminder(self, params: dict[str, Any]) -> dict[str, Any]:
        service = self._service().reminders
        reminder = service.get(str(params["reminderId"]))
        reminder.completed = bool(params.get("completed", True))
        service.update(reminder)
        actual = service.get(reminder.id)
        if actual.id != reminder.id or actual.completed != reminder.completed:
            raise BridgeError("MUTATION_UNKNOWN", "Apple write needs read-back reconciliation.")
        return {"action": "completed" if actual.completed else "reopened",
                "provider": "pyicloud", "reminderId": actual.id, "committed": True}

    def delete_reminder(self, params: dict[str, Any]) -> dict[str, Any]:
        service = self._service().reminders
        reminder = service.get(str(params["reminderId"]))
        service.delete(reminder)
        remaining = service.list_reminders(
            list_id=reminder.list_id, include_completed=True, results_limit=200,
        ).reminders
        if any(item.id == reminder.id for item in remaining):
            raise BridgeError("MUTATION_UNKNOWN", "Apple write needs read-back reconciliation.")
        return {"action": "deleted", "provider": "pyicloud",
                "reminderId": reminder.id, "committed": True}

    @staticmethod
    def _normalize_reminder(reminder: Any) -> dict[str, Any]:
        return {
            "reminderId": str(reminder.id), "listId": str(reminder.list_id),
            "title": str(reminder.title), "notes": str(reminder.desc or ""),
            "dueAt": reminder.due_date.isoformat() if reminder.due_date else None,
            "completed": bool(reminder.completed), "deleted": bool(reminder.deleted),
            "urgent": bool(reminder.priority == 1 or reminder.flagged),
            "priority": int(reminder.priority), "flagged": bool(reminder.flagged),
            "allDay": bool(reminder.all_day), "timezone": reminder.time_zone,
        }

    @staticmethod
    def _reminder_schedule(
        params: dict[str, Any], *, default_actual: datetime | None = None,
        default_notes: str = "",
    ) -> tuple[datetime | None, datetime | None, str]:
        advance = int(params.get("remindMinutesBefore", 0))
        if not 0 <= advance <= 10080:
            raise BridgeError("INVALID_REQUEST", "remindMinutesBefore must be 0 to 10080.")
        raw_actual = params.get("time")
        actual = parse_rfc3339(str(raw_actual)) if raw_actual else default_actual
        if params.get("urgent") and actual is None:
            raise BridgeError("INVALID_REQUEST", "An actual time is required for an urgent alarm.")
        if "remindMinutesBefore" in params and advance and not raw_actual:
            raise BridgeError("INVALID_REQUEST", "time is required when changing advance notice.")
        if advance and actual is None:
            raise BridgeError("INVALID_REQUEST", "An actual time is required for advance notice.")
        if params.get("allDay") and advance:
            raise BridgeError("INVALID_REQUEST", "All-day reminders cannot use minute advance notice.")
        due = actual
        user_notes = str(params.get("notes", default_notes)).strip()
        notes = user_notes
        return actual, due, notes

    def _reminder_mutation_result(
        self, action: str, service: Any, reminder_id: str, expected: dict[str, Any],
        *, actual_at: datetime | None, advance: int,
    ) -> dict[str, Any]:
        try:
            actual = self._normalize_reminder(service.get(reminder_id))
            for key, value in expected.items():
                if key == "dueAt":
                    observed = parse_rfc3339(actual[key]) if actual[key] else None
                    wanted = parse_rfc3339(value) if value else None
                    if observed != wanted:
                        raise ValueError("Reminder due time differs")
                elif actual[key] != value:
                    raise ValueError("Reminder field differs")
        except Exception as exc:
            raise BridgeError(
                "MUTATION_UNKNOWN", "Apple reminder write needs read-back reconciliation."
            ) from exc
        return {"action": action, "provider": "pyicloud", "reminderId": reminder_id,
                "committed": True,
                "actualTime": actual_at.isoformat() if actual_at else None,
                "reminderTime": actual["dueAt"], "remindMinutesBefore": advance}

    @staticmethod
    def _assert_identity(current: dict[str, Any], params: dict[str, Any]) -> None:
        if any(current.get(key) != str(params[key]) for key in ("calendarId", "eventId")):
            raise BridgeError("CONFLICT", "Apple returned a different calendar event.")

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
        if not isinstance(result, dict):
            raise BridgeError("MUTATION_UNKNOWN", "Apple write needs read-back reconciliation.")
        if any(result.get(key) for key in ("serviceErrors", "error", "errors")):
            raise BridgeError("UPSTREAM_CHANGED", "Apple rejected the calendar mutation.")
        return result

    @staticmethod
    def _mutation_result(
        action: str, event: EventObject, response: dict[str, Any],
        calendar: Any = None, params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(response, dict) or not response or any(
            response.get(key) for key in ("serviceErrors", "error", "errors")
        ):
            raise BridgeError("MUTATION_UNKNOWN", "Apple write needs read-back reconciliation.")
        # A nonempty HTTP response is not a commit receipt. Read the exact resource
        # back; unexpected schemas, stale values or transport errors are ambiguous
        # outcomes and must never authorize automatic replay.
        try:
            if calendar is None or params is None:
                raise ValueError("Read-back context is required")
            if action == "deleted":
                # pyiCloud's get_event_detail indexes Event[0], losing the distinction
                # between a confirmed empty array and other failures. Preserve it.
                query = dict(calendar.params)
                query.update({
                    "lang": "en-us", "usertz": event.tz,
                    "dsid": calendar.session.service.data["dsInfo"]["dsid"],
                })
                try:
                    reply = calendar.session.get(
                        f"{calendar._calendar_event_detail_url}/{event.pguid}/{event.guid}",
                        params=query,
                    )
                    reply.raise_for_status()
                    raw = reply.json()
                    if not isinstance(raw, dict) or raw.get("Event") != [] or any(
                        raw.get(key) for key in ("serviceErrors", "error", "errors")
                    ):
                        raise ValueError("Deletion has not been confirmed")
                except PyiCloudAPIResponseException as exc:
                    # Apple normally returns 404 for a deleted event. A 404 alone
                    # can also hide permission loss, so require independent proof
                    # that the same collection is readable and this GUID is absent
                    # from its original time window. Never accept auth/network errors.
                    if str(exc.code) != "404" or exc.reason.casefold() != "not found":
                        raise
                    if exc.response is not None and exc.response.status_code != 404:
                        raise
                    ICloudProvider._verify_deleted_window(calendar, event)
            else:
                raw = calendar.get_event_detail(event.pguid, event.guid, as_obj=False)
                if not isinstance(raw, dict):
                    raise ValueError("Unexpected event schema")
                actual = normalize_event(raw)
                expected = {
                    "calendarId": event.pguid, "eventId": event.guid,
                    "title": event.title, "location": event.location,
                    "allDay": event.all_day,
                    "notes": str(params.get("notes") or ""),
                    "url": str(params.get("url") or ""),
                }
                if any(actual[key] != value for key, value in expected.items()):
                    raise ValueError("Read-back event fields differ")
                for key, wanted in (("start", event.start_date), ("end", event.end_date)):
                    if not actual[key] or parse_rfc3339(actual[key]) != wanted:
                        raise ValueError("Read-back event times differ")
        except Exception as exc:
            raise BridgeError(
                "MUTATION_UNKNOWN", "Apple write needs read-back reconciliation."
            ) from exc
        return {
            "action": action,
            "provider": "pyicloud",
            "calendarId": event.pguid,
            "eventId": event.guid,
            "committed": True,
        }

    @staticmethod
    def _verify_deleted_window(calendar: Any, event: EventObject) -> None:
        collections = calendar.get_calendars(as_objs=False)
        if not isinstance(collections, list) or any(
            not isinstance(item, dict) or not item.get("guid") for item in collections
        ) or sum(item["guid"] == event.pguid for item in collections) != 1:
            raise ValueError("Original calendar is not readable")
        events = calendar.get_events(
            event.start_date - timedelta(days=1),
            event.end_date + timedelta(days=1),
            as_objs=False,
        )
        if not isinstance(events, list) or any(
            not isinstance(item, dict) or not item.get("guid")
            or not (item.get("pGuid") or item.get("pguid")) for item in events
        ):
            raise ValueError("Unexpected event listing schema")
        if any(item["guid"] == event.guid for item in events):
            raise ValueError("Deleted event is still listed")
