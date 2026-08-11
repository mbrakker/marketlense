# Document-map substantive-quality validation

## Objective

Prevent schema-valid but content-free document maps from advancing report
generation, regardless of the report publisher or source route. Validate the
change with a fresh, isolated live workflow through generated HTML only; do not
publish externally.

## Root cause

The affected maps for `1peitcvhjunidq7dq-kuxwxi8xjbja16q` and
`1cv8ypeywpjevvnkaolx9n-s79az36idc` contained only report/vector-store IDs and
the `doc_map` pack label. `doc_map` confidence counted non-empty structural
fields (`title`, `doc_id`, `sections`, and section summaries), so those payloads
received a generated/keep status despite containing no source-derived subject
matter. The same structural check allowed an invalid cache entry to be reused.

## Plan

1. Add failing unit coverage for identifier-and-metadata-only document maps,
   including recovery to a substantive replacement and rejection of a cached
   placeholder. Keep a legitimate, source-topic map as the positive control.
2. In `src/generators/evidence_packs/doc_map_strategy.py`, make the shared
   document-map summary distinguish structural presence from substantive,
   source-derived language. Treat runtime IDs, field labels, and metadata-only
   boilerplate as control text, not document content. Return a stable reason and
   bounded quality counters for logging/state.
3. Route the existing generator confidence and cache-adaptation paths through
   that shared assessment. A low-quality primary response must enter the
   existing bounded structured-output recovery sequence; a low-quality cache
   must be regenerated rather than returned.
4. Document the runtime contract in `docs/docpacks/pack-specs.md` and make the
   prompt explicitly prohibit identifier/metadata substitutes.
5. Run targeted document-map tests, formatting/lint checks as available, inspect
   the final diff, then execute an isolated live feature run using the two
   retained, checksum-verified acquisition artifacts. Seed their already
   verified source identity in the isolated store, then run admission, ingest,
   analysis, report generation, and HTML rendering. Check the new document maps
   for substantive source topics and record the retained output path and any
   typed blockers.

## Acceptance criteria

- An ID/vector-store/pack-name-only map is rejected before downstream artifact
  generation and causes bounded model recovery.
- A cached map with the same defect is not reused.
- A normal source-topic map remains accepted without publisher-specific rules.
- The live run produces a non-placeholder document map and generated HTML, with
  no external publication action.
