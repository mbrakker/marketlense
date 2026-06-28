from __future__ import annotations

import json
from pathlib import Path

from scripts.quality.release_evidence_review import (
    build_release_evidence_review,
    render_release_evidence_review_markdown,
    write_release_evidence_review,
)


def _write_manifest(path: Path, *, issues: list[dict[str, str]]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "release_id": "release-20260628",
                "generated_at": "2026-06-28T12:00:00+00:00",
                "commit_sha": "abc123",
                "command_args": ("manifest",),
                "passed": not issues,
                "artifacts": [
                    {
                        "name": "coverage",
                        "path": "coverage.xml",
                        "required": True,
                        "expected_schema_version": "7.14.1",
                        "schema_version": "7.14.1",
                        "status": "passed" if not issues else "stale",
                        "passed": not issues,
                        "generated_at": "1781589182618",
                        "modified_at": "2026-06-28T11:59:00+00:00",
                        "producer_command": "python scripts/ci/check_coverage.py",
                        "byte_count": 100,
                        "artifact_sha256": "a" * 64,
                    }
                ],
                "issues": issues,
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_release_evidence_review_summarizes_clean_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "release_evidence_manifest.json"
    _write_manifest(manifest_path, issues=[])

    review = build_release_evidence_review(
        manifest_paths=(manifest_path,),
        generated_at="2026-06-28T13:00:00+00:00",
        today="2026-06-28",
    )

    markdown = render_release_evidence_review_markdown(review)
    assert review.schema_version == "1.0"
    assert review.passed is True
    assert review.artifact_count == 1
    assert review.issue_count == 0
    assert review.unwaived_issue_count == 0
    assert "| coverage | passed | yes | 0 | 0 |" in markdown
    assert "Release Evidence Review" in markdown


def test_release_evidence_review_applies_matching_waiver(tmp_path: Path) -> None:
    manifest_path = tmp_path / "release_evidence_manifest.json"
    waiver_path = tmp_path / "release_evidence_waivers.yaml"
    _write_manifest(
        manifest_path,
        issues=[
            {
                "artifact_name": "coverage",
                "artifact_path": "coverage.xml",
                "reason": "artifact_stale",
                "detail": "coverage.xml was older than the gate start",
            }
        ],
    )
    waiver_path.write_text(
        "\n".join(
            [
                'schema_version: "1.0"',
                "waivers:",
                "  - artifact_name: coverage",
                "    reason: artifact_stale",
                "    owner: release-owner",
                '    expires_on: "2026-07-01"',
                "    justification: CI rerun reused audited coverage output.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    review = build_release_evidence_review(
        manifest_paths=(manifest_path,),
        waiver_path=waiver_path,
        generated_at="2026-06-28T13:00:00+00:00",
        today="2026-06-28",
    )

    assert review.passed is True
    assert review.manifest_passed is False
    assert review.issue_count == 1
    assert review.waived_issue_count == 1
    assert review.unwaived_issue_count == 0
    assert review.issues[0].waived is True
    assert review.issues[0].waiver_owner == "release-owner"


def test_release_evidence_review_fails_unwaived_manifest_issue(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "release_evidence_manifest.json"
    _write_manifest(
        manifest_path,
        issues=[
            {
                "artifact_name": "coverage",
                "artifact_path": "coverage.xml",
                "reason": "artifact_stale",
                "detail": "coverage.xml was older than the gate start",
            }
        ],
    )

    review = build_release_evidence_review(
        manifest_paths=(manifest_path,),
        generated_at="2026-06-28T13:00:00+00:00",
        today="2026-06-28",
    )

    assert review.passed is False
    assert review.unwaived_issue_count == 1
    assert review.issues[0].waived is False


def test_release_evidence_review_rejects_invalid_waivers(tmp_path: Path) -> None:
    manifest_path = tmp_path / "release_evidence_manifest.json"
    waiver_path = tmp_path / "release_evidence_waivers.yaml"
    _write_manifest(
        manifest_path,
        issues=[
            {
                "artifact_name": "coverage",
                "artifact_path": "coverage.xml",
                "reason": "artifact_stale",
                "detail": "coverage.xml was older than the gate start",
            }
        ],
    )
    waiver_path.write_text(
        "\n".join(
            [
                'schema_version: "1.0"',
                "waivers:",
                "  - artifact_name: coverage",
                "    reason: artifact_stale",
                "    owner: ''",
                '    expires_on: "2026-06-27"',
                "    justification: ''",
                "  - artifact_name: mutation",
                "    reason: artifact_failed",
                "    owner: release-owner",
                '    expires_on: "2026-07-01"',
                "    justification: not matched",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    review = build_release_evidence_review(
        manifest_paths=(manifest_path,),
        waiver_path=waiver_path,
        generated_at="2026-06-28T13:00:00+00:00",
        today="2026-06-28",
    )

    assert review.passed is False
    assert {error.reason for error in review.waiver_errors} == {
        "waiver_expired",
        "waiver_justification_missing",
        "waiver_owner_missing",
        "waiver_unmatched",
    }


def test_write_release_evidence_review_persists_json_and_markdown(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "release_evidence_manifest.json"
    output_json = tmp_path / "release_evidence_review.json"
    output_md = tmp_path / "release_evidence_review.md"
    _write_manifest(manifest_path, issues=[])
    review = build_release_evidence_review(
        manifest_paths=(manifest_path,),
        generated_at="2026-06-28T13:00:00+00:00",
        today="2026-06-28",
    )

    write_release_evidence_review(
        review,
        output_json_path=output_json,
        output_markdown_path=output_md,
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["artifacts"][0]["name"] == "coverage"
    assert output_json.read_text(encoding="utf-8").endswith("\n")
    assert output_md.read_text(encoding="utf-8").endswith("\n")
