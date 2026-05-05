from __future__ import annotations

from typing import Any


def error(code: str, message: str, *, details: Any | None = None) -> dict:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return payload

