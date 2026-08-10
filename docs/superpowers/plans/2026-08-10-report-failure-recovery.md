# Report Failure Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recover previously failed report packages by carrying canonical source identity into rendering, rejecting generated filename titles before card rendering, and applying existing structured-output recovery to invalid evidence references.

**Architecture:** Rendering will select title and publisher from a resolved canonical source identity when generated analysis metadata is absent or unsafe, without relaxing public metadata governance. Artifact-family response validation will verify each model response's references against the retained canonical evidence set before the shared structured-output executor decides whether to repair or regenerate it. Cover layout receives a semantically valid title rather than a filename/hash surrogate.

**Tech Stack:** Python 3.12, typed frozen contracts, existing report-store identity service, existing structured-output recovery service, Pillow cover renderer, pytest.

## Global Constraints

- Preserve public-metadata, grounding, semantic, provenance, and final HTML gates; do not suppress a required invalid field.
- Trust a title or publisher fallback only from `SourceIdentityResolution` with `identity_status == "resolved"`.
- Keep model recovery bounded by the existing primary, deterministic repair, model repair, and regeneration sequence.
- Do not introduce a new provider, queue, persistence store, or publisher-specific rule.
- Run live validation only against cached prior cohort PDFs with isolated state/cost paths and no WordPress publication.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `src/generators/report_render_generator.py` | Resolve safe render metadata from canonical source identity before metadata upsert and cover-card generation. |
| `src/generators/_artifact_generator/generation.py` | Validate each artifact-family response against canonical evidence before the shared recovery executor accepts it. |
| `tests/test_report_render_generator_metadata_governance.py` | Prove resolved source identity repairs placeholder publisher and hash-suffixed filename title without weakening governance. |
| `tests/_test_artifact_generator/` | Prove an invalid evidence reference causes the existing structured recovery path before final assembly. |
| `tests/integration/test_cover_image_service.py` | Prove the repaired historical title fits all canonical card sizes. |
| `docs/workflows/report-processing.md` | Describe canonical identity-backed render metadata and reference-recovery behavior. |

### Task 1: Use canonical identity for render metadata

**Files:**

- Modify: `src/generators/report_render_generator.py`
- Test: `tests/test_report_render_generator_metadata_governance.py`

- [ ] **Step 1: Write failing tests**

Create one test where a resolved source identity supplies a publisher when the analysis/database value is `Not extracted`, and a second where an MD5-derived `-pdf` title is replaced by the resolved canonical title.

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `python -m pytest -q tests/test_report_render_generator_metadata_governance.py`

Expected: the tests fail because rendering uses the placeholder publisher and hash-suffixed title.

- [ ] **Step 3: Implement the minimal resolved-identity metadata selection**

Add deterministic title detection for an MD5 hash with an optional file-style suffix. Use a resolved identity's non-placeholder canonical title/publisher only as the fallback for generated or empty render metadata. Preserve the existing public-governance validation and metadata upsert flow.

- [ ] **Step 4: Run the focused tests and confirm GREEN**

Run: `python -m pytest -q tests/test_report_render_generator_metadata_governance.py tests/test_report_render_generator.py`

Expected: all selected tests pass.

### Task 2: Recover invalid artifact evidence references before assembly

**Files:**

- Modify: `src/generators/_artifact_generator/generation.py`
- Test: `tests/_test_artifact_generator/cases_*.py`

- [ ] **Step 1: Write a failing recovery test**

Use the real artifact generator with bounded fake provider responses: first return an otherwise schema-valid insight with `MISSING_REF`, then return the same insight with a retained evidence ID. Assert the returned artifact uses the retained ID and the repair response was consumed.

- [ ] **Step 2: Run the focused test and confirm RED**

Run the exact new test with `python -m pytest -q <test-node-id>`.

Expected: it fails because final assembly raises `schema_reference_missing` instead of invoking family recovery.

- [ ] **Step 3: Implement minimal pre-acceptance reference validation**

Pass a family-level validator to the existing `render_artifact_json_model` calls. The validator must call the canonical `validate_evidence_references` service with the retained evidence/doc-map payload so the existing structured-output executor performs its fixed recovery sequence.

- [ ] **Step 4: Run focused artifact tests and confirm GREEN**

Run: `python -m pytest -q tests/_test_artifact_generator tests/test_schema_validator.py`

Expected: all selected tests pass.

### Task 3: Document and validate prior failures

**Files:**

- Modify: `docs/workflows/report-processing.md`

- [ ] **Step 1: Document the actual recovery boundary**

State that rendering selects only resolved source identity as fallback metadata, that public URL absence is represented as `Not available`, and that artifact evidence references enter shared structured-output recovery before final grounding validation.

- [ ] **Step 2: Run static and focused validation**

Run Ruff, `git diff --check`, the affected unit/integration tests, and the report-render/cover checks.

- [ ] **Step 3: Run live prior-failure validation**

Use the exact retained PDFs for the former cover, public-metadata, and artifact-reference failures. Run the canonical report pipeline in an isolated validation profile with a sufficient local budget, no external publication, and verify each reaches `processed`/publish-ready or report any remaining typed blocker.

- [ ] **Step 4: Commit and merge**

After fresh verification, commit only task files and merge the feature branch into `main`, preserving unrelated untracked work.
