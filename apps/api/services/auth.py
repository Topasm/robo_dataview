from __future__ import annotations

import os

from fastapi import Request
from fastapi.responses import JSONResponse


API_KEY_HEADER_NAME = "X-Robot-Data-Studio-API-Key"


def configured_api_key() -> str | None:
    value = os.getenv("ROBOT_DATA_STUDIO_API_KEY", "").strip()
    return value or None


async def enforce_api_key(request: Request, call_next):
    expected = configured_api_key()
    if expected is None or not request.url.path.startswith("/api") or request.method == "OPTIONS":
        return await call_next(request)
    provided = request.headers.get(API_KEY_HEADER_NAME)
    if provided != expected:
        return JSONResponse(
            status_code=401,
            content={"detail": "Missing or invalid API key"},
        )
    return await call_next(request)
