# Report Card And Semantic Cover System Design

## Status

Approved through visual review on June 13, 2026.

The user approved:

- three reusable report-card variants only: small, medium, and large;
- Semantic Visual Grammar for report-cover geometry;
- a complete compact TLDR for small cards and a complete standard TLDR for medium and large cards;
- full report-title fitting on the large hero cover;
- content-independent alignment when multiple cards share a row;
- distinct global and regional geography pictograms;
- a `New` badge for reports less than seven days old.

## Goal

Replace the portal's inconsistent report-card presentations and cropped source imagery with one reusable, premium report-card system. Each report receives a deterministic semantic visual identity derived from its content, rendered consistently across the three card variants.

## Scope

This design covers:

- report-card content contracts;
- small, medium, and large report-card presentation;
- compact and standard card TLDR generation;
- two large-card key insights;
- semantic cover-geometry classification and rendering;
- publish-date, geography, and covered-period metadata;
- the seven-day `New` rule;
- replacement of existing report-card renderings across the WordPress portal;
- validation, backfill, testing, documentation, and release archives.

It does not redesign non-report cards, report-detail page content, navigation, filters, taxonomy definitions, or publisher profiles.

## Design Positioning

- Narrative role: each card is an executive intelligence brief, not a generic article teaser.
- Viewing distance: small cards support rapid archive scanning; medium cards support comparison; large cards support featured-report evaluation.
- Visual temperature: quiet, authoritative, analytical, premium, and evidence-led.
- Capacity: titles and TLDRs remain complete. Density is controlled through bounded content contracts rather than visual clipping.

## Visual System

The cards preserve the existing MarketLense visual language:

- deep navy base: `#061A31`;
- elevated navy: `#082B54`;
- restrained signal blue: `#0B5CAD`;
- cool page surface: `#EEF3F8`;
- subtle border: `#D8E0EA`;
- primary ink: `#10243E`;
- muted text: `#637086`;
- `New` accent: muted rust `#B64B36`.

Light cyan, electric blue, vivid gradients, photographic stock backgrounds, and category-color rainbows are excluded. Geometry uses low-opacity steel-blue, white, and navy tonal variation.

Existing portal typefaces remain authoritative. Editorial serif typography is used for report titles; the existing sans-serif is used for metadata, TLDRs, labels, and actions.

Cards use restrained elevation:

- base: subtle border and low shadow;
- hover and keyboard focus: maximum `translateY(-2px)` plus a slightly stronger shadow;
- reduced-motion mode: no transform and no nonessential transition.

## Canonical Card Content Contract

Every published report must expose the following card-ready fields before the new renderers are enabled:

| Field | Contract |
| --- | --- |
| Report title | Complete, normalized title. No ellipsis or mid-word truncation. |
| Card title scale | One validated presentation class from the approved title scale. |
| Publisher | Complete normalized publisher name. |
| Published date | Canonical WordPress publication timestamp and formatted display value. |
| Geography label | Normalized human-readable scope. |
| Geography scope | `global`, `regional`, `country`, or `unknown`. |
| Covered period | Complete normalized report period, distinct from publication date. |
| Compact TLDR | One complete summary of at most 18 words. Used by small cards. |
| Standard TLDR | One complete summary of at most 45 words. Used by medium and large cards. |
| Key insights | Exactly two ranked, complete insights for large cards. |
| Cover fingerprint | Valid semantic geometry fingerprint and deterministic seed. |
| Cover assets | Valid small, medium, and large cover outputs from the same fingerprint. |

The compact and standard TLDRs are separately authored projections of the same grounded report evidence. The compact TLDR is not a character slice or first-line extraction from the standard TLDR.

The latest approved TLDR requirement supersedes the original small-card one-line-summary concept. A small card displays the complete compact TLDR in its reserved text track, normally across two or three lines.

## Text Fitting And Alignment

Visual alignment must not depend on whether a title or TLDR occupies fewer lines.

At normal card-grid breakpoints:

- each variant uses an explicit internal CSS grid;
- title, publisher, metadata, TLDR, insights, and footer occupy named tracks;
- title tracks reserve the approved maximum line capacity;
- TLDR tracks reserve the approved maximum line capacity for that variant;
- footer actions align to the same baseline across sibling cards;
- empty optional metadata does not collapse the metadata track.

Text rules:

- no `line-clamp` for report titles or TLDRs;
- no ellipsis for report titles or TLDRs;
- no `overflow: hidden` or `overflow: clip` on semantic title or TLDR containers;
- `text-wrap: balance` is a progressive enhancement for short titles;
- `text-wrap: pretty` is a progressive enhancement for TLDRs and insights;
- long unbroken tokens use safe wrapping without changing DOM order.

The report-processing/import contract assigns a validated card-title scale class. The class selects the largest approved font size that keeps the complete title inside the normal three-line card track at the canonical variant width. If no approved class fits, the payload fails with `card_title_overflow`; the renderer does not clamp it.

At narrow widths, increased text spacing, or 200% browser zoom, cards may grow vertically and reflow to one column. Content preservation takes priority over equal row height in accessibility reflow states.

## Small Card

The small card is the default high-density listing component.

It contains:

- generated wide cover;
- optional `New` badge;
- full report title in a reserved three-line title track;
- publisher;
- publish date, geography, and covered period pictograms with labels;
- complete compact TLDR, maximum 18 words;
- one consistent report action.

It does not contain taxonomy chips, counters, quotes, or key-insight bullets.

Primary usage:

- report archive grids;
- search results;
- latest-report grids;
- related reports;
- topic and publisher report listings where scanning density is primary.

## Medium Card

The medium card provides additional evaluation detail without becoming a featured module.

It contains:

- generated medium cover;
- optional `New` badge;
- full report title in a reserved three-line title track;
- publisher;
- publish date, geography, and covered period pictograms with labels;
- complete standard TLDR, maximum 45 words;
- one consistent report action.

Primary usage:

- curated report rows;
- publisher and topic landing highlights;
- homepage or section modules where more context is required than a listing card provides.

The desktop composition places media and body side by side. It stacks in document order on narrow containers without cropping the cover.

## Large Card

The large card is the only featured-report card.

It contains:

- generated portrait hero cover;
- optional `New` badge;
- full report title;
- publisher;
- publish date, geography, and covered period pictograms with labels;
- complete standard TLDR, maximum 45 words;
- exactly two ranked key-insight bullets;
- one primary report action.

The vertical hero always contains the complete report name. The cover renderer selects the largest approved title font that fits the fixed title rectangle. Publisher remains anchored at the top and covered period remains anchored at the bottom. If the complete title cannot fit at the minimum approved size, cover generation fails explicitly rather than truncating the title.

Primary usage:

- homepage featured report;
- a section-level featured report;
- any single-report promotional placement that currently uses a bespoke report feature.

## Metadata Pictograms

The metadata row uses one consistent inline SVG set:

- publication date: calendar pictogram;
- global or multi-market geography: globe pictogram;
- region, country, city, or local market: locator pictogram;
- covered period: calendar-range pictogram.

The geography classifier follows these rules:

- `global`: explicit global, worldwide, international, or multiple named markets;
- `regional`: one named supranational region such as Europe or Asia Pacific;
- `country`: one named country, state, city, or local market;
- `unknown`: no reliable geography value.

Regional and country scopes use the locator pictogram. Unknown geography is omitted from speech and display, while the card's metadata track remains stable.

Pictograms are decorative and use `aria-hidden="true"`; the adjacent visible text provides the accessible value.

## New Badge

A report is new when:

```text
age_seconds >= 0 and age_seconds < 7 * DAY_IN_SECONDS
```

The calculation uses the canonical publication timestamp. A future-dated report is not new. The badge disappears at exactly seven days. The rule is computed on the server and is not duplicated in client-side JavaScript.

## Semantic Cover Direction

The approved direction is **Semantic Visual Grammar**.

The cover does not decorate a category with a literal icon. It expresses the report's evidence structure as abstract geometry. The same report retains one recognizable visual identity across every card size.

The cover palette is shared across all reports. Differentiation comes from geometry, density, direction, geography treatment, and a stable report seed rather than unrelated colors.

## Cover Fingerprint Contract

Report processing produces a versioned cover fingerprint containing:

- `geometry_family`;
- `evidence_shape`;
- `direction`;
- `geography_scope`;
- `evidence_density`;
- `domain_layer`;
- `seed`;
- `selection_reason`;
- `schema_version`.

Allowed evidence shapes:

- `trend`;
- `comparison`;
- `distribution`;
- `flow`;
- `network`;
- `concentration`;
- `hierarchy`;
- `cycle`;
- `uncertainty`;
- `system`.

Allowed directions:

- `rising`;
- `falling`;
- `stable`;
- `volatile`;
- `converging`;
- `diverging`;
- `cyclical`;
- `neutral`.

Evidence density is `metric_rich`, `balanced`, or `qualitative`. The domain layer is a restrained secondary texture selected from normalized report taxonomy, not raw duplicate WordPress slugs.

## Geometry Families

The grammar provides 16 families. This is enough variation to represent the current report corpus while remaining testable and visually coherent.

| Family | Selection criterion |
| --- | --- |
| Ascending Trajectory | Dominant directional trend is rising or accelerating. |
| Descending Trajectory | Dominant directional trend is falling or contracting. |
| Volatility Corridor | The report emphasizes fluctuation, instability, or changing ranges. |
| Convergence Funnel | Segments, scenarios, or measures move toward a common state. |
| Divergence Fan | Segments, scenarios, or measures spread apart. |
| Parallel Bands | Direct comparison without a meaningful rank or directional winner. |
| Ranked Strata | Ordered benchmarks, maturity levels, leaders, or tiers dominate. |
| Distribution Field | Spread, cohorts, segmentation, dispersion, or population shape dominates. |
| Concentration Core | Market share, dominance, clustering, or concentration dominates. |
| Flow Channels | Journeys, funnels, supply chains, migration, or movement dominates. |
| Network Constellation | Relationships, ecosystems, dependencies, or connected actors dominate. |
| Hierarchy Terraces | Layered operating models, priorities, or nested structures dominate. |
| Cycle Orbit | Recurrence, seasonality, feedback loops, or repeating stages dominate. |
| Forecast Horizon | Outlooks, scenarios, projections, or future time horizons dominate. |
| Uncertainty Envelope | Risk ranges, confidence bands, ambiguity, or scenario spread dominates. |
| System Matrix | Multi-factor transformation, operating systems, or interacting frameworks dominate. |

Selection priority is deterministic:

1. Use the dominant evidence shape from the grounded cover-semantics artifact.
2. Apply direction when it selects a more specific family.
3. Prefer forecast or uncertainty families when forward scenarios or ranges are central to the report thesis.
4. Resolve ties using evidence density, then the stable seed.
5. Record the selected family and reason in structured logs.

WordPress never chooses or changes the geometry family at render time.

## Geometry Modifiers

Each family accepts restrained modifiers without becoming a new family:

- geography: global mesh or regional contour emphasis;
- density: sparse, balanced, or dense mark count;
- domain: subtle grid, wave, cohort, route, contour, or circuit texture;
- stable seed: line positions, node positions, and phase offsets.

Modifiers must not add literal category illustrations. They remain abstract and subordinate to the primary family.

## Cover Asset Generation

The system renders three aspect-specific PNG assets from one fingerprint and seed:

- small: `1600 x 900` (`16:9`) wide listing cover;
- medium: `1200 x 1500` (`4:5`) medium-card cover;
- large: `1200 x 1600` (`3:4`) portrait hero cover.

These are separate compositions, not crops of one raster image. Geometry is recalculated in normalized coordinates for each aspect ratio so focal forms, publisher, title, and period remain inside protected zones.

Each cover contains:

- publisher at the fixed top anchor;
- complete report title in the central protected title zone;
- covered period at the fixed bottom anchor;
- semantic geometry behind the text;
- no category label unless it is part of a future separately approved design.

The renderer is deterministic. Identical fingerprint, seed, text, fonts, and configuration produce identical cover bytes.

Cover images are decorative duplicates of adjacent card text and use empty alternative text. The semantic title, publisher, and covered period remain present as HTML in the card body.

## Architecture

The implementation preserves the existing modular monolith and existing external-system boundaries.

### Python Report Processing

- Contracts remain in the existing contracts layer and receive explicit schema-version changes.
- The existing summary artifact gains `card_tldr_compact`; the existing `tldr` becomes the standard card TLDR and is validated at 45 words.
- Cover semantics are produced as a dedicated grounded artifact in their own prompt namespace.
- The existing cover-image generator maps the fingerprint to a geometry family and assembles render requests.
- The existing cover-image service performs only filesystem/font/image rendering I/O.
- The existing cover-image orchestrator owns sequencing, retries, backoff, and outcome state.
- Cover generation produces a versioned three-asset result rather than one reusable cropped image.

No new external service, process, deployable component, or peer service entrypoint is introduced.

### WordPress Plugin

- `Report_View_Model_Builder` remains the canonical presentation-data builder.
- It validates and exposes the compact TLDR, standard TLDR, two key insights, geography scope, `is_new`, and three cover assets.
- A focused `Report_Card_Renderer` class owns the three report-card markup variants.
- Existing shortcode methods delegate report-card markup to this renderer.
- The current large shortcode file does not receive new card composition logic.
- Renderer input is a normalized view model plus one enum-like size value: `small`, `medium`, or `large`.
- There is no fourth generic, legacy, or context-specific report-card renderer.

### WordPress Theme

- The block theme owns card layout, tokens, responsive behavior, focus states, and container-query adaptations.
- Theme patterns and templates select one of the three plugin-rendered variants.
- Existing report placements are migrated to the appropriate canonical variant.
- Non-report cards retain their existing components.

This adds one semantically owned plugin module and does not split a module into three or more peers. No mandatory architecture-review trigger is introduced.

## Data Flow

1. Report analysis produces grounded summary, ranked insights, taxonomy, geography, and covered-period data.
2. Summary generation emits a complete standard TLDR and complete compact TLDR.
3. Cover-semantics generation emits the versioned fingerprint.
4. The cover generator deterministically selects one geometry family and renders three aspect-specific assets.
5. The report artifact and publish workflow persist card fields and cover-asset references.
6. WordPress import validates the complete payload before publication or update.
7. `Report_View_Model_Builder` adapts stored fields into one normalized card view model.
8. `Report_Card_Renderer` renders the requested canonical variant.
9. Theme CSS controls responsive presentation without changing content semantics.

## Error Handling

Python validation failures raise typed, non-retryable `AppError` values. Required error codes include:

- `card_tldr_compact_invalid`;
- `card_tldr_standard_invalid`;
- `card_title_overflow`;
- `card_key_insights_invalid`;
- `cover_fingerprint_invalid`;
- `cover_geometry_invalid`;
- `cover_title_overflow`;
- `cover_asset_set_incomplete`.

Transient filesystem or rendering failures remain retryable only when the existing error taxonomy classifies them as transient. Retry decisions remain in the orchestrator.

WordPress must not synthesize, shorten, or clip missing card intelligence. An incomplete imported card payload is rejected and logged. The old card renderer remains active during backfill; the global switch to the new renderer occurs only after the migration audit reports zero invalid published reports.

## Structured Logging

New Python events use the existing structured logging system and include `run_id`, `task_id`, `span_id`, `module`, `role`, and `event`.

Logged events include:

- normalized TLDR lengths and validation results;
- selected cover prompt namespace, prompt hash, exact redacted rendered prompt, and model parameters;
- raw and adapted cover-semantics response;
- geometry selection inputs, selected family, seed, and reason;
- cover render start and completion for each size;
- measured title fit class or overflow failure;
- final three-asset outcome.

Secrets and unrelated report content are not added to logs.

## Migration And Rollout

Rollout is staged to avoid runtime fallbacks:

1. Add and verify versioned contracts, prompts, validation, semantic geometry, and three-asset cover rendering.
2. Regenerate compact TLDRs, standard TLDR validation, two key insights, fingerprints, and cover assets for every published report.
3. Publish the new fields and asset references to WordPress while legacy card markup remains active.
4. Run a WordPress audit that reports missing or invalid fields per report.
5. Enable the three canonical renderers only when the audit returns zero invalid published reports.
6. Replace every report-card placement across templates, patterns, shortcodes, archive, search, topic, publisher, related-report, and featured-report contexts.
7. Remove obsolete report-card CSS and markup only after equivalence tests prove no report placement depends on them.
8. Regenerate installable theme and plugin ZIP archives after tests and browser verification pass.

## Testing

### Python Contracts And Generation

- Serialization round-trip and schema snapshot tests cover every added or changed dataclass.
- Positive tests verify complete 18-word-or-shorter compact TLDRs and 45-word-or-shorter standard TLDRs.
- Failure tests reject over-limit, empty, sentinel, clipped, or ellipsis-ended TLDRs.
- Key-insight tests require exactly two complete nonempty values.
- Table-driven geometry tests cover all 16 family mappings and tie-breaking rules.
- Determinism tests assert identical fingerprints and seeds produce identical outputs.
- Mutation-sensitive tests fail if geometry selection is replaced with a constant family.
- Cover-service integration tests render all three assets and assert dimensions, output existence, and complete title fit.
- A title stress fixture covers the current 100-character live title.
- An impossible-title fixture raises `cover_title_overflow` rather than producing clipped output.
- Generator and orchestrator tests assert required structured log fields, retry propagation, attempt counts, and state transitions.

### WordPress

- View-model harness tests validate all canonical card fields and reject incomplete payloads.
- Boundary tests cover `New` at zero seconds, six days 23:59:59, exactly seven days, and future timestamps.
- Geography tests verify globe, locator, and omitted-unknown behavior.
- Renderer tests verify that only `small`, `medium`, and `large` are accepted.
- Small-card tests assert compact TLDR use and absence of key insights.
- Medium-card tests assert standard TLDR use and absence of large-only insights.
- Large-card tests assert standard TLDR use and exactly two insights.
- Output escaping follows WordPress escaping-at-output rules for text, attributes, and URLs.
- Static migration tests fail if obsolete report-card classes or bespoke report-card markup remain in portal templates and patterns.

### Browser Verification

- Verify representative grids at 1440px, 1024px, 768px, and 390px.
- Verify multiple adjacent cards with one-, two-, and three-line titles remain aligned.
- Verify maximum compact and standard TLDR fixtures remain complete and aligned.
- Verify 200% text zoom and text-spacing overrides produce no loss of content.
- Verify medium and large responsive stacking uses document order.
- Verify mouse, keyboard, and reduced-motion states.
- Verify no horizontal overflow and no unexpected console errors.
- Verify covers are aspect-specific compositions rather than visibly cropped derivatives.

## Documentation

Update `README.md` and `README_WORDPRESS.md` with:

- the three canonical report-card variants and their usage map;
- compact and standard TLDR contracts;
- semantic geometry fingerprint fields and 16 families;
- cover regeneration and backfill commands;
- WordPress migration audit and rollout gate;
- `New` badge and geography pictogram rules;
- theme and plugin ZIP generation steps.

## Success Criteria

- Every report placement uses exactly one of the three canonical report-card variants.
- Every small card shows a complete compact TLDR of at most 18 words.
- Every medium and large card shows a complete standard TLDR of at most 45 words.
- No card title or TLDR uses visual truncation, clamping, or ellipsis.
- Adjacent cards align at normal grid breakpoints regardless of shorter content.
- Every large card displays exactly two key insights.
- Every large hero cover contains the complete report name.
- Every report has one semantic fingerprint and three uncropped aspect-specific cover assets.
- Geometry selection is deterministic, content-derived, logged, and chosen from the approved 16 families.
- Global reports use the globe pictogram; regional and country-specific reports use the locator pictogram.
- The `New` badge appears only from publication through six days 23:59:59.
- The migration audit reports zero invalid published reports before renderer activation.
- Targeted Python, WordPress, static migration, and browser tests pass.
- Updated theme and plugin ZIP archives are generated from the verified implementation.

## Reference Standards

- WordPress output must follow the official escaping guidance: https://developer.wordpress.org/apis/security/escaping/
- Theme and pattern integration must follow the Block Editor theme and pattern handbooks: https://developer.wordpress.org/block-editor/how-to-guides/themes/ and https://developer.wordpress.org/block-editor/reference-guides/block-api/block-patterns/
- Card layout may use widely available CSS Grid and subgrid where appropriate: https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Grid_layout/Subgrid
- Text must remain available when resized, consistent with WCAG 2.2 resize and reflow requirements: https://www.w3.org/WAI/WCAG22/Understanding/resize-text and https://www.w3.org/WAI/WCAG22/Understanding/reflow.html
