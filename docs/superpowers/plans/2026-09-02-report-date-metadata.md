# Report Date Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ambiguous public `Period` metadata with deterministic `Edition`, `Published`, and `Data period` fields while preserving retained source metadata.

**Architecture:** Keep raw `time_period` and source-publication provenance unchanged. The render generator supplies the already verified source publication date to the render payload; the render view deterministically projects it, a title-explicit edition, and a distinct source data period into separately labelled HTML fields. The display projection fails closed for uncertain dates and removes redundant equal values.

**Tech Stack:** Python 3.12, pytest, Jinja report renderer, retained JSON benchmark artifacts.

## Global Constraints

- Do not add an LLM or any external call.
- Never derive a publication date from `time_period`, a title year, or file metadata.
- Never derive an edition from source `time_period`.
- Omit uncertain or redundant display values; preserve all retained raw metadata.
- Render all 15 retained report artifacts before commit; no publication side effects.

---

### Task 1: Define public date projection cases

**Files:**
- Create: `tests/fixtures/editorial_temporal/report_date_metadata.json`
- Modify: `tests/test_public_metadata_projection.py`

**Interfaces:**
- Consumes: `render_report(RenderRequest(...)) -> RenderResponse`.
- Produces: labelled visible metadata for edition, source publication date, and a distinct data period.

- [x] **Step 1: Write fixture-backed failing render tests**

```python
assert "Edition: 2019" in html
assert "Published: November 2018" in html
assert "Data period: 2024E" in html
assert "Period:" not in html
```

Cover: edition year different from publication year; equal edition/publication year (without duplicate output); data year different from edition; explicit date range; and missing publication date.

- [x] **Step 2: Run the focused test to confirm the current ambiguous output fails**

Run: `python -m pytest -q tests/test_public_metadata_projection.py`

Expected: failures show `Period` output or missing explicit date labels.

### Task 2: Project source-backed report dates at the public render boundary

**Files:**
- Modify: `src/generators/report_render_generator.py`
- Modify: `src/services/_render_service/view.py`
- Modify: `src/services/_render_service/normalization.py`

**Interfaces:**
- Consumes: verified `SourcePublicationMetadata.publication_date`, report title, and retained `time_period`.
- Produces: `edition`, `published_date`, and `data_period` view values plus matching identity and snapshot labels.

- [x] **Step 1: Pass only the verified source publication date to rendering**

```python
render_data_dict["source_publication_date"] = _publication_date(runtime)
```

Use the existing fail-closed provenance policy; unverified or absent dates remain empty.

- [x] **Step 2: Implement deterministic, non-duplicative view projection**

```python
dates = _public_report_dates(
    report_title=report_title,
    source_publication_date=_s(data.get("source_publication_date")),
    time_period=time_period,
)
```

Derive `Edition` only from a title that explicitly names a report/outlook edition. Format source dates at their supplied precision only. Render `Data period` only when it is distinct from visible edition and publication values. Delete public `Period` labels.

- [x] **Step 3: Run focused tests until green**

Run: `python -m pytest -q tests/test_public_metadata_projection.py tests/test_report_render_generator_publication_metadata.py`

Expected: all fixture cases pass and a verified source date reaches the render payload.

### Task 3: Document and validate the public contract

**Files:**
- Modify: `docs/product/editorial-output.md`
- Test: `tests/test_taxonomy_generator.py`
- Test: `tests/test_render_service_public_prose.py`
- Test: `tests/test_render_service_public_advisory.py`

**Interfaces:**
- Consumes: the 15 retained `report_analysis/artifacts.json` benchmark inputs.
- Produces: a bounded render corpus and public-quality report with visible date metadata inspected.

- [x] **Step 1: Update the canonical editorial-output documentation**

Document that Edition is title-explicit, Published uses only verified source provenance, Data period retains a distinct material observation period, and unknown/redundant values are omitted.

- [x] **Step 2: Run tests and the full retained render corpus**

```powershell
python -m pytest -q tests/test_taxonomy_generator.py tests/test_public_metadata_projection.py tests/test_report_render_generator_publication_metadata.py tests/test_render_service_public_prose.py tests/test_render_service_public_advisory.py tests/test_public_advisory_render_benchmark.py
python scripts/ci/check_public_report_quality.py --minimum-reports 15 --output-dir out/report-date-metadata-quality --output-json out/report-date-metadata-quality.json
git diff --check
```

Inspect every rendered benchmark HTML's visible date labels, including the retained Activate examples. The benchmark only reads retained artifacts and runs no LLM calls.

- [ ] **Step 3: Commit and push only with fresh successful evidence**

```powershell
git add src/generators/report_render_generator.py src/services/_render_service/view.py src/services/_render_service/normalization.py tests/test_public_metadata_projection.py tests/test_report_render_generator_publication_metadata.py tests/fixtures/editorial_temporal/report_date_metadata.json docs/product/editorial-output.md docs/superpowers/plans/2026-09-02-report-date-metadata.md
git commit -m "fix: clarify report date metadata"
git push
```
