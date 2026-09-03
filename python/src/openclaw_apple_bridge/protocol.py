from __future__ import annotations

from typing import Any

from .errors import BridgeError, classify_exception
from .icloud import ICloudProvider
from .rail12306 import plan_email


def dispatch(
    request: dict[str, Any], provider_factory: type[ICloudProvider] = ICloudProvider
) -> dict[str, Any]:
    request_id = str(request.get("requestId") or "")
    try:
        data: Any
        operation = str(request.get("operation") or "")
        params = request.get("params") or {}
        if not isinstance(params, dict):
            raise BridgeError("INVALID_REQUEST", "params must be an object.")
        if operation == "rail12306.plan":
            data = plan_email(params)
        else:
            provider = provider_factory(request.get("config") or {})
            handlers = {
                "account.status": provider.status,
                "calendar.list": provider.list_calendars,
                "calendar.events": lambda: provider.list_events(params),
                "calendar.get": lambda: provider.get_event(params),
                "calendar.create": lambda: provider.create_event(params),
                "calendar.update": lambda: provider.update_event(params),
                "calendar.delete": lambda: provider.delete_event(params),
            }
            if operation not in handlers:
                raise BridgeError("INVALID_REQUEST", "Unknown operation.")
            data = handlers[operation]()
        return {"protocolVersion": 1, "requestId": request_id, "ok": True, "data": data}
    except BridgeError as exc:
        return {
            "protocolVersion": 1,
            "requestId": request_id,
            "ok": False,
            "error": {"code": exc.code, "message": exc.message, "retryable": exc.retryable},
        }
    except Exception as exc:  # noqa: BLE001 -- trust-boundary redaction
        safe = classify_exception(exc)
        return {
            "protocolVersion": 1,
            "requestId": request_id,
            "ok": False,
            "error": {"code": safe.code, "message": safe.message, "retryable": safe.retryable},
        }
