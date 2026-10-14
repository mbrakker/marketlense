from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_PDF_CANDIDATE_ADVISORY_WARNING_REASONS = frozenset(
    {"runtime_regression_warning", "runtime_regression_failure"}
)


@dataclass(frozen=True)
class ReleaseEvidenceArtifactInput:
    name: str
    path: Path
    expected_schema_version: str
    producer_command: str = ""
    required: bool = True


@dataclass(frozen=True)
class ReleaseEvidenceArtifact:
    name: str
    path: str
    required: bool
    expected_schema_version: str
    schema_version: str | None
    status: str
    passed: bool
    generated_at: str | None
    modified_at: str | None
    producer_command: str
    byte_count: int
    artifact_sha256: str | None
    repository_commit_sha: str | None


@dataclass(frozen=True)
class ReleaseEvidenceIssue:
    artifact_name: str
    artifact_path: str
    reason: str
    detail: str


@dataclass(frozen=True)
class ReleaseEvidenceManifest:
    schema_version: str
    release_id: str
    generated_at: str
    commit_sha: str
    command_args: tuple[str, ...]
    passed: bool
    artifacts: tuple[ReleaseEvidenceArtifact, ...]
    issues: tuple[ReleaseEvidenceIssue, ...]


def build_release_evidence_manifest(
    *,
    artifact_inputs: Iterable[ReleaseEvidenceArtifactInput],
    release_id: str,
    commit_sha: str,
    command_args: Sequence[str],
    generated_at: str | None = None,
    fresh_after: str | None = None,
    expected_commit_sha: str | None = None,
) -> ReleaseEvidenceManifest:
    artifacts: list[ReleaseEvidenceArtifact] = []
    issues: list[ReleaseEvidenceIssue] = []
    fresh_after_dt = _parse_datetime(fresh_after) if fresh_after else None
    for artifact_input in sorted(artifact_inputs, key=lambda item: item.name):
        artifact, artifact_issues = _read_artifact(
            artifact_input,
            fresh_after=fresh_after_dt,
        )
        artifacts.append(artifact)
        issues.extend(artifact_issues)
        if (
            expected_commit_sha
            and artifact_input.required
            and artifact.repository_commit_sha
            and artifact.repository_commit_sha != commit_sha
        ):
            issues.append(
                ReleaseEvidenceIssue(
                    artifact_name=artifact.name,
                    artifact_path=artifact.path,
                    reason="artifact_commit_sha_mismatch",
                    detail=(
                        f"artifact repository commit {artifact.repository_commit_sha} "
                        f"does not match release commit {commit_sha}"
                    ),
                )
            )
    if expected_commit_sha and commit_sha != expected_commit_sha:
        issues.append(
            ReleaseEvidenceIssue(
                artifact_name="release_evidence_manifest",
                artifact_path="",
                reason="commit_sha_mismatch",
                detail=f"manifest commit {commit_sha} does not match {expected_commit_sha}",
            )
        )
    return ReleaseEvidenceManifest(
        schema_version="1.0",
        release_id=release_id,
        generated_at=generated_at or _now(),
        commit_sha=commit_sha,
        command_args=tuple(command_args),
        passed=not issues,
        artifacts=tuple(artifacts),
        issues=tuple(issues),
    )


def write_release_evidence_manifest(
    manifest: ReleaseEvidenceManifest,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(asdict(manifest), ensure_ascii=True, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _read_artifact(
    artifact_input: ReleaseEvidenceArtifactInput,
    *,
    fresh_after: datetime | None,
) -> tuple[ReleaseEvidenceArtifact, tuple[ReleaseEvidenceIssue, ...]]:
    path = artifact_input.path
    display_path = _rel(path)
    if not path.is_file():
        issue = ReleaseEvidenceIssue(
            artifact_name=artifact_input.name,
            artifact_path=display_path,
            reason="artifact_missing",
            detail=f"required artifact not found: {display_path}",
        )
        return (
            _artifact(
                artifact_input,
                display_path=display_path,
                schema_version=None,
                status="missing",
                passed=False,
                generated_at=None,
                modified_at=None,
                byte_count=0,
                artifact_sha256=None,
            ),
            (issue,) if artifact_input.required else (),
        )

    raw = path.read_bytes()
    byte_count = len(raw)
    artifact_sha256 = hashlib.sha256(raw).hexdigest()
    modified_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        xml_payload = _xml_payload(raw)
        if xml_payload is not None:
            return _artifact_from_payload(
                artifact_input,
                display_path=display_path,
                payload=xml_payload,
                byte_count=byte_count,
                artifact_sha256=artifact_sha256,
                modified_at=modified_at,
                fresh_after=fresh_after,
            )
        issue = ReleaseEvidenceIssue(
            artifact_name=artifact_input.name,
            artifact_path=display_path,
            reason="artifact_invalid_json",
            detail=f"artifact is not valid UTF-8 JSON: {exc}",
        )
        return (
            _artifact(
                artifact_input,
                display_path=display_path,
                schema_version=None,
                status="invalid",
                passed=False,
                generated_at=None,
                modified_at=_datetime_text(modified_at),
                byte_count=byte_count,
                artifact_sha256=artifact_sha256,
            ),
            (issue,),
        )
    if not isinstance(payload, dict):
        issue = ReleaseEvidenceIssue(
            artifact_name=artifact_input.name,
            artifact_path=display_path,
            reason="artifact_invalid_shape",
            detail="artifact JSON root must be an object",
        )
        return (
            _artifact(
                artifact_input,
                display_path=display_path,
                schema_version=None,
                status="invalid",
                passed=False,
                generated_at=None,
                modified_at=_datetime_text(modified_at),
                byte_count=byte_count,
                artifact_sha256=artifact_sha256,
            ),
            (issue,),
        )

    return _artifact_from_payload(
        artifact_input,
        display_path=display_path,
        payload=payload,
        byte_count=byte_count,
        artifact_sha256=artifact_sha256,
        modified_at=modified_at,
        fresh_after=fresh_after,
    )


def _artifact_from_payload(
    artifact_input: ReleaseEvidenceArtifactInput,
    *,
    display_path: str,
    payload: dict[str, Any],
    byte_count: int,
    artifact_sha256: str,
    modified_at: datetime,
    fresh_after: datetime | None,
) -> tuple[ReleaseEvidenceArtifact, tuple[ReleaseEvidenceIssue, ...]]:
    schema_version = _string_or_none(payload.get("schema_version"))
    generated_at = _string_or_none(payload.get("generated_at"))
    repository_commit_sha = _embedded_repository_commit_sha(payload)
    if artifact_input.name == "pdf_candidate":
        status, passed = _pdf_candidate_status(payload)
    else:
        status, passed = _status_from_payload(payload)
    issues: list[ReleaseEvidenceIssue] = []
    if schema_version != artifact_input.expected_schema_version:
        issues.append(
            ReleaseEvidenceIssue(
                artifact_name=artifact_input.name,
                artifact_path=display_path,
                reason="schema_version_mismatch",
                detail=(
                    f"expected schema_version {artifact_input.expected_schema_version}, "
                    f"got {schema_version or '<missing>'}"
                ),
            )
        )
    if not passed:
        issues.append(
            ReleaseEvidenceIssue(
                artifact_name=artifact_input.name,
                artifact_path=display_path,
                reason="artifact_failed",
                detail=f"artifact status is {status}",
            )
        )
    evidence_errors = _artifact_evidence_errors(artifact_input.name, payload)
    if evidence_errors:
        status = "invalid"
        passed = False
        issues.append(
            ReleaseEvidenceIssue(
                artifact_name=artifact_input.name,
                artifact_path=display_path,
                reason="artifact_invalid_queue_evidence",
                detail="; ".join(evidence_errors[:10]),
            )
        )
    if (
        artifact_input.required
        and fresh_after is not None
        and modified_at < fresh_after
    ):
        status = "stale"
        passed = False
        issues.append(
            ReleaseEvidenceIssue(
                artifact_name=artifact_input.name,
                artifact_path=display_path,
                reason="artifact_stale",
                detail=(
                    f"artifact modified at {_datetime_text(modified_at)} before "
                    f"freshness threshold {_datetime_text(fresh_after)}"
                ),
            )
        )
    return (
        _artifact(
            artifact_input,
            display_path=display_path,
            schema_version=schema_version,
            status=status,
            passed=passed,
            generated_at=generated_at,
            modified_at=_datetime_text(modified_at),
            byte_count=byte_count,
            artifact_sha256=artifact_sha256,
            repository_commit_sha=repository_commit_sha,
        ),
        tuple(issues),
    )


def _xml_payload(raw: bytes) -> dict[str, Any] | None:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    return {
        "schema_version": root.attrib.get("version"),
        "generated_at": root.attrib.get("timestamp"),
        "passed": True,
    }


def _artifact(
    artifact_input: ReleaseEvidenceArtifactInput,
    *,
    display_path: str,
    schema_version: str | None,
    status: str,
    passed: bool,
    generated_at: str | None,
    modified_at: str | None,
    byte_count: int,
    artifact_sha256: str | None,
    repository_commit_sha: str | None = None,
) -> ReleaseEvidenceArtifact:
    return ReleaseEvidenceArtifact(
        name=artifact_input.name,
        path=display_path,
        required=artifact_input.required,
        expected_schema_version=artifact_input.expected_schema_version,
        schema_version=schema_version,
        status=status,
        passed=passed,
        generated_at=generated_at,
        modified_at=modified_at,
        producer_command=artifact_input.producer_command,
        byte_count=byte_count,
        artifact_sha256=artifact_sha256,
        repository_commit_sha=repository_commit_sha,
    )


def _embedded_repository_commit_sha(payload: dict[str, Any]) -> str | None:
    direct = _string_or_none(payload.get("repository_commit_sha"))
    if direct:
        return direct
    repository = payload.get("repository")
    if not isinstance(repository, dict):
        return None
    return _string_or_none(
        repository.get("expected_commit_sha") or repository.get("commit_sha")
    )


def _artifact_evidence_errors(name: str, payload: dict[str, Any]) -> tuple[str, ...]:
    if name != "workflow_queue_evidence":
        return ()
    from scripts.quality.generate_workflow_queue_evidence import (
        validate_workflow_queue_evidence,
    )

    return validate_workflow_queue_evidence(payload)


def _status_from_payload(payload: dict[str, Any]) -> tuple[str, bool]:
    if _has_items(payload.get("failures")):
        return "failed", False
    if _has_items(payload.get("warnings")):
        return "warned", False

    explicit_passed = payload.get("passed")
    if isinstance(explicit_passed, bool):
        return ("passed", True) if explicit_passed else ("failed", False)

    comparison = payload.get("comparison")
    if isinstance(comparison, dict):
        if _has_items(comparison.get("failures")):
            return "failed", False
        if _has_items(comparison.get("warnings")):
            return "warned", False
        comparison_passed = comparison.get("passed")
        if isinstance(comparison_passed, bool):
            return ("passed", True) if comparison_passed else ("failed", False)

    pdf_scorecard = payload.get("pdf_benchmark_scorecard")
    if isinstance(pdf_scorecard, dict):
        if pdf_scorecard.get("evidence_complete") is False:
            return "incomplete", False
        if _has_items(pdf_scorecard.get("failures")):
            return "failed", False
        if _has_items(pdf_scorecard.get("warnings")):
            return "warned", False
        scorecard_passed = pdf_scorecard.get("passed")
        if isinstance(scorecard_passed, bool):
            return ("passed", True) if scorecard_passed else ("failed", False)

    return "passed", True


def _pdf_candidate_status(payload: dict[str, Any]) -> tuple[str, bool]:
    if any(key in payload for key in ("passed", "failures", "warnings", "status")):
        return "invalid", False
    skipped_pdf_paths = payload.get("skipped_pdf_paths")
    comparison = payload.get("comparison")
    if (
        not isinstance(skipped_pdf_paths, list)
        or skipped_pdf_paths
        or not isinstance(comparison, dict)
    ):
        return "invalid", False

    comparison_passed = comparison.get("passed")
    failures = comparison.get("failures")
    warnings = comparison.get("warnings")
    rows = comparison.get("rows")
    if (
        type(comparison_passed) is not bool
        or not isinstance(failures, list)
        or not isinstance(warnings, list)
        or not isinstance(rows, list)
        or "status" in comparison
        or not rows
    ):
        return "invalid", False
    if failures or not comparison_passed:
        return "failed", False

    warning_paths: set[str] = set()
    for warning in warnings:
        if not isinstance(warning, dict):
            return "invalid", False
        pdf_path = warning.get("pdf_path")
        reason = warning.get("reason")
        detail = warning.get("detail")
        if (
            not isinstance(pdf_path, str)
            or not pdf_path.strip()
            or pdf_path in warning_paths
            or not isinstance(reason, str)
            or reason not in _PDF_CANDIDATE_ADVISORY_WARNING_REASONS
            or not isinstance(detail, str)
            or not detail.strip()
        ):
            return "invalid", False
        warning_paths.add(pdf_path)

    row_paths: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            return "invalid", False
        pdf_path = row.get("pdf_path")
        row_status = row.get("status")
        expected_count = row.get("expected_candidate_count")
        actual_count = row.get("actual_candidate_count")
        expected_signature = row.get("expected_signature")
        actual_signature = row.get("actual_signature")
        expected_degraded_pages = row.get("expected_degraded_page_count")
        actual_degraded_pages = row.get("actual_degraded_page_count")
        expected_pdf_sha256 = row.get("expected_pdf_sha256")
        actual_pdf_sha256 = row.get("actual_pdf_sha256")
        if (
            not isinstance(pdf_path, str)
            or not pdf_path.strip()
            or not isinstance(row_status, str)
            or row_status not in {"passed", "warned"}
            or type(expected_count) is not int
            or type(actual_count) is not int
            or expected_count < 0
            or actual_count < 0
            or not isinstance(expected_signature, str)
            or not expected_signature
            or not isinstance(actual_signature, str)
            or not actual_signature
            or type(expected_degraded_pages) is not int
            or type(actual_degraded_pages) is not int
            or expected_degraded_pages < 0
            or actual_degraded_pages < 0
            or not isinstance(expected_pdf_sha256, str)
            or not isinstance(actual_pdf_sha256, str)
            or not actual_pdf_sha256
        ):
            return "invalid", False
        if pdf_path in row_paths:
            return "invalid", False
        if (
            expected_count != actual_count
            or expected_signature != actual_signature
            or expected_degraded_pages != actual_degraded_pages
            or (expected_pdf_sha256 and expected_pdf_sha256 != actual_pdf_sha256)
        ):
            return "failed", False
        if (row_status == "warned") != (pdf_path in warning_paths):
            return "invalid", False
        row_paths.add(pdf_path)

    if not warning_paths.issubset(row_paths):
        return "invalid", False

    if not _pdf_candidate_comparison_matches_canonical_baseline(payload):
        return "invalid", False
    return ("warned", True) if warnings else ("passed", True)


def _pdf_candidate_comparison_matches_canonical_baseline(
    payload: dict[str, Any],
) -> bool:
    from scripts.quality.pdf_candidate_benchmark import (
        DEFAULT_BASELINE_PATH,
        PdfCandidateBenchmarkObservation,
        compare_benchmark_observations,
        load_benchmark_baseline,
    )

    baseline_path_text = payload.get("baseline_path")
    observation_payloads = payload.get("observations")
    iterations = payload.get("iterations")
    if (
        not isinstance(baseline_path_text, str)
        or not baseline_path_text.strip()
        or not isinstance(observation_payloads, list)
        or not observation_payloads
        or type(iterations) is not int
        or iterations < 1
    ):
        return False

    baseline_path = Path(baseline_path_text)
    if not baseline_path.is_absolute():
        baseline_path = ROOT / baseline_path
    canonical_baseline_path = (ROOT / DEFAULT_BASELINE_PATH).resolve()
    try:
        if baseline_path.resolve() != canonical_baseline_path:
            return False
        baseline_entries = load_benchmark_baseline(canonical_baseline_path)
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        return False

    baseline_by_path = {entry.pdf_path: entry for entry in baseline_entries}
    if (
        not baseline_entries
        or len(baseline_by_path) != len(baseline_entries)
        or len({entry.report_name for entry in baseline_entries})
        != len(baseline_entries)
    ):
        return False

    observations: list[PdfCandidateBenchmarkObservation] = []
    observed_paths: set[str] = set()
    for observation_payload in observation_payloads:
        if not isinstance(observation_payload, dict) or set(observation_payload) != {
            "pdf_path",
            "report_name",
            "candidate_count",
            "signature",
            "degraded_page_count",
            "durations_seconds",
            "median_seconds",
            "pdf_sha256",
        }:
            return False
        pdf_path = observation_payload.get("pdf_path")
        report_name = observation_payload.get("report_name")
        candidate_count = observation_payload.get("candidate_count")
        signature = observation_payload.get("signature")
        degraded_page_count = observation_payload.get("degraded_page_count")
        durations_seconds = observation_payload.get("durations_seconds")
        median_seconds = observation_payload.get("median_seconds")
        pdf_sha256 = observation_payload.get("pdf_sha256")
        if (
            not isinstance(pdf_path, str)
            or not pdf_path.strip()
            or pdf_path in observed_paths
            or pdf_path not in baseline_by_path
            or report_name != baseline_by_path[pdf_path].report_name
            or type(candidate_count) is not int
            or candidate_count < 0
            or not isinstance(signature, str)
            or not signature
            or type(degraded_page_count) is not int
            or degraded_page_count < 0
            or not isinstance(durations_seconds, list)
            or len(durations_seconds) != iterations
            or any(
                not _nonnegative_finite_number(duration)
                for duration in durations_seconds
            )
            or not _nonnegative_finite_number(median_seconds)
            or round(float(statistics.median(durations_seconds)), 6) != median_seconds
            or not isinstance(pdf_sha256, str)
            or not pdf_sha256
        ):
            return False
        try:
            observations.append(
                PdfCandidateBenchmarkObservation(
                    pdf_path=pdf_path,
                    report_name=report_name,
                    candidate_count=candidate_count,
                    signature=signature,
                    degraded_page_count=degraded_page_count,
                    durations_seconds=tuple(durations_seconds),
                    median_seconds=median_seconds,
                    pdf_sha256=pdf_sha256,
                )
            )
        except (TypeError, ValueError):
            return False
        observed_paths.add(pdf_path)

    if observed_paths != set(baseline_by_path):
        return False

    expected = compare_benchmark_observations(
        baseline_entries=baseline_entries,
        observations=observations,
        fail_on_runtime_regression=False,
    )
    expected_payload = {
        "passed": expected.passed,
        "failures": [asdict(issue) for issue in expected.failures],
        "warnings": [asdict(issue) for issue in expected.warnings],
        "rows": [asdict(row) for row in expected.rows],
    }
    return payload["comparison"] == expected_payload


def _has_items(value: Any) -> bool:
    return isinstance(value, list) and bool(value)


def _nonnegative_finite_number(value: Any) -> bool:
    if type(value) not in {int, float} or value < 0:
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _datetime_text(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat()


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _git_commit_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "failed to resolve git commit SHA")
    return result.stdout.strip()


def _parse_key_value(value: str, *, flag_name: str) -> tuple[str, str]:
    if "=" not in value:
        raise ValueError(f"{flag_name} must use name=value format: {value}")
    key, raw = value.split("=", 1)
    key = key.strip()
    raw = raw.strip()
    if not key or not raw:
        raise ValueError(f"{flag_name} must include a non-empty name and value")
    return key, raw


def _artifact_inputs(
    artifacts: Sequence[str],
    expected_schemas: Sequence[str],
    artifact_commands: Sequence[str],
) -> tuple[ReleaseEvidenceArtifactInput, ...]:
    expected_by_name = {
        name: version
        for name, version in (
            _parse_key_value(value, flag_name="--expected-schema")
            for value in expected_schemas
        )
    }
    command_by_name = {
        name: command
        for name, command in (
            _parse_key_value(value, flag_name="--artifact-command")
            for value in artifact_commands
        )
    }
    inputs: list[ReleaseEvidenceArtifactInput] = []
    for value in artifacts:
        name, raw_path = _parse_key_value(value, flag_name="--artifact")
        expected_schema = expected_by_name.get(name)
        if expected_schema is None:
            raise ValueError(f"Missing --expected-schema {name}=<version>")
        inputs.append(
            ReleaseEvidenceArtifactInput(
                name=name,
                path=(ROOT / raw_path).resolve(),
                expected_schema_version=expected_schema,
                producer_command=command_by_name.get(name, ""),
            )
        )
    return tuple(inputs)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Write a release evidence manifest for retained quality-gate artifacts."
        )
    )
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--expected-schema", action="append", default=[])
    parser.add_argument("--artifact-command", action="append", default=[])
    parser.add_argument("--commit-sha", default="")
    parser.add_argument("--fresh-after", default="")
    parser.add_argument("--require-head-commit", action="store_true")
    parser.add_argument(
        "--allow-issues",
        action="store_true",
        help="Write failed manifests without making this command the approval gate.",
    )
    parser.add_argument(
        "--output-json",
        default="out/release_evidence_manifest.json",
    )
    args = parser.parse_args(argv)
    artifact_inputs = _artifact_inputs(
        args.artifact,
        args.expected_schema,
        args.artifact_command,
    )
    if not artifact_inputs:
        raise ValueError("At least one --artifact is required.")
    commit_sha = args.commit_sha or _git_commit_sha()
    expected_commit_sha = _git_commit_sha() if args.require_head_commit else None
    command_args = tuple(
        sys.argv if argv is None else ("release_evidence_manifest", *argv)
    )
    manifest = build_release_evidence_manifest(
        artifact_inputs=artifact_inputs,
        release_id=args.release_id,
        commit_sha=commit_sha,
        command_args=command_args,
        fresh_after=args.fresh_after or None,
        expected_commit_sha=expected_commit_sha,
    )
    write_release_evidence_manifest(manifest, (ROOT / args.output_json).resolve())
    print(json.dumps(asdict(manifest), ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if manifest.passed or args.allow_issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
