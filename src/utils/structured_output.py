"""Safe typed failures for bounded structured-output recovery.

The original provider text is intentionally retained only in memory long enough
for the owning orchestrator to issue its one permitted targeted repair.  It is
not included in :class:`AppError` context, normal logs, durable remediation
records, or evidence exports.
"""

from __future__ import annotations

from typing import Any

from src.utils.errors import AppError


class StructuredOutputFailure(AppError):
    """An output-contract failure with private in-memory repair material."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        artifact_family: str,
        response_text: str,
        schema_errors: str = "",
        repair_attempt: int = 0,
        error_class: str = "",
        failure_context: dict[str, Any] | None = None,
    ) -> None:
        context: dict[str, Any] = {
            "artifact_family": artifact_family,
            "response_chars": len(response_text or ""),
            "repair_attempt": max(0, int(repair_attempt or 0)),
            "error_class": str(error_class or "").strip(),
        }
        # Bounded, identifier-only retention of the inner validation cause so
        # terminal remediation records stay actionable without retaining any
        # provider response or report content.
        for key, value in (failure_context or {}).items():
            if value not in (None, "", [], {}):
                context[key] = value
        super().__init__(
            code=code,
            message=message,
            retryable=False,
            context=context,
        )
        self.response_text = response_text
        self.schema_errors = schema_errors
        self.artifact_family = artifact_family
