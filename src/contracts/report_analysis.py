from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class AnalysisPackPathRequest:
    schema_version: str = field(metadata={"doc": "Analysis pack path request schema version."})
    output_dir: str = field(metadata={"doc": "Base output directory."})
    report_id: str = field(metadata={"doc": "Report identifier used as slug fallback when report_slug is missing."})
    pack_name: str = field(metadata={"doc": "Pack name without file extension."})
    report_slug: Optional[str] = field(default=None, metadata={"doc": "Optional normalized report slug for per-report layout."})


@dataclass(frozen=True)
class AnalysisPackPathResponse:
    schema_version: str = field(metadata={"doc": "Analysis pack path response schema version."})
    output_path: str = field(metadata={"doc": "Resolved JSON output path for the pack."})


@dataclass(frozen=True)
class AnalysisStorePackRequest:
    schema_version: str = field(metadata={"doc": "Analysis pack store request schema version."})
    output_dir: str = field(metadata={"doc": "Base output directory."})
    report_id: str = field(metadata={"doc": "Report identifier."})
    pack_name: str = field(metadata={"doc": "Pack name without file extension."})
    payload: Dict[str, Any] = field(metadata={"doc": "JSON-serializable payload to write."})
    report_slug: Optional[str] = field(default=None, metadata={"doc": "Optional normalized report slug for per-report layout."})


@dataclass(frozen=True)
class AnalysisStorePackResponse:
    schema_version: str = field(metadata={"doc": "Analysis pack store response schema version."})
    output_path: str = field(metadata={"doc": "Primary output path where payload was stored."})
