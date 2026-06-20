# Briefing Card System Design

## Status

Approved through browser review on June 20, 2026.

## Goal

Replace the existing generic briefing feature and archive cards with one reusable briefing-card system. The system mirrors the established report-card placement sizes and responsive behavior while presenting briefing-specific, decision-ready information.

## Design Decisions

- Three variants only: `small`, `medium`, and `large`.
- Cards use the report-card system's placement geometry, focus behavior, motion limits, and container-query responsive behavior.
- Briefing covers are deterministic, aspect-specific semantic-geometry images using a distinct premium executive-blue palette. They are not crops of report covers.
- Cover title text is vertically centered for every size, including `small`.
- Briefing cards use briefing content, not report provenance fields: issue date, executive summary, decision focus, executive takeaways, source-report count, and evidence-item count.
- A `New` badge appears when the canonical WordPress publication age is at least zero and less than seven days. Future-dated briefings and briefings exactly seven days old are not new.

## Card Content Contract

Every published briefing rendered by the canonical card renderer must provide a versioned contract with:

| Field | Semantic contract |
| --- | --- |
| Title | Complete normalized briefing title. |
| Title scale | One approved title-fit class. |
| Issue date | Canonical WordPress publication timestamp and display date. |
| Compact summary | Complete decision-context sentence for small cards. |
| Standard summary | Complete executive summary for medium and large cards. |
| Decision focus | One complete, actionable decision statement. |
| Executive takeaways | Exactly two complete takeaways for large cards. |
| Source report IDs | Unique IDs of published report records that support the briefing. |
| Source report count | Computed from validated source report IDs. |
| Evidence item count | Computed by summing the validated evidence-reference counts of the source reports. |
| Cover fingerprint | Versioned semantic fingerprint, including the briefing palette profile. |
| Cover assets | Complete small, medium, and large aspect-specific briefing covers. |

The renderer must reject an incomplete contract rather than generate a fallback summary, placeholder counter, or arbitrary featured image.

### Small

- 16:9 briefing cover with centered title, issue-date anchor, and optional `New` badge.
- Issue date, full title, and compact executive summary.
- Source-report and evidence-item counters with decorative inline SVG icons and visible labels.
- One `Read briefing` action.

### Medium

- 4:5 cover used in the established side-by-side medium-card layout, with centered cover title and optional `New` badge.
- Issue date, full title, standard executive summary, and decision focus.
- Source-report and evidence-item counters.
- One `Read briefing` action.

### Large

- 3:4 portrait cover used in the established featured-card layout, with centered cover title and optional `New` badge.
- Issue date, full title, standard executive summary, and decision focus.
- Exactly two executive takeaways.
- Source-report and evidence-item counters.
- One `Read briefing` action.

## Architecture

### Python cover generation

The existing deterministic cover pipeline gains a briefing palette profile rather than a second renderer or external system. The profile keeps the established semantic geometry and three aspect-specific rendering passes, while using executive blue `#0A255A` as its base and restrained steel-blue geometry accents. Briefing cover title placement is the same vertically centered protected zone for each size.

The briefing cover fingerprint is versioned and identifies the briefing palette profile. Rendering fails explicitly when a complete title cannot fit its protected zone or an asset set is incomplete.

### WordPress plugin

- `Briefing_Card_View_Model_Builder` owns briefing card-contract validation and derives counts from the linked report records.
- `Briefing_Card_Renderer` owns the three briefing markup variants only.
- `Meta` registers briefing-specific, REST-visible metadata for the versioned contract and the source report ID list.
- `Shortcodes` selects briefing card variants for the homepage feature and briefing archives. It does not compose briefing-card markup itself.
- The existing report renderer and report view-model builder are unchanged except for the public evidence-count data already required to compute grounded briefing totals.

No generic cross-content card renderer is introduced. The report and briefing renderers have distinct contracts and identical placement vocabulary.

### Theme

The block theme owns layout and visual behavior. Briefing selectors extend the canonical card layout with briefing-specific content tracks and the executive-blue cover identity. The implementation uses the established safe default layout plus container-query adaptation, preserves document order on narrow containers, and honors reduced-motion preferences.

## Data Flow

1. A briefing author selects published source reports and supplies validated briefing-specific editorial fields.
2. The cover pipeline produces the three briefing cover assets from the briefing fingerprint and palette profile.
3. WordPress persists the briefing contract, source IDs, and cover media IDs.
4. `Briefing_Card_View_Model_Builder` validates the contract, resolves the source count, and sums evidence counts from source reports.
5. `Briefing_Card_Renderer` renders one requested variant.
6. Theme CSS presents it at its card placement without changing semantics.

## Error Handling

- An invalid card schema, missing summary, missing decision focus, incomplete takeaways, invalid source ID, absent source report, invalid cover fingerprint, or incomplete cover asset set prevents rendering and is logged through the existing WordPress error path.
- Empty counts are valid only when the source report list is empty by explicit briefing contract policy; the first implementation requires at least one validated source report to avoid an unsupported briefing narrative.
- The `New` calculation is server-side and uses the same boundary rule as report cards.

## Testing

- Unit/harness tests validate the briefing contract and reject each required missing field.
- Renderer tests assert only `small`, `medium`, and `large` are accepted.
- Tests assert the selected summary, decision focus, takeaways, counters, cover, and action for every variant.
- Source-report tests assert duplicate IDs are rejected or normalized before counting, missing/unpublished reports fail validation, and evidence totals match linked report evidence counts.
- `New` boundary tests cover zero seconds, six days 23:59:59, exactly seven days, and future timestamps.
- Static migration tests reject legacy briefing-card markup in homepage and archive rendering paths.
- Browser checks cover 1440px, 1024px, 768px, and 390px; centered cover titles; no horizontal overflow; keyboard focus; and reduced-motion behavior.

## Success Criteria

- Homepage featured briefing uses the large canonical briefing card.
- Briefing archive uses the small canonical briefing card.
- Medium card remains reusable through the canonical renderer for curated briefing placements.
- Every card cover contains a vertically centered title and uses the briefing color profile.
- Every rendered card shows accurate source-report and evidence-item counts.
- `New` is visible only during the first seven days after publication.
- Existing report cards retain their current behavior.
