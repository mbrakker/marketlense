# PDF Panel Detection Semantic Decomposition Review

## Trigger

This record documents a movement-only internal split of
`src/services/_pdf/_visual_heuristics/panel_detection.py` into two semantic
sibling modules. The change adds fewer than three peer modules, so it does not
cross the mandatory architecture-review trigger in `AGENTS.md`; the rationale
and regression evidence are recorded because the code is on a quality-critical
PDF extraction path.

## Capability And Boundary

Capability: deterministic visual panel detection for local PDF candidate
extraction.

Bounded context: the existing PDF service family canonically exposed by
`src/services/pdf_service.py`, with
`src/services/_pdf/visual_heuristics.py` retained as the existing internal
facade.

This change preserves the modular monolith. It introduces no service
entrypoint, process boundary, network interaction, provider/model request,
prompt/config change, or contract/schema change.

## Semantic Ownership

The private visual-heuristics family now owns panel behavior as follows:

- `panel_text.py` owns deterministic title, caption, numeric/metric,
  component-text, footer/banner, and compact-stat interpretation.
- `panel_geometry.py` owns deterministic component grouping and panel bounds
  extension or clamping.
- `panel_detection.py` owns detector decisions, candidate shadowing, layout
  rejection, panel candidate coordination, and `_panel_chart_rects()`.

Dependency direction remains acyclic:

```text
chart_layout -> panel_text -> panel_geometry -> panel_detection -> collectors
```

The facade exports the same internal compatibility symbols for existing
consumers in `figures.py`, `visual_candidates.py`, `crop.py`, and test
builders.

## Boundary Decision

The split is semantic rather than cosmetic. Text interpretation and geometry
construction use different deterministic inputs and failure analysis paths,
while the detector coordinator retains candidate-ordering and rejection
decisions. Neither new module forwards calls without owning behavior.

The deferred precomputed visual-relationships optimization remains outside
this work. Combining algorithm changes with ownership movement would prevent
exact attribution of output or timing differences.

## Preservation Controls

The implementation must preserve:

- thresholds, branching order, candidate ordering, and PDF operations
- panel rectangle and caption output
- complete candidate contracts, extraction statistics, packaged JSON, and
  crop bytes
- the `pdf_service.py` canonical boundary and `visual_heuristics.py` facade
- local-only validation with no Drive, OpenAI, OCR-provider, or browser
  acquisition activity

## Pre-Edit Evidence

Focused affected synthetic baseline:

```text
108 passed
```

Structural ownership test RED confirmation before source movement:

```text
tests/test_pdf_panel_detection_decomposition.py: 1 failed, 1 passed
failure: panel_text.py did not yet exist
```

The local pre-edit baseline was written outside the repository and confirmed
the approved PDFs exercise panel logic:

```text
KANTAR - Media Reactions 2025 APAC Webinar Deck_ACIG.pdf
  panel_count: 11 across 8 pages
  candidate_count: 20
  median single-worker runtime, 3 runs: 3.977910 seconds
  degraded_pages: []; triage_failure_count: 0; extraction_failure_count: 0

CAPGEMINI - 2026-Retail-Trends_ACIG.pdf
  panel_count: 7 across 7 pages
  candidate_count: 12
  median single-worker runtime, 3 runs: 2.154625 seconds
  degraded_pages: []; triage_failure_count: 0; extraction_failure_count: 0
```

## Implementation Evidence

Post-split measured ownership from `python scripts/count_long_files.py
--min-lines 500`:

```text
src/services/_pdf/_visual_heuristics/panel_detection.py: 1,002 lines
src/services/_pdf/_visual_heuristics/panel_geometry.py: 988 lines
src/services/_pdf/_visual_heuristics/panel_text.py: 952 lines
```

The focused post-movement suite passed:

```text
164 passed
```

The split-symbol, formatting, type-check, architecture-import, and
forbidden-patching gates also passed after movement and facade rewiring.

## Completion Evidence

Configured synthetic and policy verification passed:

```text
Focused affected suite: 164 passed
Full default suite with coverage: 2,632 passed, 17 deselected
Formatting, risk-policy, split-symbol, type-check, architecture-import,
  forbidden-patching, repository-hygiene, quality-ledger,
  remediation-runbook, backlog-source, contract-schema, and WordPress gates:
  passed
Coverage: global 82.64%, services 82.05%, generators 86.55%,
  orchestrators 84.30% (all thresholds passed)
Mutation gate: passed
Quality regression gate: passed, including candidate extraction metrics
Prompt fixture regression: token totals and estimated cost unchanged; passed
```

The full synthetic run emitted existing browser-use deprecation and resource
warnings outside the changed PDF panel modules; no assertion or gate failed.

Approved local real-PDF comparison ran the PDF service and candidate-pack
generator only, with crop files written to temporary output directories:

```text
KANTAR - Media Reactions 2025 APAC Webinar Deck_ACIG.pdf
  panels/pages: 11 / 8 -> 11 / 8
  candidates: 20 -> 20
  degraded_pages: [] -> []
  triage_failure_count: 0 -> 0
  extraction_failure_count: 0 -> 0
  panel rectangles/captions, candidate contracts, packaged JSON, crop hashes:
    exact match
  median single-worker runtime: 3.977910 -> 3.716014 seconds

CAPGEMINI - 2026-Retail-Trends_ACIG.pdf
  panels/pages: 7 / 7 -> 7 / 7
  candidates: 12 -> 12
  degraded_pages: [] -> []
  triage_failure_count: 0 -> 0
  extraction_failure_count: 0 -> 0
  panel rectangles/captions, candidate contracts, packaged JSON, crop hashes:
    exact match
  median single-worker runtime: 2.154625 -> 1.995182 seconds
```

Both measured runtime ratios were below `1.0`, within the acceptance threshold
of no more than 10 percent slowdown. This local gate performs no Drive,
OpenAI, OCR-provider, or browser-acquisition activity and detected no quality,
speed, or cost regression in the affected path.
