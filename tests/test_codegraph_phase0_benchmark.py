from __future__ import annotations

from scripts.quality.codegraph_phase0_benchmark import (
    _mcp_text,
    discovery_files_from_text,
    evaluate_phase0,
    native_discovery_files,
)


def test_native_discovery_files_comes_only_from_actual_command_output() -> None:
    output = (
        "src/services/file_service.py\n"
        "notes about an API contract\n"
        "tests/test_file_service.py\n"
    )

    assert native_discovery_files(output) == (
        "src/services/file_service.py",
        "tests/test_file_service.py",
    )


def test_codegraph_discovery_files_keeps_non_reference_paths_from_actual_output() -> (
    None
):
    output = "- `src/services/file_service.py` calls `src/contracts/files.py`\n"

    assert discovery_files_from_text(output) == (
        "src/services/file_service.py",
        "src/contracts/files.py",
    )


def test_mcp_text_joins_text_blocks_and_rejects_malformed_results() -> None:
    assert (
        _mcp_text(
            {
                "result": {
                    "content": [
                        {"type": "text", "text": "first"},
                        {"type": "image", "data": "ignored"},
                        {"type": "text", "text": "second"},
                    ]
                }
            }
        )
        == "first\nsecond"
    )


def test_evaluate_phase0_rejects_missed_files_and_unmet_targets() -> None:
    report = evaluate_phase0(
        native_rows=(
            {
                "case_id": "ML-ARCH-001",
                "relevant_file_recall": 1.0,
                "structural_conclusion": "correct",
                "retrieval_calls": 4,
                "token_proxy": 400,
                "elapsed_ms": 400,
            },
        ),
        codegraph_rows=(
            {
                "case_id": "ML-ARCH-001",
                "relevant_file_recall": 0.5,
                "structural_conclusion": "correct",
                "retrieval_calls": 1,
                "token_proxy": 500,
                "elapsed_ms": 450,
            },
        ),
        thresholds={
            "retrieval_calls_reduction_percent": 50,
            "token_proxy_reduction_percent": 25,
            "elapsed_time_reduction_percent": 30,
        },
    )

    assert report["passed"] is False
    assert "missed_relevant_files:ML-ARCH-001" in report["failures"]
    assert "token_proxy_target_not_met" in report["failures"]
    assert "elapsed_time_target_not_met" in report["failures"]


def test_evaluate_phase0_accepts_correct_retrieval_with_target_improvements() -> None:
    report = evaluate_phase0(
        native_rows=(
            {
                "case_id": "ML-ARCH-001",
                "relevant_file_recall": 1.0,
                "structural_conclusion": "correct",
                "retrieval_calls": 4,
                "token_proxy": 400,
                "elapsed_ms": 400,
            },
        ),
        codegraph_rows=(
            {
                "case_id": "ML-ARCH-001",
                "relevant_file_recall": 1.0,
                "structural_conclusion": "correct",
                "retrieval_calls": 1,
                "token_proxy": 250,
                "elapsed_ms": 200,
            },
        ),
        thresholds={
            "retrieval_calls_reduction_percent": 50,
            "token_proxy_reduction_percent": 25,
            "elapsed_time_reduction_percent": 30,
        },
    )

    assert report["passed"] is True
    assert report["aggregate"]["retrieval_calls_reduction_percent"] == 75.0
    assert report["aggregate"]["token_proxy_reduction_percent"] == 37.5
    assert report["aggregate"]["elapsed_time_reduction_percent"] == 50.0
