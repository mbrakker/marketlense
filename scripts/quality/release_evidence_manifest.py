from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[2]


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
    )


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


def _has_items(value: Any) -> bool:
    return isinstance(value, list) and bool(value)


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
