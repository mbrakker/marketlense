# Batch 4 Identity Traceability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the remaining deterministic report identity, provenance projection, and immutable review-HTML traceability safeguards without regenerating editorial content.

**Architecture:** Preserve the existing source-identity resolver as the single authority for title and provenance roles. Supply a bounded immutable render-provenance value through the existing render request/data contract, have the render service emit it as a non-visible top-of-document comment, and have publish readiness reject artifacts without the complete marker. This retains the existing render-only invalidation path.

**Tech Stack:** Python 3, dataclasses, Jinja2, BeautifulSoup, pytest, SQLite-backed report metadata.

## Global Constraints

- Keep title and organisation resolution source-supported and publisher-agnostic.
- Do not change finding, evidence, validation, Core Signal, LinkedIn, or factual relationship generation.
- Do not add a model family; identity LLM use remains the existing bounded ambiguity fallback.
- Missing traceability values are `unknown`; the build comment itself is mandatory.
- Metadata-only corrections use the existing render-only recovery path.

---

### Task 1: Complete source-title candidate normalization

**Files:**
- Modify: `src/generators/report_title_resolution_generator.py`
- Modify: `tests/test_report_title_resolution.py`
- Modify: `docs/ops/source-publication-metadata.md`

**Interfaces:**
- Produces: `resolve_report_title(...) -> ReportTitleResolution` with source punctuation/casing intact and filename acquisition suffixes removed.

- [x] **Step 1: Write failing title tests** for a cover title containing `Europe's` and `Retail & Commerce Media`, a filename ending `June 26`, and acronym-led source branding.
- [x] **Step 2: Run the tests** with `python -m pytest -q tests/test_report_title_resolution.py` and confirm the failures describe the missing resolution behavior.
- [x] **Step 3: Implement only normalization necessary for the failing tests** while retaining the established candidate source order and bounded LLM ambiguity input.
- [x] **Step 4: Re-run the focused title tests** and inspect the exact resolved public title.

### Task 2: Preserve distinct source provenance roles through public projection

**Files:**
- Modify: `src/services/document_identity_service.py`
- Modify: `src/services/_report_store_service/metadata.py`
- Modify: `src/generators/report_render_generator.py`
- Modify: `src/services/_render_service/view.py`
- Modify: `tests/test_source_identity_provenance.py`
- Modify: `tests/test_report_render_generator_metadata_governance.py`
- Modify: `docs/ops/source-publication-metadata.md`

**Interfaces:**
- Consumes: `SourceProvenanceRoles` on `SourceIdentityResolution`.
- Produces: a canonical publisher, optional person/organisation author, distinct data-provider attribution, and matching public render data.

- [x] **Step 1: Write failing tests** showing a named source byline remains JSON-LD author and an incidental data provider cannot become publisher.
- [x] **Step 2: Run the focused provenance tests** and verify the expected failure.
- [x] **Step 3: Implement the smallest role-specific deterministic selection/projection change.**
- [x] **Step 4: Re-run the focused provenance and render tests.**

### Task 3: Add immutable HTML build provenance and enforce it in readiness

**Files:**
- Modify: `src/contracts/report_assets.py`
- Modify: `src/generators/report_render_generator.py`
- Modify: `src/services/_render_service/workflow.py`
- Modify: `src/generators/publish_readiness_generator.py`
- Modify: `tests/test_report_render_generator.py`
- Modify: `tests/test_publish_readiness_gate.py`
- Modify: `docs/ops/source-publication-metadata.md`

**Interfaces:**
- Produces: `RenderRequest.build_provenance: dict[str, str]` containing `git_sha`, `generation_run_id`, `validation_run_id`, `source_id`, `source_md5`, `artifact_hash`, `generation_profile`, and `generated_at_utc`.
- Produces: the non-visible `marketbearing-build` HTML comment and a failing readiness rule for an absent or malformed marker.

- [x] **Step 1: Write failing renderer/readiness tests** asserting all eight keys, literal unknown fallback, and distinct run markers.
- [x] **Step 2: Run those tests** and verify the marker is absent.
- [x] **Step 3: Add the typed contract and emit an escaped comment directly after the document declaration; derive values from the existing runtime/context and artifact lineage.**
- [x] **Step 4: Add the readiness parser/rule and run the focused tests until they pass.**

### Task 4: Verify regression boundaries and documentation

**Files:**
- Modify: `docs/ops/source-publication-metadata.md`
- Modify: `CONSOLIDATED_TODO.md` only if its Batch 4 entry remains open after all acceptance evidence exists.

- [ ] **Step 1: Run identity, provenance, render, readiness, card, WordPress-projection, and public-editorial focused tests.**
- [ ] **Step 2: Run `git diff --check` and inspect the final diff for scope/secrets.**
- [ ] **Step 3: Run the approved isolated discovery → acquisition → ingest → publish workflow if its local profile and report corpus are available; otherwise retain the exact unavailable prerequisite and do not claim the real-report audit.**
- [ ] **Step 4: Commit only after all available checks pass using `fix: finalize report identity and provenance projection`, then push the current branch.**
