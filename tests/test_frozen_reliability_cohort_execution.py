from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.quality.ias_live_canary_runner import summarize_frozen_cohort_results
from scripts.quality.run_frozen_reliability_cohort import run_frozen_reliability_cohort


def test_frozen_cohort_runs_selected_members_with_independent_report_deadlines(
    tmp_path: Path,
) -> None:
    members = []
    report_ids = []
    for index in range(5):
        source_path = tmp_path / f"source-{index}.pdf"
        content = f"frozen-cohort-fixture-{index}".encode("utf-8")
        source_path.write_bytes(content)
        content_md5 = hashlib.md5(content, usedforsecurity=False).hexdigest()
        if index in {1, 3}:
            report_ids.append(f"cohort-{content_md5[:20]}")
        members.append(
            {
                "source_path": str(source_path.resolve()),
                "content_md5": content_md5,
                "source_domain": "publisher.example",
                "report_name": f"Frozen fixture {index}",
                "landing_page_url": f"https://publisher.example/reports/{index}",
                "source_page_url": "https://publisher.example/reports",
                "publisher_name": "Fixture Publisher",
                "downloaded_at_utc": "2026-09-01T00:00:00Z",
            }
        )
    manifest = tmp_path / "cohort.json"
    manifest.write_text(json.dumps({"members": members}), encoding="utf-8")
    captured: list[dict[str, object]] = []
    reuse_telemetry = {
        "artifact_path": "validation_claim_reuse_decisions.jsonl",
        "event_count": 1,
        "invalid_event_count": 0,
        "totals_across_validation_passes": {"reused_validation_results": 2},
        "reuse_fallback_reason_counts": {},
    }

    def run_once(**kwargs):
        captured.append(kwargs)
        source = kwargs["sources"][0]
        report_id = f"cohort-{source['content_md5'][:20]}"
        index = int(source["report_name"].rsplit(" ", maxsplit=1)[1])
        return {
            "git_sha": "a" * 40,
            "run_directory": str(kwargs["runs_root"] / "production-run"),
            "reports": [
                {
                    "report_id": report_id,
                    "admission_outcome": "admitted",
                    "final_state": "awaiting_review",
                    "terminal_failure_code": "",
                    "awaiting_review": True,
                    "publication_readiness": "pass",
                    "bounded_automatic_repair": False,
                    "operator_intervention": False,
                }
            ],
            "cohort_metrics": {
                "model_provider_calls": index + 1,
                "input_tokens": 100 * (index + 1),
                "output_tokens": 10 * (index + 1),
                "cost_usd": 0.1 * (index + 1),
                "duration_seconds": 12.0 * (index + 1),
                "validation_reuse_telemetry": reuse_telemetry,
                "bounded_automatic_repair": False,
                "operator_intervention_count": 0,
            },
        }

    result = run_frozen_reliability_cohort(
        sources_manifest=manifest,
        sources_root=tmp_path,
        runs_root=tmp_path,
        report_ids=tuple(report_ids),
        max_duration_seconds=984,
        run_cohort_once=run_once,
    )

    assert len(captured) == 2
    assert all(len(call["sources"]) == 1 for call in captured)
    assert all(call["max_duration_seconds"] == 984 for call in captured)
    assert len({str(call["runs_root"]) for call in captured}) == 2
    assert [report["report_id"] for report in result["reports"]] == report_ids
    assert all(
        report["validation_reuse_telemetry"] == reuse_telemetry
        for report in result["reports"]
    )
    assert all(
        report["metric_attribution"] == "per_report_isolated_workflow"
        for report in result["reports"]
    )
    assert result["cohort_size"] == 2
    assert result["git_sha"] == "a" * 40
    assert result["cohort_metrics"]["model_provider_calls"] == sum(range(2, 5, 2))
    assert result["cohort_metrics"]["cost_usd"] == 0.6
    assert result["summary"]["mean_cost"] == 0.3
    retained = json.loads(
        Path(result["cohort_directory"])
        .joinpath("cohort_result.json")
        .read_text(encoding="utf-8")
    )
    assert retained["git_sha"] == "a" * 40
    assert retained["cohort_size"] == 2
    assert all(
        report["validation_reuse_telemetry"] == reuse_telemetry
        for report in retained["reports"]
    )


def test_frozen_cohort_can_run_one_shared_cross_report_batch_with_all_members(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source-workspace"
    source_root.mkdir()
    members = []
    for index in range(5):
        relative_path = Path("out") / f"frozen-{index}.pdf"
        source_path = source_root / relative_path
        source_path.parent.mkdir(parents=True, exist_ok=True)
        content = f"shared-staging-cohort-{index}".encode("utf-8")
        source_path.write_bytes(content)
        members.append(
            {
                "source_path": relative_path.as_posix(),
                "content_md5": hashlib.md5(content, usedforsecurity=False).hexdigest(),
                "source_domain": "publisher.example",
                "report_name": f"Frozen report {index}",
                "landing_page_url": f"https://publisher.example/reports/{index}",
                "source_page_url": "https://publisher.example/reports",
                "publisher_name": "Fixture Publisher",
                "downloaded_at_utc": "2026-10-01T00:00:00Z",
            }
        )
    manifest = tmp_path / "frozen.json"
    manifest.write_text(json.dumps({"members": members}), encoding="utf-8")
    captured: list[dict[str, object]] = []

    def run_once(**kwargs):
        captured.append(kwargs)
        reports = [
            {
                "report_id": f"cohort-{item['content_md5'][:20]}",
                "admission_outcome": "admitted",
                "final_state": "published",
                "awaiting_review": False,
                "published": True,
                "workflow_attempt_count": 1,
                "publication_readiness": "pass",
                "terminal_failure_code": "",
            }
            for item in kwargs["sources"]
        ]
        return {
            "git_sha": "b" * 40,
            "run_directory": str(kwargs["runs_root"] / "isolated-run"),
            "reports": reports,
            "cohort_metrics": {
                "model_provider_calls": 5,
                "input_tokens": 500,
                "output_tokens": 100,
                "cost_usd": 0.25,
                "duration_seconds": 90.0,
                "operator_intervention_count": 0,
            },
        }

    result = run_frozen_reliability_cohort(
        sources_manifest=manifest,
        sources_root=source_root,
        runs_root=tmp_path / "runs",
        shared_batch=True,
        enable_cross_report_analysis=True,
        run_cohort_once=run_once,
    )

    assert len(captured) == 1
    assert len(captured[0]["sources"]) == 5
    assert captured[0]["enable_cross_report_analysis"] is True
    assert result["cohort_size"] == 5
    assert result["summary"]["published_report_count"] == 5
    assert Path(result["cohort_directory"], "cohort_result.json").is_file()


def test_staging_rejects_noncanonical_manifest_before_run_cohort_once(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "other-cohort.json"
    manifest.write_text(json.dumps({"members": []}), encoding="utf-8")
    calls: list[dict[str, object]] = []

    with pytest.raises(ValueError, match="pinned five-report manifest"):
        run_frozen_reliability_cohort(
            sources_manifest=manifest,
            runs_root=tmp_path / "runs",
            shared_batch=True,
            publish_to_wordpress_staging=True,
            staging_hostname="marketlense.medianewsonline.com",
            allow_insecure_staging_http=True,
            enable_cross_report_analysis=True,
            run_cohort_once=lambda **kwargs: calls.append(kwargs),
        )

    assert calls == []
    assert not (tmp_path / "runs").exists()


def test_cohort_summary_retains_batch_metrics_only_at_cohort_scope() -> None:
    summary = summarize_frozen_cohort_results(
        [
            {
                "report_id": "report-1",
                "admission_outcome": "admitted",
                "final_state": "failed",
                "terminal_failure_code": "typed_failure",
                "cost": None,
                "total_duration_seconds": None,
                "bounded_automatic_repair": None,
            }
        ],
        cohort_metrics={
            "cost_usd": 1.25,
            "duration_seconds": 90.0,
            "bounded_automatic_repair": True,
        },
    )

    assert summary["cohort_cost_usd"] == 1.25
    assert summary["cohort_duration_seconds"] == 90.0
    assert summary["cohort_bounded_automatic_repair"] is True
    assert summary["mean_cost"] == "unavailable"
    assert summary["mean_duration_seconds"] == "unavailable"
    assert summary["bounded_repair_rate"] == "unavailable"


def test_cohort_summary_uses_report_scoped_metrics_in_shared_batch() -> None:
    results = [
        {
            "report_id": f"report-{index}",
            "admission_outcome": "admitted",
            "final_state": "published",
            "bounded_automatic_repair": index == 2,
            "cost": float(index) / 10,
            "total_duration_seconds": float(index * 10),
            "metric_attribution": "canonical_run_and_report_id",
        }
        for index in (1, 2, 3)
    ]

    summary = summarize_frozen_cohort_results(
        results,
        cohort_metrics={
            "cost_usd": 1.0,
            "duration_seconds": 90.0,
            "bounded_automatic_repair": True,
            "model_provider_calls": 20,
            "input_tokens": 1000,
            "output_tokens": 300,
        },
    )

    assert summary["mean_cost"] == 0.2
    assert summary["median_cost"] == 0.2
    assert summary["mean_duration_seconds"] == 20
    assert summary["median_duration_seconds"] == 20
    assert summary["bounded_repair_rate"] == pytest.approx(1 / 3)
    assert (
        summary["per_report_metric_scope"] == "report_scoped_excludes_shared_handoffs"
    )
    assert summary["cohort_cost_usd"] == 1.0
    assert summary["cohort_duration_seconds"] == 90.0


def test_cohort_summary_keeps_failed_admitted_reports_in_its_denominator() -> None:
    summary = summarize_frozen_cohort_results(
        [
            {
                "admission_outcome": "admitted",
                "awaiting_review": True,
                "bounded_automatic_repair": False,
                "publication_readiness": "pass",
                "operator_intervention": False,
                "final_state": "awaiting_review",
                "terminal_failure_code": "",
                "cost": 0.30,
                "total_duration_seconds": 30.0,
            },
            {
                "admission_outcome": "admitted",
                "awaiting_review": False,
                "bounded_automatic_repair": True,
                "publication_readiness": "fail",
                "operator_intervention": False,
                "final_state": "failed",
                "terminal_failure_code": "publish_readiness_failed",
                "cost": 0.10,
                "total_duration_seconds": 10.0,
            },
            {
                "admission_outcome": "insufficient_content",
                "awaiting_review": True,
                "bounded_automatic_repair": False,
                "publication_readiness": "pass",
                "operator_intervention": True,
                "final_state": "awaiting_review",
                "terminal_failure_code": "",
                "cost": 0.20,
                "total_duration_seconds": 20.0,
            },
        ]
    )

    assert summary == {
        "report_count": 3,
        "terminal_outcome_complete": True,
        "missing_terminal_report_count": 0,
        "missing_terminal_report_ids": [],
        "admitted_report_count": 2,
        "cohort_admission_rate": 2 / 3,
        "workflow_denominator": 2,
        "first_attempt_awaiting_review_rate": 1 / 2,
        "published_report_count": 0,
        "first_attempt_published_rate": 0.0,
        "publication_readiness_rate": 1 / 2,
        "bounded_repair_rate": 1 / 2,
        "workflow_failure_rate": 1 / 2,
        "typed_terminal_rate": 1.0,
        "operator_intervention_count": 1,
        "failure_code_pareto": {"publish_readiness_failed": 1},
        "mean_cost": 0.2,
        "median_cost": 0.2,
        "mean_duration_seconds": 20.0,
        "median_duration_seconds": 20.0,
    }


def test_cohort_summary_marks_missing_terminal_outcomes_incomplete() -> None:
    summary = summarize_frozen_cohort_results(
        [
            {
                "report_id": "report-1",
                "admission_outcome": "admitted",
                "final_state": "running",
                "terminal_failure_code": "",
            }
        ]
    )

    assert summary["terminal_outcome_complete"] is False
    assert summary["missing_terminal_report_count"] == 1
    assert summary["missing_terminal_report_ids"] == ["report-1"]
