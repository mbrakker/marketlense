from __future__ import annotations


def test_findings_target_coverage_requires_each_numeric_relationship():
    from src.generators.evidence_pack_generator import _findings_target_is_covered

    target = {
        "id": "gaming",
        "title": "Finding and keeping users",
        "pages": [19],
        "key_points": [
            "Casino installs +22% and sessions -5%; slots installs +46% "
            "and sessions -5%."
        ],
    }
    findings = [
        {
            "id": "only-casino-pair",
            "section_id": "gaming",
            "text": "Casino installs grew 22%; slots installs grew 46%.",
            "evidence": (
                "Casino installs +22%, sessions -5%; slots installs +46%, sessions -5%."
            ),
            "pages": [19],
        }
    ]

    assert not _findings_target_is_covered(
        target, findings, {"only-casino-pair"}, [target]
    )


def test_findings_target_numbers_ignore_chart_identifiers():
    from src.generators.evidence_pack_generator import (
        _findings_target_number_markers,
    )

    assert _findings_target_number_markers(
        "Figure 9, October 2025: money-off promotions 75%, percentage-off 74%, "
        "and buy-one-get-one-free 73%.",
    ) == {"2025", "75%", "74%", "73%"}


def test_findings_target_coverage_falls_back_for_relationships_split_across_claims():
    from src.generators.evidence_pack_generator import _findings_target_is_covered

    target = {
        "id": "gaming",
        "title": "Finding and keeping users",
        "pages": [18],
        "key_points": [
            "Casino installs +22% and sessions -5%; slots installs +46% "
            "and sessions -5%."
        ],
    }
    findings = [
        {
            "id": "casino-pair",
            "section_id": "gaming",
            "text": "Casino installs grew 22% and sessions fell 5% in 2025.",
            "evidence": "Casino installs +22%; sessions -5% in 2025.",
            "pages": [19],
        },
        {
            "id": "slots-pair",
            "section_id": "gaming",
            "text": "Slots installs grew 46% and sessions fell 5% in 2025.",
            "evidence": "Slots installs +46%; sessions -5% in 2025.",
            "pages": [19],
        },
    ]

    assert not _findings_target_is_covered(
        target, findings, {"casino-pair", "slots-pair"}, [target]
    )


def test_findings_target_coverage_falls_back_for_equivalent_numeric_formatting():
    from src.generators.evidence_pack_generator import _findings_target_is_covered

    target = {
        "id": "market-growth",
        "title": "Market growth",
        "pages": [4],
        "key_point": "Global revenue increased to $0.3T in 2025.",
    }
    findings = [
        {
            "id": "market-growth-2025",
            "section_id": "market-growth",
            "text": "Global revenue rose to $300 billion in 2025.",
            "evidence": "Global revenue reached $300 billion in 2025.",
            "pages": [5],
        }
    ]

    assert not _findings_target_is_covered(
        target, findings, {"market-growth-2025"}, [target]
    )


def test_findings_target_coverage_falls_back_for_qualitative_paraphrase():
    from src.generators.evidence_pack_generator import _findings_target_is_covered

    target = {
        "id": "portfolio-simplification",
        "title": "Portfolio simplification as a value creation strategy",
        "pages": [18],
        "key_point": (
            "Portfolio simplification can unlock value for buyers and sellers."
        ),
    }
    findings = [
        {
            "id": "carve-out-value",
            "section_id": "portfolio-simplification",
            "text": (
                "Carve-outs can simplify portfolios and unlock value for buyers "
                "and sellers."
            ),
            "evidence": (
                "Carve-outs can simplify portfolios and unlock value for buyers "
                "and sellers."
            ),
            "pages": [19],
        }
    ]

    assert not _findings_target_is_covered(
        target, findings, {"carve-out-value"}, [target]
    )


def test_findings_target_coverage_does_not_compare_printed_and_physical_page_numbers():
    from src.generators.evidence_pack_generator import _findings_target_is_covered

    target = {
        "id": "revenue-growth",
        "title": "Revenue growth",
        "pages": [4],  # DocMap printed label; source page is physical PDF page 5.
        "key_point": "Revenue increased 12% in 2025.",
    }
    findings = [
        {
            "id": "revenue-growth-2025",
            "section_id": "revenue-growth",
            "text": "Revenue increased 12% in 2025.",
            "evidence": "Revenue increased 12% in 2025.",
            "pages": [5],
        }
    ]

    assert _findings_target_is_covered(
        target, findings, {"revenue-growth-2025"}, [target]
    )


def test_findings_target_coverage_rejects_values_swapped_between_subjects():
    from src.generators.evidence_pack_generator import _findings_target_is_covered

    target = {
        "id": "benchmarks",
        "title": "Growth by category",
        "pages": [19],
        "key_points": ["Casino 22%; Slots 46%."],
    }
    findings = [
        {
            "id": "swapped-categories",
            "section_id": "benchmarks",
            "text": "Casino 46%; Slots 22%.",
            "evidence": "Casino 22%; Slots 46%.",
            "pages": [19],
        }
    ]

    assert not _findings_target_is_covered(
        target, findings, {"swapped-categories"}, [target]
    )


def test_grounded_finding_paraphrase_leaves_target_uncertain_for_fallback():
    from src.generators.evidence_pack_generator import (
        _missing_findings_retrieval_targets,
    )

    target = {
        "id": "portfolio-simplification",
        "title": "Portfolio simplification",
        "key_point": (
            "Portfolio simplification can unlock value for buyers and sellers."
        ),
        "pages": [18],
    }
    findings = [
        {
            "id": "carve-out-value",
            "section_id": "portfolio-simplification",
            "text": (
                "Carve-outs can simplify portfolios and unlock value for buyers "
                "and sellers."
            ),
            "evidence": (
                "Carve-outs can simplify portfolios and unlock value for buyers "
                "and sellers."
            ),
            "pages": [19],
        }
    ]

    assert _missing_findings_retrieval_targets(
        [target], findings, {"carve-out-value"}
    ) == [target]


def test_fallback_dedup_keeps_distinct_claims_with_shared_numbers():
    from src.generators.evidence_pack_generator import (
        _merge_supported_fallback_findings,
    )

    primary = {
        "id": "casino-installs-2025",
        "section_id": "gaming",
        "text": "Casino installs rose 22% in 2025.",
        "evidence": "Casino installs +22% in 2025.",
        "pages": [19],
    }
    fallback = [
        {
            "id": "casino-installs-repeat",
            "section_id": "gaming",
            "text": "  casino installs rose 22% in 2025. ",
            "evidence": "The same result appears in a different excerpt.",
            "pages": [19],
        },
        {
            "id": "slots-installs-2025",
            "section_id": "gaming",
            "text": "Slots installs rose 22% in 2025.",
            "evidence": "Slots installs +22% in 2025.",
            "pages": [19],
        },
        {
            "id": "casino-sessions-2025",
            "section_id": "gaming",
            "text": "Casino sessions rose 22% in 2025.",
            "evidence": "Casino sessions +22% in 2025.",
            "pages": [19],
        },
        {
            "id": "casino-installs-2024",
            "section_id": "gaming",
            "text": "Casino installs rose 22% in 2024.",
            "evidence": "Casino installs +22% in 2024.",
            "pages": [19],
        },
        {
            "id": "same-claim-other-section",
            "section_id": "retail",
            "text": "Casino installs rose 22% in 2025.",
            "evidence": "Casino installs +22% in 2025.",
            "pages": [19],
        },
    ]

    merged = _merge_supported_fallback_findings(
        [primary], {"casino-installs-2025"}, fallback
    )

    assert [item["id"] for item in merged] == [
        "casino-installs-2025",
        "slots-installs-2025",
        "casino-sessions-2025",
        "casino-installs-2024",
        "same-claim-other-section",
    ]


def test_missing_findings_targets_checks_all_bounded_targets_and_returns_two():
    from src.generators.evidence_pack_generator import (
        _missing_findings_retrieval_targets,
    )

    targets = [
        {
            "id": f"section-{index}",
            "title": f"Section {index}",
            "key_point": f"Section {index} has a source-backed result.",
            "pages": [index],
        }
        for index in range(1, 5)
    ]
    findings = [
        {
            "id": f"finding-{index}",
            "section_id": f"section-{index}",
            "text": f"Section {index} has a source-backed result.",
            "evidence": f"Section {index} has a source-backed result.",
            "pages": [index],
        }
        for index in (1, 2)
    ]

    assert (
        _missing_findings_retrieval_targets(
            targets, findings, {"finding-1", "finding-2"}
        )
        == targets[2:4]
    )
