from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pymupdf as fitz
import pytest

from src.utils.text_normalization import normalize_for_lookup

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = (
    REPOSITORY_ROOT
    / "docs/quality/verified-claims-step2-adversarial-corpus-20261020.json"
)


def _corpus() -> dict[str, object]:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def test_adversarial_corpus_covers_each_required_mutation_boundary() -> None:
    corpus = _corpus()
    cases = corpus.get("cases")
    assert isinstance(cases, list)
    assert len(cases) == 9
    assert len({case["case_id"] for case in cases}) == len(cases)
    assert {case["mutation"] for case in cases} >= {
        "metric_unit",
        "metric_label_relationship",
        "cohort_denominator",
        "geography",
        "forecast_observation_status",
        "reporting_period",
        "physical_source_page",
        "unsupported_causal_interpretation",
        "conflicting_chart_total",
    }
    for case in cases:
        assert case["report"]
        assert case["candidate_id"]
        assert case["original_claim"]
        assert case["evidence_id"]
        assert case["physical_pages"]
        assert case["source_anchor"]
        assert case["source_truth"]
        assert case["replacement_policy"] in {
            "report_level_replacement_allowed",
            "strict_original_direction",
        }
        assert case["expected_terminal"] in {
            "verified_or_corrected",
            "unresolved_or_failed",
        }


@pytest.mark.integration
def test_adversarial_corpus_binds_to_hash_matched_actual_pdfs() -> None:
    corpus = _corpus()
    manifest_path = REPOSITORY_ROOT / str(corpus["source_manifest"])
    if not manifest_path.is_file():
        pytest.skip("retained second-cohort source manifest is not available locally")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_records = manifest.get("source_pdfs")
    assert isinstance(source_records, dict)

    for case in corpus["cases"]:
        source = source_records[case["report"]]
        pdf_path = Path(str(source["path"]))
        if not pdf_path.is_absolute():
            pdf_path = REPOSITORY_ROOT / pdf_path
        if not pdf_path.is_file():
            pytest.skip(f"source PDF unavailable locally: {case['report']}")
        actual_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        assert actual_hash == str(source["sha256"]).lower()
        with fitz.open(pdf_path) as document:
            page_count = document.page_count
            for page_number in case["physical_pages"]:
                assert 1 <= page_number <= page_count
                page_text = normalize_for_lookup(document[page_number - 1].get_text())
                assert page_text
        assert len(normalize_for_lookup(case["source_truth"])) >= 24
