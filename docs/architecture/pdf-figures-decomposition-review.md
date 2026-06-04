# PDF Figures Semantic Decomposition Review

## Trigger

This review is required because decomposition of
`src/services/_pdf/figures.py` introduces four focused private peer modules
inside the existing PDF service family.

## Capability And Boundary

Capability: local PDF figure extraction, including candidate page triage,
chart/table overlap pruning, candidate collection, and legacy best-figure
image selection.

Bounded context: the existing PDF service family canonically exposed by
`src/services/pdf_service.py`. The existing
`src/services/_pdf/figures.py` module remains the compatibility facade used by
`pdf_service.py`, crop helpers, and legacy tests.

This is an internal modular-monolith decomposition. It adds no external
system boundary, deployable process, service entrypoint, contract/schema
change, prompt/config path, provider interaction, retry policy, or model/API
call.

## Semantic Ownership

The private implementation family is:

- `_figures/triage.py`: page scoring, page-gate recall-floor selection,
  degraded-page policy adaptation, and triage records.
- `_figures/pruning.py`: chart/table shadow pruning, final chart candidate
  pruning, local title reanchoring, and crop-compatible geometry constants.
- `_figures/candidates.py`: candidate collection service flow, chart/table
  extractor delegation, artifact assembly, degraded-candidate annotation, and
  service logging.
- `_figures/best_figure.py`: legacy single best embedded-image selection for
  fallback figure extraction.

The facade explicitly imports owners in dependency order:

```text
triage -> pruning -> candidates -> best_figure -> figures
```

Existing callers continue importing through `figures.py` or `pdf_service.py`,
so the normal PDF service path gains no competing entrypoint.

## Boundary Decision

The split is semantic rather than line-count driven. Page triage, final
candidate pruning, collection/logging coordination, and legacy embedded-image
selection have different deterministic inputs and investigation paths. Keeping
them in one private owner would preserve unrelated reasons for change in one
module. Creating deployable or public service boundaries would add operational
complexity without scaling, isolation, ownership, or compliance evidence.

The same outcome cannot be achieved with fewer modules and the same clarity
because combining triage with pruning couples page-gate policy to candidate
geometry decisions, while combining legacy best-figure extraction with
candidate collection ties a fallback image path to the gallery candidate flow.

## Preservation Controls

This movement-only change preserves:

- heuristic thresholds, branch order, candidate ordering, threading behavior,
  cache behavior, scoring, logging events, and output contracts
- all exports used through `figures.py`
- the `pdf_service.py` canonical service boundary
- local-only validation with no Drive, OpenAI, OCR-provider, model, or browser
  acquisition activity

## Movement Audit

Direct AST movement audit against `HEAD:src/services/_pdf/figures.py`:

```text
moved_symbol_count: 39
unchanged_moved_symbol_count: 35
changed_moved_symbol_count: 4
changed_moved_symbols:
  _extract_charts_sequential
  _extract_charts
  _extract_tables_sequential
  _extract_tables
facade_owned_definitions_after_split: 0
```

The four changed moved symbols are delegation wrappers whose only required
source change is relative import depth from the new private package location.

Post-split ownership line counts:

```text
src/services/_pdf/figures.py: 700
src/services/_pdf/_figures/triage.py: 346
src/services/_pdf/_figures/pruning.py: 372
src/services/_pdf/_figures/candidates.py: 458
src/services/_pdf/_figures/best_figure.py: 216
```

## Verification Evidence

Red test first:

```text
python -m pytest tests/test_pdf_figures_decomposition.py -q
result before move: 2 failed, 1 passed
failure basis: new private owner modules and facade import order did not exist
```

Focused affected synthetic suite:

```text
python -m pytest tests/test_pdf_figures_decomposition.py tests/test_pdf_figures_service tests/test_pdf_crop_decomposition.py tests/test_pdf_crop_service.py tests/test_pdf_internal_boundaries.py -q
result: 163 passed
```

Full default synthetic suite:

```text
python -m pytest -q
result: 2813 passed, 19 deselected, 22 warnings, 20 subtests passed
```

Lint:

```text
python -m ruff check src/services/_pdf/figures.py src/services/_pdf/_figures tests/test_pdf_figures_decomposition.py
result: All checks passed
```

Live local PDF comparison against a detached `HEAD` worktree:

```text
baseline_json:
  C:\Users\8FEE~1\AppData\Local\Temp\market-lense-figures-live-2146bd1d212e4624b7cf2afa2e532ce8\baseline.json
current_json:
  C:\Users\8FEE~1\AppData\Local\Temp\market-lense-figures-live-2146bd1d212e4624b7cf2afa2e532ce8\current.json

CAPGEMINI - 2026-Retail-Trends_ACIG.pdf
  workers_1: same_response=true; chart/table counts 12/0 -> 12/0; runtime 3.549756s -> 2.475687s
  workers_2: same_response=true; chart/table counts 12/0 -> 12/0; runtime 2.886421s -> 2.382096s
  best_figure: same_response=true; runtime 0.081147s -> 0.074622s

BRAZE - 2026 Predictions_ACIG.pdf
  workers_1: same_response=true; chart/table counts 4/2 -> 4/2; runtime 11.067861s -> 10.464671s
  workers_2: same_response=true; chart/table counts 4/2 -> 4/2; runtime 11.807596s -> 10.925895s
  best_figure: same_response=true; runtime 2.773150s -> 2.751336s
```

The affected live path is local PDF processing. It performs no OpenAI, LLM,
Drive, network, OCR-provider, or browser calls, so model/API cost remains
unchanged at zero for this service path.
