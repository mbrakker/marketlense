# x100 Output Quality Tasks

Last audited: 2026-07-10

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
- The 2026-07-10 root audit says the x100 program is substantially partially implemented; remaining gaps are public rendering of new intelligence payloads, pipeline autopilot, durable publish jobs/outbox, online run-budget enforcement, and hosted-site/product polish.
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

- **Title:** Add retained-artifact strategic insight and editorial quality benchmarks [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Strategic insight fields are generated, but retained real artifacts do not yet benchmark role diversity, duplicated insight overlap, `so_what`/`now_what` quality, metric calibration, evidence linkage, caveats, and generic phrasing.
  - Why implement: The system needs output-quality regression evidence over real generated artifacts, not only prompt renderability and schema validity.
  - Tradeoffs / risks: Benchmarks must avoid brittle text snapshots and use semantic, contract-grounded assertions.
  - Acceptance Criteria:
    - A retained-artifact benchmark reports insight diversity, coverage-role balance, duplicate-overlap warnings, evidence-link completeness, metric support, caveat quality, and banned/generic phrasing.
    - The benchmark emits JSON/Markdown evidence suitable for release review.
    - Failures include artifact ID, field path, rule ID, and suggested remediation.

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
    - Figure assets include human-readable exhibit title, why-this-matters, source context, public confidence, ranking rationale, metric callouts, linked claims, and proof statements when available.
    - Tests reject raw extraction prefixes, OCR fragments, `F1`, `Additional figure`, duplicate boilerplate, placeholders, generic figure labels, and internal-looking identifiers.

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

- **Title:** Stop WordPress runtime synthesis of intelligence claims [Impact: 5/5, Effort: 4/5]
  - Problem fixed: WordPress runtime code can still derive weekly signals, strategic themes, freshness-style movement, and publisher authority from post counts, taxonomy counts, and dates.
  - Why implement: Analytical claims must come from approved Python projections and artifacts so they remain reproducible and evidence-governed.
  - Tradeoffs / risks: Missing projections need neutral UI/admin diagnostics so public pages do not look broken or fabricate intelligence.
  - Acceptance Criteria:
    - Homepage, signal, briefing, archive, and publisher intelligence modules read approved projection data only.
    - Runtime post/taxonomy counts may support navigation counts but not strategic or authority claims.
    - Tests prove missing projections fail closed and no intelligence claim is generated solely from WordPress runtime queries.

- **Title:** Add deterministic related Reports and Briefings blocks [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Public report pages do not yet have complete deterministic related-Briefings and related-Reports blocks as defined in the user-facing guide.
  - Why implement: Related-content modules turn isolated reports into a research portal and use the entity model already present for Reports, Signals, Briefings, Topics, Publishers, and Figures.
  - Tradeoffs / risks: Relationships must come from approved projections and validated artifacts, not runtime WordPress inference.
  - Acceptance Criteria:
    - Report pages render related Reports and Briefings when approved relationships are recoverable.
    - Relationship payloads include rationale/source metadata safe for public display.
    - Missing relationships render no filler and no synthetic recommendation.

- **Title:** Harden archive/search facets, mobile workflows, CTAs, and public performance [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Search, archive, intake, and mobile/performance issues can make the public product feel unfinished even when report content is strong.
  - Why implement: Discovery and intake workflows are part of output quality.
  - Tradeoffs / risks: Frontend changes need screenshot coverage and must preserve canonical URLs/social metadata.
  - Acceptance Criteria:
    - Archives support validated facets such as report type, key-figure availability, visual evidence count, source-quality band, methodology availability, validation status, and signal support.
    - Briefing, correction, and report/source submission CTAs resolve to real intake flows with validation and confirmation states.
    - Mobile/tablet/desktop smoke screenshots cover homepage, search, archive, report detail, contact, and submit pages with no overflow or clipped controls.
    - Performance gates track response start, DOM complete, request count, page weight, canonical URLs, Open Graph, and Twitter metadata.

- **Title:** Harden hosted public-site trust surface [Impact: 5/5, Effort: 3/5]
  - Problem fixed: The root audit still lists HTTPS, sitemap canonicalization, safe 404/500 behavior, stack-trace/path leakage, branded failure pages, hosted latency, and legacy polluted content verification as open product-trust gaps.
  - Why implement: Public trust fails if generated content is strong but the hosted site exposes infrastructure errors, unsafe failure pages, or stale polluted projections.
  - Tradeoffs / risks: Hosted fixes must preserve canonical URLs, metadata, and deployment rollback safety.
  - Acceptance Criteria:
    - Hosted smoke checks cover HTTPS, canonical sitemap URLs, branded 404/500 pages, no PHP/server path leakage, representative public pages, metadata/social tags, request count, page weight, response-start, and DOM-complete targets.
    - Legacy polluted publisher/card/exhibit records have a re-projection or verification path.
    - Failures withhold publish or produce explicit remediation evidence.

---

## 2. Visual Evidence and Crop Acceptance Quality

- **Title:** Add bounded multimodal final-crop QA escalation outside the PDF service [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Low-confidence `.qa.json` sidecars are not escalated to a canonical multimodal boundary for accept/repair/reject decisions.
  - Why implement: Deterministic QA should handle clear cases, while ambiguous final crops can be checked by a bounded model-backed generator/orchestrator path without putting model calls inside the PDF service.
  - Tradeoffs / risks: Escalation must be optional by profile, budgeted, logged, and routed through services/generators/orchestrators according to role boundaries.
  - Acceptance Criteria:
    - Low-confidence or borderline strict-crop sidecars can trigger bounded multimodal QA through the canonical model service boundary.
    - The model returns accept, repair, or reject with defect labels and evidence-backed rationale.
    - Orchestrator policy controls budget, retry, and fallback behavior; PDF service remains free of model calls.

- **Title:** Expand crop benchmarks from candidate signatures to rendered visual metrics [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Existing crop/candidate benchmarks can pass while rendered public crop quality regresses.
  - Why implement: The crop-quality standard is the final PNG and HTML presentation, not only candidate count, bbox signature, or runtime.
  - Tradeoffs / risks: Golden fixtures must be curated and stable enough for CI/release evidence without overfitting one rendering algorithm.
  - Acceptance Criteria:
    - A curated golden crop corpus covers difficult real reports, dense tables, dark slides, colored cards, multi-panel pages, small footnotes, and nearby decorative images.
    - Benchmarks report golden bbox IoU, perceptual image diff, whitespace percentage, clipped text count, contamination count, OCR completeness ratio, and minimum readable text height.
    - Release evidence includes benchmark deltas and retained HTML visual smoke screenshots for representative reports.

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

- **Title:** Add safe comparative positioning for cross-report synthesis [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Multi-report output needs useful comparison without unsafe metric normalization.
  - Why implement: Cross-report synthesis can compare themes, assumptions, evidence direction, methodology, and audience implications while preserving data integrity.
  - Tradeoffs / risks: Raw metric magnitudes must not be compared across publishers unless normalized by source evidence and explicitly allowed.
  - Acceptance Criteria:
    - Cross-report prompts allow comparisons on themes, assumptions, evidence direction, publisher focus, methodology differences, audience implications, and convergent/divergent claims.
    - Validators reject unsupported cross-publisher metric normalization.
    - Fixture tests cover convergence, divergence, and limitation language.

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

- **Title:** Add deterministic ranking and crop-refine shortcuts [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Strong candidates can still incur ranking and crop-refine model calls.
  - Why implement: Obvious-pass/obvious-reject paths reduce latency and cost while preserving full mode.
  - Tradeoffs / risks: Shortcuts must not silently degrade visual or editorial quality.
  - Acceptance Criteria:
    - Ranking LLM is bypassed when deterministic scoring yields enough strong table/chart candidates.
    - `rank_max_candidates` is adaptive by profile and escalates only when no acceptable figures are found.
    - Fast mode uses one-pass crop refinement or deterministic bbox expansion, and high-confidence candidates can skip crop-refine LLM.

- **Title:** Convert Drive prefetch from stage barrier to streaming queue [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Drive cache-prefetch exists but completes the full selected batch before report processing starts.
  - Why implement: A bounded producer/consumer queue lets report generation begin on ready PDFs while later files continue downloading and hashing.
  - Tradeoffs / risks: Queueing must preserve idempotency, backpressure, Drive/PDF/LLM concurrency limits, and retry/defer semantics.
  - Acceptance Criteria:
    - Prefetch producer lists, downloads, validates, hashes, and emits ready-file records into a bounded queue.
    - Report-generation consumers process ready files under separate I/O, PDF, and LLM concurrency caps.
    - Tests cover duplicate suppression, failed download defer, queue backpressure, and stable finalization.

- **Title:** Reuse initial native text and add worker-safe PDF context pooling [Impact: 3/5, Effort: 3/5]
  - Problem fixed: Parallel source preparation can submit `_load_text` again, and within-file parallelism disables shared PDF context rather than using safe per-worker contexts.
  - Why implement: Reusing text and managed PDF contexts reduces local CPU/I/O without changing output semantics.
  - Tradeoffs / risks: PyMuPDF handles must not be shared unsafely across threads, and OCR-changed PDFs must invalidate reused text.
  - Acceptance Criteria:
    - Source prep reuses the initial native text response/status when the analysis PDF is unchanged.
    - Per-worker PDF contexts or a bounded context pool provide deterministic cleanup and no cross-thread unsafe handle sharing.
    - Tests cover OCR invalidation, parallel source prep, and context cleanup on failure.

- **Title:** Apply adaptive concurrency decisions to live worker limits [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Workflow-control can resolve adaptive concurrency, but selected limits are not yet applied to ingest, report, evidence, artifact, or browser worker windows.
  - Why implement: Adaptive concurrency only improves throughput and stability when runtime worker pools consume its decisions.
  - Tradeoffs / risks: Limit changes should occur at safe batch/window boundaries and preserve provider/API caps.
  - Acceptance Criteria:
    - Batch boundaries feed observations into adaptive concurrency resolution.
    - Selected limits are applied to the next bounded execution window for relevant resource classes.
    - Logs show prior limit, selected limit, reason, observed pressure, and safety caps.

- **Title:** Unify rendered-page acquisition behind one PDF render cache boundary [Impact: 4/5, Effort: 4/5]
  - Problem fixed: PDF parsing caches and rendered-artifact caches remain split, and there is no single rendered-page service used by every PDF stage.
  - Why implement: A canonical render cache reduces duplicate rendering and makes cache invalidation/versioning easier to reason about.
  - Tradeoffs / risks: Existing fingerprint sidecars and page-artifact caches must be preserved or migrated without changing outputs.
  - Acceptance Criteria:
    - Rendered page acquisition is served by one service boundary keyed by PDF md5, page, DPI, render variant, parser/settings fingerprints, and artifact version.
    - Candidate extraction, previews, crop-refine pages, and final crop rendering use the same boundary where compatible.
    - Equivalence tests prove rendered outputs and cache invalidation remain correct.

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

- **Title:** Add a deterministic executor for normal route playbooks [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Normal route playbooks are selected and sent to prompts, but only private-API evidence has deterministic replay.
  - Why implement: Known open/click/fill/select/submit/verify steps should run before invoking the LLM for recurring browser routes.
  - Tradeoffs / risks: Drift must fall back to browser-use with evidence rather than silently failing or corrupting route memory.
  - Acceptance Criteria:
    - Playbook executor supports deterministic DOM actions with CSS/text/role selectors and confidence scoring.
    - Executor runs before browser-use for eligible playbooks and records avoided LLM/browser steps.
    - Drift evidence is persisted for playbook repair and fallback uses the normal acquisition path.

- **Title:** Add trusted-publisher private-API promotion overrides [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Global private-API promotion thresholds remain conservative even for stable publishers where fewer canary observations may be enough.
  - Why implement: Publisher-scoped thresholds shorten the learning loop while preserving global safety.
  - Tradeoffs / risks: Lower thresholds require stricter validation and must not become a broad default.
  - Acceptance Criteria:
    - Publisher-scoped threshold overrides can define lower success/source counts with owner, reason, and expiry.
    - Low-threshold promotion requires same-host, expected status, required markers, verified artifact, and fallback route preservation.
    - Promotion decisions log publisher override, validation evidence, and rollback path.

- **Title:** Add HTTP-only static DOM scan before browser preflight [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Bounded browser preflight still launches a browser for pages where static HTML/scripts/meta tags may reveal PDF candidates.
  - Why implement: Static extraction can find many report assets before any browser startup.
  - Tradeoffs / risks: Static candidates must be validated by MIME/type and file signature before acceptance.
  - Acceptance Criteria:
    - HTTP scan extracts PDF/document candidates from anchors, scripts, JSON, JSON-LD, meta tags, OpenGraph tags, canonical URLs, and embedded `.pdf` strings.
    - Candidates are validated by response status, MIME/type, file signature, and publisher/report scope.
    - Browser preflight runs only when static extraction is inconclusive.

- **Title:** Narrow browser preflight eligibility and reuse state on escalation [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Browser preflight still runs for low-yield route families and still stops its browser before full-agent escalation, causing double launch.
  - Why implement: Cheaper escalation reduces 10-24 second bounded-browser paths and repeated startup/navigation costs.
  - Tradeoffs / risks: Reused browser/page state must remain scoped, deterministic, and cleaned up reliably on failure.
  - Acceptance Criteria:
    - Preflight eligibility uses route family, publisher success history, static evidence, and listing/email-gate low-yield policies.
    - Escalation can reuse preflight browser/page, cookies, local storage, current URL, and downloaded-candidate context.
    - Tests cover preflight skip, escalation reuse, cleanup on failure, and no cross-publisher leakage.

- **Title:** Reduce browser prompt playbook payload [Impact: 4/5, Effort: 2/5]
  - Problem fixed: Prompt preparation can still serialize up to three playbooks with multiple step and trap lines.
  - Why implement: Sending only the winning playbook by default lowers token cost and reduces agent confusion.
  - Tradeoffs / risks: Alternative playbooks should still be available for low-confidence route selection.
  - Acceptance Criteria:
    - Route prompts include only the winning playbook by default.
    - Alternative playbooks are included only when selection confidence is low or drift evidence requires them.
    - Full playbook YAML remains outside the prompt and prompt hashes capture the compact payload.

- **Title:** Add live terminal watchers for browser-use early stop [Impact: 5/5, Effort: 3/5]
  - Problem fixed: Current terminal salvage handles some timeout/blocker cases but does not continuously watch downloads, network events, confirmation text, or blocker quorum during normal runs.
  - Why implement: Stopping as soon as terminal evidence appears avoids extra LLM/action steps after success or known failure.
  - Tradeoffs / risks: Watchers must avoid false positives and route terminal evidence through normal artifact finalization.
  - Acceptance Criteria:
    - Runtime watches download directory, network PDF/document URLs, email/request confirmations, form disappearance, terminal pages, and known blockers.
    - Terminal evidence signals agent stop and emits typed success/blocker outcomes.
    - Tests cover valid artifact, email confirmation, blocker quorum, terminal page, and non-terminal false-positive text.

- **Title:** Canary-enable same-publisher session reuse and warm workers for bounded batches [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Session reuse and warm worker pool infrastructure exist but remain opt-in or disabled by default.
  - Why implement: Warm batch execution avoids repeated profile, cookie-banner, subprocess, and browser startup costs.
  - Tradeoffs / risks: Rollout must prevent cross-publisher leakage and restart workers under run-count, idle, or memory limits.
  - Acceptance Criteria:
    - Safe same-publisher session reuse can be enabled for bounded batch acquisition profiles with TTL and host scope.
    - Warm worker pool can be canary-enabled for same-publisher batches with one-shot subprocess fallback.
    - Telemetry reports reuse outcomes, avoided startups, worker restarts, memory pressure, and failure fallback counts.

- **Title:** Add conditional browser evidence and blocker forensics policies [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Known successful routes and expected blockers can still capture heavy screenshots, HTML, assets, network resources, copied artifacts, and detailed logs.
  - Why implement: Verified repeat successes and remembered blockers should be cheap while novel failures still retain forensic detail.
  - Tradeoffs / risks: Sampling and drift detection must preserve enough evidence to debug regressions.
  - Acceptance Criteria:
    - Known verified successes store minimal evidence: artifact hash, artifact URL, route ID, validation status, final URL, and sampled audit flag.
    - Full evidence is retained for new publishers, new routes, failed runs, sampled audits, drift, parser errors, and suspected regressions.
    - Expected CAPTCHA, 403, static archive, business-email rejection, and remembered blockers default to metadata-only forensics with typed blocker codes.

- **Title:** Add route-specific worker timeout buffers [Impact: 3/5, Effort: 2/5]
  - Problem fixed: Route-specific agent budgets exist, but the one-shot worker still adds a fixed outer timeout buffer.
  - Why implement: Per-route worker buffers fail stuck runs faster and free capacity sooner.
  - Tradeoffs / risks: The outer envelope must still leave enough time for terminal salvage and artifact finalization.
  - Acceptance Criteria:
    - Worker timeout buffer is resolved by route family and terminal-salvage policy.
    - Known impossible routes fail fast with typed blocker outcomes.
    - Tests assert route-specific outer timeout calculation and salvage-before-timeout behavior.

- **Title:** Add browser acquisition avoided-spend benchmark [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Operational memory and cache features exist, but there is no read-only benchmark quantifying avoided browser launches, model calls, runtime, retries, and cost.
  - Why implement: Browser-use x100 progress should be measured by how often runs avoid full agent work.
  - Tradeoffs / risks: Benchmark must be read-only and must not mutate route memory, artifacts, or publisher state.
  - Acceptance Criteria:
    - Benchmark reports exact-route reuse, publisher-policy reuse, mailbox-promoted memory, artifact-cache hits, deterministic autofill, warm-worker reuse, avoided launches, avoided model calls, latency savings, and cost per acquired report.
    - Results are grouped by publisher, route family, and outcome.
    - JSON/Markdown evidence can be retained in release or quality review artifacts.

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

- **Title:** Expand due-work scheduling beyond mailbox delivery [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Mailbox delivery has durable due-request scheduling, but model limits, endpoint outages, credential blockers, validation repair, publishing, and other workflows lack a generic scheduler.
  - Why implement: Autonomy needs one deferred-work mechanism rather than one-off queues per workflow.
  - Tradeoffs / risks: Existing mailbox scheduling should be reused or adapted, not duplicated.
  - Acceptance Criteria:
    - Generic scheduled actions cover retryable, deferred, and user-action-required work outside mailbox delivery.
    - Scheduler can dispatch through existing orchestrators with attempt budgets and loop prevention.
    - Tests cover mailbox due work, credential blockers, validation repair, publish defer, and retryable endpoint failure.

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
    - Model routing policy maps task family and difficulty to model tier, max input budget, fallback tier, quality threshold, and deterministic compaction strategy.

- **Title:** Roll deterministic context compaction across eligible model-call families [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Context compaction exists for JSON prompt requests but is disabled by default and not consistently applied across evidence, artifact, validation, OCR/image, or vector-backed call families.
  - Why implement: Budget-aware autonomy needs deterministic prompt-size control before model calls, with retained anchors and reproducible logs.
  - Tradeoffs / risks: Compaction must preserve metrics, quotes, claims, citations, evidence, validation anchors, sources, figures, tables, and page references.
  - Acceptance Criteria:
    - Eligible model-call families declare compaction policy, max tokens/cost thresholds, preserved anchors, and fallback behavior.
    - Logs record compaction trigger, retained anchors, dropped sections, avoided tokens, and estimated avoided cost.
    - Regression tests compare evidence retention on fixed corpora.

- **Title:** Add provider failover behind the single LLM contract [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Provider failure can block autonomous runs when a policy-approved fallback could succeed.
  - Why implement: Resilience belongs behind the canonical LLM boundary with orchestrator-visible decisions.
  - Tradeoffs / risks: Failover must be bounded, policy-driven, normalized, and not visible as provider-specific payloads to generators.
  - Acceptance Criteria:
    - Provider-specific responses normalize into the stable typed LLM response contract.
    - Failover is bounded, logged, retry-policy aware, and orchestrator-visible.
    - Tests cover primary success, fallback success, fallback exhaustion, provider mismatch validation, and non-retryable contract failures.

- **Title:** Promote health scorecards and public-site trust checks into autonomous gates [Impact: 5/5, Effort: 4/5]
  - Problem fixed: Scorecards and smoke checks exist but should directly drive publish, repair, retry, hold, and notification decisions.
  - Why implement: Autonomous publishing must not ship broken or low-trust public pages.
  - Tradeoffs / risks: Thresholds must be calibrated to catch real failures without causing noisy holds.
  - Acceptance Criteria:
    - Every autonomous workflow writes a health scorecard consumed before publish or retry.
    - Public-site trust checks cover HTTPS, canonical sitemap URLs, 404/500 behavior, no path/PHP leakage, representative pages, metadata/social tags, request count, and page weight.
    - Failed checks withhold, roll back, or route pages to remediation with retained screenshots/evidence.

- **Title:** Expand autonomous happy-path smoke to full report lifecycle [Impact: 4/5, Effort: 4/5]
  - Problem fixed: The autonomous smoke suite currently covers mailbox acquisition, but not full report generation, crash resume, validation repair, health gating, or WordPress hold/draft/publish policy.
  - Why implement: A pipeline-wide supervisor needs non-live proof over the whole autonomous lifecycle before it can be trusted.
  - Tradeoffs / risks: Tests must fake only external boundaries and use real SQLite, checkpoints, idempotency, supervisor decisions, and scorecards.
  - Acceptance Criteria:
    - Smoke suite covers fresh run planning, fake Drive input, fake LLM responses, report generation, checkpoint crash/resume, validation repair, health gating, publish hold/draft/publish, mailbox due work, and duplicate suppression.
    - External systems are faked at service boundaries.
    - The suite emits retained scorecard and remediation-summary evidence.

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

- **Title:** Complete root tool manifest consolidation [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Root `pyproject.toml` now carries tool config, but `pytest.ini`, `mypy.ini`, explicit `mypy.ini` usage, and dependency metadata outside `[project]` still fragment the tool manifest.
  - Why implement: Tooling should have one source of truth so local runs, CI, and agents do not diverge on hidden defaults.
  - Tradeoffs / risks: Migration must preserve existing commands and avoid broad formatting or dependency churn.
  - Acceptance Criteria:
    - Remaining pytest, mypy, coverage, Ruff, and packaging/dependency configuration is either moved into `pyproject.toml` or explicitly documented as intentionally separate.
    - CI/local scripts stop hard-coding stale config-file paths where unnecessary.
    - Focused config tests or command checks prove behavior is unchanged.

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

- **Title:** Complete staged mypy strictness and full Ruff rollout [Impact: 4/5, Effort: 4/5]
  - Problem fixed: The mypy baseline is burned down, but active settings still allow broad missing imports, disabled return-any warnings, follow-imports skipping, and limited Ruff enforcement.
  - Why implement: Type and lint debt should stay burned down through staged strictness, not just a zero baseline snapshot.
  - Tradeoffs / risks: Strictness must be introduced by package tier to avoid noisy unrelated rewrites.
  - Acceptance Criteria:
    - Contracts, services, generators, orchestrators, UI, and CLI have staged mypy strictness targets with owner/expiry for remaining exceptions.
    - Ruff lint enforcement expands beyond changed-file `F` checks toward the policy rule set.
    - CI reports strictness progress and fails new unwaived violations in critical packages.

- **Title:** Expand repository entropy and long-file hygiene checks [Impact: 3/5, Effort: 3/5]
  - Problem fixed: Hygiene scanning has allowlist ownership/expiry, but duplicate-file, orphan-script, stale-doc, unused-fixture, root-clutter, vendored-drift, and full long-file inventory gates remain incomplete.
  - Why implement: Repo entropy raises the cost for future agents and hides genuine implementation risk.
  - Tradeoffs / risks: Checks need explicit allowlists for retained evidence, caches, fixtures, and vendored code.
  - Acceptance Criteria:
    - Hygiene checks report duplicate files, orphan scripts, stale docs, unused fixtures, root clutter, vendored drift, expired allowlists, and long-file inventory.
    - Findings include owner, path, reason, expiry/waiver status, and severity.
    - Main CI or release evidence includes the hygiene report with bounded noise.

- **Title:** Complete movement-only publish and ingest orchestrator decomposition [Impact: 5/5, Effort: 5/5]
  - Problem fixed: `publish_orchestrator.py` remains the principal publishing hotspot, and `ingest_orchestrator.py` still owns substantial state filtering, Drive materialization, worker coordination, cursor policy, and finalization behavior.
  - Why implement: These coordinators are high-risk control-plane surfaces that need semantic private owners without changing public behavior.
  - Tradeoffs / risks: This must be movement-only unless behavior changes are explicitly approved; retry behavior, ordering, idempotency, logs, and side effects must be preserved.
  - Acceptance Criteria:
    - `publish_orchestrator.py` remains the canonical public facade while semantic private owners absorb publish package validation, cross-report workflow, term resolution, state transitions, idempotency, and readiness assembly as appropriate.
    - `ingest_orchestrator.py` keeps `run_ingest` as the public entrypoint while remaining stable capabilities move into private owners.
    - Movement evidence and focused tests prove public imports, retry counts, cursor behavior, state transitions, logs, and external side effects are unchanged.

- **Title:** Add changed-critical-file mutation selection [Impact: 4/5, Effort: 3/5]
  - Problem fixed: Mutation thresholds are policy-backed, but target inventory and caps remain manually hard-coded and changed critical modules are not automatically required to have mutation coverage or waivers.
  - Why implement: Changed critical control-plane and generator code should be hard to fake by default.
  - Tradeoffs / risks: Mutation runtime must stay bounded with clear target selection and waiver rules.
  - Acceptance Criteria:
    - Changed critical files in generators, orchestrators, services, contracts, and control-plane packages are discovered automatically.
    - Each changed critical file has mutation coverage or an explicit owner/reason/expiry waiver.
    - CI reports selected targets, skipped targets, survivor counts, and waiver status.

- **Title:** Add import-graph ownership reports and facade-thickness limits [Impact: 4/5, Effort: 4/5]
  - Problem fixed: Coupling drift and over-thick facades can hide behind compatibility layers.
  - Why implement: Boundary and indirection health should be visible before it becomes structural debt.
  - Tradeoffs / risks: Facade limits must preserve legitimate compatibility facades and semantic public boundaries.
  - Acceptance Criteria:
    - PR artifacts report fan-in, fan-out, private module leakage, cross-context imports, avoided/detected cycles, and new dependency edges.
    - Facade gates enforce max facade-owned logic, max private imports unless justified, no forwarding-only wrapper chains beyond one compatibility layer, and module docstrings explaining semantic ownership.
    - Violations require explicit waiver or refactor.

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

1. Add retained-artifact quality benchmarks for insight diversity, role coverage, `so_what`/`now_what`, metric calibration, evidence linkage, generic phrasing, duplicated insights, and caveat quality.
2. Close public product trust gaps: remove WordPress runtime intelligence synthesis, fix hosted trust surface, add real intake flows, complete mobile/search polish, clean card/exhibit leakage, and reduce hosted latency.
3. Build the missing autonomous control loop: typed `PipelinePlan`, autopilot profiles, supervisor, generic scheduler, durable dead letters, and remediation re-entry through existing orchestrators.
4. Add durable publishing and online budget authority: publish jobs/outbox, `RunBudget` enforcement before costly side effects, and broader budget-aware model routing/context compaction rollout.
5. Package speed primitives into explicit execution modes: `fast_ingest`/`fast_cached`/`high_quality`, DAG scheduling, draft-first enrichment, adaptive prefetch, and live adaptive concurrency.
6. Finish crop-quality release evidence: low-confidence multimodal escalation, golden crops, final-crop QA scorecard ingestion, and retained HTML visual smoke evidence.
7. Close code-hygiene enforcement gaps: root pre-commit, one local/CI gate manifest, strict mypy/Ruff rollout, publish/ingest decomposition, changed-critical mutation targeting, import/facade reports, repo-entropy checks, and hygiene scorecards.
8. Measure browser acquisition savings: avoided browser launches/model calls from exact-route reuse, publisher-policy reuse, mailbox-promoted memory, artifact caching, deterministic autofill, static DOM scan, session reuse, and warm-worker execution.
