# Step 1 Evidence-backed Insight Shortlisting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve evidence-backed insight shortlisting for the frozen five-report cohort while preserving existing schemas, factual protections, downstream generation, and fail-closed behavior.

**Architecture:** Keep shortlisting in `src/generators/artifact_normalization.py`, where candidate normalization, deterministic evidence binding, ranking, and finding fallbacks already live. Use only retained candidate scores, evidence-pack metadata, editorial-plan evidence priorities, and report-theme coverage; keep orchestration in `generation.py` limited to passing the eligible fallback pool and applying the existing selector. Bump the existing selection version so artifact caches cannot reuse selections made by the old behavior.

**Tech Stack:** Python, pytest, existing artifact normalization/generation contracts, retained JSON report-analysis artifacts, repository CI scripts.

## Global Constraints

- No new LLM calls, database, vector store, service, or complex ranking framework.
- Reuse existing services and validators; do not weaken evidence-fidelity, retained-claim, safe-removal, or publication-readiness checks.
- Preserve stable candidate IDs, canonical evidence IDs, physical PDF pages, evidence spans, protected factual fields, output schemas, and downstream compatibility.
- Do not invent missing bindings or promote unresolved Step 0 reference cases.
- Use the exact frozen Capgemini, Activate, KPMG, Reuters Institute, and Adjust cohort; no paid provider calls or publication writes.
- Stop before Step 2 visual factualisation and before canonical verified-claim persistence or editorial-authority changes.

---

### Task 1: Add failing selector and fallback behavior tests

**Files:**
- Modify: `tests/_test_artifact_generator/cases_05_docmap_insight_selection.py`
- Modify: `tests/test_artifact_normalization_source_fidelity.py`
- Create: `tests/test_artifact_insight_shortlisting.py`

**Interfaces:**
- Consumes: existing public `select_artifact_insights()`, `fallback_artifact_insights_from_findings()`, and `fallback_artifact_insights_from_evidence()` calls.
- Produces: executable behavioral expectations for ranking, theme coverage, safe semantic equivalence, distinct same-topic metrics, fallback quality, missing bindings, stable IDs/pages/spans, and fail-closed eligibility.

- [ ] **Step 1: Write the failing tests**

  Add tests that call the real public selector/fallback functions with small retained-style dictionaries:

  - a high-score candidate with complete metric/evidence binding beats a generic lower-score observation, while a plan-priority theme is still represented;
  - two differently worded candidates with the same evidence ID and identical metric binding collapse to one, keeping the stronger candidate’s stable ID and protected fields;
  - candidates on the same page/topic remain distinct when their metric label/value, cohort, period, or observation status differs;
  - candidates with missing evidence IDs or missing metric bindings do not become eligible replacements, and a source-page hint alone does not create a binding;
  - findings fallbacks rank supported, high-confidence, page-bound findings before weaker/source-order findings and retain more than the final shortlist size for replacement;
  - an explicit fidelity pack excludes unsupported findings from the fallback pool, but the absence of a fidelity pack preserves the established findings-pack behavior;
  - cache metadata exposes a new selection version and the value differs from the current `stable_id_unique_selection:2` version.

- [ ] **Step 2: Run the focused tests and verify the expected failures**

  Run:

  ```powershell
  python -m pytest -q tests/test_artifact_insight_shortlisting.py tests/_test_artifact_generator/cases_05_docmap_insight_selection.py tests/test_artifact_normalization_source_fidelity.py
  ```

  Expected: the new assertions fail because current deduplication uses normalized text only, finding fallbacks stop at source order, and the selection version is still `stable_id_unique_selection:2`. Existing unrelated tests must not be silently changed to make the new tests pass.

### Task 2: Implement deterministic evidence-backed ranking and safe semantic identity

**Files:**
- Modify: `src/generators/artifact_normalization.py:25,1061-1590`
- Modify: `tests/test_artifact_insight_shortlisting.py`

**Interfaces:**
- Consumes: normalized insight fields, finding confidence/pages/section metadata, evidence-fidelity results, editorial-plan theme evidence IDs and priorities.
- Produces: the unchanged `List[Dict[str, Any]]` selector/fallback interfaces with deterministic ordering and preserved payload fields.

- [ ] **Step 1: Add the minimal selection helpers**

  Replace the text-only duplicate key with a conservative semantic identity composed from existing retained data:

  - stable `evidence_id` when present;
  - normalized proposition text/evidence text;
  - all populated protected metric-binding fields (`label`, `value`, `unit`, `trend`, `timeframe`, `geography`, `segment`, `sample_size`, `subject`, `cohort`, `denominator`, `observation_status`);
  - evidence-span identity including source pack, physical page, offsets, and normalized span text.

  Treat two records as equivalent only when their evidence identity is the same and their populated proposition/metric-binding signatures agree. If any protected dimension conflicts or is absent on one side, retain both rather than infer equivalence. Stable-ID collision handling remains authoritative for the candidate/final factual-field restoration already in place.

- [ ] **Step 2: Make ranking use existing signals only**

  Compute a tuple, not a new configurable scoring framework, with:

  1. evidence eligibility/physical-page binding;
  2. existing `decision_relevance_score`, `metric_strength_score`, `novelty_score`, then `score` when present;
  3. evidence-pack confidence and direct finding/quote support type;
  4. editorial-plan priority and whether the candidate covers an unrepresented theme;
  5. stable source order and ID as deterministic tie-breakers.

  Do not inspect arbitrary business words or add keyword relevance rules. Keep the selected payload copied from the existing final/candidate/finding item; never synthesize metrics, evidence IDs, pages, or spans.

- [ ] **Step 3: Change final selection to use the ranking while preserving broad coverage**

  Select the best eligible grounded lead, then satisfy plan themes in priority order, then fill remaining required slots by rank. Do not force a weak candidate merely to hit a count; retain the existing fail-closed downstream behavior when fewer than the required eligible insights exist. Preserve the existing narrow-plan and stable-ID compatibility cases where the records are genuinely distinct.

- [ ] **Step 4: Run the focused tests and fix only behavior regressions**

  Run the Task 1 command. Then run the full artifact-generator selection module:

  ```powershell
  python -m pytest -q tests/test_artifact_generator.py tests/test_artifact_normalization_source_fidelity.py
  ```

  Expected: all new tests and existing selection/factual-preservation tests pass; any changed expected ordering must be justified by the new evidence-backed ranking, not by weakening assertions.

### Task 3: Improve eligible finding fallbacks and invalidate artifact selection caches

**Files:**
- Modify: `src/generators/artifact_normalization.py:1518-1610`
- Modify: `src/generators/_artifact_generator/generation.py:1219-1245`
- Modify: `src/generators/report_regeneration_generator.py` at existing finding-fallback call sites
- Modify: `src/generators/_artifact_generator/storage.py` only if cache matching requires an explicit version comparison
- Modify: `tests/_test_artifact_generator/cases_06_editorial_plan.py`
- Modify: `tests/test_artifact_insight_shortlisting.py`

**Interfaces:**
- Consumes: retained findings/quotes and optional `evidence_fidelity.results` already passed through artifact generation/regeneration.
- Produces: a larger, ranked, fidelity-approved replacement pool through the existing fallback functions; cache metadata with a bumped `ARTIFACT_INSIGHT_SELECTION_VERSION`.

- [ ] **Step 1: Implement fallback eligibility and ranking**

  When an evidence-fidelity result set is present, admit only findings with `status == "supported"`, a canonical finding ID, non-empty text/evidence, and a physical page. If the fidelity pack is absent, retain the existing pack-level eligibility rule. Rank eligible findings using confidence, existing finding scores if present, page-bound evidence, editorial-plan evidence priority, and deterministic source order; return the requested limit without truncating the available pool before ranking. Quote fallback remains evidence-ID/page/text bound and does not supply missing finding bindings.

- [ ] **Step 2: Pass enough alternatives to the final selector and regeneration paths**

  Keep the current target count for the final output, but request an expanded bounded fallback pool based on the number of plan evidence IDs and target slots. Let the selector deduplicate and rank it. Apply the same fallback function in deterministic regeneration/replacement paths so a rejected item is replaced by the strongest remaining eligible finding, not the first source-order item.

- [ ] **Step 3: Bump and test the selection cache version**

  Change `ARTIFACT_INSIGHT_SELECTION_VERSION` to `evidence_backed_shortlisting:1` (or an equivalent clearly new value) and assert that `_artifact_cache_meta()` includes it. Existing cache-key and prompt/input invalidation assertions must remain green; a cache written with the old version must not match the new expected metadata/key.

- [ ] **Step 4: Run focused cache/fallback/generation tests**

  ```powershell
  python -m pytest -q tests/_test_artifact_generator/cases_05_docmap_insight_selection.py tests/_test_artifact_generator/cases_06_editorial_plan.py tests/test_artifact_insight_shortlisting.py
  ```

### Task 4: Replay the frozen five-report cohort and write the Step 1 evidence ledger

**Files:**
- Create: `docs/quality/verified-claims-step1-shortlisting-20261018.md`
- Modify: `docs/backlog/E-evidence.md` only in the existing E18 Step 1 evidence section if the measured result is complete enough to record
- Modify: `CONSOLIDATED_TODO.md` only if the existing E18 row/linked text would otherwise misstate Step 1 status

**Interfaces:**
- Consumes: exact frozen manifest `docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json`, manifest SHA-256 `744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`, and local retained report-analysis artifacts under `tmp/frozen20-next5-systemic-fix-20260930/frozen-reliability-xxcdkw0r/members/ias-first-attempt-7z7shs6j/output`.
- Produces: a compact, committed before/after selection ledger and an explicit 15-case reference-set assessment without raw PDFs, prompts, model responses, or fabricated fixtures.

- [ ] **Step 1: Run provider-free replay and collect metrics**

  Invoke the canonical selector/fallback workflow against the retained `findings.json`, `evidence_fidelity.json`, `artifacts.json`, and editorial-plan data for Capgemini, Activate, KPMG, Adjust, and Reuters Institute. Record candidate counts, selected IDs, theme coverage, meaningful evidence retention, duplicate removals, fallback replacements, stable-ID/page/span preservation, and insufficient-evidence abstentions. Do not call a provider or publication endpoint.

- [ ] **Step 2: Compare the 15 Step 0 cases**

  For each reference case, classify the updated result as retained, replaced by an eligible alternative, editorially omitted, still held for unresolved binding, or factual regression. Explicitly inspect ACT-001/002/003/004, CAP-001/002/003/004, KPM-001/002/003, REU-001/002/003, and ADJ-001; distinguish a missing editorial selection from an incorrect promoted claim.

- [ ] **Step 3: Write the compact evidence report**

  Include branch/start/end SHAs, exact manifest and retained-artifact identities, per-report before/after ledger with reasons, measurable improvements/regressions, test commands/results, no-provider/no-publication confirmation, and remaining limitations. State clearly that Step 2 was not started.

### Task 5: Run release-relevant verification and finish the branch

**Files:**
- Modify only files required by the tested implementation and evidence report.

**Interfaces:**
- Consumes: changed selector/fallback/cache implementation and Step 1 evidence report.
- Produces: verified branch commit pushed to `codex/fix-retained-insight-evidence-validation`, with no Step 2 work.

- [ ] **Step 1: Run focused and editorial-output checks**

  Run:

  ```powershell
  python -m pytest -q tests/test_artifact_insight_shortlisting.py tests/test_artifact_generator.py tests/test_artifact_normalization_source_fidelity.py
  python -m pytest -q tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py
  python -m pytest -q tests/test_render_service_public_advisory.py tests/test_render_service_public_prose.py
  python scripts/ci/check_public_report_quality.py
  ```

  Record exact pass/fail/skip results and any pre-existing failure separately.

- [ ] **Step 2: Run repository gates and inspect the final diff**

  Run `python scripts/ci/check_backlog_source.py`, `python scripts/ci/check_documentation.py --check-generated`, `python scripts/ci/check_repository_hygiene.py`, and `git diff --check`; inspect `git diff --stat` and `git diff` for scope and secret exposure. Do not add retained raw artifacts.

- [ ] **Step 3: Commit and push**

  ```powershell
  git add src/generators/artifact_normalization.py src/generators/_artifact_generator/generation.py src/generators/report_regeneration_generator.py src/generators/_artifact_generator/storage.py tests docs/quality/verified-claims-step1-shortlisting-20261018.md docs/backlog/E-evidence.md CONSOLIDATED_TODO.md
  git commit -m "feat: improve evidence-backed insight shortlisting"
  git push origin codex/fix-retained-insight-evidence-validation
  ```

  Report the commit SHA, exact verification results, before/after ledger, remaining limitations, and PASS/PARTIAL/FAIL verdict. Stop before Step 2.
