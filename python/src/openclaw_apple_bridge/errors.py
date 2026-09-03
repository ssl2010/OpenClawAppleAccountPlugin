from __future__ import annotations


class BridgeError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def classify_exception(exc: Exception) -> BridgeError:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "-20209" in text or "locked" in text:
        return BridgeError(
            "ACCOUNT_LOCKED", "Apple account is locked; operator action is required."
        )
    if "2fa" in text or "two-factor" in text or "verification code" in text:
        return BridgeError("TWO_FACTOR_REQUIRED", "Apple two-factor authentication is required.")
    if "authentication" in name or "failedlogin" in name or "password" in text:
        return BridgeError("AUTH_REQUIRED", "Apple authentication is required.")
    if "timeout" in name or "timed out" in text:
        return BridgeError("SERVICE_UNAVAILABLE", "Apple service timed out.", retryable=True)
    if "rate" in text and "limit" in text:
        return BridgeError("RATE_LIMITED", "Apple service rate limit reached.", retryable=True)
    return BridgeError("SERVICE_UNAVAILABLE", "Apple service request failed.", retryable=True)
