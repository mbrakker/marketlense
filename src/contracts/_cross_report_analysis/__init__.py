"""Private semantic owners for cross-report analysis contracts."""

from __future__ import annotations

from typing import Literal

CROSS_REPORT_ANALYSIS_SCHEMA_VERSION = "1.0"

PublicationMode = Literal[
    "generate_only",
    "validate_only",
    "publish_dry_run",
    "publish_live",
]
ProjectionReadinessStatus = Literal["not_projected", "projected", "failed"]
CrossReportContentClass = Literal[
    "claim",
    "finding",
    "quote",
    "metric",
    "section",
    "figure",
]
CrossReportReadContentClass = Literal["claim", "finding", "quote", "metric"]
CrossReportValidationStatus = Literal["pass", "fail"]
CrossReportOutcomeStatus = Literal[
    "generated",
    "validated",
    "published",
    "skipped",
    "failed",
]
CrossReportPublishStatus = Literal[
    "not_requested",
    "dry_run",
    "published",
    "skipped",
    "error",
]
CrossReportEvidenceAgreementType = Literal["convergent", "divergent", "thin_coverage"]
