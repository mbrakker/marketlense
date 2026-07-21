from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.quality.collect_cto_review_evidence import (
    ArtifactIntegrityError,
    EvidencePaths,
    collect,
    validate_consistency,
)
from tests.test_collect_cto_review_evidence import _strict_paths


def test_tampered_leakage_artifact_fails_inventory_validation(tmp_path: Path) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    collect(paths)
    leakage_path = paths.output_dir / "log_content_leakage.json"
    leakage = json.loads(leakage_path.read_text())
    leakage["status"] = "failed"
    leakage_path.write_text(json.dumps(leakage), encoding="utf-8")

    with pytest.raises(ArtifactIntegrityError):
        validate_consistency(
            paths.output_dir,
            expected_run_id=json.loads(
                (paths.output_dir / "detailed_metrics.json").read_text()
            )["evidence_run_id"],
            strict=True,
        )


def test_atomic_replace_never_merges_prior_bundle_files(tmp_path: Path) -> None:
    paths, _, _, _ = _strict_paths(tmp_path)
    collect(paths)
    (paths.output_dir / "old-only.txt").write_text("obsolete", encoding="utf-8")
    replacement = EvidencePaths(
        **{
            **paths.__dict__,
            "replace_output": True,
            "evidence_run_id": "replacement-run",
        }
    )

    collect(replacement)

    assert not (replacement.output_dir / "old-only.txt").exists()
    manifest = json.loads(
        (replacement.output_dir / "evidence_run_manifest.json").read_text()
    )
    assert manifest["evidence_run_id"] == "replacement-run"
