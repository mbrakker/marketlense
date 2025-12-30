from __future__ import annotations

import base64
from typing import Optional


def build_auth_header(
    *,
    username: Optional[str],
    app_password: Optional[str],
    bearer_token: Optional[str],
) -> str:
    if bearer_token:
        return f"Bearer {bearer_token}"
    if not username or not app_password:
        raise ValueError("Missing WordPress username or application password")
    raw = f"{username}:{app_password}".encode("utf-8")
    token = base64.b64encode(raw).decode("ascii")
    return f"Basic {token}"
