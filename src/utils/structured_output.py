"""Safe typed failures for bounded structured-output recovery.

The original provider text is intentionally retained only in memory long enough
for the owning orchestrator to issue its one permitted targeted repair.  It is
not included in :class:`AppError` context, normal logs, durable remediation
records, or evidence exports.
"""

from __future__ import annotations

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
    ) -> None:
        super().__init__(
            code=code,
            message=message,
            retryable=False,
            context={
                "artifact_family": artifact_family,
                "response_chars": len(response_text or ""),
                "repair_attempt": max(0, int(repair_attempt or 0)),
            },
        )
        self.response_text = response_text
        self.schema_errors = schema_errors
        self.artifact_family = artifact_family
