# Editorial Output

> **Documentation type:** Current reference
> **Canonical topic:** Editorial output
> **Update trigger:** Public artifact contract or publication model changes.

The report pipeline produces source-attributed HTML and structured report artifacts. Editorial content is generated from validated report evidence and is subject to schema, completeness, and publication validation before WordPress side effects occur.

Report-local output can include summaries, insights, quotes, figure selections, topics, key figures, and other approved public modules when supported by the retained artifact contract. Internal evidence identifiers and machine-only publication data are not public output.

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
selection are separate flows. Derived metric labels retain a leading geographic
initialism and the complete first source sentence rather than emitting a clipped
fragment.

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
construction without adding a post-generation rewrite or a new publication
gate.

Public titles are normalized from retained metadata before rendering: filename
separators, document suffixes, literal truncation marks, and repeated adjacent
years are removed. SEO descriptions prefer a complete retained compact TLDR;
otherwise they end at a real sentence boundary within the configured length,
never a decimal or abbreviation period. A public canonical URL is emitted only
after a MarketLense WordPress URL is known; the original report URL remains a source
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

Comparative claims preserve source-proven temporal context from findings through
candidate and final insights, summaries, Expert View, LinkedIn, and the rendered
Core signal. A source comparison that uses distinct quarters, half-years,
month/year values, fiscal years, or a forecast marker retains those qualifiers;
it is never reduced to a shared year. The deterministic editorial check blocks a
public claim only when it restates both source comparison values but loses a
source-proven qualifier, or when it contains malformed wording such as `in to`
or `between and`. It does not infer a missing period and does not reject a valid
same-year comparison merely because both qualifiers contain the same year.

The report header's Core signal uses only a complete retained sentence or a
bounded complete clause. Its deterministic clause extraction preserves
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
