import ast
import inspect

from src.generators.validation import evidence
from src.generators.validation.evidence import (
    build_evidence_windows,
    char_ngram_counts,
    retrieve_evidence_windows,
)


def test_build_evidence_windows_stores_precomputed_char_vectors() -> None:
    windows = build_evidence_windows(
        ["Retail media revenue grew 17% in 2025 as loyalty data improved."]
    )

    assert len(windows) == 1
    window = windows[0]
    expected_counts = char_ngram_counts(window.text, n=3)
    assert window.char_ngram_counts == expected_counts
    assert window.char_ngram_norm == sum(
        value * value for value in expected_counts.values()
    ) ** 0.5
    assert window.char_ngram_norm > 0.0


def test_retrieve_evidence_windows_uses_bounded_top_k_without_full_sort() -> None:
    source = inspect.getsource(evidence.retrieve_evidence_windows)
    tree = ast.parse(source)

    assert "heapq" in source
    assert ".sort(" not in source
    assert "sorted(scored" not in source
    assert "sorted(ranked" not in source


def test_retrieve_evidence_windows_preserves_tie_and_duplicate_order() -> None:
    windows = build_evidence_windows(
        [
            "Alpha beta adoption rose in the enterprise segment.",
            "Alpha beta adoption rose in the enterprise segment.",
            "Unrelated checkout commentary with no overlap.",
        ]
    )

    retrieved = retrieve_evidence_windows(
        "Alpha beta adoption rose",
        windows,
        top_k=1,
    )

    assert [window.idx for window in retrieved] == [0, 1]


def test_retrieve_evidence_windows_prioritizes_quantity_heavy_claims() -> None:
    windows = build_evidence_windows(
        [
            "Retail media revenue grew 17% in 2025 after self-service adoption.",
            "Retail media revenue grew 12% in 2025 after managed-service demand.",
            "Brand awareness improved without a reported growth percentage.",
        ]
    )

    retrieved = retrieve_evidence_windows(
        "Revenue grew 17% in 2025.",
        windows,
        top_k=1,
    )

    assert retrieved
    assert retrieved[0].idx == 0
    assert "17%" in retrieved[0].text


def test_retrieve_evidence_windows_handles_empty_inputs() -> None:
    windows = build_evidence_windows(["Retail media revenue grew 17%."])

    assert retrieve_evidence_windows("", windows) == []
    assert retrieve_evidence_windows("   ", windows) == []
    assert retrieve_evidence_windows("Retail media revenue grew 17%.", []) == []


def test_retrieve_evidence_windows_handles_long_pdf_text_with_stable_order() -> None:
    prefix_tokens = [f"prefix{i}" for i in range(430)]
    target_tokens = (
        "retail media networks reported 17% revenue growth from loyalty audiences "
        "and closed loop measurement"
    ).split()
    suffix_tokens = [f"suffix{i}" for i in range(430)]
    long_text = " ".join(prefix_tokens + target_tokens + suffix_tokens)
    windows = build_evidence_windows([long_text])

    retrieved = retrieve_evidence_windows(
        "closed loop measurement drove 17% retail media revenue growth",
        windows,
        top_k=2,
    )

    assert len(windows) > 1
    assert retrieved
    assert [window.idx for window in retrieved] == sorted(
        window.idx for window in retrieved
    )
    assert any("17%" in window.text for window in retrieved)
