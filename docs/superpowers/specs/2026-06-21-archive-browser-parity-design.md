# Archive Browser Parity

## Goal

Make `/briefings/` and `/signals/` match `/reports/` for card footprint, search, filters, result counts, sorting, pagination, and desktop sticky controls. Keep the card content specific to each post type.

## Existing State

`render_report_browser()` owns the full report archive browser. It renders the search field, active-filter chips, sticky filter rail, result count, sort controls, responsive grid, and pagination. The reports page CSS scopes its compact, sticky presentation to `.ml-reports-archive-page`.

Briefings and signals instead render through separate index methods. They render their own card lists and do not use the archive browser. Their renderers support `small`, `medium`, and `large` variants; the reports archive uses the `small` card footprint.

## Approved Design

Create one private archive-browser path inside the existing shortcode bounded context. It accepts the content type, its canonical query contract, archive labels, available facets, and the existing type-specific card renderer. The public shortcode methods remain unchanged and delegate to that owner.

The common browser will provide all current Reports controls for all three content types:

- URL-backed search and active-filter chips;
- category, publisher, region, and period facets when data exists for the type;
- current-view count, sort controls, pagination, and empty state;
- Reports-equivalent sticky utility bar, sidebar, and result header on desktop;
- the same three/two/one-column responsive grid.

Briefings and signals will render their existing `small` canonical variants in that grid. This gives their card media the Reports archive 16:9 aspect ratio and makes their outer dimensions match report cards without changing their semantic fields or card renderer contracts.

The Reports archive CSS will be generalized from the page-specific `.ml-reports-archive-page` selector to a shared archive-browser modifier class emitted by all three archive surfaces. Homepage and featured-card layouts remain untouched.

## Boundary and Data Flow

`Shortcodes` remains the public WordPress boundary. The new private owner only coordinates query state and markup for archive browsing; it does not duplicate the report, briefing, or signal view-model/card-renderer responsibilities. Existing renderers keep ownership of card markup.

The shared browser builds a `WP_Query` from selected URL state, renders the existing filter and pagination helpers, invokes the injected type-specific renderer with `small`, and resets post data. No new service, external system, deployable unit, or public shortcode is introduced.

## Error Handling

Invalid URL filter values normalize to the current archive defaults, matching the Reports behavior. Empty result sets render the existing archive empty-state treatment. Card contracts that are invalid continue to be omitted as they are today; the query is constrained to each type's canonical card schema so pagination and counts reflect renderable cards.

## Verification

Before implementation, add focused tests that assert both Briefings and Signals expose the shared browser controls and render the `small` canonical card variant. Retain tests proving their separate card contracts.

After implementation, run the focused WordPress tests and the relevant PHP runtime harnesses. Deploy through the existing WordPress workflow, then use a real browser to verify all three live archive URLs at desktop and mobile widths, including sticky controls, search/filter state, result counts, and equal card dimensions.

## Scope Guardrails

No changes to homepage cards, article pages, card data contracts, content taxonomy semantics, public shortcode names, or card-renderer behavior outside archive use are included.
