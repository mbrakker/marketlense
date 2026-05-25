from __future__ import annotations

from dataclasses import dataclass, field

from .identity import BrowserDownloadSettings
from .playbooks import BrowserRoutePrivateApiPromotionCandidate
from .runtime import BrowserReportDownloadResult


@dataclass(frozen=True)
class BrowserRoutePrivateApiAutoPromotionDetectionRequest:
    schema_version: str = field(
        metadata={"doc": "Private-API auto-promotion detection request schema version."}
    )
    settings: BrowserDownloadSettings = field(
        metadata={
            "doc": "Browser-download settings controlling detection thresholds and timeouts."
        }
    )
    result: BrowserReportDownloadResult = field(
        metadata={
            "doc": "Verified browser-download result to inspect for private-API candidates."
        }
    )
    observed_at: str = field(
        default="",
        metadata={
            "doc": "UTC ISO timestamp used for deterministic candidate metadata."
        },
    )


@dataclass(frozen=True)
class BrowserRoutePrivateApiAutoPromotionDetectionResponse:
    schema_version: str = field(
        metadata={
            "doc": "Private-API auto-promotion detection response schema version."
        }
    )
    candidate_count: int = field(
        metadata={"doc": "Number of validated private-API candidates returned."}
    )
    candidates: list[BrowserRoutePrivateApiPromotionCandidate] = field(
        metadata={
            "doc": "Validated candidates derived from the browser terminal evidence."
        }
    )
    skipped_reason: str = field(
        default="",
        metadata={"doc": "Reason detection did not run or returned no candidates."},
    )
