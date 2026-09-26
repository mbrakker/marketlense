from __future__ import annotations

from copy import deepcopy

from src.generators.public_editorial_quality_generator import (
    enumerate_public_editorial_items,
    evaluate_public_editorial_quality,
)
from tests._test_public_editorial_quality_generator._shared import (
    _retained_artifacts,
)


def test_public_item_inventory_and_identity_evidence_fail_closed_atomically() -> None:
    artifacts = deepcopy(_retained_artifacts())
    artifacts["public_metadata"] = {
        "title": "PowerPoint Presentation",
        "publisher": "Wrong publisher",
        "author": "Wrong author",
        "edition": "2024",
    }
    artifacts["insights_final"][0].update(
        {
            "so_what": "The source-backed finding changes the next planning review.",
            "now_what": "Compare the source-backed finding before allocating budget.",
        }
    )

    report = evaluate_public_editorial_quality(
        report_id="social-video",
        artifacts=artifacts,
        metadata_evidence={
            "title": "Activate Technology & Media Outlook 2025: Social Video",
            "publisher": "Activate Consulting",
            "author": "Activate Research",
            "edition": "2025",
        },
    )
    item_ids = {item.item_id for item in enumerate_public_editorial_items(artifacts)}
    hard_failures = {
        (issue.affected_field, issue.hard_fail_class, issue.public_item_id)
        for issue in report.issues
        if issue.hard_fail_class
    }

    assert {
        "summary:tldr",
        "summary:card_tldr_compact",
        "summary:executive_summary",
        "insight:IC-001:text",
        "insight:IC-001:so_what",
        "insight:IC-001:now_what",
        "quotes_final:quotes:1",
        "public_metadata:metadata:title",
        "public_metadata:metadata:publisher",
        "public_metadata:metadata:author",
        "public_metadata:metadata:edition",
    } <= item_ids
    assert (
        "metadata.title",
        "incorrect_report_identity",
        "public_metadata:metadata:title",
    ) in hard_failures
    assert (
        "metadata.publisher",
        "incorrect_publisher_author_attribution",
        "public_metadata:metadata:publisher",
    ) in hard_failures
    assert (
        "metadata.edition",
        "incorrect_timeframe",
        "public_metadata:metadata:edition",
    ) in hard_failures
    assert report.publishable is False


def test_json_ld_provenance_conflict_fails_metadata_only_repair() -> None:
    report = evaluate_public_editorial_quality(
        report_id="digital-2022-sweden",
        artifacts={},
        metadata_evidence={"publisher": "DataReportal", "author": "Simon Kemp"},
        html=(
            '<h1 id="report-title">Digital 2022: Sweden</h1>'
            '<script type="application/ld+json">'
            '{"publisher":{"@type":"Organization","name":"Kepios"},'
            '"author":{"@type":"Organization","name":"Kepios"}}'
            "</script>"
        ),
    )

    assert report.publishable is False
    assert {
        (issue.affected_field, issue.hard_fail_class, issue.repair_target)
        for issue in report.issues
    } >= {
        ("json_ld.publisher", "incorrect_publisher_author_attribution", "metadata"),
        ("json_ld.author", "incorrect_publisher_author_attribution", "metadata"),
    }
