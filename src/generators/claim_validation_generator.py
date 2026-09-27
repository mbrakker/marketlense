"""Deterministic retained-artifact claim validation before publish readiness."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from typing import Callable

from src.contracts.claim_validation import (
    CLAIM_VALIDATION_SCHEMA_VERSION,
    ClaimCandidate,
    ClaimEvidenceReference,
    ClaimKind,
    ClaimSemanticGroundingResult,
    ClaimSemanticInput,
    ClaimValidationCheck,
    ClaimValidationPackage,
    ClaimValidationResult,
)
from src.contracts.protected_facts import (
    ProtectedFactComparison,
    compare_protected_fact_texts,
)
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_from_payload,
    soft_copy_material_sentences,
)
from src.utils.errors import AppError
from src.utils.quantity import extract_quantities, quantities_match
from src.utils.text_normalization import normalize_for_lookup

_CAUSAL_RE = re.compile(
    r"\b(cause[sd]?|driv(?:e|es|en)|lead(?:s|ing)? to|result(?:s|ed)? in)\b", re.I
)
_INTERPRETIVE_RE = re.compile(
    r"\b(recommend|suggest|should|could|may|likely|interpret)\b", re.I
)
_QUOTED_RE = re.compile(r"""(?:"[^"]+"|“[^”]+”|‘[^’]+’|'[^']+')""")
_RECOVERY_TOKEN_RE = re.compile(r"[a-z]{4,}")
_RECOVERY_STOP_WORDS = {
    "about",
    "after",
    "against",
    "also",
    "among",
    "and",
    "are",
    "because",
    "been",
    "being",
    "between",
    "both",
    "but",
    "from",
    "have",
    "into",
    "more",
    "most",
    "over",
    "that",
    "than",
    "their",
    "there",
    "these",
    "this",
    "those",
    "through",
    "under",
    "were",
    "which",
    "while",
    "with",
}

SemanticValidator = Callable[[ClaimCandidate, list[str]], tuple[bool, str, str]]
SemanticBatchValidator = Callable[
    [list[ClaimSemanticInput]], list[ClaimSemanticGroundingResult]
]


@dataclass(frozen=True)
class _ClaimValidationInput:
    candidate: ClaimCandidate
    text: str
    require_all_evidence_references: bool = False
    provenance_error: str = ""


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _claim_kind(text: str) -> ClaimKind:
    if _QUOTED_RE.search(text):
        return "quotation"
    if extract_quantities(text):
        return "numeric"
    if _CAUSAL_RE.search(text):
        return "causal"
    if _INTERPRETIVE_RE.search(text):
        return "interpretive"
    return "descriptive"


def _factual(kind: ClaimKind) -> bool:
    return kind != "interpretive"


def _evidence_index(evidence_packs: dict) -> dict[str, tuple[str, str, int | None]]:
    indexed: dict[str, tuple[str, str, int | None]] = {}
    for pack_name, payload in sorted(evidence_packs.items()):
        if not isinstance(payload, dict):
            continue
        for value in payload.values():
            if not isinstance(value, list):
                continue
            for item in value:
                if not isinstance(item, dict):
                    continue
                evidence_id = str(
                    item.get("id") or item.get("evidence_id") or ""
                ).strip()
                text = " ".join(
                    str(item.get(key) or "").strip()
                    for key in (
                        "text",
                        "evidence",
                        "excerpt",
                        "quote",
                        "quote_text",
                        "description",
                        "summary",
                        "title",
                        "key_points",
                    )
                    if str(item.get(key) or "").strip()
                )
                if evidence_id and text:
                    page_value = item.get("page")
                    indexed[evidence_id] = (
                        pack_name,
                        text,
                        int(page_value) if isinstance(page_value, int) else None,
                    )
    return indexed


def _references(
    raw: object, evidence: dict[str, tuple[str, str, int | None]]
) -> list[ClaimEvidenceReference]:
    values: list[tuple[str, int | None]] = []
    if isinstance(raw, dict):
        root = str(raw.get("evidence_id") or "").strip()
        if root:
            values.append((root, None))
        for evidence_id in raw.get("evidence_ids") or []:
            value = str(evidence_id or "").strip()
            if value:
                values.append((value, None))
        for span in raw.get("evidence_spans") or []:
            if isinstance(span, dict) and str(span.get("evidence_id") or "").strip():
                values.append(
                    (
                        str(span["evidence_id"]).strip(),
                        span.get("page") if isinstance(span.get("page"), int) else None,
                    )
                )
    return [
        ClaimEvidenceReference(
            schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
            evidence_id=value,
            source_pack=evidence.get(value, ("", "", None))[0],
            page=page if page is not None else evidence.get(value, ("", "", None))[2],
            text_hash=_hash(evidence.get(value, ("", "", None))[1])
            if value in evidence
            else "",
        )
        for value, page in sorted(
            set(values), key=lambda item: (item[0], -1 if item[1] is None else item[1])
        )
    ]


def _candidates(
    artifacts: dict, evidence: dict[str, tuple[str, str, int | None]]
) -> list[_ClaimValidationInput]:
    output: list[_ClaimValidationInput] = []
    soft_copy_claims, soft_copy_provenance_error = _soft_copy_claims_by_hash(artifacts)

    def add(
        family: str,
        text: object,
        raw: object = None,
        *,
        classification: str = "",
        claim_id: str = "",
        affected_section: str = "",
        entity_id: str = "",
        require_all_evidence_references: bool = False,
        provenance_error: str = "",
    ) -> None:
        claim = str(text or "").strip()
        if not claim:
            return
        kind = _claim_kind(claim)
        candidate = ClaimCandidate(
            schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
            claim_id=claim_id or f"claim:{len(output) + 1}",
            source_family=family,
            text=claim,
            text_hash=_hash(claim),
            kind=kind,
            factual=(
                True
                if classification == "factual"
                else False
                if classification in {"interpretive", "recommendation"}
                else _factual(kind)
            ),
            evidence_references=_references(raw, evidence),
            affected_section=affected_section,
            entity_id=entity_id,
        )
        output.append(
            _ClaimValidationInput(
                candidate=candidate,
                text=claim,
                require_all_evidence_references=require_all_evidence_references,
                provenance_error=provenance_error,
            )
        )

    def add_soft_copy(family: str, text: object, *, affected_section: str = "") -> None:
        claim = str(text or "").strip()
        if not claim:
            return
        text_hash = _soft_copy_text_hash(claim)
        if soft_copy_provenance_error:
            add(
                family,
                claim,
                claim_id=f"soft_copy_provenance:{family}:{text_hash[:16]}",
                classification="factual",
                affected_section=affected_section or family,
                provenance_error=soft_copy_provenance_error,
            )
            return
        provenance = soft_copy_claims.get((family, text_hash))
        if provenance is None:
            add(
                family,
                claim,
                claim_id=f"soft_copy_provenance:{family}:{text_hash[:16]}",
                classification="factual",
                affected_section=affected_section or family,
                provenance_error="soft_copy_provenance_sentence_missing",
            )
            return
        add(
            family,
            claim,
            {
                "evidence_ids": list(provenance.evidence_ids),
                "evidence_spans": list(provenance.source_spans),
            },
            classification=provenance.classification,
            claim_id=provenance.claim_id,
            affected_section=affected_section or family,
            entity_id=provenance.claim_id,
            require_all_evidence_references=provenance.classification == "factual",
        )

    summary = artifacts.get("summary")
    if isinstance(summary, dict):
        for index, raw in enumerate(summary.get("claim_evidence_map") or [], start=1):
            if isinstance(raw, dict):
                claim_identity = str(
                    raw.get("id") or raw.get("claim_id") or index
                ).strip()
                add(
                    "summary",
                    raw.get("claim"),
                    raw,
                    claim_id=f"summary_claim:{claim_identity}",
                    affected_section=f"summary.claim_evidence_map:{claim_identity}.claim",
                    entity_id=f"summary_claim:{claim_identity}",
                )
        for key in ("tldr", "card_tldr_compact", "executive_summary"):
            for sentence in soft_copy_material_sentences(summary.get(key)):
                add_soft_copy("summary", sentence, affected_section=f"summary.{key}")
    for family, item_key, text_key in (
        ("insights_final", "insights_final", "text"),
        ("quotes_final", "quotes_final", "text"),
    ):
        for raw in artifacts.get(item_key) or []:
            if isinstance(raw, dict):
                stable_id = str(
                    raw.get("id")
                    or raw.get("insight_id")
                    or raw.get("evidence_id")
                    or ""
                ).strip()
                if family == "insights_final":
                    claim_id = f"insight:{stable_id}:text" if stable_id else ""
                    affected = (
                        f"insights:{stable_id}.text" if stable_id else "insights_final"
                    )
                    entity = f"insight:{stable_id}:text" if stable_id else ""
                else:
                    claim_id = f"quote:{stable_id}:text" if stable_id else ""
                    affected = (
                        f"quotes:{stable_id}.text" if stable_id else "quotes_final"
                    )
                    entity = f"quote:{stable_id}:text" if stable_id else ""
                add(
                    family,
                    raw.get(text_key),
                    raw,
                    claim_id=claim_id,
                    affected_section=affected,
                    entity_id=entity,
                )
                if family == "insights_final" and isinstance(raw.get("metric"), dict):
                    metric_text = _metric_claim_text(raw["metric"])
                    if metric_text:
                        add(
                            family,
                            metric_text,
                            raw,
                            claim_id=f"insight:{stable_id}:metric" if stable_id else "",
                            affected_section=(
                                f"insights:{stable_id}.metric"
                                if stable_id
                                else "insights_final"
                            ),
                            entity_id=f"insight:{stable_id}:metric"
                            if stable_id
                            else "",
                        )
    for index, raw in enumerate(artifacts.get("key_figures") or [], start=1):
        if not isinstance(raw, dict):
            continue
        stable_id = str(raw.get("id") or raw.get("key_figure_id") or index).strip()
        figure_text = _metric_claim_text(raw)
        if figure_text:
            add(
                "key_figures",
                figure_text,
                raw,
                claim_id=f"key_figure:{stable_id}:figure",
                affected_section=f"key_figures:{stable_id}.figure",
                entity_id=f"key_figure:{stable_id}:figure",
            )
    for family in ("expert_comment", "linkedin_post"):
        value = artifacts.get(family)
        if isinstance(value, str):
            for sentence in soft_copy_material_sentences(value):
                add_soft_copy(family, sentence, affected_section=family)
    for family in ("executive_summary", "executive_takeaways"):
        value = artifacts.get(family)
        if isinstance(value, str):
            for sentence in soft_copy_material_sentences(value):
                add(family, sentence)
    return output


def _metric_claim_text(metric: dict) -> str:
    """Create a stable factual display from retained metric fields."""

    values = [
        str(metric.get(key) or "").strip()
        for key in (
            "label",
            "subject",
            "value",
            "unit",
            "geography",
            "segment",
            "cohort",
            "denominator",
            "timeframe",
            "observation_status",
        )
    ]
    return " ".join(value for value in values if value)


def _soft_copy_claims_by_hash(
    artifacts: dict,
) -> tuple[dict[tuple[str, str], SoftCopyClaimProvenance], str]:
    """Read exact soft-copy provenance as a mandatory validation boundary."""

    if "soft_copy_claim_provenance" not in artifacts:
        return {}, "soft_copy_provenance_missing"
    payload = artifacts.get("soft_copy_claim_provenance")
    if not isinstance(payload, dict) or payload.get("schema_version") != "1.0":
        return {}, "soft_copy_provenance_invalid"

    try:
        claims = soft_copy_claim_provenance_from_payload(payload)
    except (AppError, TypeError, ValueError):
        return {}, "soft_copy_provenance_invalid"
    indexed: dict[tuple[str, str], SoftCopyClaimProvenance] = {}
    for claim in claims:
        key = (claim.artifact_family, claim.text_hash)
        if key in indexed:
            return {}, "soft_copy_provenance_ambiguous"
        indexed[key] = claim
    return indexed, ""


def _soft_copy_text_hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def _checks(
    candidate: ClaimCandidate,
    text: str,
    source_evidence: dict[str, tuple[str, str, int | None]],
    *,
    require_all_evidence_references: bool = False,
) -> tuple[list[ClaimValidationCheck], ProtectedFactComparison | None]:
    refs = candidate.evidence_references
    known = [
        reference for reference in refs if reference.evidence_id in source_evidence
    ]
    all_references_known = bool(refs) and len(known) == len(refs)
    evidence_check = (
        ClaimValidationCheck(
            schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
            name="evidence_reference_completeness",
            status="passed" if all_references_known else "failed",
            reason="evidence_references_resolved"
            if all_references_known
            else "missing_evidence_reference"
            if not refs
            else "unknown_evidence_reference",
        )
        if require_all_evidence_references
        else ClaimValidationCheck(
            schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
            name="evidence_reference_completeness",
            status="passed" if known else "failed",
            reason="evidence_reference_present"
            if known
            else "missing_or_unknown_evidence_reference",
        )
    )
    checks = [evidence_check]
    cited = [source_evidence[reference.evidence_id][1] for reference in known]
    protected_facts = None
    if cited:
        protected_facts = compare_protected_fact_texts(text, "\n".join(cited))
        checks.extend(
            ClaimValidationCheck(
                schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
                name=f"protected_fact_{dimension}_consistency",
                status="failed",
                reason=f"protected_fact_{dimension}_incompatible",
            )
            for dimension in protected_facts.incompatible_dimensions
        )
    if candidate.kind == "numeric":
        quantities = extract_quantities(text)
        cited_quantities = [
            value for source in cited for value in extract_quantities(source)
        ]
        checks.append(
            ClaimValidationCheck(
                schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
                name="number_value_unit_match",
                status="passed"
                if quantities
                and all(
                    any(
                        _quantity_entailed_by_evidence(candidate, evidence)
                        for evidence in cited_quantities
                    )
                    for candidate in quantities
                )
                else "failed",
                reason="quantities_matched"
                if quantities
                and all(
                    any(
                        _quantity_entailed_by_evidence(candidate, evidence)
                        for evidence in cited_quantities
                    )
                    for candidate in quantities
                )
                else "quantity_not_entailed",
            )
        )
    elif candidate.kind == "quotation":
        normalized = normalize_for_lookup(text).replace('"', "")
        checks.append(
            ClaimValidationCheck(
                schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
                name="quote_match",
                status="passed"
                if any(normalized in normalize_for_lookup(source) for source in cited)
                else "failed",
                reason="quote_matched"
                if any(normalized in normalize_for_lookup(source) for source in cited)
                else "quote_not_matched",
            )
        )
    else:
        checks.append(
            ClaimValidationCheck(
                schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
                name="entity_geography_period_consistency",
                status="not_applicable",
                reason="requires_semantic_or_editorial_assessment",
            )
        )
    return checks, protected_facts


def _validate_claims_against_sources(
    candidates: list[_ClaimValidationInput],
    source_evidence: dict[str, tuple[str, str, int | None]],
    *,
    artifact: object,
    semantic_validator: SemanticValidator | None = None,
    semantic_batch_validator: SemanticBatchValidator | None = None,
    semantic_results: list[ClaimSemanticGroundingResult] | None = None,
    source_identity: str = "",
) -> ClaimValidationPackage:
    """Validate claims against authoritative retained source text.

    Candidate extraction remains owned by the artifact or evidence-pack boundary.
    Deterministic checks always run first. Retained-claim semantic fallback is
    collected into one batch and consumes only identity-matched tri-state results.
    """

    results: list[ClaimValidationResult] = []
    semantic_ids: list[str] = []
    for candidate_input in candidates:
        candidate = candidate_input.candidate
        text = candidate_input.text
        if candidate_input.provenance_error:
            checks = [
                ClaimValidationCheck(
                    schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
                    name="soft_copy_provenance_integrity",
                    status="failed",
                    reason=candidate_input.provenance_error,
                )
            ]
            protected_facts = None
        else:
            checks, protected_facts = _checks(
                candidate,
                text,
                source_evidence,
                require_all_evidence_references=(
                    candidate_input.require_all_evidence_references
                ),
            )
        failed = [check.reason for check in checks if check.status == "failed"]
        deterministic_entailment = any(
            check.name in {"number_value_unit_match", "quote_match"}
            and check.status == "passed"
            for check in checks
        )
        status = (
            "supported"
            if deterministic_entailment and not failed
            else "unsupported"
            if failed
            else "unresolved"
        )
        deterministic_status = status
        semantic_used = False
        execution_identity = ""
        semantic_outcome = None
        semantic_reason = ""
        if status == "unresolved" and semantic_validator is not None:
            sources = [
                source_evidence[ref.evidence_id][1]
                for ref in candidate.evidence_references
                if ref.evidence_id in source_evidence
            ]
            supported, reason, execution_identity = semantic_validator(
                candidate, sources
            )
            semantic_used = True
            status = "supported" if supported else "unsupported"
            failed = [reason]
            semantic_outcome = "entailed" if supported else None
            semantic_reason = reason
            if execution_identity:
                semantic_ids.append(execution_identity)
        results.append(
            ClaimValidationResult(
                schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
                candidate=candidate,
                checks=checks,
                status=status,  # type: ignore[arg-type]
                deterministic_status=deterministic_status,  # type: ignore[arg-type]
                reasons=failed,
                protected_facts=protected_facts,
                semantic_outcome=semantic_outcome,
                semantic_reason=semantic_reason,
                semantic_validator_used=semantic_used,
                semantic_execution_identity=execution_identity,
            )
        )

    if semantic_batch_validator is not None and semantic_results is not None:
        raise ValueError("Provide a semantic batch validator or results, not both")
    semantic_inputs = _semantic_inputs(results, source_evidence, source_identity)
    semantic_results_provided = semantic_results is not None
    if semantic_batch_validator is not None and semantic_inputs:
        # One report-level operation receives every eligible unresolved claim.
        semantic_results = semantic_batch_validator(semantic_inputs)
        semantic_results_provided = True
    if semantic_results_provided:
        results = _apply_semantic_results(
            results,
            semantic_inputs,
            semantic_results or [],
        )

    return _claim_validation_package(artifact=artifact, results=results)


def _semantic_inputs(
    results: list[ClaimValidationResult],
    source_evidence: dict[str, tuple[str, str, int | None]],
    source_identity: str,
) -> list[ClaimSemanticInput]:
    inputs: list[ClaimSemanticInput] = []
    for result in results:
        candidate = result.candidate
        if (
            not candidate.factual
            or result.deterministic_status != "unresolved"
            or any(check.status == "failed" for check in result.checks)
        ):
            continue
        refs = candidate.evidence_references
        if not refs or any(ref.evidence_id not in source_evidence for ref in refs):
            continue
        evidence_ids_and_hashes = [
            {
                "evidence_id": ref.evidence_id,
                "source_pack": ref.source_pack,
                "page": ref.page,
                "text_hash": ref.text_hash,
            }
            for ref in refs
        ]
        inputs.append(
            ClaimSemanticInput(
                schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
                candidate=candidate,
                evidence_texts=[source_evidence[ref.evidence_id][1] for ref in refs],
                evidence_hash=_hash(evidence_ids_and_hashes),
                source_identity=source_identity,
            )
        )
    return inputs


def _apply_semantic_results(
    results: list[ClaimValidationResult],
    semantic_inputs: list[ClaimSemanticInput],
    semantic_results: list[ClaimSemanticGroundingResult],
) -> list[ClaimValidationResult]:
    inputs_by_id: dict[str, list[ClaimSemanticInput]] = {}
    results_by_id: dict[str, list[ClaimSemanticGroundingResult]] = {}
    for semantic_input in semantic_inputs:
        inputs_by_id.setdefault(semantic_input.candidate.claim_id, []).append(
            semantic_input
        )
    for semantic_result in semantic_results:
        results_by_id.setdefault(semantic_result.identity.claim_id, []).append(
            semantic_result
        )

    updated: list[ClaimValidationResult] = []
    for result in results:
        if result.deterministic_status != "unresolved":
            updated.append(result)
            continue
        candidate = result.candidate
        matching_inputs = inputs_by_id.get(candidate.claim_id, [])
        matching_results = results_by_id.get(candidate.claim_id, [])
        if not matching_inputs:
            updated.append(result)
            continue
        if len(matching_inputs) > 1:
            updated.append(
                replace(
                    result,
                    semantic_disagreement="ambiguous_semantic_input_identity",
                )
            )
            continue
        if len(matching_results) > 1:
            updated.append(
                replace(
                    result,
                    semantic_disagreement="ambiguous_semantic_result_identity",
                )
            )
            continue
        if not matching_results:
            expected_evidence_ids = [
                reference.evidence_id for reference in candidate.evidence_references
            ]
            mismatched_claim_ids = [
                semantic_result
                for semantic_result in semantic_results
                if semantic_result.identity.claim_text_hash == candidate.text_hash
                and semantic_result.identity.evidence_ids == expected_evidence_ids
                and semantic_result.identity.evidence_hash
                == matching_inputs[0].evidence_hash
            ]
            updated.append(result)
            if len(mismatched_claim_ids) == 1:
                updated[-1] = replace(
                    result,
                    semantic_disagreement="semantic_result_claim_id_mismatch",
                )
            else:
                updated[-1] = replace(
                    result,
                    semantic_disagreement="semantic_result_missing",
                )
            continue
        semantic_input = matching_inputs[0]
        semantic = matching_results[0]
        identity = semantic.identity
        expected_evidence_ids = [
            reference.evidence_id for reference in candidate.evidence_references
        ]
        identity_matches = (
            identity.schema_version == "1.0"
            and identity.claim_text_hash == candidate.text_hash
            and identity.evidence_ids == expected_evidence_ids
            and identity.evidence_hash == semantic_input.evidence_hash
            and identity.source_identity == semantic_input.source_identity
            and bool(identity.prompt_family)
            and bool(identity.prompt_content_hash)
            and bool(identity.execution_identity)
            and bool(identity.validator_version)
            and bool(identity.model_provider)
            and bool(identity.model_name)
            and bool(identity.configuration_policy_identity)
            and bool(identity.relevant_input_hash)
        )
        if not identity_matches:
            updated.append(
                replace(
                    result,
                    semantic_disagreement="semantic_result_identity_mismatch",
                )
            )
            continue

        disagreement = semantic.disagreement
        outcome = semantic.outcome
        incompatible_dimensions = (
            semantic.protected_facts.incompatible_dimensions
            if semantic.protected_facts is not None
            else []
        )
        incompatible_proposition = bool(
            semantic.protected_facts is not None
            and semantic.protected_facts.proposition_status == "incompatible"
        )
        if outcome == "entailed" and (
            incompatible_dimensions or incompatible_proposition
        ):
            disagreement = disagreement or (
                "entailed_with_incompatible_protected_dimensions"
                if incompatible_dimensions
                else "entailed_with_incompatible_proposition"
            )
            outcome = "contradicted"
        status = {
            "entailed": "supported",
            "contradicted": "unsupported",
            "not_established": "unresolved",
        }[outcome]
        reasons = [semantic.reason] if semantic.reason and status != "supported" else []
        updated.append(
            replace(
                result,
                status=status,  # type: ignore[arg-type]
                reasons=reasons,
                semantic_outcome=outcome,
                semantic_reason=semantic.reason,
                semantic_protected_facts=semantic.protected_facts,
                semantic_identity=identity,
                semantic_disagreement=disagreement,
                semantic_validator_used=True,
                semantic_execution_identity=identity.execution_identity,
            )
        )
    return updated


def _claim_validation_package(
    *, artifact: object, results: list[ClaimValidationResult]
) -> ClaimValidationPackage:
    return _claim_validation_package_for_hash(
        artifact_hash=_hash(artifact), results=results
    )


def _claim_validation_package_for_hash(
    *, artifact_hash: str, results: list[ClaimValidationResult]
) -> ClaimValidationPackage:
    unsupported = sum(
        1 for item in results if item.candidate.factual and item.status == "unsupported"
    )
    unresolved = sum(
        1 for item in results if item.candidate.factual and item.status == "unresolved"
    )
    deterministic_passes = sum(
        1
        for item in results
        if item.status == "supported" and not item.semantic_validator_used
    )
    semantic_execution_identities = sorted(
        {
            item.semantic_execution_identity
            for item in results
            if item.semantic_execution_identity
        }
    )
    package_hash = _hash(
        {
            "artifact_hash": artifact_hash,
            "results": [asdict(item) for item in results],
            "semantic_execution_identities": semantic_execution_identities,
        }
    )
    return ClaimValidationPackage(
        schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
        artifact_hash=artifact_hash,
        package_hash=package_hash,
        results=results,
        readiness_status="awaiting_review"
        if not unsupported and not unresolved
        else "not_publishable",
        unsupported_factual_count=unsupported,
        unresolved_factual_count=unresolved,
        deterministic_pass_count=deterministic_passes,
        semantic_validation_count=sum(item.semantic_validator_used for item in results),
        semantic_execution_identities=semantic_execution_identities,
    )


def retained_claim_semantic_inputs(
    package: ClaimValidationPackage,
    evidence_packs: dict,
    *,
    source_identity: str = "",
) -> list[ClaimSemanticInput]:
    """Return only unresolved factual claims with all exact linked source text."""

    return _semantic_inputs(
        package.results,
        _evidence_index(evidence_packs),
        source_identity,
    )


def apply_retained_claim_semantic_results(
    package: ClaimValidationPackage,
    semantic_inputs: list[ClaimSemanticInput],
    semantic_results: list[ClaimSemanticGroundingResult],
) -> ClaimValidationPackage:
    """Attach identity-matched report-level results to deterministic dispositions."""

    results = _apply_semantic_results(
        package.results,
        semantic_inputs,
        semantic_results,
    )
    return _claim_validation_package_for_hash(
        artifact_hash=package.artifact_hash,
        results=results,
    )


def _source_index(
    source_spans: list[dict[str, object]],
) -> dict[str, tuple[str, str, int | None]]:
    indexed: dict[str, tuple[str, str, int | None]] = {}
    for index, raw in enumerate(source_spans, start=1):
        span_id = str(raw.get("id") or f"source:{index}").strip()
        text = str(raw.get("text") or "").strip()
        page = raw.get("page")
        if span_id and text:
            indexed[span_id] = (
                "source_pdf",
                text,
                page if isinstance(page, int) and not isinstance(page, bool) else None,
            )
    return indexed


def _source_references(
    raw: dict,
    source_evidence: dict[str, tuple[str, str, int | None]],
) -> list[ClaimEvidenceReference]:
    pages_raw = raw.get("pages", raw.get("page"))
    pages = pages_raw if isinstance(pages_raw, list) else [pages_raw]
    page_values = [
        value
        for value in pages
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
    ]
    has_page_provenance = any(
        source_page is not None
        for _source_id, (_pack, _text, source_page) in source_evidence.items()
    )
    if has_page_provenance and not page_values:
        source_text = _item_source_text(raw)
        page_values = _matched_source_pages(source_text, source_evidence)
        if not page_values:
            return []
    matching = [
        source_id
        for source_id, (_, _, source_page) in source_evidence.items()
        if not page_values or source_page in page_values
    ]
    return [
        ClaimEvidenceReference(
            schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
            evidence_id=source_id,
            source_pack=source_evidence[source_id][0],
            page=source_evidence[source_id][2],
            text_hash=_hash(source_evidence[source_id][1]),
        )
        for source_id in sorted(matching)
    ]


def _matched_source_pages(
    evidence_text: str,
    source_evidence: dict[str, tuple[str, str, int | None]],
) -> list[int]:
    """Recover one page only when its text is the best deterministic match.

    Generated page labels are useful metadata, not an authoritative boundary.  If
    they are absent, recovering every page that shares a common year or percentage
    would manufacture a misleading lineage.  A recovered reference is therefore
    limited to the single best page, using both meaningful-text overlap and
    non-calendar metric values; otherwise the evidence remains untrusted.
    """

    normalized = normalize_for_lookup(evidence_text)
    if not normalized:
        return []
    exact = sorted(
        {
            page
            for _source_id, (_pack, source_text, page) in source_evidence.items()
            if page is not None and normalized in normalize_for_lookup(source_text)
        }
    )
    if exact:
        return exact[:1]

    evidence_tokens = _recovery_tokens(evidence_text)
    evidence_quantities = _recovery_quantity_values(evidence_text)
    candidates: list[tuple[int, int, int]] = []
    for _source_id, (_pack, source_text, page) in source_evidence.items():
        if page is None:
            continue
        token_overlap = len(evidence_tokens & _recovery_tokens(source_text))
        quantity_overlap = len(
            evidence_quantities & _recovery_quantity_values(source_text)
        )
        if token_overlap >= 5 or quantity_overlap >= 2:
            candidates.append((quantity_overlap, token_overlap, page))
    if not candidates:
        return []
    best_quantities, best_tokens, best_page = max(candidates)
    if best_quantities == 0 and best_tokens < 5:
        return []
    return [best_page]


def _recovery_tokens(value: str) -> set[str]:
    return {
        token
        for token in _RECOVERY_TOKEN_RE.findall(normalize_for_lookup(value))
        if token not in _RECOVERY_STOP_WORDS
    }


def _item_source_text(raw: dict) -> str:
    """Join distinct generated evidence fields without duplicating an assertion."""

    values = [
        str(raw.get(key) or "").strip()
        for key in ("evidence", "quote", "text", "description")
        if str(raw.get(key) or "").strip()
    ]
    return " ".join(dict.fromkeys(values))


def _item_claim_text(raw: dict) -> str:
    """Return the generated assertion, excluding its non-authoritative rationale."""

    for key in ("text", "quote", "description", "evidence"):
        value = str(raw.get(key) or "").strip()
        if value:
            return value
    return ""


def _recovery_quantity_values(value: str) -> set[float]:
    """Return non-calendar values for deterministic source-page retrieval."""

    return {
        float(quantity.value)
        for quantity in extract_quantities(value)
        if quantity.unit_family != "time"
        and not (quantity.value.is_integer() and 1900 <= int(quantity.value) <= 2100)
    }


def _quantity_entailed_by_evidence(candidate: object, evidence: object) -> bool:
    """Reject an exact assertion when the source provides only a bound.

    ``quantities_match`` is deliberately symmetric enough for similarity and
    retrieval use cases.  Evidence fidelity is directional: "more than 20%"
    can support an assertion such as "more than 20%", but cannot support the
    exact assertion "52%" merely because 52 is above the lower bound.
    """

    candidate_comparator = str(getattr(candidate, "comparator", ""))
    evidence_comparator = str(getattr(evidence, "comparator", ""))
    if candidate_comparator in {"eq", "approx"} and evidence_comparator in {
        "gt",
        "gte",
        "lt",
        "lte",
    }:
        return False
    return quantities_match(candidate, evidence)  # type: ignore[arg-type]


def _evidence_fidelity_candidates(
    evidence_packs: dict,
    source_evidence: dict[str, tuple[str, str, int | None]],
) -> list[_ClaimValidationInput]:
    candidates: list[_ClaimValidationInput] = []
    for pack_name, root_key in (
        ("findings", "findings"),
        ("quote_candidates", "quote_candidates"),
    ):
        pack = evidence_packs.get(pack_name)
        if not isinstance(pack, dict):
            continue
        items = pack.get(root_key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            evidence_id = str(item.get("id") or item.get("evidence_id") or "").strip()
            text = _item_claim_text(item)
            if not evidence_id or not text:
                continue
            kind = _claim_kind(text)
            candidates.append(
                _ClaimValidationInput(
                    candidate=ClaimCandidate(
                        schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
                        claim_id=f"evidence:{pack_name}:{evidence_id}",
                        source_family=f"evidence_pack:{pack_name}",
                        text=text,
                        text_hash=_hash(text),
                        kind=kind,
                        factual=_factual(kind),
                        evidence_references=_source_references(item, source_evidence),
                    ),
                    text=text,
                )
            )
    return candidates


def validate_evidence_fidelity(
    evidence_packs: dict,
    *,
    source_spans: list[dict[str, object]],
    semantic_validator: SemanticValidator | None = None,
) -> ClaimValidationPackage:
    """Validate generated, editorially usable evidence against PDF-derived spans."""

    source_evidence = _source_index(source_spans)
    return _validate_claims_against_sources(
        _evidence_fidelity_candidates(evidence_packs, source_evidence),
        source_evidence,
        artifact=evidence_packs,
        semantic_validator=semantic_validator,
    )


def exclude_untrusted_evidence(
    evidence_packs: dict, package: ClaimValidationPackage
) -> dict:
    """Return evidence packs with unsupported material findings and quotes removed."""

    trusted = deepcopy(evidence_packs)
    blocked = {
        result.candidate.claim_id.removeprefix(f"evidence:{pack_name}:")
        for result in package.results
        if result.status != "supported"
        for pack_name in ("findings", "quote_candidates")
        if result.candidate.claim_id.startswith(f"evidence:{pack_name}:")
    }
    for pack_name, root_key in (
        ("findings", "findings"),
        ("quote_candidates", "quote_candidates"),
    ):
        pack = trusted.get(pack_name)
        if not isinstance(pack, dict) or not isinstance(pack.get(root_key), list):
            continue
        pack[root_key] = [
            item
            for item in pack[root_key]
            if not isinstance(item, dict)
            or str(item.get("id") or item.get("evidence_id") or "").strip()
            not in blocked
        ]
    return trusted


def validate_retained_claims(
    artifacts: dict,
    evidence_packs: dict,
    *,
    semantic_batch_validator: SemanticBatchValidator | None = None,
    semantic_results: list[ClaimSemanticGroundingResult] | None = None,
    source_identity: str = "",
) -> ClaimValidationPackage:
    """Validate retained claims, batching semantic fallback for undecidable facts."""

    evidence = _evidence_index(evidence_packs)
    return _validate_claims_against_sources(
        _candidates(artifacts, evidence),
        evidence,
        artifact=artifacts,
        semantic_batch_validator=semantic_batch_validator,
        semantic_results=semantic_results,
        source_identity=source_identity,
    )
