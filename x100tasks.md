# x100 Output Quality Tasks

Last audited: 2026-07-08

This file is the Notion-derived x100 intake backlog for Market Lense output quality, speed, autonomy, browser-use cost, and hygiene work. It is based on the root Notion page `18 - x100 Output Quality Improvements`, all six fetched child guides, and the Browser-Use Speed and Cost x100 guide.

This is an intake backlog, not an implementation approval. Before any item starts, recheck current repository state, define baseline and target metrics, confirm owner/review date, and keep the change compliant with `AGENTS.md`.

## Source Pages

- Root hub: https://app.notion.com/p/394290cc00d381709c1bd171e4d9c690
- Prompt Output Quality Guide: https://app.notion.com/p/394290cc00d3819facf3db0c4ad8b219
- User-Facing Output Quality Guide: https://app.notion.com/p/394290cc00d381f09d1cf109205a2a11
- Candidate Crop Quality Guide: https://app.notion.com/p/394290cc00d381379771e3db0edd8eb2
- Speed x100 Improvement Guide: https://app.notion.com/p/394290cc00d381578eadea4f566c3d1f
- Browser-Use Speed and Cost x100 Guide: https://app.notion.com/p/396290cc00d3810ca575d1ecf089e565
- Autonomous System x100 Guide: https://app.notion.com/p/394290cc00d38124983fec7a5f94e0db
- Code Hygiene x100 Improvements Guide: https://app.notion.com/p/394290cc00d381eba993f3c84200d817

## Backlog Rules

- Treat this file as a separate x100 intake list, not a replacement for `CONSOLIDATED_TODO.md`.
- Promote items into `CONSOLIDATED_TODO.md` only when they become active implementation work.
- Remove or close an item when current code proves it is already resolved.
- Merge overlapping Notion items into one scoped implementation item instead of creating duplicate work.
- Before implementation starts, every prioritized item must have an owner, baseline metric, target metric, affected tests, and review/expiry date.
- Keep changes compliant with `AGENTS.md`: no placeholder logic, no role mixing, no prompt text in code, no private-helper monkeypatching, and no new deployable boundary without architecture review.
- Speed improvements must be explicit profiles or policies, not silent output-quality degradation.
- Notion remains documentation and planning only. Runtime contracts, prompts, schemas, fixtures, migrations, validation behavior, and publish gates remain repo-owned.

Scoring:

- `Impact`: `1` low leverage, `5` highest leverage across public trust, output quality, speed, cost, reliability, autonomy, or architecture.
- `Effort`: `1` localized change, `5` broad refactor/migration with cross-module coordination.

## Current-State Evidence From Notion Intake

- The root hub identifies six improvement tracks: prompt/artifact quality, public output quality, crop/visual quality, speed/throughput, autonomous operation, and code hygiene.
- The prompt guide says prompt namespaces, prompt rendering, hashing, dry-run validation, fixture coverage, JSON-oriented calls, validation, and targeted regeneration already exist; the gaps are specificity, evidence grading, claim traceability, editorial judgment, and output-quality evaluations.
- The user-facing guide says backend governance is substantial, while the public product still needs sharper editorial hierarchy, cleaner metadata, readable evidence, trust cues, navigation, CTA workflows, mobile polish, and performance gates.
- The crop guide says candidate extraction, table/chart discovery, crop refinement, strict crop modes, deterministic bbox guards, and candidate benchmarks already exist; the missing acceptance object is the final rendered PNG and HTML presentation.
- The speed guide says md5/prompt-hash caching, checkpoints, artifact fingerprints, Drive listing improvements, SQLite WAL, bounded LLM concurrency, and adaptive crop refinement already exist; remaining leverage is skip paths, LLM/browser avoidance, safe concurrency, and draft-first publishing.
- The Browser-Use guide says Market Lense already has an agent-avoidance ladder across direct PDF probes, report-page PDF-link probes, onsite capture, static email/access probes, bounded browser preflight, route playbooks, private API replay, and full browser-use fallback; the x100 path is making most repeat acquisitions stop being browser-use runs.
- The autonomy guide says preflight, retry policy, checkpoints, validation regeneration, idempotency, workflow-control observations, adaptive concurrency, and model-call audits already exist; the missing layer is one supervisor that plans, resumes, repairs, defers, publishes, and explains outcomes.
- The hygiene guide says quality gates are already substantial; remaining risk is enforcement drift, baseline debt, broad coordinators, fragmented tooling config, selective structural gates, and missing hygiene scorecards.

## Priority Order

1. Public trust and output sharpness.
2. Visual evidence and crop acceptance quality.
3. Prompt and artifact contract hardening.
4. Speed and throughput with explicit modes.
5. Browser-use agent avoidance and acquisition cost reduction.
6. Autonomous operation through existing orchestrators.
7. Code hygiene and executable enforcement.

---

## 1. Public Trust and Output Sharpness

- **Title:** Add metadata and extraction leakage gates before public rendering [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Public pages can expose placeholder metadata, polluted labels, raw extraction fragments, weak default cards, or internal-looking values.
  - Why implement: Public trust is the highest visible quality surface and should fail closed before WordPress delivery.
  - Tradeoffs / risks: Gates must distinguish incomplete-but-valid abstentions from real leakage so they do not block legitimate niche reports.
  - Acceptance Criteria:
    - Publish/readiness checks reject placeholder publishers, sentinel metadata, field-name leakage, raw OCR/table fragments, weak card summaries, and invalid archive facets.
    - Blocked reports emit typed remediation context and structured logs.
    - Tests cover positive public metadata, placeholder leakage, raw extraction leakage, and abstention/limitation states.

- **Title:** Create a shared Market Lense editorial constitution [Impact: 5/5, Effort: 2/5]
  - Problem fixed: Artifact prompts define tone and quality rules inconsistently.
  - Why implement: A reusable house style raises summaries, insights, expert comments, LinkedIn copy, Briefings, and cross-report output together.
  - Tradeoffs / risks: Shared prompt content must remain repo-owned and must not become hidden prompt text outside prompt-service control.
  - Acceptance Criteria:
    - Editorial constitution lives in a prompt namespace or shared prompt block loaded only through the prompt service.
    - It defines executive, concise, evidence-led output; anti-generic language; abstention; and unsupported-claim rules.
    - Prompt fixture coverage proves affected artifacts render with the shared block and log prompt paths/hash.

- **Title:** Add universal claim ledgers and canonical evidence IDs [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Claims can be validated only at coarse artifact level, making targeted repair and public citation harder.
  - Why implement: Claim-level support mapping makes validation, regeneration, rendering, and public trust checks precise.
  - Tradeoffs / risks: Contract changes must preserve downstream compatibility and avoid exposing internal evidence IDs directly in public HTML.
  - Acceptance Criteria:
    - Generated artifacts can include claim ledgers with claim text, artifact section, evidence IDs, support type, confidence, and risk.
    - Evidence packs use one canonical evidence reference model across findings, metrics, quotes, charts, methods, limitations, recommendations, and risks.
    - Validation and regeneration tests prove unsupported or weak claims route to targeted repair or abstention.

- **Title:** Add evidence quality grades and source-backed claim policies [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Strong prose can be generated from weak paraphrase or loose section context.
  - Why implement: High-impact claims should prefer direct metrics, direct quotes, chart readouts, explicit findings, or explicit recommendations.
  - Tradeoffs / risks: Some reports have sparse evidence, so the policy must allow transparent omissions instead of forcing generic content.
  - Acceptance Criteria:
    - Evidence objects carry quality grades such as direct metric, direct quote, chart readout, explicit finding, explicit recommendation, methodology note, section summary, or weak paraphrase.
    - Artifact prompts and validators prevent strong claims from weak evidence unless explicitly marked as low confidence or omitted.
    - Tests assert both strong-evidence generation and weak-evidence abstention behavior.

- **Title:** Build a metric spine per report [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Key quantified facts can be diluted across summaries, findings, expert comments, social copy, and cards.
  - Why implement: A metric spine makes pages concrete, consistent, and easier for executives to scan.
  - Tradeoffs / risks: Metrics must preserve unit, timeframe, segment, geography, comparator, baseline, sample size, and caveats when available.
  - Acceptance Criteria:
    - Each qualified report selects 3-6 source-backed metrics with value, unit, timeframe, segment, geography, comparator/baseline/delta where present, evidence ID, and confidence notes.
    - Summaries, cards, exhibits, and social variants reuse spine metrics without inventing missing context.
    - Contract, schema, fixture, and rendering tests cover complete and sparse metric packs.

- **Title:** Expose readable public evidence spans for high-impact claims [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Internal evidence IDs are auditable but not useful to public readers.
  - Why implement: Claims feel verifiable when users can expand source excerpts, source/page labels, and limitations.
  - Tradeoffs / risks: Public citations must redact internal paths, avoid leaking raw artifact IDs, and respect source context.
  - Acceptance Criteria:
    - Claims, metrics, quotes, recommendations, and risks render readable evidence labels and source/page context.
    - Internal evidence IDs remain available for audit but are not the public presentation layer.
    - Public rendering tests prove no raw IDs, paths, or extraction fragments leak.

- **Title:** Upgrade report cards and exhibit titles to premium editorial copy [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Cards and visual labels can look automated through weak TLDRs, raw fragments, repeated summaries, or generic figure names.
  - Why implement: Cards and exhibits are the primary discovery and credibility surfaces.
  - Tradeoffs / risks: Card copy must be concise and source-backed without duplicating full summaries.
  - Acceptance Criteria:
    - Report cards include concise analyst-grade summaries, key takeaways, valid covers, and clean metadata.
    - Figure assets include human-readable exhibit title, why-this-matters, source context, confidence, and linked claims when available.
    - Tests reject raw extraction prefixes, OCR fragments, duplicate boilerplate, placeholders, and generic figure labels.

- **Title:** Add decision brief, recommendation, and risk-register artifacts [Impact: 5/5, Effort: 5/5]
  - Problem fixed: Report pages summarize evidence but do not consistently provide a boardroom-ready decision layer.
  - Why implement: Executives need decision implications, priority moves, watchouts, risks, confidence, and source-backed recommendations.
  - Tradeoffs / risks: Advisory content must abstain when unsupported and must not infer advice from weak evidence.
  - Acceptance Criteria:
    - Optional `decision_brief`, `recommendations`, and `risk_register` artifacts are typed contracts with schema snapshots and fixture coverage.
    - Empty or weak source packs produce explicit not-found or abstention states.
    - Public renderers show source-backed content only and neutral empty states when omitted.

- **Title:** Add a source-quality and methodology trust panel [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Users cannot easily see how a page was generated, validated, constrained, or why a source is high/medium/low value.
  - Why implement: Transparent methodology and source-quality rationale make generated intelligence more defensible.
  - Tradeoffs / risks: The panel must not expose secrets, internal paths, raw logs, or unstable implementation details.
  - Acceptance Criteria:
    - Report pages can render extraction method, OCR use, validation state, abstentions, warnings, limitations, and source-quality component rationales.
    - Missing diagnostics render neutral UI or admin diagnostics, not fabricated quality claims.
    - Tests cover redaction, missing-data handling, and public copy constraints.

- **Title:** Build related intelligence navigation from approved projections [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Report pages can feel isolated from Signals, Briefings, Topics, Publishers, Figures, Regions, Time Periods, and related reports.
  - Why implement: The public site should behave like an intelligence portal, not a flat WordPress list.
  - Tradeoffs / risks: WordPress must render approved projections and must not synthesize intelligence from runtime post counts or taxonomy queries.
  - Acceptance Criteria:
    - Related Reports, Briefings, Signals, Topics, Publishers, Figures, Regions, and Time Periods are derived from validated artifacts and metadata projections.
    - Missing projections fail closed with neutral UI or admin diagnostics.
    - Tests prove no strategic claim is generated solely from WordPress runtime queries.

- **Title:** Harden archive/search facets, mobile workflows, CTAs, and public performance [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Search, archive, intake, and mobile/performance issues can make the public product feel unfinished even when report content is strong.
  - Why implement: Discovery and intake workflows are part of output quality.
  - Tradeoffs / risks: Frontend changes need screenshot coverage and must preserve canonical URLs/social metadata.
  - Acceptance Criteria:
    - Archives support validated facets such as report type, key-figure availability, visual evidence count, source-quality band, methodology availability, validation status, and signal support.
    - Briefing, correction, and report/source submission CTAs resolve to real intake flows with validation and confirmation states.
    - Mobile/tablet/desktop smoke screenshots cover homepage, search, archive, report detail, contact, and submit pages with no overflow or clipped controls.
    - Performance gates track response start, DOM complete, request count, page weight, canonical URLs, Open Graph, and Twitter metadata.

---

## 2. Visual Evidence and Crop Acceptance Quality

- **Title:** Add post-render crop QA as the final crop acceptance gate [Impact: 5/5, Effort: 4/5]
  - Problem fixed: The pipeline validates candidates and bboxes, but the final rendered PNG is not the acceptance object.
  - Why implement: Public pages should only show crops that are complete, readable, cleanly bounded, and useful as evidence.
  - Tradeoffs / risks: QA must avoid rejecting valid design variants such as dark slides, shaded cards, and multi-panel reports.
  - Acceptance Criteria:
    - `verify_crop_image` or equivalent runs after final PNG render and before acceptance.
    - Checks cover edge-clipped text, oversized margins, neighbor contamination, readability, suspicious aspect ratio, and missing title/source/legend when present.
    - Rejected crops are omitted from public HTML or routed to repair with typed defect labels.

- **Title:** Add crop quality scores and diagnostics sidecars [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Crop failures are hard to inspect and benchmark because crop decisions lack a complete diagnostic artifact.
  - Why implement: Scores and sidecars make selection, fallback ordering, repair, and regression tests observable.
  - Tradeoffs / risks: Sidecar schema must be stable enough for benchmarks without overfitting to one crop algorithm.
  - Acceptance Criteria:
    - Crop metadata includes content completeness, edge integrity, margin balance, neighbor contamination, readability, visual crispness, total score, and defect labels.
    - Each crop writes a diagnostics JSON sidecar with candidate ID/type, page, original/refined/final bbox, render scale, trims, QA score, defects, repair actions, accepted, and rejection reason.
    - Tests and benchmarks assert diagnostics presence and meaningful failure labels.

- **Title:** Create `publication_strict` crop mode and remove legacy user-facing fallback [Impact: 5/5, Effort: 4/5]
  - Problem fixed: User-facing fallback crops can use lower-quality legacy behavior.
  - Why implement: One production-grade crop mode should own final public visual quality.
  - Tradeoffs / risks: Compatibility with existing chart/table strict modes must be preserved or migrated explicitly.
  - Acceptance Criteria:
    - `publication_strict` runs bbox tightening, optional multimodal refine, edge guard, high-DPI render, content-aware trim, final PNG QA, repair loop, and acceptance scoring.
    - Table fallbacks use table-strict behavior, chart fallbacks use chart-strict behavior, and mixed/unknown visuals use publication-strict behavior.
    - Tests prove no final user-facing crop is created by legacy mode except diagnostic-only outputs.

- **Title:** Add final crop-image multimodal QA and bounded auto-repair [Impact: 5/5, Effort: 5/5]
  - Problem fixed: Bbox refinement can still produce clipped, contaminated, or poorly framed final images.
  - Why implement: Multimodal crop QA and repair can catch issues only visible in the final PNG.
  - Tradeoffs / risks: Model-backed QA must be bounded, logged, and optional under explicit speed profiles.
  - Acceptance Criteria:
    - Final crop QA returns accept, repair, or reject with defect labels.
    - Repair can expand clipped sides, trim unrelated fragments, snap to card/table boundaries, and rebalance whitespace.
    - Repair loops are capped at 2-3 iterations and stop when quality does not improve.

- **Title:** Replace uniform border trim with content-aware crop trim [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Fixed color/tolerance trimming fails on shaded cards, dark slides, gradients, and colored report panels.
  - Why implement: Content-aware trimming improves final margin balance without clipping meaningful content.
  - Tradeoffs / risks: Trim logic must account for text-block edge awareness and intentional card backgrounds.
  - Acceptance Criteria:
    - Trimming uses edge density, connected components, text-block edge awareness, background segmentation, and per-side adaptive thresholds.
    - Adaptive padding varies by table, chart, and infographic card crop type.
    - Golden crop tests cover dark slides, colored cards, and dense tables.

- **Title:** Render final selected crops at higher quality profiles [Impact: 4/5, Effort: 2/5]
  - Problem fixed: Low-DPI preview renders can cause bbox mistakes and unreadable final images.
  - Why implement: Selected public crops need higher-resolution rendering than discovery previews.
  - Tradeoffs / risks: Higher DPI increases runtime and storage, so it should apply to final selected crops and be explicit by profile.
  - Acceptance Criteria:
    - Discovery, crop-refinement, and final-visual-QA DPI profiles are configurable.
    - Final selected crops render at a higher quality profile with downsampling only when needed for HTML performance.
    - Benchmarks report runtime and artifact-size deltas.

- **Title:** Add table boundary, chart completeness, and visual card boundary detectors [Impact: 4/5, Effort: 5/5]
  - Problem fixed: Crops can clip table rules, chart axes/legends/sources, or infographic card containers.
  - Why implement: Different visual types need completeness checks that match their semantic structure.
  - Tradeoffs / risks: Detector confidence must be explicit to avoid snapping to unrelated page decorations.
  - Acceptance Criteria:
    - Table crops can snap to high-confidence outer rules using drawings, raster edges, text alignment clusters, and header bands.
    - Chart crops detect axis labels, tick labels, legend blocks, title/caption, source, and notes.
    - Infographic crops detect visible card/container boundaries, shadows, backgrounds, and internal group spacing.

- **Title:** Add neighbor-contamination detection for final crops [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Final crops may include adjacent panel fragments, following headings, footers, page numbers, prose, or decorative images.
  - Why implement: Even complete visuals lose credibility when unrelated neighboring content appears inside the crop.
  - Tradeoffs / risks: The detector must tolerate legitimate multi-panel figures and grouped exhibit decks.
  - Acceptance Criteria:
    - Detection uses PDF text-block geometry and raster connected components.
    - Legitimate grouped panels can be accepted with a clear figure-group classification.
    - Tests cover adjacent headings, footer/page-number contamination, decorative images, and valid multi-panel charts.

- **Title:** Build golden crop fixtures and visual crop benchmarks [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Candidate count/signature benchmarks can pass while final crop visual quality regresses.
  - Why implement: Crop quality needs rendered-image metrics and difficult fixture coverage.
  - Tradeoffs / risks: Golden fixtures must be curated, stable, and small enough for CI or split into local/live tiers.
  - Acceptance Criteria:
    - A manual golden set covers 50-100 difficult crop examples over dense reports, dark slides, colored cards, multi-panel pages, tables, small footnotes, and decorative-photo layouts.
    - Benchmarks report golden bbox IoU, final PNG perceptual diff, whitespace percentage, clipped text count, neighbor contamination count, OCR completeness ratio, and minimum readable text height.
    - Benchmark deltas are attached to release evidence or local quality reports.

- **Title:** Add publisher/style crop profiles and HTML visual smoke tests [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Recurring publisher layouts and final HTML presentation can still regress after crop selection succeeds.
  - Why implement: Publisher-specific layout memory and browser screenshots protect the actual public presentation.
  - Tradeoffs / risks: Profiles must not become brittle special cases that bypass global crop acceptance rules.
  - Acceptance Criteria:
    - Publisher/style profiles store preferred padding, title/source/note positions, card-background handling, theme behavior, and multi-panel spacing heuristics.
    - HTML smoke tests assert images are not blurry at display size, do not overflow, captions align, margins look consistent, and images are not unreadable thumbnails.
    - Profile decisions are logged and benchmarked against non-profile fallback behavior.

---

## 3. Prompt and Artifact Contract Hardening

- **Title:** Add prompt partials or controlled shared prompt composition [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Grounding, JSON discipline, evidence policy, metric policy, abstention, style, and anti-generic rules can drift across prompt namespaces.
  - Why implement: Shared prompt fragments make output quality consistent and easier to validate.
  - Tradeoffs / risks: Composition must remain deterministic and owned by the prompt service, not by generators.
  - Acceptance Criteria:
    - Prompt service supports shared includes or controlled pre-render composition with prompt paths, hash, rendered text, and model parameters logged.
    - Generators request prompts by name and never concatenate prompt text.
    - Fixture coverage proves shared blocks are included consistently.

- **Title:** Generate prompt schema snippets from source-of-truth contracts [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Loose hand-written schema descriptions in prompts can drift from runtime contracts.
  - Why implement: Runtime contracts should remain the schema authority and prompt text should reflect them deterministically.
  - Tradeoffs / risks: Schema snippets must be concise enough for token budgets and stable enough for fixture regression.
  - Acceptance Criteria:
    - Prompt schema snippets are generated from canonical contracts or JSON schemas.
    - Snippets include required fields, allowed null/empty behavior, min/max counts, enums, field descriptions, and valid/invalid examples where useful.
    - Contract/schema snapshot tests and prompt fixture tests catch schema drift.

- **Title:** Add abstention-first artifact generation rules [Impact: 5/5, Effort: 2/5]
  - Problem fixed: Sparse evidence can produce generic or hallucinated content instead of transparent omission.
  - Why implement: Trust improves when weak artifacts return explicit not-found or limitation states.
  - Tradeoffs / risks: Public rendering must handle empty artifacts gracefully.
  - Acceptance Criteria:
    - Artifact prompts support empty artifact status metadata, missing evidence type, and precise regeneration target when possible.
    - Validators accept correct abstentions and reject unsupported generated filler.
    - Positive and negative tests cover enough-evidence, weak-evidence, and no-evidence cases.

- **Title:** Add scored insight selection and strategic coverage roles [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Accurate insights can still be repetitive, generic, or weakly strategic.
  - Why implement: Insight selection should surface decision-relevant, specific, non-obvious, well-supported coverage.
  - Tradeoffs / risks: Scores should improve selection without becoming an unexplained black box.
  - Acceptance Criteria:
    - Insight candidates include decision relevance, metric strength, specificity, novelty, ecommerce/digital relevance, evidence strength, non-obviousness, actionability, and non-overlap scores.
    - Final insights carry coverage roles such as market shift, customer behavior, operational implication, commercial signal, technology/channel signal, risk, recommendation, or methodology caveat.
    - Tests assert selection diversity, evidence support, and no duplicated low-value insights.

- **Title:** Add `so what` and `now what` fields plus report-type lensing [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Outputs can read as flat summaries rather than decision-support analysis.
  - Why implement: Readers need what changed, why it matters, operator implication, watchout, and decision question.
  - Tradeoffs / risks: Action language must remain source-backed and domain lensing must not introduce unsupported extrapolation.
  - Acceptance Criteria:
    - Summary, expert comment, LinkedIn post, and cross-report synthesis contracts include analytical fields where appropriate.
    - Artifact generation accepts structured report lenses such as ecommerce, digital marketing, Amazon marketplaces, retail media, consumer trends, payments, logistics, AI commerce, platform policy, or category intelligence.
    - Tests cover domain lens selection and unsupported-action abstention.

- **Title:** Create `topics_covered`, `key_figures`, and chart insight card artifacts [Impact: 5/5, Effort: 5/5]
  - Problem fixed: Public pages need scannable topic, figure, and chart modules that are more structured than generic prose.
  - Why implement: These artifacts make report pages more useful and connect prompt output to public rendering.
  - Tradeoffs / risks: New artifacts require contracts, fixtures, validators, renderers, and migration-safe optional handling.
  - Acceptance Criteria:
    - `topics_covered` includes topic, subtopics, why it matters, evidence IDs, and pages.
    - `key_figures` includes figure, unit, segment, geography, timeframe, source page, why it matters, caveat, evidence ID, and related chart candidate when available.
    - Chart insight cards include caption, chart takeaway, business implication, metric mentions, evidence confidence, and avoid reason if weak.

- **Title:** Make visual ranking editorial as well as visual-quality based [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Selected charts can be visually dense but not the most useful evidence for the page.
  - Why implement: Figures should support the report thesis, standalone usefulness, executive readability, social usefulness, and summary/insight relevance.
  - Tradeoffs / risks: Editorial ranking must not bypass visual QA or select low-quality crops.
  - Acceptance Criteria:
    - `rank_candidates` includes editorial dimensions for thesis support, standalone usefulness, executive readability, differentiated data, non-duplication, social usefulness, and evidence relevance.
    - Visual-quality and editorial-quality scores are both logged and available for selection decisions.
    - Tests prove low-quality visuals cannot win solely on editorial usefulness.

- **Title:** Generate LinkedIn post variants by persona with evidence ledgers [Impact: 3/5, Effort: 3/5]
  - Problem fixed: A single social post variant limits reuse and can miss audience framing.
  - Why implement: Persona variants make report output more useful for promotion while preserving evidence discipline.
  - Tradeoffs / risks: Social copy is high risk for unsupported claims and generic language.
  - Acceptance Criteria:
    - LinkedIn output includes executive insight, operator practical, and data-led variants with hook, body, optional bullets, hashtags, evidence ledger, and unsupported-claim risk flag.
    - Banned-pattern and claim-ledger checks apply to every variant.
    - Tests reject unsupported hooks and generic first sentences.

- **Title:** Add anti-generic banned-pattern checks [Impact: 4/5, Effort: 2/5]
  - Problem fixed: AI-sounding phrases lower perceived quality even when content is accurate.
  - Why implement: Banned-pattern checks provide fast, deterministic quality feedback.
  - Tradeoffs / risks: Phrase checks must not become overbroad false positives for legitimate source quotes.
  - Acceptance Criteria:
    - Checks cover phrases such as rapidly evolving landscape, game changer, unlock, leverage, delve, robust, seamless, crucial, it is important to note, and this report highlights.
    - First sentences must include a concrete noun, metric, category, market actor, or implication unless quoting source text.
    - Tests cover generated copy, source quotes, and allowed technical terms.

- **Title:** Add safe comparative positioning for cross-report synthesis [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Multi-report output needs useful comparison without unsafe metric normalization.
  - Why implement: Cross-report synthesis can compare themes, assumptions, evidence direction, methodology, and audience implications while preserving data integrity.
  - Tradeoffs / risks: Raw metric magnitudes must not be compared across publishers unless normalized by source evidence and explicitly allowed.
  - Acceptance Criteria:
    - Cross-report prompts allow comparisons on themes, assumptions, evidence direction, publisher focus, methodology differences, audience implications, and convergent/divergent claims.
    - Validators reject unsupported cross-publisher metric normalization.
    - Fixture tests cover convergence, divergence, and limitation language.

- **Title:** Make regeneration critique-first and validation severity-aware [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Regeneration can rewrite broadly instead of repairing the precise failed claim or field.
  - Why implement: Critique-first repair and severity routing make validation/remediation targeted and publish-safe.
  - Tradeoffs / risks: Repair payloads must remain machine-facing and not leak into public HTML.
  - Acceptance Criteria:
    - Regeneration output includes diagnosis, sentences to replace, evidence to use, risks removed, and repaired artifact.
    - Validation output includes severity, repair target namespace, suggested fix instruction, can-publish-with-warning, and affected artifact field.
    - Tests cover blocker, warning, info, targeted repair, and publish-with-warning routing.

- **Title:** Build golden-output prompt evaluations [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Prompt regression currently protects renderability and costs more than qualitative output quality.
  - Why implement: Golden-output checks catch generic, unsupported, schema-weak, or low-value artifacts.
  - Tradeoffs / risks: Golden checks must be deterministic and avoid brittle wording expectations.
  - Acceptance Criteria:
    - Prompt fixtures assert no generic hooks, every metric has unit/timeframe when available, every artifact claim has evidence, summaries avoid unsupported extrapolation, captions include business implication, expert comments do not restate insights, and cross-report synthesis distinguishes convergence/divergence/limitations.
    - Golden-output failures emit clear rule IDs and affected artifact fields.
    - CI or local quality gates include bounded prompt-quality evaluation.

---

## 4. Speed and Throughput With Explicit Modes

- **Title:** Add a formal `fast_ingest` profile [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Operators lack an explicit time-to-first-report mode that preserves full editorial mode separately.
  - Why implement: Fast draft output should defer expensive non-critical stages without silently lowering default quality.
  - Tradeoffs / risks: Fast mode must be logged and visible so draft artifacts are not mistaken for full editorial output.
  - Acceptance Criteria:
    - `fast_ingest` profile explicitly disables or defers figure captions, deep validation regeneration, crop-refine LLM, signal artifacts, public-site checks, and expensive grounding where configured.
    - Fast/default/full profiles are versioned and loaded through config/workflow-control.
    - Logs expose active profile, skipped stages, deferred stages, cache hits/misses, and quality tradeoffs.

- **Title:** Enable automatic latest-safe resume from ingest [Impact: 5/5, Effort: 2/5]
  - Problem fixed: Reruns can redo work even though the report pipeline supports latest-safe checkpoint resume.
  - Why implement: Warm reruns should skip directly to the newest valid checkpoint.
  - Tradeoffs / risks: Operators must still have an explicit clean-run option.
  - Acceptance Criteria:
    - Ingest calls report pipeline with `auto_resume_from_latest_safe=True` unless clean run is explicitly requested.
    - Checkpoint artifact integrity is validated before reuse.
    - Tests cover warm rerun, corrupt checkpoint, missing artifact, and explicit clean run.

- **Title:** Lazily construct LLM/model clients by reached stage [Impact: 3/5, Effort: 2/5]
  - Problem fixed: Multiple scoped clients can be constructed before the pipeline knows which scopes are needed.
  - Why implement: Lazy construction reduces startup overhead and avoids unnecessary provider setup in skipped stages.
  - Tradeoffs / risks: Dependency injection boundaries must remain explicit and generators must not construct clients.
  - Acceptance Criteria:
    - OCR, validation, regeneration, caption, and artifact clients are constructed only when their stage is reached.
    - Logs show client construction by role/stage.
    - Tests prove skipped stages do not initialize unused model clients.

- **Title:** Model report generation as a DAG scheduler [Impact: 5/5, Effort: 5/5]
  - Problem fixed: Some independent work waits unnecessarily behind vector indexing or serial stage order.
  - Why implement: A DAG can run non-dependent source prep, vector indexing, figure selection, preview rendering, taxonomy/evidence/artifacts, and render work under safe dependencies.
  - Tradeoffs / risks: This is a control-plane refactor and must preserve domain behavior, retries, idempotency, logs, and checkpoints.
  - Acceptance Criteria:
    - Stage dependencies are explicit typed data, not implicit branch order.
    - Non-vector-dependent nodes can run while vector indexing is pending.
    - Pipeline tests prove state transitions, retry counts, checkpoint semantics, and idempotency remain unchanged or approved.

- **Title:** Replace fixed vector-store polling with fast-first polling [Impact: 3/5, Effort: 2/5]
  - Problem fixed: Fixed 5-second polling wastes time when indexing finishes quickly.
  - Why implement: Fast-first polling reduces latency without changing provider timeout semantics.
  - Tradeoffs / risks: Polling must remain bounded and must not increase provider load excessively.
  - Acceptance Criteria:
    - Poll schedule uses fast-first delays such as 0.5s, 1s, 2s, then 5s capped by existing timeout.
    - Bulk runs can batch status checks where service support exists.
    - Tests assert attempt count, delays, timeout, and structured retry/defer logs.

- **Title:** Parallelize independent table and chart ranking under global LLM caps [Impact: 3/5, Effort: 3/5]
  - Problem fixed: Independent ranking batches can run serially and increase latency.
  - Why implement: Controlled parallelism can reduce report runtime without increasing total model work.
  - Tradeoffs / risks: Must respect global model concurrency, retry policy, and deterministic output ordering.
  - Acceptance Criteria:
    - Table and chart ranking can run concurrently when workflow-control allows it.
    - Final candidate ordering remains deterministic.
    - Tests assert concurrency limits, stable ordering, and retry propagation.

- **Title:** Add deterministic ranking and crop-refine shortcuts [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Strong candidates can still incur ranking and crop-refine model calls.
  - Why implement: Obvious-pass/obvious-reject paths reduce latency and cost while preserving full mode.
  - Tradeoffs / risks: Shortcuts must not silently degrade visual or editorial quality.
  - Acceptance Criteria:
    - Ranking LLM is bypassed when deterministic scoring yields enough strong table/chart candidates.
    - `rank_max_candidates` is adaptive by profile and escalates only when no acceptable figures are found.
    - Fast mode uses one-pass crop refinement or deterministic bbox expansion, and high-confidence candidates can skip crop-refine LLM.

- **Title:** Centralize page-render caching across PDF stages [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Contents previews, crop-refine page renders, final crop renders, and candidate extraction can duplicate page rendering work.
  - Why implement: A shared render cache improves warm runs and reduces repeated PDF rendering.
  - Tradeoffs / risks: Cache keys must include enough versioning to avoid stale artifacts.
  - Acceptance Criteria:
    - Page render cache is keyed by PDF md5, page number, DPI, render variant, and crop/cache version.
    - PDF stages use the canonical page-render cache through service boundaries.
    - Tests cover cache hit/miss, invalidation, artifact hash, and equivalent output.

- **Title:** Reuse native text and add worker-safe PDF contexts [Impact: 3/5, Effort: 3/5]
  - Problem fixed: Source prep can reload native text and reopen/reparse PDFs across parallel tasks.
  - Why implement: Reusing parsed state reduces local CPU and I/O overhead.
  - Tradeoffs / risks: PDF contexts must remain worker-safe and avoid unsafe shared document access.
  - Acceptance Criteria:
    - Initial native text response/status are reused unless OCR changed the analysis PDF.
    - A per-worker PDF context pool or equivalent reduces repeated parsing without shared unsafe state.
    - Tests cover OCR-change invalidation and parallel worker safety assumptions.

- **Title:** Split Drive/cache prefetch from report-generation workers [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Bulk ingestion can wait on Drive download/cache materialization before keeping downstream workers busy.
  - Why implement: Producer/consumer separation improves throughput without increasing LLM rate-limit pressure.
  - Tradeoffs / risks: Queue semantics must be idempotent and must not create new deployable boundaries without review.
  - Acceptance Criteria:
    - Producer lists Drive, prefilters state, downloads/caches PDFs, computes md5, and feeds report-generation consumers.
    - Workflow-control telemetry manages Drive/PDF/LLM concurrency separately.
    - Tests cover duplicate suppression, retry/defer behavior, and provider cap preservation.

- **Title:** Make Drive listing cursor-first and batch skip metadata complete [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Large Drive folders can be rescanned, and per-file skip decisions can require extra state checks.
  - Why implement: Cursor-first listing and full batch skip metadata reduce bulk ingest overhead.
  - Tradeoffs / risks: Operators need an explicit rescan path for intentional full scans.
  - Acceptance Criteria:
    - Per-folder cursor semantics are default for all modes unless `--rescan` or equivalent is explicit.
    - Batch state query returns processed state, last error, text-validation status, vector-store status, and retryability flags.
    - Tests cover limit overrides, forced report-card runs, rescan, and processed-state skip decisions.

- **Title:** Key vector-store reuse by md5 [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Duplicate or renamed PDFs may not reuse the same indexed vector store if reuse is file-state oriented.
  - Why implement: md5-keyed reuse avoids repeated indexing for identical content.
  - Tradeoffs / risks: Alias handling and lifecycle cleanup need clear ownership and idempotency.
  - Acceptance Criteria:
    - State stores md5-keyed vector-store cache entries with file aliases and artifact refs.
    - Duplicate/renamed PDFs reuse existing indexed stores when compatible.
    - Tests cover alias creation, reuse, stale store handling, and cleanup policy.

- **Title:** Split validation into inline deterministic and deferred LLM grounding [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Validation and regeneration loops can dominate latency for drafts and bulk ingestion.
  - Why implement: Deterministic schema/completeness checks can run inline while expensive evidence grounding is deferred to publish or high-value paths.
  - Tradeoffs / risks: Draft outputs must be clearly marked and blocked from final publish until required grounding completes.
  - Acceptance Criteria:
    - Inline validation covers schema, required fields, artifact completeness, and references.
    - Deferred validation covers expensive grounding and regeneration before final publish or high-value reports.
    - Workflow-control records deferred validation obligations and publish gates consume them.

- **Title:** Publish draft HTML first and enrich later [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Report publication waits for every enrichment module even when a useful draft page could exist sooner.
  - Why implement: Draft-first output improves time-to-value while preserving full editorial mode.
  - Tradeoffs / risks: Draft state must be explicit and public policy must decide whether drafts are visible, private, or preview-only.
  - Acceptance Criteria:
    - Draft pages include metadata, summary, topics, key findings, and available figures.
    - Later enrichment can add captions, srcsets, signal artifacts, LinkedIn variants, performance checks, and full validation.
    - Tests cover draft state, enrichment transition, publish gating, and no silent downgrade of full mode.

---

## 5. Browser-Use Speed and Cost

- **Title:** Enable private-API and route-playbook promotion through canary rollout [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Repeated browser routes can remain expensive manual agent runs even when network evidence reveals deterministic HTTP or private-API replay paths.
  - Why implement: The largest cost reduction comes from converting browser-use routes into direct replay routes.
  - Tradeoffs / risks: Promotion thresholds must stay conservative globally and stricter validation must protect low-threshold trusted-publisher overrides.
  - Acceptance Criteria:
    - Route and private-API promotion can run in `dry_run` for trusted publishers, then `write` after reviewed candidate fingerprints and verified PDF artifacts.
    - Publisher-scoped threshold overrides can lower required successes/source diversity only with same-host, expected-status, required-marker, and artifact-validation checks.
    - Private-API replay falls back to the original browser route when endpoint validation fails and logs promotion decisions.

- **Title:** Add a deterministic executor for normal route playbooks [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Selected route playbooks guide the LLM instead of executing known steps directly.
  - Why implement: DOM-level execution can avoid LLM calls for recurring gated forms and PDF-click routes.
  - Tradeoffs / risks: Executor drift must fall back to browser-use and persist evidence rather than silently failing.
  - Acceptance Criteria:
    - Playbook steps support deterministic open, click, fill, select, submit, and verify actions with CSS/text/role selectors and confidence scoring.
    - Executor runs before full browser-use for eligible playbooks.
    - Drift evidence is persisted and routed back into playbook improvement.

- **Title:** Persist artifact-level acquisition cache [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Route memory can choose a path, but unchanged reports may still rerun acquisition instead of returning a valid existing artifact.
  - Why implement: Returning a valid cached local/Drive artifact eliminates the entire browser/HTTP acquisition path.
  - Tradeoffs / risks: Cache keys and invalidation must prevent stale or wrong-publisher artifacts.
  - Acceptance Criteria:
    - Cache keys include normalized URL, publisher scope, report title, final artifact URL, artifact md5/sha256, and relevant prompt/schema/cache versions.
    - Cached artifacts are reused only when local/Drive artifact validation passes.
    - Revalidation occurs when URL, report title, artifact presence/hash, cache version, or expiry changes.

- **Title:** Strengthen publisher-level route policy before browser escalation [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Planner can spend low-yield probes or browser launches despite stable publisher route history.
  - Why implement: Publisher-level success distributions should schedule dominant routes first and demote repeatedly failing fallbacks.
  - Tradeoffs / risks: Stale or conflicting policy evidence must fail closed and preserve safe recovery classes.
  - Acceptance Criteria:
    - Per-publisher route success distribution, failure distribution, TTL, and route-family confidence are persisted.
    - Dominant route families run first and repeatedly failing fallback routes are demoted.
    - Route decisions log selected family, confidence, TTL status, avoided browser/model-call estimate, and recovery class.

- **Title:** Add HTTP-only static DOM scan before browser preflight [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Bounded browser preflight still launches a browser for pages where static HTML/scripts/meta tags may reveal PDF candidates.
  - Why implement: Static extraction can find many report assets before any browser startup.
  - Tradeoffs / risks: Static candidates must be validated by MIME/type and file signature before acceptance.
  - Acceptance Criteria:
    - HTTP scan extracts PDF/document candidates from anchors, scripts, JSON, JSON-LD, meta tags, OpenGraph tags, canonical URLs, and embedded `.pdf` strings.
    - Candidates are validated by response status, MIME/type, file signature, and publisher/report scope.
    - Browser preflight runs only when static extraction is inconclusive.

- **Title:** Narrow browser preflight eligibility and reuse preflight state on escalation [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Browser preflight can spend 10-24 seconds on low-yield pages and then full browser-use can double-launch from scratch.
  - Why implement: Preflight should run only when likely to find rendered assets, and escalation should reuse page/session state.
  - Tradeoffs / risks: Session reuse must remain scoped, deterministic, and cleaned up on failure.
  - Acceptance Criteria:
    - Preflight is skipped for known email gates, listing hubs, and publishers with poor rendered-PDF history unless static/candidate evidence suggests value.
    - Preflight browser/page can remain alive when escalation is likely and pass cookies, local storage, current URL, and downloaded-candidate context to the full agent path.
    - Failure cleanup is deterministic and tests cover skip, reuse, and cleanup paths.

- **Title:** Add route-specific agent step and timeout budgets [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Global `max_steps` and timeout buffers produce overly loose stuck-run envelopes for simple routes.
  - Why implement: Route-specific budgets reduce LLM calls, wall time, and blocked worker capacity.
  - Tradeoffs / risks: Budgets must escalate only when terminal evidence suggests real progress.
  - Acceptance Criteria:
    - `browser_pdf_click`, `browser_email_form`, `browser_onsite_report`, and `browser_listing_hub` have explicit max-step and timeout policies.
    - Worker timeout buffers vary by route family and trigger terminal salvage before the outer envelope expires.
    - Known impossible routes such as CAPTCHA, 403, and business-email rejection fail fast with typed outcomes.

- **Title:** Stop browser-use on terminal evidence [Impact: 5/5, Effort: 3/5]
  - Problem fixed: The agent can continue reasoning/action steps after success or known terminal failure has already appeared.
  - Why implement: Early stopping avoids extra model calls and latency after a valid artifact, email confirmation, blocker, or terminal page is observed.
  - Tradeoffs / risks: Watchers must avoid false terminal detection and must route through normal artifact finalization.
  - Acceptance Criteria:
    - Agent runtime watches download directory, network PDF/document URLs, visible confirmation text, form disappearance, and known blocker text.
    - Terminal evidence signals agent stop and moves directly to typed artifact finalization or blocker handling.
    - Tests cover valid download, email confirmation, known blocker, and false-positive non-terminal text.

- **Title:** Split browser prompts by route family and minimize playbook payload [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Browser prompts can include broad context, multiple playbooks, route metadata, identity fields, consent policy, and candidate traces even when only one route family matters.
  - Why implement: Smaller route-specific prompts reduce token cost, latency, and agent confusion without changing the model.
  - Tradeoffs / risks: Prompt text must stay in prompt namespaces and full playbook YAML must remain outside ad hoc prompt construction.
  - Acceptance Criteria:
    - Prompt namespaces exist for `browser_pdf_click`, `browser_email_form`, `browser_onsite_report`, and `browser_listing_hub`.
    - Prompts include only route-relevant variables, the winning playbook by default, compact trap labels, and alternatives only on low-confidence selection.
    - Prompt paths, hashes, rendered text, and model parameters are logged through the prompt service.

- **Title:** Run deterministic form autofill before invoking the LLM [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Known identity fields and consent policy can consume LLM steps on email-gated reports.
  - Why implement: DOM-based autofill can submit unambiguous forms without browser-use reasoning.
  - Tradeoffs / risks: Unknown required fields, ambiguous selects, and consent uncertainty must escalate rather than guess.
  - Acceptance Criteria:
    - Visible form fields are detected through DOM inspection and filled with configured identity values when confidence is high.
    - Consent rules are applied deterministically from `browser_download_identity.yaml`.
    - LLM/browser-use runs only for unknown required fields, ambiguous select values, route drift, or uncertain consent.

- **Title:** Enable same-publisher session reuse and warm browser worker pools for batches [Impact: 5/5, Effort: 5/5]
  - Problem fixed: Batch acquisition can repeatedly pay profile creation, cookie banner, subprocess startup, payload handoff, and browser setup costs.
  - Why implement: Warm same-publisher sessions and workers reduce startup overhead for batches while preserving crash isolation fallback.
  - Tradeoffs / risks: Cross-publisher leakage is unacceptable; workers need restart limits and memory-pressure handling.
  - Acceptance Criteria:
    - Session reuse is enabled only for batch acquisition, scoped by publisher host, uses short TTLs, and disables cross-publisher reuse unless explicitly safe.
    - Warm isolated workers can process batch/publisher jobs through IPC or equivalent while the subprocess path remains a fallback.
    - Workers restart after N runs or memory pressure, and telemetry records reuse outcomes.

- **Title:** Make browser evidence and failure forensics conditional [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Success and expected-blocker paths can capture heavy screenshots, HTML snapshots, assets, network resources, copied artifacts, and detailed logs unnecessarily.
  - Why implement: Known verified routes and repeated expected blockers should be cheap to record.
  - Tradeoffs / risks: Novel failures and sampled audits still need rich forensic packs for route improvement.
  - Acceptance Criteria:
    - Known verified success paths store minimal evidence: artifact hash, artifact URL, route ID, validation status, and final URL.
    - Full evidence is retained for new publishers, new routes, failed runs, sampled audits, route drift, parser errors, and suspected regressions.
    - Expected blockers such as CAPTCHA, 403, static archive blocks, business-email rejection, and remembered blockers default to metadata-only forensics.

- **Title:** Optimize publisher-inventory browser traversal waits and scrolling [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Publisher inventory discovery can repeatedly scroll, wait, and probe nested surfaces even when candidate growth is unlikely.
  - Why implement: Inventory traversal speed improves when DOM extraction, growth fingerprints, and event waits replace fixed loops.
  - Tradeoffs / risks: Scroll reduction must not miss virtualized or nested report lists for publishers that require it.
  - Acceptance Criteria:
    - Per-publisher telemetry records whether nested scrolling or virtualization is needed and how much candidate growth each scroll produced.
    - Traversal starts with DOM extraction, scrolls only when candidate growth is expected, and stops after no-growth fingerprints.
    - Fixed sleeps are replaced with URL/candidate-signature waits where possible, settle helpers receive page context consistently, and latency by wait reason is logged.

---

## 6. Autonomous Operation Through Existing Orchestrators

- **Title:** Build a single autonomous run supervisor [Impact: 5/5, Effort: 5/5]
  - Problem fixed: Operators still choose between ingest, publish, download, mailbox poll, or UI replay entrypoints.
  - Why implement: One supervisor can plan, resume, retry, repair, defer, publish, dead-letter, or notify safely.
  - Tradeoffs / risks: The supervisor must not duplicate generator domain logic or service I/O.
  - Acceptance Criteria:
    - Supervisor consumes state, checkpoints, preflight reports, retry telemetry, validation failures, idempotency records, publish readiness, and health scorecards.
    - It emits typed supervisor decisions before each side effect.
    - Execution routes through existing orchestrators and canonical services only.

- **Title:** Add a read-only `PipelinePlan` before execution [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Operators request implementation flags instead of intent and side-effect visibility.
  - Why implement: A no-side-effect plan makes autonomous runs inspectable and safer.
  - Tradeoffs / risks: Plan generation must not pre-create side effects or perform expensive work.
  - Acceptance Criteria:
    - `autopilot --plan-only` or equivalent produces typed steps, skipped work, blockers, credentials, side effects, checkpoints, idempotency keys, and expected artifacts.
    - Plans cover ready, partial, failed, missing-credential, and publish-only states.
    - Plan execution uses existing orchestrators without duplicating domain logic.

- **Title:** Make workflow-control mandatory execution authority [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Workflow-control can resolve metadata, but paths may still bypass policy gates.
  - Why implement: Autonomy needs one authority for intent, retry policy, preflight profile, publish policy, pre-LLM gates, operational memory, and concurrency.
  - Tradeoffs / risks: Existing CLI/UI paths must be migrated carefully to avoid behavior drift.
  - Acceptance Criteria:
    - No CLI/UI autonomous path bypasses workflow-control gates.
    - Every workflow logs resolved intent, retry policy, side-effect plan, budget profile, resume stage, and blockers.
    - Tests cover direct CLI, UI replay, supervisor, and publish-ready paths.

- **Title:** Implement durable autonomous dead letters and scheduled actions [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Failures and deferred work are not consistently managed as pipeline-wide autonomous work items.
  - Why implement: Temporary rate limits, endpoint instability, mailbox delays, credential refresh windows, and terminal failures should recover or escalate without manual reruns.
  - Tradeoffs / risks: Duplicate failure loops must be suppressed and state migrations must be backwards compatible.
  - Acceptance Criteria:
    - `autonomous_dead_letters` records run ID, workflow, step, AppError taxonomy, retry decision, checkpoint stage, input checksum, artifact refs, remediation code, and runbook link.
    - `scheduled_actions` records workflow, step, payload reference, earliest/latest run time, retry decision, blocker code, dependency, and attempt budget.
    - Tests cover transient retry cooldown, permanent dead-letter, duplicate loop suppression, and user-action-required scheduling.

- **Title:** Turn mailbox delivery into an autonomous worker [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Mail delivery requests still depend on manual polling paths.
  - Why implement: Gated-report acquisition should continue through workflow-control without operator intervention.
  - Tradeoffs / risks: Worker must ignore unrelated mailbox messages and prevent duplicate processing.
  - Acceptance Criteria:
    - Due mailbox requests are selected by workflow-control and passed to existing mail acquisition orchestrators.
    - Seen message IDs, publisher/domain matching, and delivery-intent matching prevent cross-publisher contamination.
    - Successful acquisition updates the existing report source row, route history, and operational memory.

- **Title:** Create durable publish jobs and a transactional outbox [Impact: 5/5, Effort: 5/5]
  - Problem fixed: A read-only publish snapshot cannot manage durable autonomous publication and retries.
  - Why implement: Publish intents and WordPress side effects need transactional durability, idempotency, retry, and dead-letter handling.
  - Tradeoffs / risks: If the current snapshot remains read-only, it must be renamed rather than treated as a queue.
  - Acceptance Criteria:
    - `publish_jobs` stores publish intents and lifecycle state.
    - `publish_outbox` atomically records WordPress side-effect intents.
    - Jobs can be retried, dead-lettered, and idempotently delivered without corrupting publish state on partial WordPress failure.

- **Title:** Expand idempotency metadata to every external side effect [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Autonomous reruns are unsafe if any ambiguous write can duplicate external side effects.
  - Why implement: Idempotency is the foundation for safe retry, resume, and publish automation.
  - Tradeoffs / risks: Side-effect registry must not create pass-through abstractions or duplicate service boundaries.
  - Acceptance Criteria:
    - Side-effect registry maps OpenAI/vector writes, Drive uploads, WordPress media/posts, report-store mutations, state transitions, cost ledger writes, archive writes, route playbook promotion, and browser identity updates to owner, scope, logical key, checksum inputs, and artifact refs.
    - CI fails new unwaived side effects without idempotency metadata.
    - Tests prove duplicate suppression and checksum mismatch behavior.

- **Title:** Add real-time spend guardrails and budget-aware model routing [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Autonomous execution needs pre-call cost/time/token controls, not only post-run reporting.
  - Why implement: Safe unattended operation requires bounded spend decisions and deterministic compaction.
  - Tradeoffs / risks: Budget decisions must be explicit outcomes rather than silent quality reductions.
  - Acceptance Criteria:
    - `RunBudget` covers run/day/publisher scopes for USD, model calls, tokens, wall time, retries, browser launches, Drive writes, WordPress writes, and PDFs per batch.
    - Expensive actions check budget before execution and produce warn, pause, defer, stop, or override outcomes.
    - Model routing policy maps task family to model tier, max input budget, fallback tier, quality threshold, and deterministic compaction strategy.

- **Title:** Add provider failover behind the single LLM contract [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Provider failure can block autonomous runs when a policy-approved fallback could succeed.
  - Why implement: Resilience belongs behind the canonical LLM boundary with orchestrator-visible decisions.
  - Tradeoffs / risks: Failover must be bounded, policy-driven, normalized, and not visible as provider-specific payloads to generators.
  - Acceptance Criteria:
    - Provider-specific responses normalize into the stable typed LLM response contract.
    - Failover is bounded, logged, retry-policy aware, and orchestrator-visible.
    - Tests cover primary success, fallback success, fallback exhaustion, provider mismatch validation, and non-retryable contract failures.

- **Title:** Add deterministic autonomous context compaction [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Oversized contexts can exceed token/cost budgets without a reproducible reduction strategy.
  - Why implement: Compaction should preserve required metrics, quotes, claims, citations, and validation anchors.
  - Tradeoffs / risks: Compaction must be deterministic and quality-tested on fixed corpora.
  - Acceptance Criteria:
    - Compaction is triggered before model calls when token or cost budgets are exceeded.
    - Regression tests compare evidence retention on fixed prompt/output corpora.
    - Run ledger records avoided tokens and estimated avoided cost.

- **Title:** Promote health scorecards and public-site trust checks into autonomous gates [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Scorecards and smoke checks exist but should directly drive publish, repair, retry, hold, and notification decisions.
  - Why implement: Autonomous publishing must not ship broken or low-trust public pages.
  - Tradeoffs / risks: Thresholds must be calibrated to catch real failures without causing noisy holds.
  - Acceptance Criteria:
    - Every autonomous workflow writes a health scorecard consumed before publish or retry.
    - Public-site trust checks cover HTTPS, canonical sitemap URLs, 404/500 behavior, no path/PHP leakage, representative pages, metadata/social tags, request count, and page weight.
    - Failed checks withhold, roll back, or route pages to remediation with retained screenshots/evidence.

- **Title:** Use operational memory before browser launch [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Acquisition can spend browser/model work before checking remembered route evidence.
  - Why implement: Route memory should avoid expensive browser launches when recent reliable evidence exists.
  - Tradeoffs / risks: Stale or conflicting evidence must fail closed.
  - Acceptance Criteria:
    - Planner checks publisher/domain route history, HTTP probes, mailbox evidence, and route TTL before browser use.
    - Decisions log before/after recommendation, confidence, TTL status, and avoided browser/model-call estimates.
    - Successful mailbox outcomes promote into route memory and stale/conflicting evidence blocks reuse.

- **Title:** Add production-like autonomous smoke suites [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Autonomous behavior needs end-to-end confidence without live APIs in default CI.
  - Why implement: Safe autopilot requires tests over real SQLite state, checkpoints, idempotency, supervisor, and scorecards.
  - Tradeoffs / risks: Fakes must be external-boundary fakes, not monkeypatches of core logic.
  - Acceptance Criteria:
    - Non-live smoke suite uses fixture PDFs, fake Drive, fake LLM responses, fake WordPress, real SQLite, real checkpoints, real idempotency, real supervisor, and real health scorecards.
    - Tests cover fresh run, crash resume, duplicate suppression, validation repair, and publish hold/draft/publish policy.
    - Forbidden patching rules are respected.

- **Title:** Generate capability maps and autonomous release/remediation summaries [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Future agents need deterministic ownership and run outcome summaries without log archaeology.
  - Why implement: Capability maps and summaries reduce operational confusion and make autonomous runs reviewable.
  - Tradeoffs / risks: Generated docs must come from code/config and should fail stale, not become manually edited drift.
  - Acceptance Criteria:
    - `docs/generated/capability_map.md` covers external system to service boundary, workflow to orchestrator/generator/service/contracts, artifact to prompt/schema/generator/validator, state table to owner, side effect to idempotency scope, and failure code to runbook/remediation.
    - Autonomous summaries include what ran, changed, skipped, failed, auto-fixed, deferred, required credentials, published, and held from publish.
    - CI fails stale generated maps or missing required ownership metadata.

---

## 7. Code Hygiene and Executable Enforcement

- **Title:** Create one root `pyproject.toml` as canonical tool manifest [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Tool configuration is split across requirements files, pytest config, mypy config, CI scripts, and custom quality scripts.
  - Why implement: One project manifest reduces hidden defaults and agent confusion.
  - Tradeoffs / risks: Migration must preserve existing formatter, type, test, and quality behavior.
  - Acceptance Criteria:
    - Root manifest owns formatter, linter, type-checker, pytest, coverage, packaging metadata, and tool settings.
    - Existing commands continue to work or documented replacements are added.
    - CI/local verification proves no behavior drift from config migration.

- **Title:** Replace loose dependency ranges with a locked dependency graph [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Mixed pinned/ranged dependencies make local and CI installs nondeterministic over time.
  - Why implement: Reproducible installs reduce regression risk and improve security patch review.
  - Tradeoffs / risks: Lock tooling must fit the repo's deployment model and not break WordPress/Python workflows.
  - Acceptance Criteria:
    - Runtime and dev dependency groups are lockable through `uv.lock`, `pip-tools`, Poetry, or an approved equivalent.
    - CI installs from the lockfile.
    - README documents lock refresh and security update review flow.

- **Title:** Add root pre-commit hooks [Impact: 4/5, Effort: 2/5]
  - Problem fixed: Pre-commit exists only in vendored/browser-use context, not as a root project standard.
  - Why implement: Most simple hygiene defects should be blocked before CI.
  - Tradeoffs / risks: Hooks must be fast enough for daily use and align with CI.
  - Acceptance Criteria:
    - Root hooks cover Ruff format, Ruff lint, mypy changed files or scoped typing, secret scanning, YAML/JSON validation, no-large-files, and line-ending normalization.
    - Hook commands share the same configuration as CI/local gates.
    - README documents setup and bypass policy for rare cases.

- **Title:** Create one declarative quality-gate source for local and CI [Impact: 5/5, Effort: 4/5]
  - Problem fixed: `run_quality_gate.py` and GitHub Actions can drift because gates are separately hard-coded.
  - Why implement: One gate manifest makes local and CI behavior converge.
  - Tradeoffs / risks: Gate generation must preserve ordering, environment assumptions, and artifact retention.
  - Acceptance Criteria:
    - `quality_gates.yaml` or equivalent declares gate order, commands, required artifacts, live/non-live status, and waiver rules.
    - Local quality command and CI consume the same source.
    - Tests fail if generated/local/CI gate definitions drift.

- **Title:** Promote structural/refactor checks into always-on CI [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Some boundary and movement checks run only in refactor audit paths.
  - Why implement: Role/I/O drift and service-boundary drift should be blocked on every PR.
  - Tradeoffs / risks: Existing waivers must be explicit, justified, and expiring.
  - Acceptance Criteria:
    - Main CI runs role I/O boundary checks, service boundary map checks, applicable movement evidence checks, and long-file inventory checks.
    - Violations include actionable module/role information.
    - Existing exceptions are allowlisted with owner, reason, and expiry.

- **Title:** Expire, burn down, and tighten the mypy baseline [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Type debt can be normalized through stale baseline entries and broad skipped imports.
  - Why implement: Contracts, services, generators, orchestrators, UI, and CLI should become progressively enforceable.
  - Tradeoffs / risks: Strictness must be staged to avoid a noisy broad rewrite.
  - Acceptance Criteria:
    - Expired mypy baseline entries are removed or re-owned with valid reason and expiry.
    - Strictness tiers are defined for contracts, services, generators, orchestrators, UI, and CLI.
    - New type errors fail immediately in critical packages.

- **Title:** Add Ruff linting beyond formatting [Impact: 4/5, Effort: 2/5]
  - Problem fixed: Formatting alone does not catch unused imports, broad exceptions, complexity, shadowing, dead code, implicit Optional, or ambiguous names.
  - Why implement: Linting reduces hidden cleanup defects and improves module hygiene.
  - Tradeoffs / risks: Initial rollout may need scoped rule enables and documented waivers.
  - Acceptance Criteria:
    - `ruff check` runs locally and in CI.
    - Rules cover unused imports, import sorting, broad exceptions, complexity, shadowing, dead code, implicit Optional, and critical-path naming where configured.
    - Any initial baseline has owner, reason, and expiry.

- **Title:** Expand repository hygiene scanning [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Repo entropy can grow through duplicate files, orphan scripts, stale docs, root clutter, unused fixtures, vendored drift, and expired allowlists.
  - Why implement: Future agents need a cleaner workspace and higher-signal quality gates.
  - Tradeoffs / risks: The scanner must avoid false positives on intentional artifacts, caches, and retained evidence.
  - Acceptance Criteria:
    - Hygiene scanner detects duplicate files, orphan scripts, stale docs, root clutter, unused fixtures, vendored drift, and expired allowlists.
    - Allowlist entries include owner, reason, and expiry.
    - CI or release evidence reports hygiene deltas.

- **Title:** Expand service-boundary mapping across all external systems [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Boundary mapping focused on selected systems can miss unofficial entrypoints elsewhere.
  - Why implement: One external system should have one canonical service boundary/namespace.
  - Tradeoffs / risks: Some internal capabilities may need semantic demotion without public import breakage.
  - Acceptance Criteria:
    - Service map covers OpenAI/LLM providers, Google Drive, WordPress, filesystem, SQLite, browser/runtime acquisition, PDF/OCR stack, email/IMAP, HTTP/network, and vector store.
    - CI fails second unofficial service entrypoints without architecture review.
    - README or generated docs show canonical external-system ownership.

- **Title:** Extend role/I/O boundary scanning across runtime layers [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Generators, orchestrators, CLI, UI, and utilities can drift into direct I/O or private internals.
  - Why implement: Architecture rules become enforceable only when all runtime surfaces are scanned.
  - Tradeoffs / risks: Service-owned file/config/env access must be distinguished from legitimate CLI argument parsing.
  - Acceptance Criteria:
    - Scanning covers `src/generators`, `src/utils`, `src/orchestrators`, `src/_cli`, and `src/ui`.
    - Generators do not read files directly; orchestrators do not perform external I/O directly except through service contracts; UI uses orchestrator/service boundaries; environment access is service/config-owned.
    - Tests cover allowed and forbidden examples.

- **Title:** Semantically decompose `publish_orchestrator.py` while preserving its facade [Impact: 5/5, Effort: 5/5]
  - Problem fixed: Publish orchestration remains a broad side-effect-heavy workflow surface.
  - Why implement: Cleaner semantic owners reduce public-site regression risk and improve test isolation.
  - Tradeoffs / risks: This must be movement-only unless behavior changes are explicitly approved.
  - Acceptance Criteria:
    - `publish_orchestrator.py` remains the canonical public boundary.
    - Private semantic owners cover publish package validation, cross-report publish workflow, WordPress term resolution, publish-state transitions, idempotency, and preflight/readiness assembly where justified.
    - Public imports, patch points, route ordering, retry behavior, idempotency, logs, and WordPress side effects are preserved with movement evidence and focused tests.

- **Title:** Semantically decompose `ingest_orchestrator.py` while preserving `run_ingest` [Impact: 5/5, Effort: 5/5]
  - Problem fixed: Ingest orchestration owns batch filtering, locking, cursor management, worker coordination, retry routing, Drive materialization, and finalization.
  - Why implement: Smaller semantic control-plane owners reduce concurrency and rerun defects.
  - Tradeoffs / risks: Do not move domain generation into orchestrator helpers or external I/O into new orchestrator helpers.
  - Acceptance Criteria:
    - `run_ingest` remains the canonical public entrypoint.
    - Extracted private owners have semantic responsibility such as lock lifecycle, DB preflight, Drive materialization routing, state prefiltering, worker execution, cursor policy, or finalization.
    - Movement audit proves retry counts, cursor behavior, ordering, logs, and side effects are unchanged.

- **Title:** Split `tests/test_publish_generator.py` by observable behavior [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Large mixed test files are hard to review and can encourage internal patching.
  - Why implement: Behavior-focused test modules improve mutation targeting and reduce over-mocking risk.
  - Tradeoffs / risks: Test movement must preserve assertions and avoid weakening coverage.
  - Acceptance Criteria:
    - Tests are split by observable behavior such as request contract construction, WordPress payload adaptation, HTML snapshots, taxonomy/tag resolution, error taxonomy, idempotency, and side effects.
    - Public pytest entrypoints remain compatible if required.
    - Coverage and mutation results do not regress.

- **Title:** Raise coverage and mutation gates by criticality [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Conservative thresholds and manually capped mutation targets can miss critical regressions.
  - Why implement: Critical control flow and generators should be harder to fake or regress.
  - Tradeoffs / risks: Threshold increases should follow baseline cleanup and test concentration reduction.
  - Acceptance Criteria:
    - Coverage targets are staged toward contracts 95%, generators 85%, orchestrators 80%, services 75%, control-plane 90%+, and explicit UI/theme coverage where browser smoke tests apply.
    - Mutation targets are generated from changed critical files plus a core always-on set.
    - Changed critical files require meaningful mutation coverage or explicit waiver.

- **Title:** Add import-graph ownership reports and facade-thickness limits [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Coupling drift and over-thick facades can hide behind compatibility layers.
  - Why implement: Boundary and indirection health should be visible before it becomes structural debt.
  - Tradeoffs / risks: Facade limits must preserve legitimate compatibility facades and semantic public boundaries.
  - Acceptance Criteria:
    - PR artifacts report fan-in, fan-out, private module leakage, cross-context imports, avoided/detected cycles, and new dependency edges.
    - Facade gates enforce max facade-owned logic, max private imports unless justified, no forwarding-only wrapper chains beyond one compatibility layer, and module docstrings explaining semantic ownership.
    - Violations require explicit waiver or refactor.

- **Title:** Convert architectural rules into machine-readable policy [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Prose rules can drift from CI scripts and future agents may not know which checks implement which rule.
  - Why implement: Executable policy makes architecture rules enforceable and auditable.
  - Tradeoffs / risks: Policy must not duplicate logic inconsistently across scripts.
  - Acceptance Criteria:
    - `architecture_policy.yaml` or equivalent encodes allowed imports by role, allowed I/O by role, external-system ownership, forbidden placeholders, prompt-text ownership, test patching rules, architecture review triggers, and decomposition evidence requirements.
    - CI scripts consume the policy.
    - Tests verify representative policy allow/deny cases.

- **Title:** Create code hygiene scorecards for PRs and releases [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Hygiene trends are hard to review without a single artifact.
  - Why implement: Scorecards turn type debt, coverage, mutation, boundary violations, allowlist expiry, and dependency drift into visible release evidence.
  - Tradeoffs / risks: Scorecards should report deltas clearly and avoid becoming noisy dashboards.
  - Acceptance Criteria:
    - `code_hygiene_scorecard.json` and `code_hygiene_scorecard.md` include type debt count, expired baseline count, package coverage, mutation score by target, long-file inventory, import cycles, boundary violations, allowlist expiry, dependency drift, dead-code findings, facade warnings, and root clutter.
    - PR/release evidence includes scorecards.
    - Configured regressions fail gates or require explicit waiver with owner and expiry.

## Source Coverage Map

The scoped backlog above intentionally merges overlapping Notion work. The following source items were covered:

- Prompt guide: editorial constitution; prompt partials; schema snippets from contracts; claim ledger; evidence grades; canonical evidence IDs; abstention; scored insight rubric; so-what/now-what; report-type lens; topics covered; key figures; editorial visual ranking; chart insight cards; LinkedIn persona variants; banned-pattern corpus; safe comparative positioning; critique-first regeneration; severity-aware validation; golden-output evaluations.
- User-facing guide: decision brief; metric spine; strategic insight coverage roles; editorial contract versioning; metadata leakage; premium report-card copy; exhibit titles; evidence exhibit deck; readable evidence spans; source-quality panel; observation/so-what/now-what rendering; source-backed recommendations; risk register; methodology trust panel; Signals navigation; related Briefings and Reports; archive/search intelligence facets; mobile responsive polish; real CTA workflows; public-site performance gates.
- Crop guide: post-render crop QA; crop quality score; edge-intersecting text repair/rejection; final crop-image multimodal QA; content-aware trim; adaptive padding; higher-resolution final crops; higher crop-refine DPI; table outer-rule detection; chart axis/legend detection; visual card boundary detection; neighbor contamination detection; remove legacy user-facing fallback; publication-strict mode; iterative repair loop; diagnostics sidecars; visual crop metrics; manual golden crop set; publisher/style profiles; HTML visual smoke tests.
- Speed guide: fast-ingest profile; latest-safe ingest resume; lazy LLM clients; DAG scheduler; fast-first vector polling; parallel table/chart ranking; deterministic ranking skip; adaptive rank limits; one-pass fast crop refine; crop-refine LLM skip for high-confidence candidates; centralized page-render cache; native text reuse; worker-safe PDF context pool; adaptive concurrency; Drive/cache prefetch queue; cursor-first Drive listing; full batch skip metadata; md5 vector-store reuse; two-tier validation; draft-first HTML publishing.
- Browser-use guide: private-API auto-promotion; lower trusted-publisher promotion thresholds; deterministic route-playbook executor; artifact-level cache; aggressive publisher route policy; HTTP-only static DOM scan; narrowed browser preflight; preflight browser/page reuse on escalation; route-specific max steps and timeouts; terminal-evidence early stop; route-family prompt namespaces; minimized playbook prompt payload; deterministic form autofill; same-publisher session reuse; warm worker pool; route-specific worker timeout buffers; lightweight success evidence; metadata-only expected-blocker forensics; optimized inventory scrolling; event/fingerprint waits and fixed settle calls.
- Autonomy guide: supervisor; PipelinePlan; workflow-control execution authority; autonomous dead letters; scheduler; mailbox worker; publish jobs/outbox; side-effect idempotency registry; real-time spend guardrails; budget-aware model routing; provider failover; context compaction; health scorecard gates; public-site trust checks; metadata/extraction leakage at publish time; no WordPress runtime intelligence synthesis; route memory before browser launch; autonomous smoke tests; capability maps; release/remediation summaries.
- Hygiene guide: root pyproject; lockfile; pre-commit; shared quality-gate definition; structural checks in main CI; mypy baseline burn-down; stricter mypy tiers; Ruff linting; repository hygiene scanning; full service-boundary map; full role/I/O scanning; publish orchestrator decomposition; ingest orchestrator decomposition; publish-generator test split; higher coverage thresholds; broader mutation testing; import-graph ownership reports; facade-thickness limits; machine-readable architecture policy; hygiene scorecards.

## Near-Term Implementation Queue

1. Metadata leakage gate, editorial constitution, claim ledger, and canonical evidence IDs.
2. Metric spine, readable evidence spans, premium card/exhibit copy, and decision brief.
3. Post-render crop QA, crop diagnostics sidecars, crop quality score, and `publication_strict` mode.
4. `fast_ingest`, latest-safe ingest resume, deferred grounding validation, and deterministic ranking/crop shortcuts.
5. Browser private-API/playbook promotion, artifact-level acquisition cache, HTTP-only static DOM scan, and route-specific agent budgets.
6. Autonomous supervisor, PipelinePlan, scheduler, and durable dead letters.
7. Root tool manifest, lockfile, shared quality-gate manifest, mypy baseline cleanup, and boundary enforcement.
