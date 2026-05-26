# PDF Table Heuristics Decomposition Architecture Review

## Trigger

This review is required because decomposition of
`src/services/_pdf/table_heuristics.py` introduces five focused private peer
modules inside the existing PDF extraction service family.

## Capability And Current Bounded Context

Capability: deterministic PDF table-candidate interpretation, region
formation, rejection, and deduplication.

Bounded context: the existing PDF service family canonically exposed by
`src/services/pdf_service.py`.

## Boundary Decision

This change preserves the modular monolith. It introduces a private
implementation package:

```text
src/services/_pdf/_table_heuristics/
```

The current `src/services/_pdf/table_heuristics.py` remains the internal
compatibility surface for `figures.py` and `table_candidates.py`; external
callers continue using `pdf_service`.

No new network/process boundary, deployable unit, external interaction,
contract schema, model path, or independent service entrypoint is introduced.

## Why The Boundary Is Semantic

The source module currently joins responsibilities that evolve and fail for
different reasons:

- threshold/pattern policy
- internal analysis models
- page-layout and textual band interpretation
- table-region construction and bbox adjustment
- candidate rejection, scoring, and deduplication

The selected modules align to those responsibilities. They are not arbitrary
line-count partitions: each module has a distinct table-analysis purpose and
can be reasoned about without reading unrelated candidate stages.

## Fewer-Module Assessment

A single extracted helper would only relocate the monolith. A two- or
three-module design would force page interpretation, geometry formation, and
false-positive screening back into combined modules, preserving the current
responsibility overlap.

Keeping policy and internal data models separate avoids duplicating numerous
threshold values and dataclass definitions across region and screening work.
Neither file adds an application layer; each owns shared declarations required
by multiple real capability modules.

The compatibility surface retains only execution-only helpers with no inward
capability dependency. Shared preview/text-statistics operations belong with
layout interpretation and are reexported through the facade; this avoids a
facade-to-capability-to-facade import cycle while preserving all existing
imports.

Numeric-fragment recognition also stays with layout interpretation:
`_table_fragment_is_numeric()` depends on `_cell_is_numeric()`, so both are
owned by layout and reexported for screening/callers rather than creating a
layout-to-screening-to-layout cycle.

## Cognitive Load Assessment

Existing consumers retain one import surface, so normal candidate execution
does not require new navigation. Engineers changing table behavior can go
directly to the affected concern: policy, model definitions, page layout,
region formation, or screening/deduplication. The split reduces the unrelated
code needed to inspect one table failure mode while preserving one bounded
context.

## Preservation Controls

The decomposition is movement-only unless a verified regression requires a
correction. It must preserve:

- compatibility imports from `table_heuristics.py`
- table candidate IDs, page numbers, bboxes, preview/caption values, features,
  validation decisions, and deduplication order
- candidate response/degraded-page contract semantics
- PDF parsing, rendering, page artifact caching, and worker resolution
- service log ownership and current error behavior
- absence of external calls, model costs, or uploads from table heuristics

## Verification Plan

Pre-edit affected synthetic baseline:

```text
69 passed
```

Approved real-PDF equivalence target:

```text
cache/1Wm4HRYQ0ImIAEx4-tw2vz1T2i2ignIBD.pdf
stored report name: year-in-review-2022.pdf
candidate_count: 21
table_count: 12
degraded_pages: 0
single-worker pre-refactor elapsed_seconds: 51.119
```

The post-refactor comparison must reproduce each raw table candidate's ID,
page, rounded bbox, preview, caption, and typed features and must retain zero
degradation/failure counts. Local elapsed time is compared for material
regression investigation; no algorithm or I/O path is intended to change.

Required completion evidence:

- structural ownership/compatibility test fails before extraction and passes
  after extraction
- affected and default synthetic suites pass
- configured formatting, type, architecture, forbidden-patching, hygiene,
  coverage, mutation, and quality-regression gates pass
- the approved local previously processed PDF comparison passes after
  synthetic gates

Execution evidence will be recorded in this review after implementation and
verification.

## Execution Evidence

Implemented ownership:

- `src/services/_pdf/table_heuristics.py`: `402` lines; compatibility facade
  retaining execution-only helpers.
- `src/services/_pdf/_table_heuristics/regions.py`: `1,065` lines; region
  formation and bbox adjustment.
- `src/services/_pdf/_table_heuristics/screening.py`: `996` lines; rejection,
  quality scoring, overlap, and deduplication.
- `src/services/_pdf/_table_heuristics/layout.py`: `733` lines; page-layout,
  text interpretation, preview/statistics, and numeric fragment recognition.
- `src/services/_pdf/_table_heuristics/policy.py` and `models.py`: shared
  threshold/pattern policy and immutable private records.

Regressions detected and fixed during implementation:

- Initial mechanical extraction omitted the five `@dataclass(frozen=True)`
  decorators in `models.py`; focused behavior tests failed on construction of
  moved records. The decorators were restored before the implementation
  commit.
- The extracted capability files initially omitted original module-level
  dependencies (`statistics`, `math`, `re`, and typing imports). Focused tests
  and Ruff detected the missing imports; the imports were restored before the
  implementation commit.

Synthetic verification results:

```text
Focused affected suite: 70 passed
Broader affected PDF/service suite: 154 passed, 9 deselected
Default non-integration suite with coverage: 2617 passed, 16 deselected,
  15 subtests passed
Formatting/link/architecture/forbidden-patching/hygiene/type gates: passed
Coverage: global 82.64%, services 82.04%, generators 86.55%,
  orchestrators 84.27% (all thresholds passed)
Mutation gate: passed
Quality regression gate: passed, including candidate extraction metrics
```

The full synthetic run emitted existing resource/deprecation warnings outside
the modified table-heuristics package; no affected assertion or quality gate
failed.

Approved previously processed PDF comparison:

```text
source: cache/1Wm4HRYQ0ImIAEx4-tw2vz1T2i2ignIBD.pdf
report: year-in-review-2022.pdf
mode: local single-worker extraction to temporary output only
candidate_count: 21 -> 21
table_count: 12 -> 12
degraded_pages: [] -> []
triage_failure_count: 0 -> 0
extraction_failure_count: 0 -> 0
table IDs, pages, rounded bboxes, preview text, captions, typed features:
  exact match
elapsed_seconds: 54.254 pre-refactor -> 51.086 post-refactor
```

This comparison performs no upload or model request and detected no behavior,
quality, speed, or cost regression in the affected local extraction path.
