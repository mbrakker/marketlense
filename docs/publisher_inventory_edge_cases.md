# Publisher Inventory Discovery Edge Cases

This document tracks publisher-specific discovery behaviors observed during live runs.
It is intentionally separate from the main README so the shared discovery path can stay generic while edge cases remain visible for future decomposition work.

## Status Meanings

- `passed`: discovery completed, quality gating produced a plausible report set, and `publishers.discovery_test_status` was written as passed.
- `failed:<error_code>`: discovery completed with a typed failure and the same status was written to `publishers.discovery_test_status`.
- `under_review`: live behavior completed but still needs another generic fix before it should be treated as canonical.

## Publisher Notes

### Activate Consulting

- Status: `passed`
- Insights URL: `https://www.activate.com/insights`
- Edge case:
  - archive is a simple one-page inventory, but browser drift can inflate the raw candidate set without producing any new qualified report assets
  - some report cards expose both landing-page and direct-PDF style links, so the raw snapshot is broader than the final report-like download queue
- Generic handling now used:
  - raw-only snapshot drift guard keeps the previous snapshot canonical when the raw diff changes but screening and quality reject everything new

### AXA

- Status: `passed`
- Insights URL: `https://www.axa.com/en/commitments/publications-reportings-and-policies`
- Edge case:
  - one-page archive with dense publication/report listings and cookie-banner interaction at first paint
- Generic handling now used:
  - cookie-banner dismissal remains scoped to consent surfaces
  - small but dense one-page archives are accepted as real inventory surfaces without forcing artificial pagination

### Acxiom

- Status: `passed`
- Insights URL: `https://www.acxiom.com/resources/`
- Edge case:
  - single-page resource archive exposes a visible `Load more` affordance even when the current inventory is already stable
- Generic handling now used:
  - same-page growth probing distinguishes real pagination progress from inert controls so stable one-page archives do not overrun

### Adjust

- Status: `passed`
- Insights URL: `https://www.adjust.com/resources/ebooks/`
- Edge case:
  - archive starts on a teaser page and then expands into `/all`, so the final inventory spans two rendered states with duplicate cards between them
- Generic handling now used:
  - cumulative multipage/load-more traversal with deterministic normalization keeps the teaser and expanded archive states aligned without double-queueing

### Boston Consulting Group (BCG)

- Status: `passed`
- Insights URL: `https://www.bcg.com/search?q=Reports&s=1&f7=00000171-f17b-d394-ab73-f3fbae0d0000`
- Edge case:
  - search results include a mix of `Report ...` and `Article ...` publication pages, and some landing-page checks are bot-protected
- Generic handling now used:
  - bot-protected landing pages stay acceptable only when the source title is still explicitly report-like
  - article-labeled candidates are rejected even when the landing-page fetch is blocked

### Brand Finance

- Status: `passed`
- Insights URL: `https://brandfinance.com/insights`
- Edge case:
  - archive is shallow but mixes branded marketing/news content and genuine index/report pages
- Generic handling now used:
  - screening and landing-page qualification keep only report/index-style assets with substantial document framing

### Braze

- Status: `passed:no_report_assets`
- Insights URL: `https://www.braze.com/resources/articles`
- Edge case:
  - archive is a valid content surface but the discovered candidates are editorial articles rather than report assets
- Generic handling now used:
  - first-run archives with raw candidates but zero qualified report assets now record `passed:no_report_assets` and skip noisy snapshot uploads

### Bright Local

- Status: `passed`
- Insights URL: `https://www.brightlocal.com/research/`
- Edge case:
  - deep research archive spans 11 pages and mixes surveys, studies, benchmark writeups, and a few lightweight poll pages
- Generic handling now used:
  - report/study/survey-oriented archive filtering keeps the full research corpus traversable while still rejecting obvious non-asset hubs on reruns

### Capgemini

- Status: `passed`
- Insights URL: `https://www.capgemini.com/insights/research-library/ai-perspectives-2026/`
- Edge case:
  - page is a research-library detail surface that exposes a mix of sibling research links, a true report page, and direct PDF downloads
- Generic handling now used:
  - screening prefers report-library assets over generic research-library navigation
  - landing-page quality accepts both gated report pages and direct PDF research briefs

### Adobe

- Status: `passed`
- Insights URL: `https://business.adobe.com/resources/reports.html`
- Edge case:
  - bottom-button pagination spans 22 pages
  - landing pages are real report assets, but direct HTTP landing-page verification frequently times out
  - archive also mixes obvious publisher-accolade pieces and report microsite sections
- Generic handling now used:
  - button-pagination traversal to exhaustion
  - transient landing-page timeout fallback for already screened report-like assets
  - stricter rejection of publisher-success analyst marketing
  - nested report-section URL rejection

### Algolia

- Status: `passed`
- Insights URL: `https://resources.algolia.com/reports`
- Edge case:
  - deep `Show More` archive with very large cumulative candidate volume
  - resource hub mixes report assets with academy, support, webinar, and video surfaces
  - some newly surfaced `/resources/asset/` report-like URLs resolve to real 404 pages after screening
- Generic handling now used:
  - candidate-screening prefilter rejects academy/support/webinar/video/training items before LLM screening
  - long candidate titles are truncated in the screening prompt to keep large archives within runtime bounds
  - dynamic screening batch sizing uses fewer, larger batches for deep archives
  - dead-link-only screened deltas are tolerated on reruns when a previous canonical snapshot already exists, so a broken new asset card does not fail the entire publisher run

### AlixPartners

- Status: `passed`
- Insights URL: `https://www.alixpartners.com/insights/`
- Edge case:
  - deep load-more archive with mixed report assets and editorial articles
  - some third-party legal practice guides and report microsite section URLs previously slipped through quality gating
  - same-URL load-more pagination can expose repeated terminal DOM states after the real archive has already stopped growing
- Generic handling now used:
  - landing-page rejection for legal practice-area guide URLs
  - nested report-section URL rejection for report microsite child pages
  - editorial article rejection remains active for thought-leadership pages without real asset signals
  - duplicate same-URL load-more states are ignored when the candidate set has stopped changing, which keeps deep archives from churning snapshots

### Cardlytics

- Status: `under_review`
- Insights URL: `https://www.cardlytics.com/research-and-insights`
- Edge case:
  - archive cards route through `/blog/` URLs even when the landing pages are real gated report assets
  - naive editorial-path rejection can drop report pages that still expose strong report framing and form-gated access
- Generic handling now used:
  - editorial-looking URLs remain acceptable when the landing page shows strong distribution plus document signals and report framing, while dated/news-style editorial URLs still stay rejected

### Comscore

- Status: `passed`
- Insights URL: `https://www.comscore.com/Insights/`
- Edge case:
  - deep archive uses straightforward page-number navigation and includes a large backlog of older white papers, playbooks, and reports
- Generic handling now used:
  - pagination URL traversal continues across numbered pages within the command cap
  - quality gating keeps document/report assets and drops obvious non-report archive noise

### Consumer Goods Technology

- Status: `passed`
- Insights URL: `https://consumergoods.com/research-reports`
- Edge case:
  - archive mixes numbered pagination and inert load-more surfaces, which can produce duplicate terminal states near the end
- Generic handling now used:
  - same-signature cycle detection stops inert terminal loops instead of burning the full page cap

### Datareportal

- Status: `bounded`
- Insights URL: `https://datareportal.com/reports/`
- Edge case:
  - very deep archive continues surfacing new report pages beyond the shared page ceiling
- Generic handling now used:
  - cross-URL candidate-signature cycle detection still guards against repeated offset states when no new inventory appears
  - current live behavior is a legitimate bounded crawl, not a freeze or stale-state loop

### Devoteam

- Status: `under_review`
- Insights URL: `https://www.devoteam.com/insights/`
- Edge case:
  - long-running archive traversal can exceed a single browser attempt timeout before reaching a stable terminal state
- Generic handling now used:
  - the orchestrator now enforces a hard per-publisher command budget so long runs fail explicitly and persist `discovery_test_status` instead of being killed by the shell

### Digital Shelf Institute

- Status: `passed`
- Insights URL: `https://www.digitalshelfinstitute.org/resources-library`
- Edge case:
  - archive uses repeated button-driven pagination on a single URL instead of clean page-number URLs
- Generic handling now used:
  - button-pagination traversal now advances repeated same-URL inventory states and still records the correct discovered page number for qualified report assets

### Earnest Analytics

- Status: `bounded`
- Insights URL: `https://www.earnestanalytics.com/insights`
- Edge case:
  - deep archive exposes a large sequence of numbered pages through `paged=` URLs without exhausting within the shared page cap
- Generic handling now used:
  - next-page URL traversal continues deterministically and cleanly records a bounded outcome once the shared page limit is reached

### Euromonitor

- Status: `bounded`
- Insights URL: `https://www.euromonitor.com/insights/`
- Edge case:
  - archive relies on repeated in-place `Load more` expansion and can accumulate hundreds of candidates before the shared page cap
- Generic handling now used:
  - same-page DOM growth is treated as pagination progress, and the run now exits cleanly as a bounded deep archive instead of a generic failure

### Garden Media

- Status: `passed:no_report_assets`
- Insights URL: `https://gardenmediagroup.com/2026-garden-trends-report/`
- Edge case:
  - source is a single trend-report landing page rather than a reusable archive surface
- Generic handling now used:
  - first-run archives that yield only pre-rejected/non-qualifying candidates are marked `passed:no_report_assets` instead of failing or uploading a noisy snapshot

### Harries Williams

- Status: `passed`
- Insights URL: `https://www.harriswilliams.com/our-insights`
- Edge case:
  - archive exposes printable long-form report pages without a direct download CTA and mixes them with non-report insight items
- Generic handling now used:
  - printable report-page acceptance keeps structured report assets even when they are HTML pages rather than downloads, while the screening stage removes the surrounding archive noise

### Amadeus

- Status: `passed`
- Insights URL: `https://amadeus.com/en/resources`
- Edge case:
  - mixed resource hub where real white papers and research pages coexist with trend articles
  - landing pages often use weak CTA text such as `Read the report`
- Generic handling now used:
  - report/white-paper filtering keeps only likely document assets
  - trend/article pages without sufficient document/report signals are rejected
  - title resolution still needs future normalization work when landing pages expose weak CTA text instead of a clean document title

### Allspring

- Status: `passed`
- Insights URL: `https://www.allspringglobal.com/insights`
- Edge case:
  - one-page insights archive looks paginated (`?page=1`) but behaves as a stable single rendered state
- Generic handling now used:
  - inert same-page states are treated as completion instead of forced pagination

### Atomico

- Status: `passed`
- Insights URL: `https://atomico.com/insights`
- Edge case:
  - report pages can sit behind anti-bot or challenge pages during direct landing-page inspection
  - accepted report pages often still expose noisy publisher/date text in the resolved title
- Generic handling now used:
  - bot-protected landing-page fallback keeps already screened report-like assets instead of treating them as dead links
  - title cleanup still needs future normalization work for publisher/date prefixes

### PSFK

- Status: `passed`
- Insights URL: `https://www.psfk.com/insights`
- Edge case:
  - archive is initially a truncated preview behind a generic `Explore all 31+ library entries` control
  - valid report assets are hosted off-apex on `psfk.gumroad.com`
  - archive also mixes in article/newsletter cards
- Generic handling now used:
  - archive-preview expansion before normal pagination handling
  - archive-card acceptance allows off-apex destinations when the card itself is clearly report-like

### Publicis Commerce

- Status: `passed`
- Insights URL: `https://www.publiciscommerce.com/insights`
- Edge case:
  - multi-page archive with thought-leadership and report-like assets mixed together
  - card text often includes author/date/category/read-more chrome
  - some article bodies mention `purchase`, which can look like a paid/publication signal if parsed too loosely
- Generic handling now used:
  - card-title extraction prefers heading text over the entire card body
  - landing-page purchase detection is restricted to CTA/price signals instead of any body-text mention

### Publicis Sapient

- Status: `passed`
- Insights URL: `https://www.publicissapient.com/resources/blog`
- Edge case:
  - archive exposes tabbed sections and previously drifted into a single detail page
  - research assets live under the archive surface and need report-focused tab selection
- Generic handling now used:
  - archive-surface drift recovery
  - tab traversal with report-focused section preference

### Pubmatic

- Status: `passed`
- Insights URL: `https://pubmatic.com/reports/`
- Edge case:
  - printable infographic/report pages do not always expose a direct download CTA
- Generic handling now used:
  - printable report pages are accepted when they have document/report framing even without download

### Quid

- Status: `passed`
- Insights URL: `https://www.quid.com/knowledge-hub/resource-library`
- Edge case:
  - very deep paginated archive (`Page X of Y`) with a large inventory
- Generic handling now used:
  - `Page X of Y` pagination detection
  - higher bounded page cap and timeout for deep but finite archives
