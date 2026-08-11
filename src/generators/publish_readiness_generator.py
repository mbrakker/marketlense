"""Canonical, deterministic readiness gate for rendered report publication."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from src.contracts.public_editorial_quality import PublicEditorialQualityReport
from src.contracts.publish_readiness import (
    PUBLISH_READINESS_SCHEMA_VERSION,
    PUBLISH_READINESS_VALIDATOR_VERSION,
    PublishReadinessArtifact,
    PublishReadinessRuleResult,
)
from src.contracts.validation import ValidationReport
from src.generators.public_editorial_quality_generator import (
    evaluate_public_editorial_quality,
)
from src.utils.publication_projection import publication_projection_hash

_INTERNAL_TOKEN = re.compile(
    r"\b(?:evidence|claim|file|finding|insight|quote|figure)"
    r"(?:_[a-z0-9][a-z0-9_]*|-[a-z0-9-]*\d[a-z0-9-]*)\b",
    re.IGNORECASE,
)
_RAW_EVIDENCE_TOKEN = re.compile(
    r"\b(?:turn\d+(?:file|search)\d+|(?:f|e|ev|ic|fig)[_-]?\d{1,5})\b",
    re.IGNORECASE,
)
_PRIVATE_LOCATION = re.compile(
    r"(?:https?://(?:drive\.google\.com|localhost|127\.0\.0\.1)\S*|"
    r"\b[A-Za-z]:[\\/]|(?:^|[\"'])/(?:out|cache|state)/)",
    re.IGNORECASE,
)
_FILENAME_TITLE = re.compile(
    r"(?:^|\s)[^\s]+\.(?:pdf|html?|json|png|jpe?g|webp)(?:\s|$)", re.IGNORECASE
)
_DUPLICATED_YEAR = re.compile(r"\b(20\d{2})\D{0,4}\1\b")
_ELLIPSIS = re.compile(r"(?:\.\.\.|…)")
_MECHANICAL = re.compile(r"\b(?:answer|observation)\s*:", re.IGNORECASE)
_NON_PUBLIC_CARD_STATUSES = {
    "abstained",
    "limited",
    "not_applicable",
    "omitted",
    "text_only",
    "unavailable",
    "weak",
    "weak_evidence",
}
_MAX_READINESS_AGE = timedelta(hours=24)


@dataclass(frozen=True)
class PublishReadinessVerification:
    """Outcome of consuming a retained readiness decision at publication time."""

    status: str
    issues: list[str]


def evaluate_publish_readiness(
    *,
    report_id: str,
    artifacts: dict[str, Any],
    evidence_packs: dict[str, dict[str, Any]],
    validation_report: ValidationReport | None,
    final_html: str,
    final_html_path: str,
    category_ids: Iterable[object] = (),
    regeneration_attempts: Iterable[object] = (),
    artifact_hashes: dict[str, str] | None = None,
    configuration_hash: str = "",
    policy_hash: str = "",
    producer_revision: str = "",
    provenance: dict[str, str] | None = None,
    created_at: datetime | None = None,
) -> PublishReadinessArtifact:
    """Evaluate the one release policy over artifacts, final HTML and projection."""
    safe_artifacts = artifacts if isinstance(artifacts, dict) else {}
    safe_packs = evidence_packs if isinstance(evidence_packs, dict) else {}
    now = created_at or datetime.now(UTC)
    results: list[PublishReadinessRuleResult] = []
    results.append(_validation_result(validation_report))
    results.append(_category_result(safe_artifacts, category_ids, safe_packs))
    results.append(_material_evidence_result(safe_artifacts, safe_packs))
    results.append(_regeneration_result(regeneration_attempts))
    results.append(_figure_linkage_result(safe_artifacts, safe_packs, final_html))
    results.extend(
        _html_results(
            report_id=report_id,
            artifacts=safe_artifacts,
            final_html=final_html,
            final_html_path=final_html_path,
        )
    )
    results.append(_provenance_result(final_html, provenance or {}))
    results.sort(key=lambda item: item.rule_id)
    artifact = PublishReadinessArtifact(
        report_id=str(report_id),
        status="pass" if all(item.status == "pass" for item in results) else "fail",
        artifact_hashes={
            str(key): str(value)
            for key, value in sorted((artifact_hashes or {}).items())
            if str(key).strip() and str(value).strip()
        },
        rule_results=results,
        final_html_hash=_sha256(final_html),
        publication_projection_hash=publication_projection_hash(final_html),
        configuration_hash=_hash_or_sentinel(configuration_hash, "configuration"),
        policy_hash=_hash_or_sentinel(policy_hash, "policy"),
        producer_revision=str(producer_revision or "workspace"),
        created_at_utc=now.isoformat(),
        expires_at_utc=(now + _MAX_READINESS_AGE).isoformat(),
        staleness_conditions=[
            "final_html_hash_changed",
            "publication_projection_hash_changed",
            "artifact_hash_changed",
            "configuration_hash_changed",
            "policy_hash_changed",
            "producer_revision_changed",
            "expired",
        ],
        provenance={
            str(key): str(value) for key, value in sorted((provenance or {}).items())
        },
    )
    return replace(artifact, artifact_hash=_artifact_signature(artifact))


def publish_readiness_payload(artifact: PublishReadinessArtifact) -> dict[str, Any]:
    """Serialize the artifact without exposing rendered content in events."""
    return asdict(artifact)


def parse_publish_readiness_payload(payload: object) -> PublishReadinessArtifact:
    """Parse the persisted artifact strictly enough for fail-closed publication."""
    data = payload if isinstance(payload, dict) else {}
    raw_results = data.get("rule_results")
    malformed = not isinstance(payload, dict) or not isinstance(raw_results, list)
    results: list[PublishReadinessRuleResult] = []
    for item in raw_results if isinstance(raw_results, list) else []:
        if not isinstance(item, dict):
            malformed = True
            continue
        surfaces = item.get("surfaces")
        if not isinstance(surfaces, list) or any(
            not isinstance(surface, str) for surface in surfaces
        ):
            malformed = True
            continue
        results.append(
            PublishReadinessRuleResult(
                rule_id=str(item.get("rule_id") or ""),
                status=str(item.get("status") or "fail"),
                surfaces=[surface for surface in surfaces if surface],
                detail=str(item.get("detail") or ""),
                schema_version=str(
                    item.get("schema_version") or PUBLISH_READINESS_SCHEMA_VERSION
                ),
            )
        )
    return PublishReadinessArtifact(
        report_id=str(data.get("report_id") or ""),
        status=str(data.get("status") or "fail"),
        artifact_hashes={
            str(key): str(value)
            for key, value in (data.get("artifact_hashes") or {}).items()
            if str(key) and str(value)
        }
        if isinstance(data.get("artifact_hashes"), dict)
        else {},
        rule_results=results,
        final_html_hash=str(data.get("final_html_hash") or ""),
        publication_projection_hash=str(data.get("publication_projection_hash") or ""),
        configuration_hash=str(data.get("configuration_hash") or ""),
        policy_hash=str(data.get("policy_hash") or ""),
        producer_revision=str(data.get("producer_revision") or ""),
        created_at_utc=str(data.get("created_at_utc") or ""),
        expires_at_utc=str(data.get("expires_at_utc") or ""),
        staleness_conditions=[
            str(value) for value in data.get("staleness_conditions", []) if str(value)
        ]
        if isinstance(data.get("staleness_conditions"), list)
        else [],
        provenance={
            str(key): str(value)
            for key, value in (data.get("provenance") or {}).items()
        }
        if isinstance(data.get("provenance"), dict)
        else {},
        artifact_hash=str(data.get("artifact_hash") or ""),
        validator_version=str(data.get("validator_version") or ""),
        schema_version="" if malformed else str(data.get("schema_version") or ""),
    )


def verify_publish_readiness(
    *,
    artifact: PublishReadinessArtifact | None,
    report_id: str,
    final_html: str,
    configuration_hash: str = "",
    policy_hash: str = "",
    producer_revision: str = "",
    now: datetime | None = None,
) -> PublishReadinessVerification:
    """Verify the existing decision; intentionally never re-evaluates quality rules."""
    if artifact is None:
        return PublishReadinessVerification("missing", ["publish_readiness.missing"])
    issues: list[str] = []
    if artifact.schema_version != PUBLISH_READINESS_SCHEMA_VERSION:
        issues.append("publish_readiness.schema_unsupported")
    if artifact.validator_version != PUBLISH_READINESS_VALIDATOR_VERSION:
        issues.append("publish_readiness.validator_unsupported")
    if artifact.report_id != str(report_id):
        issues.append("publish_readiness.report_id_mismatch")
    if artifact.status != "pass":
        issues.append("publish_readiness.not_ready")
    if not artifact.artifact_hash or artifact.artifact_hash != _artifact_signature(
        artifact
    ):
        issues.append("publish_readiness.signature_invalid")
    if artifact.final_html_hash != _sha256(final_html):
        issues.append("publish_readiness.final_html_changed")
    if artifact.publication_projection_hash != publication_projection_hash(final_html):
        issues.append("publish_readiness.publication_projection_changed")
    if configuration_hash and artifact.configuration_hash != _hash_or_sentinel(
        configuration_hash, "configuration"
    ):
        issues.append("publish_readiness.configuration_changed")
    if policy_hash and artifact.policy_hash != _hash_or_sentinel(policy_hash, "policy"):
        issues.append("publish_readiness.policy_changed")
    if producer_revision and artifact.producer_revision != producer_revision:
        issues.append("publish_readiness.producer_revision_changed")
    expires = _parse_utc(artifact.expires_at_utc)
    if expires is None or expires <= (now or datetime.now(UTC)):
        issues.append("publish_readiness.expired")
    return PublishReadinessVerification(
        "pass" if not issues else "fail", sorted(issues)
    )


def verify_publication_projection(
    *, artifact: PublishReadinessArtifact | None, projected_body_html: str
) -> PublishReadinessVerification:
    """Verify the completed WordPress body without rerunning editorial rules."""
    if artifact is None:
        return PublishReadinessVerification("missing", ["publish_readiness.missing"])
    if artifact.publication_projection_hash != publication_projection_hash(
        projected_body_html
    ):
        return PublishReadinessVerification(
            "fail", ["publish_readiness.publication_projection_changed"]
        )
    return PublishReadinessVerification("pass", [])


def _validation_result(
    validation_report: ValidationReport | None,
) -> PublishReadinessRuleResult:
    if validation_report is None:
        return _fail(
            "publish_readiness.semantic_grounding",
            ["validation"],
            "validation report missing",
        )
    failed = [
        issue
        for issue in validation_report.issues
        if str(issue.severity).casefold() == "error"
        or str(issue.rule_id).casefold()
        in {"semantic", "grounding", "deferred_grounding_required"}
    ]
    if validation_report.status != "pass" or failed:
        return _fail(
            "publish_readiness.semantic_grounding",
            ["validation"],
            "semantic or grounding validation did not pass",
        )
    return _pass("publish_readiness.semantic_grounding", ["validation"])


def _category_result(
    artifacts: dict[str, Any],
    category_ids: Iterable[object],
    evidence_packs: dict[str, dict[str, Any]],
) -> PublishReadinessRuleResult:
    canonical = _normalized_strings(category_ids)
    artifact_values = _normalized_strings(
        artifacts.get("categories") or artifacts.get("category_decisions") or []
    )
    if not canonical:
        if _has_explicit_uncategorized_abstention(evidence_packs):
            return _pass(
                "publish_readiness.category_consistency",
                ["categories", "context_category_fit"],
            )
        return _fail(
            "publish_readiness.category_consistency",
            ["categories", "artifacts.category_decisions"],
            "canonical category assignment missing",
        )
    if not artifact_values:
        return _fail(
            "publish_readiness.category_consistency",
            ["categories", "artifacts.category_decisions"],
            "retained category assignment missing",
        )
    if artifact_values != canonical:
        return _fail(
            "publish_readiness.category_consistency",
            ["categories", "artifacts.category_decisions"],
            "rendered category decisions differ from retained category assignment",
        )
    return _pass("publish_readiness.category_consistency", ["categories"])


def _has_explicit_uncategorized_abstention(
    evidence_packs: dict[str, dict[str, Any]],
) -> bool:
    """Accept only the audited no-category outcome produced after bounded repair."""
    fit_payload = evidence_packs.get("context_category_fit")
    if not isinstance(fit_payload, dict):
        return False
    if _normalized_strings(fit_payload.get("selected_category_ids") or []):
        return False
    fits = _dict_items(fit_payload.get("category_fits"))
    return bool(fits) and all(
        str(item.get("decision") or "").casefold() == "reject"
        and str(item.get("semantic_rule_status") or "").casefold() == "rejected"
        and str(item.get("remediation_signal") or "")
        == "topic_semantics_unresolved_abstained"
        for item in fits
    )


def _material_evidence_result(
    artifacts: dict[str, Any], evidence_packs: dict[str, dict[str, Any]]
) -> PublishReadinessRuleResult:
    valid_ids = _evidence_ids(evidence_packs)
    missing: list[str] = []
    invalid: list[str] = []
    for family, item in _material_claim_items(artifacts):
        evidence_ids = _claim_evidence_ids(item)
        if evidence_ids is None:
            invalid.append(family)
            continue
        if not evidence_ids or any(
            evidence_id not in valid_ids for evidence_id in evidence_ids
        ):
            missing.append(family)
    if invalid:
        return _fail(
            "publish_readiness.material_claim_evidence",
            ["artifacts", "evidence_packs"],
            f"{len(invalid)} material claims have an invalid evidence reference shape",
        )
    if missing:
        return _fail(
            "publish_readiness.material_claim_evidence",
            ["artifacts", "evidence_packs"],
            f"{len(missing)} material claims lack a valid retained evidence reference",
        )
    return _pass(
        "publish_readiness.material_claim_evidence", ["artifacts", "evidence_packs"]
    )


def _regeneration_result(
    regeneration_attempts: Iterable[object],
) -> PublishReadinessRuleResult:
    attempts = list(regeneration_attempts or [])
    if not attempts:
        return _pass("publish_readiness.regeneration_promotion", ["regeneration"])
    last = attempts[-1]
    outcome = str(
        last.get("promotion_outcome")
        if isinstance(last, dict)
        else getattr(last, "promotion_outcome", "")
    ).casefold()
    if outcome != "promoted":
        return _fail(
            "publish_readiness.regeneration_promotion",
            ["regeneration"],
            "latest regenerated artifact was not promoted",
        )
    return _pass("publish_readiness.regeneration_promotion", ["regeneration"])


def _figure_linkage_result(
    artifacts: dict[str, Any], evidence_packs: dict[str, dict[str, Any]], html: str
) -> PublishReadinessRuleResult:
    cards = _dict_items(artifacts.get("chart_insight_cards"))
    public_cards = [
        card
        for card in cards
        if str(card.get("status") or "").casefold() not in _NON_PUBLIC_CARD_STATUSES
        and card.get("crop_qa_accepted") is True
    ]
    candidates = _accepted_candidates(evidence_packs)
    evidence_ids = _evidence_ids(evidence_packs)
    insight_ids = {
        str(item.get("id") or "").strip()
        for item in _dict_items(artifacts.get("insights_final"))
        if str(item.get("id") or "").strip()
    }
    incomplete = 0
    for card in public_cards:
        candidate_id = str(card.get("candidate_id") or "").strip()
        candidate = candidates.get(candidate_id)
        source_page = str(card.get("source_page") or "").strip()
        evidence_id = str(card.get("evidence_id") or "").strip()
        insight_id = str(card.get("insight_id") or "").strip()
        caption = str(card.get("caption") or card.get("retained_caption") or "").strip()
        takeaway = str(card.get("public_takeaway") or "").strip()
        candidate_page = (
            str(candidate.get("source_page") or candidate.get("page") or "").strip()
            if candidate
            else ""
        )
        candidate_evidence_id = (
            str(candidate.get("evidence_id") or "").strip() if candidate else ""
        )
        if (
            candidate is None
            or not source_page
            or not candidate_page
            or candidate_page != source_page
            or evidence_id not in evidence_ids
            or (candidate_evidence_id and candidate_evidence_id != evidence_id)
            or insight_id not in insight_ids
            or not caption
            or not takeaway
        ):
            incomplete += 1
    rendered_cards = _rendered_chart_cards(html)
    expected_takeaways = {
        str(card.get("public_takeaway") or "").strip() for card in public_cards
    }
    rendered_takeaways = {
        takeaway
        for takeaway in expected_takeaways
        if takeaway
        and any(takeaway in rendered_card for rendered_card in rendered_cards)
    }
    if (
        incomplete
        or len(rendered_cards) != len(public_cards)
        or rendered_takeaways != expected_takeaways
    ):
        return _fail(
            "publish_readiness.figure_linkage",
            ["artifacts.chart_insight_cards", "rendered.chart_cards"],
            (
                "public chart cards are unlinked, weak, or differ from the "
                "accepted-card projection"
            ),
        )
    return _pass(
        "publish_readiness.figure_linkage",
        ["artifacts.chart_insight_cards", "rendered.chart_cards"],
    )


def _html_results(
    *, report_id: str, artifacts: dict[str, Any], final_html: str, final_html_path: str
) -> list[PublishReadinessRuleResult]:
    quality = evaluate_public_editorial_quality(
        report_id=report_id,
        artifacts=artifacts,
        html=final_html,
        html_path=final_html_path,
    )
    editorial_result = _editorial_result(quality)
    document = BeautifulSoup(final_html, "html.parser")
    surfaces = _html_surfaces(document)
    joined = " ".join(value for _, value in surfaces)
    results = [editorial_result]
    if (
        _INTERNAL_TOKEN.search(joined)
        or _RAW_EVIDENCE_TOKEN.search(joined)
        or _PRIVATE_LOCATION.search(joined)
    ):
        results.append(
            _fail(
                "publish_readiness.public_identifier_leak",
                [name for name, _ in surfaces],
                "internal identifier or private location rendered",
            )
        )
    else:
        results.append(
            _pass(
                "publish_readiness.public_identifier_leak",
                [name for name, _ in surfaces],
            )
        )
    if _MECHANICAL.search(joined) or _ELLIPSIS.search(joined):
        results.append(
            _fail(
                "publish_readiness.rendered_scaffolding",
                [name for name, _ in surfaces],
                "mechanical scaffold or unresolved truncation rendered",
            )
        )
    else:
        results.append(
            _pass(
                "publish_readiness.rendered_scaffolding", [name for name, _ in surfaces]
            )
        )
    title_values = [
        value for name, value in surfaces if name in {"title", "h1", "heading"}
    ]
    if any(
        _FILENAME_TITLE.search(value) or _DUPLICATED_YEAR.search(value)
        for value in title_values
    ):
        results.append(
            _fail(
                "publish_readiness.public_title_quality",
                ["title", "heading"],
                "filename-style title or duplicated year rendered",
            )
        )
    else:
        results.append(
            _pass("publish_readiness.public_title_quality", ["title", "heading"])
        )
    if _has_repeated_boilerplate(surfaces):
        results.append(
            _fail(
                "publish_readiness.repeated_boilerplate",
                ["body", "caption", "quotation"],
                "substantial public sentence repeats",
            )
        )
    else:
        results.append(
            _pass(
                "publish_readiness.repeated_boilerplate",
                ["body", "caption", "quotation"],
            )
        )
    return results


def _provenance_result(
    html: str, provenance: dict[str, str]
) -> PublishReadinessRuleResult:
    document = BeautifulSoup(html, "html.parser")
    source = document.select_one("#source")
    source_links = source.select("a[href]") if source else []
    hrefs = [str(link.get("href") or "").strip() for link in source_links]
    safe_verified = {
        value.rstrip("/")
        for key, value in provenance.items()
        if key in {"publisher_landing_page_url", "original_report_url"}
        and _is_safe_public_url(value)
    }
    if any(
        not _is_safe_public_url(href) or href.rstrip("/") not in safe_verified
        for href in hrefs
    ):
        return _fail(
            "publish_readiness.public_source_provenance",
            ["source.links"],
            "public source link is not verified publisher provenance",
        )
    if not hrefs:
        safe_attribution = "Source URL: Not available"
        source_text = source.get_text(" ", strip=True) if source else ""
        if safe_verified or safe_attribution not in source_text:
            return _fail(
                "publish_readiness.public_source_provenance",
                ["source"],
                "missing safe attribution for unavailable publisher provenance",
            )
    return _pass(
        "publish_readiness.public_source_provenance", ["source", "source.links"]
    )


def _editorial_result(
    report: PublicEditorialQualityReport,
) -> PublishReadinessRuleResult:
    if report.status != "pass":
        return _fail(
            "publish_readiness.editorial_quality",
            ["artifacts", "rendered_html"],
            "canonical editorial rule failed",
        )
    return _pass("publish_readiness.editorial_quality", ["artifacts", "rendered_html"])


def _html_surfaces(document: BeautifulSoup) -> list[tuple[str, str]]:
    surfaces: list[tuple[str, str]] = []
    for tag_name in (
        "title",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "figcaption",
        "blockquote",
    ):
        for node in document.find_all(tag_name):
            surfaces.append(
                (
                    "heading" if tag_name.startswith("h") else tag_name,
                    node.get_text(" ", strip=True),
                )
            )
    body = (
        document.body.get_text(" ", strip=True)
        if document.body
        else document.get_text(" ", strip=True)
    )
    surfaces.append(("body", body))
    for node in document.select("a"):
        surfaces.append(("link_label", node.get_text(" ", strip=True)))
        surfaces.append(("link_href", str(node.get("href") or "")))
    for node in document.select("[alt]"):
        surfaces.append(("alt", str(node.get("alt") or "")))
    for node in document.select("meta, link[rel=canonical]"):
        name = str(node.get("name") or node.get("property") or node.get("rel") or "")
        value = str(node.get("content") or node.get("href") or "")
        surfaces.append(("metadata", " ".join(part for part in (name, value) if part)))
    for node in document.select('script[type="application/ld+json"]'):
        surfaces.append(("json_ld", node.get_text(" ", strip=True)))
    return [(name, value) for name, value in surfaces if value]


def _has_repeated_boilerplate(surfaces: list[tuple[str, str]]) -> bool:
    sentences: list[str] = []
    for name, text in surfaces:
        if name != "body":
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            normalized = " ".join(
                re.sub(r"[^a-z0-9]+", " ", sentence.casefold()).split()
            )
            if len(normalized) >= 48 and _looks_like_boilerplate(normalized):
                sentences.append(normalized)
    return any(count > 1 for count in _counts(sentences).values())


def _looks_like_boilerplate(sentence: str) -> bool:
    """Avoid treating deliberate evidence reuse as repeated generic copy."""
    return bool(
        re.search(
            r"\b(?:marketlense|marketbearing|source backed|decision relevance|"
            r"review this|this (?:report|source|briefing)|readers? can|"
            r"report can be evaluated)\b",
            sentence,
        )
    )


def _counts(items: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return counts


def _material_claim_items(
    artifacts: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    raw_summary = artifacts.get("summary")
    summary = raw_summary if isinstance(raw_summary, dict) else {}
    for item in _dict_items(summary.get("claim_evidence_map")):
        if str(item.get("claim") or "").strip():
            items.append(("summary.claim_evidence_map", item))
    for family in ("insights_final", "quotes_final", "chart_insight_cards"):
        for item in _dict_items(artifacts.get(family)):
            text = str(
                item.get("text") or item.get("claim") or item.get("caption") or ""
            ).strip()
            if text:
                items.append((family, item))
    for item in _dict_items(artifacts.get("claim_ledgers")):
        text = str(
            item.get("claim_text") or item.get("claim") or item.get("statement") or ""
        ).strip()
        if text:
            items.append(("claim_ledgers", item))
    return items


def _claim_evidence_ids(item: dict[str, Any]) -> set[str] | None:
    scalar = item.get("evidence_id")
    plural = item.get("evidence_ids", [])
    if scalar is not None and not isinstance(scalar, str):
        return None
    if not isinstance(plural, (list, tuple)) or any(
        not isinstance(value, str) or not value.strip() for value in plural
    ):
        return None
    values = [scalar, *plural]
    return {
        str(value).strip()
        for value in values
        if value is not None and str(value).strip()
    }


def _evidence_ids(value: object) -> set[str]:
    identifiers: set[str] = set()
    for item in _walk_dicts(value):
        for key in ("evidence_id", "id"):
            identifier = str(item.get(key) or "").strip()
            if identifier and (
                key == "evidence_id"
                or any(
                    name in item
                    for name in (
                        "snippet",
                        "evidence",
                        "text",
                        "citation",
                        "page",
                        "pages",
                    )
                )
            ):
                identifiers.add(identifier)
    return identifiers


def _accepted_candidates(
    evidence_packs: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for pack in evidence_packs.values():
        if not isinstance(pack, dict):
            continue
        for field_name in (
            "chart_candidates",
            "charts",
            "figures",
            "visual_candidates",
        ):
            for item in _dict_items(pack.get(field_name)):
                candidate_id = str(
                    item.get("candidate_id")
                    or item.get("chart_id")
                    or item.get("id")
                    or ""
                ).strip()
                accepted = (
                    item.get("accepted") is True or item.get("crop_qa_accepted") is True
                )
                if candidate_id and accepted:
                    candidates[candidate_id] = item
    return candidates


def _rendered_chart_cards(html: str) -> list[str]:
    document = BeautifulSoup(html, "html.parser")
    return [
        node.get_text(" ", strip=True)
        for node in document.select(".chart-insight-grid > article")
    ]


def _walk_dicts(value: object) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_dicts(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_dicts(nested)


def _dict_items(value: object) -> list[dict[str, Any]]:
    return (
        [item for item in value if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def _normalized_strings(values: object) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    normalized: set[str] = set()
    for value in values:
        if isinstance(value, dict):
            value = (
                value.get("category_id")
                or value.get("category")
                or value.get("id")
                or ""
            )
        token = str(value).strip()
        if token:
            normalized.add(token)
    return sorted(normalized)


def _is_safe_public_url(value: object) -> bool:
    parsed = urlsplit(str(value or "").strip())
    return bool(
        parsed.scheme in {"http", "https"}
        and parsed.netloc
        and not parsed.username
        and not parsed.password
        and parsed.hostname
        and parsed.hostname.casefold()
        not in {"drive.google.com", "localhost", "127.0.0.1", "::1"}
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_or_sentinel(value: str, namespace: str) -> str:
    normalized = str(value or "").strip()
    return (
        normalized
        if normalized
        else _sha256(f"publish-readiness:{namespace}:unavailable")
    )


def _artifact_signature(artifact: PublishReadinessArtifact) -> str:
    payload = asdict(replace(artifact, artifact_hash=""))
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _parse_utc(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _pass(rule_id: str, surfaces: list[str]) -> PublishReadinessRuleResult:
    return PublishReadinessRuleResult(rule_id=rule_id, status="pass", surfaces=surfaces)


def _fail(rule_id: str, surfaces: list[str], detail: str) -> PublishReadinessRuleResult:
    return PublishReadinessRuleResult(
        rule_id=rule_id, status="fail", surfaces=surfaces, detail=detail
    )


__all__ = [
    "PublishReadinessVerification",
    "evaluate_publish_readiness",
    "parse_publish_readiness_payload",
    "publish_readiness_payload",
    "verify_publish_readiness",
    "verify_publication_projection",
]
