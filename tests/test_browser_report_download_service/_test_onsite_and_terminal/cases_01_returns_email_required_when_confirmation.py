# ruff: noqa: F401,F403,F405
from __future__ import annotations

import json
from io import BytesIO

import fitz
from PIL import Image

from src.contracts.http_acquisition import HttpAcquisitionResponse
from src.services._browser_report_download._http.adobe_indesign import (
    _adobe_indesign_pages,
    _extract_embedded_adobe_indesign_publication,
    _render_adobe_indesign_capture_html,
    try_embedded_adobe_indesign_capture,
)
from src.services._browser_report_download._http.issuu import (
    try_embedded_issuu_capture,
)
from src.services._browser_report_download._http.onsite_capture import (
    _html_for_pdf_rendering,
    _should_try_direct_onsite_capture,
    try_direct_onsite_capture,
)

from ._shared import *  # noqa: F401,F403


def test_embedded_issuu_capture_builds_complete_rendered_pdf(
    tmp_path: Path,
    run_context,
) -> None:
    revision_id = "260511211811"
    publication_id = "4ffef46b07ef26cee53bfbec364bcae3"

    def jpeg_bytes(color: tuple[int, int, int]) -> bytes:
        image = Image.new("RGB", (48, 64), color)
        stream = BytesIO()
        image.save(stream, format="JPEG")
        return stream.getvalue()

    def execute(*, request, ctx, requests_module):
        if request.purpose.endswith("document"):
            body = json.dumps(
                {
                    "revisionId": revision_id,
                    "publicationId": publication_id,
                    "pageCount": 2,
                }
            )
            return HttpAcquisitionResponse(
                schema_version="1.0",
                purpose=request.purpose,
                method=request.method,
                request_url=request.url,
                final_url=request.url,
                status_code=200,
                headers={"content-type": "text/html"},
                content_type="text/html",
                text_body=body,
            )
        page_number = 1 if request.url.endswith("page_1.jpg") else 2
        return HttpAcquisitionResponse(
            schema_version="1.0",
            purpose=request.purpose,
            method=request.method,
            request_url=request.url,
            final_url=request.url,
            status_code=200,
            headers={"content-type": "image/jpeg"},
            content_type="image/jpeg",
            body_bytes=jpeg_bytes((page_number * 40, 20, 30)),
        )

    result = try_embedded_issuu_capture(
        request=BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://publisher.example/reports/report",
            settings=_settings(tmp_path),
        ),
        ctx=run_context,
        normalized_url="https://publisher.example/reports/report",
        download_dir=tmp_path,
        source_page_url="https://publisher.example/reports/report-pdf/",
        source_page_html=(
            '<iframe src="https://e.issuu.com/embed.html?'
            'd=report-2026&amp;u=publisher"></iframe>'
        ),
        http_acquisition_executor=execute,
    )

    assert result is not None
    assert result.outcome == "captured"
    assert result.onsite_capture_format == "rendered_onsite_pdf"
    assert result.onsite_page_count == 2
    with fitz.open(result.onsite_capture_path) as document:
        assert document.page_count == 2


def test_direct_onsite_capture_follows_public_form_redirect_to_issuu(
    tmp_path: Path,
    run_context,
) -> None:
    source_url = "https://publisher.example/reports/benchmark-report-2026"
    redirect_url = "https://publisher.example/reports/benchmark-report-2026-pdf/"
    revision_id = "260511211811"
    publication_id = "4ffef46b07ef26cee53bfbec364bcae3"

    def jpeg_bytes() -> bytes:
        image = Image.new("RGB", (48, 64), (40, 20, 30))
        stream = BytesIO()
        image.save(stream, format="JPEG")
        return stream.getvalue()

    def response(*, request, body: str = "", image: bytes | None = None):
        return HttpAcquisitionResponse(
            schema_version="1.0",
            purpose=request.purpose,
            method=request.method,
            request_url=request.url,
            final_url=request.url,
            status_code=200,
            headers={"content-type": "image/jpeg" if image else "text/html"},
            content_type="image/jpeg" if image else "text/html",
            text_body=body or None,
            body_bytes=image,
        )

    def execute(*, request, ctx, requests_module):
        if request.url == source_url:
            return response(
                request=request,
                body=(
                    "<html><title>Benchmark Report</title><form "
                    'data-redirect="/reports/benchmark-report-2026-pdf/">'
                    "<input name='email'></form></html>"
                ),
            )
        if request.url == redirect_url:
            return response(
                request=request,
                body=(
                    '<iframe src="https://e.issuu.com/embed.html?'
                    'd=benchmark-report-2026&amp;u=publisher"></iframe>'
                ),
            )
        if request.purpose.endswith("document"):
            return response(
                request=request,
                body=json.dumps(
                    {
                        "revisionId": revision_id,
                        "publicationId": publication_id,
                        "pageCount": 2,
                    }
                ),
            )
        return response(request=request, image=jpeg_bytes())

    result = try_direct_onsite_capture(
        request=BrowserReportDownloadRequest(
            schema_version="1.0",
            url=source_url,
            route_family_hint="browser_email_form",
            settings=_settings(tmp_path),
        ),
        ctx=run_context,
        normalized_url=source_url,
        download_dir=tmp_path,
        http_acquisition_executor=execute,
    )

    assert result is not None
    assert result.outcome == "captured"
    assert result.onsite_page_count == 2


def test_direct_onsite_capture_captures_issuu_embedded_on_source_page(
    tmp_path: Path,
    run_context,
) -> None:
    source_url = "https://publisher.example/reports/public-embedded-report"
    revision_id = "260511211811"
    publication_id = "4ffef46b07ef26cee53bfbec364bcae3"

    def jpeg_bytes() -> bytes:
        image = Image.new("RGB", (48, 64), (40, 20, 30))
        stream = BytesIO()
        image.save(stream, format="JPEG")
        return stream.getvalue()

    def response(*, request, body: str = "", image: bytes | None = None):
        return HttpAcquisitionResponse(
            schema_version="1.0",
            purpose=request.purpose,
            method=request.method,
            request_url=request.url,
            final_url=request.url,
            status_code=200,
            headers={"content-type": "image/jpeg" if image else "text/html"},
            content_type="image/jpeg" if image else "text/html",
            text_body=body or None,
            body_bytes=image,
        )

    def execute(*, request, ctx, requests_module):
        if request.url == source_url:
            return response(
                request=request,
                body=(
                    '<iframe src="https://e.issuu.com/embed.html?'
                    'd=public-embedded-report&amp;u=publisher"></iframe>'
                ),
            )
        if request.purpose.endswith("document"):
            return response(
                request=request,
                body=json.dumps(
                    {
                        "revisionId": revision_id,
                        "publicationId": publication_id,
                        "pageCount": 2,
                    }
                ),
            )
        return response(request=request, image=jpeg_bytes())

    result = try_direct_onsite_capture(
        request=BrowserReportDownloadRequest(
            schema_version="1.0",
            url=source_url,
            route_family_hint="browser_email_form",
            settings=_settings(tmp_path),
        ),
        ctx=run_context,
        normalized_url=source_url,
        download_dir=tmp_path,
        http_acquisition_executor=execute,
    )

    assert result is not None
    assert result.outcome == "captured"
    assert result.onsite_capture_format == "rendered_onsite_pdf"
    assert result.onsite_page_count == 2


def test_html_for_pdf_rendering_removes_external_assets_but_keeps_report_text() -> None:
    rendered = _html_for_pdf_rendering(
        "<html><head><link rel='stylesheet' href='https://cdn.example/style.css'>"
        "<style>@media print { body { color: black; } }</style></head>"
        "<body><article><h1>Report title</h1><p>Report findings.</p>"
        "<img src='https://cdn.example/chart.png'><iframe src='https://example.com/embed'></iframe>"
        "</article></body></html>"
    )

    assert "Report findings." in rendered
    assert "stylesheet" not in rendered
    assert "chart.png" not in rendered
    assert "iframe" not in rendered


def test_extract_embedded_adobe_indesign_publication_requires_public_view_url() -> None:
    publication = _extract_embedded_adobe_indesign_publication(
        """
        <iframe
          src="https://indd.adobe.com/view/9d9a68f6-38a9-4278-b61c-4506b24240b0?allowFullscreen=true"
        ></iframe>
        """
    )

    assert publication == "9d9a68f6-38a9-4278-b61c-4506b24240b0"
    assert (
        _extract_embedded_adobe_indesign_publication(
            '<iframe src="https://example.com/view/9d9a68f6-38a9-4278-b61c-4506b24240b0"></iframe>'
        )
        is None
    )
    assert (
        _extract_embedded_adobe_indesign_publication(
            '<a href="https://indd.adobe.com/view/9d9a68f6-38a9-4278-b61c-4506b24240b0">Report</a>'
        )
        is None
    )
    assert (
        _extract_embedded_adobe_indesign_publication(
            '<script>"https://indd.adobe.com/view/9d9a68f6-38a9-4278-b61c-4506b24240b0"</script>'
        )
        is None
    )


def test_adobe_indesign_capture_html_preserves_published_page_text() -> None:
    pages = _adobe_indesign_pages(
        json.dumps(
            {
                "framesData": [
                    {
                        "pageNo": 1,
                        "frameData": [
                            {
                                "textBoundary": [
                                    [["DIGITAL 2025", [0, 12]]],
                                    [["GLOBAL OVERVIEW REPORT", [0, 24]]],
                                ]
                            }
                        ],
                    },
                    {
                        "pageNo": 2,
                        "frameData": [
                            {"textBoundary": [[["Published report findings", [0, 12]]]]}
                        ],
                    },
                ]
            }
        )
    )

    capture_html = _render_adobe_indesign_capture_html(pages)

    assert pages == [
        (1, ["DIGITAL 2025 GLOBAL OVERVIEW REPORT"]),
        (2, ["Published report findings"]),
    ]
    assert 'data-page-number="1"' in capture_html
    assert "Published report findings" in capture_html


def test_adobe_indesign_capture_counts_distinct_published_pages() -> None:
    pages = _adobe_indesign_pages(
        json.dumps(
            {
                "framesData": [
                    {
                        "pageNo": 1,
                        "frameData": [{"textBoundary": [["first frame"]]}],
                    },
                    {
                        "pageNo": 1,
                        "frameData": [{"textBoundary": [["second frame"]]}],
                    },
                ]
            }
        )
    )

    assert pages == [(1, ["first frame second frame"])]


def test_embedded_adobe_indesign_capture_requires_complete_public_content(
    tmp_path: Path,
    run_context,
) -> None:
    publication_id = "9d9a68f6-38a9-4278-b61c-4506b24240b0"
    content = json.dumps(
        {
            "framesData": [
                {
                    "pageNo": page_number,
                    "frameData": [{"textBoundary": [["Verified report text " * 80]]}],
                }
                for page_number in (1, 2)
            ]
        }
    )

    def execute(*, request, ctx, requests_module):
        body = (
            '"VERSION_PREFIX":"cukv"' if request.purpose.endswith("viewer") else content
        )
        return HttpAcquisitionResponse(
            schema_version="1.0",
            purpose=request.purpose,
            method=request.method,
            request_url=request.url,
            final_url=request.url,
            status_code=200,
            headers={"content-type": "application/json"},
            content_type="application/json",
            text_body=body,
        )

    result = try_embedded_adobe_indesign_capture(
        request=BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://publisher.example/report",
            settings=_settings(tmp_path),
        ),
        ctx=run_context,
        normalized_url="https://publisher.example/report",
        download_dir=tmp_path,
        source_page_url="https://publisher.example/report",
        source_page_html=(
            f'<iframe src="https://indd.adobe.com/view/{publication_id}"></iframe>'
        ),
        http_acquisition_executor=execute,
    )

    assert result is not None
    assert result.outcome == "captured"
    assert result.onsite_page_count == 2
    assert (tmp_path / "adobe_indesign_capture.html").is_file()
    assert (tmp_path / "adobe_indesign_content.json").is_file()


def test_report_detail_without_route_hint_is_eligible_for_public_embed_capture(
    tmp_path: Path,
) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://publisher.example/reports/digital-overview-report",
        settings=_settings(tmp_path),
    )

    assert _should_try_direct_onsite_capture(request) is True


def test_direct_onsite_capture_renders_public_detail_without_candidate_trace(
    tmp_path: Path,
    run_context,
) -> None:
    """A specific public longread need not require discovery metadata or an Agent."""
    source_url = (
        "https://publisher.example/our-insights/three-point-perspective/"
        "equity-issuance-whats-driving-this-wave"
    )

    def execute(*, request, ctx, requests_module):
        return HttpAcquisitionResponse(
            schema_version="1.0",
            purpose=request.purpose,
            method=request.method,
            request_url=request.url,
            final_url=source_url,
            status_code=200,
            headers={"content-type": "text/html"},
            content_type="text/html",
            text_body=(
                "<html><title>Equity issuance insight</title>"
                "<noscript>Please enable JavaScript to use this site.</noscript>"
                "<body><article>"
                "<h1>The return of equity issuance</h1><p>"
                + ("Public market analysis and report findings. " * 120)
                + "</p></article></body></html>"
            ),
        )

    result = try_direct_onsite_capture(
        request=BrowserReportDownloadRequest(
            schema_version="1.0",
            url=source_url,
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
            route_kind_hint="onsite_report",
        ),
        ctx=run_context,
        normalized_url=source_url,
        download_dir=tmp_path,
        http_acquisition_executor=execute,
    )

    assert result is not None
    assert result.outcome == "captured"
    assert result.onsite_capture_format == "rendered_onsite_pdf"
    assert Path(str(result.onsite_capture_path)).read_bytes().startswith(b"%PDF")


def test_direct_onsite_capture_does_not_choose_an_ambiguous_listing_hub(
    tmp_path: Path,
    run_context,
) -> None:
    source_url = "https://publisher.example/research.html"

    def unexpected_execute(**kwargs):
        raise AssertionError(
            "A generic listing hub must not be fetched as an on-site report"
        )

    result = try_direct_onsite_capture(
        request=BrowserReportDownloadRequest(
            schema_version="1.0",
            url=source_url,
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
            route_kind_hint="onsite_report",
        ),
        ctx=run_context,
        normalized_url=source_url,
        download_dir=tmp_path,
        http_acquisition_executor=unexpected_execute,
    )

    assert result is None


def test_direct_onsite_capture_rejects_a_short_javascript_interstitial(
    tmp_path: Path,
    run_context,
) -> None:
    source_url = "https://publisher.example/insights/detail-report"

    def execute(*, request, ctx, requests_module):
        return HttpAcquisitionResponse(
            schema_version="1.0",
            purpose=request.purpose,
            method=request.method,
            request_url=request.url,
            final_url=source_url,
            status_code=200,
            headers={"content-type": "text/html"},
            content_type="text/html",
            text_body=(
                "<html><body>Please enable JavaScript to continue. "
                "This page cannot be displayed.</body></html>"
            ),
        )

    result = try_direct_onsite_capture(
        request=BrowserReportDownloadRequest(
            schema_version="1.0",
            url=source_url,
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
            route_kind_hint="onsite_report",
        ),
        ctx=run_context,
        normalized_url=source_url,
        download_dir=tmp_path,
        http_acquisition_executor=execute,
    )

    assert result is None


def test_unhinted_report_detail_falls_back_when_public_embed_is_unverified(
    tmp_path: Path,
    run_context,
) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://publisher.example/reports/digital-overview-report",
        settings=_settings(tmp_path),
    )

    def execute(*, request, ctx, requests_module):
        return HttpAcquisitionResponse(
            schema_version="1.0",
            purpose=request.purpose,
            method=request.method,
            request_url=request.url,
            final_url=request.url,
            status_code=200,
            headers={"content-type": "text/html"},
            content_type="text/html",
            text_body=(
                "<html><title>Report</title><article>"
                f"{'report findings ' * 100}</article></html>"
            ),
        )

    result = try_direct_onsite_capture(
        request=request,
        ctx=run_context,
        normalized_url=request.url,
        download_dir=tmp_path,
        http_acquisition_executor=execute,
    )

    assert result is None


__all__ = [
    "test_html_for_pdf_rendering_removes_external_assets_but_keeps_report_text",
    "test_adobe_indesign_capture_counts_distinct_published_pages",
    "test_embedded_adobe_indesign_capture_requires_complete_public_content",
    "test_extract_embedded_adobe_indesign_publication_requires_public_view_url",
    "test_report_detail_without_route_hint_is_eligible_for_public_embed_capture",
    "test_direct_onsite_capture_renders_public_detail_without_candidate_trace",
    "test_direct_onsite_capture_does_not_choose_an_ambiguous_listing_hub",
    "test_direct_onsite_capture_rejects_a_short_javascript_interstitial",
    "test_unhinted_report_detail_falls_back_when_public_embed_is_unverified",
    "test_adobe_indesign_capture_html_preserves_published_page_text",
]
