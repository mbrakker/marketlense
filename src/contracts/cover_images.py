from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional

from src.contracts.report_cards import CardCoverAssetSet, CoverFingerprint
from src.utils.errors import AppError


@dataclass(frozen=True)
class CoverImageLayout:
    schema_version: str = field(metadata={"doc": "Cover image layout schema version."})
    width: int = field(metadata={"doc": "Output image width in pixels."})
    height: int = field(metadata={"doc": "Output image height in pixels."})
    publisher_x: int = field(metadata={"doc": "Publisher rectangle left edge."})
    publisher_y: int = field(metadata={"doc": "Publisher rectangle top edge."})
    publisher_width: int = field(metadata={"doc": "Publisher rectangle width."})
    publisher_height: int = field(metadata={"doc": "Publisher rectangle height."})
    title_x: int = field(metadata={"doc": "Title rectangle left edge."})
    title_y: int = field(metadata={"doc": "Title rectangle top edge."})
    title_width: int = field(metadata={"doc": "Title rectangle width."})
    title_height: int = field(metadata={"doc": "Title rectangle height."})
    period_x: int = field(metadata={"doc": "Covered-period rectangle left edge."})
    period_y: int = field(metadata={"doc": "Covered-period rectangle top edge."})
    period_width: int = field(metadata={"doc": "Covered-period rectangle width."})
    period_height: int = field(metadata={"doc": "Covered-period rectangle height."})
    title_font_max: int = field(metadata={"doc": "Max font size for the report title."})
    title_font_min: int = field(metadata={"doc": "Min font size for the report title."})
    publisher_font_max: int = field(metadata={"doc": "Max publisher font size."})
    publisher_font_min: int = field(metadata={"doc": "Min publisher font size."})
    period_font_max: int = field(metadata={"doc": "Max covered-period font size."})
    period_font_min: int = field(metadata={"doc": "Min covered-period font size."})
    title_line_spacing: float = field(
        metadata={"doc": "Line spacing multiplier for wrapped title text."}
    )


@dataclass(frozen=True)
class CoverImageStyle:
    schema_version: str = field(metadata={"doc": "Cover image style schema version."})
    background_color: str = field(
        metadata={"doc": "Hex background color for the cover."}
    )
    background_elevated_color: str = field(
        metadata={"doc": "Hex color for elevated background planes."}
    )
    geometry_color: str = field(metadata={"doc": "Hex base geometry color."})
    geometry_highlight_color: str = field(
        metadata={"doc": "Hex geometry highlight color."}
    )
    text_color: str = field(metadata={"doc": "Hex text color for labels and title."})
    font_regular_path: str = field(
        metadata={"doc": "Filesystem path to the regular font."}
    )
    font_bold_path: str = field(metadata={"doc": "Filesystem path to the bold font."})


@dataclass(frozen=True)
class CoverImageStyleConfig:
    schema_version: str = field(
        metadata={"doc": "Cover image style config schema version."}
    )
    defaults: CoverImageStyle = field(metadata={"doc": "Default cover image style."})
    layouts: Dict[str, CoverImageLayout] = field(
        metadata={"doc": "Canonical small, medium, and large cover layouts."}
    )


@dataclass(frozen=True)
class CoverStyleLoadRequest:
    schema_version: str = field(
        metadata={"doc": "Cover style config load request schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path to the cover style YAML."})


@dataclass(frozen=True)
class CoverStyleLoadResponse:
    schema_version: str = field(
        metadata={"doc": "Cover style config load response schema version."}
    )
    config: CoverImageStyleConfig = field(
        metadata={"doc": "Loaded cover style configuration."}
    )


@dataclass(frozen=True)
class CoverImageReport:
    schema_version: str = field(
        metadata={"doc": "Cover image report data schema version."}
    )
    file_id: str = field(metadata={"doc": "Report file identifier."})
    title: str = field(metadata={"doc": "Report title."})
    publisher: Optional[str] = field(metadata={"doc": "Report publisher (optional)."})
    report_slug: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional report output slug for storing the cover under out/<report-slug>/assets."
        },
    )
    categories: List[str] = field(
        default_factory=list, metadata={"doc": "Assigned category identifiers."}
    )
    time_period: Optional[str] = field(
        default=None, metadata={"doc": "Optional time period label."}
    )
    region: Optional[str] = field(
        default=None, metadata={"doc": "Optional region label."}
    )
    fingerprint: Optional[CoverFingerprint] = field(
        default=None,
        metadata={"doc": "Required semantic cover fingerprint for schema version 2.0."},
    )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "CoverImageReport":
        if payload.get("schema_version") != "2.0":
            raise AppError(
                code="cover_contract_migration_required",
                message="Legacy single-cover requests must be regenerated",
                retryable=False,
            )
        fingerprint_payload = payload.get("fingerprint")
        if not isinstance(fingerprint_payload, Mapping):
            raise AppError(
                code="cover_fingerprint_invalid",
                message="Cover image reports require a semantic fingerprint",
                retryable=False,
            )
        raw_categories = payload.get("categories")
        categories = (
            [str(item) for item in raw_categories]
            if isinstance(raw_categories, (list, tuple))
            else []
        )
        return cls(
            schema_version="2.0",
            file_id=str(payload.get("file_id") or "").strip(),
            title=str(payload.get("title") or "").strip(),
            publisher=str(payload.get("publisher") or "").strip() or None,
            report_slug=str(payload.get("report_slug") or "").strip() or None,
            categories=categories,
            time_period=str(payload.get("time_period") or "").strip() or None,
            region=str(payload.get("region") or "").strip() or None,
            fingerprint=CoverFingerprint.from_dict(fingerprint_payload),
        )


@dataclass(frozen=True)
class CoverImageGenerationRequest:
    schema_version: str = field(
        metadata={"doc": "Cover image generation request schema version."}
    )
    output_dir: str = field(metadata={"doc": "Base output directory for cover images."})
    style_config_path: str = field(
        metadata={"doc": "Filesystem path to the cover style YAML."}
    )
    reports: List[CoverImageReport] = field(
        metadata={"doc": "Reports to generate cover images for."}
    )


@dataclass(frozen=True)
class CoverImageGenerationOutcome:
    schema_version: str = field(
        metadata={"doc": "Cover image generation outcome schema version."}
    )
    file_id: str = field(metadata={"doc": "Report file identifier."})
    title: str = field(metadata={"doc": "Report title."})
    status: str = field(metadata={"doc": "Outcome status: generated|error|skipped."})
    assets: Optional[CardCoverAssetSet] = field(
        default=None,
        metadata={
            "doc": "Canonical three-size cover asset set for schema version 2.0."
        },
    )
    error: Optional[str] = field(
        default=None, metadata={"doc": "Error message, if any."}
    )


@dataclass(frozen=True)
class CoverImageOrchestratorRequest:
    schema_version: str = field(
        metadata={"doc": "Cover image orchestrator request schema version."}
    )
    reports_db: str = field(
        metadata={"doc": "Filesystem path to the reports metadata database."}
    )
    output_dir: str = field(metadata={"doc": "Base output directory for cover images."})
    style_config_path: str = field(
        metadata={"doc": "Filesystem path to the cover style YAML."}
    )
    limit: Optional[int] = field(
        default=None,
        metadata={"doc": "Optional limit for the number of reports to process."},
    )
    file_id: Optional[str] = field(
        default=None, metadata={"doc": "Optional report file ID filter."}
    )


@dataclass(frozen=True)
class CoverImageRenderRequest:
    schema_version: str = field(
        metadata={"doc": "Cover image render request schema version."}
    )
    output_path: str = field(metadata={"doc": "Filesystem path for the rendered PNG."})
    size: str = field(metadata={"doc": "Canonical cover size being rendered."})
    title: str = field(metadata={"doc": "Report title."})
    publisher: Optional[str] = field(metadata={"doc": "Report publisher (optional)."})
    style: CoverImageStyle = field(metadata={"doc": "Resolved style for the report."})
    layout: CoverImageLayout = field(
        metadata={"doc": "Layout configuration for rendering."}
    )
    fingerprint: CoverFingerprint = field(
        metadata={"doc": "Deterministic semantic geometry fingerprint."}
    )
    time_period: Optional[str] = field(
        default=None, metadata={"doc": "Optional time period label."}
    )


@dataclass(frozen=True)
class CoverImageRenderResponse:
    schema_version: str = field(
        metadata={"doc": "Cover image render response schema version."}
    )
    output_path: str = field(
        metadata={"doc": "Filesystem path to the generated cover image."}
    )
    width: int = field(metadata={"doc": "Rendered image width in pixels."})
    height: int = field(metadata={"doc": "Rendered image height in pixels."})
    title_font_size: int = field(
        metadata={"doc": "Measured title font size used by the renderer."}
    )
