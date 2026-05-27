# PDF Visual Candidate Semantic Decomposition Review

## Trigger

This review is required because decomposition of
`src/services/_pdf/visual_candidates.py` introduces three focused private
peer modules inside the existing PDF extraction service family.

## Capability And Boundary

Capability: deterministic chart and infographic candidate extraction from
local PDF page artifacts.

Bounded context: the existing PDF service family canonically exposed by
`src/services/pdf_service.py`. The existing
`src/services/_pdf/visual_candidates.py` module remains the compatibility
facade used by `figures.py`, `table_candidates.py`, and test builders.

This is an internal modular-monolith decomposition. It adds no external
system boundary, deployable process, service entrypoint, contract/schema
change, logging owner, prompt/config path, or provider interaction.

## Semantic Ownership

The private implementation family is:

- `_visual_candidates/raster.py`: raster probe caching, render/profile
  calculation, image-card qualification, OCR density, and chart confidence.
- `_visual_candidates/screening.py`: caption/context interpretation and
  deterministic false-positive or dense-recovery screening.
- `_visual_candidates/extraction.py`: page context construction, candidate
  emission/overlap handling, ordering, and worker coordination.

The facade explicitly imports owners in dependency order:

```text
visual_heuristics -> raster -> screening -> extraction -> visual_candidates
```

Existing callers continue importing through `visual_candidates.py`, so the
normal PDF service call path gains no competing entrypoint or forwarding
layer.

## Boundary Decision

The split is semantic rather than line-count driven. Raster qualification,
textual screening, and extraction coordination have different deterministic
inputs and investigation paths. Each private module owns implementation
bodies rather than forwarding calls.

A two-module split would require combining image classification with text
rejection or with worker/candidate sequencing, preserving unrelated reasons
for change in one module. Three owners are the smallest boundary that keeps
those responsibilities separate while retaining a single compatibility
surface.

The recorded `CONSOLIDATED_TODO.md` optimization to precompute per-page visual
relationships is deliberately deferred. Changing relationship scans during
source movement would prevent exact attribution of output or timing changes.

## Preservation Controls

This movement-only change must preserve:

- heuristic thresholds, branch order, candidate ordering, relationship scans,
  raster/PDF operations, threading behavior, cache behavior, and scoring
- all exports used through `visual_candidates.py`
- candidate contracts, extraction stats, crop-pack JSON, and crop bytes
- the `pdf_service.py` canonical service boundary
- local-only validation with no Drive, OpenAI, OCR-provider, model, or browser
  acquisition activity

## Pre-Edit Evidence

The structural ownership test was added and run before source movement:

```text
tests/test_pdf_visual_candidates_decomposition.py: 3 failed
failure basis: new owner modules and facade exports did not yet exist
```

The pre-edit local-PDF baseline was written outside the repository and
captured direct visual extraction at one and two workers, complete canonical
candidate/stats output, candidate-pack JSON with crop hashes, and five
single-worker runtime samples:

```text
KANTAR - Media Reactions 2025 APAC Webinar Deck_ACIG.pdf
  charts: 9; tables: 11
  degraded_pages: []; triage_failure_count: 0; extraction_failure_count: 0
  median single-worker collect_candidates runtime: 3.969709 seconds

CAPGEMINI - 2026-Retail-Trends_ACIG.pdf
  charts: 12; tables: 0
  degraded_pages: []; triage_failure_count: 0; extraction_failure_count: 0
  median single-worker collect_candidates runtime: 2.029933 seconds
```

## Implemented Ownership

Post-split measured ownership from `python scripts/count_long_files.py
--min-lines 500`:

```text
src/services/_pdf/visual_candidates.py: 164 lines
src/services/_pdf/_visual_candidates/extraction.py: 1,176 lines
src/services/_pdf/_visual_candidates/screening.py: 684 lines
src/services/_pdf/_visual_candidates/raster.py: 558 lines
```

The new decomposition and boundary enforcement tests pass, and the existing
PDF figures/crop behavior suite passes through the unchanged compatibility
surface.

A direct AST movement audit against the pre-refactor `HEAD` source confirmed
that `41` moved class/function definitions and `32` owned constants are
unchanged apart from location and formatting.

## Completion Evidence

Configured synthetic and policy verification passed:

```text
Focused affected suite: 169 passed
Full default suite with coverage: 2,635 passed, 17 deselected
Formatting, risk-policy, split-symbol, type-check, architecture-import,
  forbidden-patching, repository-hygiene, quality-ledger,
  remediation-runbook, backlog-source, contract-schema, and WordPress gates:
  passed
Coverage: global 82.65%, services 82.06%, generators 86.55%,
  orchestrators 84.30% (all thresholds passed)
Mutation gate: passed
Quality regression gate: passed, including candidate extraction metrics
Prompt fixture regression: token totals and estimated cost unchanged; passed
```

The full synthetic run emitted existing browser-use deprecation and resource
warnings outside the changed PDF visual-candidate modules; no assertion or
gate failed.

Approved local real-PDF comparison ran the PDF service and candidate-pack
generator only, writing crop artifacts to temporary directories:

```text
KANTAR - Media Reactions 2025 APAC Webinar Deck_ACIG.pdf
  charts/tables: 9 / 11 -> 9 / 11
  degraded_pages: [] -> []
  triage_failure_count: 0 -> 0
  extraction_failure_count: 0 -> 0
  direct visual candidates/stats at workers 1 and 2, canonical candidates/stats,
    packaged JSON, and crop SHA256 hashes: exact match
  median single-worker runtime, 5 runs: 3.969709 -> 3.931865 seconds

CAPGEMINI - 2026-Retail-Trends_ACIG.pdf
  charts/tables: 12 / 0 -> 12 / 0
  degraded_pages: [] -> []
  triage_failure_count: 0 -> 0
  extraction_failure_count: 0 -> 0
  direct visual candidates/stats at workers 1 and 2, canonical candidates/stats,
    packaged JSON, and crop SHA256 hashes: exact match
  median single-worker runtime, 5 runs: 2.029933 -> 2.020573 seconds
```

Both measured medians satisfy the selected zero-slowdown criterion. This
local gate performs no Drive, OpenAI, OCR-provider, model, or browser
acquisition activity and found no output, cost, or runtime regression in the
affected path.
