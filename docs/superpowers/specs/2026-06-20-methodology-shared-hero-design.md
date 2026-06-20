# Methodology Shared Hero Design

## Goal

Migrate the Methodology page header to the existing canonical `ml_archive_hero` component without changing its downstream methodology content or the shared visual system.

## Architecture

Add one validated `methodology` context to `render_archive_hero()`. The existing renderer remains the sole owner of hero structure and delegates all values to `render_archive_metric()`. The Methodology block template becomes a context-only call site:

```text
[ml_archive_hero context="methodology"]
```

No new shortcode, renderer, CSS selector, JavaScript, service, or deployable boundary is introduced.

## Content And Metrics

Preserve the current Methodology hero copy exactly:

- Kicker: `Methodology`
- Title: `How Market Bearing keeps published research connected to its evidence`
- Lead: `The pipeline combines deterministic extraction, typed validation, and structured editorial shaping so every published report brief is reproducible, reviewable, and source-aware.`

Render these live counters in order:

1. Reports
2. Publishers
3. Topics
4. Regions

All counts retain the existing stats-service semantics.

## Template Scope

In `page-methodology.html`:

- change the main wrapper to the same full-width directory-page structure used by shared hero routes;
- replace only the existing `ml-taxonomy-header` block with `[ml_archive_hero context="methodology"]`;
- place the existing methodology grids, quality controls, and post content inside the standard constrained content frame;
- preserve all six process steps, headings, copy, and order.

## Testing

Follow red-green-refactor:

1. Extend the shared-hero contract test to require the Methodology template and ordered metric configuration.
2. Run the focused test and confirm it fails because the context and template call do not exist.
3. Add the renderer context and migrate the template.
4. Run the focused test, full WordPress portal tests, PHP syntax check, and WordPress subproject checker.
5. Verify Methodology through the existing local production-component browser harness at desktop, tablet, and mobile widths, including no overflow and four visible counters.
6. Rebuild the tracked WordPress plugin and theme ZIP archives after verification.

## Documentation

Update `README_WORDPRESS.md` so the supported-context list and counter mapping include Methodology.

## Non-Goals

- No CSS changes.
- No changes to methodology body content.
- No changes to counter calculations.
- No redesign of any other page.
- No remote deployment through unavailable REST upload capabilities.

