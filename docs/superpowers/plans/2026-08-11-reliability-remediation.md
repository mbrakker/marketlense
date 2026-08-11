# Reliability Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a fresh immutable 20-report run produce trustworthy per-report funnel metrics, preserve resolved source attribution, and remove the four observed report-card/artifact blockers without weakening publication safeguards.

**Architecture:** Keep the immutable validation manifest as the source of truth. The evidence exporter will distinguish a final, deduplicated cohort funnel from raw attempt telemetry; admission identity will be propagated through ingest rather than replaced by an `unattributed` fallback; deterministic artifact/card checks will repair only when retained grounded data supports the repair. Publishing remains all-or-nothing at the cohort gate.

**Tech Stack:** Python 3.12, SQLite, typed dataclass contracts, YAML cover configuration, pytest, existing isolated validation-run workflow.

## Global Constraints

- Do not lower the cohort success threshold, replace frozen cohort members, enable `--success-target`, or publish a partial cohort.
- Preserve complete public titles and grounded source claims; do not truncate, invent insights, or treat a failed readiness rule as a success.
- Treat model output as untrusted: every deterministic fallback must be derived from already schema-valid, evidence-linked retained artifacts.
- Keep raw retry/attempt events, but never label them as member conversion rates.
- Retain the source-identity admission requirement; an unresolved publisher must be rejected before cohort freeze, not silently relabelled.
- Use `.env` only for credentials and do not commit run outputs, provider payloads, or secrets.
- Update the workflow and WordPress/card documentation selected by `docs/README.md` in the same changeset.

---

### Task 1: Export a truthful final-member funnel and separately retain raw attempt telemetry

**Files:**
- Modify: `scripts/quality/export_reliability_run_evidence.py:38-331`
- Modify: `tests/test_export_reliability_run_evidence.py:10-77`
- Modify: `docs/workflows/validation-and-regeneration.md` (Reliability telemetry and usage attribution)

**Interfaces:**
- Consumes: `validation_run_cohort_members`, `validation_run_entity_attempts`, `validation_run_stage_records`, and `llm_usage_events` for one `validation_run_id`.
- Produces: `stage_conversion_metrics.csv` and `aggregate_funnel.json` with at most one final outcome per `(report_id, stage)`; `stage_attempt_metrics.csv` for every retained attempt event; run-scoped `cost_by_stage.csv` and `cost_by_report.csv`.

- [ ] **Step 1: Write a failing exporter test with two reports, a superseded attempt, and a retry.**

```python
def test_export_deduplicates_current_member_stage_outcomes_and_scopes_usage(
    tmp_path: Path,
) -> None:
    # Insert r1/current with discovery succeeded twice then ingestion publish_ready;
    # insert r1/old with a failed acquisition; insert r2/current with ingestion failure.
    export_run_evidence(
        state_dir=state_dir,
        artifact_dir=artifact_dir,
        output_dir=output_dir,
        validation_run_id="validation:test",
    )
    funnel = json.loads((output_dir / "aggregate_funnel.json").read_text())
    assert funnel["terminal_outcomes"] == {"permanent_failure": 1, "publish_ready": 1}
    assert max(row["count"] for row in funnel["stage_outcomes"]) <= 2
    assert (output_dir / "stage_attempt_metrics.csv").is_file()
    assert list(csv.DictReader((output_dir / "cost_by_report.csv").open())) == [
        {"report_id": "r1", "estimated_cost_usd": "0.120000", "status": "attributed"},
        {"report_id": "r2", "estimated_cost_usd": "0.030000", "status": "attributed"},
    ]
```

- [ ] **Step 2: Run the focused test to confirm the current raw-counter implementation fails.**

Run: `pytest tests/test_export_reliability_run_evidence.py::test_export_deduplicates_current_member_stage_outcomes_and_scopes_usage -v`

Expected: FAIL because `stage_conversion_metrics.csv` counts all stage records (including retries/superseded attempts), and usage is not filtered by validation run.

- [ ] **Step 3: Join stage rows to the current entity attempt and select the latest record per report and stage.**

```python
stage_rows = _rows(
    conn,
    """
    SELECT attempts.report_id, stages.attempt_id, stages.stage,
           stages.terminal_outcome, stages.failure_code, stages.retryable,
           stages.repair_disposition, stages.idempotency_state,
           stages.started_at_utc, stages.completed_at_utc
    FROM validation_run_stage_records AS stages
    JOIN validation_run_entity_attempts AS attempts
      ON attempts.attempt_id = stages.attempt_id
    WHERE stages.validation_run_id=? AND attempts.is_current=1
    ORDER BY attempts.report_id, stages.stage,
             stages.completed_at_utc DESC, stages.started_at_utc DESC
    """,
    (validation_run_id,),
)
final_stage_rows = _latest_stage_row_by_report_and_stage(stage_rows)
```

Implement `_latest_stage_row_by_report_and_stage(rows: list[dict[str, Any]]) -> list[dict[str, Any]]` using a `(report_id, stage)` key and the already-descending query order. Build `stage_conversion_metrics.csv` only from `final_stage_rows`; write the untouched `stage_rows` aggregate to `stage_attempt_metrics.csv` with fields `stage`, `outcome`, `attempt_event_count`, and `cohort_size`.

- [ ] **Step 4: Scope and attribute usage costs to this exact run.**

```python
usage_rows = _rows(
    usage_conn,
    """
    SELECT report_id, stage, action, semantic_task, prompt_namespace, provider,
           model, input_tokens, output_tokens, estimated_cost_usd
    FROM llm_usage_events
    WHERE validation_run_id=?
    ORDER BY report_id, timestamp_utc, id
    """,
    (validation_run_id,),
)
```

Aggregate `cost_by_stage.csv` by the retained `stage` field, aggregate `cost_by_report.csv` by `report_id`, and emit `status="attributed"` for every cohort member with a numeric total (including `0.000000`). Emit a `retention_gap` row only when a ledger schema lacks `report_id`; do not use it for a normal zero-cost member.

- [ ] **Step 5: Run focused exporter tests and document the two metrics views.**

Run: `pytest tests/test_export_reliability_run_evidence.py -v`

Expected: PASS; final-funnel counts never exceed cohort size, raw attempt counts remain auditable, and no other validation run contributes cost.

- [ ] **Step 6: Commit the isolated telemetry correction.**

```bash
git add scripts/quality/export_reliability_run_evidence.py tests/test_export_reliability_run_evidence.py docs/workflows/validation-and-regeneration.md
git commit -m "fix: deduplicate reliability funnel evidence"
```

### Task 2: Preserve resolved publisher identity from admission through the immutable cohort ledger

**Files:**
- Modify: `src/orchestrators/ingest_orchestrator.py:470-525, 1100-1500, 1940-1960`
- Modify: `src/orchestrators/report_pipeline_orchestrator.py:480-510`
- Test: `tests/test_ingest_cohort.py`
- Test: `tests/test_admission_preflight_orchestrator.py`
- Modify: `docs/workflows/report-processing.md` (admission and cohort-freeze sections)

**Interfaces:**
- Consumes: `AdmissionPreflightDecision.publisher_id` and `source_identity_id` for an admitted report.
- Produces: matching non-empty publisher/source identifiers in `validation_run_cohort_members`, entity attempts, run context, and usage attribution for every admitted report.

- [ ] **Step 1: Add a failing cohort test for identity propagation.**

```python
def test_frozen_cohort_preserves_admission_identity_in_manifest_and_attempts(
    ingest_settings, run_context
) -> None:
    admission = run_admission_preflight(
        _request(ingest_settings), run_context, dependencies=_resolved_identity_dependencies()
    )
    result = _run_immutable_cohort(
        settings=ingest_settings, run_context=run_context, admissions=[admission]
    )
    members = _read_cohort_members(ingest_settings.reports_db, result.validation_run_id)
    assert [(row.publisher_id, row.source_identity_id) for row in members] == [
        ("Acme Research", "source:acme-2026")
    ]
```

- [ ] **Step 2: Run the focused test and confirm the fallback loses identity.**

Run: `pytest tests/test_ingest_cohort.py -k preserves_admission_identity -v`

Expected: FAIL because one cohort/attempt construction path writes `unattributed` or `drive_unattributed` after a valid admission decision.

- [ ] **Step 3: Thread the admission decision as the single identity source.**

Replace only the literals on the frozen-cohort path with values already carried by the admission decision:

```python
publisher_id = admission.decision.publisher_id.strip()
source_identity_id = admission.decision.source_identity_id.strip()
if not publisher_id or not source_identity_id:
    raise AppError(
        code="validation_cohort_identity_missing",
        message="Frozen cohort members require resolved admission identity",
        retryable=False,
    )
```

Pass these values through `report_pipeline_orchestrator` into the manifest/usage context. Keep `missing_source_identity` at admission; do not add a fallback or a later repair path for unresolved members.

- [ ] **Step 4: Add a regression assertion that unresolved identity cannot enter a frozen cohort.**

```python
assert result.admitted is False
assert result.decision.outcome == "missing_source_identity"
with pytest.raises(AppError, match="validation_cohort_identity_missing"):
    _freeze_member(
        publisher_id="",
        source_identity_id="source:x",
        report_id="drive-x",
    )
```

- [ ] **Step 5: Run admission/cohort tests and commit.**

Run: `pytest tests/test_admission_preflight_orchestrator.py tests/test_ingest_cohort.py -v`

Expected: PASS; a resolved publisher persists unchanged and unresolved sources cannot be frozen.

```bash
git add src/orchestrators/ingest_orchestrator.py src/orchestrators/report_pipeline_orchestrator.py tests/test_ingest_cohort.py tests/test_admission_preflight_orchestrator.py docs/workflows/report-processing.md
git commit -m "fix: preserve admitted source identity in cohorts"
```

### Task 3: Recover card insights and candidate artifacts only from retained grounded evidence

**Files:**
- Modify: `src/generators/_artifact_generator/generation.py:317-460`
- Modify: `src/generators/report_card_projection.py:244-262`
- Modify: `src/generators/report_render_generator.py:760-805`
- Test: `tests/_test_report_analysis_generator/cases_01_polls_vector_store_status_until.py`
- Test: `tests/test_report_card_projection.py`
- Modify: `docs/workflows/validation-and-regeneration.md` (Grounding-safe candidate regeneration)

**Interfaces:**
- Consumes: normalized, evidence-linked `insights_candidates` and `insights_final` artifact data.
- Produces: exactly two card insights when at least two retained grounded candidates exist; otherwise the current typed readiness failure remains.

- [ ] **Step 1: Write failing tests for the two observed artifact conditions.**

```python
def test_candidates_fall_back_to_retained_findings_when_model_payload_is_empty(
    artifact_dependencies, run_context
) -> None:
    artifacts = _generate_artifacts_with_candidates(
        dependencies=artifact_dependencies,
        ctx=run_context,
        model_candidates={"insights_candidates": []},
    )
    assert len(artifacts["insights_candidates"]) >= 5
    assert all(item["evidence_id"] for item in artifacts["insights_candidates"])

def test_manifest_uses_two_grounded_candidates_when_final_insights_are_missing():
    manifest = build_report_card_manifest(_manifest_request(
        insights_final=(),
        insights_candidates=(_candidate("One", "ev-1"), _candidate("Two", "ev-2")),
    ))
    assert manifest.key_insights == ("One", "Two")
```

- [ ] **Step 2: Run the targeted tests to establish the current failure.**

Run: `pytest tests/_test_report_analysis_generator/cases_01_polls_vector_store_status_until.py -k candidates tests/test_report_card_projection.py -k insights -v`

Expected: FAIL for an empty model candidate payload with valid findings, and for a card request with grounded candidates but no final-insight list.

- [ ] **Step 3: Add a deterministic, fail-closed card-insight projection.**

```python
def _card_insights_from_grounded_items(items: Sequence[Mapping[str, object]]) -> tuple[str, str]:
    values = tuple(
        " ".join(str(item.get("text") or "").split())
        for item in items
        if str(item.get("evidence_id") or "").strip()
        and str(item.get("text") or "").strip()
    )
    if len(values) < 2:
        raise AppError(
            code="card_key_insights_invalid",
            message="Exactly two complete card insights are required",
            retryable=False,
        )
    return values[:2]
```

Use it after existing candidate normalization/fallback, not to manufacture content. Extend `ReportCardManifestRequest` only if it does not already receive candidates at this boundary; pass normalized candidates from `report_render_generator`. Do not select an item lacking an evidence ID.

- [ ] **Step 4: Keep failed model artifacts observable and route repair narrowly.**

When a candidate model artifact is schema-invalid but grounded findings supply the minimum candidate set, retain the model failure in the regeneration audit and use the deterministic projection as card input. When fewer than two evidence-linked items exist, preserve `insights_candidates`/`card_key_insights_invalid` and do not call broad regeneration.

- [ ] **Step 5: Run tests and commit.**

Run: `pytest tests/_test_report_analysis_generator/cases_01_polls_vector_store_status_until.py tests/test_report_card_projection.py -v`

Expected: PASS; valid retained evidence recovers the card while insufficient evidence still fails closed.

```bash
git add src/generators/_artifact_generator/generation.py src/generators/report_card_projection.py src/generators/report_render_generator.py tests/_test_report_analysis_generator/cases_01_polls_vector_store_status_until.py tests/test_report_card_projection.py docs/workflows/validation-and-regeneration.md
git commit -m "fix: derive card insights from grounded artifacts"
```

### Task 4: Expand approved complete-title capacity and cover fit without clipping

**Files:**
- Modify: `src/generators/report_card_projection.py:112-151`
- Modify: `src/config/cover-styles.yaml`
- Modify: `src/services/cover_image_service.py:99-149`
- Test: `tests/test_report_card_projection.py`
- Test: `tests/integration/test_cover_image_service.py`
- Modify: `README_WORDPRESS.md` (report-card presentation contract)

**Interfaces:**
- Consumes: normalized canonical report title and approved small/medium/large cover layout.
- Produces: a measured title scale and three complete, non-clipped cover assets for titles seen in the failed cohort; an impossible title still returns its typed overflow error.

- [ ] **Step 1: Add stress fixtures for the two failed full titles and the medium-cover failure.**

```python
LONG_RELIABILITY_TITLE = (
    "A complete reliability title representative of the two 11 August card "
    "overflow reports, preserved without ellipsis or truncation"
)

def test_select_title_scale_accepts_reliability_stress_title():
    assert select_title_scale(LONG_RELIABILITY_TITLE) == "xxlong"
```

Add an integration test that renders this exact title at small, medium, and large size and asserts each output file exists.

- [ ] **Step 2: Run the stress tests and confirm the current constraints reject the title.**

Run: `pytest tests/test_report_card_projection.py -k reliability_stress tests/integration/test_cover_image_service.py -k reliability_stress -v`

Expected: FAIL with `card_title_overflow` and/or `cover_title_overflow`.

- [ ] **Step 3: Add one approved `xxlong` scale and matching fit budget.**

Change the scale bands only enough to admit the stress title, returning `"xxlong"` above the existing `xlong` band. Increase the medium title rectangle or lower its approved minimum font only by the measured amount that lets the complete stress title fit. Do not use clipping, `line-clamp`, ellipsis, a hidden-overflow style, or a shortened display title.

```python
if count <= 140:
    return "xlong"
if count <= _MAX_XXLONG_CARD_TITLE_CHARACTERS:
    return "xxlong"
raise AppError(
    code="card_title_overflow",
    message="Complete report title does not fit the approved card title scale",
    retryable=False,
)
```

Keep the existing impossible-title test and add one title beyond the new maximum; it must still raise `card_title_overflow`.

- [ ] **Step 4: Verify all cover variants and the WordPress projection.**

Run: `pytest tests/test_report_card_projection.py tests/integration/test_cover_image_service.py tests/_test_publish_generator/cases_04_report_cards.py -v`

Expected: PASS; small, medium, and large output files exist for the stress title, title scale is `xxlong`, and publication payload preserves the exact title.

- [ ] **Step 5: Commit the measured capacity correction.**

```bash
git add src/generators/report_card_projection.py src/config/cover-styles.yaml src/services/cover_image_service.py tests/test_report_card_projection.py tests/integration/test_cover_image_service.py README_WORDPRESS.md
git commit -m "fix: support complete long report card titles"
```

### Task 5: Validate the remediation against a new isolated immutable 20-report run

**Files:**
- Create: `src/config/app.reliability_full_YYYYMMDD_<uuid>.yaml`
- Create: `docs/CTO_evidence/reliability_full_YYYYMMDD_<uuid>/`
- Create: `docs/releases/YYYY-MM-DD-20-report-reliability-remediation.md`
- Modify: `docs/quality/evidence.md` only if the evidence schema/collector changes in Task 1

**Interfaces:**
- Consumes: a fresh 20-member admitted cohort, the corrected exporter, current validation/recovery flow, and the canonical publisher.
- Produces: a new run-scoped evidence pack with reconciled final funnel, raw attempts, source attribution, cost attribution, terminal outcomes, publication decision, and release record.

- [ ] **Step 1: Run focused regression suites before external work.**

Run: `pytest tests/test_export_reliability_run_evidence.py tests/test_admission_preflight_orchestrator.py tests/test_ingest_cohort.py tests/test_report_card_projection.py tests/integration/test_cover_image_service.py tests/_test_publish_generator/cases_04_report_cards.py -v`

Expected: PASS.

- [ ] **Step 2: Create a unique isolated run profile and verify all run-owned paths.**

```powershell
$run = "reliability_full_$(Get-Date -Format yyyyMMdd)_$([guid]::NewGuid().ToString('N'))"
Copy-Item src/config/app.yaml "src/config/app.$run.yaml"
# Update only output/cache/state/usage/log paths to this namespace before running.
```

Confirm every output, cache, state, ledger, log, and evidence path is under the new namespace; retain the profile and provenance without secret values.

- [ ] **Step 3: Discover, acquire, admit, and freeze exactly 20 reports.**

Run the approved isolated commands from `docs/workflows/report-processing.md`. Before expensive processing, assert every frozen member has a resolved source identity and a publisher ID that is neither empty, `unattributed`, nor `drive_unattributed`. Reject nonconforming candidates before freeze; never replace a member afterwards.

- [ ] **Step 4: Execute ingest and bounded recovery, then export evidence.**

For each typed failure, use the existing narrow checkpoint/regeneration path. Run:

```powershell
python scripts/quality/export_reliability_run_evidence.py --state-dir state/$run --artifact-dir out/$run --output-dir out/$run/evidence_export --validation-run-id <derived-validation-run-id>
```

Assert `stage_conversion_metrics.csv` never has a count above 20; assert `stage_attempt_metrics.csv` contains all retry events; reconcile `terminal_outcomes.csv` with the immutable cohort manifest; and confirm costs are filtered to the run ID.

- [ ] **Step 5: Publish only if the unchanged cohort gate authorizes it.**

If every required target passes, use the canonical WordPress publisher, require authenticated readback for every member, then perform an unchanged repeat-publication check with zero actual writes. If the gate fails, retain evidence and report typed failures; do not publish successful members alone.

- [ ] **Step 6: Run the repository quality gate, inspect the diff, and commit evidence.**

Run: `python scripts/ci/run_quality_gate.py`

Expected: PASS, or record exact pre-existing/unavailable failures separately. Then run `git diff --check`, inspect for secret/path leakage, update the release record with actual outcomes only, and commit implementation plus evidence intentionally.

## Self-Review

- [ ] Every observed terminal loss maps to a plan task: title overflow and cover fit (Task 4), invalid card insights and schema-invalid candidates (Task 3), and unreliable funnel accounting (Task 1).
- [ ] Discovery/acquisition remain governed by immutable admission; Task 2 fixes observed attribution leakage without admitting unresolved sources.
- [ ] Publication/readback/repeat checks remain conditional on the cohort gate, so this plan cannot convert a failed run into a partial release.
- [ ] The new run proves both final member conversion and raw retry activity, avoiding the current impossible 200% conversion figures.
