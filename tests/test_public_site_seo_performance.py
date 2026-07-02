from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from scripts.quality.public_site_seo_performance import (
    _metadata_from_html,
    inspect_site,
)


HTML = """<!doctype html>
<html>
<head>
  <title>Market Bearing</title>
  <meta name="description" content="Governed market research.">
  <link rel="canonical" href="http://127.0.0.1/">
  <meta property="og:title" content="Market Bearing">
  <meta property="og:description" content="Governed market research.">
  <meta property="og:url" content="http://127.0.0.1/">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="Market Bearing">
  <meta name="twitter:description" content="Governed market research.">
</head>
<body><main>Public site</main></body>
</html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        del self.path
        body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002
        del format, args


def test_metadata_extraction_requires_seo_and_social_tags() -> None:
    metadata = _metadata_from_html(HTML)

    assert metadata["meta.description"] == "Governed market research."
    assert metadata["link.canonical"] == "http://127.0.0.1/"
    assert metadata["og.title"] == "Market Bearing"
    assert metadata["twitter.card"] == "summary"


def test_public_site_checker_records_metadata_and_performance_metrics() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/"
        report = inspect_site(
            base_url=base_url,
            paths=["/"],
            baseline={
                "required_metadata": [
                    "meta.description",
                    "link.canonical",
                    "og.title",
                    "og.description",
                    "og.url",
                    "twitter.card",
                    "twitter.title",
                    "twitter.description",
                ],
                "baseline": {
                    "response_start_ms": 5000,
                    "dom_complete_ms": 5000,
                    "request_count": 5,
                    "page_weight_bytes": 100000,
                },
            },
            timeout_seconds=5,
        )
    finally:
        server.shutdown()
        server.server_close()

    assert report.passed is True
    assert report.pages[0].status_code == 200
    assert report.pages[0].response_start_ms >= 0
    assert report.pages[0].dom_complete_ms >= report.pages[0].response_start_ms
    assert report.pages[0].request_count == 1
    assert report.pages[0].missing_metadata == []
