from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.quality.replay_validation_repair_benchmark import (
    _benchmark_manifest,
    _case_paths,
    _validation_report,
)
from src.utils.cache_utils import sha256_json


def test_benchmark_manifest_requires_its_frozen_self_hash(tmp_path: Path) -> None:
    body = {"schema_version": "1.0", "frozen": True, "cases": []}
    canonical = (
        json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    body["manifest_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(body), encoding="utf-8")

    loaded, expected = _benchmark_manifest(path)
    assert loaded["frozen"] is True
    assert expected == body["manifest_sha256"]

    body["frozen"] = False
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest is invalid"):
        _benchmark_manifest(path)


def test_benchmark_case_inputs_are_hash_pinned_and_workspace_local(
    tmp_path: Path,
) -> None:
    artifact = {"schema_version": "1.0", "summary": {"tldr": "retained"}}
    artifact_path = tmp_path / "artifacts.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    case = {
        "input_files": {
            "artifacts": {
                "path": "artifacts.json",
                "sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            }
        },
        "original_artifact_canonical_sha256": sha256_json(artifact),
    }

    paths, observed_path = _case_paths(case, tmp_path)
    assert paths["artifacts"] == artifact_path.resolve()
    assert observed_path == artifact_path.resolve()

    case["input_files"]["artifacts"]["path"] = "../outside.json"
    with pytest.raises(ValueError, match="outside workspace"):
        _case_paths(case, tmp_path)


def test_benchmark_reuses_the_retained_initial_validation_failures() -> None:
    report = _validation_report(
        {
            "schema_version": "1.0",
            "issues": [
                {
                    "message": "retained validator failure",
                    "severity": "error",
                    "affected_section": "summary.tldr",
                    "rule_id": "grounding",
                    "repair_target": "summary",
                    "entity_id": "summary:1",
                    "evidence_ids": ["finding:1"],
                }
            ],
        }
    )
    assert report.status == "fail"
    assert report.issues[0].rule_id == "grounding"
    assert report.issues[0].repair_target == "summary"
