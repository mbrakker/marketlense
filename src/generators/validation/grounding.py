from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from typing import Any, Callable, List, Mapping, Sequence

from src.contracts.claim_validation import (
    CLAIM_GROUNDING_VALIDATOR_VERSION,
    ClaimSemanticGroundingResult,
    ClaimSemanticInput,
    ClaimSemanticValidationIdentity,
    ClaimValidationPackage,
)
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
    retained_claim_semantic_inputs,
    validate_retained_claims,
)
from src.generators.prompt_preparation import prepare_prompt_bundle
from src.generators.report_title_resolution_generator import is_generic_report_title
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
from src.utils.text_normalization import normalize_text

from .evidence import sanitize_citation_tokens
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

RULE_ID = "grounding"
GROUNDING_FAMILY_SCHEMA_VERSION = "1.3"
GROUNDING_OUTPUT_SCHEMA_IDENTITY = "grounding_validation_output_v2"
GROUNDING_VALIDATOR_VERSION = CLAIM_GROUNDING_VALIDATOR_VERSION
GROUNDING_MAX_CLAIMS_PER_CALL = 4
GROUNDING_MAX_PUBLIC_ITEMS_PER_CALL = 8


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
    for index in range(batch_count):
        claim_group = claim_groups[index] if index < len(claim_groups) else []
        public_group = public_groups[index] if index < len(public_groups) else []
        batches.append(
            (
                {
                    "public_factual_items": public_group,
                    "retained_claims_to_ground": [
                        entry for _semantic_input, entry in claim_group
                    ],
                },
                [semantic_input for semantic_input, _entry in claim_group],
            )
        )
    return batches


def run_grounding_rule(runtime: ValidationRuntime) -> List[ValidationIssue]:
    package = validate_retained_claims(
        runtime.request.artifacts,
        runtime.request.evidence_packs,
        source_identity=runtime.source_id,
    )
    semantic_inputs = retained_claim_semantic_inputs(
        package,
        runtime.request.evidence_packs,
        source_identity=runtime.source_id,
        source_pages=runtime.request.source_pages,
    )
    runtime.retained_claim_validation = package

    def retain_claim_results(updated: ClaimValidationPackage) -> None:
        runtime.retained_claim_validation = updated

    issues = run_grounding_check(
        request=runtime.request,
        settings=runtime.settings,
        grounding_use_vector_store=runtime.prepared.grounding_use_vector_store,
        evidence_texts=runtime.prepared.evidence_texts,
        evidence_windows=runtime.prepared.evidence_windows,
        prompt_client=runtime.prompt_client,
        openai_client=runtime.openai_client,
        ctx=runtime.ctx,
        source_id=runtime.source_id,
        vector_store_content_hash=runtime.vector_store_content_hash,
        retained_claim_package=package,
        retained_claim_inputs=semantic_inputs,
        retained_claim_validation_sink=retain_claim_results,
    )
    issues.extend(
        _deterministic_claim_validation_issues(
            runtime.retained_claim_validation or package
        )
    )
    return issues


def _deterministic_claim_validation_issues(
    package: ClaimValidationPackage,
) -> List[ValidationIssue]:
    """Expose deterministic retained-claim failures to candidate validation."""
    issues: List[ValidationIssue] = []
    for result in package.results:
        candidate = result.candidate
        if not candidate.factual or result.deterministic_status != "unsupported":
            continue
        for check in result.checks:
            if check.status != "failed":
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
    if retained_claim_package is None:
        retained_claim_package = validate_retained_claims(
            artifacts,
            request.evidence_packs,
            source_identity=source_id or request.source_id,
        )
    if retained_claim_inputs is None:
        retained_claim_inputs = retained_claim_semantic_inputs(
            retained_claim_package,
            request.evidence_packs,
            source_identity=source_id or request.source_id,
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
    batch_prompt_vars = [
        {
            "report_json": json.dumps(batch_payload, ensure_ascii=False),
            "evidence_json": json.dumps(list(evidence_texts), ensure_ascii=False),
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
            user_variables=variables,
        )

    prompt_bundles = [
        prepare_batch_bundle(variables) for variables in batch_prompt_vars
    ]
    prompt_bundle = prompt_bundles[0]
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
            "batch_policy": {
                "schema_version": "1.0",
                "max_claims_per_call": GROUNDING_MAX_CLAIMS_PER_CALL,
                "max_public_items_per_call": GROUNDING_MAX_PUBLIC_ITEMS_PER_CALL,
            },
        }
    )
    configuration_policy_hash = sha256_json(
        {
            "execution_policy_hash": prompt_bundle.execution_policy.policy_hash,
            "execution_policy": asdict(prompt_bundle.execution_policy.policy),
            "routing_policy": asdict(prompt_bundle.routing_decision),
        }
    )
    try:
        output_schema = provider_output_schema("grounding_validation_output")
        _validate_semantic_input_identities(retained_claim_inputs)

        def validate_grounding_payload(
            payload: object,
            expected_inputs: Sequence[ClaimSemanticInput] | None = None,
        ) -> None:
            validate_schema(
                SchemaValidateRequest(
                    schema_version="1.0",
                    payload=payload,
                    schema_name="grounding_validation_output",
                ),
                prompt_ctx,
            )
            _validate_grounding_check_coverage(
                payload,
                retained_claim_inputs if expected_inputs is None else expected_inputs,
                retained_item_ids,
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
            for batch_index, (batch_spec, batch_vars, batch_bundle) in enumerate(
                zip(
                    grounding_batches,
                    batch_prompt_vars,
                    prompt_bundles,
                    strict=True,
                ),
                start=1,
            ):
                _batch_payload, batch_semantic_inputs = batch_spec

                def call_model(
                    mode: str,
                    original_response: str,
                    schema_errors: str,
                    *,
                    variables=batch_vars,
                    base_bundle=batch_bundle,
                    call_index=batch_index,
                ):
                    nonlocal recovery_attempted
                    if mode != "primary":
                        recovery_attempted = True
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
                            },
                            settings=settings,
                            ctx=prompt_ctx,
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
                        ctx=prompt_ctx,
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
                    validate_grounding_payload(payload, batch_semantic_inputs)

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
                    prompt_ctx,
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
                response_payload["unsupported"].extend(
                    recovery.payload.get("unsupported") or []
                )
                response_payload["checks"].extend(recovery.payload.get("checks") or [])
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
            prompt_content_hash=prompt_bundle.prompt_content_hash,
            execution_identity=prompt_bundle.execution_identity.execution_identity,
            validator_version=GROUNDING_VALIDATOR_VERSION,
            model_provider=str(prompt_bundle.execution_policy.policy.provider),
            model_name=prompt_bundle.resolved_model,
            configuration_policy_identity=configuration_policy_hash,
            relevant_input_hash=relevant_input_hash,
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
        retained_claim_item_ids = set(retained_item_ids.values())
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
                retained_claim_not_established = (
                    unresolved and s(entry.get("item_id")) in retained_claim_item_ids
                )
                issues.append(
                    issue(
                        rule_id=RULE_ID,
                        message=(
                            f"[factual_claim|{violation_type}]"
                            f" {reason}.{dimension_text}: {text[:200]}"
                        ),
                        severity=(
                            "warning"
                            if unresolved and not retained_claim_not_established
                            else "error"
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


def _validate_grounding_check_coverage(
    payload: object,
    semantic_inputs: Sequence[ClaimSemanticInput],
    retained_item_ids: Mapping[str, str],
) -> None:
    """Require one exact structured check for each unique retained claim."""

    if not isinstance(payload, dict):
        return
    expected = {
        retained_item_ids[semantic_input.candidate.claim_id]: (
            semantic_input.candidate.text
        )
        for semantic_input in semantic_inputs
    }
    if not expected:
        return
    checks_by_id: dict[str, list[dict[str, Any]]] = {}
    checks = payload.get("checks")
    if isinstance(checks, list):
        for check in checks:
            if isinstance(check, dict) and s(check.get("item_id")):
                checks_by_id.setdefault(s(check.get("item_id")), []).append(check)
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
                "Grounding must return exactly one identity-matching factual check "
                "for each retained claim"
            ),
            retryable=False,
            context={
                "missing_claim_ids": missing_claim_ids[:32],
                "missing_claim_count": len(missing_claim_ids),
            },
        )


def _retained_claim_semantic_results(
    checks: object,
    semantic_inputs: Sequence[ClaimSemanticInput],
    *,
    retained_item_ids: Mapping[str, str],
    source_identity: str,
    prompt_family: str,
    prompt_content_hash: str,
    execution_identity: str,
    validator_version: str,
    model_provider: str,
    model_name: str,
    configuration_policy_identity: str,
    relevant_input_hash: str,
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
            schema_version="1.0",
            claim_id=candidate.claim_id,
            claim_text_hash=candidate.text_hash,
            evidence_ids=[
                reference.evidence_id for reference in candidate.evidence_references
            ],
            evidence_hash=semantic_input.evidence_hash,
            source_identity=source_identity,
            prompt_family=prompt_family,
            prompt_content_hash=prompt_content_hash,
            execution_identity=execution_identity,
            validator_version=validator_version,
            model_provider=model_provider,
            model_name=model_name,
            configuration_policy_identity=configuration_policy_identity,
            relevant_input_hash=relevant_input_hash,
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
    if retained_claim_inputs is None:
        package = validate_retained_claims(
            artifacts,
            request.evidence_packs,
            source_identity=request.source_id,
        )
        retained_claim_inputs = retained_claim_semantic_inputs(
            package,
            request.evidence_packs,
            source_identity=request.source_id,
        )
    summary = artifacts.get("summary") if isinstance(artifacts, dict) else {}
    insights_raw = (
        artifacts.get("insights_final") if isinstance(artifacts, dict) else []
    )
    insights: List[dict] = []
    for insight in insights_raw if isinstance(insights_raw, list) else []:
        if not isinstance(insight, dict):
            continue
        metric = ensure_dict(insight.get("metric"))
        insights.append(
            {
                "id": s(insight.get("id")),
                "text": s(insight.get("text")),
                "evidence_id": s(insight.get("evidence_id")),
                "evidence": s(insight.get("evidence")),
                "metric": {
                    "value": s(metric.get("value")),
                    "unit": s(metric.get("unit")),
                    "timeframe": s(metric.get("timeframe")),
                    "trend": s(metric.get("trend")),
                    "sample_size": s(metric.get("sample_size")),
                    "geography": s(metric.get("geography")),
                    "segment": s(metric.get("segment")),
                    "subject": s(metric.get("subject")),
                    "cohort": s(metric.get("cohort")),
                    "denominator": s(metric.get("denominator")),
                    "observation_status": s(metric.get("observation_status")),
                },
                "so_what": sanitize_citation_tokens(s(insight.get("so_what"))),
                "now_what": sanitize_citation_tokens(s(insight.get("now_what"))),
            }
        )
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
        "claim_evidence_map": summary.get("claim_evidence_map")
        if isinstance(summary, dict)
        else [],
    }
    title_is_canonical = _matches_canonical_doc_map_identity(
        request.report.title, request.evidence_packs.get("doc_map"), field="title"
    )
    publisher_is_canonical = _matches_canonical_doc_map_identity(
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
        report_title=("" if title_is_canonical else request.report.title),
        publisher=("" if publisher_is_canonical else request.report.publisher),
        insights=insights,
        summary=summary_clean,
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
    if not public_key or not isinstance(doc_map, dict):
        return False
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
        return False
    canonical_value = values[0]
    if field == "title" and is_generic_report_title(canonical_value):
        return False
    return public_key == next(iter(canonical_keys))


def _identity_match_key(value: object) -> str:
    """Apply the punctuation/casing normalization used by source title matching."""
    return re.sub(r"[^a-z0-9]", "", s(value).casefold())


def _public_factual_items(
    *,
    artifacts: dict,
    evidence_packs: dict,
    report_title: str,
    publisher: str,
    insights: Sequence[dict],
    summary: dict[str, Any],
) -> List[dict]:
    """Material public claims with their exact retained evidence payloads."""
    items: List[dict] = []
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
            item = {
                "item_id": item_id,
                "section": section,
                "text": claim,
                "evidence_ids": [value for value in evidence_ids if value],
                "retained_evidence": s(evidence_text),
            }
            if declared_classification:
                item["declared_classification"] = declared_classification
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
                provenance_evidence = [
                    s(span.get("text"))
                    for span in claim.source_spans
                    if s(span.get("evidence_id")) in claim.evidence_ids
                    and s(span.get("text"))
                ]
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
    evidence_text = "\n".join(s(entry.get("evidence")) for entry in summary_evidence)
    summary_evidence_by_id = {
        s(entry.get("evidence_id")): s(entry.get("evidence"))
        for entry in summary_evidence
    }
    for field_name in ("tldr", "card_tldr_compact", "executive_summary"):
        add_soft_copy_sentences(
            "summary",
            field_name,
            summary.get(field_name),
            evidence_ids,
            evidence_text,
            summary_evidence_by_id,
        )
    insight_evidence = {
        s(insight.get("evidence_id")): s(insight.get("evidence"))
        for insight in insights
    }
    evidence_spans = artifact_evidence_span_index(
        doc_map=ensure_dict(evidence_packs.get("doc_map")),
        evidence_packs=evidence_packs,
    )

    def evidence_text_for_id(evidence_id: str) -> str:
        spans = evidence_spans.get(evidence_id.casefold(), [])
        for source_pack in ("findings", "doc_map"):
            texts = list(
                dict.fromkeys(
                    s(span.get("text"))
                    for span in spans
                    if s(span.get("source_pack")) == source_pack and s(span.get("text"))
                )
            )
            if texts:
                return "\n".join(texts)
        return insight_evidence.get(evidence_id, "")

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
                insight.get("evidence"),
                declared_classification,
            )
    for index, figure in enumerate(artifacts.get("key_figures", []), start=1):
        if not isinstance(figure, dict):
            continue
        evidence_id = s(figure.get("evidence_id"))
        add(
            f"key_figure:{index}:figure",
            f"key_figures:{index}.figure",
            metric_claim_text(figure),
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
    for family in ("expert_comment", "linkedin_post"):
        add_soft_copy_sentences(
            family,
            family,
            artifacts.get(family),
            list(insight_evidence),
            "\n".join(insight_evidence.values()),
            insight_evidence,
        )
    add("metadata:title", "metadata.title", report_title)
    add("metadata:publisher", "metadata.publisher", publisher)
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
        if (
            classification in {
                "analyst_interpretation",
                "prescriptive_recommendation",
            }
            and section_policy_value in {"soft", "mixed"}
        ):
            return "info"
        return "warning"
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
