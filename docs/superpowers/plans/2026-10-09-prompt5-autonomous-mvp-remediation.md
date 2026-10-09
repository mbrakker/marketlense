# Prompt 5 Autonomous MVP Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the measured frozen-cohort summary and editorial regressions, prove the autonomous publication lifecycle against the user-confirmed WordPress staging site, and merge only after final evidence and CI pass.

**Architecture:** Preserve the existing report, validation, approval, queue, WordPress, Signal, and Briefing boundaries. Fix summary finalization at the artifact boundary with source-backed fallback or explicit abstention, clarify summary-lead intent in its existing prompt, and use isolated state plus existing orchestration for all end-to-end checks.

**Tech Stack:** Python, pytest, YAML prompt resources, SQLite migrations, existing frozen-cohort runner, autonomous supervisor and durable queues, WordPress REST staging gate, GitHub Actions.

## Global Constraints

- Process exactly the five reports in `docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json` and verify their retained source hashes.
- Preserve the historical baseline at `0ec3cdff841e16df7044f6645fe8379a464f41ca`; do not regenerate or mutate it.
- Do not manually approve, repair, or requeue work during the unattended canary; retain diagnostics as separate runs.
- Use only the user-confirmed staging target from `.env`; never publish to production.
- Keep quality primary: do not weaken grounding, validation, readiness, or the Signal human-review restriction; do not cherry-pick successful reruns.
- Isolate state and outputs, bound provider work, and retain redacted evidence without credentials, prompts, provider responses, or source extracts.
- Require green full CI on the final branch SHA before merging.

---

### Task 1: Close the repaired compact-summary validation gap

**Files:**
- Modify: `src/generators/_artifact_generator/storage.py`
- Test: `tests/test_soft_copy_finalization.py`

**Interfaces:**
- Consumes: `assemble_artifacts_payload`, summary claim evidence maps, soft-copy repair metadata, and existing `constrain_summary_to_source_backed_claims` behavior.
- Produces: final repaired summaries whose compact TLDR is either a complete source-backed sentence of at most 18 words or explicitly abstained; existing provenance and card fallback rules remain authoritative.

- [x] Add `test_repaired_summary_with_invalid_compact_tldr_uses_direct_source_claim` to build an artifact through `_assemble_soft_copy` with a repaired summary, one direct evidence claim under 18 words, and an invalid compact field.
- [x] Run `python -m pytest -q tests/test_soft_copy_finalization.py::test_repaired_summary_with_invalid_compact_tldr_uses_direct_source_claim` and confirm it fails because the invalid repair copy bypasses deterministic source-backed reconciliation.
- [x] In `assemble_artifacts_payload`, validate repaired compact copy before preserving the repair-in-progress exemption; run existing direct-claim reconciliation when invalid, and preserve explicit summary abstention if no eligible direct claim exists.
- [x] Rerun the focused test, then `python -m pytest -q tests/test_soft_copy_finalization.py tests/test_report_card_projection.py tests/_test_artifact_generator/cases_01_validates_schema_and_evidence_ids.py`.
- [x] Confirm existing fail-closed tests still reject abstained summaries without a valid retained insight.

### Task 2: Make the summary lead requirement apply to both TLDRs

**Files:**
- Modify: `src/prompts/report_vs/artifacts/summary/user.yaml`
- Verify: prompt fixtures and summary/render output tests.

**Interfaces:**
- Consumes: the existing editorial plan, retained evidence, direct findings, summary schema, and provenance contract.
- Produces: a standard and compact TLDR that lead with the most material executive-relevant supported finding; keep each qualification, cohort, denominator, and period attached to its claim.

- [x] Add `test_summary_prompt_requires_both_tldrs_to_use_the_report_level_lead` in `tests/test_prompt_dry_run_validation.py`; assert the loaded summary prompt explicitly prioritizes the material supported finding for both TLDR fields and rejects section descriptions when stronger findings exist.
- [x] Run `python -m pytest -q tests/test_prompt_dry_run_validation.py::test_summary_prompt_requires_both_tldrs_to_use_the_report_level_lead` and confirm it fails because the current prompt lacks that requirement.
- [x] Clarify that each TLDR is the report-level lead, prioritize a direct quantified finding when present, forbid a section/topic description when a stronger supported finding exists, and retain the existing abstention rule when no short direct claim exists.
- [x] Run `python -m pytest -q tests/test_prompt_service.py tests/test_prompt_dry_run_validation.py tests/test_prompt_fixture_corpus_regression.py tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py`.
- [x] Run `python scripts/ci/check_prompt_fixture_regression.py --baseline docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json --config src/config/app.yaml --iterations 3` and record prompt identity, routing/model, schema, grounding, and output-quality findings.

### Task 3: Prepare an isolated autonomous-MVP preflight environment

**Files:**
- No tracked configuration or credential files; use a private run directory under `tmp/` and the existing SQLite migration/service entrypoints.
- Retain redacted outcomes in `out/` and the comparison report.

**Interfaces:**
- Consumes: `.env` values in process memory, the `autonomous_mvp` profile, and canonical state, reports, Signal-store, and LLM-usage migrations.
- Produces: isolated local and bounded live capability reports with no test-state reuse and no secret values in output.

- [ ] Create fresh isolated state, reports, Signal-store, and LLM-usage databases in the run directory; apply canonical migrations rather than copying user state.
- [ ] Load `.env` values into the test process without copying `.env` into the worktree or printing values; verify only variable presence, target host, and token expiry metadata.
- [ ] Run `python -m src.cli capability-preflight --profile autonomous_mvp` and resolve every local blocker at its documented resource/config boundary.
- [ ] Run `python -m src.cli capability-preflight --profile autonomous_mvp --live`; retain provider-call and external-write counts, and stop if the target or any configured destination differs from the confirmed staging site.

### Task 4: Verify frozen-cohort Signal and Briefing handoffs

**Files:**
- No production changes unless a focused failing test demonstrates a defect.
- Verify: existing Signal candidate store, Briefing generation, and queue integration tests.

**Interfaces:**
- Consumes: the five current cohort projections, immutable Signal manifests, the enabled isolated cross-report workflow, and human-review policy.
- Produces: hash-validated Signal evidence, explicit single-report grounding holds where required, and a validated multi-report Briefing; never an unapproved Signal post.

- [ ] Build cross-report inputs only from the five current retained reports and enable cross-report analysis only in the isolated canary configuration.
- [ ] Read back each Signal manifest through the canonical service and verify contract/hash immutability, mutation rejection, and replay idempotency.
- [ ] Run valid multi-report Briefing generation and validation with its cost and duration reported separately from per-report processing.
- [ ] Keep single-report Signal groups held and confirm no Signal publication is produced without the required human-review approval.

### Task 5: Verify autonomous approval and WordPress staging lifecycle

**Files:**
- No production code unless a focused failing test demonstrates an implementation defect.
- Verify: `scripts/ci/check_wordpress_staging_rest_gate.py`, existing publish queue/service tests, and the autonomous supervisor.

**Interfaces:**
- Consumes: current cohort output, isolated durable state, the `autonomous_mvp` overlay, and the user-confirmed staging host plus `.env` credentials.
- Produces: one fresh eligible draft publication, authenticated readback of required metadata, an idempotent replay with zero additional writes, and bounded retry/recovery evidence.

- [ ] Run the WordPress REST staging gate using a unique run suffix and only the confirmed staging host; record created object IDs and authenticated readback results, never credentials.
- [ ] Run the real autonomous supervisor against isolated cohort jobs and verify first-attempt approval/publication occurs only for a ready, unchanged, grounded package.
- [ ] Replay the same durable publication job and compare destination object IDs/write counters; require no duplicate object or new write.
- [ ] Exercise stale, unsupported, and override-required package holds using existing tests; exercise transient retry/recovery through the existing controlled service/queue test seam and verify bounded attempts.
- [ ] Confirm no report, Briefing, or Signal write reaches any host other than the confirmed staging site; keep Signal human review enforced.

### Task 6: Run the final unattended cohort, retain evidence, and merge

**Files:**
- Update: `docs/quality/frozen-five-autonomous-mvp-comparison-20261009.md`
- Update: `docs/README.md` only if the report location changes.
- Retain: redacted run manifests/results under the existing `out/` evidence convention.

**Interfaces:**
- Consumes: the exact frozen manifest, final source SHA, completed preflights, paired baseline/current artifacts, staging readback, and Signal/Briefing outcomes.
- Produces: final per-report and cohort scorecards, explicit GO/CONDITIONAL GO/NO-GO decision, green full CI, and a merged branch only if acceptance criteria are met.

- [ ] Reverify manifest SHA-256 and all five PDF MD5 values before queue admission.
- [ ] Run the unattended five-report cohort on the final source SHA with no manual approval, repair, or requeue; retain any diagnostic rerun separately.
- [ ] Compare each report against the unchanged historical artifact using the same factual, grounding, editorial, visual, readiness, timing, token, call, and cost boundaries; classify unavailable or topology-dependent measures as incomparable.
- [ ] Rerun affected focused checks, PDF benchmarks, public-quality checks, `python scripts/ci/check_formatting.py`, `python scripts/ci/check_ruff_lint.py`, and full GitHub CI on the final SHA.
- [ ] Inspect the final diff for scope, retained evidence, and secret exposure; merge the branch only when every applicable acceptance criterion is evidenced and CI is green.
