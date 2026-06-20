# Shared Directory Hero Design

## Goal

Replace the Reports, Topics, Signals, and Briefings landing-page heroes with the premium visual language already used by the Publishers directory. Preserve the Publishers result while moving every affected route onto one reusable, configurable hero component.

## Success Criteria

- Publishers, Reports, Topics, Signals, and Briefings use one canonical hero renderer and one shared CSS component.
- Every hero renders four context-relevant counters from live WordPress content.
- A visual design change can be made once in the shared renderer or shared component styles and affect every usage.
- Existing page copy, URLs, archive content, filters, and index behavior remain unchanged.
- Desktop, tablet, mobile, keyboard, reduced-motion, and horizontal-overflow checks pass.

## Architecture

Add one `ml_archive_hero` shortcode to the existing canonical `MarketLense_Core_Shortcodes` boundary. The shortcode owns the hero markup and a closed, validated context configuration for `publishers`, `reports`, `topics`, `signals`, and `briefings`.

Each WordPress template invokes the component with only a validated context:

```text
[ml_archive_hero context="reports"]
```

The renderer delegates counter values to the existing `ml_archive_metric` behavior rather than introducing another counting implementation. Unknown contexts return an empty string. All configured copy and labels are escaped and translatable through the existing WordPress conventions.

This approach is preferred over repeated native block markup because it provides a single structural owner. A custom Gutenberg block is rejected because the repository has no block build toolchain and the added runtime/editor complexity is not justified.

## Route Coverage

The shared component replaces legacy hero markup in these theme templates:

- `page-publishers-directory.html`
- `archive-ml_report.html`
- `archive.html`
- `page-topics-directory.html`
- `page-signals.html`
- `archive-ml_signal.html`
- `page-briefings.html`
- `archive-ml_briefing.html`

No taxonomy-detail, search, homepage, or single-content hero is changed.

## Content And Metrics

Existing editorial copy remains unchanged.

| Context | Counter 1 | Counter 2 | Counter 3 | Counter 4 |
| --- | --- | --- | --- | --- |
| Publishers | Publishers | Reports | Regions | Topics |
| Reports | Reports | Publishers | Topics | Regions |
| Topics | Topics | Reports | Publishers | Regions |
| Signals | Signals | Reports | Topics | Publishers |
| Briefings | Briefings | Reports | Publishers | Topics |

All values remain dynamic through the existing stats service and `ml_archive_metric` contract. Signal fallback semantics and content-backed taxonomy rules remain unchanged.

## Visual System

- Narrative role: authoritative directory/archive introduction.
- Viewing distance: phone through desktop browser.
- Visual temperature: premium, institutional, and restrained.
- Layout: editorial copy beside four equal metric cards; cards collapse from four columns to two and then one without changing DOM order.
- Palette: existing deep navy gradient (`#06264b`, `#082b54`, `#031a35`), white typography, and the existing signal-blue accent.
- Typography: existing Market Bearing sans family; strong white display heading, compact uppercase kicker, readable lead text, and tabular-feeling numeric counters.
- Spacing: existing component rhythm based on approximately 8px increments.
- Radius: restrained `0.35rem` to `0.45rem` radii.
- Depth: translucent card fill, fine white border, inset highlight, and no heavy floating shadow.
- Texture: CSS grid lines and a restrained lower-corner technical accent; all decoration remains non-semantic.
- Motion: no required animation. Existing reduced-motion behavior remains intact.

Shared component selectors use a neutral `ml-archive-hero` namespace. Page-specific selectors must not own the common visual treatment. Context classes or data attributes may be emitted only for genuinely necessary content-specific adjustments.

## Responsive And Accessibility Behavior

- Preserve one page-level `h1` and sequential content headings.
- Keep counter labels and values in the DOM; decorative counter icons remain hidden from assistive technology.
- Preserve natural source order across breakpoints.
- Ensure readable text contrast over the navy surface.
- Avoid JavaScript-dependent layout and client-rendered hero content.
- Prevent horizontal overflow at 390px, 768px, 1024px, and 1440px viewports.
- Maintain usable rendering at 200% zoom and with browser text-spacing overrides.

## Testing

Follow red-green-refactor:

1. Update the WordPress portal contract test first so it requires every covered template to use `ml_archive_hero` with the correct context and rejects legacy page-specific hero structures.
2. Require the component configuration to expose exactly four metric entities per context and preserve the agreed order.
3. Run the focused test and confirm it fails because the shared component does not yet exist.
4. Implement the renderer, template substitutions, and shared CSS.
5. Run the focused test, the complete WordPress subproject check, and relevant formatting/static checks.
6. Use the browser against the local WordPress site to verify all five destinations at desktop, tablet, and mobile widths. Capture screenshots and inspect computed layout, overflow, headings, counter count, and visible counter values.
7. Compare Publishers before and after to ensure its visual hierarchy has not regressed.

## Documentation

Update `README_WORDPRESS.md` to describe `ml_archive_hero`, its supported contexts, four-counter mappings, and the shared customization boundary. Do not duplicate implementation details outside that canonical description.

## Non-Goals

- No changes to report cards, archive filters, directory listings, publishing behavior, routes, taxonomies, or stats calculations.
- No new JavaScript, animation framework, custom Gutenberg block, external dependency, or build pipeline.
- No redesign of homepage, taxonomy-detail, search, or single-content heroes.
- No speculative component options beyond the five approved contexts.
