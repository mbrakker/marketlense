from __future__ import annotations

from typing import Any, Dict, Optional


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        cause: Optional[Exception] = None,
        retryable: bool = False,
        severity: str = "error",
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.cause = cause
        self.retryable = retryable
        self.severity = severity
        self.context = context or {}
