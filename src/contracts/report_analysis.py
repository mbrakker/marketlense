from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class AnalysisPackPathRequest:
    schema_version: str = field(metadata={"doc": "Analysis pack path request schema version."})
    output_dir: str = field(metadata={"doc": "Base output directory."})
    report_id: str = field(metadata={"doc": "Report identifier (legacy path key)."})
    pack_name: str = field(metadata={"doc": "Pack name without file extension."})
    report_slug: Optional[str] = field(default=None, metadata={"doc": "Optional normalized report slug for new layout."})


@dataclass(frozen=True)
class AnalysisPackPathResponse:
    schema_version: str = field(metadata={"doc": "Analysis pack path response schema version."})
    output_path: str = field(metadata={"doc": "Resolved JSON output path for the pack."})


@dataclass(frozen=True)
class AnalysisStorePackRequest:
    schema_version: str = field(metadata={"doc": "Analysis pack store request schema version."})
    output_dir: str = field(metadata={"doc": "Base output directory."})
    report_id: str = field(metadata={"doc": "Report identifier (legacy path key)."})
    pack_name: str = field(metadata={"doc": "Pack name without file extension."})
    payload: Dict[str, Any] = field(metadata={"doc": "JSON-serializable payload to write."})
    report_slug: Optional[str] = field(default=None, metadata={"doc": "Optional normalized report slug for new layout."})
    mirror_legacy: bool = field(default=True, metadata={"doc": "Whether to mirror writes into the legacy output layout."})


@dataclass(frozen=True)
class AnalysisStorePackResponse:
    schema_version: str = field(metadata={"doc": "Analysis pack store response schema version."})
    output_path: str = field(metadata={"doc": "Primary output path where payload was stored."})
    legacy_output_path: Optional[str] = field(default=None, metadata={"doc": "Legacy mirror path when created."})
