# A21 First-Attempt Reliability Blockers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the frozen-cohort report queue reach durable `awaiting_review` on a clean deterministic fixture while preserving canonical identity, truthful regeneration provenance, grounding-safe editorial repair, and the existing A21 semantics.

**Architecture:** Keep the current queue/outbox, validation manifest, checkpoints, prompt-family materialisation, publication-readiness record, and `validation_reliability_service` as the only state and measurement surfaces. Propagate report-bound `RunContext` identity through the existing context chain, enrich regenerated artifact cache provenance with the same prompt-bundle identity format used by primary artifact generation, and route soft-copy repair from retained evidence deterministically.

**Tech Stack:** Python 3, frozen dataclass contracts, SQLite report/state stores, existing fake OpenAI boundary, pytest.

## Global Constraints

- Do not change validation rules, A21 success semantics, retry bounds, queue graph, telemetry systems, or database schema unless a current contract proves it necessary.
- Use the existing queue handlers, worker, outbox materialiser, checkpoints, validation manifest, publication-readiness service, prompt service, and reliability builder.
- Mock only OpenAI and other actual external boundaries; retain real orchestrators, storage services, queue records, manifest records, and checkpoints.
- For a frozen validation cohort, canonical `source_identity_id` and `publisher_id` must never be replaced by an MD5, file ID, display name, or sentinel.
- Do not use quarantined evidence in a repair package. Keep deterministic evidence selection bounded; abstain when retained support is insufficient.
- Update `docs/workflows/report-processing.md` and `docs/workflows/validation-and-regeneration.md` with the supported behavior in the same change set.

---

### Task 1: Preserve admitted identity through every report-generation child context and manifest record

**Files:**
- Modify: `src/orchestrators/report_analysis_orchestrator.py:135-137, 386-400, 422-1229`
- Modify: `src/generators/pdf_text_ocr_generator.py:41-49`
- Modify: `src/generators/figure_caption_generator.py:324-332`
- Modify: `src/orchestrators/_report_generation_orchestrator/workflow.py:85-87, render manifest setup`
- Test: `tests/test_validation_run_manifest.py`
- Test: `tests/test_figure_caption_generator.py`
- Test: `tests/test_openai_ocr_service.py`
- Test: `tests/test_report_analysis_orchestrator_decomposition.py`

**Interfaces:**
- Consumes: `RunContext.source_identity_id`, `RunContext.publisher_id`, runtime MD5, and runtime publisher display name.
- Produces: canonical identity on all report-analysis/manifest rows and descendant OCR, caption, regeneration, render, and readiness contexts.

- [ ] **Step 1: Write failing manifest and child-context tests**

```python
ctx = replace(_ctx(), validation_run_id="validation-1", cohort_id="cohort-1",
              source_identity_id="source:canonical", publisher_id="publisher:stable")
# Run the real analysis-stage recorder and inspect SQLite manifest rows.
assert {row.source_identity_id for row in rows} == {"source:canonical"}
assert {row.publisher_id for row in rows} == {"publisher:stable"}
assert "source-md5" not in {row.source_identity_id for row in rows}
assert "Industry Analytics Summit" not in {row.publisher_id for row in rows}
```

```python
assert ocr_request_ctx.source_identity_id == "source:canonical"
assert caption_request_ctx.publisher_id == "publisher:stable"
```

Name the break these catch: an inherited frozen-cohort ID is overwritten by `runtime.md5` or `runtime.publisher_name`.

- [ ] **Step 2: Run the new tests and confirm red**

Run: `python -m pytest -q tests/test_validation_run_manifest.py tests/test_figure_caption_generator.py tests/test_openai_ocr_service.py tests/test_report_analysis_orchestrator_decomposition.py`

Expected: failure showing an MD5/display name or fallback identity in a descendant context or manifest row.

- [ ] **Step 3: Implement the smallest identity-preserving correction**

Keep the existing `_analysis_source_identity_id(ctx, fallback)` and `_manifest_source_identity_id(ctx, fallback)` precedence. Add the equivalent local expression only where a context is currently overwritten:

```python
source_identity_id=(str(runtime.ctx.source_identity_id or "").strip()
                    or runtime.md5 or runtime.file.file_id)
publisher_id=(str(runtime.ctx.publisher_id or "").strip()
              or runtime.publisher_name or "unattributed")
```

Pass the resolved canonical source ID to every `record_validation_analysis_stage` call. Retain fallback behavior only for an unbound, non-cohort context. Do not alter `validation_manifest_cohort_member_conflict` handling.

- [ ] **Step 4: Run the focused identity tests and inspect resulting manifest IDs**

Run: `python -m pytest -q tests/test_validation_run_manifest.py tests/test_figure_caption_generator.py tests/test_openai_ocr_service.py tests/test_report_analysis_orchestrator_decomposition.py`

Expected: all selected tests pass; every frozen-cohort row contains `source:canonical` and `publisher:stable` despite deliberately different MD5 and publisher display name values.

### Task 2: Add the real deterministic frozen-cohort queue-to-A21 integration coverage

**Files:**
- Modify: `tests/test_validation_queue_lineage.py`
- Modify only if the test exposes a production handoff defect: `src/orchestrators/_workflow_queue_handlers/report_pipeline.py`
- Test: `tests/test_validation_reliability_service.py`

**Interfaces:**
- Consumes: one real `FrozenValidationCohortQueueSubmissionRequest`, fake external model responses, and isolated report/state/usage SQLite files.
- Produces: a durable queue/readiness chain ending at `awaiting_review`, matching manifest lineage, and deterministic A21 bytes/hash.

- [ ] **Step 1: Extend the current frozen-cohort test with its failing end-to-end assertions**

```python
for queue_name in (
    "source_ingest", "report_selection", "report_analysis",
    "report_render", "publication_readiness",
):
    result = run_workflow_worker_once(state_db, queue_name, "a21-test-worker", _ctx())
    assert result.terminal_status == "succeeded"
    materialize_workflow_outbox(state_db, "a21-test-worker", _ctx())

artifact_one = build_validation_reliability_artifact(request, _ctx())
artifact_two = build_validation_reliability_artifact(request, _ctx())
entity = artifact_one.first_attempt_entities[0]
assert (entity.first_pass, entity.eventual_success, entity.operator_intervention) == (True, True, False)
assert canonical_json_bytes(artifact_one) == canonical_json_bytes(artifact_two)
assert artifact_one.artifact_hash == artifact_two.artifact_hash
```

Also assert the real queue jobs, validation-manifest records, durable readiness record, and report package carry one `validation_run_id`, `cohort_id`, `root_workflow_id`, immutable `report_id`, canonical source/publisher IDs, and one package checksum.

Name the break this catches: a queue handoff or child context breaks canonical lineage before durable readiness while unit-level queue tests still stop at `report_analysis`.

- [ ] **Step 2: Run the integration test and confirm red**

Run: `python -m pytest -q tests/test_validation_queue_lineage.py::test_frozen_validation_queue_submission_binds_manifest_to_generated_queue_root`

Expected: failure before `awaiting_review` caused by one of the identity/provenance/repair defects, rather than an assertion-only failure.

- [ ] **Step 3: Make only the exposed production handoff corrections**

Retain `_stage_child_submission` and `_report_publication_readiness_submission` as the canonical queue mechanism. If a frozen payload already has admission identity, use it; otherwise retain current admission fallback. Ensure the `RunContext` supplied to pipeline stages has the job's canonical IDs before descendants are created, and do not add a second workflow route.

- [ ] **Step 4: Run the full-chain test twice and retain deterministic evidence**

Run: `python -m pytest -q tests/test_validation_queue_lineage.py tests/test_workflow_queue_registry.py tests/test_workflow_queue_decomposition.py tests/test_validation_reliability_service.py`

Expected: the clean fixture reaches durable `awaiting_review`, A21 reports first-pass/eventual success, and the two in-test builds have byte-identical canonical serialization and hash.

### Task 3: Record actual regeneration prompt identity and reject stale regenerated checkpoints

**Files:**
- Modify: `src/generators/report_regeneration_generator.py:240-295, 812-833`
- Modify: `src/generators/_artifact_generator/rendering.py:59-236` only if it needs to expose the already-prepared prompt bundle to its existing caller
- Modify: `src/orchestrators/_report_generation_orchestrator/resume.py:653-690`
- Modify: `src/orchestrators/_report_generation_orchestrator/checkpoints.py:671-770` only for the existing family materialisation reader
- Test: `tests/test_report_regeneration_generator.py`
- Test: `tests/test_report_checkpoint_lineage_validation.py`
- Test: `tests/test_prompt_preparation.py`

**Interfaces:**
- Consumes: the primary artifact `_cache.prompts` format and `prepare_prompt_bundle` / `PreparedPromptBundle` identities.
- Produces: an artifact cache retaining prior primary-family identity for unchanged output and actual `report_vs/artifacts/regenerate/...` identity for replacement output.

- [ ] **Step 1: Write failing provenance and resume tests**

```python
candidate = regenerate_artifacts(request_for("expert_comment", "summary"), ctx)
prompts = candidate.updated_artifacts["_cache"]["prompts"]
assert prompts["report_vs/artifacts/summary"] == prior_primary_summary_identity
assert prompts["report_vs/artifacts/regenerate/expert_comment"]["prompt_content_hash"] == regeneration_hash

with pytest.raises(AppError, match="prompt identity"):
    _validate_checkpoint_artifact_prompt_identities(runtime, stale_candidate_checkpoint, path)
```

Cover `summary`, `expert_comment`, and `linkedin_post`; mutate a regeneration prompt fixture to prove stale replacement provenance is rejected; retain a valid candidate checkpoint and prove normal resume accepts it.

Name the break these catch: replacement content can be promoted while `_cache.prompts` falsely claims it was generated by the old primary prompt.

- [ ] **Step 2: Run the new tests and confirm red**

Run: `python -m pytest -q tests/test_report_regeneration_generator.py tests/test_report_checkpoint_lineage_validation.py tests/test_prompt_preparation.py`

Expected: regenerated artifacts retain only the copied primary cache and checkpoint validation accepts an identity that does not describe the replacement prompt.

- [ ] **Step 3: Use canonical prompt preparation to merge per-family replacement identity**

For each `_render_regeneration_model` execution, prepare the existing prompt bundle once, call `render_artifact_json_model(..., prepared_prompt_bundle=prepared)`, and persist a cache entry derived from that same bundle:

```python
prompts[namespace] = {
    "prompt_system_sha256": prepared.prompt_set.system.sha256,
    "prompt_user_sha256": prepared.prompt_set.user.sha256,
    "prompt_content_hash": prepared.prompt_content_hash,
    "dependency_manifest": asdict(prepared.dependency_manifest),
    "execution_identity": prepared.execution_identity.execution_identity,
    "execution_identity_manifest": asdict(prepared.execution_identity),
    "model": prepared.resolved_model,
    "execution_policy_hash": prepared.execution_policy.policy_hash,
    "execution_policy_source": prepared.execution_policy.policy_source,
}
```

Keep every untouched entry byte-for-byte as its prior identity. Extend the existing resume validation to require the regeneration namespace for a regenerated family and validate its current content hash; do not introduce a parallel provenance schema.

- [ ] **Step 4: Run provenance, checkpoint, and artifact-family regression suites**

Run: `python -m pytest -q tests/test_report_regeneration_generator.py tests/test_report_checkpoint_lineage_validation.py tests/test_prompt_preparation.py tests/test_prompt_family_materialization.py tests/test_prompt_family_minimal_execution.py`

Expected: unchanged families retain their original identity, each regenerated family retains its matching regeneration identity, copied stale cache fails, changed regeneration prompt invalidates reuse, and valid checkpoint resume succeeds.

### Task 4: Align supported editorial repair instructions and soft-copy evidence routing

**Files:**
- Modify: applicable primary and regeneration prompt resources under `src/prompts/report_vs/artifacts/`
- Modify: `src/orchestrators/_report_analysis_orchestrator/regeneration_plan.py:130-236`
- Modify: `src/generators/report_regeneration_generator.py:375-480`
- Test: `tests/test_report_regeneration_generator.py`
- Test: `tests/test_report_analysis_category_repair.py`
- Test: `tests/test_public_editorial_quality_generator.py`
- Test: `tests/test_public_report_quality_gate.py`
- Test: `tests/test_prompt_fixture_corpus_regression.py`

**Interfaces:**
- Consumes: validation issue text/section, retained claim-evidence mappings, editorial-plan themes, findings, quotes, metrics, and quarantined IDs.
- Produces: bounded deterministic grounding packages for soft sections and prompt instructions that permit interpretation/advice only when it adds no unsupported factual premise.

- [ ] **Step 1: Write failing behavioral fixtures**

```python
plan = _build_regeneration_plan(
    validation_report_with_issue("expert_comment", evidence_ids=[]), artifacts
)
candidate = regenerate_artifacts(request_with(plan, retained_evidence), _ctx())
assert candidate.prompt_grounding["expert_comment"]["evidence_ids"] == ["finding-2"]
assert "quarantined-1" not in candidate.prompt_grounding["expert_comment"]["evidence_ids"]
assert validate_public_editorial(unsupported_prediction_fixture).status == "fail"
assert validate_public_editorial(supported_conditional_advice_fixture).status == "pass"
```

Name the breaks these catch: an empty issue evidence list creates an empty repair package despite relevant retained evidence, or a prompt introduces prediction/causality/benefit/source attribution absent from evidence.

- [ ] **Step 2: Run the fixtures and confirm red**

Run: `python -m pytest -q tests/test_report_regeneration_generator.py tests/test_report_analysis_category_repair.py tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py tests/test_prompt_fixture_corpus_regression.py`

Expected: soft-copy repair has no selected retained support and IAS-style public-copy fixtures expose the primary/regeneration instruction mismatch.

- [ ] **Step 3: Add deterministic soft-section grounding fallback and constrained prompt language**

Extend `_issue_grounding` to resolve `expert_comment` and `linkedin_post` using, in order: directly linked claim evidence, matching insight/theme evidence, then a stable bounded ranking of retained findings/quotes/metrics. In `_build_grounding_package`, always exclude `excluded_evidence_ids`, use only the first bounded deterministic entries, and leave the section eligible for formal abstention when no support remains.

Update both primary and `regenerate/` prompt resources to require descriptive factual clauses when the evidence is descriptive; allow labelled analyst interpretation or conditional advice only when it is traceable to retained support and adds no new factual premise, prediction, causal outcome, certainty, operational/financial benefit, metric, or source attribution. Do not modify validators.

- [ ] **Step 4: Run LLM/editorial deterministic evaluation and IAS retained fixture**

Run: `python -m pytest -q tests/test_report_regeneration_generator.py tests/test_report_analysis_category_repair.py tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py tests/test_prompt_service.py tests/test_prompt_dry_run_validation.py tests/test_prompt_fixture_corpus_regression.py`

Then run the repository's retained IAS fixture through analysis, validation, and bounded regeneration using its isolated fake/provider-safe profile. Record the before/after failure codes and any remaining failures without changing validation policy.

### Task 5: Document the corrected contract and run proportionate repository gates

**Files:**
- Modify: `docs/workflows/report-processing.md`
- Modify: `docs/workflows/validation-and-regeneration.md`
- Modify: `docs/quality/evidence.md` only for A21 retained-artifact evidence semantics

- [ ] **Step 1: Document current behavior**

State that frozen-cohort report identity is immutable through queue, analysis, render, and readiness; regenerated families retain the actual regeneration prompt identity while unchanged families retain theirs; and soft-copy repairs use bounded, deterministic, non-quarantined retained evidence or abstain.

- [ ] **Step 2: Run focused checks and static gates**

Run: `python -m pytest -q tests/test_validation_queue_lineage.py tests/test_workflow_queue_registry.py tests/test_report_analysis_orchestrator_decomposition.py tests/test_openai_ocr_service.py tests/test_figure_caption_generator.py tests/test_validation_run_manifest.py tests/test_report_checkpoint_lineage_validation.py tests/test_report_regeneration_generator.py tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py tests/test_validation_reliability_service.py`

Run the repository-configured schema, type, lint, architecture, dependency, and documentation gates from `docs/quality/release-gates.md`; do not weaken a gate or baseline.

- [ ] **Step 3: Perform required deterministic repeat evidence**

Run the full-chain frozen A21 test twice from isolated retained state and retain the two serialized artifact hashes/byte comparison. Run the retained IAS analysis/validation/regeneration fixture and record its final issue codes.

- [ ] **Step 4: Preserve the live/benchmark completion boundary**

Only after deterministic A21 and retained IAS evidence pass, run one explicitly opted-in, bounded live IAS canary if credentials and operator authority are available. Do not start the twenty-report benchmark. Do not mark A21 complete: closure still requires the governed representative benchmark plus authenticated publication/readback/replay validation.
