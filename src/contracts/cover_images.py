from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class CoverImageLayout:
    schema_version: str = field(metadata={"doc": "Cover image layout schema version."})
    width: int = field(metadata={"doc": "Output image width in pixels."})
    height: int = field(metadata={"doc": "Output image height in pixels."})
    accent_width: int = field(metadata={"doc": "Width of the left accent band in pixels."})
    margin_x: int = field(metadata={"doc": "Horizontal margin for text layout."})
    margin_y: int = field(metadata={"doc": "Vertical margin for text layout."})
    label_font_size: int = field(metadata={"doc": "Base font size for the category label."})
    title_font_max: int = field(metadata={"doc": "Max font size for the report title."})
    title_font_min: int = field(metadata={"doc": "Min font size for the report title."})
    publisher_font_size: int = field(metadata={"doc": "Base font size for the publisher name."})
    time_font_size: int = field(metadata={"doc": "Base font size for the time period pill text."})
    title_line_spacing: float = field(metadata={"doc": "Line spacing multiplier for wrapped title text."})
    label_gap: int = field(metadata={"doc": "Gap below the category label in pixels."})
    footer_gap: int = field(metadata={"doc": "Gap above the footer text in pixels."})
    pill_padding_x: int = field(metadata={"doc": "Horizontal padding for the time period pill."})
    pill_padding_y: int = field(metadata={"doc": "Vertical padding for the time period pill."})
    pill_radius: int = field(metadata={"doc": "Corner radius for the time period pill."})
    pill_border_width: int = field(metadata={"doc": "Border width for the time period pill."})
    pill_fill_color: str = field(metadata={"doc": "Fill color for the time period pill."})
    pill_text_color: str = field(metadata={"doc": "Text color for the time period pill."})
    pill_border_color: str = field(metadata={"doc": "Border color for the time period pill."})


@dataclass(frozen=True)
class CoverImageStyle:
    schema_version: str = field(metadata={"doc": "Cover image style schema version."})
    background_color: str = field(metadata={"doc": "Hex background color for the cover."})
    accent_color: str = field(metadata={"doc": "Hex accent color for the left band."})
    text_color: str = field(metadata={"doc": "Hex text color for labels and title."})
    category_label: str = field(metadata={"doc": "Category label text (optional)."})
    font_regular_path: str = field(metadata={"doc": "Filesystem path to the regular font."})
    font_bold_path: str = field(metadata={"doc": "Filesystem path to the bold font."})
    background_image_path: Optional[str] = field(default=None, metadata={"doc": "Optional background image path."})


@dataclass(frozen=True)
class CoverImageStyleOverrides:
    schema_version: str = field(metadata={"doc": "Cover image style overrides schema version."})
    background_color: Optional[str] = field(default=None, metadata={"doc": "Override for background color."})
    accent_color: Optional[str] = field(default=None, metadata={"doc": "Override for accent color."})
    text_color: Optional[str] = field(default=None, metadata={"doc": "Override for text color."})
    category_label: Optional[str] = field(default=None, metadata={"doc": "Override for category label."})
    font_regular_path: Optional[str] = field(default=None, metadata={"doc": "Override for regular font path."})
    font_bold_path: Optional[str] = field(default=None, metadata={"doc": "Override for bold font path."})
    background_image_path: Optional[str] = field(default=None, metadata={"doc": "Override for background image path."})


@dataclass(frozen=True)
class CoverImageStyleConfig:
    schema_version: str = field(metadata={"doc": "Cover image style config schema version."})
    defaults: CoverImageStyle = field(metadata={"doc": "Default cover image style."})
    categories: Dict[str, CoverImageStyleOverrides] = field(metadata={"doc": "Per-category style overrides."})
    layout: CoverImageLayout = field(metadata={"doc": "Layout configuration shared across categories."})


@dataclass(frozen=True)
class CoverStyleLoadRequest:
    schema_version: str = field(metadata={"doc": "Cover style config load request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to the cover style YAML."})


@dataclass(frozen=True)
class CoverStyleLoadResponse:
    schema_version: str = field(metadata={"doc": "Cover style config load response schema version."})
    config: CoverImageStyleConfig = field(metadata={"doc": "Loaded cover style configuration."})


@dataclass(frozen=True)
class CoverImageReport:
    schema_version: str = field(metadata={"doc": "Cover image report data schema version."})
    file_id: str = field(metadata={"doc": "Report file identifier."})
    title: str = field(metadata={"doc": "Report title."})
    publisher: Optional[str] = field(metadata={"doc": "Report publisher (optional)."})
    categories: List[str] = field(default_factory=list, metadata={"doc": "Assigned category identifiers."})
    time_period: Optional[str] = field(default=None, metadata={"doc": "Optional time period label."})
    region: Optional[str] = field(default=None, metadata={"doc": "Optional region label."})


@dataclass(frozen=True)
class CoverImageGenerationRequest:
    schema_version: str = field(metadata={"doc": "Cover image generation request schema version."})
    output_dir: str = field(metadata={"doc": "Base output directory for cover images."})
    style_config_path: str = field(metadata={"doc": "Filesystem path to the cover style YAML."})
    reports: List[CoverImageReport] = field(metadata={"doc": "Reports to generate cover images for."})


@dataclass(frozen=True)
class CoverImageGenerationOutcome:
    schema_version: str = field(metadata={"doc": "Cover image generation outcome schema version."})
    file_id: str = field(metadata={"doc": "Report file identifier."})
    title: str = field(metadata={"doc": "Report title."})
    status: str = field(metadata={"doc": "Outcome status: generated|error|skipped."})
    output_path: Optional[str] = field(default=None, metadata={"doc": "Filesystem path to the generated cover PNG."})
    error: Optional[str] = field(default=None, metadata={"doc": "Error message, if any."})


@dataclass(frozen=True)
class CoverImageOrchestratorRequest:
    schema_version: str = field(metadata={"doc": "Cover image orchestrator request schema version."})
    reports_db: str = field(metadata={"doc": "Filesystem path to the reports metadata database."})
    output_dir: str = field(metadata={"doc": "Base output directory for cover images."})
    style_config_path: str = field(metadata={"doc": "Filesystem path to the cover style YAML."})
    limit: Optional[int] = field(default=None, metadata={"doc": "Optional limit for the number of reports to process."})
    file_id: Optional[str] = field(default=None, metadata={"doc": "Optional report file ID filter."})


@dataclass(frozen=True)
class CoverImageRenderRequest:
    schema_version: str = field(metadata={"doc": "Cover image render request schema version."})
    output_path: str = field(metadata={"doc": "Filesystem path for the rendered PNG."})
    title: str = field(metadata={"doc": "Report title."})
    publisher: Optional[str] = field(metadata={"doc": "Report publisher (optional)."})
    category_label: str = field(metadata={"doc": "Category label text."})
    style: CoverImageStyle = field(metadata={"doc": "Resolved style for the report."})
    layout: CoverImageLayout = field(metadata={"doc": "Layout configuration for rendering."})
    time_period: Optional[str] = field(default=None, metadata={"doc": "Optional time period label."})


@dataclass(frozen=True)
class CoverImageRenderResponse:
    schema_version: str = field(metadata={"doc": "Cover image render response schema version."})
    output_path: str = field(metadata={"doc": "Filesystem path to the generated cover image."})
    width: int = field(metadata={"doc": "Rendered image width in pixels."})
    height: int = field(metadata={"doc": "Rendered image height in pixels."})
