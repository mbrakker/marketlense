"""Deterministic retained-artifact claim validation before publish readiness."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from typing import Callable, Literal, Mapping, Sequence

from src.contracts.claim_validation import (
    CLAIM_GROUNDING_VALIDATOR_VERSION,
    CLAIM_VALIDATION_SCHEMA_VERSION,
    CLAIM_VALIDATION_VALIDATOR_VERSION,
    ClaimCandidate,
    ClaimEvidenceReference,
    ClaimKind,
    ClaimSemanticGroundingResult,
    ClaimSemanticInput,
    ClaimSemanticOutcome,
    ClaimSemanticValidationIdentity,
    ClaimValidationCheck,
    ClaimValidationExecutionIdentity,
    ClaimValidationLineage,
    ClaimValidationPackage,
    ClaimValidationResult,
)
from src.contracts.pdf_text import PdfTextPage
from src.contracts.protected_facts import (
    ProtectedFactComparison,
    compare_protected_fact_texts,
)
from src.contracts.soft_copy_claim_provenance import (
    SoftCopyClaimProvenance,
    soft_copy_claim_provenance_from_payload,
    soft_copy_material_sentences,
    soft_copy_public_text,
)
from src.generators.artifact_normalization import canonical_artifact_quote_id
from src.utils.errors import AppError
from src.utils.pdf_text_layout import (
    has_two_panel_percent_chart_candidate,
    two_panel_chart_platform_names,
)
from src.utils.publication_projection import publication_projection_hash
from src.utils.quantity import Quantity, extract_quantities, quantities_match
from src.utils.text_normalization import normalize_for_lookup

_CAUSAL_RE = re.compile(
    r"\b(cause[sd]?|driv(?:e|es|en)|lead(?:s|ing)? to|result(?:s|ed)? in|"
    r"because|since|due to|given that)\b",
    re.I,
)
_INTERPRETIVE_RE = re.compile(
    r"\b(recommend|suggest|should|could|may|likely|interpret)\b", re.I
)
_COMPARATIVE_RE = re.compile(
    r"\b(?:compared\s+(?:with|to)|versus|vs\.?|outperform(?:ed|s)?|"
    r"underperform(?:ed|s)?|higher|lower|more|less)\b",
    re.I,
)
_QUOTED_RE = re.compile(
    r"""(?:"[^"]+"|“[^”]+”"""
    r"|(?<!\w)‘(?:[^’\r\n]|(?<=\w)’(?=\w|\s+\w))+’(?!\w)"
    r"|(?<!\w)'(?:[^'\r\n]|(?<=\w)'(?=\w|\s+\w))+'(?!\w))"
)
_MINIMAL_QUOTED_RE = re.compile(
    r"""(?:"[^"]+"|“[^”]+”"""
    r"|(?<!\w)‘(?:[^’\r\n]|(?<=\w)’(?=\w|\s+\w))+?’(?!\w)"
    r"|(?<!\w)'(?:[^'\r\n]|(?<=\w)'(?=\w|\s+\w))+?'(?!\w))"
)
_LAYOUT_CHART_ROW_RE = re.compile(
    r"^Panel\s+(?P<panel>[12]):\s+the\s+"
    r"(?P<cohort>.+?)\s+total-view\s+cohort\s+is\s+"
    r"(?P<creator_value>\d+(?:\.\d+)?)%\s+of\s+creators\s+in\s+"
    r"the\s+stated\s+over-(?P<population>\d+(?:\.\d+)?\s*[kmb])-view\s+"
    r"creator\s+population,\s+with\s+"
    r"(?P<view_value>\d+(?:\.\d+)?)%\s+of\s+views\s+in\s+"
    r"the\s+chart's\s+%\s+total\s+frame\.$",
    re.IGNORECASE,
)
_VISUAL_PANEL_LABEL_RE = re.compile(
    r"^(?P<side>left|right) panel visible label:\s*(?P<label>[^.]+)\.$",
    re.IGNORECASE,
)
_CLAIM_CHART_METRIC_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*%\s*(?:of\s+)?"
    r"(?P<metric>creators?|views?)\b",
    re.IGNORECASE,
)
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
EvidenceSemanticBatchValidator = Callable[
    [list[ClaimCandidate], list[str]], Mapping[str, tuple[bool, str, str]]
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


def claim_validation_package_hash(package: dict | ClaimValidationPackage) -> str:
    """Return the canonical package hash without its self-referential field."""
    payload = (
        asdict(package)
        if isinstance(package, ClaimValidationPackage)
        else dict(package)
    )
    payload["package_hash"] = ""
    return _hash(payload)


def claim_validation_package_hash_valid(package: object) -> bool:
    if isinstance(package, ClaimValidationPackage):
        payload = asdict(package)
    elif isinstance(package, dict):
        payload = dict(package)
    else:
        return False
    supplied = str(payload.get("package_hash") or "")
    return bool(supplied and supplied == claim_validation_package_hash(payload))


def attach_claim_validation_execution_identity(
    package: ClaimValidationPackage,
    *,
    report_id: str,
    source_id: str,
    source_md5: str,
    configuration_hash: str,
    policy_hash: str,
) -> dict:
    """Persist validation output as a candidate tied to its producing context."""
    payload = asdict(package)
    payload["validation_identity"] = asdict(
        ClaimValidationExecutionIdentity(
            schema_version="1.1",
            report_id=str(report_id or ""),
            source_id=str(source_id or ""),
            source_md5=str(source_md5 or ""),
            claim_validation_validator_version=CLAIM_VALIDATION_VALIDATOR_VERSION,
            grounding_validator_version=CLAIM_GROUNDING_VALIDATOR_VERSION,
            configuration_hash=str(configuration_hash or ""),
            policy_hash=str(policy_hash or ""),
        )
    )
    payload["package_hash"] = ""
    payload["package_hash"] = claim_validation_package_hash(payload)
    return payload


def _claim_kind(text: str) -> ClaimKind:
    # Claim kind is retained as a compatibility field, not a semantic gate.
    # Regexes cannot decide whether a sentence is factual, interpretive, or
    # normative; the existing grounding model owns that classification.
    del text
    return "descriptive"


def _factual(kind: ClaimKind) -> bool:
    return kind != "interpretive"


def _claim_requires_factual_validation(
    *,
    text: str,
    kind: ClaimKind,
    classification: str,
    evidence_bound: bool = False,
) -> bool:
    """Return the material-item readiness flag without judging its meaning.

    This helper is retained for the persisted contract and for callers that
    need to describe a candidate.  Semantic classification belongs to the
    grounding model: editorial wording, numeric overlap, and claim-kind
    regular expressions must not decide whether an item reaches that model.
    Every enumerated public item is therefore readiness-relevant.  Technical
    evidence-reference failures are handled separately by the deterministic
    checks.
    """

    del text, kind, classification, evidence_bound
    return True


def _evidence_index(evidence_packs: dict) -> dict[str, tuple[str, str, int | None]]:
    indexed: dict[str, tuple[str, str, int | None]] = {}

    def _supported_finding_statement(evidence_id: str, item: dict) -> str:
        """Return a generated finding only when its source binding is retained.

        Finding ``text`` is normally editorial copy and must not establish
        numeric support by itself.  Evidence-fidelity validation is the one
        existing contract that can promote that statement: it requires an
        exact candidate identity/text match and a concrete source-PDF page.
        Mirror that contract here so retained-claim validation sees the same
        source-backed finding statement as downstream evidence-span binding.
        """

        findings_pack = evidence_packs.get("findings")
        family_status = (
            findings_pack.get("family_status")
            if isinstance(findings_pack, dict)
            else None
        )
        if not (
            isinstance(family_status, dict)
            and family_status.get("status") == "generated"
            and family_status.get("policy_action") == "keep"
        ):
            return ""
        statement = str(item.get("text") or item.get("statement") or "").strip()
        if not statement:
            return ""

        fidelity = evidence_packs.get("evidence_fidelity")
        results = fidelity.get("results") if isinstance(fidelity, dict) else None
        matching_statement = ""
        matching_pages: set[int] = set()
        for result in results if isinstance(results, list) else []:
            if not isinstance(result, dict) or result.get("status") != "supported":
                continue
            candidate = result.get("candidate")
            if not isinstance(candidate, dict):
                continue
            if (
                str(candidate.get("claim_id") or "").strip()
                != (f"evidence:findings:{evidence_id}")
                or str(candidate.get("text") or "").strip() != statement
            ):
                continue
            references = candidate.get("evidence_references")
            pages: set[int] = set()
            if isinstance(references, list):
                for reference in references:
                    if not isinstance(reference, dict):
                        continue
                    if reference.get("source_pack") != "source_pdf":
                        continue
                    page = reference.get("page")
                    if (
                        isinstance(page, int)
                        and not isinstance(page, bool)
                        and page > 0
                    ):
                        pages.add(page)
            if not pages:
                continue
            item_pages_raw = item.get("pages", item.get("page"))
            item_page_values = (
                item_pages_raw if isinstance(item_pages_raw, list) else [item_pages_raw]
            )
            item_pages: set[int] = set()
            for page in item_page_values:
                if isinstance(page, int) and not isinstance(page, bool) and page > 0:
                    item_pages.add(page)
            if not item_pages or not item_pages.issubset(pages):
                continue
            if matching_statement and (
                matching_statement != statement or matching_pages != pages
            ):
                return ""
            matching_statement = statement
            matching_pages = pages
        return matching_statement

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
                if pack_name in {"findings", "quote_candidates"}:
                    # A finding's ``text`` is generated copy, not additional
                    # source evidence. A quote candidate is different: its
                    # contract defines ``text`` as the source quotation.
                    text = _item_direct_evidence_text(
                        item, include_text=pack_name == "quote_candidates"
                    )
                    if pack_name == "findings":
                        statement = _supported_finding_statement(evidence_id, item)
                        if statement and statement not in text:
                            text = " ".join(
                                value for value in (text, statement) if value
                            )
                else:
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


_CLAIM_PROVENANCE_KEYS = frozenset(
    {
        "evidence",
        "evidence_id",
        "evidence_ids",
        "evidence_spans",
        "source_id",
        "source_identity",
        "source_page",
        "source_pages",
        "source_span",
        "source_spans",
        "source_text",
        "source_quote",
        "provenance",
        "provenance_id",
        "page",
        "pages",
        "page_number",
        "start_offset",
        "end_offset",
        "span_start",
        "span_end",
    }
)


def _claim_provenance_hash(raw: object) -> str:
    if not isinstance(raw, dict):
        return ""
    provenance = {
        key: value
        for key, value in raw.items()
        if key in _CLAIM_PROVENANCE_KEYS or "provenance" in key.casefold()
    }
    return _hash(provenance) if provenance else ""


def _candidates(
    artifacts: dict,
    evidence: dict[str, tuple[str, str, int | None]],
    *,
    verified_facts_only: bool = False,
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
            factual=_claim_requires_factual_validation(
                text=claim,
                kind=kind,
                classification=classification,
                evidence_bound=bool(_references(raw, evidence)),
            ),
            evidence_references=_references(raw, evidence),
            affected_section=affected_section,
            entity_id=entity_id,
            provenance_hash=_claim_provenance_hash(raw),
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
            require_all_evidence_references=_claim_requires_factual_validation(
                text=claim,
                kind=_claim_kind(claim),
                classification=provenance.classification,
                evidence_bound=bool(provenance.evidence_ids),
            ),
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
        summary_fields = ("tldr", "card_tldr_compact", "executive_summary")
        field_sentences: dict[str, set[str]] = {}
        for key in summary_fields:
            for sentence in soft_copy_material_sentences(summary.get(key)):
                field_sentences.setdefault(sentence, set()).add(key)
        for sentence in soft_copy_material_sentences(
            soft_copy_public_text("summary", summary)
        ):
            owners = field_sentences.get(sentence, set())
            section = f"summary.{next(iter(owners))}" if len(owners) == 1 else "summary"
            add_soft_copy("summary", sentence, affected_section=section)
    for family, item_key, text_key in (
        ("insights_final", "insights_final", "text"),
        ("quotes_final", "quotes_final", "text"),
    ):
        quote_occurrences: dict[tuple[str, int], int] = {}
        for raw in artifacts.get(item_key) or []:
            if isinstance(raw, dict):
                if family == "quotes_final":
                    evidence_id = str(raw.get("evidence_id") or "").strip()
                    page_value = raw.get("page")
                    page = page_value if isinstance(page_value, int) else 0
                    occurrence_key = (evidence_id, page)
                    occurrence_index = quote_occurrences.get(occurrence_key, 0)
                    quote_occurrences[occurrence_key] = occurrence_index + 1
                    stable_id = canonical_artifact_quote_id(
                        raw, occurrence_index=occurrence_index
                    )
                else:
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
                    metric_text = metric_claim_text(
                        raw["metric"],
                        include_observations=verified_facts_only,
                        label_fields=verified_facts_only,
                    )
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
        stable_id = str(
            raw.get("id") or raw.get("figure_id") or raw.get("key_figure_id") or index
        ).strip()
        figure_text = metric_claim_text(
            raw,
            include_observations=verified_facts_only,
            label_fields=verified_facts_only,
        )
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


def metric_claim_text(
    metric: dict,
    *,
    include_observations: bool = False,
    label_fields: bool = False,
) -> str:
    """Create the canonical factual display from retained metric fields."""

    def display(field_name: str, value: object) -> str:
        text = str(value or "").strip()
        return f"{field_name}={text}" if label_fields and text else text

    display_value = metric.get("value") or metric.get("figure")
    source_statement = str(metric.get("source_statement") or "").strip()
    values = [
        display(key, metric.get(key))
        for key in (
            "label",
            "subject",
            "unit",
            "geography",
            "segment",
            "cohort",
            "denominator",
            "timeframe",
            "observation_status",
        )
    ]
    if source_statement:
        values.insert(0, display("source_statement", source_statement))
    values.insert(2, display("value", display_value))
    observations = metric.get("observations")
    if include_observations and isinstance(observations, list):
        for observation in observations:
            if not isinstance(observation, dict):
                continue
            values.extend(
                display(key, observation.get(key))
                for key in (
                    "label",
                    "value",
                    "unit",
                    "timeframe",
                    "geography",
                    "segment",
                    "cohort",
                    "denominator",
                    "observation_status",
                )
                if str(observation.get(key) or "").strip()
            )
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
    verified_facts_only: bool = False,
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
    if verified_facts_only:
        return checks, None
    cited = [source_evidence[reference.evidence_id][1] for reference in known]
    # Keep protected-dimension comparison as bounded diagnostic context for
    # audit/reuse, but never turn it into a deterministic semantic verdict.
    protected_facts = (
        compare_protected_fact_texts(text, "\n".join(cited)) if cited else None
    )
    checks.append(
        ClaimValidationCheck(
            schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
            name="semantic_grounding_required",
            status="not_applicable",
            reason="semantic_authority_deferred_to_grounding_model",
        )
    )
    return checks, protected_facts


def _chart_relationship_fidelity_check(
    claim: str,
    cited_sources: Sequence[tuple[str, str, int | None]],
) -> ClaimValidationCheck | None:
    """Verify platform/cohort/metric tuples when a page contains this chart form."""

    native_chart_sources = [
        (text, page)
        for source_pack, text, page in cited_sources
        if source_pack == "source_pdf" and has_two_panel_percent_chart_candidate(text)
    ]
    if not native_chart_sources:
        return None
    native_chart_text, chart_page = native_chart_sources[0]
    if chart_page is None:
        return _chart_relationship_failure("chart_physical_page_unresolved")
    expected_labels = two_panel_chart_platform_names(native_chart_text)
    chart_specific_claim = bool(
        re.search(r"\d+(?:\.\d+)?\s*%", claim)
        and re.search(r"\b(?:creators?|views?)\b", claim, re.IGNORECASE)
        and (
            re.search(r"\b\d+\s*m(?:\s*\+)?", claim, re.IGNORECASE)
            or any(
                re.search(
                    rf"(?<![\w]){re.escape(label)}(?![\w])",
                    claim,
                    re.IGNORECASE,
                )
                for label in (expected_labels or ())
            )
        )
    )
    if not chart_specific_claim:
        return None

    layout_texts = [
        text
        for source_pack, text, page in cited_sources
        if source_pack == "source_pdf_layout" and page == chart_page
    ]
    rows = []
    for layout_text in layout_texts:
        for line in layout_text.splitlines():
            match = _LAYOUT_CHART_ROW_RE.fullmatch(line.strip())
            if match is not None:
                rows.append(
                    {
                        "panel": int(match.group("panel")),
                        "cohort": _normalize_chart_cohort(match.group("cohort")),
                        "creator_value": float(match.group("creator_value")),
                        "view_value": float(match.group("view_value")),
                        "population": match.group("population").replace(" ", ""),
                    }
                )
    if not rows:
        return _chart_relationship_failure("chart_layout_relationship_unresolved")

    visual_sources = [
        text
        for source_pack, text, page in cited_sources
        if source_pack == "source_pdf_visual" and page == chart_page
    ]
    visual_labels: dict[int, str] = {}
    for visual_text in visual_sources:
        for line in visual_text.splitlines():
            match = _VISUAL_PANEL_LABEL_RE.fullmatch(line.strip())
            if match is None:
                continue
            panel = 1 if match.group("side").casefold() == "left" else 2
            visual_labels[panel] = match.group("label").strip()
    if (
        len(rows) != 4
        or set(visual_labels) != {1, 2}
        or expected_labels is None
        or {label.casefold() for label in visual_labels.values()}
        != {label.casefold() for label in expected_labels}
        or len({label.casefold() for label in visual_labels.values()}) != 2
    ):
        return _chart_relationship_failure("chart_visual_identity_unresolved")
    for row in rows:
        row["platform"] = visual_labels[int(row["panel"])]

    platform_matches = [
        row
        for row in rows
        if re.search(
            rf"(?<![\w]){re.escape(str(row['platform']))}(?![\w])",
            claim,
            re.IGNORECASE,
        )
    ]
    if not platform_matches:
        return _chart_relationship_failure("chart_platform_relationship_unresolved")

    population = str(platform_matches[0]["population"])
    population_match = re.fullmatch(
        r"(?P<number>\d+(?:\.\d+)?)(?P<unit>[kmb])", population, re.IGNORECASE
    )
    if population_match is None:
        return _chart_relationship_failure("chart_population_scope_unresolved")
    number = re.escape(population_match.group("number"))
    unit = re.escape(population_match.group("unit"))
    stated_population = re.search(
        rf"\bcreators?\b[^.;]{{0,100}}\b(?:over|more\s+than|>\s*)\s*"
        rf"{number}\s*{unit}\s+total\s+views\b",
        claim,
        re.IGNORECASE,
    )
    if stated_population is None:
        return _chart_relationship_failure("chart_population_scope_unresolved")

    platform_names = list(dict.fromkeys(str(row["platform"]) for row in rows))
    for platform in platform_names:
        if re.search(
            rf"\b(?:all|every)\s+(?:the\s+)?{re.escape(platform)}\s+"
            rf"(?:creators?|views?)\b",
            claim,
            re.IGNORECASE,
        ):
            return _chart_relationship_failure("chart_population_scope_expanded")
    platform_mentions = sorted(
        (
            match
            for name in platform_names
            for match in re.finditer(
                rf"(?<![\w]){re.escape(name)}(?![\w])", claim, re.IGNORECASE
            )
        ),
        key=lambda match: match.start(),
    )
    checked_row_count = 0
    for mention_index, mention in enumerate(platform_mentions):
        platform = mention.group(0)
        previous_mention_end = (
            platform_mentions[mention_index - 1].end() if mention_index else 0
        )
        preceding_boundary = max(
            claim.rfind(".", previous_mention_end, mention.start()),
            claim.rfind(";", previous_mention_end, mention.start()),
            claim.rfind(",", previous_mention_end, mention.start()),
            claim.rfind("\n", previous_mention_end, mention.start()),
        )
        start = max(previous_mention_end, preceding_boundary + 1)
        next_mention_start = (
            platform_mentions[mention_index + 1].start()
            if mention_index + 1 < len(platform_mentions)
            else len(claim)
        )
        following_boundary = min(
            (
                position
                for delimiter in (".", ";", ",", "\n")
                if (
                    position := claim.find(delimiter, mention.end(), next_mention_start)
                )
                >= 0
            ),
            default=next_mention_start,
        )
        end = min(next_mention_start, following_boundary)
        segment = claim[start:end]
        if re.search(
            rf"\b(?:all|every)\s+{re.escape(platform)}\s+(?:creators?|views?)\b",
            segment,
            re.IGNORECASE,
        ):
            return _chart_relationship_failure("chart_population_scope_expanded")

        for row in rows:
            if str(row["platform"]).casefold() != platform.casefold():
                continue
            if str(row["cohort"]) not in _normalize_chart_cohort(segment):
                continue
            checked_row_count += 1
            metrics: dict[str, list[float]] = {"creator": [], "view": []}
            for match in _CLAIM_CHART_METRIC_RE.finditer(segment):
                metric = (
                    "creator"
                    if match.group("metric").casefold().startswith("creator")
                    else "view"
                )
                metrics[metric].append(float(match.group("value")))
            if not metrics["creator"] or not metrics["view"]:
                return _chart_relationship_failure("chart_metric_label_unresolved")
            if metrics["creator"][0] != row["creator_value"]:
                return _chart_relationship_failure("chart_metric_relationship_mismatch")
            if metrics["view"][0] != row["view_value"]:
                return _chart_relationship_failure("chart_metric_relationship_mismatch")
    if checked_row_count == 0:
        return _chart_relationship_failure("chart_cohort_relationship_unresolved")
    return ClaimValidationCheck(
        schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
        name="chart_relationship_fidelity",
        status="passed",
        reason="chart_platform_cohort_metrics_and_scope_matched",
    )


def _normalize_chart_cohort(value: str) -> str:
    return re.sub(r"[^a-z0-9+]", "", str(value or "").casefold())


def _chart_relationship_failure(reason: str) -> ClaimValidationCheck:
    return ClaimValidationCheck(
        schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
        name="chart_relationship_fidelity",
        status="failed",
        reason=reason,
    )


def _validate_claims_against_sources(
    candidates: list[_ClaimValidationInput],
    source_evidence: dict[str, tuple[str, str, int | None]],
    *,
    artifact: object,
    semantic_validator: SemanticValidator | None = None,
    evidence_semantic_batch_validator: EvidenceSemanticBatchValidator | None = None,
    semantic_batch_validator: SemanticBatchValidator | None = None,
    semantic_results: list[ClaimSemanticGroundingResult] | None = None,
    source_identity: str = "",
    verified_facts_only: bool = False,
) -> ClaimValidationPackage:
    """Validate claims against authoritative retained source text.

    Candidate extraction remains owned by the artifact or evidence-pack boundary.
    Deterministic checks establish only technical evidence/provenance integrity.
    Every material candidate with a valid evidence binding is sent to the
    existing semantic batch and consumes only identity-matched tri-state results.
    """

    if semantic_validator is not None and evidence_semantic_batch_validator is not None:
        raise ValueError("Provide a semantic validator or its batch adapter, not both")
    if evidence_semantic_batch_validator is not None and (
        semantic_batch_validator is not None or semantic_results is not None
    ):
        raise ValueError("Evidence-fidelity and retained-claim batching cannot overlap")
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
                verified_facts_only=verified_facts_only,
            )
        structural_failures = [
            check.reason
            for check in checks
            if check.status == "failed"
            and check.name
            in {"evidence_reference_completeness", "soft_copy_provenance_integrity"}
        ]
        # Numeric, quotation, protected-dimension and chart comparisons are
        # diagnostics only.  They cannot certify or reject meaning before the
        # grounding model has classified and entailed the complete item.
        status = "unsupported" if structural_failures else "unresolved"
        failed = structural_failures
        deterministic_status = status
        semantic_used = False
        execution_identity = ""
        semantic_outcome: ClaimSemanticOutcome | None = None
        semantic_reason = ""
        if (
            status == "unresolved"
            and semantic_validator is not None
            and evidence_semantic_batch_validator is None
        ):
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

    if evidence_semantic_batch_validator is not None:
        pending_by_evidence: dict[
            tuple[tuple[str, str], ...], list[tuple[int, ClaimCandidate]]
        ] = {}
        pending_id_counts: dict[str, int] = {}
        for index, (candidate_input, result) in enumerate(
            zip(candidates, results, strict=True)
        ):
            if result.deterministic_status != "unresolved":
                continue
            candidate = candidate_input.candidate
            pending_id_counts[candidate.claim_id] = (
                pending_id_counts.get(candidate.claim_id, 0) + 1
            )
            evidence_bindings = tuple(
                (ref.evidence_id, source_evidence[ref.evidence_id][1])
                for ref in candidate.evidence_references
                if ref.evidence_id in source_evidence
            )
            pending_by_evidence.setdefault(evidence_bindings, []).append(
                (index, candidate)
            )

        duplicate_claim_ids = {
            claim_id for claim_id, count in pending_id_counts.items() if count > 1
        }
        for evidence_bindings, indexed_candidates in pending_by_evidence.items():
            valid_candidates = [
                (index, candidate)
                for index, candidate in indexed_candidates
                if candidate.claim_id not in duplicate_claim_ids
            ]
            for index, candidate in indexed_candidates:
                if candidate.claim_id in duplicate_claim_ids:
                    results[index] = replace(
                        results[index],
                        status="unsupported",
                        reasons=["semantic_claim_identity_ambiguous"],
                    )
            if not valid_candidates:
                continue

            batch_candidates = [candidate for _index, candidate in valid_candidates]
            batch_result = evidence_semantic_batch_validator(
                batch_candidates,
                [text for _evidence_id, text in evidence_bindings],
            )
            if not isinstance(batch_result, Mapping):
                batch_result = {}
            for index, candidate in valid_candidates:
                member = batch_result.get(candidate.claim_id)
                if (
                    not isinstance(member, tuple)
                    or len(member) != 3
                    or type(member[0]) is not bool
                    or not isinstance(member[1], str)
                    or not isinstance(member[2], str)
                ):
                    supported = False
                    reason = "semantic_support_not_established"
                    execution_identity = ""
                else:
                    supported, reason, execution_identity = member
                results[index] = replace(
                    results[index],
                    status="supported" if supported else "unsupported",
                    reasons=[reason],
                    semantic_outcome="entailed" if supported else None,
                    semantic_reason=reason,
                    semantic_validator_used=True,
                    semantic_execution_identity=execution_identity,
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
    source_pages: Sequence[PdfTextPage] = (),
) -> list[ClaimSemanticInput]:
    inputs: list[ClaimSemanticInput] = []
    seen_semantic_identities: set[tuple[object, ...]] = set()
    for result in results:
        candidate = result.candidate
        if result.deterministic_status != "unresolved":
            continue
        refs = candidate.evidence_references
        if not refs or any(ref.evidence_id not in source_evidence for ref in refs):
            continue
        evidence_texts, evidence_identities = _semantic_evidence_bindings(
            refs=refs,
            source_evidence=source_evidence,
            source_pages=source_pages,
        )
        evidence_hash = _hash(evidence_identities)
        semantic_identity = (
            candidate.claim_id,
            candidate.source_family,
            candidate.text,
            candidate.text_hash,
            candidate.kind,
            candidate.factual,
            tuple(candidate.evidence_references),
            tuple(evidence_texts),
            evidence_hash,
            source_identity,
        )
        if semantic_identity in seen_semantic_identities:
            continue
        seen_semantic_identities.add(semantic_identity)
        inputs.append(
            ClaimSemanticInput(
                schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
                candidate=candidate,
                evidence_texts=evidence_texts,
                evidence_hash=evidence_hash,
                source_identity=source_identity,
            )
        )
    return inputs


def retained_claim_semantic_evidence_hash(
    candidate: ClaimCandidate | Mapping[str, object],
    evidence_packs: dict,
    source_pages: Sequence[PdfTextPage] = (),
) -> str:
    """Hash the exact linked evidence identity used by semantic grounding."""

    payload = asdict(candidate) if isinstance(candidate, ClaimCandidate) else candidate
    references = payload.get("evidence_references")
    if not isinstance(references, list):
        return _hash([])
    _, identities = _semantic_evidence_bindings(
        refs=references,
        source_evidence=_evidence_index(evidence_packs),
        source_pages=source_pages,
    )
    return _hash(identities)


def _semantic_evidence_bindings(
    *,
    refs: Sequence[ClaimEvidenceReference | Mapping[str, object]],
    source_evidence: dict[str, tuple[str, str, int | None]],
    source_pages: Sequence[PdfTextPage],
) -> tuple[list[str], list[dict[str, object]]]:
    evidence_texts: list[str] = []
    identities: list[dict[str, object]] = []
    for ref in refs:
        evidence_id = str(_reference_value(ref, "evidence_id") or "")
        evidence_entry = source_evidence.get(evidence_id)
        source_pack, retained_text, indexed_page = evidence_entry or ("", "", None)
        page_value = _reference_value(ref, "page")
        referenced_page = page_value if isinstance(page_value, int) else indexed_page
        source_page = (
            _source_page_for_reference(
                source_pack=source_pack,
                referenced_page=referenced_page,
                source_pages=source_pages,
            )
            if evidence_entry is not None
            else None
        )
        page_text = source_page.text.strip() if source_page is not None else ""
        evidence_texts.append(page_text or retained_text)
        identity: dict[str, object] = {
            "evidence_id": evidence_id,
            "source_pack": str(_reference_value(ref, "source_pack") or ""),
            "page": page_value,
            "text_hash": str(_reference_value(ref, "text_hash") or ""),
        }
        if source_page is not None and page_text:
            identity.update(
                {
                    "source_page_id": f"source:page:{source_page.page_number}",
                    "source_page_printed_number": referenced_page,
                    "source_page_text_hash": _hash(page_text),
                }
            )
        identities.append(identity)
    return evidence_texts, identities


def _reference_value(
    reference: ClaimEvidenceReference | Mapping[str, object], field_name: str
) -> object:
    if isinstance(reference, Mapping):
        return reference.get(field_name)
    return getattr(reference, field_name, None)


def _source_page_for_reference(
    *,
    source_pack: str,
    referenced_page: int | None,
    source_pages: Sequence[PdfTextPage],
) -> PdfTextPage | None:
    if referenced_page is None or referenced_page <= 0:
        return None
    if source_pack != "doc_map":
        return next(
            (
                page
                for page in source_pages
                if page.page_number == referenced_page and page.text.strip()
            ),
            None,
        )

    matches = [
        page
        for page in source_pages
        if page.text.strip() and _has_printed_page_label(page.text, referenced_page)
    ]
    return matches[0] if len(matches) == 1 else None


def _has_printed_page_label(page_text: str, page_number: int) -> bool:
    """Match a DocMap's printed page only in likely header/footer lines."""

    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in str(page_text or "").splitlines()
        if line.strip()
    ]
    edge_lines = lines[:8] + lines[-8:]
    number = re.escape(str(page_number))
    for line in edge_lines:
        if line == str(page_number):
            return True
        if re.fullmatch(rf"(?i)(?:page|p\.?)\s*{number}(?:\s+of\s+\d+)?", line):
            return True
        if re.match(rf"^{number}[©�]\s+\d{{4}}\s+copyright\b", line, re.I):
            return True
        if len(line) <= 120 and re.search(rf"[•·|\-–—]\s*{number}$", line):
            return True
    return False


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
            identity.schema_version in {"1.0", "1.1"}
            and identity.claim_text_hash == candidate.text_hash
            and identity.evidence_ids == expected_evidence_ids
            and identity.evidence_hash == semantic_input.evidence_hash
            and identity.source_identity == semantic_input.source_identity
            and bool(identity.prompt_family)
            and bool(identity.prompt_content_hash)
            and bool(identity.execution_identity)
            and identity.validator_version == CLAIM_GROUNDING_VALIDATOR_VERSION
            and bool(identity.model_provider)
            and bool(identity.model_name)
            and bool(identity.configuration_policy_identity)
            and bool(identity.relevant_input_hash)
            and (identity.schema_version == "1.0" or bool(identity.retrieval_identity))
        )
        if not identity_matches:
            updated.append(
                replace(
                    result,
                    semantic_disagreement="semantic_result_identity_mismatch",
                )
            )
            continue

        # Protected-fact comparisons are retained as audit context only.  They
        # cannot override the independent grounding model's semantic outcome;
        # that would recreate the deterministic entailment veto this package
        # is intended to eliminate.
        disagreement = semantic.disagreement
        outcome = semantic.outcome
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
    unsupported = sum(1 for item in results if item.status == "unsupported")
    unresolved = sum(1 for item in results if item.status == "unresolved")
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
    package = ClaimValidationPackage(
        schema_version=CLAIM_VALIDATION_SCHEMA_VERSION,
        artifact_hash=artifact_hash,
        package_hash="",
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
    return replace(
        package,
        package_hash=claim_validation_package_hash(package),
    )


def materialize_retained_claim_package(
    package: ClaimValidationPackage | dict | None,
    *,
    report_id: str,
    artifacts: dict,
    evidence_packs: dict,
    final_html: str,
    source_id: str = "",
    source_pages: Sequence[PdfTextPage] = (),
    source_md5: str = "",
    configuration_hash: str = "",
    policy_hash: str = "",
    verified_facts_only: bool = False,
) -> tuple[dict | None, str]:
    """Bind current deterministic grounding and matching semantic results.

    The persisted validation package is only a candidate. A candidate that no
    longer matches the canonical final artifacts is discarded; deterministic
    grounding is rebuilt from those final inputs, while no semantic provider is
    called. Missing identities that prevent an authoritative package return a
    stable terminal code.
    """
    report_id = str(report_id or "").strip()
    source_id = str(source_id or "").strip()
    configuration_hash = str(configuration_hash or "").strip()
    policy_hash = str(policy_hash or "").strip()
    if not report_id or not source_id or not configuration_hash or not policy_hash:
        return None, "retained_claim_materialization_identity_missing"
    if (
        not isinstance(artifacts, dict)
        or not isinstance(evidence_packs, dict)
        or not isinstance(final_html, str)
    ):
        return None, "retained_claim_materialization_input_invalid"

    current = validate_retained_claims(
        artifacts,
        evidence_packs,
        source_identity=source_id,
        verified_facts_only=verified_facts_only,
    )
    current_payload = attach_claim_validation_execution_identity(
        current,
        report_id=report_id,
        source_id=source_id,
        source_md5=source_md5,
        configuration_hash=configuration_hash,
        policy_hash=policy_hash,
    )
    candidate_payload = (
        asdict(package)
        if isinstance(package, ClaimValidationPackage)
        else dict(package)
        if isinstance(package, dict)
        else {}
    )
    reusable_semantic_results = _claim_validation_semantic_results_for_final_inputs(
        candidate_payload,
        current=current,
        report_id=report_id,
        source_id=source_id,
        evidence_packs=evidence_packs,
        source_pages=source_pages,
        source_md5=source_md5,
        configuration_hash=configuration_hash,
        policy_hash=policy_hash,
    )
    current_results = current_payload["results"]
    current_by_candidate: dict[str, list[dict]] = {}
    for result in current_results:
        if isinstance(result, dict) and isinstance(result.get("candidate"), dict):
            current_by_candidate.setdefault(_hash(result["candidate"]), []).append(
                result
            )
    for candidate_hash, stored_result in reusable_semantic_results.items():
        matching_current = current_by_candidate.get(candidate_hash, [])
        if not matching_current:
            continue
        semantic_result_fields = (
            "status",
            "reasons",
            "semantic_outcome",
            "semantic_reason",
            "semantic_protected_facts",
            "semantic_identity",
            "semantic_disagreement",
            "semantic_validator_used",
            "semantic_execution_identity",
        )
        if any(
            current_result.get("deterministic_status")
            != stored_result.get("deterministic_status")
            or _hash(current_result.get("checks")) != _hash(stored_result.get("checks"))
            or _hash(current_result.get("protected_facts"))
            != _hash(stored_result.get("protected_facts"))
            for current_result in matching_current
        ):
            continue
        for current_result in matching_current:
            current_result.update(
                {field: stored_result.get(field) for field in semantic_result_fields}
            )
    semantic_results = [
        result
        for result in current_results
        if isinstance(result, dict) and result.get("semantic_validator_used") is True
    ]
    unsupported = sum(
        result.get("status") == "unsupported" for result in current_results
    )
    unresolved = sum(result.get("status") == "unresolved" for result in current_results)
    deterministic_passes = sum(
        result.get("status") == "supported"
        and result.get("semantic_validator_used") is not True
        for result in current_results
    )
    raw = current_payload
    raw["unsupported_factual_count"] = unsupported
    raw["unresolved_factual_count"] = unresolved
    raw["deterministic_pass_count"] = deterministic_passes
    raw["semantic_validation_count"] = len(semantic_results)
    raw["semantic_execution_identities"] = sorted(
        {
            str(result["semantic_identity"]["execution_identity"])
            for result in semantic_results
            if isinstance(result.get("semantic_identity"), dict)
        }
    )
    raw["readiness_status"] = (
        "not_publishable" if unsupported or unresolved else "awaiting_review"
    )
    semantic_execution_ids = sorted(
        {
            str(result["semantic_identity"]["execution_identity"])
            for result in semantic_results
            if isinstance(result.get("semantic_identity"), dict)
        }
    )
    prompt_hashes = sorted(
        {
            str(result["semantic_identity"]["prompt_content_hash"])
            for result in semantic_results
            if isinstance(result.get("semantic_identity"), dict)
        }
    )
    model_identities = sorted(
        {
            f"{result['semantic_identity']['model_provider']}"
            f"/{result['semantic_identity']['model_name']}"
            for result in semantic_results
            if isinstance(result.get("semantic_identity"), dict)
        }
    )
    lineage = ClaimValidationLineage(
        schema_version="1.1",
        report_id=report_id,
        final_artifact_hash=current.artifact_hash,
        publication_projection_hash=publication_projection_hash(final_html),
        evidence_pack_hash=_hash(evidence_packs),
        source_id=source_id,
        source_md5=str(source_md5 or ""),
        claim_validation_validator_version=CLAIM_VALIDATION_VALIDATOR_VERSION,
        grounding_validator_version=CLAIM_GROUNDING_VALIDATOR_VERSION,
        semantic_execution_identities=semantic_execution_ids,
        semantic_prompt_content_hashes=prompt_hashes,
        semantic_model_identities=model_identities,
        configuration_hash=configuration_hash,
        policy_hash=policy_hash,
    )
    raw["schema_version"] = CLAIM_VALIDATION_SCHEMA_VERSION
    raw["lineage"] = asdict(lineage)
    raw["package_hash"] = ""
    raw["package_hash"] = claim_validation_package_hash(raw)
    return raw, ""


def _claim_validation_semantic_results_for_final_inputs(
    raw: dict,
    *,
    current: ClaimValidationPackage,
    report_id: str,
    source_id: str,
    evidence_packs: dict,
    source_pages: Sequence[PdfTextPage],
    source_md5: str,
    configuration_hash: str,
    policy_hash: str,
) -> dict[str, dict]:
    """Return only semantic claim results whose exact inputs survive finalization."""
    if raw.get(
        "schema_version"
    ) != CLAIM_VALIDATION_SCHEMA_VERSION or not claim_validation_package_hash_valid(
        raw
    ):
        return {}
    artifact_hash = str(raw.get("artifact_hash") or "")
    if len(artifact_hash) != 64 or any(
        character not in "0123456789abcdef" for character in artifact_hash
    ):
        return {}
    validation_identity = raw.get("validation_identity")
    if not isinstance(validation_identity, dict) or any(
        (
            validation_identity.get("schema_version") != "1.1",
            validation_identity.get("report_id") != report_id,
            validation_identity.get("claim_validation_validator_version")
            != CLAIM_VALIDATION_VALIDATOR_VERSION,
            validation_identity.get("grounding_validator_version")
            != CLAIM_GROUNDING_VALIDATOR_VERSION,
            validation_identity.get("source_id") != source_id,
            validation_identity.get("source_md5") != source_md5,
            validation_identity.get("configuration_hash") != configuration_hash,
            validation_identity.get("policy_hash") != policy_hash,
        )
    ):
        return {}

    raw_results = raw.get("results")
    if not isinstance(raw_results, list) or any(
        not isinstance(result, dict)
        or not isinstance(result.get("candidate"), dict)
        or not isinstance(result["candidate"].get("factual"), bool)
        or result.get("status")
        not in {"supported", "unsupported", "unresolved", "not_applicable"}
        or result.get("deterministic_status")
        not in {"supported", "unsupported", "unresolved", "not_applicable"}
        or not isinstance(result.get("semantic_validator_used"), bool)
        for result in raw_results
    ):
        return {}
    semantic_results = [
        result for result in raw_results if result["semantic_validator_used"] is True
    ]
    unsupported = sum(result["status"] == "unsupported" for result in raw_results)
    unresolved = sum(result["status"] == "unresolved" for result in raw_results)
    deterministic_passes = sum(
        result["status"] == "supported"
        and result["semantic_validator_used"] is not True
        for result in raw_results
    )
    if (
        type(raw.get("unsupported_factual_count")) is not int
        or raw.get("unsupported_factual_count") != unsupported
        or type(raw.get("unresolved_factual_count")) is not int
        or raw.get("unresolved_factual_count") != unresolved
        or type(raw.get("deterministic_pass_count")) is not int
        or raw.get("deterministic_pass_count") != deterministic_passes
        or type(raw.get("semantic_validation_count")) is not int
        or raw.get("semantic_validation_count") != len(semantic_results)
        or raw.get("readiness_status")
        != ("not_publishable" if unsupported or unresolved else "awaiting_review")
    ):
        return {}

    current_semantic_inputs = _semantic_inputs(
        current.results,
        _evidence_index(evidence_packs),
        source_id,
        source_pages,
    )
    current_evidence_hash_by_candidate = {
        _hash(asdict(semantic_input.candidate)): semantic_input.evidence_hash
        for semantic_input in current_semantic_inputs
    }
    current_by_candidate: dict[str, list[dict]] = {}
    for result in current.results:
        current_by_candidate.setdefault(_hash(asdict(result.candidate)), []).append(
            asdict(result)
        )
    semantic_execution_ids: set[str] = set()
    reusable: dict[str, dict] = {}
    ambiguous: set[str] = set()
    for result in semantic_results:
        identity = result.get("semantic_identity")
        candidate = result.get("candidate")
        if not isinstance(identity, dict) or not isinstance(candidate, dict):
            return {}
        candidate_hash = _hash(candidate)
        references = candidate.get("evidence_references")
        if not isinstance(references, list) or any(
            not isinstance(reference, dict) for reference in references
        ):
            return {}
        expected_evidence_ids = [
            str(reference.get("evidence_id") or "") for reference in references
        ]
        expected_evidence_hash = current_evidence_hash_by_candidate.get(candidate_hash)
        execution_identity = str(identity.get("execution_identity") or "")
        if (
            identity.get("schema_version") not in {"1.0", "1.1"}
            or not execution_identity
            or str(result.get("semantic_execution_identity") or "")
            != execution_identity
            or str(identity.get("validator_version") or "")
            != CLAIM_GROUNDING_VALIDATOR_VERSION
            or str(identity.get("source_identity") or "") != source_id
            or not str(identity.get("prompt_content_hash") or "")
            or not str(identity.get("model_provider") or "")
            or not str(identity.get("model_name") or "")
            or not str(identity.get("prompt_family") or "")
            or not str(identity.get("configuration_policy_identity") or "")
            or not str(identity.get("relevant_input_hash") or "")
            or (
                identity.get("schema_version") == "1.1"
                and not re.fullmatch(
                    r"[0-9a-f]{64}", str(identity.get("retrieval_identity") or "")
                )
            )
            or identity.get("claim_id") != candidate.get("claim_id")
            or identity.get("claim_text_hash") != candidate.get("text_hash")
            or identity.get("evidence_ids") != expected_evidence_ids
            or not expected_evidence_hash
            or identity.get("evidence_hash") != expected_evidence_hash
            or result.get("deterministic_status") != "unresolved"
            or {
                "entailed": "supported",
                "contradicted": "unsupported",
                "not_established": "unresolved",
            }.get(result.get("semantic_outcome"))
            != result.get("status")
        ):
            return {}
        semantic_execution_ids.add(execution_identity)
        current_matches = current_by_candidate.get(candidate_hash, [])
        if not current_matches:
            continue
        if candidate.get("factual") is not True or any(
            result.get("deterministic_status")
            != current_result.get("deterministic_status")
            or _hash(result.get("checks")) != _hash(current_result.get("checks"))
            or _hash(result.get("protected_facts"))
            != _hash(current_result.get("protected_facts"))
            or result.get("deterministic_status") != "unresolved"
            for current_result in current_matches
        ):
            continue
        existing = reusable.get(candidate_hash)
        if existing is None:
            reusable[candidate_hash] = result
            continue
        semantic_result_fields = (
            "status",
            "deterministic_status",
            "reasons",
            "semantic_outcome",
            "semantic_reason",
            "semantic_protected_facts",
            "semantic_identity",
            "semantic_disagreement",
            "semantic_validator_used",
            "semantic_execution_identity",
        )
        if any(
            existing.get(field) != result.get(field) for field in semantic_result_fields
        ):
            ambiguous.add(candidate_hash)

    if not isinstance(raw.get("semantic_execution_identities"), list) or sorted(
        str(item) for item in raw["semantic_execution_identities"]
    ) != sorted(semantic_execution_ids):
        return {}
    return {
        candidate_hash: result
        for candidate_hash, result in reusable.items()
        if candidate_hash not in ambiguous
    }


def retained_claim_semantic_inputs(
    package: ClaimValidationPackage,
    evidence_packs: dict,
    *,
    source_identity: str = "",
    source_pages: Sequence[PdfTextPage] = (),
) -> list[ClaimSemanticInput]:
    """Return only unresolved factual claims with all exact linked source text."""

    return _semantic_inputs(
        package.results,
        _evidence_index(evidence_packs),
        source_identity,
        source_pages,
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


def reuse_retained_claim_semantic_results(
    package: ClaimValidationPackage,
    semantic_inputs: list[ClaimSemanticInput],
    prior_package: ClaimValidationPackage | dict | None,
    *,
    expected_prior_artifact_hash: str,
    report_id: str,
    source_id: str,
    source_md5: str,
    configuration_hash: str,
    policy_hash: str,
    prompt_family: str,
    prompt_execution_identity: str,
    model_provider: str,
    model_name: str,
    configuration_policy_identity: str,
    retrieval_identity: str,
    prompt_content_hash_by_claim_id: dict[str, str],
) -> tuple[ClaimValidationPackage, list[ClaimSemanticInput], dict[str, object]]:
    """Reuse only passing semantic results bound to exact claim/source identities."""
    fallback_reasons: dict[str, int] = {}

    def reject(reason: str) -> None:
        fallback_reasons[reason] = fallback_reasons.get(reason, 0) + 1

    prior = (
        asdict(prior_package)
        if isinstance(prior_package, ClaimValidationPackage)
        else dict(prior_package)
        if isinstance(prior_package, dict)
        else {}
    )
    if not prior:
        reject("prior_package_missing")
        old_results: list[dict] = []
    elif prior.get(
        "schema_version"
    ) != CLAIM_VALIDATION_SCHEMA_VERSION or not claim_validation_package_hash_valid(
        prior
    ):
        reject("prior_package_invalid")
        old_results = []
    elif (
        not expected_prior_artifact_hash
        or prior.get("artifact_hash") != expected_prior_artifact_hash
    ):
        reject("prior_artifact_identity_mismatch")
        old_results = []
    elif prior.get("readiness_status") not in {
        "awaiting_review",
        "not_publishable",
    }:
        reject("prior_package_invalid")
        old_results = []
    else:
        identity = prior.get("validation_identity")
        expected_validation_identity = {
            "schema_version": "1.1",
            "report_id": str(report_id or ""),
            "source_id": str(source_id or ""),
            "source_md5": str(source_md5 or ""),
            "claim_validation_validator_version": CLAIM_VALIDATION_VALIDATOR_VERSION,
            "grounding_validator_version": CLAIM_GROUNDING_VALIDATOR_VERSION,
            "configuration_hash": str(configuration_hash or ""),
            "policy_hash": str(policy_hash or ""),
        }
        if not isinstance(identity, dict) or any(
            identity.get(key) != expected
            for key, expected in expected_validation_identity.items()
        ):
            reject("validator_identity_incompatible")
            old_results = []
        else:
            results_value = prior.get("results")
            if not isinstance(results_value, list) or any(
                not isinstance(result, dict)
                or not isinstance(result.get("candidate"), dict)
                for result in results_value
            ):
                reject("prior_package_invalid")
                old_results = []
            else:
                semantic = [
                    result
                    for result in results_value
                    if result.get("semantic_validator_used") is True
                ]
                unsupported = sum(
                    result.get("status") == "unsupported" for result in results_value
                )
                unresolved = sum(
                    result.get("status") == "unresolved" for result in results_value
                )
                semantic_execution_ids = sorted(
                    {
                        str(result.get("semantic_execution_identity") or "")
                        for result in semantic
                        if result.get("semantic_execution_identity")
                    }
                )
                if (
                    type(prior.get("unsupported_factual_count")) is not int
                    or prior.get("unsupported_factual_count") != unsupported
                    or type(prior.get("unresolved_factual_count")) is not int
                    or prior.get("unresolved_factual_count") != unresolved
                    or type(prior.get("semantic_validation_count")) is not int
                    or prior.get("semantic_validation_count") != len(semantic)
                    or prior.get("readiness_status")
                    != (
                        "not_publishable"
                        if unsupported or unresolved
                        else "awaiting_review"
                    )
                    or prior.get("semantic_execution_identities")
                    != semantic_execution_ids
                ):
                    reject("prior_package_invalid")
                    old_results = []
                else:
                    old_results = results_value

    if old_results:
        old_by_id: dict[str, list[dict]] = {}
        for old_result in old_results:
            old_candidate = old_result["candidate"]
            claim_id = str(old_candidate.get("claim_id") or "")
            if claim_id:
                old_by_id.setdefault(claim_id, []).append(old_result)
    else:
        old_by_id = {}

    current_by_id: dict[str, list[ClaimValidationResult]] = {}
    for current_result in package.results:
        current_by_id.setdefault(current_result.candidate.claim_id, []).append(
            current_result
        )

    reused_results: list[ClaimSemanticGroundingResult] = []
    reused_ids: set[str] = set()
    for semantic_input in semantic_inputs:
        candidate = semantic_input.candidate
        claim_id = candidate.claim_id
        old_matches = old_by_id.get(claim_id, [])
        current_matches = current_by_id.get(claim_id, [])
        if not old_results:
            # Package-level fallback already has a precise reason.
            continue
        if not old_matches:
            reject("new_claim")
            continue
        if len(old_matches) != 1 or len(current_matches) != 1:
            reject("claim_identity_ambiguous")
            continue

        prior_result = old_matches[0]
        current_result = current_matches[0]
        prior_candidate = prior_result.get("candidate")
        if not isinstance(prior_candidate, dict):
            reject("prior_package_invalid")
            continue
        current_candidate = asdict(candidate)
        if prior_candidate != current_candidate:
            if (
                prior_candidate.get("text_hash") != candidate.text_hash
                or prior_candidate.get("text") != candidate.text
            ):
                reject("claim_identity_changed")
            elif (
                prior_candidate.get("evidence_references")
                != current_candidate["evidence_references"]
            ):
                reject("evidence_identity_changed")
            elif (
                not prior_candidate.get("provenance_hash")
                or not candidate.provenance_hash
                or prior_candidate.get("provenance_hash") != candidate.provenance_hash
            ):
                reject("provenance_identity_changed")
            else:
                reject("claim_identity_changed")
            continue
        if (
            not re.fullmatch(r"[0-9a-f]{64}", candidate.provenance_hash)
            or current_result.deterministic_status
            != prior_result.get("deterministic_status")
            or _hash([asdict(check) for check in current_result.checks])
            != _hash(prior_result.get("checks"))
            or _hash(
                asdict(current_result.protected_facts)
                if current_result.protected_facts is not None
                else None
            )
            != _hash(prior_result.get("protected_facts"))
        ):
            reject("deterministic_validation_changed")
            continue
        if (
            prior_result.get("status") != "supported"
            or prior_result.get("semantic_outcome") != "entailed"
            or prior_result.get("semantic_validator_used") is not True
            or prior_result.get("semantic_disagreement")
        ):
            reject("prior_result_not_supported")
            continue
        identity = prior_result.get("semantic_identity")
        if not isinstance(identity, dict):
            reject("semantic_identity_missing")
            continue
        expected_evidence_ids = [
            reference.evidence_id for reference in candidate.evidence_references
        ]
        if (
            identity.get("schema_version") != "1.1"
            or identity.get("claim_id") != claim_id
            or identity.get("claim_text_hash") != candidate.text_hash
            or identity.get("evidence_ids") != expected_evidence_ids
            or identity.get("evidence_hash") != semantic_input.evidence_hash
            or identity.get("source_identity") != semantic_input.source_identity
            or identity.get("retrieval_identity") != retrieval_identity
            or str(prior_result.get("semantic_execution_identity") or "")
            != identity.get("execution_identity")
        ):
            reject("evidence_identity_changed")
            continue
        current_prompt_content_hash = prompt_content_hash_by_claim_id.get(claim_id, "")
        if not re.fullmatch(r"[0-9a-f]{64}", current_prompt_content_hash):
            reject("semantic_identity_missing")
            continue
        if identity.get("prompt_content_hash") != current_prompt_content_hash:
            reject("prompt_context_changed")
            continue
        if any(
            (
                identity.get("prompt_family") != prompt_family,
                identity.get("execution_identity") != prompt_execution_identity,
                identity.get("validator_version") != CLAIM_GROUNDING_VALIDATOR_VERSION,
                identity.get("model_provider") != model_provider,
                identity.get("model_name") != model_name,
                identity.get("configuration_policy_identity")
                != configuration_policy_identity,
            )
        ):
            reject("validator_identity_incompatible")
            continue
        if not all(
            re.fullmatch(r"[0-9a-f]{64}", str(identity.get(key) or ""))
            for key in (
                "prompt_content_hash",
                "relevant_input_hash",
                "retrieval_identity",
            )
        ):
            reject("semantic_identity_missing")
            continue

        raw_protected_facts = prior_result.get("semantic_protected_facts")
        if not isinstance(raw_protected_facts, dict):
            reject("semantic_identity_missing")
            continue
        protected_facts = ProtectedFactComparison.from_payload(
            raw_protected_facts.get("dimensions"),
            proposition_status=str(
                raw_protected_facts.get("proposition_status") or "unknown"
            ),
        )
        reused_results.append(
            ClaimSemanticGroundingResult(
                schema_version="1.0",
                outcome="entailed",
                reason=str(prior_result.get("semantic_reason") or ""),
                identity=ClaimSemanticValidationIdentity(
                    schema_version="1.1",
                    claim_id=str(identity["claim_id"]),
                    claim_text_hash=str(identity["claim_text_hash"]),
                    evidence_ids=list(identity["evidence_ids"]),
                    evidence_hash=str(identity["evidence_hash"]),
                    source_identity=str(identity["source_identity"]),
                    prompt_family=str(identity["prompt_family"]),
                    prompt_content_hash=str(identity["prompt_content_hash"]),
                    execution_identity=str(identity["execution_identity"]),
                    validator_version=str(identity["validator_version"]),
                    model_provider=str(identity["model_provider"]),
                    model_name=str(identity["model_name"]),
                    configuration_policy_identity=str(
                        identity["configuration_policy_identity"]
                    ),
                    relevant_input_hash=str(identity["relevant_input_hash"]),
                    retrieval_identity=str(identity["retrieval_identity"]),
                ),
                protected_facts=protected_facts,
                disagreement="",
            )
        )
        reused_ids.add(claim_id)

    if reused_results:
        package = apply_retained_claim_semantic_results(
            package,
            [
                semantic_input
                for semantic_input in semantic_inputs
                if semantic_input.candidate.claim_id in reused_ids
            ],
            reused_results,
        )
    remaining_inputs = [
        semantic_input
        for semantic_input in semantic_inputs
        if semantic_input.candidate.claim_id not in reused_ids
    ]
    reused_count = len(reused_results)
    telemetry: dict[str, object] = {
        "total_candidate_claims": len(package.results),
        "reused_validation_results": reused_count,
        "newly_validated_claims": max(0, len(package.results) - reused_count),
        "semantic_validation_calls_avoided": reused_count,
        "reuse_fallback_reason_counts": fallback_reasons,
    }
    return package, remaining_inputs, telemetry


def _source_index(
    source_spans: list[dict[str, object]],
) -> dict[str, tuple[str, str, int | None]]:
    indexed: dict[str, tuple[str, str, int | None]] = {}
    for index, raw in enumerate(source_spans, start=1):
        span_id = str(raw.get("id") or f"source:{index}").strip()
        text = str(raw.get("text") or "").strip()
        page = raw.get("page")
        if span_id and text:
            source_pack = (
                "source_pdf_layout"
                if raw.get("evidence_kind") == "native_pdf_geometry"
                and raw.get("verbatim") is False
                else "source_pdf_visual"
                if raw.get("evidence_kind") == "visual_model_transcription"
                and raw.get("verbatim") is False
                else "source_pdf"
            )
            indexed[span_id] = (
                source_pack,
                text,
                page if isinstance(page, int) and not isinstance(page, bool) else None,
            )
    return indexed


def _source_pages_support_numeric_claim(
    raw: dict,
    pages: Sequence[int],
    source_evidence: dict[str, tuple[str, str, int | None]],
) -> bool:
    claim_quantities = extract_quantities(_item_claim_text(raw))
    if not claim_quantities:
        return False
    page_quantities = [
        quantity
        for _pack, text, page in source_evidence.values()
        if page in pages
        for quantity in extract_quantities(text)
    ]
    status, _reason = _numeric_evidence_status(claim_quantities, page_quantities)
    return status == "passed"


def _source_references(
    raw: dict,
    source_evidence: dict[str, tuple[str, str, int | None]],
    *,
    include_text: bool = False,
) -> list[ClaimEvidenceReference]:
    pages_raw = raw.get("pages", raw.get("page"))
    pages = pages_raw if isinstance(pages_raw, list) else [pages_raw]
    page_values = [
        value
        for value in pages
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
    ]
    exact_evidence_pages = _exact_evidence_pages(
        _item_direct_evidence_text(raw, include_text=include_text), source_evidence
    )
    if exact_evidence_pages:
        page_values = [page for page in page_values if page in exact_evidence_pages]
        if not page_values:
            page_values = exact_evidence_pages[:1]
    elif len(page_values) == 1:
        source_text = _item_source_text(raw)
        matched_pages = _matched_source_pages(source_text, source_evidence)
        if (
            len(matched_pages) == 1
            and matched_pages[0] != page_values[0]
            and not _source_pages_support_numeric_claim(
                raw, page_values, source_evidence
            )
            and _source_pages_support_numeric_claim(raw, matched_pages, source_evidence)
        ):
            matched_page_text = "\n".join(
                text
                for _pack, text, page in source_evidence.values()
                if page == matched_pages[0]
            )
            shared_tokens = _recovery_tokens(source_text) & _recovery_tokens(
                matched_page_text
            )
            if len(shared_tokens) >= 5:
                page_values = matched_pages
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


def _item_direct_evidence_text(raw: dict, *, include_text: bool = False) -> str:
    """Return only the retained direct excerpt for a finding or quotation.

    The finding ``text`` is generated copy, so it is excluded by default. A
    quote candidate may opt in because its contract defines ``text`` as the
    source quotation rather than generated finding prose.
    """

    primary = ""
    keys: tuple[str, ...] = (
        "evidence",
        "quote",
        "quote_text",
        "snippet",
        "excerpt",
    )
    if include_text:
        keys += ("text",)
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            primary = value.strip()
            break
    return primary


def _exact_evidence_pages(
    evidence_text: str,
    source_evidence: dict[str, tuple[str, str, int | None]],
) -> list[int]:
    """Resolve a specific direct excerpt to its physical PDF page.

    Pack page values can be copied from DocMap's printed labels. Exact source
    text is authoritative when it identifies a physical page, while short
    fragments remain too ambiguous to override an explicit page value.
    """

    normalized = normalize_for_lookup(evidence_text)
    if not normalized or (
        len(_recovery_tokens(evidence_text)) < 5
        and len(_recovery_quantity_values(evidence_text)) < 2
    ):
        return []
    return sorted(
        {
            page
            for _source_id, (_pack, source_text, page) in source_evidence.items()
            if page is not None
            and (
                normalized in normalize_for_lookup(source_text)
                or _compact_lookup_text(evidence_text)
                in _compact_lookup_text(source_text)
            )
        }
    )


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
            if page is not None
            and (
                normalized in normalize_for_lookup(source_text)
                or _compact_lookup_text(evidence_text)
                in _compact_lookup_text(source_text)
            )
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


def _compact_lookup_text(value: str) -> str:
    """Remove OCR-inserted whitespace without changing lookup characters."""

    return re.sub(r"\s+", "", normalize_for_lookup(value))


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


def _numeric_evidence_status(
    claim_quantities: Sequence[Quantity], evidence_quantities: Sequence[Quantity]
) -> tuple[Literal["passed", "failed", "not_applicable"], str]:
    """Separate absent quantitative evidence from a comparable contradiction."""
    claim_quantities = [
        quantity
        for quantity in claim_quantities
        if not _is_calendar_year_quantity(quantity)
    ]
    evidence_quantities = [
        quantity
        for quantity in evidence_quantities
        if not _is_calendar_year_quantity(quantity)
    ]
    if not claim_quantities:
        return "failed", "quantity_not_entailed"
    if all(
        any(
            _quantity_entailed_by_evidence(claim, evidence)
            for evidence in evidence_quantities
        )
        for claim in claim_quantities
    ):
        return "passed", "quantities_matched"

    # A quantity with no linked evidence of its unit family is unestablished,
    # not contradicted. If the source does contain that family but the value
    # fails to match, preserve the hard numeric rejection.
    for claim in claim_quantities:
        if any(
            _quantity_entailed_by_evidence(claim, evidence)
            for evidence in evidence_quantities
        ):
            continue
        if any(
            claim.unit_family != "unknown" and claim.unit_family == evidence.unit_family
            for evidence in evidence_quantities
        ):
            return "failed", "quantity_not_entailed"

    return "not_applicable", "quantity_not_established"


def _is_calendar_year_quantity(quantity: Quantity) -> bool:
    """Let protected timeframe validation handle explicit calendar years."""

    return (
        quantity.unit_family == "time"
        and quantity.unit.casefold() in {"year", "years"}
        and quantity.value.is_integer()
        and 1900 <= int(quantity.value) <= 2100
    )


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
                        # Evidence-pack findings are also material semantic
                        # propositions.  Do not let their deterministic kind
                        # taxonomy bypass the grounding model.
                        factual=True,
                        evidence_references=_source_references(
                            item,
                            source_evidence,
                            include_text=pack_name == "quote_candidates",
                        ),
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
    semantic_batch_validator: EvidenceSemanticBatchValidator | None = None,
) -> ClaimValidationPackage:
    """Validate generated, editorially usable evidence against PDF-derived spans."""

    source_evidence = _source_index(source_spans)
    return _validate_claims_against_sources(
        _evidence_fidelity_candidates(evidence_packs, source_evidence),
        source_evidence,
        artifact=evidence_packs,
        semantic_validator=semantic_validator,
        evidence_semantic_batch_validator=semantic_batch_validator,
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
    verified_facts_only: bool = False,
) -> ClaimValidationPackage:
    """Validate retained claims, batching semantic fallback for undecidable facts."""

    evidence = _evidence_index(evidence_packs)
    return _validate_claims_against_sources(
        _candidates(artifacts, evidence, verified_facts_only=verified_facts_only),
        evidence,
        artifact=artifacts,
        semantic_batch_validator=semantic_batch_validator,
        semantic_results=semantic_results,
        source_identity=source_identity,
        verified_facts_only=verified_facts_only,
    )
