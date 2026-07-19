"""Deterministic retained-artifact claim validation before publish readiness."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from typing import Callable

from src.contracts.claim_validation import (
    CLAIM_VALIDATION_SCHEMA_VERSION,
    ClaimCandidate,
    ClaimEvidenceReference,
    ClaimKind,
    ClaimValidationCheck,
    ClaimValidationPackage,
    ClaimValidationResult,
)
from src.utils.quantity import extract_quantities
from src.utils.text_normalization import normalize_for_lookup

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_CAUSAL_RE = re.compile(
    r"\b(cause[sd]?|driv(?:e|es|en)|lead(?:s|ing)? to|result(?:s|ed)? in)\b", re.I
)
_INTERPRETIVE_RE = re.compile(
    r"\b(recommend|suggest|should|could|may|likely|interpret)\b", re.I
)
_QUOTED_RE = re.compile(r'(["“”]).+?\1')

SemanticValidator = Callable[[ClaimCandidate, list[str]], tuple[bool, str, str]]


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
                    for key in ("text", "evidence", "quote", "description", "summary")
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
) -> list[tuple[ClaimCandidate, str]]:
    output: list[tuple[ClaimCandidate, str]] = []

    def add(family: str, text: object, raw: object = None) -> None:
        claim = str(text or "").strip()
        if not claim:
            return
        kind = _claim_kind(claim)
        candidate = ClaimCandidate(
            schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
            claim_id=f"claim:{len(output) + 1}",
            source_family=family,
            text_hash=_hash(claim),
            kind=kind,
            factual=_factual(kind),
            evidence_references=_references(raw, evidence),
        )
        output.append((candidate, claim))

    summary = artifacts.get("summary")
    if isinstance(summary, dict):
        for raw in summary.get("claim_evidence_map") or []:
            if isinstance(raw, dict):
                add("summary", raw.get("claim"), raw)
        for key in ("tldr", "card_tldr_compact", "executive_summary"):
            for sentence in _SENTENCE_RE.split(str(summary.get(key) or "")):
                add("summary", sentence)
    for family, item_key, text_key in (
        ("insights_final", "insights_final", "text"),
        ("quotes_final", "quotes_final", "text"),
    ):
        for raw in artifacts.get(item_key) or []:
            if isinstance(raw, dict):
                add(family, raw.get(text_key), raw)
    for family in (
        "expert_comment",
        "linkedin_post",
        "executive_summary",
        "executive_takeaways",
    ):
        value = artifacts.get(family)
        if isinstance(value, str):
            for sentence in _SENTENCE_RE.split(value):
                add(family, sentence)
    return output


def _checks(
    candidate: ClaimCandidate,
    text: str,
    evidence: dict[str, tuple[str, str, int | None]],
) -> list[ClaimValidationCheck]:
    refs = candidate.evidence_references
    known = [reference for reference in refs if reference.evidence_id in evidence]
    checks = [
        ClaimValidationCheck(
            schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
            name="evidence_reference_completeness",
            status="passed" if known else "failed",
            reason="evidence_reference_present"
            if known
            else "missing_or_unknown_evidence_reference",
        )
    ]
    cited = [evidence[reference.evidence_id][1] for reference in known]
    if candidate.kind == "numeric":
        quantities = {
            (float(value.value), str(value.unit_family))
            for value in extract_quantities(text)
        }
        cited_quantities = {
            (float(value.value), str(value.unit_family))
            for source in cited
            for value in extract_quantities(source)
        }
        checks.append(
            ClaimValidationCheck(
                schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
                name="number_value_unit_match",
                status="passed"
                if quantities and quantities <= cited_quantities
                else "failed",
                reason="quantities_matched"
                if quantities and quantities <= cited_quantities
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
    return checks


def validate_retained_claims(
    artifacts: dict,
    evidence_packs: dict,
    *,
    semantic_validator: SemanticValidator | None = None,
) -> ClaimValidationPackage:
    """Validate retained claims; invoke semantic validation only when unresolved."""

    evidence = _evidence_index(evidence_packs)
    results: list[ClaimValidationResult] = []
    semantic_ids: list[str] = []
    for candidate, text in _candidates(artifacts, evidence):
        checks = _checks(candidate, text, evidence)
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
        semantic_used = False
        execution_identity = ""
        if status == "unresolved" and semantic_validator is not None:
            sources = [
                evidence[ref.evidence_id][1]
                for ref in candidate.evidence_references
                if ref.evidence_id in evidence
            ]
            supported, reason, execution_identity = semantic_validator(
                candidate, sources
            )
            semantic_used = True
            status = "supported" if supported else "unsupported"
            failed = [reason]
            if execution_identity:
                semantic_ids.append(execution_identity)
        results.append(
            ClaimValidationResult(
                schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
                candidate=candidate,
                checks=checks,
                status=status,  # type: ignore[arg-type]
                reasons=failed,
                semantic_validator_used=semantic_used,
                semantic_execution_identity=execution_identity,
            )
        )
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
    payload = {
        "artifact_hash": _hash(artifacts),
        "results": [asdict(item) for item in results],
        "semantic_execution_identities": sorted(set(semantic_ids)),
    }
    return ClaimValidationPackage(
        schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
        artifact_hash=payload["artifact_hash"],
        package_hash=_hash(payload),
        results=results,
        readiness_status="awaiting_review"
        if not unsupported and not unresolved
        else "not_publishable",
        unsupported_factual_count=unsupported,
        unresolved_factual_count=unresolved,
        deterministic_pass_count=deterministic_passes,
        semantic_validation_count=sum(item.semantic_validator_used for item in results),
        semantic_execution_identities=payload["semantic_execution_identities"],
    )
