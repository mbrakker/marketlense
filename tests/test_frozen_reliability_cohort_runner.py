from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from scripts.quality.ias_live_canary_runner import (
    _read_verified_facts_architecture_evidence,
    run_first_attempt_canary,
)
from scripts.quality.run_frozen_reliability_cohort import (
    DEFAULT_SOURCES_MANIFEST,
    STAGING_FROZEN_COHORT_REPORT_IDS,
    _load_members,
    _shared_batch_passes,
)
from src.utils.cache_utils import sha256_json
from src.utils.verified_facts import canonical_verified_evidence_packs
from tests._test_validation_queue_lineage._shared import (
    _full_chain_chat_response_factory,
    _full_chain_response_factory,
)


def test_verified_architecture_rejects_a_legacy_artifact_snapshot(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "retained.pdf"
    source_path.write_bytes(b"retained source snapshot")
    artifacts_path = tmp_path / "artifacts.json"
    artifacts_path.write_text(
        json.dumps(
            {
                "schema_version": "3.0",
                "insights_final": [
                    {
                        "id": "legacy-1",
                        "text": "A legacy insight",
                        "evidence_id": "finding-1",
                    }
                ],
                "_cache": {"visual_authority_canary": {"enabled": False}},
            }
        ),
        encoding="utf-8",
    )

    evidence = _read_verified_facts_architecture_evidence(
        artifact_path=artifacts_path,
        source_path=source_path,
    )

    assert evidence["passed"] is False
    assert evidence["failure_code"] == "verified_facts_artifacts_missing"


def test_verified_architecture_accepts_a_hash_bound_canonical_snapshot(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "retained.pdf"
    source_path.write_bytes(b"retained source snapshot")
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    source_identity = f"report|pdf-sha256:{source_sha256}"
    fact = {
        "schema_version": "1.0",
        "fact_id": "fact-1",
        "statement": "Revenue reached 12% in 2025.",
        "metric": {"label": "Revenue", "value": "12%", "unit": "percent"},
        "qualifiers": [],
        "source_identity": source_identity,
        "source_pdf_sha256": source_sha256,
        "supporting_physical_pages": [1],
        "verification_outcome": "verified",
        "provenance": {
            "inspected_physical_pages": [1],
            "source_truth_notes_by_page": {"1": "The page supports the fact."},
        },
    }
    facts = [fact]
    evidence_packs = canonical_verified_evidence_packs({"fact-1": fact})
    digest = sha256_json({"source_identity": source_identity, "verified_facts": facts})
    verified_evidence_id = "verified-fact:fact-1"
    span = {
        "evidence_id": verified_evidence_id,
        "source_pack": "verified_facts",
        "page": 1,
        "text": "The page supports the fact.",
        "source_identity": source_identity,
    }
    artifact_item = {
        "id": "fact-1",
        "text": fact["statement"],
        "evidence_id": verified_evidence_id,
        "pages": [1],
        "evidence_spans": [span],
    }
    artifacts = {
        "schema_version": "3.0",
        "verified_facts": facts,
        "insights_candidates": [artifact_item],
        "insights_final": [artifact_item],
        "_cache": {
            "visual_authority_canary": {
                "enabled": True,
                "digest": digest,
                "verified_fact_digest": digest,
                "verified_facts": facts,
                "verified_evidence_packs": evidence_packs,
                "audit": {
                    "expected_count": 1,
                    "evaluated_count": 1,
                    "admitted_count": 1,
                    "verified_fact_count": 1,
                    "quarantined_count": 0,
                    "coverage_complete": True,
                },
            }
        },
    }
    artifacts_path = tmp_path / "artifacts.json"
    artifacts_path.write_text(json.dumps(artifacts), encoding="utf-8")

    evidence = _read_verified_facts_architecture_evidence(
        artifact_path=artifacts_path,
        source_path=source_path,
    )

    assert evidence["passed"] is True
    assert evidence["verified_fact_ids"] == ["fact-1"]
    assert evidence["source_pdf_sha256"] == source_sha256


def test_cohort_member_missing_source_has_typed_terminal_result(tmp_path: Path) -> None:
    result = run_first_attempt_canary(
        runs_root=tmp_path,
        source_path=tmp_path / "missing.pdf",
        max_duration_seconds=1,
    )

    assert result["final_state"] == "failed"
    assert result["workflow_attempt_count"] == 0
    assert result["terminal_failure_code"] == "frozen_cohort_source_missing"
    assert Path(result["run_directory"]).joinpath("result.json").is_file()


def test_first_attempt_canary_uses_production_submission_and_supervisor_path(
    tmp_path: Path,
    external_boundary_mocks_only,
    fake_openai,
) -> None:
    """The canary reaches a terminal result through durable production queues."""

    external_boundary_mocks_only.setenv("OPENAI_API_KEY", "test-openai-key")
    fake_openai.add("vector_stores.create", {"id": "vs_canary_test"})
    fake_openai.add("files.create", {"id": "file_canary_test"})
    fake_openai.add("vector_stores.files.create", {"id": "file_canary_test"})
    fake_openai.add("vector_stores.retrieve", {"status": "completed"})
    fake_openai.add("vector_stores.update", {"id": "vs_canary_test"})
    generated_soft_copy_payloads: list[dict[str, object]] = []
    detected_unsupported_claims: list[str] = []
    fake_openai.add(
        "responses.create",
        _full_chain_response_factory(
            repair_soft_copy=False,
            reproduce_ias_soft_copy=False,
            detected_unsupported_claims=detected_unsupported_claims,
        ),
    )
    fake_openai.add(
        "chat.completions.create",
        _full_chain_chat_response_factory(
            repair_soft_copy=False,
            reproduce_ias_soft_copy=False,
            generated_soft_copy_payloads=generated_soft_copy_payloads,
            detected_unsupported_claims=detected_unsupported_claims,
        ),
    )
    source_path = Path(
        "tests/fixtures/pdf_benchmark/golden/IAS - Industry_Pulse_Report_2026_ACIG.pdf"
    ).resolve()

    result = run_first_attempt_canary(
        runs_root=tmp_path,
        source_path=source_path,
        source_metadata={
            "source_domain": "publisher.example",
            "report_name": "Industry Pulse Report 2026",
            "landing_page_url": "https://publisher.example/reports/industry-pulse-2026",
            "source_page_url": "https://publisher.example/reports",
            "publisher_name": "Industry Analytics Summit",
            "downloaded_at_utc": "2026-08-10T12:00:00Z",
        },
        max_duration_seconds=60,
    )

    assert result["admission_outcome"] == "admitted"
    assert result["workflow_root_id"]
    assert result["final_state"] in {"awaiting_review", "failed"}
    assert result["model_provider_calls"] > 0
    assert result["metric_attribution"] == "canonical_run_and_report_id"
    assert Path(result["run_directory"]).joinpath("cohort", "source.json").is_file()
    with sqlite3.connect(
        Path(result["run_directory"]) / "state" / "workflow.sqlite"
    ) as conn:
        jobs = conn.execute(
            """
            SELECT queue_name, status
            FROM workflow_jobs
            WHERE root_workflow_id=?
            ORDER BY created_at_utc, queue_name
            """,
            (result["workflow_root_id"],),
        ).fetchall()
        workers = conn.execute(
            """
            SELECT DISTINCT attempts.worker_id
            FROM workflow_job_attempts AS attempts
            JOIN workflow_jobs AS jobs ON jobs.job_id=attempts.job_id
            WHERE jobs.root_workflow_id=?
            """,
            (result["workflow_root_id"],),
        ).fetchall()

    assert jobs
    assert jobs[0][0] == "source_ingest"
    assert {queue_name for queue_name, _ in jobs} >= {
        "source_ingest",
        "report_selection",
    }
    assert workers
    assert all(
        str(worker_id).startswith(f"ias-live-canary:{result['workflow_root_id']}:")
        for (worker_id,) in workers
    )
    reports_db = Path(result["run_directory"]) / "state" / "reports.sqlite"
    with sqlite3.connect(reports_db) as conn:
        manifest_root = conn.execute(
            "SELECT workflow_run_id FROM validation_runs"
        ).fetchone()
        manifest_stages = {
            stage
            for (stage,) in conn.execute(
                "SELECT DISTINCT stage FROM validation_run_stage_records"
            )
        }

    assert manifest_root == (result["workflow_root_id"],)
    assert manifest_stages >= {
        "admission_preflight",
        "candidate_qualification",
        "source_preparation",
    }


def test_frozen_manifest_requires_pinned_source_provenance(tmp_path: Path) -> None:
    manifest = tmp_path / "cohort.json"
    manifest.write_text(json.dumps({"members": [{"source_path": "missing.pdf"}]}))

    try:
        _load_members(manifest)
    except ValueError as exc:
        assert "exactly 5, 10, or 20 members" in str(exc)
    else:
        raise AssertionError("incomplete frozen manifest was accepted")


def test_frozen_manifest_accepts_the_future_ten_report_cohort_size(
    tmp_path: Path,
) -> None:
    members = []
    for index in range(10):
        source_path = tmp_path / f"source-{index}.pdf"
        content = f"future-ten-report-fixture-{index}".encode("utf-8")
        source_path.write_bytes(content)
        members.append(
            {
                "source_path": str(source_path.resolve()),
                "content_md5": hashlib.md5(content, usedforsecurity=False).hexdigest(),
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

    loaded = _load_members(manifest, sources_root=tmp_path)

    assert len(loaded) == 10


def test_frozen_manifest_accepts_the_pinned_five_report_grounding_cohort(
    tmp_path: Path,
) -> None:
    publishers = [
        "Merchant Risk Council",
        "Deloitte",
        "Emplifi",
        "StackAdapt Inc.",
        "DoubleVerify",
    ]
    members = []
    for index, publisher in enumerate(publishers):
        source_path = tmp_path / f"source-{index}.pdf"
        content = f"pinned-grounding-regression-{publisher}".encode("utf-8")
        source_path.write_bytes(content)
        members.append(
            {
                "source_path": str(source_path.resolve()),
                "content_md5": hashlib.md5(content, usedforsecurity=False).hexdigest(),
                "source_domain": "publisher.example",
                "report_name": f"Frozen report {index}",
                "landing_page_url": f"https://publisher.example/reports/{index}",
                "source_page_url": "https://publisher.example/reports",
                "publisher_name": publisher,
                "downloaded_at_utc": "2026-09-27T00:00:00Z",
            }
        )
    manifest = tmp_path / "pinned-five.json"
    manifest.write_text(json.dumps({"members": members}), encoding="utf-8")

    loaded = _load_members(manifest, sources_root=tmp_path)

    assert [item["publisher_name"] for item in loaded] == publishers
    assert all(Path(item["resolved_source_path"]).is_file() for item in loaded)


def test_frozen_manifest_resolves_sources_from_an_explicit_workspace_root(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source-workspace"
    source_root.mkdir()
    members = []
    for index in range(5):
        relative_path = Path("out") / f"frozen-{index}.pdf"
        source_path = source_root / relative_path
        source_path.parent.mkdir(parents=True, exist_ok=True)
        content = f"frozen-source-root-{index}".encode("utf-8")
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

    loaded = _load_members(manifest, sources_root=source_root)

    assert [Path(item["resolved_source_path"]) for item in loaded] == [
        source_root / item["source_path"] for item in members
    ]


def test_frozen_manifest_loader_uses_the_supplied_byte_snapshot(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"manifest snapshot source")
    member = {
        "source_path": source.name,
        "content_md5": hashlib.md5(
            source.read_bytes(), usedforsecurity=False
        ).hexdigest(),
        "source_domain": "publisher.example",
        "report_name": "Frozen fixture",
        "landing_page_url": "https://publisher.example/report",
        "source_page_url": "https://publisher.example/reports",
        "publisher_name": "Fixture Publisher",
        "downloaded_at_utc": "2026-10-01T00:00:00Z",
    }
    snapshot = json.dumps({"members": [member] * 5}).encode("utf-8")
    manifest = tmp_path / "frozen.json"
    manifest.write_bytes(b'{"members": []}')

    loaded = _load_members(manifest, sources_root=tmp_path, manifest_bytes=snapshot)

    assert len(loaded) == 5
    assert all(item["report_name"] == "Frozen fixture" for item in loaded)


def test_staging_member_gate_rejects_partial_selection() -> None:
    from scripts.quality.run_frozen_reliability_cohort import (
        _require_exact_staging_members,
    )

    members = [
        {"content_md5": digest}
        for digest in sorted(
            {
                "81af3890cd84ece81ef16e1aabda8027",
                "cbb6e7df67412186b8bc094a424ac890",
                "2acb4a56e14add5d7717f34c378f9091",
                "4b763ae2286ca69fe8acb63b17508dfb",
                "b638414df0b1fccea1cd8a93eaf8f5aa",
            }
        )
    ]

    _require_exact_staging_members(members, members)
    with pytest.raises(ValueError, match="all five pinned frozen reports"):
        _require_exact_staging_members(members, members[:4])


@pytest.mark.parametrize("escape_kind", ["parent", "absolute"])
def test_frozen_manifest_rejects_sources_outside_explicit_workspace_root(
    tmp_path: Path, escape_kind: str
) -> None:
    source_root = tmp_path / "source-workspace"
    source_root.mkdir()
    outside = tmp_path / "outside.pdf"
    content = b"source outside frozen root"
    outside.write_bytes(content)
    source_path = (
        Path("../outside.pdf") if escape_kind == "parent" else outside.resolve()
    )
    member = {
        "source_path": str(source_path),
        "content_md5": hashlib.md5(content, usedforsecurity=False).hexdigest(),
        "source_domain": "publisher.example",
        "report_name": "Frozen fixture",
        "landing_page_url": "https://publisher.example/report",
        "source_page_url": "https://publisher.example/reports",
        "publisher_name": "Fixture Publisher",
        "downloaded_at_utc": "2026-10-01T00:00:00Z",
    }
    manifest = tmp_path / "frozen.json"
    manifest.write_text(json.dumps({"members": [member] * 5}), encoding="utf-8")

    with pytest.raises(ValueError, match="outside the configured sources root"):
        _load_members(manifest, sources_root=source_root)


def test_frozen_manifest_rejects_sources_outside_default_workspace_root(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.pdf"
    content = b"source outside default frozen root"
    outside.write_bytes(content)
    member = {
        "source_path": str(outside.resolve()),
        "content_md5": hashlib.md5(content, usedforsecurity=False).hexdigest(),
        "source_domain": "publisher.example",
        "report_name": "Frozen fixture",
        "landing_page_url": "https://publisher.example/report",
        "source_page_url": "https://publisher.example/reports",
        "publisher_name": "Fixture Publisher",
        "downloaded_at_utc": "2026-10-01T00:00:00Z",
    }
    manifest = tmp_path / "frozen.json"
    manifest.write_text(json.dumps({"members": [member] * 5}), encoding="utf-8")

    with pytest.raises(ValueError, match="outside the configured sources root"):
        _load_members(manifest)


def test_shared_batch_acceptance_requires_real_first_attempt_staging_evidence() -> None:
    report = {
        "admission_outcome": "admitted",
        "final_state": "published",
        "workflow_attempt_count": 1,
        "workflow_retry_count": 0,
        "operator_intervention": False,
        "bounded_automatic_repair": False,
        "automatic_repair_count": 0,
        "publication_readiness": "pass",
        "validation": "pass",
        "terminal_failure_code": "",
        "wordpress_post_type": "ml_report",
        "wordpress_created_this_run": True,
        "wordpress_authenticated_readback": True,
    }
    result = {
        "shared_batch": True,
        "cohort_size": 5,
        "source_manifest_sha256": "744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7",
        "reports": [
            {**report, "report_id": report_id}
            for report_id in sorted(STAGING_FROZEN_COHORT_REPORT_IDS)
        ],
        "cohort_metrics": {
            "bounded_automatic_repair": False,
            "automatic_repair_count": 0,
            "workflow_retry_count": 0,
            "operator_intervention_count": 0,
            "wordpress_staging_preflight": {
                "hostname": "marketlense.medianewsonline.com",
                "scheme": "http",
                "insecure_http_opt_in": True,
                "authenticated": True,
                "reachable": True,
                "post_status": "draft",
                "post_type": "ml_report",
                "verified_capabilities": ["create_posts"],
            },
            "wordpress_replay": {
                "status": "verified",
                "duplicate_submissions": 5,
                "first_attempt_publication_jobs": 5,
                "created_duplicate_jobs": 0,
                "attempt_counts_unchanged": True,
                "published_rows_unchanged": True,
                "additional_wordpress_writes": 0,
            },
            "cross_report_handoffs": {
                "enabled": True,
                "queue_terminal": True,
                "queue_terminal_failure_count": 0,
                "queue_expected_policy_hold_count": 0,
                "queue_unclassified_terminal_failure_count": 0,
                "queue_nonterminal_outbox_count": 0,
                "briefing_validated_multireport_count": 1,
                "briefing_validated_multireport_execution_seconds": 2.5,
                "briefing_validated_multireport_provider_usage": {
                    "provider_calls": 1,
                    "input_tokens": 20,
                    "cached_input_tokens": 0,
                    "output_tokens": 5,
                    "tool_calls": 0,
                    "estimated_cost_usd": 0.001,
                    "pricing_status_counts": {"matched": 1},
                    "unpriced_provider_call_count": 0,
                    "cost_available": True,
                },
                "signal_manifest_count": 4,
                "signal_manifest_readback_verified_count": 4,
                "signal_manifest_replay_verified_count": 4,
                "signal_manifest_mutation_probe_count": 4,
                "signal_manifest_mutation_verified_count": 4,
                "signal_manifest_mutation_preserved": True,
                "signal_manifest_mutation_probe_scope": "every_manifest",
                "signal_single_source_group_count": 4,
                "signal_single_source_insufficient_grounding_hold_count": 4,
                "signal_single_source_unsafe_group_count": 0,
                "signal_or_briefing_publication_job_count": 0,
                "signal_or_briefing_publication_status_counts": {},
                "signal_or_briefing_publication_policy_hold_count": 0,
                "signal_or_briefing_publication_unexpected_job_count": 0,
            },
        },
    }

    assert _shared_batch_passes(result) is True

    bounded_repairs = json.loads(json.dumps(result))
    bounded_repairs["cohort_metrics"]["bounded_automatic_repair"] = True
    bounded_repairs["cohort_metrics"]["automatic_repair_count"] = 3
    bounded_repairs["reports"][0]["bounded_automatic_repair"] = True
    bounded_repairs["reports"][0]["automatic_repair_count"] = 3
    assert _shared_batch_passes(bounded_repairs) is True

    safe_review_hold = json.loads(json.dumps(result))
    cross_report = safe_review_hold["cohort_metrics"]["cross_report_handoffs"]
    cross_report["queue_terminal_failure_count"] = 1
    cross_report["queue_expected_policy_hold_count"] = 1
    cross_report["signal_or_briefing_publication_job_count"] = 1
    cross_report["signal_or_briefing_publication_status_counts"] = {"blocked": 1}
    cross_report["signal_or_briefing_publication_policy_hold_count"] = 1
    assert _shared_batch_passes(safe_review_hold) is True

    unexpected_cross_report_failure = json.loads(json.dumps(safe_review_hold))
    cross_report = unexpected_cross_report_failure["cohort_metrics"][
        "cross_report_handoffs"
    ]
    cross_report["queue_terminal_failure_count"] = 2
    cross_report["queue_unclassified_terminal_failure_count"] = 1
    assert _shared_batch_passes(unexpected_cross_report_failure) is False

    unsafe_cross_report_publication = json.loads(json.dumps(result))
    cross_report = unsafe_cross_report_publication["cohort_metrics"][
        "cross_report_handoffs"
    ]
    cross_report["signal_or_briefing_publication_job_count"] = 1
    cross_report["signal_or_briefing_publication_status_counts"] = {"succeeded": 1}
    cross_report["signal_or_briefing_publication_unexpected_job_count"] = 1
    assert _shared_batch_passes(unsafe_cross_report_publication) is False

    failed = json.loads(json.dumps(result))
    failed["reports"][0]["wordpress_created_this_run"] = False
    assert _shared_batch_passes(failed) is False

    failed = json.loads(json.dumps(result))
    failed["cohort_metrics"]["wordpress_replay"]["additional_wordpress_writes"] = 1
    assert _shared_batch_passes(failed) is False

    failed = json.loads(json.dumps(result))
    failed["cohort_metrics"]["wordpress_staging_preflight"]["insecure_http_opt_in"] = (
        False
    )
    assert _shared_batch_passes(failed) is False

    failed = json.loads(json.dumps(result))
    failed["cohort_metrics"]["wordpress_staging_preflight"]["hostname"] = (
        "other.example"
    )
    assert _shared_batch_passes(failed) is False

    failed = json.loads(json.dumps(result))
    failed["cohort_metrics"]["cross_report_handoffs"][
        "signal_single_source_unsafe_group_count"
    ] = 1
    assert _shared_batch_passes(failed) is False

    failed = json.loads(json.dumps(result))
    failed["source_manifest_sha256"] = "0" * 64
    assert _shared_batch_passes(failed) is False

    failed = json.loads(json.dumps(result))
    failed["reports"][0]["report_id"] = failed["reports"][1]["report_id"]
    assert _shared_batch_passes(failed) is False

    failed = json.loads(json.dumps(result))
    failed["cohort_metrics"]["cross_report_handoffs"][
        "briefing_validated_multireport_provider_usage"
    ]["provider_calls"] = 0
    assert _shared_batch_passes(failed) is False

    failed = json.loads(json.dumps(result))
    failed["cohort_metrics"]["cross_report_handoffs"][
        "briefing_validated_multireport_provider_usage"
    ]["cost_available"] = False
    assert _shared_batch_passes(failed) is False

    for invalid_duration in (True, float("inf"), float("nan"), 0, -0.1):
        failed = json.loads(json.dumps(result))
        failed["cohort_metrics"]["cross_report_handoffs"][
            "briefing_validated_multireport_execution_seconds"
        ] = invalid_duration
        assert _shared_batch_passes(failed) is False

    for invalid_cost in (float("inf"), float("nan"), -0.001, True):
        failed = json.loads(json.dumps(result))
        failed["cohort_metrics"]["cross_report_handoffs"][
            "briefing_validated_multireport_provider_usage"
        ]["estimated_cost_usd"] = invalid_cost
        assert _shared_batch_passes(failed) is False

    failed = json.loads(json.dumps(result))
    del failed["cohort_metrics"]["cross_report_handoffs"][
        "signal_manifest_mutation_probe_scope"
    ]
    assert _shared_batch_passes(failed) is False

    failed = json.loads(json.dumps(result))
    failed["cohort_metrics"]["cross_report_handoffs"][
        "signal_manifest_mutation_verified_count"
    ] = 3
    assert _shared_batch_passes(failed) is False


def test_retained_package_lifecycle_manifest_contains_only_the_pinned_reports() -> None:
    manifest = Path(
        "docs/quality/reliability-cohort-20260927-grounding/"
        "final-package-lifecycle-5/frozen_cohort.json"
    )

    loaded = json.loads(manifest.read_text(encoding="utf-8"))["members"]

    assert [item["publisher_name"] for item in loaded] == [
        "Merchant Risk Council",
        "Deloitte",
        "Emplifi",
        "StackAdapt Inc.",
        "DoubleVerify",
    ]


def test_default_frozen_manifest_contains_ten_reports() -> None:
    manifest = json.loads(DEFAULT_SOURCES_MANIFEST.read_text(encoding="utf-8"))
    assert len(manifest["members"]) == 10


def test_frozen_manifest_rejects_missing_provenance_before_file_access(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "cohort.json"
    manifest.write_text(json.dumps({"members": [{"source_path": "missing.pdf"}] * 20}))

    try:
        _load_members(manifest)
    except ValueError as exc:
        assert "incomplete source provenance" in str(exc)
    else:
        raise AssertionError("missing provenance was accepted")
