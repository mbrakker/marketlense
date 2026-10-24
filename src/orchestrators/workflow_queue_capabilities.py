"""Lightweight capability metadata for the canonical workflow queue graph.

This module is intentionally independent from queue handler implementations.
Preflight may import it to derive capability requirements without importing the
heavy handler registry and creating an orchestrator import cycle.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from src.contracts.workflow_queue import WORKFLOW_QUEUE_NAMES


_EFFECT_CAPABILITY_FAMILIES: dict[str, str] = {
    "browser": "browser",
    "drive": "google_drive",
    "embedding": "openai_embedding_model",
    "filesystem": "writable_storage",
    "mailbox": "mailbox",
    "model": "llm_model",
    "ocr": "ocr_model",
    "pdf": "pdf_dependencies",
    "vector": "vector_store",
    "vision": "llm_model",
    "wordpress": "wordpress",
}


# The queue registry remains responsible for handlers, payloads, and graph
# edges.  This small manifest is the canonical source for capability-relevant
# external effects so preflight can inspect it without loading those handlers.
_QUEUE_EXTERNAL_EFFECTS: dict[str, tuple[str, ...]] = {
    "publisher_discovery": ("browser", "drive"),
    "report_acquisition": ("browser", "drive"),
    "mailbox_delivery": ("mailbox", "browser", "drive"),
    "source_ingest": ("pdf", "ocr"),
    "report_selection": ("pdf", "vision"),
    "report_analysis": ("model", "vector"),
    "report_render": ("filesystem",),
    "analytics_projection": (),
    "claim_embedding": ("embedding",),
    "signal_candidate": (),
    "signal_generation": ("model",),
    "briefing_opportunity": (),
    "briefing_generation": ("model",),
    "cover_generation": (),
    "publication_readiness": (),
    "wordpress_publish": ("wordpress",),
    "wordpress_projection": ("wordpress",),
    "artifact_repair": (),
    "source_revalidation": ("browser",),
    "malformed_pdf_revalidation": ("pdf",),
    "recategorization": (),
    "vector_retention": ("vector",),
    "wordpress_category_update": ("wordpress",),
    "public_render_repair": (),
    "cost_reconciliation": (),
    "release_evidence_generation": (),
}


# Most queues need no prompt/profile overlay: their capability requirements are
# derived from the declared effects above.  These few routes have additional
# configured prompt or provider semantics that cannot be inferred from effects.
_PREFLIGHT_PROFILE_OVERRIDES: dict[str, str] = {
    "publisher_discovery": "publisher_inventory",
    "report_acquisition": "report_download",
    "mailbox_delivery": "report_download",
    "report_selection": "report_generation",
    "report_analysis": "report_generation",
    "briefing_generation": "cross_report_analysis",
    "wordpress_publish": "publishing",
    "wordpress_projection": "wordpress_sync",
    "artifact_repair": "report_generation",
    "source_revalidation": "browser_acquisition",
    "recategorization": "report_generation",
    "vector_retention": "report_generation",
    "wordpress_category_update": "publishing",
    "public_render_repair": "report_generation",
}


@dataclass(frozen=True)
class WorkflowQueueCapabilityRegistration:
    """Capability-relevant metadata for one canonical workflow queue."""

    queue_name: str
    job_type: str
    expected_external_effects: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    preflight_profile: str | None = None


def capabilities_from_external_effects(effects: Sequence[str]) -> tuple[str, ...]:
    """Resolve declared queue effects to known capability families."""

    normalized = {str(effect).strip() for effect in effects if str(effect).strip()}
    unknown = sorted(normalized - set(_EFFECT_CAPABILITY_FAMILIES))
    if unknown:
        raise ValueError(
            "Workflow queue declares unrecognized external effects: "
            + ", ".join(unknown)
        )
    return tuple(sorted({_EFFECT_CAPABILITY_FAMILIES[effect] for effect in normalized}))


def canonical_external_effects(queue_name: str) -> tuple[str, ...]:
    """Return the canonical external effects declared for a queue."""

    normalized_queue = str(queue_name or "").strip()
    if normalized_queue not in WORKFLOW_QUEUE_NAMES:
        raise ValueError(f"Unknown canonical workflow queue: {normalized_queue}")
    try:
        effects = _QUEUE_EXTERNAL_EFFECTS[normalized_queue]
    except KeyError as exc:  # pragma: no cover - protects future contract drift
        raise ValueError(
            f"Canonical workflow queue lacks capability metadata: {normalized_queue}"
        ) from exc
    return tuple(sorted(effects))


def canonical_workflow_queue_capability_registration(
    queue_name: str,
) -> WorkflowQueueCapabilityRegistration | None:
    """Resolve capability metadata without importing queue handler code."""

    normalized_queue = str(queue_name or "").strip()
    if normalized_queue not in WORKFLOW_QUEUE_NAMES:
        return None
    effects = canonical_external_effects(normalized_queue)
    return WorkflowQueueCapabilityRegistration(
        queue_name=normalized_queue,
        job_type=f"{normalized_queue}.v1",
        expected_external_effects=effects,
        required_capabilities=capabilities_from_external_effects(effects),
        preflight_profile=_PREFLIGHT_PROFILE_OVERRIDES.get(normalized_queue),
    )


def preflight_profile_for_queue(queue_name: str) -> str | None:
    """Return only an explicit profile override; local routes resolve locally."""

    registration = canonical_workflow_queue_capability_registration(queue_name)
    return registration.preflight_profile if registration is not None else None


def validate_canonical_workflow_queue_capability_manifest() -> None:
    """Fail closed if the queue contract and capability manifest drift apart."""

    contract_queues = set(WORKFLOW_QUEUE_NAMES)
    manifest_queues = set(_QUEUE_EXTERNAL_EFFECTS)
    if contract_queues != manifest_queues:
        missing = sorted(contract_queues - manifest_queues)
        extra = sorted(manifest_queues - contract_queues)
        raise RuntimeError(
            "Workflow queue capability manifest does not cover the queue contract: "
            f"missing={missing}, extra={extra}"
        )


validate_canonical_workflow_queue_capability_manifest()
