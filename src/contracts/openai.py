from __future__ import annotations

from dataclasses import dataclass

from src.contracts.report_models import ReportPayload


@dataclass(frozen=True)
class OpenAIAnalyzeRequest:
    schema_version: str
    pdf_path: str
    model: str
    temperature: float
    api_key: str


@dataclass(frozen=True)
class OpenAIAnalyzeResponse:
    schema_version: str
    payload: ReportPayload
    prompt_system_sha256: str
    prompt_user_sha256: str
    model: str
    temperature: float
