# Homepage Editorial Ledger Refresh Design

## Goal

Refresh the Market Bearing homepage so it is denser, better aligned, and more premium while fixing incorrect per-report Insights, Quotes, and Topics counters.

## Approved Direction

The user approved **Option A: Editorial Ledger** on June 12, 2026.

The design preserves the existing Market Bearing identity: navy and signal blue, editorial serif headings, compact evidence-first copy, and the line-ending-in-a-dot brand motif. It does not introduce a new font, color family, image system, dependency, or homepage section.

## Positioning

- Narrative role: the homepage remains an executive intelligence index. Strategic Themes and Publisher Authority are supporting discovery surfaces, not a second hero.
- Viewing distance: the primary target is a laptop or desktop display, with a complete single-column mobile adaptation.
- Visual temperature: quiet, authoritative, evidence-led, and premium.
- Capacity: all existing dynamic records remain available. The design increases density through spacing and hierarchy rather than hiding data.

## Architecture

The existing modular WordPress boundary remains unchanged:

- `marketlense` block theme owns layout, spacing, responsive presentation, and interaction styling.
- `marketlense-core` owns report parsing, taxonomy relationships, counters, and shortcode output.
- The front-page block pattern order and shortcode entrypoints remain unchanged.

No architecture review trigger applies because the change introduces no top-level package, external system, deployable component, duplicated interaction path, or module split.

## Functional Counter Contract

Homepage and archive report counters must represent published report content using these definitions:

- Insights: unique rendered finding cards in the current `#findings` section. Legacy `#section-insights .insight-text` content remains supported for already-published older reports.
- Quotes: rendered quote figures in the current `#evidence` section, counting both `.quote-feature` and `.quote-card`. Legacy `#section-quotes .quote-card` content remains supported.
- Topics: the number of public WordPress category terms assigned through `Taxonomies::CATEGORY_TAXONOMY`. Embedded report taxonomy tags and chapter counts are not Topics.
- Citations: existing citation/evidence-reference behavior remains unchanged.

For the production featured report, the corrected badges are expected to be `05 Insights`, `04 Quotes`, `02 Topics`, and `07 Citations`.

Counts are computed in `Report_View_Model_Builder`; shortcode templates only format the returned values. No client-side counting is allowed.

## Spacing And Section Signal

The current homepage uses repeated `96px` section margins and `76px` band padding, creating excessive empty space. The refresh uses a tighter, consistent rhythm:

- Desktop band separation: `clamp(3.5rem, 5vw, 4.5rem)`.
- Desktop band block padding: `clamp(3rem, 4.5vw, 4rem)`.
- Compact section separation inside shared bands: `2rem` to `3rem`.
- Mobile band separation: `2.5rem`.
- Mobile band block padding: `2.25rem 1rem`.

The line-and-dot section signal moves directly below the title:

- top margin: `0.375rem`;
- bottom margin: `1rem` for normal sections and `1.25rem` before dense content;
- width: preserve the existing `7.5rem` line;
- dot, color, and direction: preserve the existing Market Bearing motif.

These rules apply consistently to Featured Report Brief, Featured Briefing, This Week in Intelligence, Latest Reports, Strategic Themes, Publisher Authority, process, and briefing sections.

## Header

Desktop header layout uses three aligned regions: canonical logo, centered navigation, and right-side actions.

- Logo, navigation, search, and Request a briefing share the same vertical center.
- Existing top-margin offsets on `.ml-header-actions`, `.ml-header-search`, and `.ml-header-cta` are removed at desktop widths.
- Search retains the native WordPress form and accessible label.
- Request a briefing retains its existing destination and button semantics.
- Navigation hover does not use a filled background or highlight block.
- Hover, `:focus-visible`, and current-page states use the brand line-and-dot underline.
- Keyboard focus remains visible.
- Existing mobile disclosure navigation and minimum `44px` touch targets remain intact.

## Editorial Ledger Discovery Surface

Strategic Themes and Publisher Authority remain two semantic shortcode sections inside one shared elevated surface.

### Shared Surface

- Background: white over the existing cool discovery band.
- Border: `1px solid var(--ml-border-subtle)`.
- Radius: `0.875rem`.
- Shadow: `0 1.25rem 3.75rem rgba(8, 43, 84, 0.12)`.
- Padding: `clamp(1.5rem, 3vw, 2.5rem)`.
- Desktop layout: two columns with `clamp(2rem, 4vw, 4rem)` gap.
- Tablet and mobile: one column, with a subtle divider between the sections.

### Strategic Themes

- Render the existing six themes as a compact two-column grid on desktop and one column on narrow screens.
- Each theme is a white, bordered compact card with a small elevation change on hover/focus.
- A decorative ordinal is generated with CSS counters and does not alter accessible names.
- Report counts remain visible as secondary metadata.
- The entire existing title link remains the navigation target; no duplicate overlay link is introduced.

### Publisher Authority

- Render publishers as refined ledger rows rather than loose chips.
- Each row keeps publisher name, report count, and View profile action.
- Rows use subtle separators and a restrained hover/focus surface change.
- The section note remains visible but uses a narrower measure and reduced spacing.
- Existing data order and record limit remain unchanged.

## Responsive Behavior

- At desktop widths, the shared discovery surface is two columns.
- At tablet widths, both sections stack within the same surface.
- Theme cards collapse from two columns to one.
- Publisher rows keep readable names and actions without horizontal overflow.
- Header actions wrap only at the existing mobile breakpoint; the desktop alignment fix must not force overflow.
- The page must have no horizontal scroll at representative widths of 1440px, 1024px, 768px, and 390px.

## Accessibility And Motion

- Preserve semantic section headings and native links/forms.
- Use `:focus-visible` states equivalent in strength to hover states.
- Do not communicate state through color alone; the line-and-dot geometry remains visible.
- Decorative ordinals and line signals are hidden from assistive technology through CSS-generated content or existing `aria-hidden` markup.
- Hover elevation uses a maximum `translateY(-2px)` and a transition of approximately `180ms`.
- Under `prefers-reduced-motion: reduce`, transforms and nonessential transitions are disabled.

## Testing

Tests must validate observable contracts rather than private helper behavior:

- A report fixture using current `#findings`, `#evidence`, and assigned WordPress categories produces the expected `5 / 4 / 2` counts.
- A legacy report fixture continues to produce counts from the legacy section selectors.
- Topics count comes from `Taxonomies::CATEGORY_TAXONOMY`, not embedded `.chip-list` tags.
- Featured badge rendering uses the view-model values.
- Static theme tests assert the shared discovery surface, tighter spacing, close section signal, aligned header controls, and line-and-dot hover/focus rules.
- Browser verification covers desktop and mobile screenshots, header hover/focus behavior, no horizontal overflow, and a clean console.

## Documentation

Update `README_WORDPRESS.md` and the WordPress section of `README.md` to record:

- current report counter semantics;
- the Editorial Ledger discovery treatment;
- tightened homepage spacing and section-signal placement;
- vertically aligned header actions and line-and-dot navigation interaction.

## Success Criteria

- The production featured report displays `05 Insights / 04 Quotes / 02 Topics / 07 Citations` from real report and taxonomy data.
- No report card displays zero Insights or Quotes when corresponding current report sections contain records.
- Homepage sections have visibly reduced empty space without content collisions.
- Every section line-and-dot signal sits visually close to its heading.
- Strategic Themes and Publisher Authority read as one elevated premium discovery surface.
- Header search and Request a briefing align vertically with the logo.
- Header menu hover uses only the line-and-dot signal, with no filled highlight.
- Existing mobile navigation, destinations, dynamic content order, and shortcode boundaries remain unchanged.
- Targeted tests pass and browser verification reports no console errors or layout overflow.
