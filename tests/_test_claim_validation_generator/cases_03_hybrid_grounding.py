# ruff: noqa: F401,F403,F405
from __future__ import annotations
from ._split_support_cases_03_hybrid_grounding import *  # noqa: F401,F403


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [
        ("entailed", "supported"),
        ("contradicted", "unsupported"),
        ("not_established", "unresolved"),
    ],
)
def test_retained_claim_batch_grounding_preserves_three_semantic_outcomes(
    outcome: str, expected_status: str
) -> None:
    artifacts, evidence = _ambiguous_claim()
    calls = []

    def ground_batch(claims):
        calls.append(claims)
        return [_semantic_result(claim, outcome) for claim in claims]

    package = validate_retained_claims(
        artifacts,
        evidence,
        source_identity="source-1",
        semantic_batch_validator=ground_batch,
    )

    result = package.results[0]
    assert len(calls) == 1
    assert len(calls[0]) == 1
    assert (
        calls[0][0].candidate.text
        == artifacts["summary"]["claim_evidence_map"][0]["claim"]
    )
    assert calls[0][0].evidence_texts == [
        "Wallet use is becoming a common checkout method."
    ]
    assert result.deterministic_status == "unresolved"
    assert result.semantic_outcome == outcome
    assert result.status == expected_status
    assert result.semantic_validator_used is True
    assert result.semantic_identity is not None
    assert result.semantic_identity.evidence_ids == ["f1"]


def test_retained_claim_batch_grounding_collects_unresolved_claims_once() -> None:
    first, evidence = _ambiguous_claim()
    second, _ = _ambiguous_claim(
        "Wallet use is becoming a more common checkout method for shoppers."
    )
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                *first["summary"]["claim_evidence_map"],
                {
                    **second["summary"]["claim_evidence_map"][0],
                    "id": "claim-2",
                },
            ]
        }
    }
    calls = []

    def ground_batch(claims):
        calls.append(claims)
        return [_semantic_result(claim, "not_established") for claim in claims]

    package = validate_retained_claims(
        artifacts, evidence, semantic_batch_validator=ground_batch
    )

    assert len(calls) == 1
    assert len(calls[0]) == 2
    assert {result.status for result in package.results} == {"unresolved"}
    assert {result.candidate.claim_id for result in package.results} == {
        "summary_claim:claim-1",
        "summary_claim:claim-2",
    }


def test_distinct_quotes_sharing_evidence_id_keep_distinct_grounding_identity() -> None:
    evidence = {
        "quote_candidates": {
            "quote_candidates": [
                {
                    "id": "q1",
                    "page": 1,
                    "text": (
                        "The report provides quarterly benchmarks. "
                        "Teams can compare performance over time."
                    ),
                }
            ]
        }
    }
    raw_quotes = [
        {
            "text": "The report provides quarterly benchmarks.",
            "evidence_id": "q1",
            "page": 1,
        },
        {
            "text": "Teams can compare performance over time.",
            "evidence_id": "q1",
            "page": 1,
        },
    ]
    normalized_quotes = normalize_artifact_quotes(raw_quotes)
    assert normalize_artifact_quotes(normalized_quotes) == normalized_quotes
    edited_quote = normalize_artifact_quotes(
        [{**raw_quotes[0], "text": "A corrected quarterly benchmark statement."}]
    )[0]
    assert edited_quote["id"] == normalized_quotes[0]["id"]

    for quotes in (normalized_quotes, raw_quotes):
        calls = []

        def ground(claims, calls=calls):
            calls.append([claim.candidate.claim_id for claim in claims])
            return [_semantic_result(claim, "entailed") for claim in claims]

        package = validate_retained_claims(
            {"quotes_final": quotes},
            evidence,
            semantic_batch_validator=ground,
            source_identity="source:doubleverify",
        )

        claim_ids = [result.candidate.claim_id for result in package.results]
        assert len(set(claim_ids)) == 2
        assert calls == [claim_ids]
        assert package.readiness_status == "awaiting_review"

    assert normalized_quotes[0]["id"] != normalized_quotes[1]["id"]


def test_identical_soft_copy_claims_share_one_semantic_result() -> None:
    text = "Retailers increasingly support wallet checkout."
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    artifacts = {
        "summary": {"tldr": text, "executive_summary": text},
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(
            [
                SoftCopyClaimProvenance(
                    schema_version="1.0",
                    artifact_family="summary",
                    claim_id=f"soft_copy:summary:{text_hash[:16]}",
                    text_hash=text_hash,
                    classification="factual",
                    evidence_ids=("f1",),
                    source_spans=(),
                    producing_prompt_identity={"namespace": "test/summary"},
                    generation_attempt=1,
                    regeneration_attempt=0,
                )
            ]
        ),
    }
    evidence = {
        "findings": {
            "findings": [
                {"id": "f1", "text": "Wallet use is becoming a common checkout method."}
            ]
        }
    }
    calls = []

    def ground_batch(claims):
        calls.append(claims)
        return [_semantic_result(claim, "entailed") for claim in claims]

    package = validate_retained_claims(
        artifacts,
        evidence,
        semantic_batch_validator=ground_batch,
        source_identity="source-1",
    )

    assert len(package.results) == 2
    assert len(calls) == 1
    assert len(calls[0]) == 1
    assert [result.status for result in package.results] == ["supported", "supported"]
    assert all(
        result.semantic_execution_identity == "execution-1"
        for result in package.results
    )


def test_final_package_reuses_one_semantic_result_for_duplicate_public_claims() -> None:
    text = "Retailers increasingly support wallet checkout."
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    artifacts = {
        "summary": {"tldr": text, "executive_summary": text},
        "soft_copy_claim_provenance": soft_copy_claim_provenance_to_payload(
            [
                SoftCopyClaimProvenance(
                    schema_version="1.0",
                    artifact_family="summary",
                    claim_id=f"soft_copy:summary:{text_hash[:16]}",
                    text_hash=text_hash,
                    classification="factual",
                    evidence_ids=("f1",),
                    source_spans=(),
                    producing_prompt_identity={"namespace": "test/summary"},
                    generation_attempt=1,
                    regeneration_attempt=0,
                )
            ]
        ),
    }
    evidence = {
        "findings": {
            "findings": [
                {"id": "f1", "text": "Wallet use is becoming a common checkout method."}
            ]
        }
    }
    semantic_calls = 0

    def ground(claims):
        nonlocal semantic_calls
        semantic_calls += 1
        return [_semantic_result(claim, "entailed") for claim in claims]

    candidate = claim_validation.attach_claim_validation_execution_identity(
        validate_retained_claims(
            artifacts,
            evidence,
            semantic_batch_validator=ground,
            source_identity="source-1",
        ),
        report_id="report-1",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )

    retained, failure_code = claim_validation.materialize_retained_claim_package(
        candidate,
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence,
        final_html=f"<html><body>{text}</body></html>",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )

    assert failure_code == ""
    assert retained is not None
    assert semantic_calls == 1
    assert len(candidate["results"]) == 2
    assert retained["semantic_validation_count"] == 2
    assert retained["unresolved_factual_count"] == 0
    assert [result["status"] for result in retained["results"]] == [
        "supported",
        "supported",
    ]


def test_conflicting_claim_inputs_with_same_id_remain_blocked() -> None:
    text = "Wallet use is becoming a common checkout method across retailers."
    artifacts = {
        "summary": {
            "claim_evidence_map": [
                {"id": "duplicate", "claim": text, "evidence_id": "f1"},
                {"id": "duplicate", "claim": text, "evidence_id": "f2"},
            ]
        }
    }
    evidence = {
        "findings": {
            "findings": [
                {"id": "f1", "text": "Wallet use is becoming a common method."},
                {"id": "f2", "text": "Wallet checkout has grown among retailers."},
            ]
        }
    }
    calls = []

    def ground_batch(claims):
        calls.append(claims)
        return [_semantic_result(claim, "entailed") for claim in claims]

    package = validate_retained_claims(
        artifacts,
        evidence,
        semantic_batch_validator=ground_batch,
        source_identity="source-1",
    )

    assert len(calls) == 1
    assert len(calls[0]) == 2
    assert [result.status for result in package.results] == ["unresolved", "unresolved"]
    assert {result.semantic_disagreement for result in package.results} == {
        "ambiguous_semantic_input_identity"
    }


def test_retained_claim_deterministic_support_and_contradiction_bypass_semantics() -> (
    None
):
    supported_artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "id": "claim-supported",
                    "claim": "Wallet adoption reached 42% in 2026.",
                    "evidence_id": "f1",
                }
            ]
        }
    }
    contradictory_artifacts = {
        "summary": {
            "claim_evidence_map": [
                {
                    "id": "claim-contradicted",
                    "claim": "Wallet adoption reached 43% in 2026.",
                    "evidence_id": "f1",
                }
            ]
        }
    }
    evidence = {
        "findings": {
            "findings": [{"id": "f1", "text": "Wallet adoption reached 42% in 2026."}]
        }
    }
    calls = []

    def ground_batch(claims):
        calls.append(claims)
        raise AssertionError("mechanically decided claims must bypass grounding")

    supported = validate_retained_claims(
        supported_artifacts, evidence, semantic_batch_validator=ground_batch
    )
    contradicted = validate_retained_claims(
        contradictory_artifacts, evidence, semantic_batch_validator=ground_batch
    )

    assert supported.results[0].status == "supported"
    assert supported.results[0].deterministic_status == "supported"
    assert contradicted.results[0].status == "unsupported"
    assert contradicted.results[0].deterministic_status == "unsupported"
    assert calls == []


def test_retained_claim_provenance_failure_bypasses_semantic_grounding() -> None:
    claim = "Wallet use is becoming a common checkout method across retailers."
    calls = []

    def ground_batch(claims):
        calls.append(claims)
        raise AssertionError("invalid provenance must bypass semantic grounding")

    package = validate_retained_claims(
        {"expert_comment": claim},
        {
            "findings": {
                "findings": [{"id": "f1", "text": "Wallet use is becoming common."}]
            }
        },
        semantic_batch_validator=ground_batch,
    )

    assert package.results[0].status == "unsupported"
    assert package.results[0].reasons == ["soft_copy_provenance_missing"]
    assert calls == []


def test_stale_retained_claim_grounding_identity_is_ignored() -> None:
    artifacts, evidence = _ambiguous_claim()

    def ground_batch(claims):
        stale = _semantic_result(claims[0], "entailed")
        return [
            replace(
                stale,
                identity=replace(stale.identity, claim_text_hash="stale-claim-hash"),
            )
        ]

    package = validate_retained_claims(
        artifacts, evidence, semantic_batch_validator=ground_batch
    )

    result = package.results[0]
    assert result.status == "unresolved"
    assert result.semantic_validator_used is False
    assert result.semantic_disagreement == "semantic_result_identity_mismatch"


def test_prior_grounding_validator_version_is_ignored() -> None:
    artifacts, evidence = _ambiguous_claim()

    def ground_batch(claims):
        result = _semantic_result(claims[0], "entailed")
        return [
            replace(
                result,
                identity=replace(
                    result.identity,
                    validator_version="grounding_validation_output:1.4",
                ),
            )
        ]

    package = validate_retained_claims(
        artifacts, evidence, semantic_batch_validator=ground_batch
    )

    result = package.results[0]
    assert result.status == "unresolved"
    assert result.semantic_validator_used is False
    assert result.semantic_disagreement == "semantic_result_identity_mismatch"


def test_missing_semantic_batch_result_is_explicitly_diagnostic() -> None:
    artifacts, evidence = _ambiguous_claim()

    package = validate_retained_claims(
        artifacts,
        evidence,
        semantic_batch_validator=lambda _claims: [],
    )

    result = package.results[0]
    assert result.status == "unresolved"
    assert result.semantic_outcome is None
    assert result.semantic_disagreement == "semantic_result_missing"


def test_final_claim_package_binds_current_artifact_evidence_and_source_lineage():
    artifacts, evidence = _ambiguous_claim(
        "Wallet use is becoming a common checkout method."
    )
    semantic_calls = 0

    def ground(claims):
        nonlocal semantic_calls
        semantic_calls += 1
        return [_semantic_result(claims[0], "entailed")]

    validation_package = validate_retained_claims(
        artifacts,
        evidence,
        semantic_batch_validator=ground,
        source_identity="source-1",
    )
    assert semantic_calls == 1
    package = claim_validation.attach_claim_validation_execution_identity(
        validation_package,
        report_id="report-1",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )
    materialize = getattr(claim_validation, "materialize_retained_claim_package", None)
    assert callable(materialize)

    final_html = "<html><body>Current report.</body></html>"
    retained, failure_code = materialize(
        package,
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence,
        final_html=final_html,
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )

    assert retained is not None
    assert failure_code == ""
    assert semantic_calls == 1
    assert (
        retained["lineage"]["final_artifact_hash"] == validation_package.artifact_hash
    )
    assert retained["lineage"]["publication_projection_hash"]
    assert retained["lineage"]["evidence_pack_hash"]
    assert retained["lineage"]["source_id"] == "source-1"
    assert retained["lineage"]["report_id"] == "report-1"
    assert retained["lineage"]["source_md5"] == "source-md5"
    assert retained["lineage"]["configuration_hash"] == "config-1"
    assert retained["lineage"]["policy_hash"] == "policy-1"
    assert retained["lineage"]["claim_validation_validator_version"]
    assert retained["lineage"]["grounding_validator_version"]
    assert retained["lineage"]["semantic_execution_identities"] == ["execution-1"]
    assert retained["lineage"]["semantic_prompt_content_hashes"] == ["prompt-content-1"]
    assert retained["lineage"]["semantic_model_identities"]


def test_final_claim_package_materialization_rejects_stale_evidence() -> None:
    artifacts, evidence = _ambiguous_claim(
        "Wallet use is becoming a common checkout method."
    )
    package = claim_validation.attach_claim_validation_execution_identity(
        validate_retained_claims(artifacts, evidence, source_identity="source-1"),
        report_id="report-1",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )
    evidence["findings"]["findings"][0]["text"] = "A different source fact."
    materialize = getattr(claim_validation, "materialize_retained_claim_package", None)
    assert callable(materialize)

    retained, failure_code = materialize(
        package,
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence,
        final_html="<html><body>Current report.</body></html>",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )

    assert retained is not None
    assert failure_code == ""
    assert retained["lineage"]["evidence_pack_hash"] == sha256_json(evidence)
    assert retained["lineage"]["semantic_execution_identities"] == []
    assert retained["readiness_status"] == "not_publishable"


def test_final_claim_package_rejects_changed_deterministic_disposition() -> None:
    artifacts, evidence = _ambiguous_claim(
        "Wallet use is becoming a common checkout method."
    )
    package = claim_validation.attach_claim_validation_execution_identity(
        validate_retained_claims(artifacts, evidence, source_identity="source-1"),
        report_id="report-1",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )
    package["results"][0]["status"] = "supported"
    package["results"][0]["deterministic_status"] = "supported"
    package["package_hash"] = ""
    package["package_hash"] = claim_validation.claim_validation_package_hash(package)

    retained, failure_code = claim_validation.materialize_retained_claim_package(
        package,
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence,
        final_html="<html><body>Current report.</body></html>",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )

    assert retained is not None
    assert failure_code == ""
    assert retained["readiness_status"] == "not_publishable"
    assert retained["results"][0]["status"] == "unresolved"


@pytest.mark.parametrize(
    ("identity_field", "stale_value"),
    [
        ("source_id", "source:old"),
        ("source_md5", "source-md5-old"),
        ("configuration_hash", "config-old"),
        ("policy_hash", "policy-old"),
    ],
)
def test_final_claim_package_rejects_stale_validation_identity(
    identity_field: str, stale_value: str
) -> None:
    artifacts, evidence = _ambiguous_claim(
        "Wallet use is becoming a common checkout method."
    )
    package = asdict(
        validate_retained_claims(artifacts, evidence, source_identity="source-1")
    )
    package["validation_identity"] = {
        "schema_version": "1.1",
        "report_id": "report-1",
        "source_id": "source-1",
        "source_md5": "source-md5",
        "claim_validation_validator_version": "retained_claim_validation:v2",
        "grounding_validator_version": CLAIM_GROUNDING_VALIDATOR_VERSION,
        "configuration_hash": "config-1",
        "policy_hash": "policy-1",
    }
    package["validation_identity"][identity_field] = stale_value
    package["package_hash"] = ""
    package["package_hash"] = claim_validation.claim_validation_package_hash(package)

    retained, failure_code = claim_validation.materialize_retained_claim_package(
        package,
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence,
        final_html="<html><body>Current report.</body></html>",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )

    assert retained is not None
    assert failure_code == ""
    assert retained["validation_identity"][identity_field] != stale_value


def test_missing_validation_candidate_materializes_deterministic_final_package():
    artifacts, evidence = _ambiguous_claim(
        "Wallet use is becoming a common checkout method."
    )

    retained, failure_code = claim_validation.materialize_retained_claim_package(
        None,
        report_id="report-1",
        artifacts=artifacts,
        evidence_packs=evidence,
        final_html="<html><body>Current report.</body></html>",
        source_id="source-1",
        source_md5="source-md5",
        configuration_hash="config-1",
        policy_hash="policy-1",
    )

    assert failure_code == ""
    assert retained is not None
    assert retained["lineage"]["report_id"] == "report-1"
    assert retained["lineage"]["final_artifact_hash"] == sha256_json(artifacts)
    assert retained["semantic_validation_count"] == 0
    assert retained["unresolved_factual_count"] == 1
    assert retained["readiness_status"] == "not_publishable"


from .cases_01_split_long_module import *  # noqa: F401,F403
