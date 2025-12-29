from __future__ import annotations

from dataclasses import dataclass

from src.contracts.report_models import ReportPayload


@dataclass(frozen=True)
class NormalizeRequest:
    schema_version: str
    payload: ReportPayload


@dataclass(frozen=True)
class NormalizeResponse:
    schema_version: str
    payload: ReportPayload
