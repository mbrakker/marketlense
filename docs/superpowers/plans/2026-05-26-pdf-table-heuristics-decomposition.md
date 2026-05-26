# PDF Table Heuristics Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the 3,390-line internal PDF table heuristic module into focused private capability modules while retaining its import surface and deterministic candidate output.

**Architecture:** `src/services/_pdf/table_heuristics.py` remains the compatibility boundary consumed by the existing PDF implementation. A new `_table_heuristics/` private package owns policy, analysis models, page-layout interpretation, region formation, and candidate screening/deduplication without changing `pdf_service.collect_candidates()` or its local extraction algorithm.

**Tech Stack:** Python 3.14, dataclasses, PyMuPDF, pdfplumber, pytest, AST ownership tests, Ruff/mypy/coverage/mutation quality scripts

---

## File Structure

- Create: `src/services/_pdf/_table_heuristics/__init__.py` - marks the focused private implementation package.
- Create: `src/services/_pdf/_table_heuristics/policy.py` - table thresholds, settings, and compiled marker policy.
- Create: `src/services/_pdf/_table_heuristics/models.py` - immutable private table-analysis dataclasses.
- Create: `src/services/_pdf/_table_heuristics/layout.py` - text/block/band extraction, classification, geometry, preview, and shared text statistics.
- Create: `src/services/_pdf/_table_heuristics/regions.py` - ranked-region detection and candidate bounding-box composition/expansion.
- Create: `src/services/_pdf/_table_heuristics/screening.py` - candidate statistics, validation/rejection rules, quality, overlap, and deduplication.
- Modify: `src/services/_pdf/table_heuristics.py` - stable reexport facade plus execution-only helpers.
- Create: `tests/test_pdf_table_heuristics_decomposition.py` - module ownership and compatibility-surface regression check.
- Modify: `scripts/ci/check_split_symbol_links.py` - include the new compatibility facade/private package in split-boundary validation.
- Modify: `README.md` - describe the focused private table-heuristic package.
- Modify: `long_scripts.md` - refresh the long-file inventory after decomposition.
- Modify: `docs/architecture/pdf-table-heuristics-decomposition-review.md` - add verification evidence.

### Task 1: Capture A Machine-Comparable Real-PDF Baseline

**Files:**
- Read: `cache/1Wm4HRYQ0ImIAEx4-tw2vz1T2i2ignIBD.pdf`
- Generate outside source control: `$env:TEMP/market-lense-pdf-table-live-baseline.json`

- [ ] **Step 1: Write the pre-edit baseline from the approved local PDF**

Run:

```powershell
@'
from dataclasses import asdict
import json
import tempfile
import time
from pathlib import Path
from src.contracts.report_assets import ExtractCandidatesRequest
from src.contracts.run_context import RunContext
from src.services import pdf_service

pdf = Path("cache/1Wm4HRYQ0ImIAEx4-tw2vz1T2i2ignIBD.pdf")
target = Path(__import__("os").environ["TEMP"]) / "market-lense-pdf-table-live-baseline.json"
ctx = RunContext(schema_version="1.0", run_id="pdf-table-live-baseline", task_id="year-in-review-2022", span_id="candidate-collection")
with tempfile.TemporaryDirectory(prefix="pdf-table-live-baseline-") as out_dir:
    started = time.perf_counter()
    result = pdf_service.collect_candidates(
        ExtractCandidatesRequest(schema_version="1.0", pdf_path=str(pdf), out_dir=out_dir, report_name="year-in-review-2022", parallel_workers=1),
        ctx,
    )
    tables = [
        {
            "id": c.id,
            "page": c.page,
            "bbox": [round(value, 3) for value in c.bbox],
            "preview_text": c.preview_text,
            "caption": c.caption,
            "features": asdict(c.features) if c.features is not None else None,
        }
        for c in result.candidates
        if c.kind == "table"
    ]
    payload = {
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "candidate_count": len(result.candidates),
        "table_count": len(tables),
        "stats": asdict(result.stats),
        "tables": tables,
    }
target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
print(target)
print(payload["candidate_count"], payload["table_count"], payload["stats"])
'@ | python -
```

Expected: the file is written outside the repository and reports `21` total
candidates, `12` table candidates, and zero degraded/extraction/triage
failures. If the deterministic baseline differs before source edits, stop and
update the design evidence before continuing.

### Task 2: Lock Module Ownership With A Red Test

**Files:**
- Create: `tests/test_pdf_table_heuristics_decomposition.py`

- [ ] **Step 1: Write the failing structural compatibility test**

```python
from __future__ import annotations

import ast
from pathlib import Path


PACKAGE = Path("src/services/_pdf")
FACADE = PACKAGE / "table_heuristics.py"
MODULE_SYMBOLS = {
    "_table_heuristics/policy.py": {
        "TABLE_SETTINGS_LATTICE",
        "TABLE_SETTINGS_STREAM",
        "TABLE_DEDUP_IOU",
    },
    "_table_heuristics/models.py": {
        "_TableCandidate",
        "_PageTextBlock",
        "_PageTextLine",
        "_TableTextBand",
        "_RankedTableRegion",
    },
    "_table_heuristics/layout.py": {
        "_table_page_text_blocks",
        "_table_text_bands",
        "_table_preview",
        "_extract_text_in_bbox",
        "_text_stats",
    },
    "_table_heuristics/regions.py": {
        "_detect_ranked_table_candidates",
        "_compose_table_bbox",
        "_expand_table_bbox",
    },
    "_table_heuristics/screening.py": {
        "_validate_table_candidate",
        "_dedupe_table_candidates",
        "_table_quality",
    },
}
COMPATIBILITY_SYMBOLS = {
    "TABLE_SETTINGS_LATTICE",
    "TABLE_SETTINGS_STREAM",
    "_TableCandidate",
    "_table_page_text_blocks",
    "_table_text_bands",
    "_detect_ranked_table_candidates",
    "_compose_table_bbox",
    "_expand_table_bbox",
    "_table_preview",
    "_extract_text_in_bbox",
    "_text_stats",
    "_validate_table_candidate",
    "_dedupe_table_candidates",
    "_resolve_candidate_parallel_workers",
    "_suppress_pdfminer_warnings",
}


def _owned_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    symbols = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for node in tree.body:
        if isinstance(node, ast.Assign):
            symbols.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            symbols.add(node.target.id)
    return symbols


def test_pdf_table_heuristics_use_focused_private_capability_modules() -> None:
    facade_symbols = _owned_symbols(FACADE)
    for relative_path, expected in MODULE_SYMBOLS.items():
        owned = _owned_symbols(PACKAGE / relative_path)
        assert expected <= owned
        assert not expected & facade_symbols

    source = FACADE.read_text(encoding="utf-8")
    for symbol in COMPATIBILITY_SYMBOLS:
        assert symbol in source
```

- [ ] **Step 2: Run the new test before production edits**

Run:

```powershell
python -m pytest tests/test_pdf_table_heuristics_decomposition.py -q
```

Expected: `FAILED` because
`src/services/_pdf/_table_heuristics/models.py` does not exist.

### Task 3: Extract Policy And Private Models

**Files:**
- Create: `src/services/_pdf/_table_heuristics/__init__.py`
- Create: `src/services/_pdf/_table_heuristics/policy.py`
- Create: `src/services/_pdf/_table_heuristics/models.py`
- Modify: `src/services/_pdf/table_heuristics.py`
- Test: `tests/test_pdf_table_heuristics_decomposition.py`

- [ ] **Step 1: Create the implementation package marker**

```python
"""Internal semantic families for PDF table-candidate heuristics."""
```

- [ ] **Step 2: Move policy declarations unchanged into `policy.py`**

Move `PDF_FIGURE_EXCEPTIONS`, `_PDFMINER_LOGGERS`, all current
`TABLE_*` settings/threshold declarations, `CAPTION_HINTS`,
`TABLE_CAPTION_HINTS`, `NOTE_LABEL_PREFIXES`, `EMAIL_ADDRESS_RX`,
`_PAGE_NUMBER_RX`, `_TABLE_FOOTNOTE_RX`, and `_FIGURE_CONTEXT_RX` from
`table_heuristics.py`. Keep their literal values and regular-expression flags
unchanged. `policy.py` imports only `re` and `statistics`.

- [ ] **Step 3: Move the immutable analysis records unchanged into `models.py`**

Move these dataclass definitions with their existing field order and types:

```python
_TableCandidate
_PageTextBlock
_PageTextLine
_TableTextBand
_RankedTableRegion
```

`models.py` imports `dataclass`, `Tuple`, and `pymupdf as fitz`; it imports no
service or capability module.

- [ ] **Step 4: Start the facade with explicit reexports**

Add explicit imports in `table_heuristics.py` for policy constants and model
classes so current consumers still resolve the same names:

```python
from ._table_heuristics.models import (
    _PageTextBlock,
    _PageTextLine,
    _RankedTableRegion,
    _TableCandidate,
    _TableTextBand,
)
from ._table_heuristics.policy import (
    TABLE_DEDUP_IOU,
    TABLE_SETTINGS_LATTICE,
    TABLE_SETTINGS_STREAM,
)
```

Extend this explicit import list with every policy name consumed by
`figures.py`, `table_candidates.py`, and retained facade helpers. Do not use
star imports for the new boundary.

### Task 4: Extract Page Layout And Candidate Screening

**Files:**
- Create: `src/services/_pdf/_table_heuristics/layout.py`
- Create: `src/services/_pdf/_table_heuristics/screening.py`
- Modify: `src/services/_pdf/table_heuristics.py`
- Test: `tests/test_pdf_table_heuristics_decomposition.py`
- Test: `tests/test_pdf_figures_service/test_table_heuristics.py`

- [ ] **Step 1: Move page-layout interpretation into `layout.py`**

Move the original function bodies unchanged for:

```python
_s
_int_count
_table_normalize_text
_table_text_lines
_starts_with_lower_alpha
_table_text_has_note_marker
_table_text_has_figure_context
_table_text_starts_with_footnote_marker
_table_text_has_embedded_note_marker
_table_page_text_blocks
_table_page_body_font_size
_cell_is_numeric
_table_fragment_is_numeric
_table_page_text_lines
_table_text_bands
_table_band_is_margin_noise
_table_band_is_note_like
_table_band_is_heading_like
_table_band_is_body_paragraph
_table_band_is_title_like
_table_band_is_row_like
_table_block_is_margin_noise
_cluster_is_row_continuation
_table_block_is_note_like
_table_block_is_mixed_footer_cluster
_table_block_is_heading_like
_table_block_is_body_paragraph
_table_block_is_note_continuation
_table_band_is_note_continuation
_table_block_is_title_like
_table_block_looks_dense_tabular
_alpha_ratio
_is_page_number_text
_horizontal_overlap_ratio
_vertical_overlap_ratio
_table_preview
_extract_text_in_bbox
_text_stats
_rect_intersection_area
_heading_like_block
_text_block_stats
```

Use `models.py` for block/band records and `policy.py` for thresholds/patterns.
Do not change exception handling, numeric tolerances, string normalization, or
geometry calculations.

- [ ] **Step 2: Move evidence evaluation and deduplication into `screening.py`**

Move the original bodies unchanged for:

```python
_cell_words
_numeric_char_ratio
_avg_words_per_cell
_avg_first_col_words
_row_nonempty_counts
_row_text_lengths
_col_consistency
_row_len_cv
_cell_is_page_number
_index_page_ratio
_has_caption_hint
_has_figure_context_hint
_validate_table_candidate
_stream_text_layout_like
_stream_text_block_like
_stream_infobox_like
_stream_list_like
_stream_panel_like
_stream_slide_card_like
_stream_sparse_text_like
_stream_multilist_infographic_like
_stream_low_consistency
_text_block_like
_text_block_like_loose
_filled_cells_per_row
_nonempty_text_lines
_terminal_page_number_hits
_contents_like
_section_list_like
_contents_grid_like
_reference_block_like
_front_matter_like
_contact_block_like
_prose_box_like
_visual_quote_page_like
_chart_fragment_like
_table_sort_key
_table_quality
_table_iou
_table_containment_ratio
_prefer_inner_lattice_table
_dedupe_table_candidates
```

Import shared layout functions from `layout.py`, models from `models.py`, and
thresholds from `policy.py`. Preserve rejection strings and ordering exactly.
`screening.py` does not import region formation.

- [ ] **Step 3: Reexport moved layout/screening names from the facade**

Use explicit imports from `layout.py` and `screening.py` for every moved symbol
currently imported from `table_heuristics.py` by `figures.py` or
`table_candidates.py`. Region functions remain temporarily defined in the
facade and call the imported layout/screening symbols as before; the imports
in consumer files remain unchanged.

- [ ] **Step 4: Run the focused table heuristic suite during extraction**

Run:

```powershell
python -m pytest tests/test_pdf_table_heuristics_decomposition.py tests/test_pdf_figures_service/test_table_heuristics.py -q
```

Expected while region formation is not yet moved: the structural test fails
only for `regions.py`; all previously executable table behavior continues
passing.

### Task 5: Extract Region Formation And Finish The Compatibility Facade

**Files:**
- Create: `src/services/_pdf/_table_heuristics/regions.py`
- Modify: `src/services/_pdf/table_heuristics.py`
- Modify: `scripts/ci/check_split_symbol_links.py`
- Test: `tests/test_pdf_table_heuristics_decomposition.py`
- Test: `tests/test_pdf_figures_service/test_table_heuristics.py`
- Test: `tests/test_pdf_figures_service/test_pipeline_and_cache.py`
- Test: `tests/test_pdf_crop_service.py`

- [ ] **Step 1: Move table-region construction into `regions.py`**

Move the original function bodies unchanged for:

```python
_table_rank_value
_table_horizontal_rule_rects
_group_rank_blocks_into_sequences
_ranked_table_panel_region
_detect_ranked_table_candidates
_table_attach_title_bands
_table_attach_note_bands
_shrink_stream_table_rect
_table_attach_title_blocks
_table_attach_note_blocks
_table_attach_explicit_title_context
_table_attach_mixed_footer_blocks
_table_expand_horizontal_to_content
_table_extend_overlapping_note_blocks
_table_restore_top_slack
_table_clamp_top_to_internal_title_band
_table_clamp_top_to_internal_title
_table_clamp_bottom_before_internal_heading
_compose_table_bbox
_expand_table_bbox
```

Import page interpretation helpers from `layout.py`, data records from
`models.py`, constants from `policy.py`, and `_validate_table_candidate` from
`screening.py`. Preserve bbox decisions and ranked candidate construction
exactly; `screening.py` does not import `regions.py`.

- [ ] **Step 2: Retain execution-only helpers in `table_heuristics.py`**

Leave these existing helper bodies in the compatibility module because only
candidate execution consumes them and no extracted capability depends on
them:

```python
_candidate_index_from_id
_split_even_chunks
_resolve_candidate_parallel_workers
_tally_reason
_suppress_pdfminer_warnings
```

Replace all other moved bodies with explicit facade imports from the five
private implementation modules.

- [ ] **Step 3: Extend split-boundary static checking**

Add the facade and private modules to `BOUNDARY_EXPORT_REQUIREMENTS` in
`scripts/ci/check_split_symbol_links.py` using symbols already asserted by
`tests/test_pdf_table_heuristics_decomposition.py`. The facade uses explicit
imports, so do not add the new package to `STAR_LINK_TARGETS` or create a
second public boundary.

- [ ] **Step 4: Verify the red test is now green with affected baseline tests**

Run:

```powershell
python -m pytest tests/test_pdf_table_heuristics_decomposition.py tests/test_pdf_figures_service/test_table_heuristics.py tests/test_pdf_figures_service/test_pipeline_and_cache.py tests/test_pdf_crop_service.py -q
python scripts/ci/check_split_symbol_links.py
```

Expected: all tests and static split-symbol checking pass.

- [ ] **Step 5: Commit the verified extraction**

```powershell
git add -- src/services/_pdf/table_heuristics.py src/services/_pdf/_table_heuristics tests/test_pdf_table_heuristics_decomposition.py scripts/ci/check_split_symbol_links.py
git commit -m "refactor: decompose pdf table heuristics"
```

### Task 6: Document And Run Synthetic Quality Gates

**Files:**
- Modify: `README.md`
- Modify: `long_scripts.md`
- Modify: `docs/architecture/pdf-table-heuristics-decomposition-review.md`

- [ ] **Step 1: Update documentation and audit output**

Add a README note beside the existing PDF candidate extraction split stating
that `table_heuristics.py` is now an internal compatibility facade over
`_table_heuristics/{policy,models,layout,regions,screening}.py`, preserving
`pdf_service.collect_candidates()` as the canonical entrypoint.

Run:

```powershell
python scripts/count_long_files.py --min-lines 500
```

Update `long_scripts.md` with the resulting table-heuristics facade line
count and any remaining private PDF table hotspot above the audit threshold.

- [ ] **Step 2: Run the expanded affected PDF tests**

Run:

```powershell
python -m pytest tests/test_pdf_table_heuristics_decomposition.py tests/test_pdf_figures_service tests/test_pdf_crop_service.py tests/test_pdf_internal_boundaries.py tests/integration/test_service_integrations.py -m "not integration" -q
```

Expected: zero failures.

- [ ] **Step 3: Run configured static and synthetic quality gates**

Run:

```powershell
python scripts/ci/check_formatting.py
python scripts/ci/check_split_symbol_links.py
python scripts/ci/check_architecture_imports.py
python scripts/ci/check_forbidden_patching.py
python scripts/ci/check_repository_hygiene.py
python scripts/ci/run_type_check.py
python -m pytest -m "not integration" -q --cov=src --cov-report=xml
python scripts/ci/check_coverage.py
python scripts/ci/run_mutation_gate.py
python scripts/ci/check_quality_regression.py
```

Expected: every command exits zero. Record test totals, coverage, and
mutation/quality output in the architecture review.

### Task 7: Run The Approved Real-PDF Equivalence Gate

**Files:**
- Read: `$env:TEMP/market-lense-pdf-table-live-baseline.json`
- Read: `cache/1Wm4HRYQ0ImIAEx4-tw2vz1T2i2ignIBD.pdf`
- Modify: `docs/architecture/pdf-table-heuristics-decomposition-review.md`

- [ ] **Step 1: Compare current results to the pre-edit fingerprint**

Run after all synthetic gates pass:

```powershell
@'
from dataclasses import asdict
import json
import os
import tempfile
import time
from pathlib import Path
from src.contracts.report_assets import ExtractCandidatesRequest
from src.contracts.run_context import RunContext
from src.services import pdf_service

baseline_path = Path(os.environ["TEMP"]) / "market-lense-pdf-table-live-baseline.json"
baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
pdf = Path("cache/1Wm4HRYQ0ImIAEx4-tw2vz1T2i2ignIBD.pdf")
ctx = RunContext(schema_version="1.0", run_id="pdf-table-live-post-refactor", task_id="year-in-review-2022", span_id="candidate-collection")
with tempfile.TemporaryDirectory(prefix="pdf-table-live-post-") as out_dir:
    started = time.perf_counter()
    result = pdf_service.collect_candidates(
        ExtractCandidatesRequest(schema_version="1.0", pdf_path=str(pdf), out_dir=out_dir, report_name="year-in-review-2022", parallel_workers=1),
        ctx,
    )
    tables = [
        {
            "id": c.id,
            "page": c.page,
            "bbox": [round(value, 3) for value in c.bbox],
            "preview_text": c.preview_text,
            "caption": c.caption,
            "features": asdict(c.features) if c.features is not None else None,
        }
        for c in result.candidates
        if c.kind == "table"
    ]
    actual = {
        "candidate_count": len(result.candidates),
        "table_count": len(tables),
        "stats": asdict(result.stats),
        "tables": tables,
    }
elapsed = round(time.perf_counter() - started, 3)
expected = {key: baseline[key] for key in ("candidate_count", "table_count", "stats", "tables")}
assert actual == expected, json.dumps({"expected": expected, "actual": actual}, indent=2, sort_keys=True)
print(json.dumps({"status": "match", "baseline_elapsed_seconds": baseline["elapsed_seconds"], "post_elapsed_seconds": elapsed, "candidate_count": actual["candidate_count"], "table_count": actual["table_count"]}, indent=2))
'@ | python -
```

Expected: `status` is `match`; candidate and table counts remain `21` and
`12`; all table IDs/pages/bboxes/previews/features and failure statistics are
identical. If elapsed time is materially slower than `51.119` seconds, repeat
the measurement once to rule out local variance, then investigate before
completion.

- [ ] **Step 2: Record execution evidence and commit documentation**

Add exact synthetic/gate totals and real-PDF comparison output to
`docs/architecture/pdf-table-heuristics-decomposition-review.md`, update the
README/audit documentation, then run:

```powershell
git diff --check
git add -- README.md long_scripts.md docs/architecture/pdf-table-heuristics-decomposition-review.md docs/superpowers/specs/2026-05-26-pdf-table-heuristics-decomposition-design.md docs/superpowers/plans/2026-05-26-pdf-table-heuristics-decomposition.md
git commit -m "docs: record pdf table heuristics validation"
```

Expected: clean whitespace validation and commits containing only the
documented refactor and its evidence.
