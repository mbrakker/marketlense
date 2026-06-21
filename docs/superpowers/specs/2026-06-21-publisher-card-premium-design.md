# Premium Publisher Cards Design

## Goal

Make the publisher directory a premium evidence-led discovery surface. Each publisher card must communicate the publisher's public report coverage, report-value assessment, and dominant research categories without inventing data or creating a second search/filter system.

## Approved Experience

The page remains an editorial Market Bearing directory with the existing shared archive hero. The directory uses small publisher cards by default; medium and large variants reuse the report-card size contract when a publisher card is placed in a feature context.

Each publisher card contains:

- The publisher logo from `ml_publisher_icon_source` when available, otherwise the existing publisher monogram.
- The publisher name, public profile link, and existing homepage/research-hub links when present.
- The existing published-content counts for reports, briefings, and signals.
- A report-value assessment derived from the publisher's scored public reports: aggregate score, value band, and assessed-report sample size.
- Two or three dominant report categories, followed by a `+N` overflow count when more categories exist.

Small cards are the default directory presentation. Medium and large cards reuse the existing `.ml-card--medium` and `.ml-card--large` spatial vocabulary: a contained identity/media panel beside the evidence summary on desktop, collapsing to the small stacked treatment on narrow screens.

## Design System

The implementation uses existing theme tokens only:

- Brand navy `#082b54` and signal blue `#0867d7` for hierarchy and interactive emphasis.
- Cool canvas `#f3f7fc`, white surfaces, and existing subtle borders for card separation.
- Existing sans hierarchy for UI and card metadata; the editorial typeface is not introduced into this compact data component.
- Existing radius (`0.45rem` to `0.8rem`), spacing (0.75rem, 1rem, 1.5rem), shadow, focus, hover, and reduced-motion conventions.

No new color scale, icon set, font, external dependency, or synthetic content is introduced.

## Data and Filter Contract

The publisher directory is filtered by the existing report-browser query model.

- Search, topic, period, and region filters apply to published reports.
- The publisher selector is removed from the directory filter rail because publisher cards are the returned dimension.
- A card is shown only if the associated publisher has one or more published reports matching every active filter.
- Active chips and live GET submission reuse the existing report-filter client behavior.
- Categories and coverage counts are calculated from the same matching published-report set, so a filtered card never cites unrelated report categories.

The public report-value assessment is sourced from the existing `state/reports.sqlite` `report_sources` values: `report_value_score`, `report_value_band`, and score components. The sync path must only publish an aggregate when its scored sources can be matched to the public publisher/report surface. It must otherwise render the card without an assessment rather than expose an acquisition-only or unmatched score.

## Ownership

- The WordPress plugin remains the sole frontend owner for publisher-term metadata, report filtering, card rendering, and publisher-profile output.
- Existing Python report-score and publisher-profile sync boundaries remain the sole source/synchronization owners for persisted score data and term metadata updates.
- The block theme owns the publisher directory template and visual styles.
- No request-time WordPress-to-SQLite access is introduced.

## Verification

Tests must prove that:

- The score aggregate, value band, sample size, and category citations originate from valid matched source/report data.
- Cards without a synchronized quality aggregate render normally without a fabricated assessment.
- Filtering by search, topic, period, and region returns only publishers represented by matching public reports.
- The publisher selector is absent from the publisher-directory rail while it remains available in the report archive.
- Small, medium, and large publisher cards meet the established responsive size contract, retain real logos when present, and preserve fallback monograms.
- The WordPress package and relevant Python/WordPress test suites pass.
