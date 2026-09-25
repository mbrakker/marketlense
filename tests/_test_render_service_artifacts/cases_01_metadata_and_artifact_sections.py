# ruff: noqa: F401,F403,F405

from ._shared import *


def test_source_pdf_is_never_used_as_a_marketlense_article_canonical() -> None:
    source = "https://publisher.example/reports/original-study.pdf"

    assert _marketlense_article_url(source, source_url=source) == ""
    assert (
        _marketlense_article_url(
            "https://marketlense.example/reports/original-study",
            source,
            source_url=source,
        )
        == "https://marketlense.example/reports/original-study"
    )


def test_render_embeds_immutable_build_provenance_comment(tmp_path: Path) -> None:
    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data={"title": "Traceable Report"},
            doc_name="traceable-report.pdf",
            file_id="traceable-report",
            out_dir=str(tmp_path),
            preview_png=None,
            build_provenance={
                "git_sha": "a" * 40,
                "generation_run_id": "generation-run-1",
                "validation_run_id": "validation-run-1",
                "source_id": "source:example",
                "source_md5": "b" * 32,
                "artifact_hash": "c" * 64,
                "generation_profile": "safe_default",
                "generated_at_utc": "2026-09-09T12:00:00+00:00",
            },
        ),
        _ctx(),
    )

    html = Path(response.html_path).read_text(encoding="utf-8")

    assert "<!--\nmarketbearing-build:" in html
    assert "git_sha: " + "a" * 40 in html
    assert "generation_run_id: generation-run-1" in html
    assert "validation_run_id: validation-run-1" in html
    assert "source_id: source:example" in html
    assert "source_md5: " + "b" * 32 in html
    assert "artifact_hash: " + "c" * 64 in html
    assert "generation_profile: safe_default" in html
    assert "generated_at_utc: 2026-09-09T12:00:00+00:00" in html


def test_public_title_and_meta_description_are_bounded_editorial_prose() -> None:
    assert (
        _normalize_public_title("Retail_Trends_2026_2026.pdf...")
        == "Retail Trends 2026"
    )
    assert (
        _seo_description(
            "A concise source-backed market update ends here. Extra copy is excluded.",
            fallback="Digest for Retail Trends 2026.",
            max_length=48,
        )
        == "A concise source-backed market update ends here."
    )
    assert (
        _seo_description(
            "A deliberately overlong description without punctuation " * 8,
            fallback="Digest for Retail Trends 2026.",
            max_length=80,
        )
        == "Digest for Retail Trends 2026."
    )


@pytest.mark.parametrize(
    ("description", "max_length", "expected"),
    [
        (
            "IAB reports $258.6 billion in internet advertising revenue. "
            "Later context is excluded.",
            65,
            "IAB reports $258.6 billion in internet advertising revenue.",
        ),
        (
            "Growth reached 12.5%, with $1.3T and €2.4bn in tracked activity. "
            "Later context is excluded.",
            75,
            "Growth reached 12.5%, with $1.3T and €2.4bn in tracked activity.",
        ),
        (
            "The U.S. market remained the largest contributor. "
            "Later context is excluded.",
            55,
            "The U.S. market remained the largest contributor.",
        ),
        (
            "The first finding is complete. "
            "The second finding is excluded by the maximum.",
            35,
            "The first finding is complete.",
        ),
    ],
)
def test_seo_description_keeps_decimals_and_recognizes_real_sentence_boundaries(
    description: str, max_length: int, expected: str
) -> None:
    assert (
        _seo_description(
            description,
            fallback="Digest for Retail Trends 2026.",
            max_length=max_length,
        )
        == expected
    )


def test_seo_description_never_exceeds_its_maximum_length() -> None:
    description = (
        "A complete source-backed finding ends here. Another sentence is excluded."
    )

    result = _seo_description(
        description,
        fallback="Digest for Retail Trends 2026.",
        max_length=43,
    )

    assert result == "A complete source-backed finding ends here."
    assert len(result) <= 43


@pytest.mark.parametrize(
    "description",
    [
        "Revenue reached $258.6 billion before the longer finding can finish",
        "Growth reached 12.5% with $1.3T and €2.4bn before the longer "
        "finding can finish",
        "The U.S. market remained the largest contributor before the longer "
        "finding can finish",
    ],
)
def test_seo_description_uses_fallback_instead_of_partial_decimal_or_abbreviation(
    description: str,
) -> None:
    fallback = "Digest for Retail Trends 2026."

    assert _seo_description(description, fallback=fallback, max_length=25) == fallback


def test_iab_compact_tldr_drives_all_rendered_metadata_descriptions(
    tmp_path: Path,
) -> None:
    compact_tldr = "IAB reports $258.6 billion in internet advertising revenue."
    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data={
                "title": "IAB Internet Advertising Revenue Report",
                "artifacts": {
                    "summary": {
                        "card_tldr_compact": compact_tldr,
                        "tldr": (
                            "A generic TLDR that must not be used for SEO metadata."
                        ),
                        "executive_summary": (
                            "A generic executive summary that must not be used."
                        ),
                    }
                },
            },
            doc_name="iab-report.pdf",
            file_id="iab-report",
            out_dir=str(tmp_path),
            preview_png=None,
        ),
        _ctx(),
    )

    html = Path(response.html_path).read_text(encoding="utf-8")
    descriptions = re.findall(
        r'<meta (?:name|property)="(?:description|og:description|twitter:description)" '
        r'content="([^"]+)">',
        html,
    )
    json_ld_match = re.search(
        r'<script type="application/ld\+json">(.*?)</script>', html
    )

    assert descriptions == [compact_tldr, compact_tldr, compact_tldr]
    assert json_ld_match is not None
    assert json.loads(json_ld_match.group(1))["description"] == compact_tldr
    assert "$258.6 billion" in descriptions[0]
    assert descriptions[0] != "$258."


def test_public_citation_label_rejects_internal_provenance_identifiers() -> None:
    assert _public_citation_label('"finding_4_deal_math_harder_2025"') == ""
    assert _public_citation_label('finding_4_deal_math_harder_"12_is_the_new_5"') == ""
    assert _public_citation_label("quote_candidates") == ""
    assert _public_citation_label('"Market report"') == '"Market report"'


@pytest.mark.parametrize(
    ("source_title", "max_length", "public_title"),
    [
        (
            "Trusted Execution Environments in Digital Advertising: "
            "A Pathway to Enhanced Data Privacy, Security, and Regulatory Compliance",
            110,
            "Trusted Execution Environments in Digital Advertising",
        ),
        (
            "The gaming app insights report: 2026 edition",
            110,
            "The gaming app insights report: 2026 edition",
        ),
        (
            "Mobile app trends spotlight edition: LATAM 2026",
            110,
            "Mobile app trends spotlight edition: LATAM 2026",
        ),
        (
            "A deliberately long primary report name that must remain intact",
            20,
            "A deliberately long primary report name that must remain intact",
        ),
        (
            "Long primary report name — explanatory subtitle that exceeds the limit",
            20,
            "Long primary report name",
        ),
    ],
)
def test_public_title_preserves_full_title_when_it_fits_and_never_cuts_primary_name(
    source_title: str,
    max_length: int,
    public_title: str,
) -> None:
    assert _normalize_public_title(source_title, max_length=max_length) == public_title


def test_render_removes_inline_internal_evidence_tokens_from_public_prose(
    tmp_path: Path,
) -> None:
    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data={
                "title": "Evidence Token Report",
                "insights": [],
                "quote": {"text": "", "author": ""},
                "artifacts": {
                    "summary": {
                        "tldr": "The retained signal is actionable (IC1).",
                        "executive_summary": "The action follows IC-02.",
                    },
                    "expert_comment": "Leaders should act on the signal (IC3).",
                },
            },
            doc_name="evidence-token.pdf",
            file_id="file-evidence-token",
            out_dir=str(tmp_path),
            preview_png=None,
        ),
        _ctx(),
    )

    html = Path(response.html_path).read_text(encoding="utf-8")

    assert "IC1" not in html
    assert "IC-02" not in html
    assert "IC3" not in html
    assert "The retained signal is actionable." in html


def test_render_removes_provider_file_citations_from_public_topics(
    tmp_path: Path,
) -> None:
    marker = "\ue200filecite\ue202turn0file4\ue202turn0file2\ue201"
    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data={
                "title": "Automation report",
                "artifacts": {
                    "topics_covered": [
                        {
                            "topic": "Automated email",
                            "why_it_matters": (
                                "Automated emails generated 41% of orders from 2% "
                                f"of sends. {marker}"
                            ),
                            "subtopics": [f"Conversion increased. {marker}"],
                            "pages": [8],
                        }
                    ],
                    "key_figures": [
                        {
                            "value": "41%",
                            "label": "Automated email order share",
                            "context": f"From 2% of sends. {marker}",
                        }
                    ],
                },
                "evidence_packs": {
                    "methods": {
                        "methods": [
                            {"description": (f"Analyzes 2023 merchant sends. {marker}")}
                        ]
                    }
                },
            },
            doc_name="automation.pdf",
            file_id="automation",
            out_dir=str(tmp_path),
            preview_png=None,
        ),
        _ctx(),
    )

    html = Path(response.html_path).read_text(encoding="utf-8")
    assert marker not in html
    assert "turn0file" not in html
    assert "Automated emails generated 41% of orders from 2% of sends." in html
    assert "Conversion increased." in html
    assert "From 2% of sends." in html
    assert "Analyzes 2023 merchant sends." in html
    assert "Pages 8" in html


def test_render_preserves_linkedin_paragraphs_without_markdown_emphasis(
    tmp_path: Path,
) -> None:
    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data={
                "title": "LinkedIn formatting report",
                "artifacts": {
                    "linkedin_post": (
                        "*Activate Technology & Media Outlook: 2026 Edition*\n\n"
                        "The source-backed angle survives as a second paragraph."
                    )
                },
            },
            doc_name="linkedin-formatting.pdf",
            file_id="linkedin-formatting",
            out_dir=str(tmp_path),
            preview_png=None,
        ),
        _ctx(),
    )

    html = Path(response.html_path).read_text(encoding="utf-8")

    assert "*Activate Technology" not in html
    assert (
        "Activate Technology & Media Outlook: 2026 Edition\n\nThe source-backed" in html
    )


def test_render_does_not_repeat_toc_summaries_across_public_sections(
    tmp_path: Path,
) -> None:
    repeated_summary = (
        "This report explains how a source-backed market signal informs decisions."
    )
    response = render_report(
        RenderRequest(
            schema_version="1.0",
            data={
                "title": "Signal report",
                "artifacts": {
                    "toc_topics": ["Market signal"],
                    "topics_covered": [
                        {
                            "topic": "Market signal",
                            "why_it_matters": repeated_summary,
                            "subtopics": [
                                "Prioritise the decision the signal supports."
                            ],
                            "pages": [2],
                        }
                    ],
                    "toc_topics_expanded": [
                        {
                            "topic": "Market signal",
                            "summary": repeated_summary,
                            "key_points": [
                                "Prioritise the decision the signal supports."
                            ],
                        }
                    ],
                    "toc_entries": [
                        {
                            "display_title": "Market signal",
                            "summary": repeated_summary,
                            "pages": [2],
                            "order": 1,
                        }
                    ],
                },
            },
            doc_name="signal.pdf",
            file_id="file-signal",
            out_dir=str(tmp_path),
            preview_png=None,
        ),
        _ctx(),
    )

    html = Path(response.html_path).read_text(encoding="utf-8")

    assert html.count(repeated_summary) == 1
