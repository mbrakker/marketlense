from __future__ import annotations

import json
import os
from pathlib import Path

from scripts.quality.release_evidence_manifest import (
    ReleaseEvidenceArtifactInput,
    build_release_evidence_manifest,
    main,
    write_release_evidence_manifest,
)


def test_release_evidence_manifest_orders_and_summarizes_artifacts(
    tmp_path: Path,
) -> None:
    health_path = tmp_path / "run_health_scorecard.json"
    candidate_path = tmp_path / "pdf_candidate_benchmark.json"
    health_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "warnings": [],
                "pdf_benchmark_scorecard": {
                    "passed": True,
                    "evidence_complete": True,
                },
            }
        ),
        encoding="utf-8",
    )
    candidate_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "comparison": {
                    "passed": True,
                    "failures": [],
                    "warnings": [],
                },
            }
        ),
        encoding="utf-8",
    )

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="health_scorecard",
                path=health_path,
                expected_schema_version="1.0",
            ),
            ReleaseEvidenceArtifactInput(
                name="pdf_candidate",
                path=candidate_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20260628",
        commit_sha="abc123",
        command_args=("python", "scripts/quality/release_evidence_manifest.py"),
        generated_at="2026-06-28T12:00:00+00:00",
    )

    assert manifest.schema_version == "1.0"
    assert manifest.release_id == "release-20260628"
    assert manifest.commit_sha == "abc123"
    assert manifest.command_args == (
        "python",
        "scripts/quality/release_evidence_manifest.py",
    )
    assert manifest.passed is True
    assert [artifact.name for artifact in manifest.artifacts] == [
        "health_scorecard",
        "pdf_candidate",
    ]
    assert [artifact.status for artifact in manifest.artifacts] == [
        "passed",
        "passed",
    ]
    assert manifest.artifacts[0].schema_version == "1.0"
    assert manifest.artifacts[0].artifact_sha256
    assert manifest.artifacts[0].byte_count > 0
    assert manifest.issues == ()


def test_release_evidence_manifest_reports_missing_invalid_and_failed_artifacts(
    tmp_path: Path,
) -> None:
    invalid_path = tmp_path / "coverage.json"
    failed_path = tmp_path / "mutation.json"
    invalid_path.write_text("{not-json", encoding="utf-8")
    failed_path.write_text(
        json.dumps({"schema_version": "2.0", "passed": False}),
        encoding="utf-8",
    )

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="missing_scorecard",
                path=tmp_path / "missing.json",
                expected_schema_version="1.0",
            ),
            ReleaseEvidenceArtifactInput(
                name="invalid_coverage",
                path=invalid_path,
                expected_schema_version="1.0",
            ),
            ReleaseEvidenceArtifactInput(
                name="mutation",
                path=failed_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20260628",
        commit_sha="abc123",
        command_args=("manifest",),
        generated_at="2026-06-28T12:00:00+00:00",
    )

    assert manifest.passed is False
    assert [artifact.name for artifact in manifest.artifacts] == [
        "invalid_coverage",
        "missing_scorecard",
        "mutation",
    ]
    assert [artifact.status for artifact in manifest.artifacts] == [
        "invalid",
        "missing",
        "failed",
    ]
    assert {issue.reason for issue in manifest.issues} == {
        "artifact_invalid_json",
        "artifact_failed",
        "artifact_missing",
        "schema_version_mismatch",
    }


def test_write_release_evidence_manifest_persists_sorted_json(tmp_path: Path) -> None:
    artifact_path = tmp_path / "trend.json"
    output_path = tmp_path / "release_evidence_manifest.json"
    artifact_path.write_text(
        json.dumps({"schema_version": "1.0", "comparison": {"passed": True}}),
        encoding="utf-8",
    )

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="trend",
                path=artifact_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20260628",
        commit_sha="abc123",
        command_args=("manifest",),
        generated_at="2026-06-28T12:00:00+00:00",
    )

    write_release_evidence_manifest(manifest, output_path)
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "1.0"
    assert payload["artifacts"][0]["name"] == "trend"
    assert output_path.read_text(encoding="utf-8").endswith("\n")


def test_release_evidence_manifest_accepts_coverage_xml_artifact(
    tmp_path: Path,
) -> None:
    coverage_path = tmp_path / "coverage.xml"
    coverage_path.write_text(
        '<?xml version="1.0" ?><coverage version="7.14.1" '
        'timestamp="1781589182618" line-rate="0.8314"></coverage>',
        encoding="utf-8",
    )

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="coverage",
                path=coverage_path,
                expected_schema_version="7.14.1",
            ),
        ),
        release_id="release-20260628",
        commit_sha="abc123",
        command_args=("manifest",),
        generated_at="2026-06-28T12:00:00+00:00",
    )

    assert manifest.passed is True
    assert manifest.artifacts[0].schema_version == "7.14.1"
    assert manifest.artifacts[0].status == "passed"
    assert manifest.artifacts[0].generated_at == "1781589182618"


def test_release_evidence_manifest_flags_warning_payloads(tmp_path: Path) -> None:
    warning_path = tmp_path / "trend.json"
    warning_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "comparison": {
                    "passed": True,
                    "failures": [],
                    "warnings": [{"reason": "runtime_trend_regression_warning"}],
                },
            }
        ),
        encoding="utf-8",
    )

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="trend",
                path=warning_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20260628",
        commit_sha="abc123",
        command_args=("manifest",),
        generated_at="2026-06-28T12:00:00+00:00",
    )

    assert manifest.passed is False
    assert manifest.artifacts[0].status == "warned"
    assert [issue.reason for issue in manifest.issues] == ["artifact_failed"]


def test_release_evidence_manifest_fails_stale_required_artifact(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "mutation.json"
    artifact_path.write_text(
        json.dumps({"schema_version": "1.0", "passed": True}),
        encoding="utf-8",
    )
    os.utime(artifact_path, (100.0, 100.0))

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="mutation",
                path=artifact_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20260628",
        commit_sha="abc123",
        command_args=("manifest",),
        generated_at="2026-06-28T12:00:00+00:00",
        fresh_after="1970-01-01T00:02:00+00:00",
    )

    assert manifest.passed is False
    assert manifest.artifacts[0].status == "stale"
    assert manifest.artifacts[0].modified_at == "1970-01-01T00:01:40+00:00"
    assert [issue.reason for issue in manifest.issues] == ["artifact_stale"]


def test_release_evidence_manifest_fails_commit_sha_mismatch(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "scorecard.json"
    artifact_path.write_text(
        json.dumps({"schema_version": "1.0", "passed": True}),
        encoding="utf-8",
    )

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="scorecard",
                path=artifact_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20260628",
        commit_sha="old-sha",
        command_args=("manifest",),
        generated_at="2026-06-28T12:00:00+00:00",
        expected_commit_sha="new-sha",
    )

    assert manifest.passed is False
    assert {issue.reason for issue in manifest.issues} == {"commit_sha_mismatch"}


def test_release_evidence_manifest_accepts_passed_cto_leakage_artifact(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "log_content_leakage.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generated_at": "2026-07-16T12:00:00+00:00",
                "repository_commit_sha": "a" * 40,
                "status": "passed",
                "passed": True,
            }
        ),
        encoding="utf-8",
    )

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="cto_log_content_leakage",
                path=artifact_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20260716",
        commit_sha="a" * 40,
        command_args=("manifest",),
        expected_commit_sha="a" * 40,
    )

    assert manifest.passed is True
    assert manifest.artifacts[0].repository_commit_sha == "a" * 40


def test_release_evidence_manifest_blocks_failed_cto_artifact_and_embedded_commit_mismatch(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "consistency_validation.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generated_at": "2026-07-16T12:00:00+00:00",
                "repository_commit_sha": "b" * 40,
                "exact_head_verified": False,
                "status": "failed",
                "passed": False,
            }
        ),
        encoding="utf-8",
    )

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="cto_consistency",
                path=artifact_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20260716",
        commit_sha="a" * 40,
        command_args=("manifest",),
        expected_commit_sha="a" * 40,
    )

    assert manifest.passed is False
    assert {issue.reason for issue in manifest.issues} == {
        "artifact_failed",
        "artifact_commit_sha_mismatch",
    }


def test_release_evidence_manifest_applies_freshness_to_cto_artifact(
    tmp_path: Path,
) -> None:
    artifact_path = tmp_path / "log_content_leakage.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "generated_at": "2026-07-16T12:00:00+00:00",
                "passed": True,
            }
        ),
        encoding="utf-8",
    )
    os.utime(artifact_path, (100.0, 100.0))

    manifest = build_release_evidence_manifest(
        artifact_inputs=(
            ReleaseEvidenceArtifactInput(
                name="cto_log_content_leakage",
                path=artifact_path,
                expected_schema_version="1.0",
            ),
        ),
        release_id="release-20260716",
        commit_sha="a" * 40,
        command_args=("manifest",),
        fresh_after="1970-01-01T00:02:00+00:00",
    )

    assert [issue.reason for issue in manifest.issues] == ["artifact_stale"]


def test_release_evidence_manifest_allow_issues_writes_failed_manifest(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "release_evidence_manifest.json"

    exit_code = main(
        [
            "--release-id",
            "release-20260628",
            "--artifact",
            f"missing={tmp_path / 'missing.json'}",
            "--expected-schema",
            "missing=1.0",
            "--allow-issues",
            "--output-json",
            str(output_path),
        ]
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["passed"] is False
    assert payload["issues"][0]["reason"] == "artifact_missing"
