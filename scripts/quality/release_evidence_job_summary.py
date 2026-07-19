"""Render a bounded GitHub release-evidence job summary."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
MAX_ISSUE_LINES = 10


def render_release_evidence_job_summary(
    *, review: dict[str, Any], queue_evidence: dict[str, Any], tested_sha: str
) -> str:
    """Keep reviewer-facing output scalar, explicit, and bounded."""
    issues = review.get("issues", [])
    issue_lines = [
        f"- `{issue.get('artifact_name', '')}`: `{issue.get('reason', '')}`"
        for issue in issues[:MAX_ISSUE_LINES]
        if isinstance(issue, dict)
    ]
    if len(issues) > MAX_ISSUE_LINES:
        issue_lines.append(
            f"- … {len(issues) - MAX_ISSUE_LINES} additional issue(s) omitted"
        )
    return "\n".join(
        [
            "## Release evidence",
            "",
            f"- Exact tested SHA: `{tested_sha}`",
            f"- Release-evidence status: `{'passed' if review.get('passed') else 'failed'}`",
            f"- Unwaived issue count: `{int(review.get('unwaived_issue_count', 0))}`",
            f"- Queue-evidence status: `{'passed' if queue_evidence.get('passed') else 'failed'}`",
            "- Artifact: `release-evidence-bundle`",
            "- Scope: deterministic temporary-SQLite queue evidence; not live production throughput proof.",
            "",
            "### Unwaived issues",
            "",
            *(issue_lines or ["- None."]),
            "",
        ]
    )


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


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
        raise RuntimeError(result.stderr.strip() or "unable to resolve repository HEAD")
    return result.stdout.strip()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Append bounded release-evidence status to the GitHub job summary."
    )
    parser.add_argument("--review-json", required=True)
    parser.add_argument("--queue-evidence-json", required=True)
    parser.add_argument("--output-path", required=True)
    args = parser.parse_args(argv)
    summary = render_release_evidence_job_summary(
        review=_read_object((ROOT / args.review_json).resolve()),
        queue_evidence=_read_object((ROOT / args.queue_evidence_json).resolve()),
        tested_sha=_git_head(),
    )
    with Path(args.output_path).open("a", encoding="utf-8") as handle:
        handle.write(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
