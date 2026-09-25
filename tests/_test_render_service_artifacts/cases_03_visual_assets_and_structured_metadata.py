# ruff: noqa: F401,F403,F405

from ._shared import *


@pytest.mark.parametrize(
    (
        "title",
        "publisher",
        "time_period",
        "doc_map",
        "expected_seo_title",
        "expected_metadata",
    ),
    [
        (
            "Email, SMS, and push marketing statistics for ecommerce in 2024",
            "Omnisend",
            "2023",
            {},
            (
                "Email, SMS, and push marketing statistics for ecommerce in 2024 "
                "| Omnisend | MarketBearing"
            ),
            ("Data period: 2023",),
        ),
        (
            "Activate Technology & Media Outlook 2025: eCommerce",
            "Activate Consulting",
            "2024",
            {},
            (
                "Activate Technology & Media Outlook 2025: eCommerce "
                "| Activate Consulting | MarketBearing"
            ),
            ("Edition: 2025", "Data period: 2024"),
        ),
        (
            "Ecommerce marketing report",
            "",
            "2024",
            {},
            "Ecommerce marketing report 2024 | MarketBearing",
            ("Data period: 2024",),
        ),
        (
            "Retail outlook 2025",
            "",
            "January to December 2024",
            {"publicationDate": "2025-01-15"},
            "Retail outlook 2025 | MarketBearing",
            ("Edition: 2025", "Data period: January–December 2024"),
        ),
    ],
)
def test_rendered_report_identity_keeps_title_year_and_labels_distinct_dates(
    tmp_path: Path,
    title: str,
    publisher: str,
    time_period: str,
    doc_map: dict[str, str],
    expected_seo_title: str,
    expected_metadata: tuple[str, ...],
) -> None:
    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data={
                "title": title,
                "publisher": publisher,
                "time_period": time_period,
                "evidence_packs": {"doc_map": doc_map},
                "artifacts": {"summary": {"tldr": "Source-backed summary."}},
            },
            doc_name="year-identity.pdf",
            file_id="year-identity",
            out_dir=str(tmp_path),
            preview_png=None,
        ),
        _ctx(),
    )

    html = Path(response.html_path).read_text(encoding="utf-8")

    title_values = re.findall(
        r'<title>([^<]+)</title>|(?:property="og:title"|name="twitter:title") '
        r'content="([^"]+)"',
        html,
    )
    rendered_titles = [
        unescape(next(value for value in values if value)) for values in title_values
    ]
    assert rendered_titles == [expected_seo_title] * 3
    heading = re.search(r'<h1 id="report-title">([^<]+)</h1>', html)
    assert heading is not None
    assert unescape(heading.group(1)) == title
    assert f"Title: {title}" in html
    for expected_value in expected_metadata:
        assert expected_value in html
    assert "Period:" not in html
    assert "Year:" not in html
    json_ld = json.loads(
        re.search(r'<script type="application/ld\+json">(.*?)</script>', html).group(1)
    )
    assert json_ld["headline"] == title


def test_render_omits_ambiguous_inferred_year_when_title_already_names_another_year(
    tmp_path: Path,
) -> None:
    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data={
                "title": "Technology outlook 2025",
                "evidence_packs": {"doc_map": {"year": "2024"}},
                "artifacts": {"summary": {"tldr": "Source-backed summary."}},
            },
            doc_name="ambiguous-year.pdf",
            file_id="ambiguous-year",
            out_dir=str(tmp_path),
            preview_png=None,
        ),
        _ctx(),
    )

    html = Path(response.html_path).read_text(encoding="utf-8")

    assert "<title>Technology outlook 2025 | MarketBearing</title>" in html
    assert "Title: Technology outlook 2025" in html
    assert "2024" not in html


def test_seo_title_does_not_append_a_year_when_a_compacted_subtitle_has_one() -> None:
    assert (
        _build_seo_title(
            "A deliberately long primary report name that exceeds the SEO limit: "
            "2025 edition",
            "2024",
            "Publisher",
        )
        == "A deliberately long primary report name that exceeds the SEO limit "
        "| Publisher | MarketBearing"
    )


def test_render_relabels_unknown_quote_speakers_and_shows_citation_micro_lines(
    tmp_path,
):
    data = {
        "title": "Unknown speaker report",
        "tldr": "TLDR",
        "insights": ["legacy insight"] * 5,
        "quote": {"text": "Legacy quote", "author": "Unknown"},
        "commentary": "Commentary",
        "publisher": "Artlist",
        "taxonomy": [],
        "region": "US",
        "time_period": "2026",
        "contents_page_number": 0,
        "artifacts": {
            "summary": {
                "tldr": "Artifact TLDR",
                "executive_summary": "Artifact executive summary",
                "claim_evidence_map": [
                    {
                        "claim": "Claim 1",
                        "evidence_id": "f1",
                        "evidence": "Evidence 1",
                        "pages": [7],
                        "evidence_spans": [
                            {
                                "evidence_id": "f1",
                                "source_pack": "findings",
                                "page": 7,
                            }
                        ],
                    }
                ],
            },
            "insights_final": [
                {
                    "id": "i1",
                    "text": "Artifact insight 1",
                    "evidence_id": "f1",
                    "evidence_spans": [
                        {"evidence_id": "f1", "source_pack": "findings", "page": 7}
                    ],
                    "metric": {},
                }
            ],
            "quotes_final": [
                {
                    "text": "Artifact quote",
                    "speaker": "Unknown",
                    "citation": "",
                    "page": 7,
                    "evidence_id": "q1",
                    "evidence_spans": [
                        {
                            "evidence_id": "q1",
                            "source_pack": "quote_candidates",
                            "page": 7,
                        }
                    ],
                }
            ],
        },
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="unknown.pdf",
        file_id="file_unknown",
        out_dir=str(tmp_path),
        preview_png=None,
    )
    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert "Artlist expert team" in html
    assert "Unknown speaker report, page 7" in html
    assert "q1 · report page" not in html


def test_render_surfaces_editorial_details_from_evidence_packs(tmp_path):
    data = {
        "title": "Editorial Report",
        "tldr": "Concise lead.",
        "insights": ["Insight A"] * 5,
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "region": "Global",
        "time_period": "2026 (fieldwork Oct 2025)",
        "contents_page_number": 0,
        "artifacts": {
            "summary": {
                "tldr": "Concise lead.",
                "executive_summary": "Longer summary.",
            },
            "toc_entries": [
                {
                    "display_title": "Demand outlook",
                    "section_title": "Demand outlook",
                    "summary": "Demand shifts toward APAC.",
                    "pages": [4, 5],
                    "order": 1,
                }
            ],
        },
        "evidence_packs": {
            "doc_map": {
                "title": "Editorial Report",
                "publisher": "Publisher",
                "methodology": "Survey fielded in October 2025 across 12 markets.",
                "contributors": [
                    {
                        "name": "Alex Analyst",
                        "role": "Research lead",
                        "email": "alex@example.com",
                    }
                ],
            },
            "methods": {
                "methods": [
                    {
                        "name": "Market survey",
                        "description": (
                            "Survey fielded in October 2025 across 12 markets."
                        ),
                    }
                ]
            },
            "findings": {
                "findings": [
                    {"statement": "Demand is rebounding in APAC first."},
                ]
            },
            "limitations": {
                "limitations": [
                    {"message": "Sample is weighted toward enterprise respondents."},
                ]
            },
            "scope": {
                "scope": {
                    "jurisdictions": ["US", "UK"],
                    "sources": [{"title": "Editorial Report"}],
                    "contentTypes": ["application/pdf"],
                    "samplingRate": "100%",
                    "retentionDays": 365,
                }
            },
        },
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="editorial.pdf",
        file_id="file_editorial",
        out_dir=str(tmp_path),
        preview_png=None,
    )

    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert "Read the source and check provenance" in html
    assert "Methodology" in html
    assert "Survey fielded in October 2025 across 12 markets." in html
    assert "Coverage" in html
    assert "Jurisdictions: US, UK" in html
    assert "Findings" in html
    assert "Demand is rebounding in APAC first." in html
    assert "Limitations" in html
    assert "Sample is weighted toward enterprise respondents." in html
    assert "Contacts" in html
    assert "Alex Analyst — Research lead — alex@example.com" in html
    assert "Ordered chapters" in html
    assert "1. Demand outlook" in html
    assert "Pages: 4, 5" in html
    assert "Data period: 2026" in html
    assert "Data period: 2026 (fieldwork Oct 2025)" not in html
    assert "2026" in html
    assert "Fieldwork:" not in html


def test_render_hides_figure_sections_when_disabled(tmp_path):
    data = {
        "title": "No Figures Report",
        "tldr": "TLDR",
        "insights": ["Insight A", "Insight B", "Insight C", "Insight D", "Insight E"],
        "quote": {"text": "Q", "author": "A"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["tag"],
        "region": "US",
        "time_period": "2024",
        "contents_page_number": 4,
        "_contents_image": "report/contents.png",
        "_figure_top": "report/slices/top.png",
        "_figure_gallery": [
            "report/slices/top.png",
            "report/slices/extra1.png",
            "report/slices/extra2.png",
        ],
        "_figure_section_enabled": False,
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="nofig.pdf",
        file_id="file_nofig",
        out_dir=str(tmp_path),
        preview_png=None,
    )
    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert 'id="section-figures"' not in html
    assert 'id="section-contents-preview"' not in html


def test_render_uses_per_asset_figure_captions(tmp_path):
    data = {
        "title": "Figure Caption Report",
        "tldr": "TLDR",
        "insights": ["Insight A", "Insight B", "Insight C", "Insight D", "Insight E"],
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["tag"],
        "region": "US",
        "time_period": "2024",
        "contents_page_number": 0,
        "_figure_top": "report/slices/primary.png",
        "_figure_gallery": [
            "report/slices/primary.png",
            "report/slices/secondary.png",
        ],
        "_figure_assets": [
            {
                "schema_version": "1.0",
                "image_path": "report/slices/primary.png",
                "page": 2,
                "candidate_id": "chart-1",
                "kind": "chart",
                "is_primary": True,
                "detected_caption": "Detected primary caption",
                "preview_text": "Primary preview",
                "generated_caption": "Primary generated caption",
                "display_caption": "Primary generated caption",
                "caption_source": "generated",
            },
            {
                "schema_version": "1.0",
                "image_path": "report/slices/secondary.png",
                "page": 3,
                "candidate_id": "table-2",
                "kind": "table",
                "is_primary": False,
                "detected_caption": "Detected secondary caption",
                "preview_text": "Secondary preview",
                "generated_caption": "",
                "display_caption": "Detected secondary caption",
                "caption_source": "detected",
            },
        ],
        "_figure_section_enabled": True,
        "figure": {"title": "Legacy caption", "evidence": "Legacy evidence"},
        "artifacts": {
            "chart_insight_cards": [
                {
                    "status": "generated",
                    "candidate_id": "chart-1",
                    "crop_qa_accepted": True,
                    "evidence_id": "f1",
                    "insight_id": "i1",
                    "source_page": 2,
                    "caption": "Primary generated caption",
                    "public_takeaway": "The primary chart supports the published finding.",
                },
                {
                    "status": "generated",
                    "candidate_id": "table-2",
                    "crop_qa_accepted": True,
                    "evidence_id": "f2",
                    "insight_id": "i2",
                    "source_page": 3,
                    "caption": "Detected secondary caption",
                    "public_takeaway": "The secondary table supports the published finding.",
                },
            ]
        },
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="figures.pdf",
        file_id="file_figures",
        out_dir=str(tmp_path),
        preview_png=None,
    )
    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert "Primary generated caption" in html
    assert "Detected secondary caption" in html
    assert (
        '<figcaption class="carousel-caption">Additional figure 2</figcaption>'
        not in html
    )


def test_render_keeps_legacy_figure_captions_without_figure_assets(tmp_path):
    data = {
        "title": "Legacy Figure Caption Report",
        "tldr": "TLDR",
        "insights": ["Insight A", "Insight B", "Insight C", "Insight D", "Insight E"],
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["tag"],
        "region": "US",
        "time_period": "2024",
        "contents_page_number": 0,
        "_figure_top": "report/slices/primary.png",
        "_figure_gallery": [
            "report/slices/primary.png",
            "report/slices/secondary.png",
        ],
        "_figure_section_enabled": True,
        "figure": {"title": "Legacy figure caption", "evidence": "Legacy evidence"},
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="legacy-figures.pdf",
        file_id="file_legacy_figures",
        out_dir=str(tmp_path),
        preview_png=None,
    )
    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert 'id="candidates"' not in html
    assert "Legacy figure caption" not in html


def test_render_formats_slug_chips_with_acronyms(tmp_path):
    data = {
        "title": "Chip Format Report",
        "tldr": "TLDR",
        "insights": ["Insight A", "Insight B", "Insight C", "Insight D", "Insight E"],
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "categories_display": ["ai-in-retail", "private_label"],
        "taxonomy": ["fmcg", "consumer_trends", "roi"],
        "region": "US",
        "time_period": "2024",
        "contents_page_number": 0,
        "artifacts": {"toc_topics": ["ai", "consumer_trends"]},
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="chips.pdf",
        file_id="file_chip",
        out_dir=str(tmp_path),
        preview_png=None,
        tag_acronyms=["AI", "FMCG", "ROI"],
    )
    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert "AI in Retail" in html
    assert "Private Label" in html
    assert "FMCG" in html
    assert "Consumer Trends" in html
    assert "ROI" in html
    assert "ai-in-retail" not in html
    assert "private_label" not in html


def test_render_adds_responsive_srcset_when_variant_exists(tmp_path):
    assets_dir = tmp_path / "report" / "slices"
    assets_dir.mkdir(parents=True, exist_ok=True)
    base_path = assets_dir / "primary.png"
    variant_path = assets_dir / "primary@2x.png"
    Image.new("RGB", (800, 450), color="navy").save(base_path)
    Image.new("RGB", (1600, 900), color="navy").save(variant_path)

    data = {
        "title": "Responsive Figure Report",
        "tldr": "TLDR",
        "insights": ["Insight A"] * 5,
        "quote": {"text": "Quote", "author": "Author"},
        "commentary": "Commentary",
        "publisher": "Publisher",
        "taxonomy": ["tag"],
        "region": "US",
        "time_period": "2024",
        "contents_page_number": 0,
        "_figure_assets": [
            {
                "schema_version": "1.0",
                "image_path": "report/slices/primary.png",
                "page": 2,
                "candidate_id": "chart-1",
                "kind": "chart",
                "is_primary": True,
                "display_caption": "Primary generated caption",
                "crop_qa_accepted": True,
            }
        ],
        "artifacts": {
            "chart_insight_cards": [
                {
                    "status": "generated",
                    "candidate_id": "chart-1",
                    "crop_qa_accepted": True,
                    "evidence_id": "f1",
                    "insight_id": "i1",
                    "source_page": 2,
                    "caption": "Primary generated caption",
                    "public_takeaway": "The chart supports the published finding.",
                }
            ]
        },
    }
    req = RenderRequest(
        schema_version="1.0",
        data=data,
        doc_name="responsive.pdf",
        file_id="file_responsive",
        out_dir=str(tmp_path),
        preview_png=None,
    )

    resp = render_report(req, _ctx())
    html = Path(resp.html_path).read_text(encoding="utf-8")

    assert (
        'srcset="report/slices/primary.png 1x, report/slices/primary@2x.png 2x"' in html
    )
    assert 'sizes="(max-width: 800px) 100vw, 980px"' in html
    assert 'width="800"' in html
    assert 'height="450"' in html
    assert 'loading="lazy"' in html


def test_render_creates_missing_nested_output_directory(tmp_path):
    out_dir = tmp_path / "missing" / "nested"
    req = RenderRequest(
        schema_version="1.0",
        data={
            "title": "Nested Output Report",
            "tldr": "TLDR",
            "insights": [
                "Insight A",
                "Insight B",
                "Insight C",
                "Insight D",
                "Insight E",
            ],
            "quote": {"text": "Quote", "author": "Author"},
            "commentary": "Commentary",
            "publisher": "Publisher",
            "taxonomy": ["tag"],
            "region": "US",
            "time_period": "2024",
            "contents_page_number": 0,
        },
        doc_name="nested.pdf",
        file_id="file_nested",
        out_dir=str(out_dir),
        preview_png=None,
    )

    response = render_report(req, _ctx())

    assert out_dir.exists()
    assert Path(response.html_path).exists()


def test_render_json_ld_keeps_named_author_distinct_from_publisher(tmp_path):
    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data={
                "title": "Digital 2022: Sweden",
                "publisher": "DataReportal",
                "report_identity_author": "Simon Kemp",
                "report_identity_author_kind": "person",
                "artifacts": {"summary": {"tldr": "Source-backed summary."}},
            },
            doc_name="digital-2022-sweden.pdf",
            file_id="digital-2022-sweden",
            out_dir=str(tmp_path),
            preview_png=None,
        ),
        _ctx(),
    )

    html = Path(response.html_path).read_text(encoding="utf-8")
    json_ld = json.loads(
        re.search(r'<script type="application/ld\+json">(.*?)</script>', html).group(1)
    )
    assert json_ld["publisher"] == {"@type": "Organization", "name": "DataReportal"}
    assert json_ld["author"] == {"@type": "Person", "name": "Simon Kemp"}
