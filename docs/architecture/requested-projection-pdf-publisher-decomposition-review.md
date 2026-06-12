# Requested Projection/PDF/Publisher Decomposition Review

Date: 2026-06-12

## Scope

This review covers the movement-only split requested for:

- `src/generators/analytics_projection_generator.py`
- `src/generators/_report_selection_generator/crop_refine.py`
- `src/services/_pdf/_visual_heuristics/panel_detection.py`
- `src/services/_publisher_inventory_service/discovery_activity.py`

## Boundary Decision

The change preserves the existing modular-monolith boundaries:

- Analytics projection remains a generator boundary exposed through `analytics_projection_generator.py`.
- Report-selection crop refinement remains inside the existing report-selection generator family.
- PDF panel detection remains inside the canonical PDF service internals exposed through `visual_heuristics.py`.
- Publisher discovery activity remains inside the canonical publisher-inventory service boundary.

No new public service boundary, deployable unit, external system boundary, retry path, prompt namespace, or alternate orchestration path was introduced.

## New Private Owners

- `src/generators/_analytics_projection/`
  - `common.py`: deterministic normalization, IDs, lineage, hashing.
  - `builders.py`: projected section/finding/metric/quote/claim/tag/category/figure rows.
  - `text_payloads.py`: vector text rendering helpers.
  - `vector_queue.py`: vector queue metadata and row assembly.
  - `workflow.py`: public `build_projection` workflow.
- `src/generators/_report_selection_generator/_crop_refine/`
  - `cache.py`: crop-refine keys, cache paths, cache load/write, bbox parsing, worker limits.
  - `workflow.py`: `select_refined_candidate_items`.
- `src/services/_pdf/_visual_heuristics/_panel_detection/`
  - `shadowing.py`: panel shadowing, clipping, and neighbor-bound decisions.
  - `candidates.py`: contents-page guard, panel candidate assembly, title-band merge.
- `src/services/_publisher_inventory_service/_discovery_activity/`
  - `constants.py`: report discovery constants and compiled patterns.
  - `urls.py`: URL/path/domain classification helpers.
  - `titles.py`: anchor title normalization and fallback helpers.
  - `candidates.py`: HTML/component candidate extraction and confidence scoring.
  - `browser_state.py`: rendered-state route decisions and route summaries.

## Movement Audit

Audit command compared current private owners against `HEAD:<original-file>` top-level AST blocks.

- Moved top-level symbols: `102`
- Unchanged moved symbols: `102`
- Changed moved symbols: `0`
- Missing symbols: `0`
- Facade-owned definitions after split: `0`

The original files now remain compatibility facades over the private owners.

## Verification Scope

Focused synthetic verification covers analytics projection, crop-refine selection, PDF panel heuristics, and publisher discovery parsing/traversal tests. Live verification should cover analytics projection persistence/readback, report-selection crop refinement, PDF panel heuristics against real PDF fixtures, and publisher-inventory discovery routes.
