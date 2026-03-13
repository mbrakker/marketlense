from __future__ import annotations

from src.generators.evidence_packs.base import (
    EvidencePackStrategy,
    PackNormalizationResult,
)
from src.generators.evidence_packs.common import (
    build_section_id,
    coerce_pages,
    coerce_text_list,
    derive_publisher_from_document_title,
    derive_publisher_from_report_name,
    first_non_empty_text,
    text,
    to_dict,
)


def build_empty_payload(reason: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "not_found_reason": reason,
        "doc_id": "",
        "title": "",
        "summary": "",
        "publisher": "",
        "sections": [],
    }


def summarize_payload(payload: dict[str, object]) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {
            "has_content": False,
            "sections_count": 0,
            "title_present": False,
            "doc_id_present": False,
            "summary_present": False,
            "not_found_reason": "invalid_payload",
        }
    title = str(payload.get("title") or "").strip()
    doc_id = str(payload.get("doc_id") or "").strip()
    summary_text = str(payload.get("summary") or "").strip()
    sections = payload.get("sections")
    sections_count = len(sections) if isinstance(sections, list) else 0
    not_found_reason = str(payload.get("not_found_reason") or "").strip()
    has_substantive_content = bool(title or summary_text or sections_count)
    return {
        "has_content": has_substantive_content,
        "sections_count": sections_count,
        "title_present": bool(title),
        "doc_id_present": bool(doc_id),
        "summary_present": bool(summary_text),
        "not_found_reason": not_found_reason,
    }


def summarize_completeness(payload: dict[str, object]) -> dict[str, object]:
    sections = payload.get("sections") if isinstance(payload, dict) else []
    if not isinstance(sections, list):
        sections = []
    sections_count = 0
    sections_with_summary = 0
    sections_with_key_points = 0
    for section in sections:
        if not isinstance(section, dict):
            continue
        sections_count += 1
        if text(section.get("summary")):
            sections_with_summary += 1
        if coerce_text_list(section.get("key_points")):
            sections_with_key_points += 1
    sections_missing_summary = max(0, sections_count - sections_with_summary)
    summary_coverage_ratio = (
        round(sections_with_summary / sections_count, 4) if sections_count else 0.0
    )
    key_points_coverage_ratio = (
        round(sections_with_key_points / sections_count, 4) if sections_count else 0.0
    )
    return {
        "sections_count": sections_count,
        "sections_with_summary": sections_with_summary,
        "sections_missing_summary": sections_missing_summary,
        "summary_coverage_ratio": summary_coverage_ratio,
        "sections_with_key_points": sections_with_key_points,
        "key_points_coverage_ratio": key_points_coverage_ratio,
        "warn": sections_count > 0 and sections_missing_summary > 0,
    }


def normalize_payload(
    payload: object, report_id: str, report_name: str
) -> PackNormalizationResult:
    if not isinstance(payload, dict):
        return PackNormalizationResult(
            payload=build_empty_payload(""),
            changed=False,
            metadata={
                "wrapper_key": "",
                "sections_with_ids": 0,
                "added_section_ids": 0,
                "dropped_sections": 0,
                "doc_id_filled": False,
            },
        )
    wrapper_key = ""
    candidate = payload
    for key in ("docmap", "doc_map", "docMap"):
        wrapped = payload.get(key)
        if isinstance(wrapped, dict):
            wrapper_key = key
            candidate = wrapped
            break
    normalized = dict(candidate) if isinstance(candidate, dict) else {}
    changed = bool(wrapper_key)
    cache_meta = (
        payload.get("_cache") if isinstance(payload.get("_cache"), dict) else None
    )
    if cache_meta:
        normalized["_cache"] = cache_meta
    doc_meta = to_dict(normalized.get("document"))

    raw_title = normalized.get("title")
    resolved_title = first_non_empty_text(
        text(raw_title),
        normalized.get("report_title"),
        normalized.get("document_title"),
        normalized.get("document_name"),
        normalized.get("name"),
        doc_meta.get("title"),
        doc_meta.get("name"),
    )
    if raw_title != resolved_title or "title" not in normalized:
        normalized["title"] = resolved_title
        changed = True

    raw_publisher = normalized.get("publisher")
    resolved_publisher = first_non_empty_text(
        text(raw_publisher),
        normalized.get("document_publisher"),
        normalized.get("document_organization"),
        normalized.get("document_organisation"),
        normalized.get("organization"),
        normalized.get("organisation"),
        normalized.get("publisher_name"),
        doc_meta.get("publisher"),
        doc_meta.get("organization"),
        doc_meta.get("organisation"),
        derive_publisher_from_document_title(
            first_non_empty_text(
                normalized.get("document_title"),
                normalized.get("title"),
                normalized.get("report_title"),
                doc_meta.get("title"),
            )
        ),
        derive_publisher_from_report_name(report_name),
    )
    if raw_publisher != resolved_publisher or "publisher" not in normalized:
        normalized["publisher"] = resolved_publisher
        changed = True

    raw_summary = normalized.get("summary")
    resolved_summary = first_non_empty_text(
        text(raw_summary),
        normalized.get("document_summary"),
        normalized.get("document_brief"),
        normalized.get("document_overview"),
        normalized.get("document_abstract"),
        normalized.get("document_description"),
        normalized.get("brief"),
        normalized.get("overview"),
        normalized.get("abstract"),
        normalized.get("description"),
        doc_meta.get("summary"),
        doc_meta.get("brief"),
        doc_meta.get("overview"),
        doc_meta.get("abstract"),
        doc_meta.get("description"),
    )
    if raw_summary != resolved_summary or "summary" not in normalized:
        normalized["summary"] = resolved_summary
        changed = True

    doc_id = text(normalized.get("doc_id"))
    doc_id_filled = False
    if not doc_id:
        normalized["doc_id"] = report_id
        doc_id_filled = True
        changed = True
    elif normalized.get("doc_id") != doc_id:
        normalized["doc_id"] = doc_id
        changed = True

    sections = normalized.get("sections")
    if not isinstance(sections, list):
        structure = normalized.get("structure")
        if isinstance(structure, list):
            normalized["sections"] = structure
            sections = normalized["sections"]
            changed = True
        else:
            normalized["sections"] = []
            sections = normalized["sections"]
            changed = True

    sections_with_ids = 0
    added_section_ids = 0
    dropped_sections = 0
    if isinstance(sections, list):
        updated_sections: list[dict[str, object]] = []
        for idx, section in enumerate(sections):
            if not isinstance(section, dict):
                dropped_sections += 1
                continue
            sec = dict(section)
            sec_title = first_non_empty_text(
                sec.get("title"),
                sec.get("heading"),
                sec.get("name"),
                sec.get("section"),
                sec.get("label"),
            )
            if not sec_title:
                sec_title = f"Section {idx + 1}"
            if text(sec.get("title")) != sec_title:
                sec["title"] = sec_title
                changed = True

            sec_id = str(sec.get("id") or "").strip()
            if not sec_id:
                sec_id = build_section_id(sec_title, index=idx + 1)
                sec["id"] = sec_id
                added_section_ids += 1
                changed = True

            raw_sec_summary = sec.get("summary")
            resolved_sec_summary = first_non_empty_text(
                text(raw_sec_summary),
                sec.get("brief"),
                sec.get("overview"),
                sec.get("abstract"),
                sec.get("description"),
                sec.get("text"),
                sec.get("finding"),
            )
            if raw_sec_summary != resolved_sec_summary or "summary" not in sec:
                sec["summary"] = resolved_sec_summary
                changed = True

            raw_key_points = sec.get("key_points")
            resolved_key_points = coerce_text_list(raw_key_points)
            if not resolved_key_points:
                resolved_key_points = coerce_text_list(sec.get("keyPoints"))
            if not resolved_key_points:
                resolved_key_points = coerce_text_list(sec.get("highlights"))
            if not resolved_key_points:
                resolved_key_points = coerce_text_list(sec.get("bullets"))
            if not resolved_key_points:
                resolved_key_points = coerce_text_list(sec.get("points"))
            if not resolved_key_points:
                resolved_key_points = coerce_text_list(sec.get("key_findings"))
            if raw_key_points != resolved_key_points or "key_points" not in sec:
                sec["key_points"] = resolved_key_points
                changed = True

            raw_pages = sec.get("pages")
            resolved_pages = coerce_pages(raw_pages) or coerce_pages(sec.get("page"))
            if raw_pages != resolved_pages or ("pages" not in sec and resolved_pages):
                sec["pages"] = resolved_pages
                changed = True

            raw_refs = sec.get("references")
            refs = raw_refs if isinstance(raw_refs, list) else []
            normalized_refs = [text(ref) for ref in refs if text(ref)]
            if not normalized_refs:
                source_ref = text(sec.get("source"))
                if source_ref:
                    normalized_refs = [source_ref]
            if raw_refs != normalized_refs or (
                "references" not in sec and normalized_refs
            ):
                sec["references"] = normalized_refs
                changed = True

            sections_with_ids += 1 if sec.get("id") else 0
            updated_sections.append(sec)
        normalized["sections"] = updated_sections
        if dropped_sections > 0:
            changed = True

    return PackNormalizationResult(
        payload=normalized,
        changed=changed,
        metadata={
            "wrapper_key": wrapper_key,
            "sections_with_ids": sections_with_ids,
            "added_section_ids": added_section_ids,
            "dropped_sections": dropped_sections,
            "doc_id_filled": doc_id_filled,
        },
    )


DOC_MAP_STRATEGY = EvidencePackStrategy(
    pack_name="doc_map",
    prompt_namespace_suffix="doc_map",
    schema_name="doc_map",
    normalize_payload=normalize_payload,
    empty_payload=build_empty_payload,
)
