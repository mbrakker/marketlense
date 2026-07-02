from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class PublicSitePageQuality:
    schema_version: str = field(metadata={"doc": "Public-site page quality schema."})
    url: str = field(metadata={"doc": "Absolute URL inspected."})
    status_code: int = field(metadata={"doc": "HTTP status code."})
    response_start_ms: float = field(
        metadata={"doc": "Milliseconds from request start until response headers."}
    )
    dom_complete_ms: float = field(
        metadata={"doc": "Milliseconds from request start through HTML parse."}
    )
    request_count: int = field(
        metadata={"doc": "HTML request plus discovered page resource requests."}
    )
    page_weight_bytes: int = field(
        metadata={"doc": "HTML bytes plus discovered resource content lengths."}
    )
    metadata: Dict[str, str] = field(
        metadata={"doc": "SEO/social metadata values found on the page."}
    )
    missing_metadata: List[str] = field(
        metadata={"doc": "Required metadata keys absent from the page."}
    )
    threshold_violations: List[str] = field(
        metadata={"doc": "Named performance thresholds violated by this page."}
    )


@dataclass(frozen=True)
class PublicSiteQualityReport:
    schema_version: str = field(metadata={"doc": "Public-site quality report schema."})
    base_url: str = field(metadata={"doc": "Hosted site base URL inspected."})
    pages: List[PublicSitePageQuality] = field(
        metadata={"doc": "Per-page SEO/social/performance results."}
    )
    passed: bool = field(metadata={"doc": "Whether all pages passed the gate."})
