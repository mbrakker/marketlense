# Editorial Output

> **Documentation type:** Current reference
> **Canonical topic:** Editorial output
> **Update trigger:** Public artifact contract or publication model changes.

The report pipeline produces source-attributed HTML and structured report artifacts. Editorial content is generated from validated report evidence and is subject to schema, completeness, and publication validation before WordPress side effects occur.

Report-local output can include summaries, insights, quotes, figure selections, topics, key figures, and other approved public modules when supported by the retained artifact contract. Internal evidence identifiers and machine-only publication data are not public output.

Public titles are normalized from retained metadata before rendering: filename
separators, document suffixes, literal truncation marks, and repeated adjacent
years are removed. SEO descriptions end at a word and sentence boundary within
the configured length. A public canonical URL is emitted only after a
MarketLense WordPress URL is known; the original report URL remains a source
citation and is never presented as the public canonical page.

The deterministic public-editorial gate blocks common UTF-8 mojibake sequences
and replacement characters in reader-facing prose. It retains a bounded defect
record for targeted repair rather than silently rewriting source-derived text.
It also withholds prose carrying literal truncation markers. Mechanical
editorial labels are deterministically removed at render time to preserve direct
prose, and literal truncation is omitted. The exact rendered HTML then blocks
any remaining label or truncation marker. This applies to summaries, expert
views, and LinkedIn posts. Source links are emitted only for public, credential-free
HTTP(S) URLs. When no verified publisher link is available, the report keeps a
plain disclosure and never exposes a local cache or operational path.

The report header's Core signal uses only a complete retained sentence. It
deterministically prefers a substantive market, metric, constraint, or adoption
finding over a sentence that merely describes the report or study. It otherwise uses the explicit
`Source-backed market signal` heading with a complete supporting sentence; it
never uses a clipped fragment, literal ellipsis, or a pending-data fallback
when a grounded summary is available.

Context-first category assignment uses category definitions, inclusion conditions, and exclusion conditions to assign public Topics. A non-rejected primary or secondary candidate that is semantically ambiguous is repaired once or fails closed; it cannot silently leave a report without its identified category. Taxonomy tags remain supporting metadata and prompt vocabulary; they are not a competing weighted category scorer.

Cross-report output is published as Briefings. It uses persisted report projections and evidence rather than generating intelligence inside WordPress. See [cross-report analysis](../workflows/cross-report-analysis.md) and the [WordPress front-end contract](../../README_WORDPRESS.md).
