# Consolidated TODO

Last audited: 2026-09-05
Audit basis: repository `main` product implementation at `28ad708f3bc3badf568c5f8e31f8c9d94df52775`, current WordPress theme/plugin code, retained hosted-site evidence, and a targeted crop-path review against current `main` at `1aa50412a863ef1891f14f1b81f72a4230353aed`. Hosted-only completion criteria remain open unless a current deployed smoke/readback proves them; the temporary HTTP sandbox is not treated as a production-hosting defect.

This is the repository's single, source-neutral work register. Every canonical task ID appears once in the Unified Work Register. Historical evidence may explain a closure, but it must not redefine current status.

## How to Use This Backlog

- The Unified Work Register is the canonical status source. Every `Active` row must have one matching detailed section in **Active Backlog** with a baseline, target behaviour, ordered implementation work, and acceptance criteria.
- `Deferred`, `Closed`, and `Excluded` items remain visible in the register but do not need active execution detail.
- Activate work only when the outcome and completion evidence are clear enough to execute. A separate issue/plan, named owner, target date, or review date is optional unless the work itself requires one; do not create process records solely to satisfy the backlog.
- One item owns one outcome. Merge overlapping requests into the existing owner rather than creating parallel tasks.
- Every implementation follows `AGENTS.md`: preserve role boundaries, use typed contracts, avoid placeholders/private-helper patching, and verify behavior at the real boundary.
- Quantitative current-state claims must cite or name retained evidence with an exact producer SHA/date when they are used for release or closure decisions.
- Close an item only when every stated acceptance criterion is met. Keep closure evidence concise here and retain detailed artifacts in `docs/quality/`, `docs/CTO_evidence/`, release evidence, or git history.

| Priority | Execution lane | Goal |
| --- | --- | --- |
| 1 | Autonomous safety and cost control | Make unattended runs inspectable, bounded, and recoverable. |
| 2 | Public trust and publishing | Make the public site accurate, safe, responsive, and ready for operator review. |
| 3 | Evidence quality and reuse | Turn retained evidence, embeddings, lineage, and crop QA into measurable decisions. |
| 4 | Release integrity | Make release evidence and architecture enforcement visible and reliable. |
| 5 | Boundary simplification | Reduce real control-plane and service complexity without behavior drift. |

## Unified Work Register

| Status | ID | Work item | Current outcome / merge target |
| --- | --- | --- | --- |
| Closed | A1 | Single autonomous supervisor, read-only `PipelinePlan`, and mandatory workflow-control authority | Plan authorization is enforced by CLI/UI control payloads; retained plan run and regression evidence passed. |
| Closed | A2 | Configured run profiles | Seven typed profiles resolve identically through plan, CLI, and UI. |
| Closed | A3 | Workflow-wide remediation-ledger rollout | The 31-workflow coverage matrix, bounded fail-closed reaper, read-only soak, and strict retained evidence passed. |
| Closed | A4 | Quarantine irreparably malformed Drive PDFs | `pdf-integrity-v1`, durable quarantine, and retained-file revalidation are implemented. |
| Closed | A5 | Terminal blocker and avoided-browser-spend route policy | Proven terminal blockers stop unnecessary browser escalation and retain avoided-work evidence. |
| Closed | A6 | Budget-manager closeout and operational proof | Live governed Drive/vector/LLM calls recorded actual use and subsequent calls were stopped before provider I/O at budget limits. |
| Closed | A7 | Budget-aware model routing, compaction, and failure-class fallback | Explicit route policy, anchor-preserving compaction, same-provider fallback, and retained-corpus gates are implemented. |
| Active | A8 | Compare retained model-call replay bundles | Build a deterministic, zero-provider comparison outcome for retained replay bundles. |
| Closed | A9 | Canonical report-source identity and publication provenance | Immutable source observations, deterministic resolution, safe projection, and render-only invalidation are implemented. |
| Closed | A10 | Budget-deferred-work recovery and operator requeue | Three proof-bound recovery adapters are enabled; unsupported work remains held. |
| Closed | A11 | Ledger-driven recurring-failure prevention and operator prioritization | Deterministic remediation-opportunity grouping exists and unregistered execution remains held. |
| Closed | A12 | Complete configured model-pricing coverage for spend budgets | Versioned approved pricing, cached-input billing, attribution, and hold-before-I/O behavior are implemented. |
| Closed | A13 | Former recovery/backlog source item | Historical recovery ownership was merged into A10; backlog-source integrity is enforced separately by CI tests. |
| Closed | A14 | Build retained route-economics calibration and proposal tooling | Read-only compatible-cohort route economics and thresholded operator proposals/abstentions are implemented; A19 owns mechanism-level telemetry improvements. |
| Active | A15 | Complete explicit model-policy coverage and policy-effectiveness evidence | Retire remaining compatibility fallback and retain decision-useful compatible evidence. |
| Closed | A16 | Durable corpus rehabilitation campaign execution | Review-gated retained-evidence campaigns enqueue idempotent repair work without public writes. |
| Active | A17 | Calibrate deterministic admission thresholds from retained preflight funnels | Produce read-only compatible-cohort threshold proposals without automatic admission changes. |
| Active | A18 | Harden discovery recall and authoritative acquisition handoff | Establish ground-truth recall, reversible candidate state, executable recovery, and a lossless authoritative qualification handoff. |
| Active | A19 | Harden acquisition routes, terminal semantics, and artifact verification | Make every route converge on consistent verified-artifact semantics, correct mailbox/onsite state, bounded recovery, and mechanism-level economics. |
| Closed | P0 | Public editorial remediation and sandbox end-to-end baseline | The baseline remediation/publish path was proven on a bounded sandbox cohort; successor public outcomes are owned by P2-P10/P12-P15. |
| Closed | P1 | Publish snapshot naming and synchronous idempotent publishing | Public/UI terminology uses Publish Readiness; synchronous review-gated idempotent publishing is preserved. |
| Active | P2 | Harden bounded WordPress public-observability events | Define and enforce a bounded/redacted PHP event contract for intake and public-render boundaries; R6 owns aggregate reduction telemetry. |
| Deferred | P3 | Production HTTPS and canonical transport | Activate with production-host migration. Current sandbox HTTP is intentional; do not spend MVP effort retrofitting temporary hosting. |
| Active | P4 | Close public briefing, correction, and submission intake | WordPress-native intake exists; close with P2-compliant events and current hosted smoke of validation, persistence, and confirmation. |
| Active | P5 | Validate and close responsive search and navigation | Mobile navigation/search/filter implementation exists; remaining work is hosted visual/accessibility verification and regression evidence. |
| Active | P6 | Complete blind human editorial acceptance | Automated readiness is implemented; close against the retained multi-batch human-review protocol rather than a superseded 30×3 rubric. |
| Active | P7 | Fix public performance measurement and reach hosted targets | Correct the measurement contract first, then optimize against explicit targets without metadata/content regression. |
| Active | P8 | Complete concise public evidence, methodology, and related-content surfaces | Public evidence/discovery outcome. |
| Closed | P9 | Retained public-advisory benchmark | Saved baseline comparison and grounded repair proposal/abstention output are implemented. |
| Active | P10 | Operate correlated public-render failure telemetry | Hosted aggregation/alerting outcome; safe render boundary itself is implemented. |
| Closed | P11 | Establish verified acquisition-to-ingest file/identity handoff | Canonical retained-file, MD5, source-identity, and idempotent ingest handoff were proven; A19 owns stronger cross-route structural artifact acceptance. |
| Closed | P12 | Release-locked sandbox publish canary | Exact-HEAD isolated three-report cohort published with authenticated readback and zero-write replay. |
| Closed | P13 | Make WordPress file-ID lookup independently authoritative | Authenticated immutable file-ID lookup reuses matching posts, fails closed on ambiguity, and preserves no-write reuse. |
| Closed | P14 | Retain isolated live proof of strict cohort-manifest publication binding | The isolated cohort bound only admitted members and replayed with no WordPress writes. |
| Closed | P15 | Operate canonical publish-readiness telemetry and refresh planning | Typed deterministic refresh plans route only proven minimum recovery work. |
| Closed | E1 | Claim-embedding freshness, retention, and cost controls | Due-work selection, leases, budgets/retries, health telemetry, and live bounded embedding proof are implemented. |
| Closed | E2 | Retained-artifact benchmark | Briefing/Signal prompt-token deltas, overlap/source coverage, and no-vector fallback are measured. |
| Closed | E3 | Lineage-driven minimum regeneration | Deterministic minimum regeneration authority and render-only enforcement are implemented. |
| Closed | E4 | Executable retained PDF benchmark corpus in CI | Retained corpus is hash-pinned and CI-gated. |
| Closed | E5 | Crop-QA scorecards and selection telemetry | Retained crop-QA sidecars support operator-only quality/clipping/storage scorecards. |
| Active | E6 | Retain a hash-pinned claim-embedding benchmark export | Persist approved vectors for reproducible zero-provider semantic benchmarking. |
| Closed | E7 | Planner-enforced artifact-family reuse | Retained render/crop/checkpoint/publication reuse is planner-enforced with plan/actual reconciliation. |
| Closed | E8 | Use canonical source identity to suppress duplicate research work | Exact identity/content-hash package reuse is implemented with retained evidence. |
| Closed | E9 | Materialize prompt-family outputs and route only required model calls | Primary model families use fail-closed pre-call provenance reuse. |
| Active | E10 | Attest active model-pricing rates before they become stale | Keep cost attribution and spend enforcement trustworthy as provider pricing changes. |
| Closed | E11 | Measure and optimize structured-output recovery effectiveness | Fresh isolated cohort retained 100% first-pass structured validity with zero repair cost/tokens while downstream gates remained active. |
| Active | E12 | Persist pre-category editorial context checkpoints | Extend typed recovery to genuinely category-only retries. |
| Active | E13 | Measure candidate-regeneration promotion effectiveness | Compare compatible candidate cohorts and reduce repeated unsuccessful repair spend. |
| Active | E14 | Calibrate category-fit coverage from retained outcomes | Turn retained category-fit decisions into grounded mapping/prompt proposals. |
| Active | E15 | Make publication crops visually complete and repairable | Replace shrink-biased crop refinement/QA with completeness-first localization, directional bbox repair, and human-grounded production evidence. |
| Active | R1 | Publish release-evidence reviews where reviewers work | Link exact-tested-HEAD evidence/approval to the PR/release surface and declare runtime-corpus representativeness. |
| Active | R2 | Enforce role boundaries, direct-I/O discipline, and controlled module growth | Close targeted boundary-coverage and expiring-waiver gaps without generic governance noise. |
| Active | R3 | Restore service quality coverage above the retained baseline | Add behavior-focused service coverage and refresh the baseline only from a passing exact-commit run. |
| Closed | R4 | Publication usage/projection reconciliation guard | Missing/invalid/materially lagged usage/projection evidence stops public writes without rebuilding. |
| Closed | R5 | Hash-verified dependency lock artifacts | Native Ubuntu CPython 3.12 wheelhouse and offline hash-locked install are verified. |
| Active | R6 | Review bounded-log reduction telemetry and remediate recurring callers | Aggregate reduction attempts and convert recurring oversized callers into bounded remediation. |
| Closed | S1 | Canonical service-boundary audit | CI-enforced service-boundary audit preserves approved external-effect ownership. |
| Closed | S2 | Publish/ingest facade audit | CI-enforced facade/decomposition coverage preserves routing, retries, state, and external-effect contracts. |
| Active | S3 | Simplify the PDF visual-heuristics boundary | Only address measured remaining coupling behind the canonical PDF boundary. |
| Active | S4 | Give WordPress shortcodes semantic ownership | Split the catch-all shortcode owner into coherent feature families without output/hook changes. |
| Deferred | D1 | Full report-generation DAG scheduler | Revisit only if profiling shows material idle dependency time beyond simple parallelism. |
| Deferred | D2 | Streaming Drive prefetch queue and worker-safe PDF context pooling | Revisit if batches materially wait on Drive while workers are idle. |
| Deferred | D3 | Adaptive concurrency and route-specific worker buffers | Revisit on sustained throttling, SQLite contention, or browser saturation. |
| Deferred | D4 | Multi-provider failover | Revisit when outage volume or an SLA justifies the complexity. |
| Deferred | D5 | Same-publisher warm workers/session reuse | Revisit when same-publisher volume justifies session-isolation risk. |
| Deferred | D6 | Arbitrary generic DAG or due-work scheduler | Typed durable workflow queues own current work; keep a user-configurable generic scheduler deferred. |
| Closed | D7 | Complete queue-backed publication coverage and live recovery proof | Critical publication queues have canonical handlers and retained controlled live evidence. |
| Deferred | D8 | LinkedIn persona variants and comparative positioning | Revisit when an active distribution workflow measures their value. |
| Deferred | D9 | Golden-output prompt evaluation and broader prompt-family scoring | Revisit only when current fixtures fail to detect a measured quality regression. |
| Deferred | D10 | Browser executor/static-DOM/prompt-payload/route-playbook tuning | Revisit only from a measured acquisition gap; A18/A19 own current correctness work. |
| Deferred | D11 | Root pre-commit, declarative quality-gate manifest, stricter mypy/Ruff, and hygiene scorecards | Revisit when current CI evidence proves a specific enforcement gap. |
| Deferred | D12 | Governed staging WordPress publish/projection canary | Revisit when a non-public staging site and named human approver are available. |
| Closed | C1 | Cached-provider accounting reconciliation corpus | Real provider-hit and tamper-rejection fixtures are in the CI accounting path. |
| Closed | C2 | Bounded multimodal crop-QA escalation | Typed escalation generator and deterministic no-model default are implemented/tested. |
| Closed | C3 | Lazy model construction, ranking/crop shortcuts, prefetch, and route prompt improvements | Landed behind existing boundaries with retained regression evidence. |
| Closed | C4 | Capability maps and autonomous release/remediation summaries | Generated capability maps and autonomous smoke evidence exist. |
| Closed | C5 | Prompt partials/schema snippets and prompt fixture regression | Dry-run and corpus validation are implemented. |
| Closed | C6 | Establish baseline discovery/mailbox/signal/embedding persistence paths | Durable baseline paths exist; A18/A19 own discovery/acquisition correctness hardening rather than reopening this capability milestone. |
| Closed | C7 | Logging content-exposure controls | Python structured logging is bounded/redacted; P2 owns WordPress public-boundary events and R6 owns reduction telemetry. |
| Closed | C8 | CTO evidence-collector integrity | Snapshot, exact-HEAD, provenance, consistency, and inventory validation are implemented; R1 owns reviewer-surface/runtime-corpus expansion. |
| Excluded | X1 | Draft HTML published before enrichment | Public progressive enrichment is not permitted. |
| Excluded | X2 | Automatic lower private-API promotion thresholds | Conservative thresholds remain mandatory. |
| Excluded | X3 | Invented acquisition-form identity facts or public pipeline diagnostics | Map only verified identity facts; diagnostics remain operator-only. |

## Active Backlog

The register currently contains **24 Active outcomes**. Every item below is implementation-ready and uses the same four-part contract: **Baseline**, **Target behaviour**, **What to implement, in order**, and **Acceptance criteria**.

### 1. Autonomous Safety and Cost Control

#### A8. Compare retained model-call replay bundles

- **Baseline:** Model-call replay bundles are retained and contain enough deterministic provenance to inspect prompt, contract, evidence, policy, validation, and output changes, but comparison is manual. Reviewers must inspect several files/logs and there is no canonical zero-provider diff or regression disposition.
- **Target behaviour:** A read-only comparison command accepts two compatible replay bundles and deterministically explains whether they are equivalent, compatible-but-changed, incomplete, malformed, or materially regressed. It never calls a provider and never emits retained prompt/source/model-output content.
- **What to implement, in order:**
  1. Define one typed comparison request/response contract around baseline bundle, candidate bundle, artifact family, and optional compatibility expectations.
  2. Canonically extract safe comparison fields: schema/contract version, prompt namespace/hash, policy/model identity, selected evidence IDs/hashes, validation disposition, output hash, usage/cost metadata, and retained-artifact identities.
  3. Implement deterministic field-level classification for equivalent, expected-compatible change, material regression, missing evidence, and malformed bundle cases; bound the output and preserve stable ordering.
  4. Add a CLI/operator surface that prints the summary and references retained artifacts without provider construction or external writes.
  5. Add fixtures from real retained bundles and document the command in the existing recovery/evidence workflow rather than creating another evidence system.
- **Acceptance criteria:**
  - Equivalent bundles produce an identical deterministic result across repeated runs and no false regression.
  - Changed prompt/policy/evidence/schema/output cases identify the exact changed safe fields and artifact family without printing prompt, source, or model-response text.
  - Missing and malformed bundles fail with typed bounded diagnostics rather than partial success.
  - Tests cover equivalent, changed, missing, malformed, and deterministic-order cases and prove zero provider calls/external writes by default.

#### A15. Complete explicit model-policy coverage and policy-effectiveness evidence

- **Baseline:** Startup resolves the finite production prompt/model namespace inventory and unknown reachable namespaces fail before provider I/O. `policy-effectiveness` already groups compatible ledger evidence, but some reachable routes still rely on a compatibility adapter and retained compatible evidence is insufficient for decision-useful cost/quality conclusions across all production namespaces.
- **Target behaviour:** Every reachable production model call resolves through one explicit versioned policy with no compatibility fallback. Operators can compare compatible policy cohorts for calls, validity, reuse, latency, tokens, cost, and validated-output quality without changing routing automatically.
- **What to implement, in order:**
  1. Enumerate all reachable production provider call sites/namespaces from code/config and reconcile them against the canonical policy registry; separate unreachable/test-only namespaces.
  2. Replace each remaining compatibility-adapter path with an explicit registered policy while preserving the existing provider, model, timeout, retrieval, structured-output, retry, and cache semantics.
  3. Make startup/preflight fail closed if a reachable namespace lacks a complete explicit policy and retain the resolved policy identity/hash in execution provenance.
  4. Complete `policy-effectiveness` coverage so compatible cohorts expose provider calls, validated-output rate, cache reuse, elapsed time, input/cached/output tokens, and attributed cost without retaining prompts/sources/outputs.
  5. Run retained-corpus and bounded live evidence for representative high-cost namespaces; produce operator-reviewable no-change/recommendation conclusions only when compatibility/sample requirements are met.
- **Acceptance criteria:**
  - No reachable production namespace uses the compatibility adapter; an intentionally unregistered reachable namespace fails before provider construction/I/O.
  - Policy hashes invalidate incompatible cache/replay reuse while preserving valid compatible reuse.
  - Retained and bounded live checks cover all production policy families and show complete bounded effectiveness fields or explicit `insufficient_evidence`/unknown states.
  - No command automatically changes model/provider/policy from effectiveness results; existing semantic/output contracts and retry ownership remain unchanged.

#### A17. Calibrate deterministic admission thresholds from retained preflight funnels

- **Baseline:** Versioned admission decisions retain source size/page/text, duplicate, evidence-potential, budget forecast, configuration/policy/runtime identity, decision reason, and downstream outcome metadata. Operators can see individual rejections, but there is no compatible-cohort calibration view showing whether current thresholds save cost without discarding viable reports.
- **Target behaviour:** A read-only calibration surface compares only compatible admission cohorts, quantifies cost/work avoided versus downstream completion/validation quality, and emits threshold proposals only when minimum sample/confidence/improvement gates are met. It never mutates admission policy.
- **What to implement, in order:**
  1. Define the compatibility key for admission cohorts from preflight/policy/configuration/runtime decision hashes and exclude incompatible versions deterministically.
  2. Build a read-only funnel report for each threshold family: native-text, page/size limits, evidence-potential, duplicate/quarantine and related deterministic rejection reasons.
  3. Join bounded downstream outcomes to admitted cases so the report can show completion/validation rates and provider/vector/model work actually incurred or avoided.
  4. Add counterfactual threshold proposal logic with configured minimum sample, confidence, and material-improvement gates; report an impact range and abstain on weak/noisy evidence.
  5. Add CLI/tests and one bounded retained/live replay proving the report is deterministic and side-effect free.
- **Acceptance criteria:**
  - Incompatible decision versions never enter the same cohort or proposal.
  - The report exposes denominator, admitted/rejected outcomes, downstream completion/validation, and avoided provider/vector work using bounded metadata only.
  - Threshold proposals include exact compatible decision hashes, sample/confidence evidence, and counterfactual impact; insufficient evidence produces an explicit no-change result.
  - Tests prove deterministic ordering and zero model/vector/external writes; no threshold/configuration is modified automatically.

#### A18. Harden discovery recall and authoritative acquisition handoff

- **Baseline:** Discovery has route memory, candidate screening, landing verification, coverage regression checks, and recovery records, but several early decisions are irreversible. HTTP confidence and deterministic screening can discard plausible reports before semantic qualification; raw observation also drives delta suppression, so a false negative can become permanently “seen.” Recovery can be persisted as `scheduled` without an authoritative executed second pass. The durable discovery→acquisition queue loses candidate PDF/source-page/provenance/route evidence, and acquisition can reclassify an already-qualified report. Production audits measure only discovered candidates, not recall against known publisher inventory.
- **Target behaviour:** Discovery is high-recall, reversible, and the single authority for report qualification. Acquisition receives the complete typed qualification context and decides *how* to obtain the report rather than independently re-deciding *whether* it is a report. First-run completeness and deferred recovery are explicit and executable.
- **What to implement, in order:**
  1. Retain a hash-pinned gold corpus of roughly 15–20 representative publishers and known report URLs spanning static, pagination, JS-hydrated, mixed-content, gated, multilingual, direct-PDF, and external/microsite cases; score recall and precision independently of production discovery.
  2. Convert the HTTP `0.60` confidence cutoff to ranking/triage for plausible candidates; reserve deterministic hard rejection for indisputable junk. Treat English keywords, multilingual evidence, and same-domain status as features rather than eligibility requirements.
  3. Separate observation from decision state with lifecycle (`observed`, `screened`, `qualified`, `acquisition_attempted`, `acquired`), decision/policy hashes, reason/confidence/time, and deterministic re-screen conditions.
  4. Route typed deferred-recovery recipes through the existing durable queue/remediation boundary with bounded attempts/idempotent terminal states, or remove `scheduled` terminology where no executor exists.
  5. Introduce one lossless typed qualified acquisition context carrying canonical URL/title, candidate PDF URL, source-page URLs, discovery provenance/confidence, route recommendation, and qualification/policy identity through the durable queue.
  6. Bypass the ad-hoc report-likelihood readiness classifier for discovery-qualified candidates; keep it only for direct/ad-hoc URLs that did not pass discovery.
  7. Require bounded first-run completeness proof (terminal pagination, declared total/structured source agreement, sitemap/archive corroboration, or one verification browser pass) before the first snapshot becomes authoritative.
- **Acceptance criteria:**
  - Fixed gold corpus reaches at least **97% report recall** with no material precision regression from the retained baseline; recall and precision are reported separately.
  - Mixed accepted/rejected delta fixtures prove a false negative remains eligible for later re-screening, and policy-hash changes can reconsider prior decisions without a new URL observation.
  - Plausible multilingual/external-host/report-detail cases are not hard-dropped solely for missing English tokens/domain equality; obvious junk stays deterministic/no-model.
  - At least one retained deferred-recovery case executes through the canonical durable path to `recovered|failed|held` with bounded attempts and idempotent replay.
  - The production worker receives the same candidate PDF/source-page/provenance/route evidence available to direct/audit execution.
  - Discovery-qualified candidates reach route planning without a second report-likelihood rejection; direct/ad-hoc URLs retain the fail-closed readiness guard.
  - First-run snapshots cannot become long-lived baselines without an explicit completeness proof.

#### A19. Harden acquisition routes, terminal semantics, and artifact verification

- **Baseline:** Acquisition has a strong cheap-to-expensive ladder—cache, deterministic HTTP/PDF extraction, private APIs/specialists, deterministic browser playbooks, rendered preflight, then Browser Use—but route contracts are inconsistent. `email_required` can trigger mailbox polling, the request watermark can be lost, static timeout can masquerade as gate evidence, and onsite HTML/Markdown can be marked successful although canonical ingest is PDF-only. PDF verification differs across HTTP/browser/mail/cache, apparent `.pdf` URLs can be denied browser recovery, mailbox ZIP/link behavior is over-broad, route analytics collapse distinct mechanisms, cache freshness is weak for mutable URLs, and durable archive failure can conflict with local acquisition success.
- **Target behaviour:** Every acquisition mechanism converges on one ingest-compatible structurally verified artifact definition with truthful terminal states, bounded resource use, and mechanism-level economics. Cheap deterministic paths remain first; Browser Use stays a last resort.
- **What to implement, in order:**
  1. Correct terminal/mail semantics: only verified `email_requested` may enqueue mailbox work; `email_required` is identity/configuration hold. Carry verified form-submission timing/request identity into mailbox payloads. Split broad access blockers into rate-limit/transient, JS/WAF challenge, CAPTCHA, authentication, forbidden/access-blocked, and terminal not-found classes.
  2. Reuse the canonical `pdf-integrity-v1` structural checks before success, route-memory promotion, cache population, durable archive completion, or ingest handoff for HTTP, browser, mailbox/ZIP, cache, private-API and specialist PDF outputs. Distinguish `artifact_verified_locally`, `artifact_archived`, and `acquisition_complete`.
  3. Harden HTTP/cache without making them browser-first: permit one evidence-triggered browser recovery when an apparent direct PDF proves to be HTML/WAF/viewer content; rank embedded/opaque/extensionless PDF candidates from explicit candidate evidence, DOM/CTA relation, MIME/response evidence and source relation before lexical hints; revalidate mutable cache entries with available ETag/Last-Modified/final URL/content-length/version evidence.
  4. Gate browser side effects: automatic pre-LLM form submission runs only for `browser_email_form` or strong proven report-delivery form evidence; generic PDF-click pages cannot submit newsletter/contact/demo forms. Keep deterministic playbooks/private APIs ahead of Browser Use where eligible; use a generic acquisition prompt when route family is genuinely uncertain.
  5. Make listing-hub recovery exceptional/self-healing by persisting the resolved canonical detail/download target back to source/discovery state for the next run.
  6. Unify onsite/specialist completeness: one evaluator for direct HTTP/browser capture; truncated content is never complete; HTML/Markdown remain support artifacts while ingest is PDF-only; Adobe text-only output is labelled explicitly; Issuu retains all-declared-pages verification with bounded concurrency/disk streaming.
  7. Make mailbox acquisition metadata-first and bounded: rank sender/subject/timestamp/body snippet/attachment metadata/anchor text before materialization; share affinity scoring for links and attachments; bound ZIP member count/single+total decompressed bytes/compression ratio/PDF count; suppress by message+exact normalized URL+failure class; continue through bounded lower-ranked candidates after candidate-specific failures; improve IMAP filtering/windowing.
  8. Persist mechanism-level accounting (`planned_route_family`, `resolution_method`, route kind/outcome/status, browser/Agent/mailbox usage, latency, resource counts, cost) and feed it into A14 rather than creating a parallel policy system.
  9. Reserve/finalize budgets for actual HTTP/browser/model/form/mailbox/PDF/Drive operations instead of a generic PDF-processing reservation for every attempt.
- **Acceptance criteria:**
  - `email_required` never polls; `email_requested` always carries verified submission timing and an older matching email cannot satisfy a newer request.
  - Static HTTP timeout cannot alone produce email-required/requested terminal evidence.
  - One shared structural verifier rejects malformed/truncated pseudo-PDFs consistently on every acquisition path before success is learned.
  - Onsite terminal success produces a structurally verified PDF while ingest remains PDF-only and records publisher-supplied versus rendered capture.
  - Apparent `.pdf` HTML/WAF/viewer wrappers get at most one bounded browser recovery; genuine PDFs complete without browser launch.
  - Opaque/extensionless valid PDF fixtures can succeed from DOM/MIME/candidate evidence without title tokens; probing remains bounded.
  - Pre-LLM automation cannot submit unrelated lead/newsletter/contact forms on a PDF-click route.
  - Listing-hub success repairs the future acquisition target so the next run does not repeat listing discovery.
  - Truncated onsite content is never complete; Adobe/Issuu semantics are explicit and memory/concurrency bounded.
  - Mailbox fixtures prove irrelevant messages do not materialize attachments, ZIP bombs are bounded, one failed same-host link does not suppress a valid sibling, and a retryable top candidate does not block a bounded valid lower-ranked candidate.
  - Route economics distinguish the actual resolution mechanisms and contain the resource/cost/latency fields required by A14.
  - Mutable cache freshness changes invalidate reuse; immutable/versioned sources retain cheap reuse.
  - Required archive failure leaves a recoverable pre-completion state and converges idempotently after storage recovers.
  - Route-specific budget tests prove operations are blocked only by the limits for side effects actually attempted.

### 2. Public Trust and Publishing

#### P2. Harden bounded WordPress public-observability events

- **Baseline:** Python structured logging has deterministic size/redaction controls, but WordPress intake and public-render boundaries build PHP event payloads directly and write JSON through `error_log`. Public render failures can include private exception details in operator logs, and the PHP boundary does not yet share an explicit maximum-size/redaction contract with intake.
- **Target behaviour:** All WordPress public-boundary events use one small PHP-local contract that preserves correlation/outcome/route/entity metadata while deterministically excluding public submission text and bounding private diagnostics. Public responses never expose diagnostic content; R6 receives only bounded reduction metadata.
- **What to implement, in order:**
  1. Define the allowed WordPress public-event schema, maximum serialized size, permitted scalar fields, diagnostic/private-field policy, and deterministic reduction behavior.
  2. Implement one shared PHP helper/boundary for serialization, redaction, bounding, correlation IDs, and reduction metadata; do not introduce a second external logging store.
  3. Migrate public intake success/failure and public-render failure events to the shared contract while preserving existing hooks/correlation IDs and visitor responses.
  4. Ensure exception message/path/trace data is either bounded in private-only diagnostics or reduced to safe typed metadata; never include user-submitted body/free text in standard events.
  5. Add PHP/runtime tests with maximum-size submissions and exception-like inputs and expose only aggregate reduction signals to R6.
- **Acceptance criteria:**
  - Representative maximum-size intake and render events remain at/below the canonical WordPress event byte limit.
  - Correlation ID, route/entity type, outcome/error class and reduction indicator survive deterministic reduction.
  - User submission text, credentials, filesystem paths, stack traces, and discarded raw values are absent from public responses and bounded standard-event artifacts.
  - Existing WordPress action hooks and public safe-error/intake behavior remain compatible.
  - Tests prove deterministic output and that R6 can aggregate reduction metadata without reconstructing discarded content.

#### P4. Close public briefing, correction, and submission intake

- **Baseline:** `Request a briefing`, `Send a correction`, and source/report submission flows already exist in WordPress and use nonce/honeypot/validation with private persistence. Remaining gaps are a single P2-compliant event contract and current deployed evidence that the live routes, validation, persistence, and confirmation/error behavior work end to end.
- **Target behaviour:** Each public CTA captures only necessary documented fields, rejects invalid/spam input safely, persists an operator-usable private record, emits bounded/redacted observability, and returns a clear success/error state on the deployed site.
- **What to implement, in order:**
  1. Reconcile all three intake flows against one documented field contract; remove unused/duplicate fields and keep only information required to action the request.
  2. Route intake observability through P2's shared bounded WordPress event boundary without moving intelligence generation into WordPress.
  3. Verify persistence/delivery ownership, idempotency/duplicate behavior where applicable, and operator visibility of the private record.
  4. Add/retain focused tests for nonce, validation, empty values, honeypot/spam, persistence failure, and confirmation/error rendering.
  5. Run a current hosted smoke through every CTA on the deployed sandbox/site and retain route, outcome, record/readback evidence without retaining submitted personal text.
- **Acceptance criteria:**
  - Every CTA reaches the correct form/action and collects only its documented necessary fields.
  - Empty/invalid/honeypot submissions create no actionable record and return safe deterministic feedback.
  - Valid submissions create exactly the expected private record/delivery outcome and show a clear confirmation state.
  - Events satisfy P2's byte/redaction contract and contain no submission body/free text.
  - Current hosted smoke proves all three routes and failure/success states; only then can P4 close.

#### P5. Validate and close responsive search and navigation

- **Baseline:** The theme/plugin already implement mobile navigation, header search, archive search/filter controls, responsive CSS, and prior local Playwright checks. Earlier visual observations included overflow/clipping/cramped controls and mobile-navigation concerns, but the task description had become stale because the implementation now exists. Current hosted multi-viewport visual/accessibility proof is incomplete.
- **Target behaviour:** Navigation, search, filters, and primary discovery flows are visually stable and keyboard accessible at phone, tablet, and desktop widths on all key public surfaces without changing archive/search query semantics.
- **What to implement, in order:**
  1. Define a deterministic route/viewport smoke matrix covering homepage, search, reports archive, report detail, publisher/category where applicable, contact, and submit at representative phone/tablet/desktop widths.
  2. Run current screenshots and DOM accessibility checks to identify only real remaining defects: horizontal overflow, clipping, overlap, unreadable/truncated controls, awkward hero stacking, or stray artifacts.
  3. Fix theme/plugin CSS/markup minimally, preserving query parameters, WordPress hooks, projection data, and desktop behavior.
  4. Verify mobile navigation open/close, Escape/click-close, focus visibility/order/return, backdrop/panel semantics, and search/filter keyboard operation.
  5. Retain visual-smoke screenshots plus automated no-overflow/broken-image/accessibility assertions as regression evidence.
- **Acceptance criteria:**
  - No horizontal overflow, clipped text, overlap, hidden essential control, or visible broken image on the defined route/viewport matrix.
  - Mobile navigation opens/closes intentionally, remains keyboard operable, exposes visible focus, and returns focus appropriately; no off-canvas control remains keyboard-trapped when closed.
  - Search/filter submissions preserve current GET/query semantics and return the expected archive/search state.
  - Phone/tablet/desktop screenshots are retained and automated checks fail known overflow/clipping regressions.
  - No public content/projection contract changes are introduced solely for responsive styling.

#### P6. Complete blind human editorial acceptance

- **Baseline:** `publish_readiness.json` and automated semantic/grounding/editorial checks are strong and already protect final HTML/WordPress projections. Human review is being run in representative five-report batches with a 10-point editorial scoring matrix, but the retained review program is incomplete and older TODO language specified a different 30×3 protocol that does not match the actual evidence process.
- **Target behaviour:** A fixed, representative, retained human-review program gives an explicit publishability decision and quantitative editorial scores for 15 reports, using one stable rubric and reviewer attribution. Automated gates remain necessary but are not used as a substitute for human quality judgment.
- **What to implement, in order:**
  1. Freeze three representative five-report cohorts covering materially different publishers/report types and retain their exact report/source identities and rendered artifact hashes.
  2. Lock one stable human scoring rubric across the cohorts: factual fidelity, evidence selection, analytical depth, insight specificity, commercial relevance, narrative structure, clarity, expert/human feel, and completeness; evaluate LinkedIn derivative copy separately. Keep chart/table scoring outside this item while the visual subproject is separate.
  3. Record reviewer identity/role, per-dimension scores, explicit publishability decision, blocking comments, and any appeal/outlier disposition without changing source evidence after scoring starts.
  4. Aggregate weighted cohort and overall results deterministically; separate failures caused by source limitations from editorial-generation defects.
  5. Route repeatable defects to the owning existing backlog item/prompt family and rerun only through normal governed regeneration; do not manually edit scored outputs to manufacture a pass.
- **Acceptance criteria:**
  - All **15 reports** have completed human review records with reviewer attribution and explicit publishability decision.
  - The retained rubric/weights are identical across all three cohorts and charts/tables remain explicitly excluded rather than silently scored.
  - Aggregate weighted median is at least **85/100**, and no factual-fidelity score is below **8/10** without an explicit retained appeal/outlier disposition that explains why the report remains acceptable.
  - No accepted report contains a material unsupported claim, reader-facing internal identifier, obvious AI scaffolding, or unhandled source limitation.
  - Evidence includes exact report/render hashes so the reviewed output is the same artifact considered for release.

#### P7. Fix public performance measurement and reach hosted targets

- **Baseline:** The current public-site performance script measures HTTP fetch + parse + same-site resource HEAD probes and labels the total `dom_complete_ms`; it gates against YAML `baseline`, while stricter YAML `target` values are not the pass criterion. The baseline review date is stale. Therefore the current tool is useful for regression probing but cannot honestly prove browser DOM/load target attainment.
- **Target behaviour:** Performance evidence separates cheap HTTP regression probes from real browser navigation timing, treats the retained baseline as a regression ceiling and targets as explicit optimisation goals, then improves the seven public routes without losing metadata, archive completeness, or public content contracts.
- **What to implement, in order:**
  1. Correct measurement semantics: either rename current timings to HTTP/probe metrics or add real browser navigation timing for response start, DOMContentLoaded/load and rendered readiness; never call a HEAD-probe aggregate “DOM complete.”
  2. Update the baseline schema/gate so baseline regression and target attainment are reported separately; fail regressions against baseline, report target gaps independently, and retain exact measurement method/version.
  3. Run a fresh hosted seven-route measurement and only then refresh the baseline review date/values; preserve raw scalar evidence and exact code SHA.
  4. Profile the largest target gaps and address the highest-value causes first: unnecessary WordPress queries, duplicate assets, render-blocking/unused resources, excessive payloads, or avoidable archive work—without weakening content/SEO semantics.
  5. Re-run browser and HTTP gates after each change and retain before/after route metrics.
- **Acceptance criteria:**
  - No metric name claims browser DOM/load semantics unless it is sourced from browser navigation timing.
  - Gate output clearly distinguishes `baseline_regression` from `target_gap`; YAML target values are actually evaluated and reported.
  - Fresh baseline evidence is current, method-versioned, and tied to the exact tested SHA; stale dates are not manually advanced.
  - Homepage, reports, briefings, signals, methodology, contact, and submit show no baseline regression in response timing, weight, or request count and materially reduce the largest target gaps.
  - Canonical URLs, Open Graph/Twitter metadata, archive completeness, search/filter behavior, and representative page content remain unchanged/correct after optimisation.

#### P8. Complete concise public evidence, methodology, and related-content surfaces

- **Baseline:** Retained report data includes claims/evidence, source pages, limitations/methodology, topics/categories/geography/time, source identity, embeddings and projections. Public rendering already redacts internal IDs and exposes some approved evidence/advisory data, but there is no consistent concise reader-facing contract for claim support, methodology/limitations, and first-useful related-content links.
- **Target behaviour:** Every supported report page can expose concise, approved evidence context and methodology plus deterministic related links that help a reader verify and continue research. Missing/unapproved evidence fails closed to omission/neutral language rather than exposing internal diagnostics or fabricated support.
- **What to implement, in order:**
  1. Define the public evidence projection contract from retained data: source report/publisher, approved page reference, concise excerpt or support summary, limitation/caveat, and original source link where policy allows.
  2. Define a concise methodology projection using report scope, source pages, material limitations, evidence state, and relevant timing/geography—without exposing OCR/vector/model/validation internals.
  3. Build deterministic related-content selection from existing retained metadata/identity/relationships for report, briefing, topic/category and publisher links; use stable ranking/fallback and no new LLM at render time.
  4. Project only approved fields to WordPress and render them with existing design primitives; keep WordPress render-only for intelligence.
  5. Add redaction/fail-closed tests for missing, stale, private, or unapproved source/evidence fields and related-link absence.
- **Acceptance criteria:**
  - Material public claims can show approved source report, publisher, page/support context, limitation, and original link where available without internal IDs or raw evidence text.
  - Methodology surfaces source scope/pages, material limitations and evidence state concisely; unavailable data is omitted/neutral, never fabricated.
  - Report pages expose deterministic related report/briefing/topic/publisher links when supported and no unrelated link is invented to fill a slot.
  - No provider/model call is required during WordPress rendering or related-link display.
  - Tests prove internal IDs, OCR/model/vector/crop diagnostics, private paths/Drive URLs and unapproved excerpts cannot reach the public projection.

#### P10. Operate correlated public-render failure telemetry

- **Baseline:** The WordPress public render boundary catches exceptions, returns a branded safe error, and emits `marketlense_public_render_failure` with a correlation ID and private context. Hosted release evidence does not yet aggregate these failures or provide an operator signal distinguishing expected injected failures from unexpected visitor-facing render failures.
- **Target behaviour:** Hosted/release evidence gives operators a bounded, private, correlation-based view of public-render failures by route/entity type, while visitors see only the safe response. Repeated unexpected failures are actionable without creating a public diagnostics endpoint.
- **What to implement, in order:**
  1. Make P10 consume the P2-bounded WordPress event contract so only safe bounded fields enter release aggregation.
  2. Add a read-only aggregation step for failure count, route/entity type, correlation ID/hash, first/last occurrence and expected-injected versus unexpected classification; do not retain exception text in public/release artifacts.
  3. Integrate the aggregate into hosted smoke/release evidence and define a simple threshold/disposition for zero, expected injected, and unexpected failures.
  4. Add a controlled injected-failure smoke path in non-public/sandbox validation and verify the visitor response stays branded/redacted.
  5. Link unexpected recurring failures to the existing remediation/operator workflow rather than creating another scheduler.
- **Acceptance criteria:**
  - Hosted smoke/release evidence reports bounded failure counts and correlation references by route/entity type with no stack/path/exception-message leakage.
  - A controlled injected failure is classified as expected and produces the branded public response; a synthetic unexpected case is visible as an unwaived failure.
  - Zero-failure runs explicitly report zero rather than missing telemetry.
  - Repeated aggregation is deterministic and does not expose a public diagnostics route or create external writes beyond existing evidence publication.

### 3. Evidence Quality and Reuse

#### E6. Retain a hash-pinned claim-embedding benchmark export

- **Baseline:** Claim embeddings are produced and governed in the runtime, and the A/B benchmark can make live embedding calls, but the benchmark deliberately does not retain vectors. Fixed-corpus semantic evaluation therefore falls back when persisted vectors are absent and cannot reproduce real semantic ranking in CI without provider calls.
- **Target behaviour:** A bounded, retention-governed, hash-pinned benchmark export contains only approved vector identifiers/content hashes/vectors and enough model/dimension provenance to reproduce semantic ranking and compare against lexical fallback entirely offline.
- **What to implement, in order:**
  1. Define a versioned benchmark-export schema containing opaque claim/vector identity, content hash, embedding model/dimensions/version, vector, corpus identity and generation/hash provenance—no claim/source text.
  2. Add a controlled export path from the retained benchmark corpus that validates vector count/dimensions and writes an immutable manifest/hash.
  3. Update semantic benchmark tooling to load the retained export before any provider path and fail/abstain clearly when the export is incompatible, missing, or hash-invalid.
  4. Add CI coverage comparing semantic retrieval metrics with lexical fallback and verifying zero embedding/provider calls.
  5. Document retention/update policy so a model/dimension/corpus change creates a new export rather than silently mutating the baseline.
- **Acceptance criteria:**
  - Export is hash-pinned, versioned, reproducible and contains no claim/report text or credentials.
  - CI can execute semantic ranking/coverage on the fixed corpus with **zero provider calls** and detect hash/dimension/model incompatibility.
  - Semantic versus lexical fallback metrics are retained with exact corpus/export identity and deterministic results.
  - A changed corpus/model/dimension cannot reuse an incompatible export silently.

#### E10. Attest active model-pricing rates before they become stale

- **Baseline:** Canonical cost routes fail closed when pricing is missing, invalid, stale, held, or unapproved, and the rate card carries version/source/effective information. Operator review of expiring provider rates and the reviewed transition from old to new rates remains manual and easy to miss.
- **Target behaviour:** Operators get a bounded read-only freshness/coverage report for every active production-priced route and an explicit reviewed rate-card transition with before/after cost impact. No scraped/unreviewed rate becomes active automatically.
- **What to implement, in order:**
  1. Enumerate effective production model/provider pricing keys from the same reachable policy inventory used by A15.
  2. Add a read-only attestation command reporting active, expiring, stale, held, missing, source/version/effective/review dates and coverage status without network scraping by default.
  3. Add deterministic before/after cost recomputation for recent canonical usage when an operator proposes a reviewed rate change; retain the old/new version/source and impact summary.
  4. Keep activation as an explicit reviewed configuration/rate-card change and preserve fail-before-provider behavior when the attestation is not valid.
  5. Add tests for missing, expired, held, changed, cached-input and unknown-route pricing states.
- **Acceptance criteria:**
  - Every reachable priced production route appears in the attestation as active/expiring/stale/held/missing with source/version metadata.
  - Unknown, expired, held, or missing rates cannot silently execute as zero-cost or bypass spend authority.
  - A reviewed rate transition retains before/after estimates on recent canonical usage and an explicit operator acknowledgement; no command activates rates automatically.
  - Tests cover effective-date/freshness boundaries and cached-input pricing where applicable.

#### E12. Persist pre-category editorial context checkpoints

- **Baseline:** Recovery can reuse source, selection and vector artifacts, but taxonomy/evidence context is materialized inside the pre-category analysis boundary. A category-fit failure can therefore replay unrelated taxonomy/evidence provider work even when those outputs are still valid.
- **Target behaviour:** A versioned, lineage-validated checkpoint immediately before category fitting makes a genuine category-only recovery reuse all valid upstream taxonomy/evidence context and execute only the category model family plus its deterministic dependents.
- **What to implement, in order:**
  1. Define the pre-category checkpoint contract from approved taxonomy/evidence references, source/selection/vector identities, prompt/policy/schema/config hashes, and required compatibility metadata—no raw prompt duplication.
  2. Persist the checkpoint atomically after all prerequisites validate and before category fitting starts.
  3. Extend minimum-execution/recovery planning so category-fit failures select this checkpoint only when every retained dependency remains compatible; otherwise fall back to the earliest proven safe checkpoint.
  4. Make actual execution audit planned versus reused/regenerated families and record avoided calls/tokens/cost.
  5. Add focused stale/incomplete/tampered checkpoint tests and one retained-report live recovery.
- **Acceptance criteria:**
  - Valid category-only recovery makes no source, extraction, vector, taxonomy or evidence provider call.
  - Stale/incomplete/incompatible checkpoint proof fails closed and selects the correct earlier recovery boundary instead of partial unsafe reuse.
  - Plan/actual audit names the exact reused/regenerated families and measured avoided calls/tokens/cost.
  - One retained live recovery proves the category-only path and all downstream semantic/grounding/publication gates remain active.

#### E13. Measure candidate-regeneration promotion effectiveness

- **Baseline:** Candidate regeneration retains promotion/rollback state, source/evidence lineage, validation issue codes, transformation scope, before/after hashes, prompt/policy/schema identity and usage. Operators cannot yet compare compatible cohorts to identify which repair targets succeed versus repeatedly consume model spend and roll back.
- **Target behaviour:** A read-only, evidence-safe scorecard groups compatible candidate regeneration attempts by repair target/issue/prompt/policy and shows promotion quality, rollback patterns, lineage failures, latency/tokens/cost, and bounded operator recommendations. It never weakens a grounding rule automatically.
- **What to implement, in order:**
  1. Define compatibility/cohort keys from schema, validator, prompt/policy, source/evidence and producer identities; exclude incompatible attempts.
  2. Build a read-only aggregation of attempts, promoted/rolled-back/abstained outcomes, remapped/lost evidence, source-page failures, validation issue classes, latency, tokens and cost.
  3. Separate valid evidence remapping/abstention from ungrounded failure so the scorecard does not reward promotion at the expense of evidence integrity.
  4. Add thresholded recommendations for high-confidence repeated rollback/no-value patterns and successful repair targets; recommendation only, no prompt/routing/validator mutation.
  5. Run retained and bounded live cohorts and document one concrete keep/change/no-change conclusion.
- **Acceptance criteria:**
  - Only version-compatible candidate attempts are compared; all denominators and excluded incompatible counts are explicit.
  - Scorecard contains bounded IDs/hashes/counts/usage only and cannot emit raw source, prompt, candidate, or model-response text.
  - Promotion rate is always accompanied by grounding/lineage validity; invalid promotion is never treated as success.
  - Retained/live evidence demonstrates at least one operator-reviewable reduction in repeated failed repair work or improved valid promotion rate, or explicitly concludes no change on insufficient evidence.
  - No prompt, routing or validation policy is changed automatically.

#### E14. Calibrate category-fit coverage from retained outcomes

- **Baseline:** Category fitting combines model advice with deterministic inclusion/exclusion/centrality logic, supports multiple grounded categories, and preserves supported assignments. Retained decisions exist, but operators lack a compatible-cohort view of nonempty selection, explicit uncategorized outcomes, deterministic rescue, repair use, distribution, latency/tokens/cost and the mapping concepts causing repeated gaps.
- **Target behaviour:** A bounded read-only category-fit scorecard identifies where deterministic mappings or prompts can improve grounded coverage and reduce unnecessary repair without forcing legitimate out-of-taxonomy reports into a category.
- **What to implement, in order:**
  1. Define compatibility cohorts from taxonomy/mapping version, prompt/model/policy, schema/validator and relevant configuration identities.
  2. Aggregate nonempty selection, explicit-uncategorized, selected-count distribution, deterministic rescue, repair rate, validation outcome, latency, tokens and cost by compatible identity.
  3. Retain explicit exclusions/out-of-taxonomy outcomes separately from unresolved mapping gaps so the scorecard does not optimize against valid abstention.
  4. Rank recurring uncovered semantic concepts and excess-repair causes using bounded concept/rule IDs and produce reviewable mapping/prompt proposals only above sample/confidence gates.
  5. Validate a proposed mapping/prompt change through retained and bounded live compatible cohorts using the existing gates; do not mutate taxonomy automatically.
- **Acceptance criteria:**
  - Scorecard reports complete denominators and separates selected, explicit-uncategorized, explicit-exclusion, rescue and repair outcomes.
  - Incompatible taxonomy/mapping/prompt/model/policy cohorts are never merged.
  - Proposals are bounded to mapping/prompt review and include sample/confidence evidence; no automatic taxonomy/policy change occurs.
  - Retained/bounded live evidence demonstrates a measured increase in **grounded** nonempty selection or a reduction in unnecessary category-repair calls with no increase in invalid/forced assignments, or records a justified no-change result.

#### E15. Make publication crops visually complete and repairable

- **Baseline:** The selected chart/table path already has candidate detection, semantic ranking, optional vision crop refinement, PDF geometry tightening, strict raster QA, sidecars, scorecards and bounded escalation. Visual review nevertheless shows crop geometry is not publication-ready. Current refinement can skip vision for candidates judged an “obvious pass” from usefulness/structure signals rather than boundary certainty; vision receives an unannotated full-page render at low refinement DPI; several later stages can tighten/trim the bbox; `edge_clipped_content` is currently routed through another inward content-aware trim; the table boundary detector is observational rather than rejecting; chart completeness is asymmetric; an empty refined bbox can fail open to the whole page; and some fallback/publication paths can reuse lower-DPI crops. Existing retained crop scorecards/goldens mostly prove deterministic regression stability against the same QA logic, not human semantic completeness of the final visual.
- **Target behaviour:** Every accepted publication crop contains the complete semantic visual—chart/table title when attached, full plot/table body, axes, labels, legend, annotations, headers, rows/columns, units, and attached note/source where applicable. Modest safe whitespace is preferable to missing content. Final geometry is localized once, protected by deterministic PDF-aware guardrails, rendered consistently, validated by type-specific completeness checks, and repaired by changing the bbox in the correct direction rather than cosmetically trimming an already-rendered PNG.
- **What to implement, in order:**
  1. Establish a retained human-labelled production crop corpus of roughly **50–100 visuals across 15–20 materially different publishers/report layouts**, with target visual identity, expected/acceptable bbox, required semantic components, defect edge/type, publication-ready decision, and exact source/producer hashes. Measure candidate recall separately from bbox completeness so discovery misses are not confused with crop failures.
  2. For the small set of final ranked publication candidates, make visual crop localization mandatory until retained evidence proves a boundary-confidence skip is equivalent. Feed the model both an annotated full-page image with the candidate box visibly marked and a higher-resolution local context image around the candidate (roughly **180–220 DPI**); map the returned geometry deterministically back to PDF coordinates.
  3. Make the crop-refine objective explicit and ordered: **semantic completeness → exclusion of unrelated neighbours → safe margin → tightness**. Define required components separately for charts and tables and prefer a small margin over uncertain exclusion of an attached title, label, legend, note, or source.
  4. Simplify post-model geometry to safety guardrails rather than repeated re-cropping: intersect with the physical page, fall back to the original candidate bbox on invalid/empty model output, expand for meaningfully intersected text/table rules/attached components, add a small safety margin, and prohibit heuristic inward shrink unless the removed region is provably whitespace/unrelated. Never convert an invalid model bbox into a whole-page crop.
  5. Standardize every crop that can become public to the configured final publication resolution (**216 DPI** under the current profile). Treat candidate-pack/preview crops as previews; do not reuse a lower-DPI cached crop as the final public asset unless its sidecar proves the required publication DPI/profile.
  6. Reduce raster trimming to conservative, provable background removal with a small per-edge cap and retained safety padding. Remove clipped-content defects from inward trim repair; a crop that is missing content cannot be repaired by deleting more pixels.
  7. Implement directional bbox repair with at most one bounded rerender by default: neighbour contamination shrinks only the offending edge; clipping or a missing semantic component expands only the relevant edge. Retain before/after bbox, defect edge/type, repair action, render profile and QA result in the sidecar.
  8. Make final QA type-aware and rejecting: table validation checks outer-rule/text crossings plus complete headers/rows/columns where detectable; chart validation checks all four edges and protects title/legend/axes/labels/annotations/source. Normalize defect labels so deterministic QA, escalation and release gates use the same canonical taxonomy.
  9. Run the retained corpus through the actual `publication_strict` path before and after the change, including the model-localization path where applicable. Use the human labels—not the cropper's own score—as the primary correctness outcome; only after the target is met should adaptive skipping or heuristic deletion be reconsidered for cost/speed.
- **Acceptance criteria:**
  - On the retained representative corpus, at least **95% of accepted publication crops** receive a human `publication_ready` decision, and no accepted crop has critical semantic clipping of a chart title/axis/label/legend or a table header/row/column; attached source/note content is preserved where the human label marks it required.
  - The before/after corpus shows a material reduction in clipping and neighbour-contamination defects versus the exact retained baseline with no material regression in candidate recall or selected-visual usefulness.
  - Invalid/out-of-page/empty model geometry never becomes a whole-page crop; it deterministically falls back to the original candidate geometry or a typed rejection.
  - `edge_clipped_content`/missing-component failures can only trigger bbox expansion/rerender or rejection, never an inward PNG-only trim; neighbour contamination can only shrink the implicated edge.
  - Table completeness can reject a demonstrably cut boundary/header/row/column, and chart completeness evaluates top/right as well as left/bottom with canonical defect labels shared by escalation.
  - Every final public crop sidecar proves the configured publication DPI/profile, and lower-DPI preview/fallback artifacts cannot silently enter the public asset set.
  - Focused tests cover annotated/local vision inputs, invalid-bbox fallback, directional repair, four-edge chart validation, table-boundary rejection, conservative trim, DPI reuse, and sidecar taxonomy; the retained production-strict golden/human corpus passes on the exact implementation SHA.
  - The final selected-visual path remains bounded: no more than the configured localization call plus one repair/rerender per candidate by default, and no new model/library is introduced unless the retained corpus proves the existing stack cannot reach the target.

### 4. Release Integrity and Architectural Enforcement

#### R1. Publish release-evidence reviews where reviewers work

- **Baseline:** CI builds release-evidence review artifacts, appends a bounded GitHub job summary, carries exact tested SHA and queue-evidence status, and uploads evidence. Reviewers still have to navigate workflow artifacts manually for the canonical bundle/final approval, and retained runtime evidence does not always make its representativeness versus smoke-only scope obvious at the PR/release surface.
- **Target behaviour:** The PR/release surface directly exposes exact-tested-HEAD evidence status, link/reference to the archived bundle, final approval/unwaived result, and declared runtime-corpus scope without copying unbounded evidence into comments/summaries.
- **What to implement, in order:**
  1. Define a small release-review surface contract: tested SHA, build/release run ID, review status, unwaived issue count, queue/runtime evidence status, corpus scope label, and stable artifact/reference link.
  2. Extend current CI/release automation to publish that bounded contract on the relevant PR/release surface while keeping the existing job summary/artifact as source of detail.
  3. Add an explicit representativeness label (`smoke`, `representative`, or equivalent finite taxonomy) to strict runtime evidence and propagate it into the review surface.
  4. Fail/mark unavailable on exact-HEAD mismatch, missing canonical evidence, expired/unavailable artifact, or unwaived failure rather than showing a green summary.
  5. Update README/release docs and tests for bounds, mismatch, scope labels and issue retention.
- **Acceptance criteria:**
  - A reviewer can see the exact tested SHA, final evidence disposition, unwaived issue count and canonical bundle reference without opening raw CI logs.
  - Mismatch/unavailable evidence is explicitly non-green and cannot be mistaken for approval.
  - Runtime evidence clearly states whether it is smoke-only or representative; the label is retained with provenance.
  - Surface content is bounded and does not duplicate raw evidence/private diagnostics; all unwaived issues remain accessible in the canonical bundle.
  - Tests cover exact-HEAD match/mismatch, unavailable evidence, representative/smoke labels and bounded summary behavior.

#### R2. Enforce role boundaries, direct-I/O discipline, and controlled module growth

- **Baseline:** CI already enforces role imports, direct-I/O ownership, service-boundary mapping, forbidden patching, refactor-movement evidence, coverage, mutation, and repository hygiene. Remaining gaps are targeted: some important service-boundary coverage can be absent without a clear failure, and approved facade/waiver exceptions are not uniformly narrow, owner-accountable and expiring.
- **Target behaviour:** New first-party architecture drift fails before merge unless covered by a narrowly scoped, documented, expiring waiver with an owner/reason. Pure/inaccessible boundaries are not forced into meaningless integration tests, and no generic governance layer is added.
- **What to implement, in order:**
  1. Audit current architecture/service-boundary coverage and identify only concrete uncovered first-party boundaries with external/stateful behavior or high drift risk.
  2. Define a minimal waiver record schema with exact rule/path/symbol scope, owner, reason, creation date and expiry; preserve existing valid compatibility facades where they are intentional.
  3. Extend the existing CI architecture gate so a targeted uncovered boundary or new exception fails unless a valid narrow waiver exists.
  4. Make expired/over-broad/missing-owner waivers fail deterministically and provide a bounded remediation message.
  5. Add docs/tests using representative violations, valid waivers, expiry and pure-boundary exclusions.
- **Acceptance criteria:**
  - A known targeted service-boundary coverage gap fails CI without a valid waiver.
  - Every new waiver has owner, reason, exact scope and expiry; expired or widened scope fails.
  - Pure or genuinely inaccessible boundaries are not required to add fake integration tests solely for coverage.
  - Existing public facades/external-effect ownership remain unchanged unless separately approved.
  - Tests prove target violations, valid exceptions, expiry and deterministic diagnostics.

#### R3. Restore service quality coverage above the retained baseline

- **Baseline:** Retained `src/services` coverage is **82.5763%** and the architecture floor is 75%. Recent service growth has reduced protection relative to the desired retained quality level, while the older 82.9680% figure has no valid retained baseline artifact and must not be used as a target. Coverage alone is not sufficient if added tests do not exercise observable behavior/state.
- **Target behaviour:** Behavior-focused tests protect the highest-risk stateful/external service paths and a passing exact-commit full CI measurement retains service coverage at least at the current verified baseline, with no regression in other major coverage domains.
- **What to implement, in order:**
  1. Run/inspect exact current coverage by service module and rank uncovered behavior by operational risk, focusing first on ledger/recovery, browser-worker lifecycle, artifact lineage and other durable external/stateful paths.
  2. Add tests that assert returned contracts, persisted state, retries/idempotency/failure handling or boundary calls—not lines executed solely for coverage.
  3. Re-run focused suites and then the full CI/coverage command on one exact commit; retain the measured global/contracts/generators/orchestrators/services/control-plane values.
  4. Fix real regressions exposed by the tests without adding exemptions or lowering the 75% floor.
  5. Reset the retained baseline only from that passing exact-commit run with evidence reference/SHA.
- **Acceptance criteria:**
  - `src/services` coverage is **not below 82.5763%** on the retained passing exact-commit full-suite measurement and increases where the selected behavior tests add meaningful protection.
  - Global/generator/orchestrator coverage does not regress from its retained release baseline.
  - Added tests cover observable contracts/state/failure behavior; no coverage-only dead paths, exclusions, or lowered thresholds are introduced.
  - Baseline artifact records exact SHA, command/environment and measured values and is updated only after all relevant tests/gates pass.

#### R6. Review bounded-log reduction telemetry and remediate recurring callers

- **Baseline:** Standard Python structured logging deterministically bounds nested payloads and emits `log_payload_reduced` when an event exceeds the byte contract. Operators do not yet aggregate those signals, so repeated callers attempting to serialize large domain payloads can remain hidden even though the final stored event is safe. P2 separately owns the WordPress public-boundary event contract.
- **Target behaviour:** Release/operator evidence shows where bounded-log reduction is occurring, how large attempted events are, and which modules/events repeatedly trigger reduction, without retaining/reconstructing discarded content. Recurring callers become explicit remediation work.
- **What to implement, in order:**
  1. Define a read-only aggregation contract for reduction count, module/event, attempted-size percentiles, retained-size/budget status, time window/build identity and bounded caller identity.
  2. Aggregate only existing `log_payload_reduced` metadata; do not inspect or reconstruct dropped values.
  3. Add deterministic thresholds for “recurring caller” and map threshold breaches to an owner/existing backlog/remediation reference rather than auto-mutating logging code.
  4. Integrate the scorecard into release evidence/operator review with explicit zero-event state.
  5. Add redaction/content tests using source/prompt/browser/model-like payloads and verify the aggregate cannot contain them.
- **Acceptance criteria:**
  - Release evidence reports reduction count, event/module grouping and attempted-size percentiles with explicit zero state.
  - Scorecard contains no source text, prompts, model output, browser terminal text, credentials or discarded raw values.
  - Recurring callers above threshold are linked to an owner/remediation item and remain reviewable; no automatic weakening of event bounds occurs.
  - Aggregation is deterministic for the same retained log set and tests prove redaction preservation.

### 5. Boundary Simplification

#### S3. Simplify the PDF visual-heuristics boundary

- **Baseline:** Visual heuristics, panel detection, visual-candidate, crop and table families have already been decomposed behind compatibility facades and movement evidence. A broad “clean up PDF code” task is no longer justified; any remaining simplification must start from a measured coupling/ownership defect and preserve the one canonical PDF/external-library boundary.
- **Target behaviour:** The PDF visual capability has clear semantic ownership and a smaller dependency surface only where evidence shows real coupling, while candidate/crop behavior, artifact paths, cache semantics, benchmarks and public facades remain unchanged.
- **What to implement, in order:**
  1. Run the dependency/ownership/module-size audit and identify one concrete remaining coupling that materially obscures the PDF boundary; if none is significant, close/hold with evidence rather than refactor for aesthetics.
  2. Define the intended owner/facade before movement and document which callers/contracts must remain stable.
  3. Move/extract only the identified responsibility behind the canonical PDF service boundary; do not add navigation-only layers or duplicate external-library access.
  4. Preserve compatibility facade/imports where approved callers still require them and update architecture mapping/movement evidence.
  5. Run focused equivalence tests and retained PDF candidate/crop benchmarks before closing.
- **Acceptance criteria:**
  - A specific pre-change coupling/ownership finding and measurable simplification are documented; otherwise the item may conclude “no significant change justified.”
  - External PDF/library I/O remains owned by the canonical boundary and is not duplicated in generators/orchestrators/UI.
  - Candidate selection, crop/table outputs, artifact paths, cache identities and retained benchmark signatures remain equivalent.
  - Architecture/import/service-boundary gates and focused/full relevant tests pass with no new generic facade layer.

#### S4. Give WordPress shortcodes semantic ownership

- **Baseline:** `class-marketlense-core-shortcodes.php` owns many unrelated public concerns, including navigation/search/report browsing and multiple entity surfaces. Tests protect public behavior, but the catch-all class makes feature-level changes harder to isolate and increases the risk that a local presentation change affects unrelated shortcodes.
- **Target behaviour:** Coherent shortcode families have explicit feature ownership behind a stable registration/compatibility facade. Public shortcode names, hooks, output contracts, query behavior and CSS/JS handles do not change as a result of the refactor.
- **What to implement, in order:**
  1. Inventory registered shortcodes/private helpers and group them by coherent public feature family based on shared data/query/render semantics—not file size alone.
  2. Define a thin compatibility/registration boundary and extraction order that avoids circular dependencies; start with the most independent family and move one family per step.
  3. Extract family-owned rendering/query helpers into feature-specific classes/modules while keeping shared primitives genuinely shared and WordPress-native.
  4. Preserve all existing shortcode tags, action/filter registration, asset handles, GET/query semantics and rendered markup unless a separate approved behavior item owns a change.
  5. Add/adjust PHP/runtime tests per family plus facade/registration equivalence, then remove obsolete catch-all helpers only after callers are migrated.
- **Acceptance criteria:**
  - Every extracted unit owns a coherent documented shortcode family; the original catch-all class no longer implements unrelated feature semantics directly.
  - Existing shortcode tags/hooks, report/archive/filter query behavior, public markup contracts and asset handles remain unchanged in equivalence tests.
  - No additional navigation-only abstraction or duplicate WordPress query/I/O boundary is introduced.
  - PHP/runtime tests cover each family and compatibility registration; architecture/service-boundary tests pass.

## Deferred Work

Deferred means **not an MVP blocker under current evidence**. In particular, P3 is intentionally tied to production-host migration rather than the temporary HTTP sandbox. D10 remains deferred because A18/A19 own current browser/acquisition correctness and no separate tuning program should compete with them.

## Recently Closed / Retained Evidence

The Unified Work Register is the status authority. Detailed historical narratives are intentionally not duplicated here because they became stale and contradictory. Retained proof remains in `docs/quality/`, `docs/CTO_evidence/`, release evidence, and git history. Recent/high-value closure references include:

- **E11:** [`docs/quality/e11-structured-output-recovery-evidence-2026-08-28.md`](docs/quality/e11-structured-output-recovery-evidence-2026-08-28.md).
- **E9:** [`docs/quality/e9-prompt-family-reuse-evidence-2026-08-27.md`](docs/quality/e9-prompt-family-reuse-evidence-2026-08-27.md).
- **E8:** [`docs/quality/e8-source-reuse-evidence-2026-08-28.md`](docs/quality/e8-source-reuse-evidence-2026-08-28.md).
- **P12/P14:** [`docs/CTO_evidence/p12_p14_exact_head_canary_20260827.json`](docs/CTO_evidence/p12_p14_exact_head_canary_20260827.json).
- **P6 human-review evidence:** [`docs/quality/p6-editorial-acceptance.md`](docs/quality/p6-editorial-acceptance.md) remains Active evidence, not closure evidence.

## Guardrails

- Never normalize cross-publisher metrics with incompatible definitions, geography, methodology, or time period.
- Never publish incomplete public pages for later enrichment; preview/draft is allowed only outside the public release surface.
- Never invent identity attributes for acquisition forms; map only configured, verified values.
- Never lower private-API promotion thresholds automatically.
- Never publish OCR, model, crop, vector, validation, filesystem, stack-trace, or other operator diagnostics as public product content.
- WordPress remains a rendering/publication boundary for intelligence; do not move report intelligence generation into the theme/plugin.

### Non-negotiable publishing guardrail

Automation may plan, resume, retry, repair, validate, render, draft, hold, and notify. It must not public-auto-publish until retained evidence demonstrates safe claims, no internal-ID leakage, stable crop acceptance, stable WordPress updates, duplicate suppression, rollback, and consistent editorial quality.

## Current-State Evidence

- Canonical workflow-control, budgets, recovery, model-policy routing, source identity, artifact lineage, publish readiness, and idempotent WordPress publication boundaries are implemented with retained evidence.
- WordPress currently has baseline public render safety, private intake persistence, responsive navigation/search/filter implementation, and authenticated draft/readback support. P2/P4/P5/P10 own deployed operational proof rather than missing baseline implementation.
- `sync-wordpress-intelligence` has retained evidence for **64 public content entities** — 47 reports, 5 briefings, and 12 signals — **plus 29 publishers**. Do not describe that as 64 total entities.
- HTTPS on the temporary sandbox is intentionally deferred to production-host migration under P3; it is not counted as an autonomous-MVP implementation blocker.
- P6 is an editorial human-acceptance outcome, not an automated-gate implementation gap.
- P7 is not closeable until its measurement semantics distinguish HTTP probe timing from real browser DOM/load timing and report baseline regression separately from target attainment.
- CI covers formatting, typing, architecture/import checks, forbidden patching, hygiene, coverage, mutation, prompt regression, release-evidence archival, PDF candidate/crop/trend gates, public report-quality gates, and WordPress staging verification when configured.

## Audit Notes

- Full backlog/code/WordPress reconciliation performed on 2026-09-04 against exact product-code HEAD `28ad708f3bc3badf568c5f8e31f8c9d94df52775`; targeted crop-path review refreshed on 2026-09-05 against current `main` at `1aa50412a863ef1891f14f1b81f72a4230353aed`.
- The register contains **24 Active outcomes**, and each has a full execution section with baseline, target behaviour, ordered implementation work, and acceptance criteria.
- E15 was added from the crop-path review because crop correctness is a user-visible quality outcome distinct from closed E5 telemetry, closed C2 escalation infrastructure, and S3's behavior-preserving simplification scope.
- P3 is correctly Deferred for production-host migration rather than counted as a temporary-sandbox MVP blocker.
- Historical canonical IDs previously present only in closure prose/context remain restored to the Unified Work Register: A5, A12, A13, P0, P9, P11, E1, E2, E5, E7, R4, S1, S2, and D10.
- The obsolete statement that closed A3/A6 remained Active is removed; E3 no longer delegates current work to already-closed E7.
- C6, P11, and A14 closure wording remains narrowed to the capability/tooling actually proven so A18/A19 own current production-hardening work without contradiction.
- Public-site states distinguish implemented-but-unverified outcomes from missing implementation, and intentional sandbox HTTP from production transport requirements.