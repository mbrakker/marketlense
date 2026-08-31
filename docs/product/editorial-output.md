# Editorial Output

> **Documentation type:** Current reference
> **Canonical topic:** Editorial output
> **Update trigger:** Public artifact contract or publication model changes.

The report pipeline produces source-attributed HTML and structured report artifacts. Editorial content is generated from validated report evidence and is subject to schema, completeness, and publication validation before WordPress side effects occur.

Report-local output can include summaries, insights, quotes, figure selections, topics, key figures, and other approved public modules when supported by the retained artifact contract. Internal evidence identifiers and machine-only publication data are not public output.

The single Editorial Plan treats the DocMap as the authority for report breadth.
For broad reports, its two-to-seven themes represent materially different major
source areas and preserve both source-backed sides of a material
decision-relevant tension. It does not manufacture balance or pad a narrow,
one-sided report. DocMap-aware findings extraction applies the same principle:
when file-search evidence supports materially different or counterbalancing
major sections, it retrieves both sides rather than substituting several close
subtopics from one side.

The Expert View side panel carries only the neutral `MarketBearing analysis`
identity. Report-specific interpretation belongs exclusively to the generated
Expert View body; an unsupported synthesis renders the existing explicit
abstention notice instead of generic theme claims.

The public metric spine is a bounded selection of source-backed textual metrics.
It ranks a metric whose evidence ID directly supports a selected editorial-plan
theme ahead of secondary metrics; the plan's positive priority order resolves
that editorial relevance. Missing timeframe, segment, or geography remains
visible as a metric caveat and is a secondary quality factor only among metrics
with the same editorial relevance. The spine retains the source metric's label,
exact display value, unit, and evidence ID. When that complete display can be
parsed without alteration, it also carries derived numeric metadata; the raw
display remains authoritative. A generated decimal-ending display, or a
currency integer whose linked retained source continues with a decimal digit,
is rejected only when that exact source continuation proves truncation; the
existing scoped artifact recovery then handles it. Chart, table, and crop
selection are separate flows. Every newly generated metric with a public value
also carries a concise metric-specific label bound to the same evidence ID; the
spine uses that explicit label rather than an insight-level statement. Legacy
artifacts without the field remain readable through abbreviation-safe sentence
handling, but a legacy Key Figure is omitted when no single metric-specific
label can be established. Labels never stop at a geographic initialism such as
`U.S.` or `U.K.`.

Each public metric-spine item represents exactly one primary human-readable
value, or one coherent comparison/range. Semicolon-packed values or units and
other clearly composite displays fail closed: the Key Figure is omitted while
the retained insight prose, supporting evidence, and evidence ID remain
available. Units must express one semantic unit without repeating currency
symbols or magnitude words already in the value; an unambiguous numeric value
with a malformed `$ billion` unit is rendered as a conventional currency value
and magnitude. This display rule does not alter Editorial Plan ranking or the
separate chart, table, and crop paths.

When evidence supports a Decision Brief, it serves a distinct role from the Executive Summary. Its strategic context is the concise report thesis (`tldr` or compact TLDR), never the full executive-summary prose. Decision implications use evidence-linked insight `so_what` fields; priority moves use supported `now_what` fields; and watchouts use evidence-linked counter-signals plus retained limitations. Unsupported sections are omitted rather than inferred, while the retained evidence links continue to identify the supporting source material.

LinkedIn output uses the persisted editorial plan as its primary thematic frame,
then final representative insights and the metric spine as evidence. It targets
180–280 words (with the retained 500-word hard maximum), opens on one concrete
report-backed angle, attributes a known publisher naturally, and limits normal
posts to four quantitative proof points. Broad reports identify the post as a
representative lens rather than a complete recap; narrow reports may state the
whole thesis. The prompt retains factual grounding and clean paragraph
construction. At the public rendering boundary, the LinkedIn-only sanitizer
removes internal identifiers, placeholders, truncation-marked output, bullets,
and Markdown constructs while preserving newline and paragraph structure for
the existing `white-space: pre-line` presentation. It does not alter Expert
View or the general public-prose sanitizer, add an LLM call, or add a new
publication gate.

Public titles are normalized from retained metadata before rendering: filename
separators, document suffixes, literal truncation marks, and repeated adjacent
years are removed. SEO descriptions prefer a complete retained compact TLDR;
otherwise they end at a real sentence boundary within the configured length,
never a decimal or abbreviation period. A public canonical URL is emitted only
after a MarketLense WordPress URL is known; the original report URL remains a source
citation and is never presented as the public canonical page.

The retained `time_period` remains source metadata. The public `Period` is a
deterministic, fail-closed projection that accepts only concise source-backed
years, year lists or ranges, month/year values, explicit dates or date ranges,
and quarter, half-year, or fiscal-year expressions. Surrounding prose is never
published; one unambiguous embedded year may be shown alone, while ambiguous or
unparseable values are omitted. Public `Fieldwork` is likewise limited to the
explicit date range adjacent to a fieldwork marker, preferring methodology and
time-period metadata before executive-summary fallback text.

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

Comparative claims preserve source-proven temporal context from findings through
candidate and final insights, summaries, Expert View, LinkedIn, and the rendered
Core signal. A source comparison that uses distinct quarters, half-years,
month/year values, fiscal years, or a forecast marker retains those qualifiers;
it is never reduced to a shared year. The deterministic editorial check blocks a
public claim only when it restates both source comparison values but loses a
source-proven qualifier, or when it contains malformed wording such as `in to`
or `between and`. It does not infer a missing period and does not reject a valid
same-year comparison merely because both qualifiers contain the same year.

The report header's Core signal selects one retained insight sentence before
deriving either field. Both its heading and body come from that same selected
insight, and the renderer retains its selected insight and evidence identifiers
in the view model for traceability; it never combines a strategic implication
or another finding with the selected sentence. Its deterministic clause
extraction preserves
coordinated terms (for example, `between scale and momentum` and `search and
video`) and splits only at a clear boundary such as a semicolon, colon, or
comma followed by a conjunction. It deterministically prefers a substantive
market, metric, constraint, or adoption finding over a sentence that merely
describes the report or study. It otherwise uses the explicit
`Source-backed market signal` heading with a complete supporting sentence; it
never uses a clipped fragment, literal ellipsis, or a pending-data fallback
when a grounded summary is available.

Context-first category assignment uses category definitions, inclusion conditions, and exclusion conditions to assign public Topics. A non-rejected primary or secondary candidate that is semantically ambiguous is repaired once or fails closed; it cannot silently leave a report without its identified category. Taxonomy tags remain supporting metadata and prompt vocabulary; they are not a competing weighted category scorer.

Cross-report output is published as Briefings. It uses persisted report projections and evidence rather than generating intelligence inside WordPress. See [cross-report analysis](../workflows/cross-report-analysis.md) and the [WordPress front-end contract](../../README_WORDPRESS.md).
