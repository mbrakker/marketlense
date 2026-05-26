# PDF Table Heuristics Decomposition Design

## Goal

Decompose `src/services/_pdf/table_heuristics.py` into focused private
table-capability modules without changing PDF candidate extraction behavior,
output quality, service ownership, local extraction latency, or external
cost.

## Current State

`table_heuristics.py` contains `3,390` audited physical lines and combines:

- table threshold policy and marker patterns
- private table candidate and layout dataclasses
- normalized page text/block/band interpretation
- ranked-table region detection
- table bounding-box composition and expansion
- false-positive screening, candidate validation, and deduplication
- small extraction-runtime helpers used by `table_candidates.py`

The canonical PDF service entrypoint is `src/services/pdf_service.py`.
`src/services/_pdf/figures.py` and
`src/services/_pdf/table_candidates.py` consume the current private
`table_heuristics.py` symbol surface.

Before production edits, the affected synthetic baseline is:

```text
69 passed
```

This covers `tests/test_pdf_figures_service/test_table_heuristics.py`,
`tests/test_pdf_figures_service/test_pipeline_and_cache.py`, and
`tests/test_pdf_crop_service.py`.

## Selected Architecture

Retain `table_heuristics.py` as the stable private compatibility surface and
move capability ownership into a private implementation package:

```text
src/services/_pdf/
  table_heuristics.py
  _table_heuristics/
    __init__.py
    policy.py
    models.py
    layout.py
    regions.py
    screening.py
```

The package remains internal to the existing PDF service family. Existing
consumers continue importing through `table_heuristics.py`, and public callers
continue entering through `pdf_service`.

### Capability Ownership

`policy.py` owns existing table thresholds, immutable settings, caption/note
marker policy, and compiled pattern policy. These values remain single-source
configuration for all internal table capabilities.

`models.py` owns private immutable table-analysis dataclasses:
`_TableCandidate`, `_PageTextBlock`, `_PageTextLine`, `_TableTextBand`, and
`_RankedTableRegion`.

`layout.py` owns deterministic page-content interpretation: safe scalar/text
normalization, page text blocks/lines/bands, font and overlap geometry
measurements, margin/noise recognition, note/title/body classification, and
low-level text metrics shared by downstream table decisions.

`regions.py` owns formation of candidate regions: ranked-table panel
detection, title/note/footer attachment, stream-rectangle shrink behavior,
horizontal expansion, internal heading clamps, top restoration, composed
bounding boxes, and `_expand_table_bbox`.

`screening.py` owns table evidence evaluation: cell/row statistics, caption
and figure context hints, validation rejection rules, table-like and
false-positive classifiers, candidate quality/overlap preference, and
deduplication.

`table_heuristics.py` remains the compatibility module. It reexports existing
policy, model, layout, region, and screening symbols and retains only the
small extraction-runtime helpers used directly by candidate execution, such
as worker-count resolution, chunk splitting, preview formatting, warning
suppression, and rejection-reason tallying.

## Dependency Direction

The new private modules use one-directional internal dependencies:

```text
policy  <- layout <- screening
models  <- layout <- screening
policy  <- layout <- regions
models  <- layout <- regions
screening <- regions
```

`regions.py` may call screening validation when ranked regions are converted
to validated candidates; `screening.py` must not import region formation.
When a low-level measurement is needed by both packages, it belongs in
`layout.py` rather than introducing circular imports or forwarding wrappers.

## Preserved Boundary And Behavior

The canonical service boundary remains `src/services/pdf_service.py`.
No second PDF service entrypoint, external system, process, deployment unit,
contract schema, or prompt/model path is introduced.

The refactor must preserve:

- names importable from `src.services._pdf.table_heuristics`
- `figures.py` and `table_candidates.py` caller behavior
- table method selection, bounding boxes, preview text, typed features,
  validation rejection rules, and deduplication order
- candidate contract contents and degradation statistics
- existing event ownership through the surrounding PDF service pipeline
- PDF parsing/rendering calls, parallel-worker behavior, and page-cache reuse
- zero network, provider, or upload activity introduced by table heuristics

This is a movement-only decomposition. Behavior changes are permitted only
when verification proves an existing regression and the correction is
captured by observable tests.

## Options Considered

### Selected: Private `_table_heuristics/` Package With Compatibility Surface

This provides semantic capability ownership and retains the single existing
consumer surface. It matches the repository's established private PDF/browser
capability package pattern.

### Rejected: Flat Peer Files Under `_pdf`

This would reduce the long file but disperse one coherent table capability
across the broader PDF namespace, increasing navigation and import churn.

### Rejected: Internal Function Reordering Only

This would not remove the mixed-responsibility monolith or establish focused
testable ownership.

## Real-Document Validation Target

The approved real-data gate uses a locally cached PDF already processed by
the application:

```text
cache/1Wm4HRYQ0ImIAEx4-tw2vz1T2i2ignIBD.pdf
stored report name: year-in-review-2022.pdf
```

Stored `report_figures` data includes selected table candidates on pages
`7`, `14`, `21`, `27`, and `29`, confirming the document exercises the
affected table path.

The pre-refactor read-only candidate collection run used one worker and a
temporary output directory. Its observable baseline is:

```text
candidate_count: 21
table_count: 12
degraded_pages: 0
triage_failure_count: 0
extraction_failure_count: 0
elapsed_seconds: 51.119
```

The table fingerprint includes each raw table candidate's `id`, `page`,
rounded `bbox`, `preview_text`, `caption`, and full typed feature contract.
Post-refactor validation must reproduce that fingerprint exactly. Runtime is
compared as a regression signal; a material slowdown must be investigated and
resolved before completion.

## Test And Verification Strategy

Implementation follows compatibility-preserving extraction:

1. Add an ownership/compatibility test that requires the selected private
   modules and requires existing symbols to remain importable through
   `table_heuristics.py`; observe it fail before source movement.
2. Move existing implementation bodies and constants into their assigned
   modules without changing conditions, thresholds, or call order.
3. Run affected PDF candidate, table, panel, visual, crop, and integration
   tests that operate through the PDF service boundary.
4. Run formatting, type, architecture, forbidden-patching, hygiene,
   coverage, mutation, and quality-regression gates configured by the
   repository, plus the default synthetic suite.
5. Only after synthetic gates pass, execute the approved local real-PDF
   comparison using the previously processed report and a temporary output
   directory.
6. If a mismatch or regression is found, capture the failure in an
   observable regression test where appropriate, correct it, and rerun the
   complete required gate set.

## Documentation Deliverables

The implementation updates:

- `docs/architecture/pdf-table-heuristics-decomposition-review.md`
- `README.md`
- `long_scripts.md`
