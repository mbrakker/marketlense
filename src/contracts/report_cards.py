from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Mapping, Tuple

from src.utils.errors import AppError

CARD_SIZES = ("small", "medium", "large")
GEOGRAPHY_SCOPES = ("global", "regional", "country", "unknown")
EVIDENCE_SHAPES = (
    "trend",
    "comparison",
    "distribution",
    "flow",
    "network",
    "concentration",
    "hierarchy",
    "cycle",
    "uncertainty",
    "system",
)
DIRECTIONS = (
    "rising",
    "falling",
    "stable",
    "volatile",
    "converging",
    "diverging",
    "cyclical",
    "neutral",
)
EVIDENCE_DENSITIES = ("metric_rich", "balanced", "qualitative")
DOMAIN_LAYERS = ("grid", "forecast")
GEOMETRY_FAMILIES = (
    "ascending_trajectory",
    "descending_trajectory",
    "volatility_corridor",
    "convergence_funnel",
    "divergence_fan",
    "parallel_bands",
    "ranked_strata",
    "distribution_field",
    "concentration_core",
    "flow_channels",
    "network_constellation",
    "hierarchy_terraces",
    "cycle_orbit",
    "forecast_horizon",
    "uncertainty_envelope",
    "system_matrix",
    "interlaced_mesh",
    "radial_pulse",
    "split_horizon",
    "signal_lattice",
)
TITLE_SCALES = ("short", "medium", "long", "xlong")
_COVER_DIMENSIONS = {
    "small": (1600, 900),
    "medium": (1200, 1500),
    "large": (1200, 1600),
}


def _invalid(
    code: str, message: str, *, context: dict[str, object] | None = None
) -> AppError:
    return AppError(
        code=code,
        message=message,
        retryable=False,
        context=context,
    )


def _mapping(value: object, *, code: str, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _invalid(code, f"{field_name} must be an object")
    return value


def _text(
    value: object, *, code: str, field_name: str, allow_empty: bool = False
) -> str:
    normalized = " ".join(str(value or "").split())
    if not normalized and not allow_empty:
        raise _invalid(code, f"{field_name} must be populated")
    return normalized


def _complete_sentence(value: object, *, limit: int, code: str, field_name: str) -> str:
    normalized = _text(value, code=code, field_name=field_name)
    word_count = len(normalized.split())
    if (
        word_count < 1
        or word_count > limit
        or normalized.endswith(("...", "\u2026"))
        or normalized[-1] not in ".?!"
    ):
        raise _invalid(
            code,
            f"{field_name} must be a complete sentence of 1 to {limit} words",
            context={"word_count": word_count},
        )
    return normalized


@dataclass(frozen=True)
class CardCoverAsset:
    schema_version: str = field(metadata={"doc": "Card cover asset schema version."})
    size: str = field(metadata={"doc": "Canonical card size represented by the asset."})
    output_path: str = field(metadata={"doc": "Relative or absolute cover image path."})
    width: int = field(metadata={"doc": "Cover image width in pixels."})
    height: int = field(metadata={"doc": "Cover image height in pixels."})

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "CardCoverAsset":
        size = _text(
            payload.get("size"),
            code="cover_asset_set_incomplete",
            field_name="size",
        )
        if size not in CARD_SIZES:
            raise _invalid(
                "cover_asset_set_incomplete",
                "Cover asset size is not canonical",
                context={"size": size},
            )
        expected_width, expected_height = _COVER_DIMENSIONS[size]
        width = payload.get("width")
        height = payload.get("height")
        if width != expected_width or height != expected_height:
            raise _invalid(
                "cover_asset_set_incomplete",
                "Cover asset dimensions do not match the canonical size",
                context={
                    "size": size,
                    "width": width,
                    "height": height,
                    "expected_width": expected_width,
                    "expected_height": expected_height,
                },
            )
        return cls(
            schema_version=_text(
                payload.get("schema_version"),
                code="cover_asset_set_incomplete",
                field_name="schema_version",
            ),
            size=size,
            output_path=_text(
                payload.get("output_path"),
                code="cover_asset_set_incomplete",
                field_name="output_path",
            ),
            width=expected_width,
            height=expected_height,
        )


@dataclass(frozen=True)
class CardCoverAssetSet:
    schema_version: str = field(
        metadata={"doc": "Card cover asset-set schema version."}
    )
    small: CardCoverAsset = field(metadata={"doc": "Wide small-card cover asset."})
    medium: CardCoverAsset = field(
        metadata={"doc": "Portrait medium-card cover asset."}
    )
    large: CardCoverAsset = field(metadata={"doc": "Portrait large-card cover asset."})

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "CardCoverAssetSet":
        assets: dict[str, CardCoverAsset] = {}
        for size in CARD_SIZES:
            item = payload.get(size)
            if not isinstance(item, Mapping):
                raise _invalid(
                    "cover_asset_set_incomplete",
                    "All three canonical cover assets are required",
                    context={"missing_size": size},
                )
            asset = CardCoverAsset.from_dict(item)
            if asset.size != size:
                raise _invalid(
                    "cover_asset_set_incomplete",
                    "Cover asset is assigned to the wrong size slot",
                    context={"slot": size, "asset_size": asset.size},
                )
            assets[size] = asset
        return cls(
            schema_version=_text(
                payload.get("schema_version"),
                code="cover_asset_set_incomplete",
                field_name="schema_version",
            ),
            small=assets["small"],
            medium=assets["medium"],
            large=assets["large"],
        )


@dataclass(frozen=True)
class CoverFingerprint:
    schema_version: str = field(metadata={"doc": "Cover fingerprint schema version."})
    geometry_family: str = field(metadata={"doc": "Selected semantic geometry family."})
    evidence_shape: str = field(metadata={"doc": "Dominant evidence structure."})
    direction: str = field(metadata={"doc": "Dominant directional signal."})
    geography_scope: str = field(metadata={"doc": "Normalized geography scope."})
    evidence_density: str = field(metadata={"doc": "Evidence density classification."})
    domain_layer: str = field(
        metadata={"doc": "Semantic domain layer used by geometry selection."}
    )
    seed: int = field(metadata={"doc": "Stable deterministic geometry seed."})
    selection_reason: str = field(
        metadata={"doc": "Grounded explanation for the selected geometry."}
    )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "CoverFingerprint":
        values = {
            "geometry_family": GEOMETRY_FAMILIES,
            "evidence_shape": EVIDENCE_SHAPES,
            "direction": DIRECTIONS,
            "geography_scope": GEOGRAPHY_SCOPES,
            "evidence_density": EVIDENCE_DENSITIES,
            "domain_layer": DOMAIN_LAYERS,
        }
        normalized: dict[str, str] = {}
        for field_name, allowed in values.items():
            value = _text(
                payload.get(field_name),
                code="cover_fingerprint_invalid",
                field_name=field_name,
            )
            if value not in allowed:
                raise _invalid(
                    "cover_fingerprint_invalid",
                    f"{field_name} is not an approved fingerprint value",
                    context={"field": field_name, "value": value},
                )
            normalized[field_name] = value
        seed = payload.get("seed")
        if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
            raise _invalid(
                "cover_fingerprint_invalid",
                "seed must be a non-negative integer",
            )
        return cls(
            schema_version=_text(
                payload.get("schema_version"),
                code="cover_fingerprint_invalid",
                field_name="schema_version",
            ),
            geometry_family=normalized["geometry_family"],
            evidence_shape=normalized["evidence_shape"],
            direction=normalized["direction"],
            geography_scope=normalized["geography_scope"],
            evidence_density=normalized["evidence_density"],
            domain_layer=normalized["domain_layer"],
            seed=seed,
            selection_reason=_text(
                payload.get("selection_reason"),
                code="cover_fingerprint_invalid",
                field_name="selection_reason",
            ),
        )


@dataclass(frozen=True)
class CoverFingerprintProjectionRequest:
    schema_version: str = field(
        metadata={"doc": "Cover fingerprint projection request schema version."}
    )
    file_id: str = field(metadata={"doc": "Stable report source identifier."})
    artifact_hash: str = field(
        metadata={"doc": "Hash of the grounded report artifacts."}
    )
    region: str = field(metadata={"doc": "Source geography label."})
    cover_semantics: Dict[str, object] = field(
        metadata={"doc": "Validated grounded cover-semantics artifact."}
    )


@dataclass(frozen=True)
class ReportCardManifestRequest:
    schema_version: str = field(
        metadata={"doc": "Report-card manifest projection request schema version."}
    )
    title: str = field(metadata={"doc": "Complete normalized report title."})
    publisher: str = field(metadata={"doc": "Report publisher display name."})
    published_date: str = field(metadata={"doc": "Report publication date."})
    region: str = field(metadata={"doc": "Source geography label."})
    covered_period: str = field(metadata={"doc": "Time period covered by the report."})
    tldr_compact: str = field(metadata={"doc": "Complete compact card TLDR."})
    tldr_standard: str = field(metadata={"doc": "Complete standard card TLDR."})
    insights_final: Tuple[Dict[str, object], ...] = field(
        metadata={"doc": "Ranked grounded insight records."}
    )
    fingerprint: CoverFingerprint = field(
        metadata={"doc": "Completed semantic cover fingerprint."}
    )
    covers: CardCoverAssetSet = field(
        metadata={"doc": "Completed three-size cover asset set."}
    )
    source_title: str = field(
        default="", metadata={"doc": "Public canonical source title, when available."}
    )
    source_url: str = field(
        default="", metadata={"doc": "Public canonical source URL, when available."}
    )
    source_note: str = field(
        default="", metadata={"doc": "Public source note without diagnostic details."}
    )
    source_metadata_hash: str = field(
        default="", metadata={"doc": "Resolved source-metadata compatibility hash."}
    )
    source_identity_status: str = field(
        default="unknown", metadata={"doc": "Canonical source identity status."}
    )
    source_publication_date_status: str = field(
        default="unknown", metadata={"doc": "Canonical publication-date status."}
    )


@dataclass(frozen=True)
class ReportCardManifest:
    schema_version: str = field(
        metadata={"doc": "Report-card manifest schema version."}
    )
    title: str = field(metadata={"doc": "Complete normalized report title."})
    title_scale: str = field(metadata={"doc": "Validated card title scale class."})
    publisher: str = field(metadata={"doc": "Report publisher display name."})
    published_date: str = field(metadata={"doc": "Report publication date."})
    geography_label: str = field(
        metadata={"doc": "Normalized geography display label."}
    )
    geography_scope: str = field(metadata={"doc": "Normalized geography scope."})
    covered_period: str = field(metadata={"doc": "Time period covered by the report."})
    tldr_compact: str = field(
        metadata={"doc": "Complete compact TLDR of at most 18 words."}
    )
    tldr_standard: str = field(
        metadata={"doc": "Complete standard TLDR of at most 45 words."}
    )
    key_insights: Tuple[str, str] = field(
        metadata={"doc": "Exactly two complete ranked key insights."}
    )
    fingerprint: CoverFingerprint = field(
        metadata={"doc": "Semantic cover fingerprint."}
    )
    covers: CardCoverAssetSet = field(metadata={"doc": "Three canonical cover assets."})
    source_title: str = field(
        default="", metadata={"doc": "Public canonical source title, when available."}
    )
    source_url: str = field(
        default="", metadata={"doc": "Public canonical source URL, when available."}
    )
    source_note: str = field(
        default="", metadata={"doc": "Public source note without diagnostic details."}
    )
    source_metadata_hash: str = field(
        default="", metadata={"doc": "Resolved source-metadata compatibility hash."}
    )
    source_identity_status: str = field(
        default="unknown", metadata={"doc": "Canonical source identity status."}
    )
    source_publication_date_status: str = field(
        default="unknown", metadata={"doc": "Canonical publication-date status."}
    )

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "ReportCardManifest":
        title_scale = _text(
            payload.get("title_scale"),
            code="card_title_overflow",
            field_name="title_scale",
        )
        if title_scale not in TITLE_SCALES:
            raise _invalid(
                "card_title_overflow",
                "title_scale is not approved",
                context={"title_scale": title_scale},
            )
        raw_insights = payload.get("key_insights")
        if not isinstance(raw_insights, (list, tuple)) or len(raw_insights) != 2:
            raise _invalid(
                "card_key_insights_invalid",
                "Exactly two complete card insights are required",
            )
        insights = tuple(
            _text(
                item,
                code="card_key_insights_invalid",
                field_name="key_insight",
            )
            for item in raw_insights
        )
        fingerprint_payload = _mapping(
            payload.get("fingerprint"),
            code="cover_fingerprint_invalid",
            field_name="fingerprint",
        )
        covers_payload = _mapping(
            payload.get("covers"),
            code="cover_asset_set_incomplete",
            field_name="covers",
        )
        geography_scope = _text(
            payload.get("geography_scope"),
            code="cover_fingerprint_invalid",
            field_name="geography_scope",
        )
        if geography_scope not in GEOGRAPHY_SCOPES:
            raise _invalid(
                "cover_fingerprint_invalid",
                "geography_scope is not approved",
            )
        return cls(
            schema_version=_text(
                payload.get("schema_version"),
                code="cover_fingerprint_invalid",
                field_name="schema_version",
            ),
            title=_text(
                payload.get("title"),
                code="card_title_overflow",
                field_name="title",
            ),
            title_scale=title_scale,
            publisher=_text(
                payload.get("publisher"),
                code="cover_fingerprint_invalid",
                field_name="publisher",
            ),
            published_date=_text(
                payload.get("published_date"),
                code="cover_fingerprint_invalid",
                field_name="published_date",
                allow_empty=True,
            ),
            geography_label=_text(
                payload.get("geography_label"),
                code="cover_fingerprint_invalid",
                field_name="geography_label",
                allow_empty=geography_scope == "unknown",
            ),
            geography_scope=geography_scope,
            covered_period=_text(
                payload.get("covered_period"),
                code="cover_fingerprint_invalid",
                field_name="covered_period",
                allow_empty=True,
            ),
            tldr_compact=_complete_sentence(
                payload.get("tldr_compact"),
                limit=18,
                code="card_tldr_compact_invalid",
                field_name="tldr_compact",
            ),
            tldr_standard=_complete_sentence(
                payload.get("tldr_standard"),
                limit=45,
                code="card_tldr_standard_invalid",
                field_name="tldr_standard",
            ),
            key_insights=(insights[0], insights[1]),
            fingerprint=CoverFingerprint.from_dict(fingerprint_payload),
            covers=CardCoverAssetSet.from_dict(covers_payload),
            source_title=_text(
                payload.get("source_title"),
                code="cover_fingerprint_invalid",
                field_name="source_title",
                allow_empty=True,
            ),
            source_url=_text(
                payload.get("source_url"),
                code="cover_fingerprint_invalid",
                field_name="source_url",
                allow_empty=True,
            ),
            source_note=_text(
                payload.get("source_note"),
                code="cover_fingerprint_invalid",
                field_name="source_note",
                allow_empty=True,
            ),
            source_metadata_hash=_text(
                payload.get("source_metadata_hash"),
                code="cover_fingerprint_invalid",
                field_name="source_metadata_hash",
                allow_empty=True,
            ),
            source_identity_status=_text(
                payload.get("source_identity_status") or "unknown",
                code="cover_fingerprint_invalid",
                field_name="source_identity_status",
            ),
            source_publication_date_status=_text(
                payload.get("source_publication_date_status") or "unknown",
                code="cover_fingerprint_invalid",
                field_name="source_publication_date_status",
            ),
        )


@dataclass(frozen=True)
class ReportCardManifestWriteRequest:
    schema_version: str = field(
        metadata={"doc": "Report-card manifest write request schema version."}
    )
    output_dir: str = field(metadata={"doc": "Canonical report output directory."})
    manifest: ReportCardManifest = field(
        metadata={"doc": "Validated report-card manifest."}
    )


@dataclass(frozen=True)
class ReportCardManifestWriteResponse:
    schema_version: str = field(
        metadata={"doc": "Report-card manifest write response schema version."}
    )
    manifest_path: str = field(metadata={"doc": "Resolved manifest JSON path."})
    bytes_written: int = field(metadata={"doc": "Number of bytes written."})
