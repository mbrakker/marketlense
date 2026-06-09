# Market Bearing Balanced Prototype Specification

## Goal

Extend the local prototype so it restores the useful content and trust surfaces from the existing WordPress site while preserving the approved Market Bearing editorial direction.

## Content Rule

Published reports, briefings, signals, topics, publishers, citations, metrics, excerpts, and report-detail content must come from local snapshots of published WordPress artifacts. Interface labels, navigation, methodology explanation, and Market Bearing product positioning may remain authored copy.

Taxonomy entities render only when at least one snapshot record references them. Counts are computed from snapshot relationships rather than written into HTML.

## Approved Direction

Balanced editorial:

- selective, high-authority homepage;
- complete searchable archives behind it;
- report-led evidence presentation;
- restrained enterprise-blue design system;
- no fabricated reports, metrics, quotes, publishers, or testimonials.

## Required Surfaces

### Shared

- Header navigation for Reports, Topics, Publishers, Signals, Briefings, and Methodology.
- Global research search.
- Footer trust statements, Explore links, Standards links, Contact, Privacy, Terms, and request actions.

### Homepage

- Hero search and latest governed brief.
- Trust counters for published reports, represented publishers, active topics, briefings, signals, and available citations.
- Featured report and featured briefing.
- Latest published signals with source context.
- Six latest reports with publisher, period, topics, and citation/evidence counts when present.
- Strategic themes and publisher authority, both derived from represented content.
- Four-stage Extract, Structure, Evidence-link, Publish method.
- Newsletter and contact actions.

### Directories

- Reports: complete snapshot, search, topic/publisher/period filters, sorting, count, and pagination.
- Topics: only non-empty topics, with report/briefing/signal counts and direct filtered views.
- Publishers: only represented publishers, with content counts and available source/profile links.
- Signals and Briefings: published records only, with source and evidence context.

### Report Detail

- Executive summary and key findings.
- Published figures and infographic metrics.
- Signals, quotations, expert view, LinkedIn-ready post, taxonomy, leadership implications, source, and provenance when present in the artifact.
- Computed finding, quote/citation, figure, and topic counters.
- Source and original published-page actions.

## Prototype Architecture

- `data/*.json`: immutable local snapshots of published WordPress REST records.
- `content-model.js`: pure normalization, relationship, count, search, filter, and pagination functions.
- `render.js`: DOM rendering for approved views.
- `app.js`: routing, event handling, accessibility state, and orchestration.
- `index.html`: shared shell and view mount points only.
- `styles.css`: approved design tokens and responsive presentation.

This mirrors the future WordPress ownership model:

- block theme owns templates, patterns, parts, and tokens;
- `marketlense-core` owns WordPress queries, filters, counters, taxonomies, and entity rendering;
- the Python pipeline remains the only analysis and signal-generation boundary.

## Accessibility And Performance

- Semantic landmarks and sequential headings.
- Visible keyboard focus and explicit labels.
- Polite result-count announcements.
- Native disclosure elements for long report sections.
- Reduced-motion support.
- Lazy loading for non-critical images.
- No dependency or client framework.

## Success Criteria

- Key content does not appear as duplicated hard-coded records in HTML.
- Snapshot-derived counters match snapshot relationships.
- Every taxonomy card has referenced content.
- All approved modules are present.
- Search and filters work on desktop and mobile.
- Browser console has no errors or warnings.
- WordPress runtime files remain unchanged.
