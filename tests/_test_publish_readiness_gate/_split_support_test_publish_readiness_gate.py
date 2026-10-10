# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_publish_readiness_gate.py"
)

import json
import re
from copy import deepcopy
from pathlib import Path
import pytest
from src.contracts.validation import ValidationIssue, ValidationReport
from src.generators.publish_readiness_generator import (
    evaluate_publish_readiness as _evaluate_readiness_core,
)
from src.generators.publish_readiness_generator import (
    parse_publish_readiness_payload,
    publish_readiness_payload,
    verify_publish_readiness,
)
from src.utils.cache_utils import sha256_json
from src.utils.publication_projection import publication_projection_hash


def _evaluate_readiness_for_test(**kwargs):
    kwargs.setdefault("report_card_manifest_path", "report-card-manifest.json")
    return _evaluate_readiness_core(**kwargs)


def _ready_inputs() -> tuple[dict, dict, str, dict]:
    html = """<!doctype html>
<!--
marketbearing-build:
  git_sha: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  generation_run_id: generation-run-1
  validation_run_id: validation-run-1
  source_id: source:example
  source_md5: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
  artifact_hash: cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
  generation_profile: safe_default
  generated_at_utc: 2026-09-09T12:00:00+00:00
-->
<html><head>
<title>Revenue outlook 2026 | MarketLense</title>
<link rel="canonical" href="https://marketlense.example/reports/revenue-outlook">
<meta property="og:title" content="Revenue outlook 2026">
</head><body><h1>Revenue outlook 2026</h1>
<p>Revenue grew in the measured market.</p>
<section id="source"><a href="https://publisher.example/reports/revenue-outlook">
Open original source</a></section>
<script type="application/ld+json">{"@context":"https://schema.org",
"headline":"Revenue outlook 2026"}</script>
</body></html>"""
    artifacts = {
        "categories": ["markets"],
        "summary": {
            "claim_evidence_map": [
                {
                    "claim": "Revenue grew in the measured market.",
                    "evidence_id": "F1",
                    "evidence": "Revenue grew in the measured market.",
                }
            ]
        },
        "insights_final": [
            {
                "id": "I1",
                "text": "Revenue grew in the measured market.",
                "evidence_id": "F1",
                "evidence": "Revenue grew in the measured market.",
            }
        ],
        "quotes_final": [],
        "chart_insight_cards": [],
    }
    evidence_packs = {
        "findings": {
            "findings": [
                {
                    "id": "F1",
                    "snippet": "Revenue grew in the measured market.",
                    "page": 1,
                }
            ]
        }
    }
    provenance = {
        "publisher_landing_page_url": "https://publisher.example/reports/revenue-outlook",
        "original_report_url": "",
        "marketlense_article_url": "https://marketlense.example/reports/revenue-outlook",
    }
    return artifacts, evidence_packs, html, provenance


def _seal_claim_package(package: dict) -> dict:
    sealed = deepcopy(package)
    sealed["package_hash"] = ""
    sealed["package_hash"] = sha256_json(sealed)
    return sealed


def _retained_claim_package(
    artifacts: dict,
    evidence_packs: dict,
    html: str,
    *,
    source_id: str = "source:example",
    source_md5: str = "b" * 32,
    configuration_hash: str = "config-current",
    policy_hash: str = "policy-current",
    unsupported: int = 0,
    unresolved: int = 0,
    semantic: bool = False,
) -> dict:
    statuses = (
        ["supported"] + ["unsupported"] * unsupported + ["unresolved"] * unresolved
    )
    results = []
    for index, status in enumerate(statuses, start=1):
        evidence_references = (
            [
                {
                    "schema_version": "1.4",
                    "evidence_id": "F1",
                    "source_pack": "findings",
                    "page": 1,
                    "text_hash": sha256_json("Revenue grew in the measured market."),
                }
            ]
            if semantic and index == 1
            else []
        )
        result = {
            "schema_version": "1.4",
            "candidate": {
                "schema_version": "1.4",
                "claim_id": f"claim:{index}",
                "source_family": "summary",
                "text": f"Retained factual claim {index}.",
                "text_hash": sha256_json(f"Retained factual claim {index}."),
                "kind": "descriptive",
                "factual": True,
                "evidence_references": evidence_references,
                "affected_section": "summary",
                "entity_id": "",
            },
            "checks": [],
            "status": status,
            "deterministic_status": (
                "unresolved"
                if semantic and index == 1
                else "supported"
                if status == "supported"
                else status
            ),
            "reasons": [],
            "protected_facts": None,
            "semantic_outcome": "entailed" if semantic and index == 1 else None,
            "semantic_reason": (
                "entailed from linked evidence" if semantic and index == 1 else ""
            ),
            "semantic_protected_facts": None,
            "semantic_identity": (
                {
                    "schema_version": "1.0",
                    "claim_id": f"claim:{index}",
                    "claim_text_hash": sha256_json(f"Retained factual claim {index}."),
                    "evidence_ids": ["F1"],
                    "evidence_hash": sha256_json(
                        [
                            {
                                "evidence_id": "F1",
                                "source_pack": "findings",
                                "page": 1,
                                "text_hash": sha256_json(
                                    "Revenue grew in the measured market."
                                ),
                            }
                        ]
                    ),
                    "source_identity": source_id,
                    "prompt_family": "report_vs/validate/grounding",
                    "prompt_content_hash": "prompt-content-hash",
                    "execution_identity": "grounding-execution-1",
                    "validator_version": "grounding_validation_output:1.5",
                    "model_provider": "openai",
                    "model_name": "gpt-4.1-mini",
                    "configuration_policy_identity": "grounding-policy-hash",
                    "relevant_input_hash": "grounding-input-hash",
                }
                if semantic and index == 1
                else None
            ),
            "semantic_disagreement": "",
            "semantic_validator_used": semantic and index == 1,
            "semantic_execution_identity": "grounding-execution-1"
            if semantic and index == 1
            else "",
        }
        results.append(result)
    package = {
        "schema_version": "1.4",
        "artifact_hash": sha256_json(artifacts),
        "package_hash": "",
        "results": results,
        "readiness_status": (
            "not_publishable" if unsupported or unresolved else "awaiting_review"
        ),
        "unsupported_factual_count": unsupported,
        "unresolved_factual_count": unresolved,
        "deterministic_pass_count": 0 if semantic else 1,
        "semantic_validation_count": 1 if semantic else 0,
        "semantic_execution_identities": ["grounding-execution-1"] if semantic else [],
        "validation_identity": {
            "schema_version": "1.1",
            "report_id": "report-1",
            "source_id": source_id,
            "source_md5": source_md5,
            "claim_validation_validator_version": "retained_claim_validation:v3",
            "grounding_validator_version": "grounding_validation_output:1.5",
            "configuration_hash": configuration_hash,
            "policy_hash": policy_hash,
        },
        "lineage": {
            "schema_version": "1.1",
            "report_id": "report-1",
            "final_artifact_hash": sha256_json(artifacts),
            "publication_projection_hash": publication_projection_hash(html),
            "evidence_pack_hash": sha256_json(evidence_packs),
            "source_id": source_id,
            "source_md5": source_md5,
            "claim_validation_validator_version": "retained_claim_validation:v3",
            "grounding_validator_version": "grounding_validation_output:1.5",
            "semantic_execution_identities": (
                ["grounding-execution-1"] if semantic else []
            ),
            "semantic_prompt_content_hashes": (
                ["prompt-content-hash"] if semantic else []
            ),
            "semantic_model_identities": ["openai/gpt-4.1-mini"] if semantic else [],
            "configuration_hash": configuration_hash,
            "policy_hash": policy_hash,
        },
    }
    return _seal_claim_package(package)


def _readiness_with_package(
    package: dict,
    *,
    configuration_hash: str = "config-current",
    policy_hash: str = "policy-current",
) -> object:
    artifacts, evidence_packs, html, provenance = _ready_inputs()
    return _evaluate_readiness_for_test(
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence_packs,
        validation_report=ValidationReport(schema_version="1.1", status="pass"),
        final_html=html,
        final_html_path="",
        category_ids=["markets"],
        provenance=provenance,
        retained_claim_package=package,
        retained_claim_required=True,
        source_id="source:example",
        source_md5="b" * 32,
        configuration_hash=configuration_hash,
        policy_hash=policy_hash,
    )


def _retained_grounding_rule(readiness):
    return next(
        item
        for item in readiness.rule_results
        if item.rule_id == "publish_readiness.retained_claim_grounding"
    )


__all__ = [name for name in globals() if not name.startswith("__")]
