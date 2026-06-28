from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Sequence

import yaml

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ReleaseEvidenceReviewArtifact:
    manifest_path: str
    name: str
    path: str
    required: bool
    expected_schema_version: str
    schema_version: str | None
    status: str
    passed: bool
    generated_at: str | None
    modified_at: str | None
    issue_count: int
    waived_issue_count: int
    unwaived_issue_count: int


@dataclass(frozen=True)
class ReleaseEvidenceReviewIssue:
    manifest_path: str
    artifact_name: str
    artifact_path: str
    reason: str
    detail: str
    waived: bool
    waiver_owner: str
    waiver_expires_on: str
    waiver_justification: str


@dataclass(frozen=True)
class ReleaseEvidenceWaiverError:
    waiver_index: int
    artifact_name: str
    waiver_reason: str
    owner: str
    expires_on: str
    reason_code: str
    reason_detail: str

    @property
    def reason(self) -> str:
        return self.reason_code


@dataclass(frozen=True)
class ReleaseEvidenceReviewSummary:
    schema_version: str
    generated_at: str
    manifest_paths: tuple[str, ...]
    release_ids: tuple[str, ...]
    commit_shas: tuple[str, ...]
    manifest_passed: bool
    passed: bool
    artifact_count: int
    issue_count: int
    waived_issue_count: int
    unwaived_issue_count: int
    waiver_error_count: int
    artifacts: tuple[ReleaseEvidenceReviewArtifact, ...]
    issues: tuple[ReleaseEvidenceReviewIssue, ...]
    waiver_errors: tuple[ReleaseEvidenceWaiverError, ...]


@dataclass(frozen=True)
class _Waiver:
    index: int
    artifact_name: str
    reason: str
    owner: str
    expires_on: str
    justification: str


def build_release_evidence_review(
    *,
    manifest_paths: Sequence[Path],
    waiver_path: Path | None = None,
    generated_at: str | None = None,
    today: str | date | None = None,
) -> ReleaseEvidenceReviewSummary:
    current_date = _coerce_date(today)
    manifests = tuple(_read_manifest(path) for path in manifest_paths)
    waivers, waiver_errors = _read_waivers(waiver_path, current_date)
    issue_keys = {
        (issue["artifact_name"], issue["reason"])
        for manifest, _ in manifests
        for issue in manifest.get("issues", [])
    }
    waiver_errors = waiver_errors + _unmatched_waiver_errors(waivers, issue_keys)
    valid_waivers = {
        (waiver.artifact_name, waiver.reason): waiver
        for waiver in waivers
        if not _waiver_has_error(waiver.index, waiver_errors)
    }

    review_issues: list[ReleaseEvidenceReviewIssue] = []
    issues_by_artifact: dict[tuple[str, str], list[ReleaseEvidenceReviewIssue]] = {}
    for manifest, manifest_display_path in manifests:
        for raw_issue in manifest.get("issues", []):
            waiver = valid_waivers.get(
                (str(raw_issue["artifact_name"]), str(raw_issue["reason"]))
            )
            review_issue = ReleaseEvidenceReviewIssue(
                manifest_path=manifest_display_path,
                artifact_name=str(raw_issue["artifact_name"]),
                artifact_path=str(raw_issue.get("artifact_path", "")),
                reason=str(raw_issue["reason"]),
                detail=str(raw_issue.get("detail", "")),
                waived=waiver is not None,
                waiver_owner=waiver.owner if waiver else "",
                waiver_expires_on=waiver.expires_on if waiver else "",
                waiver_justification=waiver.justification if waiver else "",
            )
            review_issues.append(review_issue)
            issues_by_artifact.setdefault(
                (manifest_display_path, review_issue.artifact_name), []
            ).append(review_issue)

    review_artifacts: list[ReleaseEvidenceReviewArtifact] = []
    for manifest, manifest_display_path in manifests:
        for raw_artifact in manifest.get("artifacts", []):
            artifact_issues = issues_by_artifact.get(
                (manifest_display_path, str(raw_artifact["name"])),
                [],
            )
            waived_count = sum(1 for issue in artifact_issues if issue.waived)
            review_artifacts.append(
                ReleaseEvidenceReviewArtifact(
                    manifest_path=manifest_display_path,
                    name=str(raw_artifact["name"]),
                    path=str(raw_artifact["path"]),
                    required=bool(raw_artifact["required"]),
                    expected_schema_version=str(
                        raw_artifact["expected_schema_version"]
                    ),
                    schema_version=_optional_str(raw_artifact.get("schema_version")),
                    status=str(raw_artifact["status"]),
                    passed=bool(raw_artifact["passed"]),
                    generated_at=_optional_str(raw_artifact.get("generated_at")),
                    modified_at=_optional_str(raw_artifact.get("modified_at")),
                    issue_count=len(artifact_issues),
                    waived_issue_count=waived_count,
                    unwaived_issue_count=len(artifact_issues) - waived_count,
                )
            )

    review_issues.sort(
        key=lambda issue: (
            issue.manifest_path,
            issue.artifact_name,
            issue.reason,
            issue.detail,
        )
    )
    review_artifacts.sort(
        key=lambda artifact: (artifact.manifest_path, artifact.name, artifact.path)
    )
    waiver_errors = tuple(
        sorted(
            waiver_errors,
            key=lambda error: (
                error.waiver_index,
                error.artifact_name,
                error.reason_code,
            ),
        )
    )
    unwaived_issue_count = sum(1 for issue in review_issues if not issue.waived)
    waived_issue_count = len(review_issues) - unwaived_issue_count
    manifest_passed = all(bool(manifest.get("passed")) for manifest, _ in manifests)
    passed = unwaived_issue_count == 0 and not waiver_errors

    return ReleaseEvidenceReviewSummary(
        schema_version="1.0",
        generated_at=generated_at or _now(),
        manifest_paths=tuple(path for _, path in manifests),
        release_ids=tuple(
            str(manifest.get("release_id", "")) for manifest, _ in manifests
        ),
        commit_shas=tuple(
            str(manifest.get("commit_sha", "")) for manifest, _ in manifests
        ),
        manifest_passed=manifest_passed,
        passed=passed,
        artifact_count=len(review_artifacts),
        issue_count=len(review_issues),
        waived_issue_count=waived_issue_count,
        unwaived_issue_count=unwaived_issue_count,
        waiver_error_count=len(waiver_errors),
        artifacts=tuple(review_artifacts),
        issues=tuple(review_issues),
        waiver_errors=waiver_errors,
    )


def render_release_evidence_review_markdown(
    review: ReleaseEvidenceReviewSummary,
) -> str:
    lines = [
        "# Release Evidence Review",
        "",
        f"- Generated at: `{review.generated_at}`",
        f"- Release IDs: `{', '.join(review.release_ids)}`",
        f"- Commit SHAs: `{', '.join(review.commit_shas)}`",
        f"- Approval status: `{'passed' if review.passed else 'failed'}`",
        f"- Manifest status before waivers: `{'passed' if review.manifest_passed else 'failed'}`",
        f"- Artifacts: `{review.artifact_count}`",
        f"- Issues: `{review.issue_count}` total, `{review.waived_issue_count}` waived, `{review.unwaived_issue_count}` unwaived",
        f"- Waiver errors: `{review.waiver_error_count}`",
        "",
        "## Artifacts",
        "",
        "| Artifact | Status | Required | Issues | Unwaived | Freshness | Manifest |",
        "| --- | --- | --- | ---: | ---: | --- | --- |",
    ]
    for artifact in review.artifacts:
        lines.append(
            "| "
            + " | ".join(
                (
                    _md(artifact.name),
                    _md(artifact.status),
                    "yes" if artifact.required else "no",
                    str(artifact.issue_count),
                    str(artifact.unwaived_issue_count),
                    _md(artifact.modified_at or ""),
                    _md(artifact.manifest_path),
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Issues",
            "",
            "| Artifact | Reason | Waived | Owner | Expires | Detail |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    if review.issues:
        for issue in review.issues:
            lines.append(
                "| "
                + " | ".join(
                    (
                        _md(issue.artifact_name),
                        _md(issue.reason),
                        "yes" if issue.waived else "no",
                        _md(issue.waiver_owner),
                        _md(issue.waiver_expires_on),
                        _md(issue.detail),
                    )
                )
                + " |"
            )
    else:
        lines.append("| none | none | no |  |  | No manifest issues. |")

    lines.extend(
        [
            "",
            "## Waiver Errors",
            "",
            "| Index | Artifact | Reason | Error | Detail |",
            "| ---: | --- | --- | --- | --- |",
        ]
    )
    if review.waiver_errors:
        for error in review.waiver_errors:
            lines.append(
                "| "
                + " | ".join(
                    (
                        str(error.waiver_index),
                        _md(error.artifact_name),
                        _md(error.waiver_reason),
                        _md(error.reason_code),
                        _md(error.reason_detail),
                    )
                )
                + " |"
            )
    else:
        lines.append("| 0 | none | none | none | No waiver errors. |")
    return "\n".join(lines) + "\n"


def write_release_evidence_review(
    review: ReleaseEvidenceReviewSummary,
    *,
    output_json_path: Path,
    output_markdown_path: Path,
) -> None:
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_markdown_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(
        json.dumps(asdict(review), ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_markdown_path.write_text(
        render_release_evidence_review_markdown(review),
        encoding="utf-8",
    )


def _read_manifest(path: Path) -> tuple[dict[str, Any], str]:
    resolved_path = path if path.is_absolute() else (ROOT / path).resolve()
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Manifest must be a JSON object: {_rel(resolved_path)}")
    if payload.get("schema_version") != "1.0":
        raise ValueError(f"Unsupported manifest schema version: {_rel(resolved_path)}")
    if not isinstance(payload.get("artifacts"), list):
        raise ValueError(f"Manifest artifacts must be a list: {_rel(resolved_path)}")
    if not isinstance(payload.get("issues"), list):
        raise ValueError(f"Manifest issues must be a list: {_rel(resolved_path)}")
    return payload, _rel(resolved_path)


def _read_waivers(
    waiver_path: Path | None,
    today: date,
) -> tuple[tuple[_Waiver, ...], tuple[ReleaseEvidenceWaiverError, ...]]:
    if waiver_path is None:
        return (), ()
    resolved_path = (
        waiver_path if waiver_path.is_absolute() else (ROOT / waiver_path).resolve()
    )
    if not resolved_path.exists():
        return (), (
            ReleaseEvidenceWaiverError(
                waiver_index=0,
                artifact_name="",
                waiver_reason="",
                owner="",
                expires_on="",
                reason_code="waiver_file_missing",
                reason_detail=f"waiver file not found: {_rel(resolved_path)}",
            ),
        )
    payload = yaml.safe_load(resolved_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Waiver file must be a YAML object: {_rel(resolved_path)}")
    raw_waivers = payload.get("waivers", [])
    if not isinstance(raw_waivers, list):
        raise ValueError(f"Waiver file waivers must be a list: {_rel(resolved_path)}")

    waivers: list[_Waiver] = []
    errors: list[ReleaseEvidenceWaiverError] = []
    for index, raw_waiver in enumerate(raw_waivers):
        if not isinstance(raw_waiver, dict):
            errors.append(
                ReleaseEvidenceWaiverError(
                    waiver_index=index,
                    artifact_name="",
                    waiver_reason="",
                    owner="",
                    expires_on="",
                    reason_code="waiver_invalid",
                    reason_detail="waiver entry must be an object",
                )
            )
            continue
        waiver = _Waiver(
            index=index,
            artifact_name=str(raw_waiver.get("artifact_name", "")).strip(),
            reason=str(raw_waiver.get("reason", "")).strip(),
            owner=str(raw_waiver.get("owner", "")).strip(),
            expires_on=str(raw_waiver.get("expires_on", "")).strip(),
            justification=str(raw_waiver.get("justification", "")).strip(),
        )
        waivers.append(waiver)
        errors.extend(_validate_waiver(waiver, today))
    return tuple(waivers), tuple(errors)


def _validate_waiver(
    waiver: _Waiver,
    today: date,
) -> tuple[ReleaseEvidenceWaiverError, ...]:
    errors: list[ReleaseEvidenceWaiverError] = []
    if not waiver.artifact_name:
        errors.append(
            _waiver_error(
                waiver, "waiver_artifact_missing", "artifact_name is required"
            )
        )
    if not waiver.reason:
        errors.append(
            _waiver_error(waiver, "waiver_reason_missing", "reason is required")
        )
    if not waiver.owner:
        errors.append(
            _waiver_error(waiver, "waiver_owner_missing", "owner is required")
        )
    if not waiver.justification:
        errors.append(
            _waiver_error(
                waiver,
                "waiver_justification_missing",
                "justification is required",
            )
        )
    try:
        expires_on = date.fromisoformat(waiver.expires_on)
    except ValueError:
        errors.append(
            _waiver_error(
                waiver,
                "waiver_expiry_invalid",
                "expires_on must be an ISO date",
            )
        )
    else:
        if expires_on < today:
            errors.append(
                _waiver_error(
                    waiver,
                    "waiver_expired",
                    f"expires_on {waiver.expires_on} is before {today.isoformat()}",
                )
            )
    return tuple(errors)


def _unmatched_waiver_errors(
    waivers: tuple[_Waiver, ...],
    issue_keys: set[tuple[str, str]],
) -> tuple[ReleaseEvidenceWaiverError, ...]:
    return tuple(
        _waiver_error(
            waiver,
            "waiver_unmatched",
            "waiver does not match any manifest issue",
        )
        for waiver in waivers
        if waiver.artifact_name
        and waiver.reason
        and (waiver.artifact_name, waiver.reason) not in issue_keys
    )


def _waiver_has_error(
    waiver_index: int,
    waiver_errors: tuple[ReleaseEvidenceWaiverError, ...],
) -> bool:
    return any(error.waiver_index == waiver_index for error in waiver_errors)


def _waiver_error(
    waiver: _Waiver,
    reason_code: str,
    reason_detail: str,
) -> ReleaseEvidenceWaiverError:
    return ReleaseEvidenceWaiverError(
        waiver_index=waiver.index,
        artifact_name=waiver.artifact_name,
        waiver_reason=waiver.reason,
        owner=waiver.owner,
        expires_on=waiver.expires_on,
        reason_code=reason_code,
        reason_detail=reason_detail,
    )


def _coerce_date(value: str | date | None) -> date:
    if value is None:
        return datetime.now(UTC).date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Review release evidence manifests and enforce waiver governance."
    )
    parser.add_argument("--manifest-json", action="append", required=True)
    parser.add_argument("--waivers-yaml", default="")
    parser.add_argument("--output-json", default="out/release_evidence_review.json")
    parser.add_argument("--output-md", default="out/release_evidence_review.md")
    args = parser.parse_args(argv)
    review = build_release_evidence_review(
        manifest_paths=tuple(Path(path) for path in args.manifest_json),
        waiver_path=Path(args.waivers_yaml) if args.waivers_yaml else None,
        generated_at=_now(),
    )
    write_release_evidence_review(
        review,
        output_json_path=(ROOT / args.output_json).resolve(),
        output_markdown_path=(ROOT / args.output_md).resolve(),
    )
    print(json.dumps(asdict(review), ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if review.passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
