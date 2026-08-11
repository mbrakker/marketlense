# Medium Cover Unbreakable Title Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render complete report titles on medium covers when a retained title contains an over-wide unbroken token.

**Architecture:** Keep title fitting in the canonical cover-image service. When a title word or hyphen segment cannot fit even on an empty line, split it only at character boundaries for visual line layout; title data remains unchanged and the existing minimum-font and title-zone limits still reject genuinely overlong titles.

**Tech Stack:** Python 3.14, Pillow, pytest, canonical cover-style YAML.

## Global Constraints

- Report- and publisher-agnostic: no title, publisher, or report-ID allowlist.
- Preserve the complete normalized title; no truncation, ellipsis, or invented replacement text.
- Do not weaken the configured title rectangle or approved minimum font size.
- Retain the non-retryable `cover_title_overflow` failure when a title cannot fit after valid character-boundary wrapping.
- Replay historical failure `1_xSIv8iu5YfGbSrY9nq2MjWCnpBgRaaU` from the retained PDF with no publication call.

---

### Task 1: Add unbreakable-token wrapping

**Files:**

- Modify: `tests/integration/test_cover_image_service.py`
- Modify: `src/services/cover_image_service.py`

**Interfaces:**

- Consumes: `_wrap_text(text, max_width, draw, font)` and a complete normalized title.
- Produces: lines no wider than `max_width`, whose concatenation preserves every character of an unbroken title token.

- [x] **Step 1: Write the failing regression test.**

```python
def test_real_cover_renderer_wraps_unbreakable_title_on_medium_cover(tmp_path):
    title = "doc_map: cf091e263a2b6ed29222c5c60b6ed133a90fbe0c-pdf"
    outcomes = generate_cover_images(_request_with_title(tmp_path, title), _ctx())

    assert outcomes[0].status == "generated"
    assert Image.open(outcomes[0].assets.medium.output_path).size == (1200, 1500)
```

- [x] **Step 2: Run the isolated test and confirm it fails with `cover_title_overflow`.**

Run: `pytest -m integration tests/integration/test_cover_image_service.py::test_real_cover_renderer_wraps_unbreakable_title_on_medium_cover -q`

Expected: FAIL because the unbroken token is measured as a single line wider than the medium title rectangle.

- [x] **Step 3: Implement the minimal character-boundary wrapping fallback.**

```python
if len(fragments) <= 1:
    for character in word:
        candidate = f"{current}{character}"
        if current and _text_bbox(draw, candidate, font)[0] > max_width:
            lines.append(current)
            current = character
        else:
            current = candidate
    continue
```

Keep the existing whitespace and hyphen wrapping behavior; use character wrapping only when an individual word or hyphen segment is too wide for an empty line.

- [x] **Step 4: Run cover rendering and card-projection tests.**

Run: `pytest -m integration tests/integration/test_cover_image_service.py -q` and `pytest tests/test_cover_image_generator.py tests/test_report_card_projection.py tests/test_report_card_contracts.py tests/test_report_render_generator.py tests/test_render_service_artifacts.py -q`

Expected: PASS, including the existing complete-title overflow contract.

### Task 2: Replay and document the fix

**Files:**

- Modify: `docs/workflows/report-processing.md`

**Interfaces:**

- Consumes: retained PDF/admission state for `1_xSIv8iu5YfGbSrY9nq2MjWCnpBgRaaU`.
- Produces: a generated medium report-card cover, valid manifest, and rendered HTML without publication.

- [x] **Step 1: Document that unbreakable title tokens can wrap at character boundaries while title content remains complete.**

- [x] **Step 2: Replay the previous medium-cover failure in the isolated reliability profile.**

Run: report pipeline from the retained PDF with `requested_output_families=["report_card_manifest", "rendered_html"]`, cache invalidation for rendered output, and no publish call.

Expected: `report_pipeline_complete` with `status="processed"`.

- [x] **Step 3: Independently validate the replayed manifest, medium asset, and complete HTML.**

Run: local Python validator using `ReportCardManifest.from_dict(...)`, file existence/size checks for all three cover assets, and an HTML document-root check.

Expected: exactly two non-empty card insights, three non-empty cover images, and a complete HTML document.

- [x] **Step 4: Inspect staged scope and commit only this repair.**

Run: focused pytest, `ruff check`, `git diff --check`, and `git diff --cached --check`.

Commit: `git commit -m "fix: wrap unbreakable medium cover titles"`
