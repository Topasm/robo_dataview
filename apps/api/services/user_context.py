from __future__ import annotations

import re

from fastapi import Header


DEFAULT_USER_ID = "local"
USER_HEADER_NAME = "X-Robot-Data-Studio-User"


def normalize_user_id(value: str | None) -> str:
    user_id = (value or DEFAULT_USER_ID).strip()
    if not user_id:
        return DEFAULT_USER_ID
    user_id = re.sub(r"\s+", "_", user_id)
    user_id = re.sub(r"[^A-Za-z0-9_.@:-]+", "_", user_id)
    return user_id[:128] or DEFAULT_USER_ID


def current_user_id(
    user_header: str | None = Header(default=None, alias=USER_HEADER_NAME),
) -> str:
    return normalize_user_id(user_header)
