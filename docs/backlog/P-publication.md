# Editorial quality, visual presentation, publishing, and public UX

Canonical owner IDs: P2, P4, P5, P6, P7, P8, P10, P16, P17. This document contains **Active outcome specifications and their retained technical proposal slices**. Status belongs to [CONSOLIDATED_TODO.md](../../CONSOLIDATED_TODO.md), not to individual proposal sections. The complete source texts are preserved unchanged in the [historical backlog](archive/CONSOLIDATED_TODO-20261011-preconsolidation.md) and [historical proposal catalogue](archive/10improvements-20261011-preconsolidation.md).

Before implementing a slice, verify its historic diagnosis at current HEAD; use its **Luna implementation prompt** together with the full evidence and criteria immediately above it. Proposed thresholds are acceptance targets, not current results. Closed parent milestones are not reopened by a proposal's historical wording.

---
 
## P2. Harden bounded WordPress public-observability events

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** none; outcome specification stands alone.

- **Baseline:** Python logging has bounds/redaction. WordPress `Public_Render_Boundary::log_failure` still emits raw exception message/file/trace to standard logs and its hook, while `Intake::log` emits separate events. No shared PHP byte/redaction boundary exists. Current runtime tests protect visitor markup but require private-path diagnostics in events, so they must change with implementation rather than count as event-safety proof.
- **Target behaviour:** All WordPress public-boundary events use one small PHP-local contract that preserves correlation/outcome/route/entity metadata while deterministically excluding public submission text and bounding private diagnostics. Public responses never expose diagnostic content; R6 receives only bounded reduction metadata.
- **What to implement, in order:**
  1. Define the allowed WordPress public-event schema, maximum serialized size, permitted scalar fields, diagnostic/private-field policy, and deterministic reduction behavior.
  2. Implement one shared PHP helper/boundary for serialization, redaction, bounding, correlation IDs, and reduction metadata; do not introduce a second external logging store.
  3. Migrate standard error logs and existing action-hook payloads to the same bounded schema, including every rejected intake branch; preserve hook names/correlation/visitor response and bound route/entity metadata.
  4. Ensure exception message/path/trace data is either bounded in private-only diagnostics or reduced to safe typed metadata; never include user-submitted body/free text in standard events.
  5. Update runtime tests that currently require raw private diagnostics; cover large-route/exception/intake inputs, byte ceilings, deterministic reduction and forbidden-value absence in logs and hooks. R6 consumes only aggregate reduction metadata.
- **Acceptance criteria:**
  - Representative maximum-size intake and render events remain at/below the canonical WordPress event byte limit.
  - Correlation ID, route/entity type, outcome/error class and reduction indicator survive deterministic reduction.
  - User submission text, credentials, filesystem paths, stack traces, and discarded raw values are absent from public responses and bounded standard-event artifacts.
  - Existing WordPress action hooks and public safe-error/intake behavior remain compatible.
  - Tests prove deterministic output and that R6 can aggregate reduction metadata without reconstructing discarded content.

### Luna implementation prompt — P2

```text
Work on P2 — Harden bounded WordPress public-observability events at the current MarketLense HEAD.
Owner specification: docs/backlog/P-publication.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
---
 
## P4. Close public briefing, correction, and submission intake

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** none; outcome specification stands alone.

- **Baseline:** All three intake types share `Intake::fields_for`, nonce/honeypot/required/email/URL validation, safe redirects and private `ml_intake` WP-admin persistence. Delivery means private inbox persistence, not outbound email. Complete P2-compliant outcome events for every rejection/persistence branch, runtime duplicate/submission behavior and approved hosted proof for all CTA routes remain open.
- **Target behaviour:** Each public CTA captures only necessary documented fields, rejects invalid/spam input safely, persists an operator-usable private record, emits bounded/redacted observability, and returns a clear success/error state on the deployed site.
- **What to implement, in order:**
  1. Verify all CTA/template routing against existing Intake::fields_for and document operator/field ownership; change fields only for demonstrated mismatch.
  2. Route intake observability through P2's shared bounded WordPress event boundary without moving intelligence generation into WordPress.
  3. Verify private WP-admin access/persistence and define repeat-submit/refresh behavior: current valid inserts create records without a submission idempotency key. Do not call inbox persistence email delivery or add notifications without a product requirement.
  4. Add PHP runtime submission cases for each intake type and nonce/type, email, required, URL, honeypot, insert failure and success branches. Assert rejection writes nothing, redirects are safe, events omit free text and repeat behavior matches its contract; source-string tests alone are insufficient.
  5. Run a current hosted smoke through every CTA on the deployed sandbox/site and retain route, outcome, record/readback evidence without retaining submitted personal text. Retain tested deployment package SHA/hash, CTA/action, safe fixture identity and private record readback; a local harness or page GET is not hosted persistence proof.
- **Acceptance criteria:**
  - Every CTA reaches the correct form/action and collects only its documented necessary fields.
  - Empty/invalid/honeypot submissions create no actionable record and return safe deterministic feedback.
  - Valid submissions create exactly the expected private record/delivery outcome and show a clear confirmation state.
  - Events satisfy P2's byte/redaction contract and contain no submission body/free text.
  - Current hosted smoke proves all three routes and failure/success states; only then can P4 close.

### Luna implementation prompt — P4

```text
Work on P4 — Close public briefing, correction, and submission intake at the current MarketLense HEAD.
Owner specification: docs/backlog/P-publication.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
---
 
## P5. Validate and close responsive search and navigation

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** none; outcome specification stands alone.

- **Baseline:** Responsive navigation/search/filter markup exists; mobile navigation is native details/summary disclosure. `public_site_responsive_smoke.py` defaults to home/reports at three widths and checks overflow/non-lazy broken images. It does not prove all-route keyboard/search interactions, lazy-image readiness, clipping/overlap, screenshots or deployment identity. Extend existing tooling and fix demonstrated defects rather than rebuild navigation.
- **Target behaviour:** Navigation, search, filters, and primary discovery flows are visually stable and keyboard accessible at phone, tablet, and desktop widths on all key public surfaces without changing archive/search query semantics.
- **What to implement, in order:**
  1. Extend the existing responsive-smoke route/viewport matrix across home, native search, report/briefing/signal archives, report detail, publisher/topic/category, contact and submit; retain frozen data and tested deployment package identities.
  2. Run current screenshots and DOM accessibility checks to identify only real remaining defects: horizontal overflow, clipping, overlap, unreadable/truncated controls, awkward hero stacking, or stray artifacts. Retain screenshots/element and interaction assertions; scroll/load lazy images and cover 200% zoom/text spacing and reduced motion where applicable.
  3. Fix theme/plugin CSS/markup minimally, preserving query parameters, WordPress hooks, projection data, and desktop behavior.
  4. Verify native details/summary disclosure by keyboard/pointer, focus order/visibility, closed-link non-focusability, collapse and search/filter behavior. Specify Escape/outside-click only if required by the actual design; do not assume modal/backdrop semantics.
  5. Retain visual-smoke screenshots plus automated no-overflow/broken-image/accessibility assertions as regression evidence. A two-route overflow/non-lazy-image pass cannot close interaction/accessibility/whole-page requirements.
- **Acceptance criteria:**
  - No horizontal overflow, clipped text, overlap, hidden essential control, or visible broken image on the defined route/viewport matrix.
  - Mobile navigation opens/closes intentionally, remains keyboard operable, exposes visible focus, and returns focus appropriately; no off-canvas control remains keyboard-trapped when closed.
  - Search/filter submissions preserve current GET/query semantics and return the expected archive/search state.
  - Phone/tablet/desktop screenshots are retained and automated checks fail known overflow/clipping regressions.
  - No public content/projection contract changes are introduced solely for responsive styling.

### Luna implementation prompt — P5

```text
Work on P5 — Validate and close responsive search and navigation at the current MarketLense HEAD.
Owner specification: docs/backlog/P-publication.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
---
 
## P6. Complete blind human editorial acceptance

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** `ART-10`, `VER-06`.

- **Baseline:** Checksum-bound readiness and automated source-fidelity/editorial checks are implemented. `docs/quality/p6-editorial-acceptance.md` retains historical five-report score matrices for Batches 1 and 2, but Batch 2 explicitly lacks reviewer/date attribution, decision tables are incomplete, and later batches remain awaiting human review. Operational reruns cannot substitute for the exact scored artifacts. `docs/quality/public-editorial-human-evaluation.md` still prescribes a conflicting 30-report 1–5 protocol. Attributable 15-report acceptance, one reproducible rubric/weight aggregate, and availability/hash verification of linked `out/` review bundles remain open.
- **Target behaviour:** A fixed, representative, retained human-review program gives an explicit publishability decision and quantitative editorial scores for 15 reports, using one stable rubric and reviewer attribution. Automated gates remain necessary but are not used as a substitute for human quality judgment.
- **What to implement, in order:**
  1. Reconcile the conflicting human-review procedure with this P6 contract and lock one authoritative rubric version, numeric weights, normalization and aggregation rule without changing thresholds. Reuse the existing three five-report cohort memberships and verify exact source/scored-render hashes; supplemental batches cannot replace difficult members. Later rerenders require a new attributed review version.
  2. Lock one stable human scoring rubric across the cohorts: factual fidelity, evidence selection, analytical depth, insight specificity, commercial relevance, narrative structure, clarity, expert/human feel, and completeness; evaluate LinkedIn derivative copy separately. Keep chart/table scoring outside this item while the visual subproject is separate.
  3. Verify existing records and obtain missing reviewer identity/role/date, explicit publishability and reviewed artifact hashes from the reviewers; collect missing reviews. Keep unattributed scores incomplete and original/repair outcomes separate; never infer approval or relabel model judgments as human review.
  4. Aggregate weighted cohort and overall results deterministically; separate failures caused by source limitations from editorial-generation defects.
  5. Route repeatable defects to the owning existing backlog item/prompt family and rerun only through normal governed regeneration; do not manually edit scored outputs to manufacture a pass.
- **Acceptance criteria:**
  - All **15 reports** have completed human review records with reviewer attribution and explicit publishability decision.
  - Every accepted record has available hash-verified reviewed output, reviewer/date attribution and the same rubric/weight version. Missing evidence blocks closure; an appeal cannot waive material source-fidelity or readiness failures.
  - The retained rubric/weights are identical across all three cohorts and charts/tables remain explicitly excluded rather than silently scored.
  - Aggregate weighted median is at least **85/100**, and no factual-fidelity score is below **8/10** without an explicit retained appeal/outlier disposition that explains why the report remains acceptable.
  - No accepted report contains a material unsupported claim, reader-facing internal identifier, obvious AI scaffolding, or unhandled source limitation.
  - Evidence includes exact report/render hashes so the reviewed output is the same artifact considered for release.

### Luna implementation prompt — P6

```text
Work on P6 — Complete blind human editorial acceptance at the current MarketLense HEAD.
Owner specification: docs/backlog/P-publication.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
### Linked technical implementation slices

Technical IDs below are **subtasks or investigations**, not additional canonical Active outcomes. Status notes are historical catalogue/reconciliation claims and require current-HEAD verification.
 
<a id="art-10"></a>
#### ART-10 — Test generated-artifact delivery by content role, not only leak counts

**Primary canonical owner:** [P6](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1 / M / ART-09 for adaptive-mode cases; current layout can be covered first. **Backlog:** P17/P8 implementation acceptance; P6 remains independent human publishability authority. Verification section owns shared gate orchestration, not this creation-stage fixture design.

**Evidence / diagnosis:** `scripts/quality/public_advisory_render_benchmark.py:45–141,164–229` measures useful artifact/render properties, including linkage, so/now-what coverage, duplicate insights, leaks, placeholders and broken assets. Its `screenshot_paths` are supplied references, not generated viewport checks. `scripts/ci/check_public_report_quality.py:40–74` compares that retained benchmark. Existing render tests protect many fields, but these counters alone cannot establish that a generated theme, decision condition, limitation or critical reader module survived layout/coercion in the intended place. **Hypothesis to verify with fixtures:** some artifact combinations can silently lose public usefulness while passing scalar checks; no current production incident is asserted.

**Luna implementation:** Extend the existing retained creation/render corpus with a small role-aware manifest: required approved thesis/theme/decision/uncertainty text identities, allowed omission reason, source links and artifact hashes for each fixture. Compare canonical HTML and WordPress public projections for required surviving roles and permitted transforms, not byte equality or raw private content exposure. Add bounded local desktop/mobile/print captures and DOM checks for hidden required content, orphan links, heading order and overflow. Keep golden updates reviewed; screenshots are not automatic human acceptance.

**Success criteria:** Deliberately dropping each required role makes the fixture gate fail with role/artifact/field identity; approved abstentions/omissions pass explicitly. All supported artifact profiles deliver their required public content once without leakage, broken links or hidden/clipped modules. Deterministic rerenders preserve normalized content/media identities.

**Validation:** `python -m pytest -q tests/test_artifact_public_projections.py tests/test_render_service_determinism.py tests/test_render_service_public_prose.py tests/test_wordpress_report_rendering_contract.py tests/test_public_editorial_quality_html.py`; extend the canonical benchmark/gate with proposed role fixtures rather than a second scorecard. Run `python scripts/ci/check_public_report_quality.py`; record browser availability and manual visual-review outcomes separately, with no hosted writes.

Artifact-review limitation: no source changes or live calls were made. Public-boundary reproduction could not start because default Python lacks `jinja2`; focused tests require a supported environment with `pytest`. Commands above are future implementation requirements, not passing results from this documentation review. Suggested sequence: ART-02/07/08 localized corrections, ART-01 durable reuse, ART-04/05/03 bounded efficiency, then ART-06/09 product-contract work with ART-10 acceptance evidence. Do not claim P6/P17/A21 closure from specifications or offline fixtures alone.

**Luna implementation prompt — ART-10 (copy/paste)**

```text
Implement ART-10 — Test generated-artifact delivery by content role, not only leak counts.
Objective: Deliver the verified behavior specified immediately above under canonical P6.
Source: docs/backlog/P-publication.md, technical slice ART-10.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update P6 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ver-06"></a>
#### VER-06 — Calibrate verifier false accepts and false rejects against blinded human evidence

**Primary canonical owner:** [P6](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1 / M / VER-05; extends P6/R1, preserves the current human acceptance thresholds.
- **Evidence / diagnosis:** Independent human acceptance is already mandated. However `docs/quality/public-editorial-human-evaluation.md:8–12` still prescribes 30 reports and a four-dimension 1–5 rubric, while canonical `CONSOLIDATED_TODO.md:P6:318–331` defines 15 reports, three cohorts and the current weighted 100-point protocol. This is a confirmed procedural contradiction. Existing model migration comparisons (`gpt6-luna-evaluation-20260923.md:34–47,49–95`) document held failures and output differences but do not establish per-class judge false-accept/false-reject calibration on an independently labelled holdout. Do not confuse editorial usefulness review with source-fidelity adjudication.
- **Luna implementation:** First align the canonical human-review procedure with P6 without changing its thresholds or inventing completed reviews. Extend the existing review record with a distinct blinded verifier-adjudication lane: sample accepted and held cases, retain exact rendered/source/package hashes, hide model and gate outcomes from reviewers, and adjudicate disagreements using the retained source. Split tuning cases from an immutable publisher/report-family holdout, excluding those used to patch prompts. Compute error counts/rates with denominators and uncertainty by violation class; insufficient samples abstain from threshold proposals. Keep this read-only and require review for any proposed policy change.
- **Success criteria:** One authoritative review protocol, independently attributable labels, and matched output hashes. Both false rejection and false acceptance are visible; no held case disappears. No claim of population-level accuracy from a tiny sample and no automatic confidence-threshold relaxation. P6 human approval remains distinct from automated validation success.
- **Validation:** Unit-test the deterministic review importer/aggregator with missing reviewer, mismatched hash, split overlap, contradictory labels and tiny-sample fixtures; propose `tests/test_verifier_calibration.py`. Run the existing documentation validator and public-quality suites. Execute the blinded review only with real reviewers; GPT6 Luna may implement tooling and assemble packets, not fabricate independent human judgments or declare P6 closed.

**Luna implementation prompt — VER-06 (copy/paste)**

```text
Implement VER-06 — Calibrate verifier false accepts and false rejects against blinded human evidence.
Objective: Deliver the verified behavior specified immediately above under canonical P6.
Source: docs/backlog/P-publication.md, technical slice VER-06.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update P6 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
---
 
## P7. Fix public performance measurement and reach hosted targets

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** none; outcome specification stands alone.

- **Baseline:** The seven-route HTTP tool labels GET/parse/same-site HEAD elapsed time `dom_complete_ms`, discovered references as requests and Content-Length estimates as page weight. These are HTTP regression/inventory estimates, not browser navigation, actual requests or transferred bytes. YAML targets remain unused and review date remains August 1; local HTTP tests do not establish hosted browser target attainment. Correct measurement before optimization.
- **Target behaviour:** Performance evidence separates cheap HTTP regression probes from real browser navigation timing, treats the retained baseline as a regression ceiling and targets as explicit optimisation goals, then improves the seven public routes without losing metadata, archive completeness, or public content contracts.
- **What to implement, in order:**
  1. Version HTTP elapsed time, discovered references, actual HEAD-probed count and estimated size with explicit unknown/failed estimates. Add distinct browser Navigation Timing/request/transfer measurements with cold/warm cache and environment identity; never compare unlike method generations.
  2. Update the baseline schema/gate so baseline regression and target attainment are reported separately; fail regressions against baseline, report target gaps independently, and retain exact measurement method/version. Version/adapt PublicSitePageQuality and tests; unavailable browser metrics or incomplete probes cannot appear as zero/pass.
  3. Run a fresh hosted seven-route measurement and only then refresh the baseline review date/values; preserve raw scalar evidence and exact code SHA. Retain deployment/package identity, repeated-run summaries and raw scalars; host variance or a manually advanced date is not improvement proof.
  4. Profile the largest target gaps and address the highest-value causes first: unnecessary WordPress queries, duplicate assets, render-blocking/unused resources, excessive payloads, or avoidable archive work—without weakening content/SEO semantics.
  5. Re-run browser and HTTP gates after each change and retain before/after route metrics.
- **Acceptance criteria:**
  - No metric name claims browser DOM/load semantics unless it is sourced from browser navigation timing.
  - Gate output clearly distinguishes `baseline_regression` from `target_gap`; YAML target values are actually evaluated and reported.
  - Fresh baseline evidence is current, method-versioned, and tied to the exact tested SHA; stale dates are not manually advanced.
  - Homepage, reports, briefings, signals, methodology, contact, and submit show no baseline regression in response timing, weight, or request count and materially reduce the largest target gaps.
  - Canonical URLs, Open Graph/Twitter metadata, archive completeness, search/filter behavior, and representative page content remain unchanged/correct after optimisation.

### Luna implementation prompt — P7

```text
Work on P7 — Fix public performance measurement and reach hosted targets at the current MarketLense HEAD.
Owner specification: docs/backlog/P-publication.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
---
 
## P8. Complete concise public evidence, methodology, and related-content surfaces

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** none; outcome specification stands alone.

- **Baseline:** Public rendering already includes sanitized claim-support labels, metric/advisory panels, methods/coverage/limitations, source metadata and native topic/publisher navigation, with render/WordPress redaction/parity tests. Topic briefs now preserve Unicode text and supplied section IDs, and ambiguous title-only matches do not borrow section pages. `src/services/_render_service/normalization.py::_coerce_public_claim_support` projects claim/support labels, but not an approved source/page/support/caveat/link contract. Methods remain free-text views, and directory navigation does not establish report-specific related-content ranking. Extend these owners rather than recreate advisory presentation, intelligence transport or taxonomy navigation.
- **Target behaviour:** Every supported report page can expose concise, approved evidence context and methodology plus deterministic related links that help a reader verify and continue research. Missing/unapproved evidence fails closed to omission/neutral language rather than exposing internal diagnostics or fabricated support.
- **What to implement, in order:**
  1. Extend the existing public claim-support projection with a versioned source/publisher, approved page, concise support, caveat and policy-approved link contract plus legacy adapter; do not create parallel reader representations. Retain approved claim/source roots and explicitly adapt physical/printed page semantics.
  2. Define a concise methodology projection using report scope, source pages, material limitations, evidence state, and relevant timing/geography—without exposing OCR/vector/model/validation internals.
  3. Build report-specific deterministic related-content selection over approved retained relationships/metadata, reusing native topic/publisher URLs. Exclude self, exact-source aliases, stale/unpublished/unavailable targets; record bounded ranking or omission reasons. No new LLM/embedding I/O at render time.
  4. Project only approved fields to WordPress and render them with existing design primitives; keep WordPress render-only for intelligence.
  5. Add redaction/fail-closed tests for missing, stale, private, or unapproved source/evidence fields and related-link absence.
- **Acceptance criteria:**
  - Material public claims can show approved source report, publisher, page/support context, limitation, and original link where available without internal IDs or raw evidence text.
  - Methodology surfaces source scope/pages, material limitations and evidence state concisely; unavailable data is omitted/neutral, never fabricated.
  - Report pages expose deterministic related report/briefing/topic/publisher links when supported and no unrelated link is invented to fill a slot.
  - No provider/model call is required during WordPress rendering or related-link display.
  - Tests prove internal IDs, OCR/model/vector/crop diagnostics, private paths/Drive URLs and unapproved excerpts cannot reach the public projection.

### Luna implementation prompt — P8

```text
Work on P8 — Complete concise public evidence, methodology, and related-content surfaces at the current MarketLense HEAD.
Owner specification: docs/backlog/P-publication.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
---
 
## P10. Operate correlated public-render failure telemetry

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** none; outcome specification stands alone.

- **Baseline:** The PHP boundary provides branded redacted visitor markup/correlation and emits `marketlense_public_render_failure`; its event payload remains unsafe/unbounded pending P2. Local injection tests and response scans do not establish hosted capture or expected-versus-unexpected failure aggregation. Publication/readback is a different boundary. Private capture, deterministic classification and operational integration remain open.
- **Target behaviour:** Hosted/release evidence gives operators a bounded, private, correlation-based view of public-render failures by route/entity type, while visitors see only the safe response. Repeated unexpected failures are actionable without creating a public diagnostics endpoint.
- **What to implement, in order:**
  1. Make P10 consume the P2-bounded WordPress event contract so only safe bounded fields enter release aggregation.
  2. Add a read-only aggregation step for failure count, route/entity type, correlation ID/hash, first/last occurrence and expected-injected versus unexpected classification; do not retain exception text in public/release artifacts. Use authorized private capture with explicit coverage/window and deployment identity. Missing capture is unavailable; observed zero requires a successfully captured window.
  3. Integrate the aggregate into hosted smoke/release evidence and define a simple threshold/disposition for zero, expected injected, and unexpected failures.
  4. Add a controlled injected-failure smoke path in non-public/sandbox validation and verify the visitor response stays branded/redacted. Bind expected injections to exact fixture/run correlation IDs, preserving unrelated unexpected failures. Reuse the local PHP harness; hosted proof requires an approved isolated sandbox.
  5. Link unexpected recurring failures to the existing remediation/operator workflow rather than creating another scheduler.
- **Acceptance criteria:**
  - Hosted smoke/release evidence reports bounded failure counts and correlation references by route/entity type with no stack/path/exception-message leakage.
  - A controlled injected failure is classified as expected and produces the branded public response; a synthetic unexpected case is visible as an unwaived failure.
  - Zero-failure runs explicitly report zero rather than missing telemetry.
  - Repeated aggregation is deterministic and does not expose a public diagnostics route or create external writes beyond existing evidence publication.

### Luna implementation prompt — P10

```text
Work on P10 — Operate correlated public-render failure telemetry at the current MarketLense HEAD.
Owner specification: docs/backlog/P-publication.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
---
 
## P16. Build a decision-grade consulting synthesis artifact

**Canonical status:** Active in [CONSOLIDATED_TODO.md](../../CONSOLIDATED_TODO.md). **Mapped technical slices:** `ANA-03`, `ANA-08`, `ANA-09`, `GRD-09`, `ARCH-E`.

- **Baseline:** Editorial plans, evidence-bound insights, deterministic executive-advisory/Decision Brief assembly, and separately generated Expert/LinkedIn copy exist. `src/generators/_artifact_generator/storage.py::build_executive_advisory_artifacts` mainly copies insight implication/action text and leaves structured rationale/impact/likelihood/mitigation empty. There is no persisted `decision_synthesis` family or governed audience-context contract. Historical P6 score matrices are partial human evidence, not consultancy-quality closure. The source-linked decision model, coherent cross-surface projections and comparative outcome proof remain open. Cross-report selection recomputes publisher diversity from immutable base scores each round and now rescales cap-rejected candidates against the completed selected-publisher set; ten shuffled permutations verify stable selected IDs, ranks and decision reasons. This deterministic control-flow result is not human evidence of synthesis quality.
- **Target behaviour:** Each report has one versioned, persisted, source-fidelity-validated decision synthesis that states what decision the evidence informs, what changed, why it matters, available actions/options, conditions and trade-offs, risks/counterevidence, uncertainty, and what evidence to collect next. Every public advisory surface is a purposeful projection of that one model, not an independent competing synthesis. Creativity means finding a report-specific, non-obvious but supported connection—not adding unsupported facts or generic strategy language.
- **What to implement, in order:**
  1. Freeze a consultancy-quality rubric and baseline on the existing P6 cohorts. Label decision clarity, evidence-to-implication chain, specificity, trade-off quality, counterevidence, actionability, originality-without-speculation, audience fit, cross-section repetition, and abstention quality; retain exact artifact hashes and reviewer attribution. P6 continues to own overall publishability acceptance.
  2. Add a versioned `decision_synthesis` family to the persisted artifact schema with bounded fields for decision question, executive thesis, evidence-backed changes, implications, actions/options, conditions, trade-offs, risks/counter-signals, known unknowns/next evidence, applicability, and confidence rationale. Every factual proposition and source-derived premise carries one or more approved evidence IDs; analyst-authored advice carries its supporting premise IDs and an explicit `source_stated|marketlense_analysis|conditional` status.
  3. Accept optional non-secret audience context only through a typed request (`role`, `industry`, `geography`, `decision_horizon`, `stated_objective`, `constraints`) and hash it into lineage. Missing context must produce a useful general executive lens; the model may not infer a company, budget, maturity, competitor position, or objective.
  4. Generate the synthesis once after the editorial plan and fidelity-approved evidence/methods/limitations are available. Use deterministic candidate assembly first, then one semantic synthesis call only where a grounded relationship/trade-off cannot be selected mechanically. Route it through the canonical prompt/LLM policy, structured-output, budget, replay, and targeted-regeneration boundaries.
  5. Validate the complete evidence→premise→implication→action chain. Factual premises use the existing source-fidelity/grounding checks; advice must be conditional when outcomes are not source-stated; contradictions, weak applicability, and missing evidence force qualification or abstention. Reject generic actions that would remain valid after changing the report's evidence IDs/title.
  6. Refactor Summary, Decision Brief, Findings implications, Expert View, card copy, and LinkedIn generation to consume the same approved synthesis while preserving purpose/length. Extend the existing deterministic advisory assembler first; declare which independent calls are replaced or retained, provide a versioned legacy adapter and leaf-level regeneration lineage. Add cross-surface redundancy measurement; do not create a competing synthesis layer.
  7. Run blinded pairwise review against the retained baseline with senior strategy/editorial reviewers. Promote only when decision quality and human preference improve without source-fidelity, completeness, cost, or first-pass regression; keep the current pipeline if evidence is inconclusive.
- **Acceptance criteria:**
  - Every non-abstained factual premise, implication, risk, trade-off, and recommended action is traceable through the retained synthesis to approved evidence IDs; advice not explicitly stated by the source is visibly conditional and cannot smuggle in an unsupported factual premise.
  - An absent audience context never invents client facts, while supplied context is schema-validated, non-secret, lineage-bound, and used only within its declared role/geography/horizon/objective/constraints.
  - Representative fixtures cover data-heavy, narrative, survey, forecast, methodology-limited, one-sided, and conflicting-evidence reports; thin evidence produces a concise abstention/unknown rather than generic recommendations.
  - On the frozen P6 comparison set, at least **80% of blinded pairwise judgments** prefer the candidate for decision usefulness and at least **75%** prefer it for report-specific insight/originality; no factual-fidelity score falls below the retained baseline and no accepted report contains an unsupported causal or commercial outcome.
  - Cross-surface near-duplicate blocks fall by at least **50%** from the exact baseline while all editorial-plan themes remain represented and each surviving module has a distinct role; metrics/qualifiers remain exact.
  - The normal first-pass path adds at most one decision-synthesis provider call; cache/lineage identity includes evidence, prompt, policy, schema, and audience context, and incompatible reuse fails closed. Targeted repair changes only the rejected synthesis fields and their deterministic dependents.
  - Schema, serialization, grounding, semantic, public-editorial, prompt-fixture, P6 human-review, and checksum-bound publish-readiness tests/evidence pass on the exact implementation SHA with zero new publication bypass or hidden retry. Scope-dependent advice uses E16 facts or explicit unknowns, legacy artifacts retain safe rendering, and preference cannot override factual/readiness rejection.

### Luna implementation prompt — P16

```text
Work on P16 — Build a decision-grade consulting synthesis artifact at the current MarketLense HEAD.
Owner specification: docs/backlog/P-publication.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
### Linked technical implementation slices

Technical IDs below are **subtasks or investigations**, not additional canonical Active outcomes. Status notes are historical catalogue/reconciliation claims and require current-HEAD verification.
 
<a id="ana-03"></a>
#### ANA-03 — Calculate publisher-diversity bonuses once per selection round

**Primary canonical owner:** [P16](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Implemented and verified in source commit `46c87c0170bfc6575a06f55de23557eb0de77334` on 2026-10-12; P16 remains Active.

**Priority / effort / dependencies:** P1; S, two slices; none. **Owner/backlog:** deterministic cross-report source ranking; new surgical correctness ticket, not a reranking-system rewrite.

**Evidence and impact:** `_select_diverse_sources()` already recomputed scores from immutable base scores and reasons during each selection round. After the last winner was added to `selected_publishers`, cap-rejected candidates still held their previous-round values. In the four-slot regression fixture, `c-sibling` retained score `4.45`, diversity score `0.75`, and `publisher_diversity` after `c-independent` from the same publisher was selected; the corrected final output is `3.7`, `0.0`, and `same_publisher_already_selected`. Under a one-report cap, same-publisher `a-sibling` changes from stale `5.05`/`publisher_diversity` to its base `4.3`/`same_publisher_already_selected`; an independent publisher correctly keeps its `0.75` bonus. The selected IDs, ranks and decision-round reasons remain unchanged across ten shuffled permutations. `max_source_reports_reached`, filter rejections, contracts and downstream selection behavior are unchanged. These fixture checks validate selector output; no canonical Briefing/Signal report replay or downstream prose-quality review was run for this slice.

**Luna implementation:** Reuse one local scorer for both the existing per-round score calculation and a final pass over cap-rejected candidates against the completed selected-publisher set. Preserve immutable base scores/reasons, the 0.75 weight, deterministic tie-breaks, selected decision-round explanations, publisher identity rules, rejection reasons, filters, contracts and downstream behavior. No model, dependency or configuration change.

**Success criteria:** For every selected source, `total_score == base_score + current_round_diversity_score` within 1e-6, regardless of number of previous rounds. No candidate ever retains a diversity bonus after its publisher is represented. Ten shuffled permutations of each labelled fixture produce identical selected IDs and decision reasons. Single-source and single-publisher behavior remains compatible except removal of stale bonuses.

**Validation (source commit `46c87c0170bfc6575a06f55de23557eb0de77334`, 2026-10-12):** `python -m pytest -q tests/test_cross_report_analysis_input_generator.py tests/test_cross_report_analysis_input_decomposition.py` — 44 passed, including ten shuffled permutations, same-publisher cap rejection, one-report limit, exact selected IDs/ranks/reasons, and final rejected scores/reasons. Before the fix, both new regressions failed on stale rejected values; after the fix, both pass. `python scripts/ci/check_ruff_lint.py`, `python scripts/ci/run_type_check.py`, `python scripts/ci/check_architecture_imports.py`, `python scripts/ci/check_role_io_boundaries.py`, and `python scripts/ci/check_service_boundary_map.py` passed. No canonical Briefing/Signal replay was run; the above component-level fixture evidence checks selected membership and rejected outputs, but does not measure downstream prose quality.

**Luna implementation prompt — ANA-03 (copy/paste)**

```text
Implement ANA-03 — Calculate publisher-diversity bonuses once per selection round.
Objective: Deliver the verified behavior specified immediately above under canonical P16.
Source: docs/backlog/P-publication.md, technical slice ANA-03.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update P16 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ana-08"></a>
#### ANA-08 — Classify agreement only among comparable, independent propositions

**Primary canonical owner:** [P16](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1; L, four reviewable slices; ANA-01/07 and GRD-07; GRD-10 supplies valid retained references. **Owner/backlog:** cross-report agreement and Signal confidence; analytic application of E16 context, not a replacement source-grounding engine.

**Evidence and impact:** `_agreement_type_and_reasons()` in `src/generators/_cross_report_analysis_input/evidence_signals.py:658–671` calls any two-publisher/two-report group convergent unless separate items contain opposing directional keywords. `_directional_markers():629–655` does not align subject/metric/geography/period or handle negation. `src/generators/signal_candidate_generator.py:63–80,101–115` promotes that label into support type and formulaic confidence. **Confirmed heuristic limitation:** EU conversion rising and US acquisition cost falling are neither corroboration nor contradiction; two publishers repeating one survey are not two independent observations. Existing confidence is a score, not a calibrated probability.

**Luna implementation:** (1) Group only approved propositions with compatible subject, metric, cohort, denominator, geography, period and observation status. (2) Preserve source-root dependency where retained; unknown independence remains unknown, not automatically independent. (3) Determine convergent/divergent only for comparable observations with supported direction and negation, otherwise emit typed non-comparable/insufficient coverage via an explicit contract transition. (4) Rename uncalibrated confidence semantics or calibrate separately on labels; no invented probabilistic interpretation. Use semantic adjudication only for unresolved supported relationships, bounded by existing orchestration.

**Success criteria:** On 40 labelled groups, non-comparable and syndicated-source fixtures never become multi-report corroboration; agreement precision is at least 95% and recall at least 90%. Unknown context/independence remains visible. A duplicated source cannot raise confidence; actual comparable contradictions survive selection. No currency/period normalization is inferred without supported rules.

**Validation:** `python -m pytest -q tests/test_cross_report_analysis_input_generator.py tests/test_cross_report_analysis_contracts.py tests/test_signal_candidate_generator.py tests/test_cross_report_analysis_orchestrator.py`. Add negation, different markets, observed-versus-forecast, duplicate-survey citations and genuine same-cohort contradictions; replay canonical Signal/Briefing inputs and inspect support labels/evidence IDs, not merely schema acceptance.

**Luna implementation prompt — ANA-08 (copy/paste)**

```text
Implement ANA-08 — Classify agreement only among comparable, independent propositions.
Objective: Deliver the verified behavior specified immediately above under canonical P16.
Source: docs/backlog/P-publication.md, technical slice ANA-08.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update P16 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="ana-09"></a>
#### ANA-09 — Bound prompt size without starving later sources or counter-evidence

**Primary canonical owner:** [P16](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1; M–L, three slices; ANA-06; coordinate ANA-04 relevance ranking. **Owner/backlog:** cross-report evidence assembly; targeted quality/cost extension using the existing configurable evidence limit and budget authority.

**Evidence and impact:** `_evidence_sort_key()` in `src/generators/_cross_report_analysis_input/evidence_signals.py:79–88` orders primarily by report, then class. Assembly truncates that order at the global item count (`827–858`), so the first report can consume all 48 slots. Every selected raw metric is appended without a corresponding cap (`860–870`). `_prompt_input_chars()` estimates size but does not bound it (`98–126`). **Confirmed shape:** source selection can claim multiple sources while bounded evidence represents only one, and a metrics-heavy corpus can grow prompt size despite the evidence limit. Actual token/cost inflation remains unmeasured.

**Luna implementation:** (1) Allocate eligible evidence by request relevance with a deterministic minimum represented-source quota when capacity permits; reserve supported counter-evidence and then fill remaining slots by incremental value. (2) Bound raw metrics and total serialized prompt size together, counting metadata/format overhead; use the canonical tokenizer if available, otherwise label conservative character estimates honestly. (3) Retain per-source considered/selected/dropped counts and reasons, and exclude unsupported sources from claims of represented coverage. Never truncate an evidence item's protected numeric/context fields mid-record.

**Success criteria:** A three-source fixture with 100 first-source claims gives every eligible source evidence at cap=48 and retains its labelled contradiction. A 1,000-metric fixture stays within the declared prompt limit; rejected/deferred records remain traceable. On ANA-06 tasks, supporting/counter-evidence recall does not regress and median prompt tokens decrease at least 20% in the metrics-heavy stratum. Small inputs retain exact evidence.

**Validation:** `python -m pytest -q tests/test_cross_report_analysis_input_generator.py tests/test_cross_report_analysis_orchestrator.py tests/test_signal_candidate_orchestrator.py`. Add skewed-source, oversized metadata, one-slot, counter-evidence and metric-heavy fixtures; compare exact serialized prompt sizes and source coverage over three identical offline replay runs, with zero provider calls.

**Luna implementation prompt — ANA-09 (copy/paste)**

```text
Implement ANA-09 — Bound prompt size without starving later sources or counter-evidence.
Objective: Deliver the verified behavior specified immediately above under canonical P16.
Source: docs/backlog/P-publication.md, technical slice ANA-09.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update P16 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="grd-09"></a>
#### GRD-09 — Ground factual premises inside recommendation and interpretation sentences

**Primary canonical owner:** [P16](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies / owner:** P0 / M–L, three bounded slices / GRD-01/02/07 / private soft-copy claim provenance. **Backlog:** P16 evidence→premise→implication→action chain and A21; verification still owns judge verdict completeness and readiness enforcement.

**Evidence and impact:** `src/generators/claim_validation_generator.py:276–292` sets a candidate nonfactual when its model-declared classification is `interpretive` or `recommendation`, regardless of numeric kind. `_semantic_inputs()` at lines 724–729 excludes nonfactual candidates. `src/generators/soft_copy_claim_provenance.py:107–120` requires evidence IDs only for declared factual bindings. **Confirmed and locally reproduced:** “Since adoption reached 99%, leaders should scale wallets” declared recommendation with no evidence has a nonfactual local result and local `awaiting_review` package. This is not proof other final grounding/readiness rules accept it. Pure advice appropriately remains nonfactual; the missing seam is its embedded factual premise.

**Luna implementation:** (1) Extend sentence-level private provenance with bounded premise clauses/character ranges and explicit factual-versus-advisory relationships, retaining the whole public sentence/hash as owner. (2) Require factual-premise evidence for material numeric, attributed, comparative or causal assertions inside advice/interpretation. Deterministic markers identify obvious required premises; unresolved semantic clause classification uses the current report-level model boundary, not an additional per-sentence loop. (3) Validate premise support through existing packages; unsupported premises cause qualification/removal of that sentence, preserving genuinely source-independent conditional advice. Version retained bindings and reuse identities.

**Success criteria:** A recommendation label cannot exempt its material factual premise; contradictory/unsupported numeric premises block that sentence's factual support. Pure recommendations and explicit hypothetical conditionals do not acquire invented evidence requirements. Every accepted premise resolves to approved roots, with bounded calls and exact final-text coverage.

**Validation:** Run `python -m pytest -q tests/test_soft_copy_claim_provenance.py tests/test_claim_validation_generator.py tests/test_grounding_editorial_interpretation.py tests/test_retained_claim_grounding.py`. Add factual-plus-advice, pure advice, hypothesis, causal-premise and altered-clause fixtures; canonical artifact→provenance→grounding replay must inspect actual premise inventory, not merely sentence classification.

**Luna implementation prompt — GRD-09 (copy/paste)**

```text
Implement GRD-09 — Ground factual premises inside recommendation and interpretation sentences.
Objective: Deliver the verified behavior specified immediately above under canonical P16.
Source: docs/backlog/P-publication.md, technical slice GRD-09.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update P16 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="arch-e"></a>
#### ARCH-E — Project the same selected evidence into summary, decision advice and Expert View

**Primary canonical owner:** [P16](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1 / M / follow-ups A–D; fold into `P16` decision synthesis and `E16` applicability instead of adding an independent synthesis family.
- **Evidence / diagnosis:** Summary and insight candidates currently share an editorial plan but do not require one ranked evidence slate. `build_executive_advisory_artifacts()` assembles implication/action/watchout text primarily from evidence-linked insights, and `_unique_advisory_texts()` keeps the first distinct entries up to its limit; textual distinctness and input order do not ensure the most useful executive recommendations. Expert context takes bounded theme/implication lists, also without a shared portfolio decision.
- **Luna implementation:** Feed summary and the existing P16 decision model the chosen thesis, best supporting facts, relevant counter-signals, applicability and approved reserve. Select advice for decision relevance, action specificity, evidence-to-premise-to-action integrity, trade-offs and report-specific usefulness. Let each public surface express a different role/length; avoid repeating identical claims in summary, decision brief and Expert View. Reuse existing deterministic advisory assembly where adequate and at most the P16-approved semantic synthesis where needed; do not silently add a model call per output family.
- **Success criteria:** Public executive claims and advice trace to approved evidence or explicit conditional analysis, use correct qualifications, prioritize the strongest actionable material, and avoid cross-surface near-duplicates. Weak/one-sided reports preserve uncertainty instead of generating generic recommendations.
- **Validation:** Test evidence-to-action linkage and input-order invariance on representative data-heavy, narrative and methodology-limited reports. Compare blinded P6/P16 editorial preference, factual fidelity, repetition and actual provider spend against the unchanged baseline.

**Luna implementation prompt — ARCH-E (copy/paste)**

```text
Implement ARCH-E — Project the same selected evidence into summary, decision advice and Expert View.
Objective: Deliver the verified behavior specified immediately above under canonical P16.
Source: docs/backlog/P-publication.md, technical slice ARCH-E.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update P16 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
---
 
## P17. Compose adaptive, non-repetitive visual report stories

**Canonical status:** Active as of the archived 2026-10-08 reconciliation. **Mapped technical slices:** `ART-06`, `ART-07`, `ART-08`, `ART-09`, `ARCH-B`, `ARCH-F`.

- **Baseline:** The fixed renderer and public/WordPress parity are implemented, including exact advisory/insight repetition suppression and strict accepted-visual linkage/omission in `src/services/_render_service/view.py`. Deterministic cover seeds now ignore `_cache` execution telemetry while remaining bound to artifact content. `templates/report.html.j2` still uses one content sequence; there is no persisted `report_composition` contract or finite source-type reading-path mode. Existing crop QA/linkage does not prove E15 semantic completeness or P17 narrative usefulness and human desktop/mobile preference. Extend the view/template boundaries without rebuilding extraction, crop QA or public transport.
- **Target behaviour:** A bounded composition plan turns already-approved editorial, advisory, evidence, and visual assets into a report-specific reading path. It chooses a finite narrative mode, module order/emphasis, visual anchors, evidence depth, and omission decisions from available content; it never generates new facts in the renderer. The same plan produces accessible, responsive HTML and WordPress projection, and every displayed visual is E15-approved and semantically necessary.
- **What to implement, in order:**
  1. Audit the hash-pinned P6 reports at desktop and mobile for module repetition, time-to-first-decision, theme coverage, evidence depth, text/visual balance, chart/table usefulness, caption/action linkage, empty/weak modules, and reading length. Add human labels for visual storytelling and information hierarchy; do not use the renderer's own score as the target.
  2. Define a small finite composition taxonomy such as `data_led`, `survey_tension`, `market_outlook`, `operating_framework`, and `concise_evidence_note`, with deterministic eligibility from report type, editorial-plan breadth, evidence/metric density, methods/limitations, and E15-approved visual inventory. Ambiguous cases use the current safe layout; do not create open-ended model-designed templates.
  3. Add a versioned `report_composition` contract mapping each planned module to one purpose, source artifact IDs, editorial-plan theme IDs, optional approved visual/caption/evidence IDs, display priority, and omission reason. Build it in the generator after P16/E15 inputs are validated; the renderer may only project the plan and cannot synthesize missing intelligence.
  4. At composition time select anchors from the already accepted visual inventory for evidentiary value and narrative role (`thesis_proof`, `comparison`, `mechanism`, `risk`, `methodology`). Initial visual selection precedes report analysis and cannot require unavailable future analytical claims. Match the approved theme/claim and complete caption/source context, pass E15, and omit assets that add no information.
  5. Refactor the HTML/WordPress view model to render the finite plan with semantic headings, stable deep links, keyboard/assistive navigation, responsive image sizing, and print/share behavior. Preserve safe fallback for legacy artifacts and keep intelligence generation out of WordPress.
  6. Add deterministic checks for uncovered priority themes, repeated paragraphs/metrics, orphan visuals, duplicated module purpose, excessive text before the first decision, visual-caption mismatch, and empty decorative sections. Keep advisory thresholds reviewable until human evidence supports a hard release gate.
  7. Compare the candidate and current layout through blinded desktop/mobile review and browser regression on the same report hashes. Promote only if comprehension, hierarchy, and visual usefulness improve without accessibility, Core Web Vitals, SEO, source fidelity, or WordPress checksum regression.
- **Acceptance criteria:**
  - Every report composition has exactly one supported finite mode, one purpose per displayed module, complete priority-theme coverage or an explicit evidence-based omission, and no renderer-created facts or prose.
  - **100% of displayed chart/table assets** carry matching candidate, crop-sidecar, evidence, insight/theme, caption, source-page, and composition-role identities; every asset passes E15 and no preview/lower-DPI/rejected crop reaches public HTML.
  - On the frozen review set, no adjacent modules contain a verbatim paragraph or materially duplicate the same claim/metric without a declared distinct purpose; deterministic redundancy decreases versus baseline without dropping decision-critical evidence.
  - At least **80% of blinded desktop/mobile comparisons** prefer the candidate for information hierarchy and visual storytelling, and at least **80% of reviewers** can identify the thesis, primary evidence, main implication, and principal limitation correctly after a bounded read.
  - Automated browser checks cover every composition mode at 390, 768, 1024, and 1440 CSS-pixel widths with no horizontal overflow, clipped text/image, broken anchor, keyboard trap, missing focus state, empty landmark, console error, failed asset request, or materially regressed accessibility result.
  - Public HTML/WordPress normalized text, links, metadata and media identities remain checksum/readiness-bound. Composition/decision/visual hashes bind mode-specific fixture/browser/human review before activation; text/no-usable-visual and legacy layouts remain safe. SEO and hosted performance remain within P7 targets; P5 owns site navigation while P17 proves report-mode behavior.

### Luna implementation prompt — P17

```text
Work on P17 — Compose adaptive, non-repetitive visual report stories at the current MarketLense HEAD.
Owner specification: docs/backlog/P-publication.md; canonical status: CONSOLIDATED_TODO.md.
First inspect the current implementation and the unmet acceptance criteria in this outcome.
Select one coherent, highest-impact unverified slice; consult its technical specification below.
Follow AGENTS.md, reuse canonical modules/contracts/tests, and avoid speculative architecture.
Preserve all factual, provenance, reliability, budget and publication guards.
Verify affected success/failure paths, downstream behavior and actual outputs where relevant.
Record exact commands/results, skipped checks, SHA, cohort, evidence, residual gaps and rollback.
Only close the canonical outcome after all its acceptance criteria have evidence.
Commit and push the scoped change, including the necessary backlog evidence update.
```
 
### Linked technical implementation slices

Technical IDs below are **subtasks or investigations**, not additional canonical Active outcomes. Status notes are historical catalogue/reconciliation claims and require current-HEAD verification.
 
<a id="art-06"></a>
#### ART-06 — Match insight requirements to independently supported source breadth

**Primary canonical owner:** [P17](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1 / M, three slices / ART-09 uses the resulting profile; independent implementation first. **Backlog:** P17/A21; requires explicit product-contract change, not blanket relaxation of quality gates.

**Evidence / diagnosis:** `src/generators/artifact_normalization.py:52–53` defines a two-insight family minimum but a five-insight report requirement. `:1082` and `src/generators/_artifact_generator/generation.py:920–925` target at least five; `src/orchestrators/_report_analysis_orchestrator/payload.py:104–110` requires five populated payload slots. Editorial-plan normalization at `artifact_normalization.py:160–171` also requires at least two themes. **Confirmed inconsistent granularity:** a valid concise source can satisfy family policy but fail report shape, or be pushed toward more themes/insights than its distinct evidence supports. No prevalence or actual hallucination rate was measured.

**Luna implementation:** Freeze a labelled concise-versus-rich report stratum before changing eligibility. Add a bounded persisted content profile with explicit independently supported theme/claim counts; source length alone is insufficient. Preserve the existing rich-report five-slot requirement. Introduce a separately versioned concise-evidence-note profile only when approved evidence supports fewer distinct items; propagate its allowed count consistently through prompts, family policy, payload, cards, renderer and readiness. If fewer than the minimum useful independent claims exist, hold/reject rather than duplicate or invent them. Card requirements remain satisfiable explicitly; no hidden padding adapter.

**Success criteria:** Labelled eligible concise fixtures deliver all independent supported claims exactly once without count-only failure; rich fixtures retain existing minimum coverage. Zero padded duplicates, invented themes or weakened grounding/readiness. Any unsupported source remains a typed hold.

**Validation:** `python -m pytest -q tests/test_artifact_generator.py tests/test_artifact_normalization.py tests/test_report_analysis_orchestrator_decomposition.py tests/test_report_card_projection.py tests/test_public_report_quality_gate.py`; new 2/3/5-claim concise/rich/misclassified fixtures plus legacy schema adapters. Blinded P6 review must show usefulness/fidelity no worse before enabling this public profile.

**Luna implementation prompt — ART-06 (copy/paste)**

```text
Implement ART-06 — Match insight requirements to independently supported source breadth.
Objective: Deliver the verified behavior specified immediately above under canonical P17.
Source: docs/backlog/P-publication.md, technical slice ART-06.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update P17 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="art-07"></a>
#### ART-07 — Preserve multilingual topic meaning and section identity

**Primary canonical owner:** [P17](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1 / S–M / none. **Backlog:** P8/P17 bounded topic-projection correctness subtask.

**Evidence / diagnosis:** `src/generators/_artifact_generator/toc.py:59–70`, `_normalize_topic_lookup_text()`, removes everything outside ASCII `a-z0-9`; `:372–386`, `_dedupe_non_empty_text()`, drops points with empty normalized keys. `:299–363` then uses these normalized titles/tokens to attach topic briefs, and `:440–470` resolves supplied section titles using normalized-title keys. **Confirmed:** non-Latin topics/points can lose matching/deduplication identity; accented distinctions can also collapse. Public-boundary reproduction was attempted but blocked on missing `jinja2`, so this is source-confirmed, not a measured production loss.

**Luna implementation:** Prefer exact persisted section ID for structurally derived TOC briefs. Use Unicode normalization/casefold and Unicode letter/number preservation for fallback lexical matching/deduplication; do not transliterate every language into English. Scope English plural and `Gen AI` normalization so it cannot mutate other languages. Ambiguous normalized titles must not overwrite one another or silently attach the wrong section. Preserve display text/page identity and retain unknown mapping explicitly rather than borrowing an unrelated summary. Version the existing topic-mapping transformation and invalidate affected derived cache families only.

**Success criteria:** Russian/Greek/Chinese and accented Latin fixtures retain all distinct title/key-point text and correct original section IDs/pages. Canonically equivalent Unicode forms deduplicate correctly; genuinely different sections do not merge. English mapping fixtures remain unchanged; no provider calls are added.

**Validation:** `python -m pytest -q tests/test_artifact_generator.py tests/test_artifact_normalization.py tests/test_render_service_artifacts.py tests/test_report_regeneration_generator.py`; extend topic-brief fixtures with non-Latin, composed/decomposed accents, duplicate headings and explicit-ID ties. Check generated public topic text and deep links through the canonical render path, not private normalizer tests alone.

**Luna implementation prompt — ART-07 (copy/paste)**

```text
Implement ART-07 — Preserve multilingual topic meaning and section identity.
Objective: Deliver the verified behavior specified immediately above under canonical P17.
Source: docs/backlog/P-publication.md, technical slice ART-07.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update P17 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="art-08"></a>
#### ART-08 — Bind cover variation to semantic content, not execution telemetry

**Primary canonical owner:** [P17](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Scoped implementation reported; verify current HEAD.

**Priority / effort / dependencies:** P1 / S–M / none. **Backlog:** E7/P17 deterministic asset reuse extension.

**Status/evidence:** Implemented. The existing cover input already excludes `_cache`; regression coverage now compares full fingerprints, deterministic cover bytes, and manifest identity across differing timing/usage/reuse metadata. Render-only replay previously trusted manifest existence; it now checks the persisted projection against current content, source identity, governed region, and style hash, and verifies all three linked asset files before reuse. Full publish-readiness/provenance validation still runs independently. Actual rerender frequency is unmeasured; these covers are deterministic geometry, not necessarily extra generative-image calls.

**Luna implementation:** Keep the existing versioned cover fingerprint and `_cache` exclusion. Persist the cover-style SHA-256 with the report-card manifest and compare the full expected manifest projection before replay. Reuse only when semantic/content fingerprint, source fields, governed region, style, and all three contained asset files match. Keep full artifact/provenance hashes separately for audit/readiness; the cover fingerprint is not package-integrity proof. Older manifests without style identity regenerate once. Do not add another cache layer.

**Success criteria:** Altering only run/usage/reuse telemetry leaves fingerprint, seed and cover bytes unchanged; compatible warm replay performs zero cover render work. Changing source identity, semantic geometry, governed region or relevant style invalidates reuse and changes the appropriate asset identity. All three canonical card assets and final package checks remain required.

**Validation:** `python -m pytest -q tests/_test_report_render_generator tests/test_report_card_projection.py` — passed (29 tests); `python -m pytest -q -m integration tests/integration/test_cover_image_service.py` — passed (7 tests). The local regressions compare fingerprint, bytes, manifest equality, warm reuse, content/source/style/region invalidation, and missing linked assets. The integration renderer suite verifies canonical image output.

**Luna implementation prompt — ART-08 (copy/paste)**

```text
Implement ART-08 — Bind cover variation to semantic content, not execution telemetry.
Objective: Deliver the verified behavior specified immediately above under canonical P17.
Source: docs/backlog/P-publication.md, technical slice ART-08.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update P17 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="art-09"></a>
#### ART-09 — Generate a finite report composition plan instead of one fixed story

**Primary canonical owner:** [P17](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

**Priority / effort / dependencies:** P1 / L, four separately reviewable slices / ART-06 profile; P16 decision synthesis and E15/CROP accepted visuals before promoting adaptive modes. **Backlog:** bounded implementation of P17; P16 continues owning analytical decision logic.

**Evidence / diagnosis:** `templates/report.html.j2:92–114,302–468` uses fixed Overview→Findings→Signals→Evidence→Expert View→Taxonomy order. `src/services/_render_service/view.py:109–132,321–356` suppresses exact duplicate advisory text and builds distinct signals, but does not produce an explicit report-level purpose/order contract. `CONSOLIDATED_TODO.md:404–422` records this exact P17 gap. **Confirmed missing composition model; hypothesis:** a source-appropriate finite layout improves reading hierarchy and decision usefulness. Initial crop selection still precedes analysis; this proposal consumes accepted visual inventory later, rather than feeding unavailable analytical claims into selection.

**Luna implementation:** (1) Freeze current layouts/reading measures on P6 reports. (2) Add a versioned generator-owned `report_composition` with finite modes, module purpose, ordered artifact/theme IDs, approved visual links and omission decisions. Start deterministic eligibility; ambiguous cases use the current safe layout. (3) Render the plan in HTML and WordPress without synthesizing facts or creating arbitrary templates. (4) Enable modes individually only after review. Reuse P16 synthesis and E15-approved assets; do not add another synthesis/model call solely to choose layout.

**Success criteria:** Every displayed module has one declared purpose and valid approved inputs; all planned themes remain covered. Duplicate-equivalent public blocks fall at least 50% against the frozen baseline, with zero lost facts/qualifiers; ≥75% of blinded reviewer choices prefer candidate reading hierarchy. Legacy/ambiguous artifacts render safely. Media quality and publication approval remain unchanged.

**Validation:** `python -m pytest -q tests/test_render_service_artifacts.py tests/test_render_service_public_advisory.py tests/test_render_service_figure_linkage.py tests/test_wordpress_report_rendering_contract.py tests/test_public_report_quality_gate.py`; add survey/outlook/framework/concise/data-rich modes, no-approved-visual and legacy fixtures. Run P17 desktop/mobile human review on hash-bound final artifacts before activation.

**Luna implementation prompt — ART-09 (copy/paste)**

```text
Implement ART-09 — Generate a finite report composition plan instead of one fixed story.
Objective: Deliver the verified behavior specified immediately above under canonical P17.
Source: docs/backlog/P-publication.md, technical slice ART-09.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update P17 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="arch-b"></a>
#### ARCH-B — Rank and select a diverse evidence slate once in the editorial plan

**Primary canonical owner:** [P17](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1 / M / follow-up A and `ART-06`; extends the existing editorial plan, `P16` synthesis and `P17` composition without a second ranking service.
- **Evidence / diagnosis:** `_summary_prioritized_evidence_json()` currently reorders findings using the first editorial theme. `select_artifact_insights()` protects candidate facts and selects theme coverage, while `_insight_rank_key()` considers candidate scores within a theme; general fill still follows candidate order. There is no single authoritative, diversity-aware editorial slate for all output families.
- **Luna implementation:** After DocMap and evidence fidelity, have the existing editorial plan identify an evidence-linked principal thesis, ranked supporting candidates, independent themes, material counter-signals and a small reserve. Use semantic reasoning where report significance, commercial implications or novelty require it; use existing deterministic eligibility, duplicate detection and constraints where reliable. Keep factual support status separate from editorial rank. Select a non-redundant portfolio rather than blindly the top N scores; retain scope/methods/limitations as mandatory context. Preserve independent summary/insight generation parallelism unless an identical-cohort measurement justifies serialization.
- **Success criteria:** Selected items are supported, substantively distinct and collectively cover the important report themes, with counterevidence and qualifications preserved. Low-ranked but materially limiting facts cannot disappear. The same approved evidence priorities can be consumed by summary, insights, advisory, visual and distribution families without diverging factual selections.
- **Validation:** Compare selected evidence IDs, theme coverage, repeats and report-specific importance on the pinned five-report cohort and P6 human-review material; include one thin-evidence and one conflicting-evidence source. Inspect output, not only scores, and prohibit unsupported priority boosts.

**Luna implementation prompt — ARCH-B (copy/paste)**

```text
Implement ARCH-B — Rank and select a diverse evidence slate once in the editorial plan.
Objective: Deliver the verified behavior specified immediately above under canonical P17.
Source: docs/backlog/P-publication.md, technical slice ARCH-B.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update P17 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
<a id="arch-f"></a>
#### ARCH-F — Reuse priorities for metrics, quotes, visuals and distribution hooks

**Primary canonical owner:** [P17](../../CONSOLIDATED_TODO.md). **Proposal disposition:** Proposal; revalidate at current HEAD.

- **Priority / effort / dependencies:** P1/P2 / M / follow-ups A/B and `E15`; extends `CROP-03`, `ART-05`, `P16` and `P17` rather than replacing their selectors.
- **Evidence / diagnosis:** `_select_key_figure_metrics()` already ranks and filters evidence-linked quantities for usefulness, numeric support and redundancy; it should remain authoritative for display correctness. Quotes have a verified small-pool deterministic path and a model path for ambiguous/larger pools. Visual candidates and cover/LinkedIn copy are selected in distinct paths and can disagree with the report's principal evidence priorities.
- **Luna implementation:** Pass selected-slate priorities and exact qualifiers to the existing Key Figure, quote, chart/table, cover and LinkedIn selection boundaries. Rank quotes by meaning, speaker/attribution support, non-duplication and relevance; never manufacture or paraphrase a purported exact quote. Rank visuals by incremental evidence value and legibility, not aesthetic appeal alone, then retain all E15 semantic-crop and final-DPI gates. Choose one defensible primary cover/social hook; keep secondary themes where genuinely distinct. Existing rendering/projection stays deterministic.
- **Success criteria:** Highlighted figures, accepted visuals, quotations, cover and social claims reinforce the report's principal findings without unsupported relationship, quote-attribution or scope changes. Lower-ranked eligible assets remain available; an unsafe crop cannot be promoted because its underlying finding ranks highly. No new provider call solely to re-rank an already obvious small quote pool.
- **Validation:** Compare selected IDs and public surfaces across a fixed source cohort; include duplicate quotations, competing charts and misleading visual/caption fixtures. Exercise CROP/E15 semantic acceptance independently of editorial priority and record selection/provider-cost deltas.

**Luna implementation prompt — ARCH-F (copy/paste)**

```text
Implement ARCH-F — Reuse priorities for metrics, quotes, visuals and distribution hooks.
Objective: Deliver the verified behavior specified immediately above under canonical P17.
Source: docs/backlog/P-publication.md, technical slice ARCH-F.
Constraints: Read AGENTS.md and the owning code, contracts, tests and source evidence.
Confirm the diagnosis still exists at current HEAD; if already fixed, only verify and reconcile.
Reuse existing services and validator/orchestration boundaries; avoid duplication and scope creep.
Meet this slice's explicit success/acceptance criteria without relaxing source or release safeguards.
Verification: Run the listed focused tests plus affected downstream/real-report checks
where the specification calls for them. Inspect actual outcomes and document any unrun gates.
Update P17 and proposal disposition only with verifiable SHA/cohort/test evidence.
Commit and push the smallest proven change.
```
 
---
