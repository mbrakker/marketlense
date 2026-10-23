from __future__ import annotations

import hashlib
import json
import re
import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from copy import deepcopy
from dataclasses import asdict, replace
from typing import Any, Callable, List, Mapping, Sequence

from src.contracts.claim_validation import (
    CLAIM_GROUNDING_VALIDATOR_VERSION,
    ClaimSemanticGroundingResult,
    ClaimSemanticInput,
    ClaimSemanticValidationIdentity,
    ClaimValidationPackage,
)
from src.contracts.pdf_text import PdfTextPage
from src.contracts.prompt_family_materialization import (
    PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
    PromptFamilyMaterializationRequest,
    PromptFamilyReuseRequest,
)
from src.contracts.protected_facts import ProtectedFactComparison
from src.contracts.schema_validation import SchemaValidateRequest
from src.contracts.soft_copy_claim_provenance import (
    soft_copy_claim_provenance_from_payload,
    soft_copy_material_sentences,
)
from src.contracts.structured_output import StructuredOutputExecutionRequest
from src.contracts.validation import ValidationIssue, ValidationRequest
from src.generators.artifact_normalization import artifact_evidence_span_index
from src.generators.claim_validation_generator import (
    apply_retained_claim_semantic_results,
    metric_claim_text,
    retained_claim_semantic_evidence_hash,
    retained_claim_semantic_inputs,
    reuse_retained_claim_semantic_results,
    validate_retained_claims,
)
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.generators.report_title_resolution_generator import (
    is_generic_report_title,
    resolve_report_title,
    source_backed_title,
)
from src.generators.structured_output_execution import (
    invoke_structured_output_model,
    recovery_prompt_bundle,
)
from src.services.prompt_family_materialization_service import (
    materialize_prompt_family,
    read_reusable_prompt_family,
)
from src.services.schema_validator_service import (
    provider_output_schema,
    validate_schema,
)
from src.services.structured_output_service import execute_structured_output
from src.utils.cache_utils import sha256_json
from src.utils.editorial_identity import insight_entity_id
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event
from src.utils.quantity import extract_quantities
from src.utils.text_normalization import normalize_for_lookup, normalize_text

from .evidence import build_evidence_windows, sanitize_citation_tokens
from .models import EvidenceWindow, ValidationRuntime
from .quantities import collect_quantities_from_texts
from .shared import (
    GROUNDING_HARD_FAILURES,
    LOGGER_NAME,
    METRIC_ATTRIBUTION_RE,
    ensure_dict,
    grounding_retrieval_mode,
    issue,
    logger,
    s,
    section_policy,
    section_root,
)
from .verified_facts import (
    VERIFIED_FACT_EVIDENCE_PREFIX,
    canonical_evidence_map,
    canonical_verified_evidence_packs,
    fact_for_evidence_id,
    validated_verified_facts,
    verified_facts_mode,
)

RULE_ID = "grounding"
GROUNDING_FAMILY_SCHEMA_VERSION = "1.4"
GROUNDING_OUTPUT_SCHEMA_IDENTITY = "grounding_validation_output_v3"
GROUNDING_VALIDATOR_VERSION = CLAIM_GROUNDING_VALIDATOR_VERSION
GROUNDING_MAX_CLAIMS_PER_CALL = 4
GROUNDING_MAX_PUBLIC_ITEMS_PER_CALL = 8


def grounding_authority_policy(verified_mode: bool) -> str:
    """Describe the sole factual authority for the grounding prompt."""

    if verified_mode:
        return (
            "VERIFIED mode: use only attached canonical verified facts as factual "
            "authority; do not retrieve or reinterpret the original PDF."
        )
    return (
        "LEGACY mode: use attached evidence and corroborate chart/table associations "
        "with file_search and the original visual when supplied evidence may contain "
        "a tuple error. Bind chart/table values by visible row, callout, connector, "
        "or legend "
        "key; OCR order alone is not the tuple. Confirm label reversals visually; "
        "unreadable or ambiguous layouts are not_established."
    )


def _grounding_batches(
    audit_payload: dict,
    semantic_inputs: Sequence[ClaimSemanticInput],
) -> list[tuple[dict, list[ClaimSemanticInput]]]:
    """Split the canonical public inventories under the provider output ceiling."""

    claim_entries = list(audit_payload.get("retained_claims_to_ground") or [])
    public_items = list(audit_payload.get("public_factual_items") or [])
    claim_pairs = list(zip(semantic_inputs, claim_entries, strict=True))
    claim_groups = [
        claim_pairs[index : index + GROUNDING_MAX_CLAIMS_PER_CALL]
        for index in range(0, len(claim_pairs), GROUNDING_MAX_CLAIMS_PER_CALL)
    ] or [[]]
    public_groups = [
        public_items[index : index + GROUNDING_MAX_PUBLIC_ITEMS_PER_CALL]
        for index in range(0, len(public_items), GROUNDING_MAX_PUBLIC_ITEMS_PER_CALL)
    ] or [[]]
    batch_count = max(len(claim_groups), len(public_groups))
    batches: list[tuple[dict, list[ClaimSemanticInput]]] = []
    canonical_verified_facts = audit_payload.get("canonical_verified_facts")
    for index in range(batch_count):
        claim_group = claim_groups[index] if index < len(claim_groups) else []
        public_group = public_groups[index] if index < len(public_groups) else []
        batch_payload: dict[str, Any] = {
            "public_factual_items": public_group,
            "retained_claims_to_ground": [
                entry for _semantic_input, entry in claim_group
            ],
        }
        if isinstance(canonical_verified_facts, dict):
            evidence_ids = [
                s(evidence_id)
                for item in public_group
                if isinstance(item, dict)
                for evidence_id in item.get("evidence_ids", [])
                if s(evidence_id).startswith(VERIFIED_FACT_EVIDENCE_PREFIX)
            ]
            evidence_ids.extend(
                s(evidence_id)
                for _semantic_input, entry in claim_group
                for evidence_id in entry.get("evidence_ids", [])
                if s(evidence_id).startswith(VERIFIED_FACT_EVIDENCE_PREFIX)
            )
            fact_ids = dict.fromkeys(
                evidence_id.removeprefix(VERIFIED_FACT_EVIDENCE_PREFIX)
                for evidence_id in evidence_ids
            )
            batch_payload["canonical_verified_facts"] = {
                fact_id: canonical_verified_facts[fact_id]
                for fact_id in fact_ids
                if fact_id in canonical_verified_facts
            }
        batches.append(
            (
                batch_payload,
                [semantic_input for semantic_input, _entry in claim_group],
            )
        )
    return batches


def _claim_prompt_content_hashes(
    grounding_batches: Sequence[tuple[dict, list[ClaimSemanticInput]]],
    prompt_bundles: Sequence[Any],
) -> dict[str, str]:
    hashes_by_claim_id: dict[str, list[str]] = {}
    for (_batch_payload, semantic_inputs), prompt_bundle in zip(
        grounding_batches, prompt_bundles, strict=True
    ):
        for semantic_input in semantic_inputs:
            hashes_by_claim_id.setdefault(semantic_input.candidate.claim_id, []).append(
                str(prompt_bundle.prompt_content_hash or "")
            )
    return {
        claim_id: hashes[0] if len(hashes) == 1 else ""
        for claim_id, hashes in hashes_by_claim_id.items()
    }


def run_grounding_rule(runtime: ValidationRuntime) -> List[ValidationIssue]:
    verified_mode = bool(getattr(runtime.prepared, "verified_facts_mode", False))
    evidence_packs = (
        runtime.prepared.authority_evidence_packs
        if verified_mode
        else runtime.request.evidence_packs
    )
    request = (
        replace(
            runtime.request,
            evidence_packs=evidence_packs,
            source_text="",
            source_pages=[],
        )
        if verified_mode
        else runtime.request
    )
    package = validate_retained_claims(
        request.artifacts,
        evidence_packs,
        source_identity=runtime.source_id,
        verified_facts_only=verified_mode,
    )
    semantic_inputs = retained_claim_semantic_inputs(
        package,
        evidence_packs,
        source_identity=runtime.source_id,
        source_pages=request.source_pages,
    )
    runtime.retained_claim_validation = package

    def retain_claim_results(updated: ClaimValidationPackage) -> None:
        runtime.retained_claim_validation = updated

    issues = run_grounding_check(
        request=request,
        settings=runtime.settings,
        grounding_use_vector_store=runtime.prepared.grounding_use_vector_store,
        evidence_texts=runtime.prepared.evidence_texts,
        evidence_windows=runtime.prepared.evidence_windows,
        prompt_client=runtime.prompt_client,
        openai_client=runtime.openai_client,
        ctx=runtime.ctx,
        source_id=runtime.source_id,
        source_md5=str(getattr(runtime, "source_md5", "") or ""),
        vector_store_content_hash=runtime.vector_store_content_hash,
        retained_claim_package=package,
        retained_claim_inputs=semantic_inputs,
        retained_claim_validation_sink=retain_claim_results,
    )
    issues.extend(
        _deterministic_claim_validation_issues(
            runtime.retained_claim_validation or package,
            verified_mode=verified_mode,
        )
    )
    return issues


def _deterministic_claim_validation_issues(
    package: ClaimValidationPackage,
    *,
    verified_mode: bool = False,
) -> List[ValidationIssue]:
    """Expose deterministic retained-claim failures to candidate validation."""
    issues: List[ValidationIssue] = []
    verified_structural_checks = {
        "evidence_reference_completeness",
        "soft_copy_provenance_integrity",
    }
    for result in package.results:
        candidate = result.candidate
        if not candidate.factual or result.deterministic_status != "unsupported":
            continue
        for check in result.checks:
            if check.status != "failed":
                continue
            if verified_mode and check.name not in verified_structural_checks:
                continue
            rule_id = f"retained_claim.{check.name}"
            issues.append(
                ValidationIssue(
                    schema_version="1.0",
                    message=(
                        f"[{rule_id}] Retained factual claim failed deterministic "
                        f"validation: {check.reason}."
                    ),
                    severity="error",
                    affected_section=(
                        candidate.affected_section or candidate.source_family
                    ),
                    rule_id=rule_id,
                    violation_type="unsupported_factual_claim",
                    entity_id=candidate.claim_id,
                    evidence_ids=list(
                        dict.fromkeys(
                            reference.evidence_id
                            for reference in candidate.evidence_references
                            if reference.evidence_id
                        )
                    ),
                )
            )
    return issues


def _exactly_evidenced_claims(
    semantic_inputs: Sequence[ClaimSemanticInput],
) -> set[str]:
    """Return factual claims explicitly reproduced by their linked evidence.

    The grounding model is still required for paraphrases and attribution, but
    an exact retained sentence in an authoritative evidence span is already a
    deterministic entailment. Treating it as unresolved lets OCR/layout noise
    override the canonical statement and causes unnecessary regeneration.
    """

    supported: set[str] = set()
    for semantic_input in semantic_inputs:
        claim = normalize_for_lookup(semantic_input.candidate.text)
        if not claim or not semantic_input.evidence_texts:
            continue
        if any(
            claim in normalize_for_lookup(evidence)
            for evidence in semantic_input.evidence_texts
        ):
            supported.add(claim)
    return supported


def run_grounding_check(
    request: ValidationRequest,
    settings,
    grounding_use_vector_store: bool,
    evidence_texts: Sequence[str],
    evidence_windows: Sequence[EvidenceWindow],
    prompt_client,
    openai_client,
    ctx,
    source_id: str = "",
    source_md5: str = "",
    vector_store_content_hash: str = "",
    prompt_family_reuse_reader=read_reusable_prompt_family,
    prompt_family_materializer=materialize_prompt_family,
    retained_claim_package: ClaimValidationPackage | None = None,
    retained_claim_inputs: list[ClaimSemanticInput] | None = None,
    retained_claim_validation_sink: Callable[[ClaimValidationPackage], None]
    | None = None,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    prompt_ctx = child_context(ctx, task_id=f"{ctx.task_id}:grounding")
    prompt_namespace = "report_vs/validate/grounding"
    artifacts = request.artifacts if isinstance(request.artifacts, dict) else {}
    verified_mode = verified_facts_mode(artifacts, request.validation_mode)
    evidence_packs = request.evidence_packs
    verified_facts: dict[str, dict[str, Any]] = {}
    if verified_mode:
        grounding_use_vector_store = False
        verified_facts = validated_verified_facts(
            artifacts,
            evidence_packs,
            expected_source_identity=str(request.source_id or ""),
        )
        evidence_packs = canonical_verified_evidence_packs(verified_facts)
        request = replace(
            request,
            evidence_packs=evidence_packs,
            source_text="",
            source_pages=[],
        )
        evidence_texts = tuple(canonical_evidence_map(verified_facts).values())
        evidence_windows = build_evidence_windows(evidence_texts)
    if retained_claim_package is None:
        retained_claim_package = validate_retained_claims(
            artifacts,
            evidence_packs,
            source_identity=source_id or request.source_id,
            verified_facts_only=verified_mode,
        )
    if retained_claim_inputs is None:
        retained_claim_inputs = retained_claim_semantic_inputs(
            retained_claim_package,
            evidence_packs,
            source_identity=source_id or request.source_id,
        )
    if verified_mode:
        _validate_verified_semantic_inputs(
            retained_claim_package,
            retained_claim_inputs,
            verified_facts,
            evidence_packs,
            source_identity=(source_id or request.source_id),
        )
    audit_payload = grounding_payload(
        request,
        artifacts,
        retained_claim_inputs=retained_claim_inputs,
    )
    public_item_ids = _public_item_ids(audit_payload.get("public_factual_items"))
    retained_item_ids = _retained_claim_grounding_item_ids(
        retained_claim_inputs,
        set(public_item_ids.values()),
    )
    grounding_batches = _grounding_batches(audit_payload, retained_claim_inputs)
    authority_policy = grounding_authority_policy(verified_mode)
    batch_prompt_vars = [
        {
            "report_json": json.dumps(batch_payload, ensure_ascii=False),
            "evidence_json": json.dumps(list(evidence_texts), ensure_ascii=False),
            "authority_policy": authority_policy,
        }
        for batch_payload, _batch_semantic_inputs in grounding_batches
    ]

    def prepare_batch_bundle(variables: dict[str, str]):
        return prepare_prompt_bundle(
            namespace=prompt_namespace,
            settings=settings,
            ctx=prompt_ctx,
            prompt_client=prompt_client,
            system_variables=variables,
            user_variables={
                key: value
                for key, value in variables.items()
                if key != "authority_policy"
            },
        )

    prompt_bundles = [
        prepare_batch_bundle(variables) for variables in batch_prompt_vars
    ]
    prompt_bundle = prompt_bundles[0]
    prompt_content_hash_by_claim_id = _claim_prompt_content_hashes(
        grounding_batches, prompt_bundles
    )
    full_grounding_batch_count = len(grounding_batches)
    configuration_policy_hash = sha256_json(
        {
            "execution_policy_hash": prompt_bundle.execution_policy.policy_hash,
            "execution_policy": asdict(prompt_bundle.execution_policy.policy),
            "routing_policy": asdict(prompt_bundle.routing_decision),
        }
    )
    retrieval_identity = sha256_json(
        {
            "use_vector_store": grounding_use_vector_store,
            "vector_store_id": request.vector_store_id or ""
            if grounding_use_vector_store
            else "",
            "vector_store_content_hash": vector_store_content_hash
            if grounding_use_vector_store
            else "",
            "retrieval_mode": grounding_retrieval_mode(grounding_use_vector_store),
        }
    )
    if retained_claim_package is None:
        retained_claim_package = validate_retained_claims(
            artifacts,
            evidence_packs,
            source_identity=source_id or request.source_id,
            verified_facts_only=verified_mode,
        )
    retained_claim_package, retained_claim_inputs, reuse_telemetry = (
        reuse_retained_claim_semantic_results(
            retained_claim_package,
            retained_claim_inputs,
            request.prior_claim_validation_package,
            expected_prior_artifact_hash=request.prior_claim_validation_artifact_hash,
            report_id=str(request.report_id),
            source_id=source_id or request.source_id,
            source_md5=source_md5,
            configuration_hash=str(ctx.configuration_hash or ""),
            policy_hash=str(ctx.policy_hash or ""),
            prompt_family=prompt_namespace,
            prompt_execution_identity=(
                prompt_bundle.execution_identity.execution_identity
            ),
            model_provider=str(prompt_bundle.execution_policy.policy.provider),
            model_name=prompt_bundle.resolved_model,
            configuration_policy_identity=configuration_policy_hash,
            retrieval_identity=retrieval_identity,
            prompt_content_hash_by_claim_id=prompt_content_hash_by_claim_id,
        )
    )

    def reuse_counter(name: str) -> int:
        value = reuse_telemetry.get(name, 0)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    reused_validation_results = reuse_counter("reused_validation_results")
    if reused_validation_results:
        audit_payload = grounding_payload(
            request,
            artifacts,
            retained_claim_inputs=retained_claim_inputs,
        )
        public_item_ids = _public_item_ids(audit_payload.get("public_factual_items"))
        retained_item_ids = _retained_claim_grounding_item_ids(
            retained_claim_inputs,
            set(public_item_ids.values()),
        )
        grounding_batches = _grounding_batches(audit_payload, retained_claim_inputs)
        batch_prompt_vars = [
            {
                "report_json": json.dumps(batch_payload, ensure_ascii=False),
                "evidence_json": json.dumps(list(evidence_texts), ensure_ascii=False),
                "authority_policy": authority_policy,
            }
            for batch_payload, _batch_semantic_inputs in grounding_batches
        ]
        prompt_bundles = [
            prepare_batch_bundle(variables) for variables in batch_prompt_vars
        ]
        prompt_bundle = prompt_bundles[0]
        prompt_content_hash_by_claim_id = _claim_prompt_content_hashes(
            grounding_batches, prompt_bundles
        )
    reuse_telemetry["grounding_calls_avoided"] = max(
        0, full_grounding_batch_count - len(grounding_batches)
    )
    logger.info(
        log_event(
            prompt_ctx,
            role="generator",
            event="prompt_selected",
            module=LOGGER_NAME,
            fields={
                "namespace": prompt_namespace,
                "system_path": prompt_bundle.prompt_set.system.path,
                "system_sha256": prompt_bundle.prompt_set.system.sha256,
                "user_path": prompt_bundle.prompt_set.user.path,
                "user_sha256": prompt_bundle.prompt_set.user.sha256,
            },
        )
    )
    logger.info(
        log_event(
            prompt_ctx,
            role="generator",
            event="prompt_rendered_identity",
            module=LOGGER_NAME,
            fields={
                "prompt_content_hash": prompt_bundle.prompt_content_hash,
                "execution_identity": (
                    prompt_bundle.execution_identity.execution_identity
                ),
            },
        )
    )
    logger.info(
        log_event(
            prompt_ctx,
            role="generator",
            event="model_resolved",
            module=LOGGER_NAME,
            fields={
                "namespace": prompt_namespace,
                "resolved_model": prompt_bundle.resolved_model,
                "default_model": settings.openai_model,
            },
        )
    )
    logger.info(
        log_event(
            prompt_ctx,
            role="generator",
            event="grounding_request_config",
            module=LOGGER_NAME,
            fields={
                "model": prompt_bundle.resolved_model,
                "temperature": prompt_bundle.effective_temperature,
                "vector_store_id_present": bool(request.vector_store_id),
                "setting_enabled": bool(
                    getattr(settings, "validation_grounding_use_vector_store", False)
                ),
                "grounding_use_vector_store": grounding_use_vector_store,
                "retrieval_mode": grounding_retrieval_mode(grounding_use_vector_store),
                "seed": prompt_bundle.effective_seed,
                "execution_policy_hash": prompt_bundle.execution_policy.policy_hash,
            },
        )
    )
    logger.info(
        log_event(
            prompt_ctx,
            role="generator",
            event="grounding_batches_planned",
            module=LOGGER_NAME,
            fields={
                "batch_count": len(grounding_batches),
                "retained_claim_count": len(retained_claim_inputs),
                "public_item_count": len(public_item_ids),
                "max_claims_per_batch": GROUNDING_MAX_CLAIMS_PER_CALL,
                "max_public_items_per_batch": GROUNDING_MAX_PUBLIC_ITEMS_PER_CALL,
                "configured_global_max_in_flight": int(
                    getattr(settings, "validation_grounding_global_max_in_flight", 1)
                ),
                "configured_global_min_interval_ms": int(
                    getattr(settings, "validation_grounding_global_min_interval_ms", 0)
                ),
            },
        )
    )
    logger.info(
        log_event(
            prompt_ctx,
            role="generator",
            event="validation_claim_reuse_decided",
            module=LOGGER_NAME,
            fields={
                "total_candidate_claims": reuse_counter("total_candidate_claims"),
                "reused_validation_results": reused_validation_results,
                "newly_validated_claims": reuse_counter("newly_validated_claims"),
                "grounding_calls_avoided": reuse_counter("grounding_calls_avoided"),
                "semantic_validation_calls_avoided": reuse_counter(
                    "semantic_validation_calls_avoided"
                ),
                "reuse_fallback_reason_counts": reuse_telemetry.get(
                    "reuse_fallback_reason_counts", {}
                ),
            },
        )
    )
    vector_provenance_verified = not grounding_use_vector_store or bool(
        str(vector_store_content_hash or "").strip()
    )
    relevant_input_hash = sha256_json(
        {
            "grounding_payload": audit_payload,
            "evidence_texts": list(evidence_texts),
            "vector_store_id": request.vector_store_id or "",
            "vector_store_content_hash": vector_store_content_hash,
            "retrieval_mode": grounding_retrieval_mode(grounding_use_vector_store),
            "authority_mode": "verified_facts" if verified_mode else "legacy",
            "authority_policy": authority_policy,
            "batch_policy": {
                "schema_version": "1.0",
                "max_claims_per_call": GROUNDING_MAX_CLAIMS_PER_CALL,
                "max_public_items_per_call": GROUNDING_MAX_PUBLIC_ITEMS_PER_CALL,
            },
        }
    )
    try:
        output_schema = provider_output_schema("grounding_validation_output")
        _validate_semantic_input_identities(retained_claim_inputs)

        def validate_grounding_payload(
            payload: object,
            expected_inputs: Sequence[ClaimSemanticInput] | None = None,
            expected_public_items: Sequence[Mapping[str, Any]] | None = None,
            *,
            ctx=prompt_ctx,
        ) -> None:
            public_items_for_validation = (
                (
                    audit_payload.get("public_factual_items", [])
                    if expected_public_items is None
                    else expected_public_items
                )
                if verified_mode
                else ()
            )
            validate_schema(
                SchemaValidateRequest(
                    schema_version="1.0",
                    payload=payload,
                    schema_name="grounding_validation_output",
                ),
                ctx,
            )
            _validate_grounding_check_coverage(
                payload,
                retained_claim_inputs if expected_inputs is None else expected_inputs,
                retained_item_ids,
                tuple(
                    public_item_ids.values()
                    if not verified_mode
                    else (
                        s(item.get("item_id"))
                        for item in public_items_for_validation
                        if isinstance(item, dict)
                    )
                ),
                expected_public_items=public_items_for_validation,
                require_public_coverage=verified_mode,
            )

        reused_payload = None
        if source_id and vector_provenance_verified:
            reuse = prompt_family_reuse_reader(
                PromptFamilyReuseRequest(
                    schema_version=PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
                    db_path=settings.reports_db,
                    output_dir=settings.output_dir,
                    report_id=str(request.report_id),
                    report_slug=request.report_name or str(request.report_id),
                    source_id=source_id,
                    family_id=prompt_namespace,
                    family_schema_version=GROUNDING_FAMILY_SCHEMA_VERSION,
                    processing_version="validation_rule_v4",
                    prompt_content_hash=prompt_bundle.prompt_content_hash,
                    execution_identity=prompt_bundle.execution_identity.execution_identity,
                    model_provider=str(prompt_bundle.execution_policy.policy.provider),
                    model_name=prompt_bundle.resolved_model,
                    model_policy_namespace="report_vs",
                    routing_policy_version=prompt_bundle.execution_policy.policy_hash,
                    validator_version=GROUNDING_VALIDATOR_VERSION,
                    relevant_input_hash=relevant_input_hash,
                    configuration_policy_hash=configuration_policy_hash,
                ),
                prompt_ctx,
            )
            if reuse.reusable:
                candidate_payload = dict(reuse.output_payload)
                try:
                    validate_grounding_payload(candidate_payload)
                except AppError as exc:
                    logger.info(
                        log_event(
                            prompt_ctx,
                            role="generator",
                            event="grounding_prompt_family_reuse_rejected",
                            module=LOGGER_NAME,
                            fields={"family_id": prompt_namespace, "reason": exc.code},
                        )
                    )
                else:
                    reused_payload = candidate_payload
                    logger.info(
                        log_event(
                            prompt_ctx,
                            role="generator",
                            event="grounding_prompt_family_reused",
                            module=LOGGER_NAME,
                            fields={
                                "family_id": prompt_namespace,
                                "reason": reuse.reason,
                            },
                        )
                    )
        recovery_attempted = False
        if reused_payload is None:
            response_payload: dict[str, Any] = {"unsupported": [], "checks": []}
            batch_jobs = [
                (batch_index, batch_spec, batch_vars, batch_bundle)
                for batch_index, (batch_spec, batch_vars, batch_bundle) in enumerate(
                    zip(
                        grounding_batches,
                        batch_prompt_vars,
                        prompt_bundles,
                        strict=True,
                    ),
                    start=1,
                )
            ]
            configured_limit = max(
                1,
                int(
                    getattr(
                        settings,
                        "validation_grounding_global_max_in_flight",
                        1,
                    )
                ),
            )
            max_workers = min(configured_limit, len(batch_jobs))
            batch_failure_event = threading.Event()
            batch_failure_lock = threading.Lock()

            def _execute_batch(
                batch_index: int,
                batch_spec: tuple[dict, list[ClaimSemanticInput]],
                batch_vars: dict[str, str],
                batch_bundle,
            ) -> tuple[int, Any, bool]:
                _batch_payload, batch_semantic_inputs = batch_spec
                batch_task_id = (
                    f"{prompt_ctx.task_id}:batch:{batch_index:02d}:grounding"
                )
                batch_ctx = child_context(
                    prompt_ctx,
                    task_id=batch_task_id,
                )
                batch_recovery_attempted = False

                def call_model(
                    mode: str,
                    original_response: str,
                    schema_errors: str,
                    *,
                    variables=batch_vars,
                    base_bundle=batch_bundle,
                    call_index=batch_index,
                ):
                    nonlocal batch_recovery_attempted
                    if mode != "primary":
                        batch_recovery_attempted = True
                    bundle = base_bundle
                    if mode != "primary":
                        bundle = recovery_prompt_bundle(
                            mode=mode,
                            artifact_family="validation_grounding",
                            schema_errors=schema_errors,
                            original_response=original_response,
                            output_schema=output_schema,
                            source_evidence={
                                "report_json": variables["report_json"],
                                "evidence_json": variables["evidence_json"],
                                "authority_policy": variables["authority_policy"],
                            },
                            settings=settings,
                            ctx=batch_ctx,
                            prompt_client=prompt_client,
                            vector_store_id=(
                                request.vector_store_id
                                if grounding_use_vector_store
                                else None
                            ),
                        )
                    return invoke_structured_output_model(
                        openai_client=openai_client,
                        prompt_bundle=bundle,
                        settings=settings,
                        ctx=batch_ctx,
                        vector_store_id=(
                            request.vector_store_id
                            if grounding_use_vector_store
                            else None
                        ),
                        report_id=str(request.report_id),
                        artifact_family="validation_grounding",
                        stage=(f"validation_grounding_batch_{call_index:02d}_{mode}"),
                        publisher_name=request.publisher_name,
                        report_name=request.report_name,
                        source_url=request.source_url,
                        output_schema=output_schema,
                        output_schema_identity=GROUNDING_OUTPUT_SCHEMA_IDENTITY,
                        repair_attempt={
                            "primary": 0,
                            "model_repair": 1,
                            "regeneration": 2,
                        }[mode],
                    )

                def validate_recovery_payload(payload: Any) -> None:
                    validate_grounding_payload(
                        payload,
                        batch_semantic_inputs,
                        batch_spec[0].get("public_factual_items") or [],
                        ctx=batch_ctx,
                    )

                recovery = execute_structured_output(
                    StructuredOutputExecutionRequest(
                        schema_version="1.0",
                        report_id=str(request.report_id),
                        artifact_family="validation_grounding",
                        schema_name="grounding_validation_output",
                        model=batch_bundle.resolved_model,
                        workflow="report_analysis",
                        prompt_family=batch_bundle.routing_decision.namespace,
                        terminal_failure_code="validation_grounding_invalid_json",
                    ),
                    batch_ctx,
                    call_model=call_model,
                    normalize_payload=lambda payload: (
                        dict(payload) if isinstance(payload, dict) else payload
                    ),
                    validate_payload=validate_recovery_payload,
                    is_substantive=lambda payload: (
                        isinstance(payload, dict) and "unsupported" in payload
                    ),
                    model_pricing=settings.model_pricing,
                )

                return batch_index, recovery.payload, batch_recovery_attempted

            def execute_batch(
                batch_index: int,
                batch_spec: tuple[dict, list[ClaimSemanticInput]],
                batch_vars: dict[str, str],
                batch_bundle,
            ) -> tuple[int, Any, bool]:
                try:
                    return _execute_batch(
                        batch_index,
                        batch_spec,
                        batch_vars,
                        batch_bundle,
                    )
                except Exception:
                    with batch_failure_lock:
                        batch_failure_event.set()
                    raise

            batch_results: dict[int, tuple[Any, bool]] = {}
            batch_failures: list[tuple[int, Exception]] = []
            next_batch = 0
            pending: dict[Future, int] = {}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                while next_batch < max_workers:
                    with batch_failure_lock:
                        if batch_failure_event.is_set():
                            break
                        batch_index, batch_spec, batch_vars, batch_bundle = batch_jobs[
                            next_batch
                        ]
                        pending[
                            executor.submit(
                                execute_batch,
                                batch_index,
                                batch_spec,
                                batch_vars,
                                batch_bundle,
                            )
                        ] = batch_index
                        next_batch += 1

                while pending:
                    completed, _not_completed = wait(
                        pending, return_when=FIRST_COMPLETED
                    )
                    for future in sorted(completed, key=pending.__getitem__):
                        batch_index = pending.pop(future)
                        try:
                            _index, payload, batch_recovery_attempted = future.result()
                        except Exception as exc:
                            batch_failures.append((batch_index, exc))
                        else:
                            batch_results[batch_index] = (
                                payload,
                                batch_recovery_attempted,
                            )

                    if batch_failures:
                        for future, batch_index in sorted(
                            pending.items(), key=lambda item: item[1]
                        ):
                            if future.cancel():
                                continue
                            try:
                                future.result()
                            except Exception as exc:
                                batch_failures.append((batch_index, exc))
                        pending.clear()
                        _failure_index, failure = min(
                            batch_failures, key=lambda item: item[0]
                        )
                        raise failure

                    while next_batch < len(batch_jobs) and len(pending) < max_workers:
                        with batch_failure_lock:
                            if batch_failure_event.is_set():
                                break
                            batch_index, batch_spec, batch_vars, batch_bundle = (
                                batch_jobs[next_batch]
                            )
                            pending[
                                executor.submit(
                                    execute_batch,
                                    batch_index,
                                    batch_spec,
                                    batch_vars,
                                    batch_bundle,
                                )
                            ] = batch_index
                            next_batch += 1

            for batch_index in sorted(batch_results):
                payload, batch_recovery_attempted = batch_results[batch_index]
                recovery_attempted = recovery_attempted or batch_recovery_attempted
                response_payload["unsupported"].extend(payload.get("unsupported") or [])
                response_payload["checks"].extend(payload.get("checks") or [])
            validate_grounding_payload(response_payload)
        else:
            response_payload = reused_payload
        unsupported: list[Any] = response_payload.get("unsupported") or []
        checks: list[Any] = response_payload.get("checks") or []
        if (
            reused_payload is None
            and source_id
            and vector_provenance_verified
            and not recovery_attempted
        ):
            prompt_family_materializer(
                PromptFamilyMaterializationRequest(
                    schema_version=PROMPT_FAMILY_MATERIALIZATION_SCHEMA_VERSION,
                    db_path=settings.reports_db,
                    output_dir=settings.output_dir,
                    report_id=str(request.report_id),
                    report_slug=request.report_name or str(request.report_id),
                    source_id=source_id,
                    family_id=prompt_namespace,
                    family_schema_version=GROUNDING_FAMILY_SCHEMA_VERSION,
                    processing_version="validation_rule_v4",
                    output_payload=response_payload,
                    system_prompt_hash=prompt_bundle.prompt_set.system.sha256,
                    user_prompt_hash=prompt_bundle.prompt_set.user.sha256,
                    prompt_content_hash=prompt_bundle.prompt_content_hash,
                    prompt_dependency_manifest=asdict(
                        prompt_bundle.dependency_manifest
                    ),
                    execution_identity=prompt_bundle.execution_identity.execution_identity,
                    execution_identity_manifest=asdict(
                        prompt_bundle.execution_identity
                    ),
                    prompt_policy_version=prompt_bundle.prompt_content_hash,
                    model_name=prompt_bundle.resolved_model,
                    model_provider=str(prompt_bundle.execution_policy.policy.provider),
                    model_policy_namespace="report_vs",
                    routing_policy_version=prompt_bundle.execution_policy.policy_hash,
                    relevant_input_hash=relevant_input_hash,
                    configuration_policy_hash=configuration_policy_hash,
                    validator_version=GROUNDING_VALIDATOR_VERSION,
                    validation_status="pass",
                ),
                prompt_ctx,
            )
        semantic_results = _retained_claim_semantic_results(
            checks,
            retained_claim_inputs,
            retained_item_ids=retained_item_ids,
            source_identity=source_id or request.source_id,
            prompt_family=prompt_namespace,
            execution_identity=prompt_bundle.execution_identity.execution_identity,
            validator_version=GROUNDING_VALIDATOR_VERSION,
            model_provider=str(prompt_bundle.execution_policy.policy.provider),
            model_name=prompt_bundle.resolved_model,
            configuration_policy_identity=configuration_policy_hash,
            relevant_input_hash=relevant_input_hash,
            retrieval_identity=retrieval_identity,
            prompt_content_hash_by_claim_id=prompt_content_hash_by_claim_id,
        )
        updated_claim_package = apply_retained_claim_semantic_results(
            retained_claim_package,
            retained_claim_inputs,
            semantic_results,
        )
        if retained_claim_validation_sink is not None:
            retained_claim_validation_sink(updated_claim_package)
        logger.info(
            log_event(
                prompt_ctx,
                role="generator",
                event="grounding_response",
                module=LOGGER_NAME,
                fields={
                    "has_json": True,
                    "unsupported_count": len(unsupported)
                    if isinstance(unsupported, list)
                    else 0,
                },
            )
        )
        failed_check_keys = set()
        exactly_evidenced_claims = _exactly_evidenced_claims(retained_claim_inputs)
        if isinstance(checks, list):
            for entry in checks:
                if not isinstance(entry, dict):
                    continue
                comparison = ProtectedFactComparison.from_payload(
                    entry.get("protected_facts"),
                    proposition_status=s(entry.get("proposition_status")),
                )
                outcome = normalize_entailment_outcome(
                    s(entry.get("entailment_outcome"))
                )
                incompatible_dimensions = comparison.incompatible_dimensions
                if (
                    outcome == "entailed"
                    and comparison.proposition_status == "compatible"
                    and not incompatible_dimensions
                ):
                    continue
                text = s(entry.get("text"))
                if normalize_for_lookup(text) in exactly_evidenced_claims:
                    continue
                section = s(entry.get("section") or "grounding")
                unresolved = (
                    outcome == "not_established"
                    and comparison.proposition_status != "incompatible"
                    and not incompatible_dimensions
                )
                violation_type = (
                    "not_established"
                    if unresolved
                    else "contradicted"
                    if incompatible_dimensions or outcome == "contradicted"
                    else "unsupported_factual_claim"
                )
                dimension_text = (
                    f" Protected dimensions: {', '.join(incompatible_dimensions)}."
                    if incompatible_dimensions
                    else ""
                )
                reason = s(entry.get("reason") or "Unsupported factual claim")
                issues.append(
                    issue(
                        rule_id=RULE_ID,
                        message=(
                            f"[factual_claim|{violation_type}]"
                            f" {reason}.{dimension_text}: {text[:200]}"
                        ),
                        severity=grounding_issue_severity(
                            section_policy_value=section_policy(section),
                            classification=normalize_claim_classification(
                                s(entry.get("classification"))
                            )
                            or "factual_claim",
                            violation_type=violation_type,
                            text=text,
                        ),
                        section=section,
                        violation_type=violation_type,
                        entity_id=_public_item_id_for_failure(
                            section, text, public_item_ids
                        ),
                    )
                )
                failed_check_keys.add((section, text))
        if isinstance(unsupported, list):
            evidence_quantities = collect_quantities_from_texts(evidence_texts)
            for window in evidence_windows:
                evidence_quantities.extend(window.quantities)
            for entry in unsupported:
                if not isinstance(entry, dict):
                    continue
                text = s(entry.get("text"))
                if normalize_for_lookup(text) in exactly_evidenced_claims:
                    continue
                section = s(entry.get("section") or "grounding")
                if (section, text) in failed_check_keys:
                    continue
                reason = s(entry.get("reason") or "Unsupported sentence")
                section_key = section_root(section)
                current_policy = section_policy(section)
                classification = normalize_claim_classification(
                    s(entry.get("classification"))
                )
                if not classification:
                    classification = infer_claim_classification(section_key, text)
                entailment_outcome = normalize_entailment_outcome(
                    s(entry.get("entailment_outcome"))
                )
                violation_type = normalize_violation_type(
                    s(entry.get("violation_type") or entry.get("failure_type"))
                )
                violation_type_supplied = bool(violation_type)
                if entailment_outcome == "contradicted":
                    violation_type = "contradicted"
                elif (
                    entailment_outcome == "not_established"
                    and classification == "factual_claim"
                    and violation_type in {"", "unsupported_factual_claim"}
                ):
                    violation_type = "not_established"
                if not violation_type:
                    violation_type = infer_violation_type(
                        section_key=section_key,
                        classification=classification,
                        text=text,
                        reason=reason,
                    )
                if (
                    not violation_type_supplied
                    and classification != "factual_claim"
                    and violation_type == "non_fatal_interpretation"
                ):
                    violation_type = "unsupported_factual_claim"
                severity = grounding_issue_severity(
                    section_policy_value=current_policy,
                    classification=classification,
                    violation_type=violation_type,
                    text=text,
                )
                if severity == "pass":
                    continue
                if text:
                    issues.append(
                        issue(
                            rule_id=RULE_ID,
                            message=(
                                f"[{classification}|{violation_type}] "
                                f"{reason}: {text[:200]}"
                            ),
                            severity=severity,
                            section=section,
                            violation_type=violation_type,
                            entity_id=_public_item_id_for_failure(
                                section, text, public_item_ids
                            ),
                        )
                    )
    except AppError as exc:
        if exc.retryable:
            logger.info(
                log_event(
                    prompt_ctx,
                    role="generator",
                    event="grounding_retryable_error_propagated",
                    module=LOGGER_NAME,
                    fields={"code": exc.code, "message": exc.message},
                )
            )
            raise
        logger.info(
            log_event(
                prompt_ctx,
                role="generator",
                event="grounding_failed",
                module=LOGGER_NAME,
                fields={"code": exc.code, "message": exc.message},
            )
        )
        issues.append(
            issue(
                rule_id=RULE_ID,
                message=f"Grounding check failed: {exc.message}",
                severity=(
                    "warning" if request.deterministic_grounding_passed else "error"
                ),
                section="grounding",
            )
        )
    return issues


def _validate_semantic_input_identities(
    semantic_inputs: Sequence[ClaimSemanticInput],
) -> None:
    """Reject claim IDs that name conflicting semantic grounding inputs."""

    identities: dict[str, tuple[object, ...]] = {}
    for semantic_input in semantic_inputs:
        candidate = semantic_input.candidate
        identity = (
            candidate.source_family,
            candidate.text,
            candidate.text_hash,
            candidate.kind,
            candidate.factual,
            tuple(candidate.evidence_references),
            semantic_input.evidence_hash,
            semantic_input.source_identity,
        )
        prior = identities.get(candidate.claim_id)
        if prior is not None and prior != identity:
            raise AppError(
                code="grounding_claim_identity_ambiguous",
                message=("A retained claim ID refers to conflicting text or evidence"),
                retryable=False,
                context={"missing_claim_ids": [candidate.claim_id]},
            )
        identities[candidate.claim_id] = identity


def _validate_verified_semantic_inputs(
    package: ClaimValidationPackage,
    semantic_inputs: Sequence[ClaimSemanticInput],
    facts: Mapping[str, Mapping[str, Any]],
    evidence_packs: dict,
    *,
    source_identity: str,
) -> None:
    """Bind supplied semantic inputs to the current verified-fact snapshot."""

    expected_source_identity = next(
        (
            str(fact.get("source_identity") or "").strip()
            for fact in facts.values()
            if str(fact.get("source_identity") or "").strip()
        ),
        "",
    )
    if (
        source_identity
        and expected_source_identity
        and source_identity.casefold() != expected_source_identity.casefold()
    ):
        raise AppError(
            code="grounding_verified_semantic_input_invalid",
            message="Verified semantic inputs use a conflicting source identity",
            retryable=False,
        )

    candidates_by_id: dict[str, list[Any]] = {}
    for result in package.results:
        candidates_by_id.setdefault(result.candidate.claim_id, []).append(
            result.candidate
        )

    canonical_evidence_texts = {
        f"verified-fact:{fact_id}": str(fact.get("statement") or "").strip()
        for fact_id, fact in facts.items()
    }

    expected_inputs: list[tuple[Any, tuple[str, ...], str, str]] = []
    for result in package.results:
        candidate = result.candidate
        if (
            not candidate.factual
            or result.deterministic_status != "unresolved"
            or any(check.status == "failed" for check in result.checks)
            or not candidate.evidence_references
        ):
            continue
        evidence_texts = tuple(
            canonical_evidence_texts.get(reference.evidence_id, "")
            for reference in candidate.evidence_references
        )
        if not all(evidence_texts):
            continue
        evidence_hash = retained_claim_semantic_evidence_hash(
            candidate,
            evidence_packs,
        )
        expected_identity = (candidate, evidence_texts, evidence_hash, source_identity)
        if not any(
            expected_identity[0] == existing[0]
            and expected_identity[1:] == existing[1:]
            for existing in expected_inputs
        ):
            expected_inputs.append(expected_identity)

    for semantic_input in semantic_inputs:
        candidate = semantic_input.candidate
        matching_candidates = candidates_by_id.get(candidate.claim_id, [])
        if not matching_candidates or not any(
            candidate == expected for expected in matching_candidates
        ):
            raise AppError(
                code="grounding_verified_semantic_input_invalid",
                message=(
                    "Verified semantic inputs do not match retained claim identities"
                ),
                retryable=False,
                context={"claim_id": candidate.claim_id},
            )
        if (
            expected_source_identity
            and semantic_input.source_identity.casefold()
            != expected_source_identity.casefold()
        ):
            raise AppError(
                code="grounding_verified_semantic_input_invalid",
                message="Verified semantic inputs use a stale source identity",
                retryable=False,
                context={"claim_id": candidate.claim_id},
            )

        expected_evidence_hash = retained_claim_semantic_evidence_hash(
            candidate, evidence_packs
        )
        expected_evidence_texts = tuple(
            canonical_evidence_texts.get(reference.evidence_id, "")
            for reference in candidate.evidence_references
        )
        if (
            semantic_input.evidence_hash != expected_evidence_hash
            or tuple(semantic_input.evidence_texts) != expected_evidence_texts
            or not all(expected_evidence_texts)
        ):
            raise AppError(
                code="grounding_verified_semantic_input_invalid",
                message=(
                    "Verified semantic inputs are not bound to canonical fact evidence"
                ),
                retryable=False,
                context={"claim_id": candidate.claim_id},
            )

        for index, expected in enumerate(expected_inputs):
            if (
                candidate == expected[0]
                and tuple(semantic_input.evidence_texts) == expected[1]
                and semantic_input.evidence_hash == expected[2]
                and semantic_input.source_identity == expected[3]
            ):
                expected_inputs.pop(index)
                break
        else:
            raise AppError(
                code="grounding_verified_semantic_input_invalid",
                message="Verified semantic inputs are incomplete or not eligible",
                retryable=False,
                context={"claim_id": candidate.claim_id},
            )

    if expected_inputs:
        raise AppError(
            code="grounding_verified_semantic_input_invalid",
            message="Verified semantic inputs omit canonical retained claims",
            retryable=False,
            context={
                "claim_ids": [item[0].claim_id for item in expected_inputs],
            },
        )


def _validate_grounding_check_coverage(
    payload: object,
    semantic_inputs: Sequence[ClaimSemanticInput],
    retained_item_ids: Mapping[str, str],
    allowed_public_item_ids: Sequence[str] = (),
    expected_public_items: Sequence[Mapping[str, Any]] = (),
    require_public_coverage: bool = False,
) -> None:
    """Require exact structured coverage for retained and verified public claims."""

    if not isinstance(payload, dict):
        return
    expected = {
        retained_item_ids[semantic_input.candidate.claim_id]: (
            semantic_input.candidate.text
        )
        for semantic_input in semantic_inputs
    }
    public_items = list(expected_public_items)
    if not public_items and isinstance(payload.get("public_factual_items"), list):
        public_items = [
            item for item in payload["public_factual_items"] if isinstance(item, dict)
        ]
    expected_public: dict[str, str] = {}
    for item in public_items:
        item_id = s(item.get("item_id"))
        text = s(item.get("text"))
        if not item_id or not text:
            raise AppError(
                code="grounding_claim_check_coverage_invalid",
                message="Verified public grounding items require stable IDs and text",
                retryable=False,
            )
        prior = expected_public.get(item_id)
        if prior is not None and prior != text:
            raise AppError(
                code="grounding_claim_check_coverage_invalid",
                message="Verified public grounding IDs refer to conflicting text",
                retryable=False,
                context={"item_id": item_id},
            )
        expected_public[item_id] = text
    allowed_item_ids = set(expected)
    allowed_item_ids.update(expected_public)
    allowed_item_ids.update(
        item_id for item_id in allowed_public_item_ids if s(item_id)
    )
    if not require_public_coverage and isinstance(
        payload.get("public_factual_items"), list
    ):
        allowed_item_ids.update(
            s(item.get("item_id"))
            for item in payload["public_factual_items"]
            if isinstance(item, dict) and s(item.get("item_id"))
        )
    response_entries = [
        entry
        for field_name in ("checks", "unsupported")
        for entry in (payload.get(field_name) or [])
        if isinstance(entry, dict)
    ]
    if require_public_coverage and any(
        not s(entry.get("item_id")) for entry in response_entries
    ):
        raise AppError(
            code="grounding_claim_check_coverage_invalid",
            message="Verified grounding responses require stable item identifiers",
            retryable=False,
        )
    unknown_item_ids = {
        s(entry.get("item_id"))
        for entry in response_entries
        if s(entry.get("item_id")) and s(entry.get("item_id")) not in allowed_item_ids
    }
    if require_public_coverage and unknown_item_ids:
        raise AppError(
            code="grounding_claim_check_coverage_invalid",
            message="Grounding response contains an unknown item identifier",
            retryable=False,
            context={"unknown_item_ids": sorted(unknown_item_ids)[:32]},
        )
    checks_by_id: dict[str, list[dict[str, Any]]] = {}
    checks = payload.get("checks")
    if isinstance(checks, list):
        for check in checks:
            if isinstance(check, dict) and s(check.get("item_id")):
                checks_by_id.setdefault(s(check.get("item_id")), []).append(check)
    if expected:
        missing_claim_ids = [
            claim_id
            for claim_id, text in expected.items()
            if len(checks_by_id.get(claim_id, [])) != 1
            or s(checks_by_id[claim_id][0].get("text")) != text
            or s(checks_by_id[claim_id][0].get("classification")) != "factual_claim"
        ]
        if missing_claim_ids:
            raise AppError(
                code="grounding_claim_check_coverage_invalid",
                message=(
                    "Grounding must return exactly one identity-matching factual "
                    "check for each retained claim"
                ),
                retryable=False,
                context={
                    "missing_claim_ids": missing_claim_ids[:32],
                    "missing_claim_count": len(missing_claim_ids),
                },
            )
    if not require_public_coverage or not expected_public:
        return
    unsupported_by_id: dict[str, list[dict[str, Any]]] = {}
    unsupported = payload.get("unsupported")
    if isinstance(unsupported, list):
        for entry in unsupported:
            if isinstance(entry, dict) and s(entry.get("item_id")):
                unsupported_by_id.setdefault(s(entry["item_id"]), []).append(entry)
    if require_public_coverage:
        malformed_checks = (
            [
                s(entry.get("item_id")) or "<missing>"
                for entry in checks
                if isinstance(entry, dict) and not s(entry.get("reason"))
            ]
            if isinstance(checks, list)
            else []
        )
        if malformed_checks:
            raise AppError(
                code="grounding_claim_check_coverage_invalid",
                message="Verified grounding checks require a substantive reason",
                retryable=False,
                context={"item_ids": malformed_checks[:32]},
            )
        valid_classifications = {
            "factual_claim",
            "analyst_interpretation",
            "prescriptive_recommendation",
        }
        malformed_unsupported = (
            [
                s(entry.get("item_id")) or "<missing>"
                for entry in unsupported
                if isinstance(entry, dict)
                and (
                    s(entry.get("classification")) not in valid_classifications
                    or s(entry.get("entailment_outcome"))
                    not in {"contradicted", "not_established"}
                    or not s(entry.get("reason"))
                )
            ]
            if isinstance(unsupported, list)
            else []
        )
        if malformed_unsupported:
            raise AppError(
                code="grounding_claim_check_coverage_invalid",
                message="Verified unsupported grounding verdicts are incomplete",
                retryable=False,
                context={"item_ids": malformed_unsupported[:32]},
            )
    public_coverage_errors: list[str] = []
    for item_id, text in expected_public.items():
        matching_checks = checks_by_id.get(item_id, [])
        matching_unsupported = unsupported_by_id.get(item_id, [])
        if len(matching_checks) > 1 or len(matching_unsupported) > 1:
            public_coverage_errors.append(item_id)
            continue
        if matching_checks:
            check = matching_checks[0]
            if s(check.get("text")) != text:
                public_coverage_errors.append(item_id)
                continue
            classification = s(check.get("classification"))
            outcome = s(check.get("entailment_outcome"))
            comparison = ProtectedFactComparison.from_payload(
                check.get("protected_facts"),
                proposition_status=s(check.get("proposition_status")),
            )
            if outcome == "entailed":
                if (
                    (
                        classification == "factual_claim"
                        and comparison.proposition_status != "compatible"
                    )
                    or comparison.incompatible_dimensions
                    or matching_unsupported
                ):
                    public_coverage_errors.append(item_id)
            elif outcome in {"contradicted", "not_established"}:
                if (
                    not matching_unsupported
                    or s(matching_unsupported[0].get("text")) != text
                ):
                    public_coverage_errors.append(item_id)
            else:
                public_coverage_errors.append(item_id)
        elif not matching_unsupported or s(matching_unsupported[0].get("text")) != text:
            public_coverage_errors.append(item_id)
    if public_coverage_errors:
        raise AppError(
            code="grounding_claim_check_coverage_invalid",
            message=(
                "Verified grounding must return one identity-matching verdict "
                "for every public item"
            ),
            retryable=False,
            context={
                "missing_or_ambiguous_public_item_ids": public_coverage_errors[:32],
                "missing_or_ambiguous_public_item_count": len(public_coverage_errors),
            },
        )


def _retained_claim_semantic_results(
    checks: object,
    semantic_inputs: Sequence[ClaimSemanticInput],
    *,
    retained_item_ids: Mapping[str, str],
    source_identity: str,
    prompt_family: str,
    execution_identity: str,
    validator_version: str,
    model_provider: str,
    model_name: str,
    configuration_policy_identity: str,
    relevant_input_hash: str,
    retrieval_identity: str,
    prompt_content_hash_by_claim_id: dict[str, str],
) -> list[ClaimSemanticGroundingResult]:
    checks_by_id: dict[str, list[dict[str, Any]]] = {}
    if isinstance(checks, list):
        for entry in checks:
            if not isinstance(entry, dict):
                continue
            item_id = s(entry.get("item_id"))
            if item_id:
                checks_by_id.setdefault(item_id, []).append(entry)
    semantic_results: list[ClaimSemanticGroundingResult] = []
    for semantic_input in semantic_inputs:
        candidate = semantic_input.candidate
        claim_prompt_content_hash = prompt_content_hash_by_claim_id.get(
            candidate.claim_id, ""
        )
        if not re.fullmatch(r"[0-9a-f]{64}", claim_prompt_content_hash):
            continue
        matching = checks_by_id.get(retained_item_ids[candidate.claim_id], [])
        if len(matching) != 1:
            continue
        entry = matching[0]
        outcome = normalize_entailment_outcome(s(entry.get("entailment_outcome")))
        if (
            not outcome
            or s(entry.get("text")) != candidate.text
            or s(entry.get("classification")) != "factual_claim"
        ):
            continue
        identity = ClaimSemanticValidationIdentity(
            schema_version="1.1",
            claim_id=candidate.claim_id,
            claim_text_hash=candidate.text_hash,
            evidence_ids=[
                reference.evidence_id for reference in candidate.evidence_references
            ],
            evidence_hash=semantic_input.evidence_hash,
            source_identity=source_identity,
            prompt_family=prompt_family,
            prompt_content_hash=claim_prompt_content_hash,
            execution_identity=execution_identity,
            validator_version=validator_version,
            model_provider=model_provider,
            model_name=model_name,
            configuration_policy_identity=configuration_policy_identity,
            relevant_input_hash=relevant_input_hash,
            retrieval_identity=retrieval_identity,
        )
        comparison = ProtectedFactComparison.from_payload(
            entry.get("protected_facts"),
            proposition_status=s(entry.get("proposition_status")),
        )
        disagreement = (
            "entailed_with_incompatible_proposition"
            if outcome == "entailed" and comparison.proposition_status == "incompatible"
            else ""
        )
        semantic_results.append(
            ClaimSemanticGroundingResult(
                schema_version="1.0",
                outcome=outcome,  # type: ignore[arg-type]
                reason=s(entry.get("reason")),
                identity=identity,
                protected_facts=comparison,
                disagreement=disagreement,
            )
        )
    return semantic_results


def grounding_payload(
    request: ValidationRequest,
    artifacts: dict,
    *,
    retained_claim_inputs: Sequence[ClaimSemanticInput] | None = None,
) -> dict:
    verified_mode = verified_facts_mode(artifacts, request.validation_mode)
    verified_facts: dict[str, dict[str, Any]] = {}
    evidence_packs = request.evidence_packs
    if verified_mode:
        verified_facts = validated_verified_facts(
            artifacts,
            evidence_packs,
            expected_source_identity=str(request.source_id or ""),
        )
        evidence_packs = canonical_verified_evidence_packs(verified_facts)
        request = replace(
            request,
            evidence_packs=evidence_packs,
            source_text="",
            source_pages=[],
        )
    if retained_claim_inputs is None:
        package = validate_retained_claims(
            artifacts,
            evidence_packs,
            source_identity=request.source_id,
            verified_facts_only=verified_mode,
        )
        retained_claim_inputs = retained_claim_semantic_inputs(
            package,
            evidence_packs,
            source_identity=request.source_id,
        )
    summary = artifacts.get("summary") if isinstance(artifacts, dict) else {}
    insights_raw = (
        artifacts.get("insights_final") if isinstance(artifacts, dict) else []
    )
    insights: List[dict] = []
    verified_evidence = canonical_evidence_map(verified_facts)
    for insight in insights_raw if isinstance(insights_raw, list) else []:
        if not isinstance(insight, dict):
            continue
        metric = ensure_dict(insight.get("metric"))
        evidence_id = s(insight.get("evidence_id"))
        fact = fact_for_evidence_id(verified_facts, evidence_id)
        authoritative_metric = (
            ensure_dict(fact.get("metric"))
            if isinstance(fact, dict) and isinstance(fact.get("metric"), dict)
            else metric
        )
        metric_payload = (
            deepcopy(authoritative_metric)
            if verified_mode and isinstance(fact, dict)
            else {
                "value": s(authoritative_metric.get("value")),
                "unit": s(authoritative_metric.get("unit")),
                "timeframe": s(authoritative_metric.get("timeframe")),
                "trend": s(authoritative_metric.get("trend")),
                "sample_size": s(authoritative_metric.get("sample_size")),
                "geography": s(authoritative_metric.get("geography")),
                "segment": s(authoritative_metric.get("segment")),
                "subject": s(authoritative_metric.get("subject")),
                "cohort": s(authoritative_metric.get("cohort")),
                "denominator": s(authoritative_metric.get("denominator")),
                "observation_status": s(
                    authoritative_metric.get("observation_status")
                ),
                "observations": authoritative_metric.get("observations")
                if isinstance(authoritative_metric.get("observations"), list)
                else [],
            }
        )
        insights.append(
            {
                "id": s(insight.get("id")),
                "text": s(insight.get("text")),
                "evidence_id": evidence_id,
                "evidence": (
                    verified_evidence.get(evidence_id, s(insight.get("evidence")))
                    if not verified_mode
                    else verified_evidence.get(evidence_id, "")
                ),
                "metric": metric_payload,
                "so_what": sanitize_citation_tokens(s(insight.get("so_what"))),
                "now_what": sanitize_citation_tokens(s(insight.get("now_what"))),
            }
        )
    raw_claim_evidence_map = (
        summary.get("claim_evidence_map") if isinstance(summary, dict) else []
    )
    claim_evidence_map: Any = raw_claim_evidence_map
    if verified_mode and isinstance(raw_claim_evidence_map, list):
        canonical_claim_evidence_map: list[dict[str, Any]] = []
        for entry in raw_claim_evidence_map:
            if not isinstance(entry, dict):
                continue
            canonical_entry = dict(entry)
            evidence_id = s(canonical_entry.get("evidence_id"))
            canonical_entry["evidence"] = verified_evidence.get(evidence_id, "")
            canonical_claim_evidence_map.append(canonical_entry)
        claim_evidence_map = canonical_claim_evidence_map
    summary_clean: dict[str, Any] = {
        "tldr": s(summary.get("tldr")) if isinstance(summary, dict) else "",
        "executive_summary": sanitize_citation_tokens(
            s(summary.get("executive_summary"))
        )
        if isinstance(summary, dict)
        else "",
        "card_tldr_compact": sanitize_citation_tokens(
            s(summary.get("card_tldr_compact"))
        )
        if isinstance(summary, dict)
        else "",
        "claim_evidence_map": claim_evidence_map,
    }
    title_is_canonical = (
        verified_mode
        or _matches_canonical_doc_map_identity(
            request.report.title, request.evidence_packs.get("doc_map"), field="title"
        )
        or _matches_explicit_source_title(request.report.title, request)
    )
    publisher_is_canonical = verified_mode or _matches_canonical_doc_map_identity(
        request.report.publisher,
        request.evidence_packs.get("doc_map"),
        field="publisher",
    )
    payload = {
        "tldr": request.report.tldr,
        "insights_final": insights,
        "quotes_final": artifacts.get("quotes_final")
        if isinstance(artifacts, dict)
        else [],
        "summary": summary_clean,
        "expert_comment": sanitize_citation_tokens(
            s(artifacts.get("expert_comment") if isinstance(artifacts, dict) else "")
        ),
        "linkedin_post": sanitize_citation_tokens(
            s(artifacts.get("linkedin_post") if isinstance(artifacts, dict) else "")
        ),
    }
    if verified_mode:
        payload["canonical_verified_facts"] = deepcopy(verified_facts)
    # This remains one batched grounding call.  The explicit inventory prevents
    # public projections such as figures and downstream prose from becoming
    # invisible merely because they are not top-level analysis artifacts.
    if not title_is_canonical and request.report.title:
        payload["title"] = request.report.title
    if not publisher_is_canonical and request.report.publisher:
        payload["publisher"] = request.report.publisher
    public_factual_items = _public_factual_items(
        artifacts=artifacts,
        evidence_packs=request.evidence_packs,
        source_pages=request.source_pages,
        report_title=("" if title_is_canonical else request.report.title),
        publisher=("" if publisher_is_canonical else request.report.publisher),
        insights=insights,
        summary=summary_clean,
        verified_facts=verified_facts,
    )
    payload["public_factual_items"] = public_factual_items
    public_item_ids = {
        s(item.get("item_id"))
        for item in public_factual_items
        if isinstance(item, dict) and s(item.get("item_id"))
    }
    retained_item_ids = _retained_claim_grounding_item_ids(
        retained_claim_inputs, public_item_ids
    )
    payload["retained_claims_to_ground"] = [
        {
            "item_id": retained_item_ids[semantic_input.candidate.claim_id],
            "section": semantic_input.candidate.affected_section
            or semantic_input.candidate.source_family,
            "text": semantic_input.candidate.text,
            "text_hash": semantic_input.candidate.text_hash,
            "evidence_ids": [
                reference.evidence_id
                for reference in semantic_input.candidate.evidence_references
            ],
            "evidence_hash": semantic_input.evidence_hash,
            "retained_evidence": [
                {
                    "evidence_id": reference.evidence_id,
                    "text_hash": reference.text_hash,
                    "source_pack": reference.source_pack,
                    "page": reference.page,
                    "text": evidence_text,
                }
                for reference, evidence_text in zip(
                    semantic_input.candidate.evidence_references,
                    semantic_input.evidence_texts,
                    strict=True,
                )
            ],
        }
        for semantic_input in retained_claim_inputs
    ]
    return payload


def _retained_claim_grounding_item_ids(
    semantic_inputs: Sequence[ClaimSemanticInput], public_item_ids: set[str]
) -> dict[str, str]:
    """Keep provider identities distinct when inventories contain the same ID."""

    assigned = set(public_item_ids)
    output: dict[str, str] = {}
    for semantic_input in semantic_inputs:
        candidate = semantic_input.candidate
        claim_id = candidate.claim_id
        provider_id = claim_id
        if provider_id in assigned:
            identity = {
                "claim_id": claim_id,
                "claim_text_hash": candidate.text_hash,
                "evidence_hash": semantic_input.evidence_hash,
                "source_identity": semantic_input.source_identity,
            }
            suffix = hashlib.sha256(
                json.dumps(
                    identity, ensure_ascii=True, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
            provider_id = f"retained_claim:{suffix}"
            collision_index = 1
            while provider_id in assigned:
                provider_id = f"retained_claim:{suffix}:{collision_index}"
                collision_index += 1
        assigned.add(provider_id)
        output[claim_id] = provider_id
    return output


def _matches_canonical_doc_map_identity(
    public_value: object, doc_map: object, *, field: str
) -> bool:
    """Match only an unambiguous, non-generic DocMap identity value."""
    public_key = _identity_match_key(public_value)
    canonical_value = _canonical_doc_map_identity(doc_map, field=field)
    return bool(public_key and canonical_value) and public_key == _identity_match_key(
        canonical_value
    )


def _canonical_doc_map_identity(doc_map: object, *, field: str) -> str:
    """Return the existing unambiguous retained identity comparison value."""
    if not isinstance(doc_map, dict):
        return ""
    candidate = doc_map
    for key in ("doc_map", "docmap", "docMap"):
        wrapped = doc_map.get(key)
        if isinstance(wrapped, dict):
            candidate = wrapped
            break
    document = candidate.get("document")
    document = document if isinstance(document, dict) else {}
    aliases = (
        ("title", "report_title", "document_title", "document_name", "name")
        if field == "title"
        else (
            "publisher",
            "document_publisher",
            "document_organization",
            "document_organisation",
            "organization",
            "organisation",
        )
    )
    values = [str(candidate.get(key) or "").strip() for key in aliases]
    if field == "title":
        values.extend(str(document.get(key) or "").strip() for key in ("title", "name"))
    else:
        values.extend(
            str(document.get(key) or "").strip()
            for key in ("publisher", "organization", "organisation")
        )
    values = [value for value in values if value]
    canonical_keys = {_identity_match_key(value) for value in values}
    if len(canonical_keys) != 1:
        return ""
    canonical_value = values[0]
    if field == "title" and is_generic_report_title(canonical_value):
        return ""
    return canonical_value


def _matches_explicit_source_title(
    public_value: object, request: ValidationRequest
) -> bool:
    """Accept a title only when the resolver found the same visible cover title.

    DocMap is a generated navigation artifact and can mistake a contents-page
    heading for document identity.  The source-page title resolver is already
    the canonical deterministic identity boundary, so a matching explicit
    cover title establishes the public title even when the DocMap is stale or
    conflicting.
    """

    public_key = _identity_match_key(public_value)
    if not public_key:
        return False
    if request.source_title_resolution is not None:
        approved_title = source_backed_title(request.source_title_resolution)
        return bool(approved_title) and public_key == _identity_match_key(
            approved_title
        )
    if not request.source_pages:
        return False
    resolution = resolve_report_title(
        file_name="",
        source_report_name="",
        pdf_metadata={},
        pages=[
            (page.page_number, page.text)
            for page in request.source_pages
            if page.page_number > 0 and page.text.strip()
        ],
    )
    explicit_title = str(resolution.explicit_source_title or "").strip()
    return bool(explicit_title) and public_key == _identity_match_key(explicit_title)


def _identity_match_key(value: object) -> str:
    """Apply the punctuation/casing normalization used by source title matching."""
    return re.sub(r"[^a-z0-9]", "", s(value).casefold())


def _public_factual_items(
    *,
    artifacts: dict,
    evidence_packs: dict,
    source_pages: Sequence[PdfTextPage] = (),
    report_title: str,
    publisher: str,
    insights: Sequence[dict],
    summary: dict[str, Any],
    verified_facts: Mapping[str, Mapping[str, Any]] | None = None,
) -> List[dict]:
    """Material public claims with their exact retained evidence payloads."""
    items: List[dict] = []
    verified_evidence_by_id = canonical_evidence_map(verified_facts or {})
    source_page_texts = {
        int(page.page_number): s(page.text)
        for page in source_pages
        if getattr(page, "page_number", 0) and s(getattr(page, "text", ""))
    }
    doc_map = ensure_dict(evidence_packs.get("doc_map"))
    roles = ensure_dict(doc_map.get("provenance_roles"))
    publisher_name = s(roles.get("publisher_name"))
    publisher_proof = [
        entry
        for entry in roles.get("evidence", [])
        if isinstance(entry, dict)
        and entry.get("role") in {"publisher", "report_owner"}
        and _identity_match_key(entry.get("name"))
        == _identity_match_key(publisher_name)
        and s(entry.get("evidence_locator"))
        and s(entry.get("evidence_hash"))
    ]
    source_identity = (
        {"publisher_name": publisher_name, "provenance_evidence": publisher_proof}
        if roles.get("status") == "resolved" and publisher_name and publisher_proof
        else {}
    )
    try:
        soft_copy_claims = soft_copy_claim_provenance_from_payload(
            artifacts.get("soft_copy_claim_provenance")
        )
    except AppError:
        soft_copy_claims = []

    def add(
        item_id: str,
        section: str,
        text: object,
        evidence_ids: Sequence[str] = (),
        evidence_text: object = "",
        declared_classification: str = "",
    ) -> None:
        claim = sanitize_citation_tokens(s(text))
        if claim:
            if verified_evidence_by_id:
                normalized_evidence_ids = [
                    s(evidence_id) for evidence_id in evidence_ids if s(evidence_id)
                ]
                if (
                    not normalized_evidence_ids
                    or any(
                        evidence_id not in verified_evidence_by_id
                        for evidence_id in normalized_evidence_ids
                    )
                    or not s(evidence_text)
                ):
                    raise AppError(
                        code="grounding_public_item_evidence_invalid",
                        message=(
                            "Verified public grounding items require one or more "
                            "known authoritative evidence bindings"
                        ),
                        retryable=False,
                        context={"item_id": item_id},
                    )
            item: dict[str, Any] = {
                "item_id": item_id,
                "section": section,
                "text": claim,
                "evidence_ids": [value for value in evidence_ids if value],
                "retained_evidence": s(evidence_text),
            }
            if declared_classification:
                item["declared_classification"] = declared_classification
            if source_identity:
                item["source_identity"] = source_identity
            if any(
                existing.get("item_id") == item_id
                and existing.get("text") == claim
                and existing.get("evidence_ids") == item["evidence_ids"]
                and existing.get("retained_evidence") == item["retained_evidence"]
                and existing.get("declared_classification", "")
                == item.get("declared_classification", "")
                and existing.get("source_identity", {})
                == item.get("source_identity", {})
                for existing in items
            ):
                return
            items.append(item)

    def add_soft_copy_sentences(
        family: str,
        section: str,
        text: object,
        fallback_evidence_ids: Sequence[str],
        fallback_evidence_text: object,
        evidence_by_id: dict[str, str],
    ) -> None:
        public_text = sanitize_citation_tokens(s(text))
        sentences = soft_copy_material_sentences(public_text)
        claims_by_hash: dict[str, list[Any]] = {}
        for claim in soft_copy_claims:
            if claim.artifact_family == family:
                claims_by_hash.setdefault(claim.text_hash, []).append(claim)
        matched = [
            claims_by_hash.get(
                hashlib.sha256(" ".join(sentence.split()).encode("utf-8")).hexdigest(),
                [],
            )
            for sentence in sentences
        ]
        if sentences and all(len(values) == 1 for values in matched):
            for sentence, values in zip(sentences, matched, strict=True):
                claim = values[0]
                provenance_evidence = (
                    [
                        verified_evidence_by_id[evidence_id]
                        for evidence_id in claim.evidence_ids
                        if evidence_id in verified_evidence_by_id
                    ]
                    if verified_evidence_by_id
                    else [
                        s(span.get("text"))
                        for span in claim.source_spans
                        if s(span.get("evidence_id")) in claim.evidence_ids
                        and s(span.get("text"))
                    ]
                )
                add(
                    claim.claim_id,
                    section,
                    sentence,
                    claim.evidence_ids,
                    "\n".join(provenance_evidence)
                    if provenance_evidence
                    else "\n".join(
                        evidence_by_id[evidence_id]
                        for evidence_id in claim.evidence_ids
                        if evidence_id in evidence_by_id
                    ),
                    claim.classification,
                )
            return
        add(
            family if family != "summary" else f"summary:{section}",
            section,
            text,
            fallback_evidence_ids,
            fallback_evidence_text,
        )

    evidence_spans = artifact_evidence_span_index(
        doc_map=ensure_dict(evidence_packs.get("doc_map")),
        evidence_packs=evidence_packs,
    )

    def retained_evidence_text_for_id(
        evidence_id: str,
        *,
        statement: str = "",
        fallback: str = "",
    ) -> str:
        """Combine concise retained copy with authoritative source spans."""

        if verified_evidence_by_id:
            return verified_evidence_by_id.get(evidence_id, "")

        spans = evidence_spans.get(evidence_id.casefold(), [])
        ordered_packs = (
            "findings_statement",
            "source_pdf",
            "findings",
            "doc_map",
        )
        texts: list[str] = []
        for source_pack in ordered_packs:
            texts.extend(
                s(span.get("text"))
                for span in spans
                if s(span.get("source_pack")) == source_pack and s(span.get("text"))
            )
        for span in spans:
            page = span.get("page")
            if isinstance(page, int) and page in source_page_texts:
                texts.append(source_page_texts[page])
        if statement:
            texts.append(statement)
        if fallback:
            texts.append(fallback)
        return "\n".join(dict.fromkeys(texts))

    summary_evidence = [
        entry
        for entry in (
            summary.get("claim_evidence_map", [])
            if isinstance(summary.get("claim_evidence_map", []), list)
            else []
        )
        if isinstance(entry, dict)
    ]
    evidence_ids = [s(entry.get("evidence_id")) for entry in summary_evidence]
    summary_evidence_by_id = {
        s(entry.get("evidence_id")): retained_evidence_text_for_id(
            s(entry.get("evidence_id")),
            fallback=s(entry.get("evidence")),
        )
        for entry in summary_evidence
    }
    evidence_text = "\n".join(summary_evidence_by_id.values())
    for field_name in ("tldr", "card_tldr_compact", "executive_summary"):
        add_soft_copy_sentences(
            "summary",
            field_name,
            summary.get(field_name),
            evidence_ids,
            evidence_text,
            summary_evidence_by_id,
        )
    insight_evidence = (
        verified_evidence_by_id
        if verified_evidence_by_id
        else {
            s(insight.get("evidence_id")): s(insight.get("evidence"))
            for insight in insights
        }
    )
    insight_statements = {
        s(insight.get("evidence_id")): s(insight.get("text"))
        for insight in insights
        if s(insight.get("evidence_id")) and s(insight.get("text"))
    }

    def evidence_text_for_id(evidence_id: str) -> str:
        return retained_evidence_text_for_id(
            evidence_id,
            statement=insight_statements.get(evidence_id, ""),
            fallback=insight_evidence.get(evidence_id, ""),
        )

    for insight in insights:
        insight_id = insight_entity_id(insight)
        evidence_id = s(insight.get("evidence_id"))
        for field_name in ("text", "so_what", "now_what"):
            declared_classification = {
                "text": "factual_claim",
                "so_what": "analyst_interpretation",
                "now_what": "prescriptive_recommendation",
            }[field_name]
            add(
                f"insight:{insight_id}:{field_name}",
                f"insights:{insight_id}.{field_name}",
                insight.get(field_name),
                [evidence_id],
                retained_evidence_text_for_id(
                    evidence_id,
                    fallback=s(insight.get("evidence")),
                ),
                declared_classification,
            )
    for index, figure in enumerate(artifacts.get("key_figures", []), start=1):
        if not isinstance(figure, dict):
            continue
        evidence_id = s(figure.get("evidence_id"))
        add(
            f"key_figure:{index}:figure",
            f"key_figures:{index}.figure",
            metric_claim_text(figure, include_observations=bool(verified_facts)),
            [evidence_id],
            evidence_text_for_id(evidence_id),
        )
        add(
            f"key_figure:{index}:why_it_matters",
            f"key_figures:{index}.why_it_matters",
            figure.get("why_it_matters"),
            [evidence_id],
            evidence_text_for_id(evidence_id),
        )
    if verified_evidence_by_id:
        for index, metric in enumerate(artifacts.get("metric_spine", []), start=1):
            if not isinstance(metric, dict):
                continue
            evidence_id = s(metric.get("evidence_id"))
            add(
                f"metric_spine:{index}:metric",
                f"metric_spine:{index}",
                metric_claim_text(metric, include_observations=True),
                [evidence_id],
                evidence_text_for_id(evidence_id),
            )
    for family in ("expert_comment", "linkedin_post"):
        add_soft_copy_sentences(
            family,
            family,
            artifacts.get(family),
            list(insight_evidence),
            "\n".join(insight_evidence.values()),
            insight_evidence,
        )
    for field, public_value in (("title", report_title), ("publisher", publisher)):
        canonical_value = _canonical_doc_map_identity(doc_map, field=field)
        add(
            f"metadata:{field}",
            f"metadata.{field}",
            public_value,
            [f"doc_map:{field}"] if canonical_value else [],
            canonical_value,
            "factual_claim",
        )
    return items


def _public_item_ids(items: object) -> dict[tuple[str, str], str]:
    """Index the retained atomic public inventory for failure attribution."""

    indexed: dict[tuple[str, str], str] = {}
    if not isinstance(items, list):
        return indexed
    for entry in items:
        if not isinstance(entry, dict):
            continue
        section = s(entry.get("section"))
        text = s(entry.get("text"))
        item_id = s(entry.get("item_id"))
        if section and text and item_id:
            indexed[(section, text)] = item_id
    return indexed


def _public_item_id_for_failure(
    section: str,
    text: str,
    public_item_ids: dict[tuple[str, str], str],
) -> str:
    """Return an atomic public item ID only for an exact audited assertion."""

    direct = public_item_ids.get((s(section), s(text)))
    if direct:
        return direct
    matches = {
        item_id
        for (item_section, item_text), item_id in public_item_ids.items()
        if item_text == s(text)
        and (
            item_section == s(section)
            or item_section.endswith(s(section))
            or s(section).endswith(item_section)
        )
    }
    if len(matches) == 1:
        return next(iter(matches))
    text_matches = {
        item_id
        for (_, item_text), item_id in public_item_ids.items()
        if item_text == s(text)
    }
    return next(iter(text_matches)) if len(text_matches) == 1 else ""


def normalize_claim_classification(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"factual", "fact", "factual_claim", "claim"}:
        return "factual_claim"
    if normalized in {"analyst_interpretation", "interpretation", "analysis"}:
        return "analyst_interpretation"
    if normalized in {"prescriptive_recommendation", "recommendation", "prescriptive"}:
        return "prescriptive_recommendation"
    return ""


def normalize_entailment_outcome(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"entailed", "contradicted", "not_established"}:
        return normalized
    return ""


def infer_claim_classification(section_key: str, text: str) -> str:
    lowered = normalize_text(text)
    policy = section_policy(section_key)
    if policy == "soft":
        if re.search(
            (
                r"\b(should|must|need to|recommend|recommended|prioriti[sz]e|"
                r"consider|action|next step|implement)\b"
            ),
            lowered,
        ):
            return "prescriptive_recommendation"
        return "factual_claim"
    if (
        policy == "mixed"
        and not METRIC_ATTRIBUTION_RE.search(lowered)
        and re.search(
            r"\b(should|could|may|might|consider|recommend|priority)\b", lowered
        )
    ):
        return "analyst_interpretation"
    return "factual_claim"


def normalize_violation_type(value: str) -> str:
    normalized = value.strip().lower()
    mapping = {
        "hallucinated_entity_or_event": "hallucinated_entity_or_event",
        "hallucination": "hallucinated_entity_or_event",
        "unsupported_number": "unsupported_number",
        "new_number": "unsupported_number",
        "misattributed_quote": "misattributed_quote",
        "quote_misattribution": "misattributed_quote",
        "report_directive_misattribution": "report_directive_misattribution",
        "report_said_x": "report_directive_misattribution",
        "unsupported_factual_claim": "unsupported_factual_claim",
        "factual_claim": "unsupported_factual_claim",
        "unsupported_causal_outcome": "unsupported_causal_outcome",
        "unsupported_causality": "unsupported_causal_outcome",
        "unsupported_certainty": "unsupported_certainty",
        "unsupported_operational_or_financial_benefit": (
            "unsupported_operational_or_financial_benefit"
        ),
        "unsupported_financial_benefit": "unsupported_operational_or_financial_benefit",
        "unsupported_operational_benefit": (
            "unsupported_operational_or_financial_benefit"
        ),
        "numerically_inconsistent": "numerically_inconsistent",
        "numeric_inconsistency": "numerically_inconsistent",
        "contradicted": "contradicted",
        "contradiction": "contradicted",
        "not_established": "not_established",
        "unresolved_factual_claim": "not_established",
        "invalid_comparison": "invalid_comparison",
        "invalid_comparator": "invalid_comparison",
        "missing_material_evidence": "missing_material_evidence",
        "missing_evidence": "missing_material_evidence",
        "hallucinated_evidence_id": "hallucinated_evidence_id",
        "unknown_evidence_id": "hallucinated_evidence_id",
        "evidence_retrieval_failure": "evidence_retrieval_failure",
        "non_fatal_interpretation": "non_fatal_interpretation",
    }
    return mapping.get(normalized, "")


def infer_violation_type(
    *,
    section_key: str,
    classification: str,
    text: str,
    reason: str,
) -> str:
    text_l = normalize_text(text)
    reason_l = normalize_text(reason)
    combined = f"{text_l} {reason_l}"
    if (
        is_report_directive_misattribution(text_l)
        or "report instruct" in combined
        or "report recommends" in combined
    ):
        return "report_directive_misattribution"
    if "invalid comparison" in combined or "incompatible comparison" in combined:
        return "invalid_comparison"
    if "numeric inconsisten" in combined or "numerically inconsisten" in combined:
        return "numerically_inconsistent"
    if "missing material evidence" in combined:
        return "missing_material_evidence"
    if "evidence id" in combined and any(
        keyword in combined for keyword in ("hallucin", "unknown", "invented")
    ):
        return "hallucinated_evidence_id"
    if "contradict" in combined:
        return "contradicted"
    if section_key.startswith("quotes") or "quote" in combined:
        return "misattributed_quote"
    if extract_quantities(text) and any(
        keyword in combined
        for keyword in ("number", "metric", "value", "figure", "percent", "unsupported")
    ):
        return "unsupported_number"
    if any(
        keyword in combined
        for keyword in (
            "hallucin",
            "invented",
            "made up",
            "contradict",
            "not in evidence",
            "unsupported fact",
            "entity",
            "event",
        )
    ):
        return "hallucinated_entity_or_event"
    if classification == "factual_claim":
        return "unsupported_factual_claim"
    return "non_fatal_interpretation"


def is_report_directive_misattribution(text: str) -> bool:
    return bool(
        re.search(
            r"\breport\s+(says|said|states|stated|instructs|instructed|requires|required|recommends|recommended)\b",
            normalize_text(text),
        )
    )


def grounding_issue_severity(
    *,
    section_policy_value: str,
    classification: str,
    violation_type: str,
    text: str,
) -> str:
    if violation_type in GROUNDING_HARD_FAILURES:
        editorial_classification = classification in {
            "analyst_interpretation",
            "prescriptive_recommendation",
        }
        protected_integrity_failures = {
            "hallucinated_entity_or_event",
            "hallucinated_evidence_id",
            "contradicted",
            "invalid_comparison",
            "misattributed_quote",
            "missing_material_evidence",
            "numerically_inconsistent",
            "report_directive_misattribution",
            "unsupported_factual_claim",
            "unsupported_number",
        }
        if (
            editorial_classification
            and section_policy_value in {"soft", "mixed"}
            and violation_type not in protected_integrity_failures
        ):
            return "info"
        return "error"
    if violation_type == "not_established":
        if classification in {
            "analyst_interpretation",
            "prescriptive_recommendation",
        } and section_policy_value in {"soft", "mixed"}:
            return "info"
        return "error"
    if violation_type == "evidence_retrieval_failure":
        return "error"
    if section_policy_value == "soft" and classification in {
        "analyst_interpretation",
        "prescriptive_recommendation",
    }:
        return "info"
    if section_policy_value == "mixed" and classification in {
        "analyst_interpretation",
        "prescriptive_recommendation",
    }:
        return "info"
    if violation_type == "non_fatal_interpretation":
        return "info"
    return "warning"
