from __future__ import annotations

import hashlib
from dataclasses import asdict
from typing import Mapping

from src.contracts.report_cards import (
    CoverFingerprint,
    CoverFingerprintProjectionRequest,
    ReportCardManifest,
    ReportCardManifestRequest,
)
from src.utils.errors import AppError

_PLACEHOLDER_METADATA = {
    "",
    "...",
    "not extracted",
    "not specified",
    "unknown",
    "unknown publisher",
    "n/a",
    "na",
    "-",
}
_OPTIONAL_CARD_METADATA_FIELDS = frozenset({"region", "covered_period", "period"})
_LEAKED_FIELD_PREFIXES = {
    "publisher",
    "region",
    "period",
    "time period",
    "year",
    "category",
    "source",
    "raw_page_text",
}
_EXTRACTION_LEAKAGE_MARKERS = {
    "ocr text block",
    "table row",
    "table ",
    "row:",
    "cell_",
    "raw_page_text",
    "extracted_text",
    "text block",
}


def select_geometry_family(semantics: dict[str, object]) -> str:
    shape = str(semantics.get("evidence_shape") or "").strip()
    direction = str(semantics.get("direction") or "neutral").strip()
    domain = str(semantics.get("domain_layer") or "").strip()
    if shape == "trend" and domain == "forecast":
        return "forecast_horizon"
    if shape == "trend" and direction == "rising":
        return "ascending_trajectory"
    if shape == "trend" and direction == "falling":
        return "descending_trajectory"
    if shape == "trend" and direction == "volatile":
        return "volatility_corridor"
    if shape == "trend" and direction == "diverging":
        return "split_horizon"
    if shape == "trend" and direction == "converging":
        return "signal_lattice"
    if shape == "trend" and direction == "neutral":
        return "interlaced_mesh"
    if shape == "comparison" and direction == "converging":
        return "convergence_funnel"
    if shape == "comparison" and direction == "diverging":
        return "divergence_fan"
    mapping = {
        "comparison": "parallel_bands",
        "distribution": "distribution_field",
        "flow": "flow_channels",
        "network": "network_constellation",
        "concentration": "concentration_core",
        "cycle": "cycle_orbit",
        "uncertainty": "uncertainty_envelope",
        "system": "system_matrix",
    }
    if shape == "hierarchy":
        return "hierarchy_terraces" if direction == "stable" else "ranked_strata"
    try:
        return mapping[shape]
    except KeyError as exc:
        raise AppError(
            code="cover_fingerprint_invalid",
            message="Cover semantics do not map to an approved geometry family",
            retryable=False,
            context={
                "evidence_shape": shape,
                "direction": direction,
                "domain_layer": domain,
            },
        ) from exc


def classify_geography(region: str) -> tuple[str, str]:
    normalized = " ".join(str(region or "").split())
    folded = normalized.casefold()
    if not normalized:
        return "", "unknown"
    if folded in {"global", "worldwide", "international", "multi-market"} or (
        "," in normalized
    ):
        return normalized, "global"
    if folded in {
        "europe",
        "asia pacific",
        "latin america",
        "middle east",
        "africa",
        "north america",
    }:
        return normalized, "regional"
    return normalized, "country"


def select_title_scale(title: str) -> str:
    normalized = " ".join(str(title or "").split())
    count = len(normalized)
    longest_token = max(
        (len(token) for token in normalized.replace("-", " ").split()),
        default=0,
    )
    if not normalized or count > 120 or longest_token > 32:
        raise AppError(
            code="card_title_overflow",
            message="Complete report title does not fit the approved card title scale",
            retryable=False,
            context={
                "character_count": count,
                "longest_token": longest_token,
            },
        )
    if count <= 42:
        return "short"
    if count <= 64:
        return "medium"
    if count <= 88:
        return "long"
    return "xlong"


def stable_cover_seed(file_id: str, artifact_hash: str) -> int:
    material = f"{file_id.strip()}:{artifact_hash.strip()}".encode("utf-8")
    return int(hashlib.sha256(material).hexdigest()[:8], 16)


def validate_public_metadata_governance(
    values: Mapping[str, object],
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    blocked_fields: list[str] = []
    for field_name, raw_value in values.items():
        text = " ".join(str(raw_value or "").split())
        folded = text.casefold()
        normalized[str(field_name)] = text
        if (
            str(field_name) in _OPTIONAL_CARD_METADATA_FIELDS
            and folded in _PLACEHOLDER_METADATA
        ):
            # A missing optional label must be omitted from public metadata,
            # never published as an extraction placeholder.
            normalized[str(field_name)] = ""
            continue
        if folded in _PLACEHOLDER_METADATA:
            blocked_fields.append(str(field_name))
            continue
        if any(marker in folded for marker in _EXTRACTION_LEAKAGE_MARKERS):
            blocked_fields.append(str(field_name))
            continue
        prefix, separator, remainder = text.partition(":")
        if (
            separator
            and remainder.strip()
            and (
                prefix.strip().casefold() in _LEAKED_FIELD_PREFIXES
                or any(f" {label}:" in f" {folded}" for label in _LEAKED_FIELD_PREFIXES)
            )
        ):
            blocked_fields.append(str(field_name))
            continue
        if str(field_name) in {"region", "covered_period", "period"}:
            word_count = len(text.split())
            if word_count > 6 or text.endswith("."):
                blocked_fields.append(str(field_name))
    if blocked_fields:
        raise AppError(
            code="public_metadata_governance_blocked",
            message="Public metadata contains placeholder or extraction-leakage values",
            retryable=False,
            severity="error",
            context={"blocked_fields": sorted(set(blocked_fields))},
        )
    return normalized


def build_cover_fingerprint(
    request: CoverFingerprintProjectionRequest,
) -> CoverFingerprint:
    _, geography_scope = classify_geography(request.region)
    semantics = request.cover_semantics
    return CoverFingerprint.from_dict(
        {
            "schema_version": "1.0",
            "geometry_family": select_geometry_family(semantics),
            "evidence_shape": semantics.get("evidence_shape"),
            "direction": semantics.get("direction"),
            "geography_scope": geography_scope,
            "evidence_density": semantics.get("evidence_density"),
            "domain_layer": semantics.get("domain_layer"),
            "seed": stable_cover_seed(request.file_id, request.artifact_hash),
            "selection_reason": semantics.get("selection_reason"),
        }
    )


def build_report_card_manifest(
    request: ReportCardManifestRequest,
) -> ReportCardManifest:
    governed = validate_public_metadata_governance(
        {
            "publisher": request.publisher,
            "region": request.region,
            "covered_period": request.covered_period,
        }
    )
    insights = tuple(
        " ".join(str(item.get("text") or "").split())
        for item in request.insights_final[:2]
    )
    if len(insights) != 2 or any(not insight for insight in insights):
        raise AppError(
            code="card_key_insights_invalid",
            message="Exactly two complete card insights are required",
            retryable=False,
        )
    geography_label, geography_scope = classify_geography(governed["region"])
    return ReportCardManifest.from_dict(
        {
            "schema_version": "1.0",
            "title": " ".join(request.title.split()),
            "title_scale": select_title_scale(request.title),
            "publisher": governed["publisher"],
            "published_date": request.published_date,
            "geography_label": geography_label,
            "geography_scope": geography_scope,
            "covered_period": governed["covered_period"],
            "tldr_compact": " ".join(request.tldr_compact.split()),
            "tldr_standard": " ".join(request.tldr_standard.split()),
            "key_insights": insights,
            "fingerprint": asdict(request.fingerprint),
            "covers": asdict(request.covers),
            "source_title": " ".join(request.source_title.split()),
            "source_url": " ".join(request.source_url.split()),
            "source_note": " ".join(request.source_note.split()),
            "source_metadata_hash": request.source_metadata_hash,
            "source_identity_status": request.source_identity_status,
            "source_publication_date_status": request.source_publication_date_status,
        }
    )
