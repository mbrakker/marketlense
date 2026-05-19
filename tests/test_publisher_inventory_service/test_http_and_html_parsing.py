from __future__ import annotations

from .builders import *  # noqa: F401,F403


def test_discover_publisher_inventory_http_parse_handles_multipage(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    html_page_1 = """
    <html><body>
      <a href="/reports/report-one">Report One 2026</a>
      <a href="/insights?page=2" rel="next">Next</a>
    </body></html>
    """
    html_page_2 = """
    <html><body>
      <a href="/reports/report-two">Report Two 2026</a>
    </body></html>
    """

    def _get(url, timeout, headers, allow_redirects=True):
        assert timeout == 10.0
        assert headers["User-Agent"].startswith("Mozilla/5.0")
        assert headers["Accept-Language"] == "en-US,en;q=0.9"
        if url.endswith("page=2"):
            return _FakeResponse(
                url="https://example.com/insights?page=2",
                text=html_page_2,
            )
        return _FakeResponse(url="https://example.com/insights", text=html_page_1)

    external_boundary_mocks_only.setattr(service.requests, "get", _get)
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/insights",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.route_kind == "http_parse"
    assert response.used_route_hint is False
    assert len(response.pages) == 2
    assert len(response.candidates) == 2
    assert response.candidates[0].provenance == "http_parse"
    assert response.candidates[0].confidence is not None
    assert response.candidates[0].confidence >= 0.60
    assert response.candidates[1].discovered_on_page_number == 2
    assert (
        response.candidates[1].source_page_url == "https://example.com/insights?page=2"
    )
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(_events(caplog))


def test_discover_publisher_inventory_http_parse_stops_on_duplicate_page_fingerprint(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
) -> None:
    html_page = """
    <html><body>
      <a href="/reports/report-one">Report One 2026</a>
      <a href="https://example.com/insights?page=2" rel="next">Next</a>
    </body></html>
    """
    requested_urls: list[str] = []

    def _get(url, timeout, headers, allow_redirects=True):
        requested_urls.append(url)
        assert timeout == 10.0
        assert headers["User-Agent"].startswith("Mozilla/5.0")
        assert headers["Accept-Language"] == "en-US,en;q=0.9"
        if url.endswith("page=2"):
            return _FakeResponse(
                url="https://example.com/insights?page=2",
                text=html_page,
            )
        return _FakeResponse(url="https://example.com/insights", text=html_page)

    external_boundary_mocks_only.setattr(service.requests, "get", _get)
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/insights",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert requested_urls == [
        "https://example.com/insights",
        "https://example.com/insights?page=2",
    ]
    assert response.route_kind == "http_parse"
    assert len(response.pages) == 1
    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/reports/report-one"
    ]
    duplicate_events = [
        event
        for event in _events(caplog)
        if event.get("event") == "publisher_inventory_http_duplicate_page_fingerprint"
    ]
    assert len(duplicate_events) == 1
    assert_logs_have_required_fields(_events(caplog))


def test_discover_publisher_inventory_http_parse_rejects_low_confidence_candidates(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    html = """
    <html><body>
      <a href="/insights/customer-trends-2026">Customer Trends 2026</a>
    </body></html>
    """

    def _get(url, timeout, headers, allow_redirects=True):
        assert timeout == 10.0
        assert headers["User-Agent"].startswith("Mozilla/5.0")
        assert headers["Accept-Language"] == "en-US,en;q=0.9"
        return _FakeResponse(url="https://example.com/insights", text=html)

    external_boundary_mocks_only.setattr(service.requests, "get", _get)

    with pytest.raises(AppError) as err:
        service.discover_publisher_inventory(
            PublisherInventoryServiceRequest(
                schema_version="1.0",
                insights_url="https://example.com/insights",
                settings=_settings(tmp_path),
                route_kind_hint="http_parse",
            ),
            run_context,
        )

    assert_app_error(err.value, code="publisher_inventory_http_empty", retryable=False)


def test_discover_publisher_inventory_http_parse_recovers_wordpress_ajax_archives(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    page_html = """
    <html>
      <head>
        <title>Resources - Example</title>
        <script>var wpajax = {"url":"https://example.com/wp-admin/admin-ajax.php","nonce":"nonce-123"};</script>
        <script src="https://example.com/wp-content/themes/example/script.js"></script>
      </head>
      <body>
        <main><a href="/resources/">Resources</a></main>
      </body>
    </html>
    """
    script_js = """
    function ajax_filter() {
      var data_ajax = {
        action: 'resources_filter',
        nonce: wpajax.nonce,
        paged: curentPage
      };
    }
    """
    ajax_page_1 = json.dumps(
        {
            "max_num_pages": 2,
            "posts": (
                '<a href="https://example.com/lp/retail-benchmark-2026">'
                "Retail Benchmark 2026"
                "</a>"
            ),
        }
    )
    ajax_page_2 = json.dumps(
        {
            "max_num_pages": 2,
            "posts": (
                '<a href="https://example.com/lp/customer-retention-playbook">'
                "Customer Retention Playbook"
                "</a>"
            ),
        }
    )

    def _get(url, timeout, headers, allow_redirects=True):
        normalized_url = str(url).rstrip("/")
        if normalized_url == "https://example.com/resources":
            return _FakeResponse(url="https://example.com/resources", text=page_html)
        if normalized_url == "https://example.com/wp-content/themes/example/script.js":
            return _FakeResponse(url=normalized_url, text=script_js)
        raise AssertionError(f"Unexpected GET url: {url}")

    def _post(url, timeout, headers, data):
        assert url == "https://example.com/wp-admin/admin-ajax.php"
        assert headers["X-Requested-With"] == "XMLHttpRequest"
        if data["paged"] == "1":
            return _FakeResponse(url=url, text=ajax_page_1)
        if data["paged"] == "2":
            return _FakeResponse(url=url, text=ajax_page_2)
        raise AssertionError(f"Unexpected AJAX payload: {data}")

    external_boundary_mocks_only.setattr(service.requests, "get", _get)
    external_boundary_mocks_only.setattr(service.requests, "post", _post)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/resources",
            settings=_settings(tmp_path),
            route_kind_hint="http_parse",
        ),
        run_context,
    )

    assert response.route_kind == "http_parse"
    assert "WordPress AJAX action `resources_filter`" in response.route_summary
    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/lp/retail-benchmark-2026",
        "https://example.com/lp/customer-retention-playbook",
    ]


def test_discover_publisher_inventory_http_parse_retries_with_trailing_slash(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    def _get(url, timeout, headers, allow_redirects=True):
        if str(url) == "https://example.com/resources":
            raise service.requests.RequestException("redirect timeout")
        if str(url) == "https://example.com/resources/":
            return _FakeResponse(
                url="https://example.com/resources/",
                text=(
                    "<html><body>"
                    "<a href='/lp/retail-benchmark-2026'>Retail Benchmark 2026</a>"
                    "</body></html>"
                ),
            )
        raise AssertionError(f"Unexpected GET url: {url}")

    external_boundary_mocks_only.setattr(service.requests, "get", _get)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/resources",
            settings=_settings(tmp_path),
            route_kind_hint="http_parse",
        ),
        run_context,
    )

    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/lp/retail-benchmark-2026"
    ]


def test_discover_publisher_inventory_http_parse_supplements_sparse_archive_with_wordpress_ajax(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    page_html = """
    <html>
      <head>
        <title>Resources - Example</title>
        <script>var wpajax = {"url":"https://example.com/wp-admin/admin-ajax.php","nonce":"nonce-123"};</script>
        <script src="https://example.com/wp-content/themes/example/script.js"></script>
      </head>
      <body>
        <main>
          <a href="/resources/">Resources</a>
          <a href="/lp/featured-retail-benchmark">Featured Retail Benchmark</a>
        </main>
      </body>
    </html>
    """
    script_js = """
    var data_ajax = {
      action: 'resources_filter',
      nonce: wpajax.nonce,
      paged: curentPage
    };
    """
    ajax_page_1 = json.dumps(
        {
            "max_num_pages": 1,
            "posts": (
                '<a href="https://example.com/lp/featured-retail-benchmark">'
                "Featured Retail Benchmark"
                "</a>"
                '<a href="https://example.com/lp/customer-retention-playbook">'
                "Customer Retention Playbook"
                "</a>"
            ),
        }
    )

    def _get(url, timeout, headers, allow_redirects=True):
        normalized_url = str(url).rstrip("/")
        if normalized_url == "https://example.com/resources":
            return _FakeResponse(url="https://example.com/resources/", text=page_html)
        if normalized_url == "https://example.com/wp-content/themes/example/script.js":
            return _FakeResponse(url=normalized_url, text=script_js)
        raise AssertionError(f"Unexpected GET url: {url}")

    def _post(url, timeout, headers, data):
        assert url == "https://example.com/wp-admin/admin-ajax.php"
        return _FakeResponse(url=url, text=ajax_page_1)

    external_boundary_mocks_only.setattr(service.requests, "get", _get)
    external_boundary_mocks_only.setattr(service.requests, "post", _post)

    response = service.discover_publisher_inventory(
        PublisherInventoryServiceRequest(
            schema_version="1.0",
            insights_url="https://example.com/resources",
            settings=_settings(tmp_path),
            route_kind_hint="http_parse",
        ),
        run_context,
    )

    assert "WordPress AJAX action `resources_filter`" in response.route_summary
    assert [candidate.url for candidate in response.candidates] == [
        "https://example.com/lp/featured-retail-benchmark",
        "https://example.com/lp/customer-retention-playbook",
    ]


def test_select_tab_labels_for_traversal_prefers_report_focused_tabs() -> None:
    state = service._RenderedInventoryState(
        page_url="https://example.com/resources/blog",
        page_title="Example Resources",
        anchors=[],
        load_more_labels=[],
        tab_labels=["All", "Articles", "Research"],
        active_tab_label="All",
        report_link_url=None,
        empty_results_visible=False,
        reset_filter_labels=[],
        has_report_filter=False,
        has_apply_button=False,
    )

    selected = service._select_tab_labels_for_traversal(
        "https://example.com/resources/blog",
        state,
    )

    assert selected == ["Research"]


def test_requires_archive_surface_recovery_for_detail_page_drift() -> None:
    state = service._RenderedInventoryState(
        page_url="https://example.com/resources/blog/cloud-cost-guide",
        page_title="Cloud Cost Guide",
        anchors=[],
        load_more_labels=[],
        tab_labels=[],
        active_tab_label="",
        report_link_url=None,
        empty_results_visible=False,
        reset_filter_labels=[],
        has_report_filter=False,
        has_apply_button=False,
    )

    assert service._requires_archive_surface_recovery(
        state=state,
        page_candidates=[],
        normalized_url="https://example.com/resources/blog",
    )


def test_is_archive_surface_accepts_small_set_of_substantive_cards() -> None:
    state = service._RenderedInventoryState(
        page_url="https://www.psfk.com/insights",
        page_title="PSFK | Living Intelligence & AI Foresight",
        anchors=[
            {
                "href": "https://psfk.gumroad.com/l/coffee-machine-innovation-report",
                "text": "Coffee Maker Innovation An essential snapshot of the ideas reshaping coffee machines.",
                "rel": "",
            },
            {
                "href": "https://newsletter.psfk.com/p/about-your-health",
                "text": "About Your Health Healthcare now runs through homes, workplaces, communities, devices and apps.",
                "rel": "",
            },
            {
                "href": "https://newsletter.psfk.com/p/future-of-wellness",
                "text": "Future of Wellness A strategic thinking brief on changing consumer wellness expectations.",
                "rel": "",
            },
        ],
        load_more_labels=[],
        tab_labels=[],
        active_tab_label="",
        report_link_url=None,
        empty_results_visible=False,
        reset_filter_labels=[],
        has_report_filter=False,
        has_apply_button=False,
    )

    assert service._is_archive_surface(state) is True


def test_terminal_results_page_accepts_page_count_hints() -> None:
    state = service._RenderedInventoryState(
        page_url="https://example.com/library",
        page_title="Example Library",
        anchors=[],
        load_more_labels=[],
        tab_labels=[],
        active_tab_label="",
        report_link_url=None,
        empty_results_visible=False,
        reset_filter_labels=[],
        has_report_filter=False,
        has_apply_button=False,
        page_index_hint=12,
        page_total_hint=12,
    )

    assert service._is_terminal_results_page(state) is True


def test_should_follow_report_listing_requires_archive_like_target() -> None:
    state = service._RenderedInventoryState(
        page_url="https://www.publicissapient.com/resources/blog",
        page_title="Publicis Sapient Blog",
        anchors=[],
        load_more_labels=[],
        tab_labels=[],
        active_tab_label="",
        report_link_url="https://www.publicissapient.com/resources/blog/cloud-cost-management-guide",
        empty_results_visible=False,
        reset_filter_labels=[],
        has_report_filter=False,
        has_apply_button=False,
    )

    assert (
        service._should_follow_report_listing(
            "https://www.publicissapient.com/resources/blog",
            state,
        )
        is False
    )


def test_should_expand_archive_library_for_small_archive_preview() -> None:
    state = service._RenderedInventoryState(
        page_url="https://www.psfk.com/insights",
        page_title="Reports & Strategic Thinking",
        anchors=[],
        load_more_labels=[],
        tab_labels=[],
        active_tab_label="",
        report_link_url=None,
        empty_results_visible=False,
        reset_filter_labels=[],
        has_report_filter=False,
        has_apply_button=False,
    )
    page_candidates = [
        service.PublisherInventoryRawCandidate(
            schema_version="1.0",
            url="https://psfk.gumroad.com/l/coffee-machine-innovation-report",
            title="Coffee Maker Innovation",
            source_page_url="https://www.psfk.com/insights",
            discovered_on_page_number=1,
        ),
        service.PublisherInventoryRawCandidate(
            schema_version="1.0",
            url="https://psfk.gumroad.com/l/2026-trends-report",
            title="To Be In 2026",
            source_page_url="https://www.psfk.com/insights",
            discovered_on_page_number=1,
        ),
    ]

    assert service._should_expand_archive_library(state, page_candidates) is True


def test_should_apply_report_filter_generically_for_visible_report_filter() -> None:
    state = service._RenderedInventoryState(
        page_url="https://www.transunion.com/insights",
        page_title="Insights | TransUnion",
        anchors=[],
        load_more_labels=[],
        tab_labels=[],
        active_tab_label="",
        report_link_url=None,
        empty_results_visible=False,
        reset_filter_labels=[],
        has_report_filter=True,
        has_apply_button=False,
    )

    assert (
        service._should_apply_report_filter(
            "https://www.transunion.com/insights",
            state,
        )
        is True
    )


def test_select_anchor_title_prefers_heading_over_noisy_card_text() -> None:
    selected = service._select_anchor_title(
        {
            "text": "Amazon Prime Day Trends Report 2024 Margaux Logan 22 / 07 / 2024 MARKETING AND THOUGHT LEADERSHIP Read more",
            "heading_text": "Amazon Prime Day Trends Report 2024",
            "aria_label": "",
            "title_attr": "",
            "img_alt": "",
        }
    )

    assert selected == "Amazon Prime Day Trends Report 2024"


def test_select_anchor_title_uses_card_context_for_generic_cta_links() -> None:
    selected = service._select_anchor_title(
        {
            "text": "Learn more",
            "heading_text": "",
            "aria_label": "",
            "title_attr": "",
            "img_alt": "",
            "context_text": (
                "Retail Data & Trends, Seasonal Retail Advice "
                "Black Friday Benchmarks 2025 "
                "Discover Bluecore's annual Black Friday benchmarks report. "
                "Learn more"
            ),
        }
    )

    assert selected.startswith(
        "Retail Data & Trends, Seasonal Retail Advice Black Friday Benchmarks 2025"
    )


def test_extract_candidates_from_html_uses_heading_for_cta_only_links() -> None:
    candidates = service._extract_candidates_from_html(
        anchors=[
            {
                "href": "https://www.bluecore.com/black-friday-benchmarks-2025/",
                "text": "Learn more",
                "heading_text": "Black Friday Benchmarks 2025",
                "aria_label": "",
                "title_attr": "",
                "img_alt": "BFCM Benchmarks",
            }
        ],
        page_url="https://www.bluecore.com/resources/",
        page_number=1,
        next_page_url=None,
        origin_url="https://www.bluecore.com/resources/",
        page_title="Resources - Bluecore",
        archive_surface=True,
    )

    assert [candidate.url for candidate in candidates] == [
        "https://www.bluecore.com/black-friday-benchmarks-2025"
    ]
    assert candidates[0].title == "Black Friday Benchmarks 2025"


def test_extract_candidates_from_html_resolves_relative_links_to_origin_host_when_browser_drifts() -> (
    None
):
    candidates = service._extract_candidates_from_html(
        anchors=[
            {
                "href": "/black-friday-benchmarks-2025/",
                "text": "Learn more",
                "heading_text": "Black Friday Benchmarks 2025",
                "aria_label": "",
                "title_attr": "",
                "img_alt": "",
            }
        ],
        page_url="https://wordpress.bluecore.app/resources",
        page_number=1,
        next_page_url=None,
        origin_url="https://www.bluecore.com/resources/",
        page_title="Resources - Bluecore",
        archive_surface=True,
    )

    assert [candidate.url for candidate in candidates] == [
        "https://www.bluecore.com/black-friday-benchmarks-2025"
    ]


def test_extract_candidates_from_html_uses_card_context_for_generic_cta_links() -> None:
    candidates = service._extract_candidates_from_html(
        anchors=[
            {
                "href": "https://www.bluecore.com/black-friday-benchmarks-2025/",
                "text": "Learn more",
                "heading_text": "",
                "aria_label": "",
                "title_attr": "",
                "img_alt": "",
                "context_text": (
                    "Retail Data & Trends, Seasonal Retail Advice "
                    "Black Friday Benchmarks 2025 "
                    "Discover Bluecore's annual Black Friday benchmarks report. "
                    "Learn more"
                ),
                "rel": "",
            }
        ],
        page_url="https://wordpress.bluecore.app/resources",
        page_number=1,
        next_page_url=None,
        origin_url="https://www.bluecore.com/resources/",
        page_title="Resources - Bluecore",
        archive_surface=True,
    )

    assert [candidate.url for candidate in candidates] == [
        "https://www.bluecore.com/black-friday-benchmarks-2025"
    ]


def test_extract_candidates_from_html_keeps_direct_report_library_pages_on_archive_surfaces() -> (
    None
):
    candidates = service._extract_candidates_from_html(
        anchors=[],
        page_url="https://www.knightfrank.com/research/report-library/active-capital-the-report-11021.aspx",
        page_number=1,
        next_page_url=None,
        origin_url="https://www.knightfrank.com/research/report-library/active-capital-the-report-11021.aspx",
        page_title="Active Capital: The Report",
        archive_surface=True,
    )

    assert [candidate.url for candidate in candidates] == [
        "https://www.knightfrank.com/research/report-library/active-capital-the-report-11021.aspx"
    ]
    assert candidates[0].title == "Active Capital: The Report"


def test_inventory_html_parser_preserves_container_text_for_generic_cta_links() -> None:
    parser = service._InventoryHtmlParser()
    parser.feed(
        """
        <html><body>
          <div class="resource-card">
            <div>Retail Data &amp; Trends</div>
            <div>Black Friday Benchmarks 2025</div>
            <div>Discover Bluecore's annual Black Friday benchmarks report.</div>
            <a href="https://www.bluecore.com/black-friday-benchmarks-2025/">Learn more</a>
          </div>
        </body></html>
        """
    )

    candidates = service._extract_candidates_from_html(
        anchors=parser.anchors,
        page_url="https://wordpress.bluecore.app/resources",
        page_number=1,
        next_page_url=None,
        origin_url="https://www.bluecore.com/resources/",
        page_title="Resources - Bluecore",
        archive_surface=True,
    )

    assert [candidate.url for candidate in candidates] == [
        "https://www.bluecore.com/black-friday-benchmarks-2025"
    ]


def test_extract_candidates_from_html_filters_false_positive_hub_and_social_links() -> (
    None
):
    html = """
    <html><body>
      <a href="/blog/social-media-industry-benchmark-report/">2025 Social Media Industry Benchmark Report</a>
      <a href="/it/insights">Italy (Italiano)</a>
      <a href="/de/insights/type/report">Deutsch</a>
      <a href="https://www.facebook.com/bainandcompany">icon-facebook-f</a>
      <a href="/insights/type/article">Article archive</a>
      <a href="/insights/topic/big-data/">Big Data</a>
      <a href="/">.st0{fill:#FFFFFF;}</a>
      <a href="/global/en/insights/report/2025/reports/">Reports</a>
      <a href="/global/en">02_Elements/Icons/Close</a>
      <a href="/vector-digital/ai-insights-and-solutions">AI, Insights, and Solutions</a>
      <a href="/insights/featured-topics/">View all featured topics</a>
      <a href="/insights/why-agentic-ai-demands-a-new-architecture/">Why Agentic AI Demands a New Architecture</a>
      <a href="/insights/topics/global-private-equity-report/">Global Private Equity Report 2026</a>
      <a href="https://www.weforum.org/stories/2026/03/how-corporate-strategy-is-changing-in-a-world-of-constant-shocks/">Redefining Corporate Strategy in a More Volatile World</a>
    </body></html>
    """
    parser = service._InventoryHtmlParser()
    parser.feed(html)

    candidates = service._extract_candidates_from_html(
        anchors=parser.anchors,
        page_url="https://www.bain.com/insights?filters=|types(424%2C420)",
        page_number=1,
        next_page_url=None,
    )

    assert [candidate.title for candidate in candidates] == [
        "2025 Social Media Industry Benchmark Report",
        "Why Agentic AI Demands a New Architecture",
        "Global Private Equity Report 2026",
    ]
    assert [candidate.url for candidate in candidates] == [
        "https://www.bain.com/blog/social-media-industry-benchmark-report",
        "https://www.bain.com/insights/why-agentic-ai-demands-a-new-architecture",
        "https://www.bain.com/insights/topics/global-private-equity-report",
    ]


def test_extract_candidates_from_html_allows_original_host_when_rendered_page_uses_hosted_subdomain() -> (
    None
):
    html = """
    <html><body>
      <a href="https://www.bluecore.com/lp/customer-movement-benchmarks/">Benchmarks for Identification, Conversion, and Retention</a>
    </body></html>
    """
    parser = service._InventoryHtmlParser()
    parser.feed(html)

    candidates = service._extract_candidates_from_html(
        anchors=parser.anchors,
        page_url="https://wordpress.bluecore.app/resources",
        page_number=1,
        next_page_url=None,
        origin_url="https://www.bluecore.com/resources",
    )

    assert [candidate.url for candidate in candidates] == [
        "https://www.bluecore.com/lp/customer-movement-benchmarks"
    ]


def test_extract_candidates_from_html_accepts_archive_surface_cards_without_report_keywords() -> (
    None
):
    html = """
    <html><body>
      <a href="https://www.publicissapient.com/resources/blog/modernization-risks-regulated-industries">
        <h3>Modernization Risks in Regulated Industries</h3>
        <span>Research</span>
      </a>
      <a href="https://www.publicissapient.com/resources/blog/the-ai-powered-investment-firm">
        <h3>The AI-Powered Investment Firm</h3>
        <span>Research</span>
      </a>
    </body></html>
    """
    parser = service._InventoryHtmlParser()
    parser.feed(html)

    candidates = service._extract_candidates_from_html(
        anchors=parser.anchors,
        page_url="https://www.publicissapient.com/resources/blog",
        page_number=1,
        next_page_url=None,
        origin_url="https://www.publicissapient.com/resources/blog",
        page_title="Publicis Sapient Blog | Articles and Research",
        active_tab_label="Research",
        archive_surface=True,
    )

    assert [candidate.url for candidate in candidates] == [
        "https://www.publicissapient.com/resources/blog/modernization-risks-regulated-industries",
        "https://www.publicissapient.com/resources/blog/the-ai-powered-investment-firm",
    ]


def test_extract_candidates_from_html_accepts_external_report_host_on_archive_surface() -> (
    None
):
    html = """
    <html><body>
      <a href="https://psfk.gumroad.com/l/coffee-machine-innovation-report-psfk-for-waldo">
        Report January 2026 Coffee Maker Innovation Download Report
      </a>
    </body></html>
    """
    parser = service._InventoryHtmlParser()
    parser.feed(html)

    candidates = service._extract_candidates_from_html(
        anchors=parser.anchors,
        page_url="https://www.psfk.com/insights",
        page_number=1,
        next_page_url=None,
        origin_url="https://www.psfk.com/insights",
        page_title="Thought Leadership Archive",
        archive_surface=True,
    )

    assert [candidate.url for candidate in candidates] == [
        "https://psfk.gumroad.com/l/coffee-machine-innovation-report-psfk-for-waldo"
    ]
