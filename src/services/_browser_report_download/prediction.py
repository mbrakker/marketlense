from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlsplit

from src.contracts.browser_download import (
    BrowserReportDownloadRequest,
    PreBrowserDocTypePrediction,
)
from src.services._browser_report_download.request import (
    url_looks_like_direct_pdf,
    validate_and_normalize_url,
)

_PDF_QUERY_KEYS = (
    "asset",
    "asseturl",
    "download",
    "downloaddata",
    "downloadurl",
    "file",
    "fileurl",
    "pdf",
    "pdfurl",
    "redirect",
    "redirect_uri",
    "redirect_url",
    "target",
    "u",
    "url",
)
_REPORT_PAGE_MARKERS = (
    "benchmark",
    "ebook",
    "guide",
    "insight",
    "outlook",
    "playbook",
    "report",
    "research",
    "study",
    "survey",
    "trend",
    "whitepaper",
)


def predict_pre_browser_doc_type(
    *,
    request: BrowserReportDownloadRequest,
    normalized_url: str,
    normalized_execution_url: str,
) -> PreBrowserDocTypePrediction:
    route_family = str(request.route_family_hint or "").strip()
    candidate_pdf_url = _normalized_candidate_pdf_url(request)
    redirect_pdf_url = _extract_direct_pdf_target(normalized_execution_url)
    source_page_url = _normalized_source_page_url(request)
    planned_browser_route = route_family.startswith("browser_")

    if route_family == "direct_pdf_probe" and normalized_execution_url:
        return PreBrowserDocTypePrediction(
            schema_version="1.0",
            predicted_doc_type="direct_pdf",
            predicted_route_family="direct_pdf_probe",
            probe_url=normalized_execution_url,
            confidence_score=1.0,
            decision_reason="The orchestrator already selected the direct PDF probe route.",
            requires_browser=False,
            evidence_labels=["planned_direct_pdf_probe"],
        )

    if normalized_execution_url and url_looks_like_direct_pdf(normalized_execution_url):
        return PreBrowserDocTypePrediction(
            schema_version="1.0",
            predicted_doc_type="direct_pdf",
            predicted_route_family="direct_pdf_probe",
            probe_url=normalized_execution_url,
            confidence_score=0.99,
            decision_reason="The execution URL path already ends with .pdf, so verify it before browser startup.",
            requires_browser=False,
            evidence_labels=["execution_url_pdf_suffix"],
        )

    if redirect_pdf_url:
        return PreBrowserDocTypePrediction(
            schema_version="1.0",
            predicted_doc_type="direct_pdf",
            predicted_route_family="direct_pdf_probe",
            probe_url=redirect_pdf_url,
            confidence_score=0.95,
            decision_reason="The execution URL exposes an embedded redirect/query target that already resolves to a PDF URL.",
            requires_browser=False,
            evidence_labels=["embedded_pdf_target", "query_redirect_pdf"],
        )

    if candidate_pdf_url and not planned_browser_route:
        confidence_score = 0.93 if route_family.startswith("browser_") else 0.9
        decision_reason = "Discovery already supplied a candidate PDF URL, so verify that target before browser startup."
        evidence_labels = ["candidate_trace_pdf_url"]
        if source_page_url and source_page_url != candidate_pdf_url:
            evidence_labels.append("source_page_context")
        return PreBrowserDocTypePrediction(
            schema_version="1.0",
            predicted_doc_type="direct_pdf",
            predicted_route_family="direct_pdf_probe",
            probe_url=candidate_pdf_url,
            confidence_score=confidence_score,
            decision_reason=decision_reason,
            requires_browser=False,
            evidence_labels=evidence_labels,
        )

    if _looks_like_report_page_context(
        normalized_execution_url=normalized_execution_url,
        request=request,
    ):
        return PreBrowserDocTypePrediction(
            schema_version="1.0",
            predicted_doc_type="report_page_pdf_link",
            predicted_route_family="report_page_pdf_link_probe",
            probe_url=normalized_execution_url or normalized_url,
            confidence_score=0.62,
            decision_reason="The URL and candidate metadata look like a report detail page, so inspect lightweight HTML for embedded PDF links before browser startup.",
            requires_browser=False,
            evidence_labels=["report_detail_markers"],
        )

    return PreBrowserDocTypePrediction(
        schema_version="1.0",
        predicted_doc_type="browser_required",
        predicted_route_family=route_family or "browser_pdf_click",
        probe_url=normalized_execution_url or normalized_url,
        confidence_score=0.2,
        decision_reason="No deterministic direct-PDF signals were found, so keep the browser route as the fallback path.",
        requires_browser=True,
        evidence_labels=["browser_fallback"],
    )


def _normalized_candidate_pdf_url(request: BrowserReportDownloadRequest) -> str:
    candidate_pdf_url = str(
        request.candidate_trace.pdf_url if request.candidate_trace is not None else ""
    ).strip()
    if not candidate_pdf_url:
        return ""
    return validate_and_normalize_url(candidate_pdf_url)


def _normalized_source_page_url(request: BrowserReportDownloadRequest) -> str:
    source_page_url = str(request.source_page_url_hint or "").strip()
    if not source_page_url:
        return ""
    return validate_and_normalize_url(source_page_url)


def _extract_direct_pdf_target(url: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    if not parsed.query:
        return ""
    query = parse_qs(parsed.query, keep_blank_values=False)
    for key in _PDF_QUERY_KEYS:
        values = query.get(key)
        if not values:
            continue
        for value in values:
            candidate = validate_and_normalize_url(unquote(str(value or "").strip()))
            if candidate and url_looks_like_direct_pdf(candidate):
                return candidate
    return ""


def _looks_like_report_page_context(
    *,
    normalized_execution_url: str,
    request: BrowserReportDownloadRequest,
) -> bool:
    if not normalized_execution_url:
        return False
    parsed = urlsplit(normalized_execution_url)
    path = str(parsed.path or "").strip().lower()
    if not path or path.endswith(".pdf"):
        return False
    context_parts = [
        path,
        str(request.url or ""),
        str(request.attempt_url or ""),
        str(request.route_family_hint or ""),
    ]
    if request.candidate_trace is not None:
        context_parts.append(str(request.candidate_trace.title or ""))
    context = " ".join(context_parts).casefold()
    if not any(marker in context for marker in _REPORT_PAGE_MARKERS):
        return False
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) < 2:
        return False
    slug_token_count = len([token for token in segments[-1].split("-") if token])
    return slug_token_count >= 2
