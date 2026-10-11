"""Render a bounded GitHub release-evidence job summary."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
MAX_SUMMARY_BYTES = 2048
MAX_INPUT_BYTES = 4 * 1024 * 1024
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_BUILD_ID_RE = re.compile(r"^[0-9]{1,20}-[0-9]{1,3}$")
_CORPUS_SCOPES = {
    "representative_report_processing": "representative",
    "post_remediation_smoke_only": "smoke-only",
    "not_declared": "unavailable",
}
_UNTRUSTED_ARTIFACT_STATES = {
    "expired",
    "incompatible",
    "invalid",
    "missing",
    "stale",
}
_ARTIFACT_STATES = _UNTRUSTED_ARTIFACT_STATES | {
    "failed",
    "incomplete",
    "passed",
    "warned",
}


def render_release_evidence_job_summary(
    *,
    review: dict[str, Any] | None,
    queue_evidence: dict[str, Any] | None,
    tested_sha: str,
    expected_run_id: str | None = None,
    runtime_evidence: dict[str, Any] | None = None,
    artifact_url: str | None = None,
) -> str:
    """Render fixed scalar fields; evidence payload text is never interpolated."""
    normalized_sha = tested_sha.strip().lower()
    if not _SHA_RE.fullmatch(normalized_sha):
        normalized_sha = ""

    review_state, issue_count, build_id, reviewed_at = _review_state(
        review,
        expected_sha=normalized_sha,
        expected_run_id=expected_run_id,
    )
    queue_state = _queue_state(queue_evidence, expected_sha=normalized_sha)
    runtime_state, corpus_scope = _runtime_state(
        runtime_evidence, expected_sha=normalized_sha
    )
    safe_artifact_url = _safe_actions_run_url(artifact_url)
    artifact_availability = "unverified" if safe_artifact_url else "unavailable"

    # This step precedes upload, and the collector records a declared scope
    # rather than verifying representative workflow execution.
    all_evidence_passed = (
        review_state == "passed"
        and queue_state == "passed"
        and runtime_state == "passed"
        and corpus_scope == "representative"
        and artifact_availability == "available"
    )
    final_disposition = "passed" if all_evidence_passed else "non-green"
    artifact_reference = (
        f"[release-evidence-bundle lookup in this workflow run]({safe_artifact_url})"
        if safe_artifact_url
        else "`release-evidence-bundle` (workflow run link unavailable)"
    )
    issue_count_text = str(issue_count) if issue_count is not None else "unavailable"
    lines = [
        "## Release evidence review",
        "",
        f"- Final reviewer disposition: `{final_disposition}`",
        f"- Tested SHA: `{normalized_sha or 'unavailable'}`",
        f"- Evidence build: `{build_id or 'unavailable'}`",
        f"- Evidence generated at: `{reviewed_at or 'unavailable'}`",
        f"- Release-review disposition: `{review_state}`",
        f"- Queue-evidence disposition: `{queue_state}`",
        f"- Unwaived issue count: `{issue_count_text}`",
        f"- Runtime-corpus evidence: `{runtime_state}`",
        f"- Runtime-corpus scope: `{corpus_scope}`",
        (
            f"- Artifact availability: `{artifact_availability}` "
            "(upload follows this summary; retention is 14 days)"
        ),
        f"- Canonical artifact reference: {artifact_reference}",
        (
            "- Queue scope: deterministic temporary-SQLite; "
            "not live production throughput proof."
        ),
        (
            "- Full canonical issues are not copied here; the bundled review "
            "JSON/Markdown contains them when upload succeeds."
        ),
        "",
    ]
    if corpus_scope == "smoke-only":
        lines.insert(
            -3,
            (
                "- Runtime-corpus limitation: smoke-only evidence does not "
                "establish representative report-processing coverage."
            ),
        )
    elif corpus_scope == "representative":
        lines.insert(
            -3,
            (
                "- Runtime-corpus limitation: the scope declaration does not "
                "verify that representative processing ran."
            ),
        )
    summary = "\n".join(lines)
    if len(summary.encode("utf-8")) > MAX_SUMMARY_BYTES:
        return (
            "\n".join(
                (
                    "## Release evidence review",
                    "",
                    "- Final reviewer disposition: `non-green`",
                    "- Summary output exceeded its fixed bound.",
                )
            )
            + "\n"
        )
    return summary


def _review_state(
    review: dict[str, Any] | None,
    *,
    expected_sha: str,
    expected_run_id: str | None,
) -> tuple[str, int | None, str | None, str | None]:
    if review is None:
        return "unavailable", None, None, None
    if not expected_sha or review.get("schema_version") != "1.0":
        return "incompatible", None, None, None

    commit_shas = review.get("commit_shas")
    if not isinstance(commit_shas, list) or len(commit_shas) != 1:
        return "incompatible", None, None, None
    commit_sha = commit_shas[0]
    if not isinstance(commit_sha, str) or not _SHA_RE.fullmatch(commit_sha.lower()):
        return "incompatible", None, None, None
    if commit_sha.lower() != expected_sha:
        return "mismatched", None, None, None

    release_ids = review.get("release_ids")
    if (
        not isinstance(release_ids, list)
        or len(release_ids) != 1
        or not isinstance(release_ids[0], str)
        or not _BUILD_ID_RE.fullmatch(release_ids[0])
    ):
        return "incompatible", None, None, None
    build_id = release_ids[0]
    if expected_run_id and build_id != expected_run_id:
        return "mismatched", None, build_id, None

    issues = review.get("issues")
    artifacts = review.get("artifacts")
    waiver_errors = review.get("waiver_errors")
    unwaived_issue_count = review.get("unwaived_issue_count")
    waiver_error_count = review.get("waiver_error_count")
    if (
        not isinstance(issues, list)
        or not isinstance(artifacts, list)
        or not artifacts
        or not isinstance(waiver_errors, list)
        or not _is_count(review.get("artifact_count"))
        or not _is_count(review.get("issue_count"))
        or not _is_count(review.get("waived_issue_count"))
        or not _is_count(unwaived_issue_count)
        or not _is_count(waiver_error_count)
        or not isinstance(review.get("passed"), bool)
        or not isinstance(review.get("manifest_passed"), bool)
    ):
        return "incompatible", None, build_id, None

    issue_rows: list[dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict) or not isinstance(issue.get("waived"), bool):
            return "incompatible", None, build_id, None
        issue_rows.append(issue)
    derived_unwaived_count = sum(not issue["waived"] for issue in issue_rows)
    derived_waived_count = len(issue_rows) - derived_unwaived_count
    if (
        len(artifacts) != review["artifact_count"]
        or len(issue_rows) != review["issue_count"]
        or derived_waived_count != review["waived_issue_count"]
        or derived_unwaived_count != unwaived_issue_count
        or len(waiver_errors) != waiver_error_count
    ):
        return "incompatible", None, build_id, None

    required_artifact_failed = False
    for artifact in artifacts:
        if (
            not isinstance(artifact, dict)
            or not isinstance(artifact.get("required"), bool)
            or not isinstance(artifact.get("passed"), bool)
        ):
            return "incompatible", None, build_id, None
        status = artifact.get("status")
        if not isinstance(status, str) or status not in _ARTIFACT_STATES:
            return "incompatible", None, build_id, None
        if artifact["passed"] != (status == "passed"):
            return "incompatible", None, build_id, None
        if not artifact["required"]:
            continue
        if status in _UNTRUSTED_ARTIFACT_STATES:
            required_artifact_failed = True

    if not isinstance(review.get("generated_at"), str):
        return "incompatible", None, build_id, None
    generated_at = _safe_timestamp(review["generated_at"])
    if not generated_at:
        return "incompatible", None, build_id, None

    if required_artifact_failed:
        return "failed", unwaived_issue_count, build_id, generated_at
    if (
        review["passed"] is not True
        or review["manifest_passed"] is not True
        or unwaived_issue_count != 0
        or waiver_error_count != 0
    ):
        return "failed", unwaived_issue_count, build_id, generated_at
    return "passed", unwaived_issue_count, build_id, generated_at


def _queue_state(queue_evidence: dict[str, Any] | None, *, expected_sha: str) -> str:
    if queue_evidence is None:
        return "unavailable"
    if not expected_sha or queue_evidence.get("schema_version") != "1.0":
        return "incompatible"

    repository = queue_evidence.get("repository")
    if not isinstance(repository, dict):
        return "incompatible"
    evidence_shas = (
        queue_evidence.get("repository_commit_sha"),
        repository.get("expected_commit_sha"),
        repository.get("initial_commit_sha"),
        repository.get("final_commit_sha"),
    )
    if not all(
        isinstance(value, str) and _SHA_RE.fullmatch(value.lower())
        for value in evidence_shas
    ):
        return "incompatible"
    if any(value.lower() != expected_sha for value in evidence_shas):
        return "mismatched"

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from scripts.quality.generate_workflow_queue_evidence import (
        validate_workflow_queue_evidence,
    )

    validation_failures = validate_workflow_queue_evidence(queue_evidence)
    if validation_failures:
        return "failed"
    if queue_evidence.get("passed") is not True:
        return "failed"
    failures = queue_evidence.get("failures")
    if not isinstance(failures, list) or failures:
        return "incompatible"
    return "passed"


def _runtime_state(
    runtime_evidence: dict[str, Any] | None, *, expected_sha: str
) -> tuple[str, str]:
    if runtime_evidence is None:
        return "unavailable", "unavailable"
    if not expected_sha or runtime_evidence.get("schema_version") != "1.0":
        return "incompatible", "unavailable"

    runtime_sha = runtime_evidence.get("repository_commit_sha")
    if not isinstance(runtime_sha, str) or not _SHA_RE.fullmatch(runtime_sha.lower()):
        return "incompatible", "unavailable"
    if runtime_sha.lower() != expected_sha:
        return "mismatched", "unavailable"

    log_corpus = runtime_evidence.get("log_corpus")
    if not isinstance(log_corpus, dict):
        return "incompatible", "unavailable"
    if (
        not isinstance(runtime_evidence.get("evidence_run_id"), str)
        or not runtime_evidence["evidence_run_id"]
        or not _safe_timestamp(str(runtime_evidence.get("generated_at") or ""))
        or not isinstance(log_corpus.get("scope_attestation"), str)
        or not isinstance(log_corpus.get("repository_provenance"), str)
    ):
        return "incompatible", "unavailable"
    raw_scope = log_corpus.get("operator_declared_scope")
    corpus_scope = _CORPUS_SCOPES.get(raw_scope) if isinstance(raw_scope, str) else None
    if corpus_scope is None:
        return "incompatible", "unavailable"
    if corpus_scope == "unavailable":
        return "unavailable", corpus_scope

    evidence_status = runtime_evidence.get("status")
    passed = runtime_evidence.get("passed")
    freshness_state = runtime_evidence.get("freshness_state")
    if (
        not isinstance(evidence_status, str)
        or evidence_status not in {"passed", "failed", "incomplete", "unavailable"}
        or not isinstance(passed, bool)
        or not isinstance(freshness_state, str)
        or freshness_state
        not in {"passed", "failed", "unverified", "not_required", "unavailable"}
        or passed != (evidence_status == "passed")
    ):
        return "incompatible", "unavailable"

    if corpus_scope == "representative":
        if evidence_status == "unavailable":
            return "unavailable", corpus_scope
        if evidence_status == "incomplete":
            return "incomplete", corpus_scope
        if not passed or freshness_state != "passed":
            return "failed", corpus_scope
        return "declared_unverified", corpus_scope
    if passed and freshness_state in {"passed", "not_required"}:
        return "passed", corpus_scope
    return "failed", corpus_scope


def _safe_actions_run_url(value: str | None) -> str | None:
    if not isinstance(value, str) or len(value) > 500:
        return None
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.netloc != parsed.hostname
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"[A-Za-z0-9.-]+", parsed.hostname)
        or not re.fullmatch(
            r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions/runs/[0-9]+",
            parsed.path,
        )
        or ".." in parsed.path.split("/")
    ):
        return None
    return value


def _safe_timestamp(value: str) -> str | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC).isoformat(timespec="seconds")


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _read_object(path: Path) -> dict[str, Any] | None:
    try:
        if path.stat().st_size > MAX_INPUT_BYTES:
            return {}
        raw = path.read_bytes()
    except OSError:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _actions_context() -> tuple[str | None, str | None]:
    server_url = os.environ.get("GITHUB_SERVER_URL", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
    parsed_server = urlparse(server_url)
    if (
        parsed_server.scheme != "https"
        or not parsed_server.hostname
        or parsed_server.username is not None
        or parsed_server.password is not None
        or parsed_server.query
        or parsed_server.fragment
        or parsed_server.path not in {"", "/"}
        or not re.fullmatch(r"[A-Za-z0-9.-]+", parsed_server.hostname)
        or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
        or not run_id.isdigit()
        or not attempt.isdigit()
    ):
        return None, None
    url = f"{server_url.rstrip('/')}/{repository}/actions/runs/{run_id}"
    run_key = f"{run_id}-{attempt}"
    return run_key, _safe_actions_run_url(url)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Append bounded release-evidence status to the GitHub job summary."
    )
    parser.add_argument("--review-json", required=True)
    parser.add_argument("--queue-evidence-json", required=True)
    parser.add_argument("--runtime-evidence-json")
    parser.add_argument("--output-path", required=True)
    args = parser.parse_args(argv)

    expected_run_id, artifact_url = _actions_context()
    tested_sha = os.environ.get("GITHUB_SHA") or _git_head()
    runtime_path = (
        (ROOT / args.runtime_evidence_json).resolve()
        if args.runtime_evidence_json
        else None
    )
    summary = render_release_evidence_job_summary(
        review=_read_object((ROOT / args.review_json).resolve()),
        queue_evidence=_read_object((ROOT / args.queue_evidence_json).resolve()),
        tested_sha=tested_sha,
        expected_run_id=expected_run_id,
        runtime_evidence=_read_object(runtime_path) if runtime_path else None,
        artifact_url=artifact_url,
    )
    with Path(args.output_path).open("a", encoding="utf-8") as handle:
        handle.write(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
