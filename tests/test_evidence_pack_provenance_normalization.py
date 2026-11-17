import pytest

from src.generators.evidence_packs.findings_strategy import normalize_findings
from src.utils.errors import AppError


def test_findings_do_not_truncate_fractional_physical_pages():
    findings = normalize_findings(
        [{"id": "f1", "text": "A finding", "evidence": "Source", "pages": [2.9]}]
    )

    assert findings[0]["pages"] == []


def test_findings_preserve_integral_page_representations():
    findings = normalize_findings(
        [{"id": "f1", "text": "A finding", "evidence": "Source", "pages": [2.0, "3"]}]
    )

    assert findings[0]["pages"] == [2, 3]


def test_multiple_distinct_evidence_fragments_are_not_silently_dropped():
    with pytest.raises(AppError) as error:
        normalize_findings(
            [{"id": "f1", "text": "A finding", "evidence": ["first", "second"]}]
        )

    assert error.value.code == "findings_evidence_fragments_unsupported"


def test_repeated_identical_evidence_does_not_require_recovery():
    findings = normalize_findings(
        [{"id": "f1", "text": "A finding", "evidence": ["same", "same"]}]
    )

    assert findings[0]["evidence"] == "same"
