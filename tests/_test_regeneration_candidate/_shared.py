# ruff: noqa: F401
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_regeneration_candidate.py"
)

import hashlib

import json

from copy import deepcopy

from pathlib import Path

from types import SimpleNamespace

import pytest

from src.contracts.run_context import RunContext

from src.contracts.validation import ValidationReport

from src.generators.artifact_normalization import (
    discard_location_only_insights,
    discard_location_only_quotes,
    normalize_artifact_evidence_ids,
    normalize_artifact_insights,
)

from src.generators._artifact_generator.family_policy import (
    build_artifact_family_status,
)

from src.generators.claim_validation_generator import validate_retained_claims

from src.generators.validation.metrics import validate_insight_metrics

from src.generators.validation.numbers import validate_new_numbers

from src.generators.validation.regeneration_candidate import (
    CandidateIntegrityResult,
    _verify_derived_artifact_roots,
    retained_claim_repair_issues,
    validate_regeneration_candidate,
)

from src.orchestrators._report_analysis_orchestrator.validation import (
    _candidate_audit,
    _failure_fingerprint,
    _repair_delta,
    _scope_validation_report,
    _with_retained_claim_repair_diagnostics,
)

from tests._test_validation_generator._shared import _report

_FIXTURE_ROOT = (
    Path(__file__).parent
    / "fixtures"
    / "docpacks"
    / "golden"
    / "the-akin-the-quarantine-cohort-exec-summary-pdf"
    / "report_analysis"
)


def _retained_artifact_and_evidence() -> tuple[dict, dict]:
    artifacts = json.loads((_FIXTURE_ROOT / "artifacts.json").read_text("utf-8"))
    evidence_packs = {
        path.stem: json.loads(path.read_text("utf-8"))
        for path in _FIXTURE_ROOT.glob("*.json")
        if path.stem not in {"artifacts", "validation", "analysis_vector_store"}
    }
    return artifacts, evidence_packs


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="run",
        task_id="task",
        span_id="span",
    )


def _soft_copy_claim(
    *,
    family: str,
    text: str,
    evidence_id: str = "qc_001",
    page: int = 6,
    regeneration_attempt: int = 0,
) -> dict[str, object]:
    normalized = " ".join(text.split())
    return {
        "schema_version": "1.0",
        "artifact_family": family,
        "claim_id": f"soft_copy:{family}:{hashlib.sha256(normalized.encode()).hexdigest()[:16]}",
        "text_hash": hashlib.sha256(normalized.encode()).hexdigest(),
        "classification": "factual",
        "evidence_ids": [evidence_id],
        "source_spans": [
            {
                "evidence_id": evidence_id,
                "source_pack": "quote_candidates",
                "page": page,
            }
        ],
        "producing_prompt_identity": {
            "namespace": f"report_vs/artifacts/{family}",
            "prompt_content_hash": "a" * 64,
        },
        "generation_attempt": 1,
        "regeneration_attempt": regeneration_attempt,
    }


def _soft_copy_artifacts() -> tuple[dict, dict, dict]:
    current, evidence_packs = _retained_artifact_and_evidence()
    current["expert_comment"] = "Generation Q is a distinct cohort."
    current["linkedin_post"] = "Generation Q formed identities online."
    current["soft_copy_claim_provenance"] = {
        "schema_version": "1.0",
        "claims": [
            _soft_copy_claim(family="expert_comment", text=current["expert_comment"]),
            _soft_copy_claim(family="linkedin_post", text=current["linkedin_post"]),
        ],
    }
    return current, deepcopy(current), evidence_packs


def _baseline_retained_claim_warnings(
    artifacts: dict, evidence_packs: dict
) -> dict[str, str]:
    """Model unrelated findings already accepted as warnings in these fixtures."""

    return {
        _failure_fingerprint(issue).key: "warning"
        for issue in retained_claim_repair_issues(artifacts, evidence_packs)
    }


def _claim_for_family(artifacts: dict, family: str) -> dict:
    return next(
        claim
        for claim in artifacts["soft_copy_claim_provenance"]["claims"]
        if claim["artifact_family"] == family
    )


def _complete_repair_selection(
    *, original_claim_id: str, repaired_claim_id: str
) -> dict[str, object]:
    """Build a complete Prompt 5 selection record for candidate fixtures."""

    selection: dict[str, object] = {
        "schema_version": "1.0",
        "claim_id": original_claim_id,
        "strategy": "claim_evidence_ids",
        "direct_evidence_ids": ["qc_001"],
        "parent_evidence_ids": [],
        "quarantined_evidence_ids": [],
        "selected_evidence_ids": ["qc_001"],
        "selected_evidence_entries": [
            {"id": "qc_001", "page": 6, "text": "Quoted evidence."}
        ],
        "repaired_claim_id": repaired_claim_id,
    }
    _refresh_repair_selection_hash(selection)
    return selection


def _refresh_repair_selection_hash(selection: dict[str, object]) -> None:
    hash_payload = {
        name: value
        for name, value in selection.items()
        if name not in {"package_sha256", "repaired_claim_id"}
    }
    selection["package_sha256"] = hashlib.sha256(
        json.dumps(
            hash_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    ).hexdigest()


__all__ = [
    name
    for name in globals()
    if name
    not in {
        "__name__",
        "__annotations__",
        "__doc__",
        "__spec__",
        "__file__",
        "__package__",
        "__loader__",
        "__cached__",
        "__builtins__",
        "_SplitPath",
    }
]
