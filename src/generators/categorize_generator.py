from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List

from src.contracts.categories import (
    CategoryAssignment,
    CategoryClassificationConfig,
    CategoryDefinition,
    CategoryMappingLoadResponse,
    CategoryScoreDetail,
)
from src.contracts.run_context import RunContext
from src.contracts.taxonomy import TaxonomyExtractResponse
from src.utils.logging import log_event
from src.utils.tag_utils import normalize_slug_tag

logger = logging.getLogger("market_lense.categorize_generator")


@dataclass
class _CategoryAccumulator:
    matched_tags: List[str] = field(default_factory=list)
    matched_norms: set[str] = field(default_factory=set)
    strong_norms: set[str] = field(default_factory=set)
    generic_norms: set[str] = field(default_factory=set)
    negative_norms: set[str] = field(default_factory=set)
    evidence_tag_norms: set[str] = field(default_factory=set)
    evidence_section_keys: set[str] = field(default_factory=set)
    secondary_tier_norms: set[str] = field(default_factory=set)
    score_raw: float = 0.0

    def remember_tag(self, tag: str, norm: str) -> None:
        if norm in self.matched_norms:
            return
        self.matched_norms.add(norm)
        self.matched_tags.append(tag)


@dataclass(frozen=True)
class _SignalBinding:
    category_id: str
    signal_kind: str
    generic: bool
    weight: float


@dataclass
class _TaxonomyTagContext:
    tier: str = ""
    section_keys: set[str] = field(default_factory=set)


def categorize_taxonomy(
    taxonomy: List[str] | TaxonomyExtractResponse,
    mappings: CategoryMappingLoadResponse,
    ctx: RunContext,
) -> CategoryAssignment:
    config = mappings.mappings.classification
    taxonomy_tags, tag_context = _normalize_taxonomy_input(taxonomy)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="categorize_start",
            module=logger.name,
            fields={
                "taxonomy_count": len(taxonomy_tags),
                "categories": len(mappings.mappings.categories),
                "max_categories": config.max_categories,
                "min_primary_score": config.min_primary_score,
                "min_secondary_score": config.min_secondary_score,
            },
        )
    )

    cat_id_to_def: Dict[str, CategoryDefinition] = {
        cat.id: cat for cat in mappings.mappings.categories
    }
    signal_index = _build_signal_index(mappings.mappings.categories, config)
    descriptor_norms = _build_descriptor_norms(mappings.mappings.categories)
    positive_signal_frequency = _positive_signal_frequency(signal_index)

    accumulators: Dict[str, _CategoryAccumulator] = defaultdict(_CategoryAccumulator)
    unmapped: List[str] = []
    unmapped_norms: set[str] = set()
    seen_signal_tags: set[str] = set()
    for raw_tag in taxonomy_tags:
        tag = (raw_tag or "").strip()
        if not tag:
            continue
        norm = normalize_slug_tag(tag)
        if not norm:
            continue
        bindings = signal_index.get(norm) or []
        if not bindings:
            if norm in descriptor_norms:
                continue
            if norm not in unmapped_norms:
                unmapped_norms.add(norm)
                unmapped.append(tag)
            continue
        seen_signal_tags.add(norm)
        for binding in bindings:
            accumulator = accumulators[binding.category_id]
            if binding.signal_kind == "negative":
                accumulator.score_raw += binding.weight
                accumulator.negative_norms.add(norm)
                continue
            frequency = max(1, positive_signal_frequency.get(norm, 1))
            accumulator.score_raw += binding.weight / frequency
            accumulator.remember_tag(tag, norm)
            if binding.generic:
                accumulator.generic_norms.add(norm)
            else:
                accumulator.strong_norms.add(norm)
                _apply_taxonomy_tag_context(accumulator, norm, tag_context)

    score_details = _build_score_details(
        accumulators=accumulators,
        cat_id_to_def=cat_id_to_def,
        config=config,
    )
    selected_details = _select_categories(score_details, cat_id_to_def, config)
    categories = [detail.category_id for detail in selected_details]
    labels = [detail.label for detail in selected_details]

    assignment = CategoryAssignment(
        schema_version="1.1",
        categories=categories,
        category_labels=labels,
        unmapped_tags=unmapped,
        score_details=score_details,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="categorize_complete",
            module=logger.name,
            fields={
                "assigned": assignment.categories,
                "unmapped": assignment.unmapped_tags,
                "matched_signal_tags": sorted(seen_signal_tags),
                "score_details": [
                    {
                        "category_id": detail.category_id,
                        "score": round(detail.score, 4),
                        "strong_match_count": detail.strong_match_count,
                        "generic_match_count": detail.generic_match_count,
                        "eligible": detail.eligible,
                        "skip_reason": detail.skip_reason,
                    }
                    for detail in score_details[:6]
                ],
            },
        )
    )
    return assignment


def _build_signal_index(
    categories: List[CategoryDefinition],
    config: CategoryClassificationConfig,
) -> Dict[str, List[_SignalBinding]]:
    global_generic_norms = {
        normalize_slug_tag(tag)
        for tag in config.global_generic_tags
        if normalize_slug_tag(tag)
    }
    tag_to_bindings: Dict[str, List[_SignalBinding]] = defaultdict(list)
    for category in categories:
        category_signals: dict[str, _SignalBinding] = {}
        for tag in category.generic_tags:
            norm = normalize_slug_tag(tag)
            if not norm:
                continue
            category_signals[norm] = _SignalBinding(
                category_id=category.id,
                signal_kind="generic",
                generic=True,
                weight=config.generic_tag_weight,
            )
        for tag in category.tags:
            norm = normalize_slug_tag(tag)
            if not norm:
                continue
            category_signals[norm] = _SignalBinding(
                category_id=category.id,
                signal_kind="legacy",
                generic=False,
                weight=config.legacy_tag_weight,
            )
        for tag in category.supporting_tags:
            norm = normalize_slug_tag(tag)
            if not norm:
                continue
            category_signals[norm] = _SignalBinding(
                category_id=category.id,
                signal_kind="supporting",
                generic=False,
                weight=config.supporting_tag_weight,
            )
        for tag in category.secondary_supporting_tags:
            norm = normalize_slug_tag(tag)
            if not norm:
                continue
            category_signals[norm] = _SignalBinding(
                category_id=category.id,
                signal_kind="secondary_supporting",
                generic=False,
                weight=config.supporting_tag_weight,
            )
        for tag in category.core_tags:
            norm = normalize_slug_tag(tag)
            if not norm:
                continue
            category_signals[norm] = _SignalBinding(
                category_id=category.id,
                signal_kind="core",
                generic=False,
                weight=config.core_tag_weight,
            )
        for norm, binding in list(category_signals.items()):
            if (
                binding.signal_kind in {"legacy", "supporting"}
                and norm in global_generic_norms
            ):
                category_signals[norm] = _SignalBinding(
                    category_id=binding.category_id,
                    signal_kind="generic",
                    generic=True,
                    weight=config.generic_tag_weight,
                )
        for tag in category.negative_tags:
            norm = normalize_slug_tag(tag)
            if not norm or norm in category_signals:
                continue
            category_signals[norm] = _SignalBinding(
                category_id=category.id,
                signal_kind="negative",
                generic=False,
                weight=config.negative_tag_weight,
            )
        for norm, binding in category_signals.items():
            tag_to_bindings[norm].append(binding)
    return dict(tag_to_bindings)


def _positive_signal_frequency(
    signal_index: Dict[str, List[_SignalBinding]],
) -> Dict[str, int]:
    frequencies: Dict[str, int] = {}
    for norm, bindings in signal_index.items():
        positive_categories = {
            binding.category_id
            for binding in bindings
            if binding.signal_kind != "negative"
        }
        frequencies[norm] = max(1, len(positive_categories))
    return frequencies


def _build_descriptor_norms(categories: List[CategoryDefinition]) -> set[str]:
    descriptor_norms: set[str] = set()
    for category in categories:
        for tag in category.descriptor_tags:
            norm = normalize_slug_tag(tag)
            if norm:
                descriptor_norms.add(norm)
    return descriptor_norms


def _build_score_details(
    *,
    accumulators: Dict[str, _CategoryAccumulator],
    cat_id_to_def: Dict[str, CategoryDefinition],
    config: CategoryClassificationConfig,
) -> List[CategoryScoreDetail]:
    score_details: List[CategoryScoreDetail] = []
    for cat_id, category in cat_id_to_def.items():
        accumulator = accumulators.get(cat_id) or _CategoryAccumulator()
        bonus = max(0, len(accumulator.strong_norms) - 1) * config.repeated_match_bonus
        score = accumulator.score_raw + bonus
        skip_reason = ""
        eligible = True
        if not category.portal_exposed:
            eligible = False
            skip_reason = "not_portal_exposed"
        elif score <= 0.0:
            eligible = False
            skip_reason = "non_positive_score"
        elif len(accumulator.strong_norms) == 0:
            eligible = False
            skip_reason = "generic_only_matches"
        elif score < config.min_secondary_score:
            eligible = False
            skip_reason = "below_secondary_threshold"
        must_have_match_count = len(
            {
                norm
                for norm in accumulator.strong_norms
                if norm
                in {
                    normalize_slug_tag(tag)
                    for tag in category.must_have_one_of
                    if normalize_slug_tag(tag)
                }
            }
        )
        secondary_rescue_eligible = _is_secondary_rescue_eligible(
            score=score,
            strong_match_count=len(accumulator.strong_norms),
            evidence_tag_count=len(accumulator.evidence_tag_norms),
            evidence_section_count=len(accumulator.evidence_section_keys),
            secondary_tier_match_count=len(accumulator.secondary_tier_norms),
            must_have_match_count=must_have_match_count,
            primary_score=0.0,
            category=category,
            config=config,
        )
        score_details.append(
            CategoryScoreDetail(
                category_id=cat_id,
                label=_category_label(cat_id, cat_id_to_def),
                score=round(score, 6),
                matched_tags=list(accumulator.matched_tags),
                strong_match_count=len(accumulator.strong_norms),
                generic_match_count=len(accumulator.generic_norms),
                evidence_tag_count=len(accumulator.evidence_tag_norms),
                evidence_section_count=len(accumulator.evidence_section_keys),
                secondary_tier_match_count=len(accumulator.secondary_tier_norms),
                must_have_match_count=must_have_match_count,
                secondary_rescue_eligible=secondary_rescue_eligible,
                eligible=eligible,
                skip_reason=skip_reason,
            )
        )
    score_details.sort(
        key=lambda detail: (
            -detail.score,
            -detail.strong_match_count,
            -cat_id_to_def[detail.category_id].priority,
            detail.category_id,
        )
    )
    return score_details


def _select_categories(
    score_details: List[CategoryScoreDetail],
    cat_id_to_def: Dict[str, CategoryDefinition],
    config: CategoryClassificationConfig,
) -> List[CategoryScoreDetail]:
    primary: CategoryScoreDetail | None = None
    for detail in score_details:
        if not detail.eligible:
            continue
        if detail.score < config.min_primary_score:
            continue
        primary = detail
        break
    if primary is None:
        return []

    selected = [primary]
    for detail in score_details:
        if detail.category_id == primary.category_id or not detail.eligible:
            continue
        if len(selected) >= max(1, config.max_categories):
            break
        if detail.score < config.min_secondary_score:
            continue
        if detail.score < primary.score * config.secondary_score_ratio:
            category = cat_id_to_def[detail.category_id]
            if not _is_secondary_rescue_eligible(
                score=detail.score,
                strong_match_count=detail.strong_match_count,
                evidence_tag_count=detail.evidence_tag_count,
                evidence_section_count=detail.evidence_section_count,
                secondary_tier_match_count=detail.secondary_tier_match_count,
                must_have_match_count=detail.must_have_match_count,
                primary_score=primary.score,
                category=category,
                config=config,
            ):
                continue
        selected.append(detail)
    return selected


def _normalize_taxonomy_input(
    taxonomy: List[str] | TaxonomyExtractResponse,
) -> tuple[List[str], Dict[str, _TaxonomyTagContext]]:
    if isinstance(taxonomy, TaxonomyExtractResponse):
        contexts: Dict[str, _TaxonomyTagContext] = {}
        for item in taxonomy.tag_evidence:
            norm = normalize_slug_tag(item.tag)
            if not norm:
                continue
            context = contexts.setdefault(norm, _TaxonomyTagContext())
            if item.tier in {"primary", "secondary"}:
                context.tier = item.tier
            section_key = normalize_slug_tag(item.section_label)
            if section_key:
                context.section_keys.add(section_key)
        tags = []
        seen = set()
        for raw_tag in (
            list(taxonomy.taxonomy or [])
            + list(taxonomy.primary_tags or [])
            + list(taxonomy.secondary_tags or [])
            + [item.tag for item in taxonomy.tag_evidence]
        ):
            tag = (raw_tag or "").strip()
            if not tag:
                continue
            norm = normalize_slug_tag(tag)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            tags.append(tag)
        return tags, contexts
    return list(taxonomy or []), {}


def _apply_taxonomy_tag_context(
    accumulator: _CategoryAccumulator,
    norm: str,
    tag_context: Dict[str, _TaxonomyTagContext],
) -> None:
    context = tag_context.get(norm)
    if context is None:
        return
    if context.section_keys:
        accumulator.evidence_tag_norms.add(norm)
        accumulator.evidence_section_keys.update(context.section_keys)
    if context.tier == "secondary":
        accumulator.secondary_tier_norms.add(norm)


def _is_secondary_rescue_eligible(
    *,
    score: float,
    strong_match_count: int,
    evidence_tag_count: int,
    evidence_section_count: int,
    secondary_tier_match_count: int,
    must_have_match_count: int,
    primary_score: float,
    category: CategoryDefinition,
    config: CategoryClassificationConfig,
) -> bool:
    if primary_score > 0.0 and score < primary_score * config.secondary_rescue_score_ratio:
        return False
    if strong_match_count < config.secondary_rescue_min_strong_matches:
        return False
    if evidence_tag_count < config.secondary_rescue_min_evidence_tags:
        return False
    if evidence_section_count < config.secondary_rescue_min_evidence_sections:
        return False
    if secondary_tier_match_count < 1:
        return False
    if category.must_have_one_of and must_have_match_count < 1:
        return False
    return True


def _category_label(cat_id: str, defs: Dict[str, CategoryDefinition]) -> str:
    cat = defs.get(cat_id)
    if not cat:
        return cat_id
    return cat.label or cat.id
