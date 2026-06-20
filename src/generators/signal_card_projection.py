from __future__ import annotations

import hashlib

from src.contracts.report_cards import CoverFingerprint, GEOMETRY_FAMILIES
from src.contracts.signal_cards import SIGNAL_CARD_SCHEMA_VERSION, SignalCardContent
from src.utils.errors import AppError


SIGNAL_COVER_FAMILIES = GEOMETRY_FAMILIES

_FAMILY_SEMANTICS: dict[str, tuple[str, str]] = {
    "ascending_trajectory": ("trend", "rising"),
    "descending_trajectory": ("trend", "falling"),
    "volatility_corridor": ("trend", "volatile"),
    "convergence_funnel": ("comparison", "converging"),
    "divergence_fan": ("comparison", "diverging"),
    "parallel_bands": ("comparison", "neutral"),
    "ranked_strata": ("hierarchy", "stable"),
    "distribution_field": ("distribution", "neutral"),
    "concentration_core": ("concentration", "stable"),
    "flow_channels": ("flow", "neutral"),
    "network_constellation": ("network", "neutral"),
    "hierarchy_terraces": ("hierarchy", "stable"),
    "cycle_orbit": ("cycle", "cyclical"),
    "forecast_horizon": ("trend", "rising"),
    "uncertainty_envelope": ("uncertainty", "volatile"),
    "system_matrix": ("system", "neutral"),
    "interlaced_mesh": ("network", "neutral"),
    "radial_pulse": ("concentration", "stable"),
    "split_horizon": ("comparison", "neutral"),
    "signal_lattice": ("system", "neutral"),
}


def _normalized(value: str) -> str:
    return " ".join(value.split())


def _stable_seed(
    *,
    title: str,
    source_report_ids: list[str],
    evidence_ids: list[str],
    confidence: float,
) -> int:
    material = "|".join(
        [
            _normalized(title),
            *sorted(_normalized(value) for value in source_report_ids),
            *sorted(_normalized(value) for value in evidence_ids),
            f"{confidence:.6f}",
        ]
    )
    return int(hashlib.sha256(material.encode("utf-8")).hexdigest()[:8], 16)


def build_signal_card_content(
    *,
    title: str,
    summary: str,
    confidence: float,
    source_report_ids: list[str],
    evidence_ids: list[str],
    uncertainty: str,
) -> SignalCardContent:
    normalized_title = _normalized(title)
    normalized_summary = _normalized(summary)
    normalized_uncertainty = _normalized(uncertainty)
    source_count = len({value for value in source_report_ids if _normalized(value)})
    evidence_count = len({value for value in evidence_ids if _normalized(value)})
    if not normalized_title or not normalized_summary or not normalized_uncertainty:
        raise AppError(
            code="signal_card_contract_invalid",
            message="Signal card title, summary, and uncertainty must be populated",
            retryable=False,
        )
    if not 0.0 <= confidence <= 1.0 or source_count < 1 or evidence_count < 1:
        raise AppError(
            code="signal_card_contract_invalid",
            message="Signal card confidence and grounded counts are invalid",
            retryable=False,
            context={
                "confidence": confidence,
                "source_count": source_count,
                "evidence_count": evidence_count,
            },
        )

    seed = _stable_seed(
        title=normalized_title,
        source_report_ids=source_report_ids,
        evidence_ids=evidence_ids,
        confidence=confidence,
    )
    geometry_family = SIGNAL_COVER_FAMILIES[seed % len(SIGNAL_COVER_FAMILIES)]
    evidence_shape, direction = _FAMILY_SEMANTICS[geometry_family]
    fingerprint = CoverFingerprint(
        schema_version="1.0",
        geometry_family=geometry_family,
        evidence_shape=evidence_shape,
        direction=direction,
        geography_scope="unknown",
        evidence_density="metric_rich" if evidence_count >= 6 else "balanced",
        domain_layer="grid",
        seed=seed,
        selection_reason=(
            "Signal cover family selected deterministically from the grounded title, "
            "source report IDs, evidence IDs, and confidence."
        ),
    )
    return SignalCardContent(
        schema_version=SIGNAL_CARD_SCHEMA_VERSION,
        summary=normalized_summary,
        confidence=confidence,
        source_count=source_count,
        evidence_count=evidence_count,
        uncertainty=normalized_uncertainty,
        fingerprint=fingerprint,
    )
