# Primary Public Report Titles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the complete title when it fits; otherwise render the intact primary report name without character-truncation.

**Architecture:** Keep the complete source title in retained evidence and metadata. At the public-title normalization boundary used by HTML headings and SEO metadata, retain the complete title when it fits and otherwise select the primary segment at a subtitle delimiter. This prevents layout overflow without corrupting source provenance or cutting a primary name.

**Tech Stack:** Python, pytest, Jinja rendering, retained-source validation.

## Global Constraints

- Preserve full source/doc-map titles outside the public rendering boundary.
- Treat `:`, en dash, and em dash as primary-title/subtitle delimiters only when the complete normalized title exceeds the display limit; do not split ordinary hyphenated words.
- Validate the failed IAB report and at least two retained reports with comparable multi-part titles without publishing externally.
- Commit only files introduced by this change; preserve unrelated workspace changes.

---

### Task 1: Specify primary title selection

**Files:**
- Modify: `tests/test_render_service_artifacts.py`

**Interfaces:**
- Consumes: `_normalize_public_title(value: str, *, max_length: int = 110) -> str`
- Produces: regression coverage for colon-delimited public titles.

- [x] Write a parameterized failing test for the IAB title and two retained multi-part report titles, asserting the part before the delimiter is used.
- [x] Run the focused test and confirm it fails because the renderer retains the subtitle.

### Task 2: Normalize public titles at the rendering boundary

**Files:**
- Modify: `src/services/_render_service/view.py`
- Modify: `docs/quality/public-editorial-quality.md`
- Test: `tests/test_render_service_artifacts.py`

**Interfaces:**
- Consumes: complete source title strings and `_normalize_public_title`.
- Produces: primary public titles for HTML, Open Graph, JSON-LD, and SEO title construction.

- [x] Add the smallest deterministic delimiter rule before length normalization.
- [x] Document that complete source titles remain retained while public headings use a primary segment.
- [x] Run the focused regression test and confirm it passes.

### Task 3: Validate retained reports and commit

**Files:**
- Modify: `docs/superpowers/plans/2026-08-11-primary-public-report-titles.md`

- [x] Render the IAB report from retained inputs and confirm its HTML heading uses `Trusted Execution Environments in Digital Advertising`.
- [x] Render two retained reports with comparable colon-delimited titles and confirm their HTML headings retain the complete title when it fits.
- [x] Run affected tests, static checks, compilation, and diff checks.
- [x] Inspect the scoped diff and commit the change.
