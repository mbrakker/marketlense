"""Persist an immutable, hash-bound Step 2 adversarial acceptance artifact.

The acceptance decision remains owned by the existing adversarial comparator.  This
module only records that decision and the source/provenance fields needed to audit
it later; it never promotes a claim or writes a canonical artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.quality.replay_verified_claims_step2_adversarial import (
    compare_adversarial_outcomes,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "1.0"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_sha() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return completed.stdout.strip()


def _case_row(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {"result_present": False}
    fields = (
        "candidate_id",
        "case_id",
        "outcome",
        "failure_reason",
        "original_claim",
        "final_claim",
        "source_identity",
        "source_pdf_sha256_expected",
        "source_pdf_sha256_actual",
        "physical_page",
        "physical_pages",
        "original_physical_pages",
        "inspected_physical_pages",
        "recovered_physical_pages",
        "supporting_physical_pages",
        "evidence_ids",
        "evidence_spans",
        "source_binding_status",
        "source_truth_notes_by_page",
        "correction_attempts",
        "verification_attempts",
    )
    return {
        "result_present": True,
        **{field: row.get(field) for field in fields if field in row},
    }


def build_adversarial_acceptance_artifact(
    *,
    corpus: Mapping[str, Any],
    result: Mapping[str, Any],
    comparator: Mapping[str, Any],
    corpus_sha256: str,
    result_sha256: str,
    comparator_sha256: str,
    git_sha: str = "",
    corpus_path: str = "",
    result_path: str = "",
) -> dict[str, Any]:
    """Build the immutable acceptance record without changing either input."""

    rows_by_id: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    raw_rows = result.get("claims")
    if isinstance(raw_rows, list):
        for row in raw_rows:
            if isinstance(row, Mapping) and isinstance(row.get("candidate_id"), str):
                rows_by_id[row["candidate_id"]].append(row)

    cases: list[dict[str, Any]] = []
    raw_cases = corpus.get("cases")
    if isinstance(raw_cases, list):
        for raw_case in raw_cases:
            if not isinstance(raw_case, Mapping):
                cases.append({"case_present": False})
                continue
            candidate_id = str(raw_case.get("candidate_id") or "")
            matching_rows = rows_by_id.get(candidate_id, [])
            case_record = {
                "case_id": raw_case.get("case_id"),
                "candidate_id": candidate_id,
                "expected_terminal": raw_case.get("expected_terminal"),
                "expected_physical_pages": raw_case.get("physical_pages"),
                "result_count": len(matching_rows),
                "result": _case_row(matching_rows[0])
                if len(matching_rows) == 1
                else {
                    "result_present": bool(matching_rows),
                    "ambiguous_result": True,
                    "rows": [_case_row(row) for row in matching_rows],
                },
            }
            if len(matching_rows) == 1:
                row = matching_rows[0]
                for field in (
                    "outcome",
                    "original_claim",
                    "final_claim",
                    "source_identity",
                    "source_pdf_sha256_expected",
                    "source_pdf_sha256_actual",
                    "physical_pages",
                    "original_physical_pages",
                    "inspected_physical_pages",
                    "supporting_physical_pages",
                    "evidence_ids",
                    "evidence_spans",
                    "source_truth_notes_by_page",
                ):
                    if field in row:
                        case_record[field] = row.get(field)
            cases.append(case_record)

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_kind": "verified_claims_step2_adversarial_acceptance",
        "immutable": True,
        "corpus_path": corpus_path,
        "result_path": result_path,
        "corpus_sha256": corpus_sha256,
        "result_sha256": result_sha256,
        "comparator_sha256": comparator_sha256,
        "comparator_git_sha": git_sha,
        "acceptance": dict(comparator),
        "cases": cases,
        "canonical_mutation": False,
        "publication_write": False,
    }


def write_immutable_artifact(path: Path, artifact: Mapping[str, Any]) -> None:
    """Create exactly one artifact; accidental overwrites are refused."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(artifact, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def persist_adversarial_acceptance(
    *, corpus_path: Path, result_path: Path, output_path: Path
) -> dict[str, Any]:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    comparator = compare_adversarial_outcomes(corpus, result)
    comparator_path = (
        Path(__file__)
        .resolve()
        .with_name("replay_verified_claims_step2_adversarial.py")
    )
    artifact = build_adversarial_acceptance_artifact(
        corpus=corpus,
        result=result,
        comparator=comparator,
        corpus_sha256=_sha256(corpus_path),
        result_sha256=_sha256(result_path),
        comparator_sha256=_sha256(comparator_path),
        git_sha=_git_sha(),
        corpus_path=str(corpus_path),
        result_path=str(result_path),
    )
    write_immutable_artifact(output_path, artifact)
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    artifact = persist_adversarial_acceptance(
        corpus_path=args.corpus,
        result_path=args.result,
        output_path=args.output,
    )
    return 0 if artifact["acceptance"].get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
