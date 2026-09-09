# Consolidated TODO

Last audited: 2026-09-07
Audit basis: repository `main` product implementation at `957ad6ceab767ac91529e461f72c6a32e0665c83`, the current workflow/CLI/configuration/quality inventory, current WordPress theme/plugin code, retained reliability and P6 editorial evidence, and a targeted visual review of current `publication_strict` crop outputs and sidecars. The audit also considered the pre-existing evidence-fidelity work in the dirty worktree but does not treat uncommitted work as completed capability. Hosted-only completion criteria remain open unless a current deployed smoke/readback proves them; the temporary HTTP sandbox is not treated as a production-hosting defect.

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
| Active | A20 | Prove clean-room capability readiness before first external work | Turn profile intent into a complete, redacted capability/dependency proof with exact remediation before any costly or mutating operation. |
| Active | A21 | Establish a representative first-attempt end-to-end reliability SLO | Measure and raise cold-start conversion from discovery through review-ready packages and approved sandbox readback without cohort substitution or manual repair. |
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
| Active | P16 | Build a decision-grade consulting synthesis artifact | Create one evidence-bound decision model that makes implications, options, trade-offs, risks, unknowns, and conditional actions coherent across public surfaces. |
| Active | P17 | Compose adaptive, non-repetitive visual report stories | Replace one fixed content sequence with a bounded composition plan that gives each source a clear narrative and uses only E15-approved visuals. |
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
| Active | E13 | Measure candidate-regeneration promotion effectiveness | Make repair item-scoped and adaptive with retry memory, deterministic/typed diagnosis, strategy diversification, and retained success benchmarks while preserving safe promotion/rollback. |
| Active | E14 | Calibrate category-fit coverage from retained outcomes | Turn retained category-fit decisions into grounded mapping/prompt proposals. |
| Active | E15 | Make publication crops visually complete and repairable | Replace shrink-biased crop refinement/QA with completeness-first localization, directional bbox repair, and human-grounded production evidence. |
| Active | E16 | Make methodology, applicability, and uncertainty decision-grade | Convert loose methods/limitations text into source-linked evidence-strength facts that constrain claims and support executive interpretation. |
| Active | R1 | Publish release-evidence reviews where reviewers work | Link exact-tested-HEAD evidence/approval to the PR/release surface and declare runtime-corpus representativeness. |
| Active | R2 | Enforce role boundaries, direct-I/O discipline, and controlled module growth | Close targeted boundary-coverage and expiring-waiver gaps without generic governance noise. |
| Active | R3 | Restore service quality coverage above the retained baseline | Add behavior-focused service coverage and refresh the baseline only from a passing exact-commit run. |
| Closed | R4 | Publication usage/projection reconciliation guard | Missing/invalid/materially lagged usage/projection evidence stops public writes without rebuilding. |
| Closed | R5 | Hash-verified dependency lock artifacts | Native Ubuntu CPython 3.12 wheelhouse and offline hash-locked install are verified. |
| Active | R6 | Review bounded-log reduction telemetry and remediate recurring callers | Aggregate reduction attempts and convert recurring oversized callers into bounded remediation. |
| Active | R7 | Prove recoverable backups and full-state disaster restoration | Back up the mutually dependent stores/artifacts consistently and prove isolated restoration, integrity, lineage, and safe resume against explicit recovery objectives. |
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

The register currently contains **30 Active outcomes**. Every item below is implementation-ready and uses the same four-part contract: **Baseline**, **Target behaviour**, **What to implement, in order**, and **Acceptance criteria**.

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

#### A20. Prove clean-room capability readiness before first external work

- **Baseline:** `plan` is side-effect free and the report-pipeline preflight checks writable runtime paths, LLM settings/policy coverage, prompt loading, and optional Drive/browser/WordPress availability. A new machine or profile can still pass that partial preflight and fail only after work starts because the selected workflow's complete dependency graph is not proven: resolved package/build compatibility, SQLite schema/integrity and lockability, PDF/render/OCR/font tools, browser runtime/version, vector-store compatibility, Drive source-read permission, mailbox mode, disk headroom, clock/TLS, or target-specific credentials/capabilities. `browser-doctor` is separate and there is no one operator answer to “can this exact profile complete this exact intent?”.
- **Target behaviour:** One read-only capability doctor resolves the selected intent/profile into its exact workflow stages and proves every required local and external capability before the first costly or mutating operation. It distinguishes `ready`, `degraded-but-supported`, `not_required`, `not_checked`, and `blocked`, emits exact safe remediation, and retains a configuration/policy/build-bound proof without exposing or changing secrets.
- **What to implement, in order:**
  1. Extend the existing pipeline-preflight contracts and orchestrator rather than adding a parallel health framework. Derive required checks from the canonical workflow/queue registry, selected run profile, planned side effects, and generated capability manifest; a stage cannot start if a required capability is absent from the proof.
  2. Add deterministic local probes for Python/locked-package compatibility, required imports and subprocess tools, configured font/template/prompt/schema assets, PDF/render/OCR availability, browser package/runtime compatibility, writable paths plus configurable free-space floor, and every canonical SQLite store's migration level, integrity, foreign keys, and bounded lock/write probe. Probes may create only uniquely named temporary files/transactions and must clean them up.
  3. Add opt-in bounded live probes for the exact external capabilities selected by the profile: Drive list/read and optional archive-write authority, LLM model/structured-output compatibility, vector-store access, mailbox read/search, browser launch/network, and WordPress schema/auth/readback. Use zero-write/read-only operations wherever the provider supports them; any write probe must be explicitly enabled, budgeted, uniquely scoped, verified, and reversed.
  4. Reconcile operator policy before work: active price-card attestation, budget authority/ledger availability, source and target identity, publication approval mode, queue controls, recovery gates, and required secret *names* without ever printing values. Make `not_checked` blocking for a required capability when a live run is requested.
  5. Expose the same report through CLI and operator UI, with a bounded summary plus a retained detailed artifact. Every blocker must name the failed stage/capability, stable error code, safe evidence, exact next command/config key, whether automatic repair is prohibited, and the command to rerun the same proof.
  6. Prove the workflow from clean supported Windows and Ubuntu environments using the hash-locked install, empty runtime stores, a copied value-free local overlay, and sandbox/read-only credentials. Keep the ordinary CI lane provider-free and run live probes only behind the existing guarded integration controls.
- **Acceptance criteria:**
  - For every registered runnable intent/profile, the doctor lists all required stages and capabilities with no required stage left `not_checked`; manifest/registry drift fails a deterministic test.
  - Clean supported Windows and Ubuntu runs install from `requirements.lock`, initialize/migrate empty stores, resolve all assets/tools, and reach a retained `ready` or explicitly supported `degraded-but-supported` proof without source-code or committed-config edits.
  - Missing/wrong binary, stale schema, corrupt database, insufficient disk, locked store, incompatible browser, missing price, absent credential name, wrong provider model, denied Drive/mailbox/WordPress capability, and TLS/clock failure each block before the affected external/costly operation with one actionable stable code.
  - A required live capability cannot inherit a green result from a skipped probe. Offline planning remains available and labels live capabilities `not_checked` without pretending the workflow is executable.
  - Default execution performs zero provider/model/browser/mailbox/Drive/WordPress writes, logs no secret values or submitted/source content, leaves no probe artifacts, and produces identical ordered output for identical environment state.
  - Tests cover the capability matrix, local probe cleanup, redaction, profile-specific omission, live-guard behavior, and proof invalidation when configuration, policy, build, dependency, schema, or tool identity changes; canonical setup/configuration/troubleshooting docs carry the one supported procedure.

#### A21. Establish a representative first-attempt end-to-end reliability SLO

- **Baseline:** Durable queues, checkpoints, lineage, retry ownership, reliability-transition telemetry, publish readiness, approval, idempotent WordPress writes, and exact-HEAD three-report canaries are implemented. Evidence still does not prove representative first-attempt conversion. The synthetic `autonomous_happy_path_smoke.py` exercises only a mailbox handoff; the retained 20-report run reached 18/20 publish-ready and 9/18 verified publications; P6 cohorts required frequent regeneration and later clean reruns to resolve held reports. Existing telemetry reports terminal conversions and failures but does not define a cold-state first-attempt SLO across the full graph.
- **Target behaviour:** A frozen representative program measures the probability that a newly admitted source reaches an immutable `awaiting_review` package on its first submitted workflow attempt, with no operator repair, cohort substitution, ungoverned retry, or reuse of derived editorial artifacts. After explicit approval, the ready subset reaches authenticated sandbox readback and a zero-write replay. Failures remain visible in the denominator and drive shared, publisher-agnostic prevention work.
- **What to implement, in order:**
  1. Reuse and extend the canonical validation-reliability artifact rather than building a second scorecard. Define `first_attempt`, `first_pass`, `bounded_recovery`, `operator_intervention`, `terminal`, and `verified_replay` precisely at entity and stage level, including internal structured-output repair, targeted regeneration, queue redelivery, process restart, and manual requeue.
  2. Freeze a stratified cohort by reusing the A18 discovery corpus, P6 editorial cohorts, and retained acquisition-route evidence where identities remain compatible. Cover direct PDF, report-page extraction, browser, gated/mailbox, on-site capture, short/long, native/OCR, data-heavy/narrative, multi-publisher, and visual/no-usable-visual cases; add only missing strata and never select or replace members based on generated outcome.
  3. Run two bound lanes on the exact implementation SHA: a deterministic provider-free replay of retained external-boundary fixtures for the whole queue graph, and a controlled live/sandbox lane from real discovery/acquisition through source ingest, analysis, render, analytics projection, publication readiness, Signal/Briefing opportunity where eligible, explicit approval, WordPress publication, authenticated readback, and identical-package replay.
  4. Extend the reliability artifact with stage denominators, first-pass/first-attempt conversion, bounded-recovery conversion, attempts and repair calls, time/cost to first terminal result, orphan/outbox/lease anomalies, operator interventions, and failure Pareto. Preserve exact cohort/configuration/policy/build and external-fixture identities; missing attribution is `unavailable`, never zero.
  5. Fix the highest-impact shared causes at their owning input/prompt/service/orchestrator boundary. Do not add report/publisher-specific exceptions, relax validation, increase retry limits to mask defects, or delete failed members. Rerun the complete immutable cohort after each promoted prevention change and retain before/after evidence.
  6. Add a release-facing SLO check with separate deterministic and controlled-live dispositions. Keep public auto-publication prohibited: automated success stops at `awaiting_review`; the publish/readback phase requires the existing explicit approval and isolated sandbox safeguards.
- **Acceptance criteria:**
  - The frozen cohort and stratum manifest are hash-pinned before execution, every admitted member remains in every denominator, and derived report/editorial/crop/readiness caches are empty at start; only explicitly declared immutable source/route fixtures may be reused.
  - The provider-free full-graph replay completes **100%** of eligible entities to the expected terminal state with zero orphan jobs, lost outbox events, stale-lease commits, duplicate effective side effects, or unclassified failures.
  - In the controlled live lane, at least **95%** of valid admitted sources reach `awaiting_review` on the first submitted attempt without operator intervention, at least **90%** pass publish readiness without targeted editorial regeneration, and **100%** reach a typed terminal state within configured bounds. Source-invalid/rights/credential blockers are reported separately but remain in the intake funnel.
  - After explicit approval, **100% of publish-ready admitted packages attempted against the healthy sandbox** receive authenticated metadata/content/media readback, and replaying the identical package requests and performs zero WordPress post writes; target outages remain explicit unavailable evidence, not a pass.
  - Stage results identify first-pass, internally repaired, retried, operator-requeued, and permanently held outcomes separately with exact calls/tokens/cost/duration; no successful retry rewrites the original first-attempt result.
  - Each promoted fix improves the compatible cohort's first-attempt conversion or cost/time-to-terminal without reducing source fidelity, editorial P6 scores, E15 crop acceptance/coverage, acquisition recall, or publication safeguards; the final evidence is bound to one exact SHA and the release surface.

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

#### P16. Build a decision-grade consulting synthesis artifact

- **Baseline:** The report pipeline has a grounded editorial plan, summary, scored insights, `so_what`/`now_what`, Decision Brief, counter-signals, limitations, Expert View, and strict claim validation. P6 reviewer-supplied scores are already strong, but closure is incomplete and the underlying decision logic is fragmented across free-form artifact fields. The fixed public report can repeat the same thesis/metric across Core Signal, Executive Summary, Decision Brief, Findings, and Expert View without proving a coherent chain from evidence to decision, explicit trade-offs, conditions, risks, and remaining unknowns. Generic senior-business context is assumed because no governed audience/decision context exists.
- **Target behaviour:** Each report has one versioned, persisted, source-fidelity-validated decision synthesis that states what decision the evidence informs, what changed, why it matters, available actions/options, conditions and trade-offs, risks/counterevidence, uncertainty, and what evidence to collect next. Every public advisory surface is a purposeful projection of that one model, not an independent competing synthesis. Creativity means finding a report-specific, non-obvious but supported connection—not adding unsupported facts or generic strategy language.
- **What to implement, in order:**
  1. Freeze a consultancy-quality rubric and baseline on the existing P6 cohorts. Label decision clarity, evidence-to-implication chain, specificity, trade-off quality, counterevidence, actionability, originality-without-speculation, audience fit, cross-section repetition, and abstention quality; retain exact artifact hashes and reviewer attribution. P6 continues to own overall publishability acceptance.
  2. Add a versioned `decision_synthesis` family to the persisted artifact schema with bounded fields for decision question, executive thesis, evidence-backed changes, implications, actions/options, conditions, trade-offs, risks/counter-signals, known unknowns/next evidence, applicability, and confidence rationale. Every factual proposition and source-derived premise carries one or more approved evidence IDs; analyst-authored advice carries its supporting premise IDs and an explicit `source_stated|marketlense_analysis|conditional` status.
  3. Accept optional non-secret audience context only through a typed request (`role`, `industry`, `geography`, `decision_horizon`, `stated_objective`, `constraints`) and hash it into lineage. Missing context must produce a useful general executive lens; the model may not infer a company, budget, maturity, competitor position, or objective.
  4. Generate the synthesis once after the editorial plan and fidelity-approved evidence/methods/limitations are available. Use deterministic candidate assembly first, then one semantic synthesis call only where a grounded relationship/trade-off cannot be selected mechanically. Route it through the canonical prompt/LLM policy, structured-output, budget, replay, and targeted-regeneration boundaries.
  5. Validate the complete evidence→premise→implication→action chain. Factual premises use the existing source-fidelity/grounding checks; advice must be conditional when outcomes are not source-stated; contradictions, weak applicability, and missing evidence force qualification or abstention. Reject generic actions that would remain valid after changing the report's evidence IDs/title.
  6. Refactor Summary, Decision Brief, Findings implications, Expert View, card copy, and LinkedIn generation to consume the same approved synthesis while preserving each surface's purpose and length. Add deterministic cross-surface redundancy measurement and prohibit verbatim or near-verbatim reuse except the short thesis/metric where repetition is explicitly justified.
  7. Run blinded pairwise review against the retained baseline with senior strategy/editorial reviewers. Promote only when decision quality and human preference improve without source-fidelity, completeness, cost, or first-pass regression; keep the current pipeline if evidence is inconclusive.
- **Acceptance criteria:**
  - Every non-abstained factual premise, implication, risk, trade-off, and recommended action is traceable through the retained synthesis to approved evidence IDs; advice not explicitly stated by the source is visibly conditional and cannot smuggle in an unsupported factual premise.
  - An absent audience context never invents client facts, while supplied context is schema-validated, non-secret, lineage-bound, and used only within its declared role/geography/horizon/objective/constraints.
  - Representative fixtures cover data-heavy, narrative, survey, forecast, methodology-limited, one-sided, and conflicting-evidence reports; thin evidence produces a concise abstention/unknown rather than generic recommendations.
  - On the frozen P6 comparison set, at least **80% of blinded pairwise judgments** prefer the candidate for decision usefulness and at least **75%** prefer it for report-specific insight/originality; no factual-fidelity score falls below the retained baseline and no accepted report contains an unsupported causal or commercial outcome.
  - Cross-surface near-duplicate blocks fall by at least **50%** from the exact baseline while all editorial-plan themes remain represented and each surviving module has a distinct role; metrics/qualifiers remain exact.
  - The normal first-pass path adds at most one decision-synthesis provider call; cache/lineage identity includes evidence, prompt, policy, schema, and audience context, and incompatible reuse fails closed. Targeted repair changes only the rejected synthesis fields and their deterministic dependents.
  - Schema, serialization, grounding, semantic, public-editorial, prompt-fixture, P6 human-review, and signed publish-readiness tests/evidence pass on the exact implementation SHA with zero new publication bypass or hidden retry.

#### P17. Compose adaptive, non-repetitive visual report stories

- **Baseline:** `report.html.j2` renders a polished but fixed Overview→Findings→Signals→Evidence→Expert View→Taxonomy sequence. Module availability changes, but hierarchy and narrative rhythm do not adapt to whether a report is a market benchmark, survey, outlook, framework, trend deck, or narrow evidence note. Visual selection/ranking and crop generation are separate from the editorial plan; P6 explicitly excludes charts/tables. A valid report can therefore be text-heavy, repeat chapter summaries, bury its strongest evidence, or place a usable chart without proving that it advances the report thesis. E15 owns crop geometry and acceptance, not story composition.
- **Target behaviour:** A bounded composition plan turns already-approved editorial, advisory, evidence, and visual assets into a report-specific reading path. It chooses a finite narrative mode, module order/emphasis, visual anchors, evidence depth, and omission decisions from available content; it never generates new facts in the renderer. The same plan produces accessible, responsive HTML and WordPress projection, and every displayed visual is E15-approved and semantically necessary.
- **What to implement, in order:**
  1. Audit the hash-pinned P6 reports at desktop and mobile for module repetition, time-to-first-decision, theme coverage, evidence depth, text/visual balance, chart/table usefulness, caption/action linkage, empty/weak modules, and reading length. Add human labels for visual storytelling and information hierarchy; do not use the renderer's own score as the target.
  2. Define a small finite composition taxonomy such as `data_led`, `survey_tension`, `market_outlook`, `operating_framework`, and `concise_evidence_note`, with deterministic eligibility from report type, editorial-plan breadth, evidence/metric density, methods/limitations, and E15-approved visual inventory. Ambiguous cases use the current safe layout; do not create open-ended model-designed templates.
  3. Add a versioned `report_composition` contract mapping each planned module to one purpose, source artifact IDs, editorial-plan theme IDs, optional approved visual/caption/evidence IDs, display priority, and omission reason. Build it in the generator after P16/E15 inputs are validated; the renderer may only project the plan and cannot synthesize missing intelligence.
  4. Select visual anchors for evidentiary value and narrative role (`thesis_proof`, `comparison`, `mechanism`, `risk`, `methodology`), not crop quality or lexical similarity alone. A visual must match the chosen theme/claim, retain its complete caption/source context, pass E15, and add information not already conveyed by adjacent copy; otherwise omit it.
  5. Refactor the HTML/WordPress view model to render the finite plan with semantic headings, stable deep links, keyboard/assistive navigation, responsive image sizing, and print/share behavior. Preserve safe fallback for legacy artifacts and keep intelligence generation out of WordPress.
  6. Add deterministic checks for uncovered priority themes, repeated paragraphs/metrics, orphan visuals, duplicated module purpose, excessive text before the first decision, visual-caption mismatch, and empty decorative sections. Keep advisory thresholds reviewable until human evidence supports a hard release gate.
  7. Compare the candidate and current layout through blinded desktop/mobile review and browser regression on the same report hashes. Promote only if comprehension, hierarchy, and visual usefulness improve without accessibility, Core Web Vitals, SEO, source fidelity, or WordPress checksum regression.
- **Acceptance criteria:**
  - Every report composition has exactly one supported finite mode, one purpose per displayed module, complete priority-theme coverage or an explicit evidence-based omission, and no renderer-created facts or prose.
  - **100% of displayed chart/table assets** carry matching candidate, crop-sidecar, evidence, insight/theme, caption, source-page, and composition-role identities; every asset passes E15 and no preview/lower-DPI/rejected crop reaches public HTML.
  - On the frozen review set, no adjacent modules contain a verbatim paragraph or materially duplicate the same claim/metric without a declared distinct purpose; deterministic redundancy decreases versus baseline without dropping decision-critical evidence.
  - At least **80% of blinded desktop/mobile comparisons** prefer the candidate for information hierarchy and visual storytelling, and at least **80% of reviewers** can identify the thesis, primary evidence, main implication, and principal limitation correctly after a bounded read.
  - Automated browser checks cover every composition mode at 390, 768, 1024, and 1440 CSS-pixel widths with no horizontal overflow, clipped text/image, broken anchor, keyboard trap, missing focus state, empty landmark, console error, failed asset request, or materially regressed accessibility result.
  - Public HTML/WordPress normalized text, links, metadata, and media identities remain signed/readiness-bound; SEO and hosted performance remain within P7 targets, and legacy artifacts render through the current safe layout rather than partial adaptive output.

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

- **Baseline:** Candidate regeneration already protects canonical artifacts through candidate-only writes, deterministic schema/evidence/source-page integrity checks, full revalidation, auditable promotion/rollback, evidence lineage, and a critique-first regeneration protocol. Repair intelligence is materially weaker than promotion safety: failures are primarily mapped from rule/section to artifact-family regeneration targets; a single failed public item can regenerate an entire family; rejected-candidate failures are retained in audits but do not become machine-usable feedback for the next retry; replacement evidence after quarantine is ranked mainly by lexical token overlap; retry attempts can repeat the same effective strategy; and the existing `validate_retained_claims()` protected-fact/numeric/quote/semantic diagnostics are not part of the central atomic repair candidate loop. The current scorecard-only scope therefore measures repeated rollback without fixing its main causes.
- **Target behaviour:** Candidate regeneration becomes genuinely atomic and adaptive while preserving the existing fail-closed promotion boundary. Every repair starts from the last promoted artifact, diagnoses the exact failing item/field and protected facts, chooses the cheapest safe repair action, changes only explicitly allowed paths, validates deterministic factual compatibility before the full gates, and records a machine-readable before/after failure delta. A rolled-back candidate never becomes the next baseline, but its strategy, evidence choices, resolved/persisting/introduced failures, and mutation scope inform the next attempt so retries deliberately use a different safe strategy rather than repeating the same failure. Deterministic corrections run without a model; model regeneration is reserved for source-grounded semantic/prose repair; unsupported items are removed/abstained rather than repeatedly paraphrased. Success is measured on a hash-pinned corpus of real historical repair failures.
- **What to implement, in order:**
  1. Extend the existing regeneration contracts, audit schema, and attempt result with typed `failure_fingerprint`, `repair_action`, `repair_strategy`, `allowed_paths`, selected/quarantined evidence identities, and a `RepairDelta` containing `resolved`, `persisting`, and `introduced` issue fingerprints. Preserve compatibility readers/migrations for retained v1 audits; do not create a parallel repair ledger.
  2. Reuse `validate_retained_claims()` inside the repair loop before generation where factual diagnosis is possible and again on candidate material before promotion. Convert its evidence-completeness, protected-fact, numeric value/unit, quote, and semantic dispositions into stable repair diagnostics instead of only human-readable validator messages; keep the existing candidate-integrity and full semantic/grounding/public-editorial gates authoritative.
  3. Make the planner resolve the smallest mutable unit from `public_item_id`, `entity_id`, affected field/path, and existing stable artifact IDs. Add item/field-level patch contracts and deterministic merge for summary claims/variants, individual final insights and metric fields, key figures, quotes, Expert View, LinkedIn, and other currently supported atomic public items. Family regeneration remains an explicit fallback only when the validator proves the failure cannot be isolated safely.
  4. Turn the existing artifact diff into an enforcement gate: a targeted candidate may modify only declared `allowed_paths` plus explicitly enumerated deterministic dependents. Any unrelated changed/added/removed path fails immediately as `regeneration_scope_violation`; passing fields remain byte-equivalent/canonically equivalent and the canonical artifact is unchanged on rejection.
  5. Add a deterministic repair-action classifier before model use. Supported actions include `COPY_CANONICAL_SOURCE_VALUE`, `CORRECT_PROTECTED_FACT`, `REBIND_EVIDENCE`, `REWRITE_FROM_EXISTING_EVIDENCE`, `REPLACE_WITH_ALTERNATIVE_EVIDENCE`, `REMOVE_CLAIM`, `REGENERATE_ITEM`, `REGENERATE_FAMILY`, and `ABSTAIN`. Exact evidence ID/page corrections, uniquely recoverable source displays/labels/periods/forecast markers, supported quote text, and other provable corrections must use deterministic patches rather than consuming an LLM attempt.
  6. Replace lexical-only alternative-evidence ranking with a bounded typed scorer that reuses existing quantity/protected-fact/evidence utilities and, where already available, semantic retrieval. Rank compatible alternatives by exact subject/entity, metric, geography, cohort/denominator, timeframe, observation/forecast status, quantity/unit relationship, source page/section proximity, and semantic relevance; exclude quarantined evidence and strongly penalize protected-fact conflicts. Return only the highest-quality bounded alternatives and abstain when no compatible retained evidence exists.
  7. Make the model repair contract return a structured private repair decision plus the minimal patch in the same call: diagnosed failure class, chosen action/strategy, evidence IDs used, facts/fields to preserve, fields to change, and patch payload. Keep current failed copy diagnostic-only, never evidence. Persist the decision for retry/audit but never publish it; do not add a separate critique model call solely to populate the contract.
  8. Replace homogeneous retries with a failure-class-specific strategy ladder. Default progression is: minimal correction using the current valid evidence; then rebind to the best compatible retained alternative and rewrite only the atomic item; then remove/replace/abstain the item rather than another paraphrase. After rollback, start from the last promoted baseline but feed the prior `RepairDelta` and rejected strategy/evidence fingerprint into planning; do not repeat an identical failed strategy+evidence combination or candidate hash unless inputs/validator identity changed materially.
  9. Add monotonic repair evaluation before full promotion. Measure original issues resolved, original issues persisting, new issues introduced, scope violations, evidence/lineage validity, and severity delta. Promotion still requires the existing complete pass; a rejected but partially improved candidate is retained only as repair memory, never canonical state. Stop early or move to safe removal/abstention when the strategy set is exhausted instead of increasing retry count to mask the defect.
  10. Expand the existing E13 scorecard into a hash-pinned real-failure benchmark using retained historical regeneration failures and rejected candidates across summary, insight/metric, quote, Expert View, LinkedIn, and public-editorial hard-fail classes. Retain baseline artifact/evidence packs, initial validation, expected legal mutation scope, prompt/policy/schema/validator identities, and outcome; do not hand-author successful replacement prose. Report valid repair success@1/@3, residual failure odds, newly introduced hard failures, out-of-scope mutation, repeated strategy/candidate hashes, deterministic-versus-model repair share, calls/tokens/cost/latency, and abstention separately.
- **Acceptance criteria:**
  - Canonical rollback/promotion safety is unchanged: every attempt begins from the last promoted artifact, no rejected candidate can become canonical input, and full existing schema, evidence-lineage, grounding, semantic, public-editorial, readiness, and publication guards remain active.
  - Atomic targeted repair produces **zero out-of-scope mutation** on the retained real-failure corpus. A fixture that changes an unrelated family/field is rejected before promotion with a stable scope-violation reason, while explicitly declared deterministic dependents remain auditable.
  - A rolled-back attempt contributes a typed `RepairDelta` and strategy/evidence fingerprint to the next plan. Tests prove attempt 2 can start from the unchanged promoted baseline while avoiding an identical failed strategy/evidence combination and explicitly accounting for failures introduced by attempt 1.
  - `validate_retained_claims()` is reused in the central candidate path for supported factual material; numeric, quote, protected-fact and evidence-reference mismatches become structured repair diagnostics without weakening or bypassing the existing authoritative validators.
  - Every uniquely provable deterministic repair path performs **zero model calls** and preserves exact source-supported value/unit/label/timeframe/forecast/quote/evidence-page semantics. Ambiguous corrections abstain or escalate rather than guessing.
  - Alternative evidence selection never returns a quarantined ID, and retained fixtures with same-number/wrong-geography, wrong-period, wrong-cohort/denominator, forecast-vs-observed, or conflicting metric relationships rank the compatible source above lexical near-matches or abstain when none exists.
  - Retry strategies are materially distinct and bounded. The system never repeats an identical rejected candidate hash or identical failure-fingerprint+strategy+evidence combination without a material input/validator change; exhausting safe strategies ends in typed removal/abstention/failure rather than unbounded regeneration.
  - The hash-pinned real-failure benchmark reports complete denominators and version-compatible cohorts. The promoted implementation demonstrates at least **90% valid repair success@3** and a **10× reduction in residual repair-failure odds versus the exact retained baseline where baseline mathematics permits it**; if baseline success is already too high for a literal 10× odds reduction, it must reach at least **95% valid success@3** and document the ceiling calculation. Abstention/removal, invalid promotion, or suppressed failures cannot be counted as successful repair.
  - New hard-failure introduction is below **2% of attempts**, unsupported/hallucinated evidence introduction is **0%**, and improvement does not come from weaker validators, broader mutation scope, publisher/report-specific exceptions, higher retry limits, or materially higher average repair cost. Compatible before/after evidence retains calls, tokens, cost, latency, success@1/@3, and failure-class distributions.
  - The read-only E13 scorecard remains evidence-safe: it exposes bounded IDs/hashes/counts/usage/strategy/failure classes only, never raw source text, prompts, candidate/model responses, or unpublished repair diagnostics; no scorecard command automatically mutates prompt, routing, evidence, or validation policy.

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
  1. Establish a retained human-labelled production crop corpus of roughly **50–100 visuals across 15–20 materially different publishers/report layouts**, with target visual identity, expected/acceptable bbox, required semantic components, defect edge/type, publication-ready decision, and exact source/producer hashes. Stratify ordinary charts/tables plus dashboards/multi-panel figures, external/shared legends, dense labels, rotated content, raster/vector mixtures, dark/coloured backgrounds, full-bleed slides, footnotes/sources, multi-column tables, and continued/multi-page tables. Measure candidate recall separately from bbox completeness so discovery misses are not confused with crop failures.
  2. For the small set of final ranked publication candidates, make visual crop localization mandatory until retained evidence proves a boundary-confidence skip is equivalent. Feed the model both an annotated full-page image with the candidate box visibly marked and a higher-resolution local context image around the candidate (roughly **180–220 DPI**); map the returned geometry deterministically back to PDF coordinates.
  3. Make the crop-refine objective explicit and ordered: **semantic completeness → exclusion of unrelated neighbours → safe margin → tightness**. Define required components separately for charts and tables and prefer a small margin over uncertain exclusion of an attached title, label, legend, note, or source. Label whether a panel is independently meaningful or requires a shared title/legend; treat a continued/multi-page table as ineligible for a single crop unless the complete reading order and repeated-header relationship are proven.
  4. Simplify post-model geometry to safety guardrails rather than repeated re-cropping: normalize page rotation/crop-box/media-box transforms, intersect with the physical page, fall back to the original candidate bbox on invalid/empty model output, expand for meaningfully intersected text/table rules/attached components, add a small safety margin, and prohibit heuristic inward shrink unless the removed region is provably whitespace/unrelated. Never convert an invalid model bbox into a whole-page crop.
  5. Standardize every crop that can become public to the configured final publication resolution (**216 DPI** under the current profile). Treat candidate-pack/preview crops as previews; do not reuse a lower-DPI cached crop as the final public asset unless its sidecar proves the required publication DPI/profile.
  6. Reduce raster trimming to conservative, provable background removal with a small per-edge cap and retained safety padding. Remove clipped-content defects from inward trim repair; a crop that is missing content cannot be repaired by deleting more pixels.
  7. Implement directional bbox repair with at most one bounded rerender by default: neighbour contamination shrinks only the offending edge; clipping or a missing semantic component expands only the relevant edge. Retain before/after bbox, defect edge/type, repair action, render profile and QA result in the sidecar.
  8. Make final QA type-aware and rejecting: table validation checks outer-rule/text crossings plus complete headers/rows/columns where detectable; chart validation checks all four edges and protects title/legend/axes/labels/annotations/source. Reject a whole-page or near-whole-page result when the labelled target is a smaller semantic visual, and reject unsupported panel separation or incomplete continued tables. Normalize defect labels so deterministic QA, escalation and release gates use the same canonical taxonomy.
  9. Run the retained corpus through the actual `publication_strict` path before and after the change, including the model-localization path where applicable. Use the human labels—not the cropper's own score—as the primary correctness outcome; only after the target is met should adaptive skipping or heuristic deletion be reconsidered for cost/speed.
- **Acceptance criteria:**
  - On the retained representative corpus, **100% of accepted publication crops** receive a human `publication_ready` decision with no blocking semantic clipping, wrong-panel selection, unrelated-neighbour contamination, incomplete continued table, or missing required title/axis/label/legend/header/row/column/note/source. At least **95% of human-labelled eligible visuals** produce an accepted publication-ready crop; the rest are explicit typed rejections/escalations, so precision cannot be achieved by rejecting everything.
  - The before/after corpus shows a material reduction in clipping and neighbour-contamination defects versus the exact retained baseline with no material regression in candidate recall or selected-visual usefulness.
  - Invalid/out-of-page/empty model geometry never becomes a whole-page crop; it deterministically falls back to the original candidate geometry or a typed rejection.
  - `edge_clipped_content`/missing-component failures can only trigger bbox expansion/rerender or rejection, never an inward PNG-only trim; neighbour contamination can only shrink the implicated edge.
  - Table completeness rejects a demonstrably cut boundary/header/row/column and any incomplete continued/multi-page table represented as complete; chart completeness evaluates all four edges. Multi-panel/shared-legend fixtures keep exactly the human-labelled semantic unit and required shared components, while near-whole-page false fallbacks are rejected.
  - Rotated pages and non-default PDF crop/media boxes map annotated/local model geometry back to the same intended PDF region within the retained tolerance; no transform error can silently select another panel or clip a required edge.
  - Every final public crop sidecar proves the configured publication DPI/profile, and lower-DPI preview/fallback artifacts cannot silently enter the public asset set.
  - Focused tests cover annotated/local vision inputs, invalid-bbox fallback, directional repair, four-edge chart validation, table-boundary rejection, conservative trim, DPI reuse, and sidecar taxonomy; the retained production-strict golden/human corpus passes on the exact implementation SHA.
  - The final selected-visual path remains bounded: no more than the configured localization call plus one repair/rerender per candidate by default, and no new model/library is introduced unless the retained corpus proves the existing stack cannot reach the target.

#### E16. Make methodology, applicability, and uncertainty decision-grade

- **Baseline:** Methods and limitations are extracted, validated, and projected through existing evidence/readiness paths, but the persisted contracts are too loose for expert interpretation: method entries may be strings or unconstrained objects and limitations are plain strings. The system cannot reliably distinguish a source-reported sample, fieldwork period, geography, weighting/model basis, forecast assumption, applicability constraint, or an actual absence of disclosure; nor can it deterministically show which claim or recommendation each constraint qualifies. P8 owns concise public presentation and P16 owns advisory synthesis, so this item owns the underlying typed methodology and applicability evidence.
- **Target behaviour:** Material methodology, scope, limitation, and uncertainty facts are versioned, source-linked, and machine-checkable. Missing disclosure remains an explicit unknown rather than an inferred weakness or invented fact. Claims and decision guidance are qualified or withheld when the evidence's population, geography, period, definition, method, or uncertainty does not support the proposed interpretation.
- **What to implement, in order:**
  1. Build a retained, human-labelled corpus spanning surveys/panels, market sizing, financial/administrative data, modelled forecasts, experiments, interviews/thought leadership, mixed-method reports, and reports with no usable method section. Label explicit sample/base, population, geography, fieldwork/data period, collection mode, weighting, coverage, metric definition, model/forecast basis, source-stated uncertainty, limitation, conflict, and applicability facts with exact evidence locations.
  2. Replace the loose methods/limitations payloads with a versioned typed contract and a compatibility migration/reader for retained legacy artifacts. Use a finite fact taxonomy and explicit states such as `reported`, `not_reported`, `not_applicable`, and `conflicting`; bind every reported fact to approved evidence identity and page/span provenance.
  3. Extend the existing methods/limitations prompt family and deterministic extractors rather than adding a parallel model step. Parse explicit dates, sample sizes, geographies, bases, units, and definitions deterministically where possible; validate all probabilistic output against source evidence and preserve abstention when the source is silent.
  4. Derive finite, explainable applicability/evidence-strength outcomes for the claims and decisions that depend on these facts. Record reason codes and the relevant scope mismatch or unknown; do not manufacture statistical confidence intervals, methodological quality scores, or causal strength when the source does not provide the inputs.
  5. Make claim validation, P16 decision synthesis, summaries/expert commentary, and cross-report comparison consume the same applicability constraints. P8 projects a concise safe subset publicly; internal provenance, diagnostics, and unsupported inferred judgments remain non-public.
  6. Add contract round-trip/schema snapshots, legacy-artifact migration tests, labelled-corpus extraction/grounding tests, contradiction/scope-mismatch fixtures, thin-source abstention fixtures, and retained expert-review evidence on the exact implementation SHA.
- **Acceptance criteria:**
  - Every accepted reported methodology/limitation fact has exact approved-source evidence identity and page/span provenance; no accepted fact invents sample size, fieldwork, weighting, geography, definition, uncertainty, model basis, or limitation.
  - On the retained labelled corpus, explicitly stated material facts achieve at least **95% recall**, while **100% of facts admitted to public or decision synthesis are human-verified correct and source-supported**; misses/rejections are reported separately so precision cannot be raised by suppressing the corpus.
  - Missing or ambiguous disclosure produces a typed unknown/conflict with an actionable reason, never a fabricated value, unqualified quality score, or silent assumption.
  - Every material claim or action whose applicability is limited by population, geography, period, definition, method, or uncertainty is explicitly qualified or withheld; incompatible scopes are never merged into one comparable trend.
  - Two independent methodology reviewers reach at least **90% agreement** with the system's supported/limited/unknown decisions on the retained cohort, with disagreements retained by reason code for remediation.
  - The change adds no provider call beyond the existing evidence/methods generation path, preserves legacy artifact readability through the declared transition, and passes schema, grounding, claim-validation, P6/P8/P16, readiness, and publication-projection tests.

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

#### R7. Prove recoverable backups and full-state disaster restoration

- **Baseline:** Durable queues, checkpoints, remediation ledgers, idempotency records, lineage, and artifact hashes support process-level recovery. Quality evidence can take read-only SQLite snapshots, but the operational state spans mutually dependent SQLite stores, retained source/artifact trees, manifests, configuration identities, and publication checkpoints. There is no canonical cross-store backup set, atomic completion marker, isolated restore workflow, or retained drill proving that a lost host can recover coherent state without duplicate external writes.
- **Target behaviour:** A backup is considered restorable only when one manifest proves a consistent, complete, integrity-checked snapshot of all required state. Restore occurs into an empty isolated target, validates schema/lineage/artifact closure before activation, and produces a reviewable resume plan. It never silently overwrites live state or replays WordPress, Drive, browser, mailbox, or model side effects.
- **What to implement, in order:**
  1. Inventory the canonical databases, WAL/sidecar requirements, artifact/source roots, queue/checkpoint/idempotency state, configuration/schema identities, and publication references required for each supported recovery profile. Classify sensitive/source material, retention, ownership, and dependencies; exclude reproducible caches only when the manifest records how they are safely rebuilt.
  2. Define a versioned backup-set manifest with snapshot ID/time, producer SHA, profile, schema versions, queue/checkpoint watermarks, database and artifact hashes/sizes, referential dependencies, retention/access-control metadata, and a final completeness marker. Standard logs retain only bounded identifiers/counts/hashes, never backed-up content or secrets.
  3. Implement consistent snapshot creation behind the existing filesystem/database service boundaries: coordinate writers, use SQLite's supported online backup/transaction semantics, copy immutable files only after referenced state is fixed, verify each member, and write the completeness marker last. Any interruption leaves an identifiable non-restorable set rather than a plausible partial backup.
  4. Add offline verification for SQLite integrity/foreign keys, hashes, schema compatibility, artifact/source referential closure, queue/checkpoint/idempotency coherence, manifest authenticity, retention, and destination access controls. Reject truncated, tampered, mixed-snapshot, missing-member, stale-schema, or unsupported-version sets with typed remediation.
  5. Implement restore only to an empty isolated target. Re-run approved migrations where required, verify the restored state again, and emit a deterministic resume/read-only reconciliation plan showing held/runnable work and external records that require authoritative readback. Activation or replacement of a live installation remains an explicit operator procedure with a documented rollback.
  6. Run retained disaster drills from a representative in-flight cohort, including crash points during snapshot, corrupted/truncated members, missing artifacts, WAL activity, and restoration followed by the bounded discovery-to-publish validation workflow in zero-write mode. Document the operator procedure, storage protection, declared objectives, evidence path, and recurring drill responsibility without adding an in-process scheduler.
- **Acceptance criteria:**
  - The supported single-host profile declares an **RPO of no more than 24 hours and an RTO of no more than 4 hours**, and a retained exact-SHA drill restores a representative in-flight state within those objectives.
  - After restore, all database integrity/foreign-key checks pass; every required source/artifact/lineage reference resolves to the declared hash; queue, lease, checkpoint, budget, remediation, and idempotency states reconcile to the manifest with no orphaned or cross-snapshot records.
  - An incomplete, interrupted, truncated, tampered, mixed, or unsupported backup never receives a restorable marker and fails closed with a typed, actionable reason before activation.
  - Restore to a non-empty/live target is blocked by default. The drill performs no provider, Drive, mailbox, browser, or WordPress write, and resuming/replaying restored publication work produces no duplicate public side effect.
  - Backup and restore logs, manifests, tests, and retained evidence expose no credential, prompt/model payload, source text, email content, or personal data; backup storage containing sensitive material uses the documented access-control and encryption-at-rest mechanism.
  - Focused tests cover consistent SQLite/WAL snapshotting, writer interruption, missing/tampered artifacts, cross-snapshot mixing, schema migration/compatibility, empty-target enforcement, lineage/idempotency reconciliation, and zero-write resume; the documented full drill is repeatable from one canonical command.

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
- Current preflight, browser-doctor, synthetic smoke, queue recovery, exact-HEAD canaries, and editorial cohorts provide valuable partial proofs, but no single profile-derived doctor or representative first-attempt SLO yet proves that a clean installation can complete the selected workflow without operator repair.
- Existing reports have strong evidence, summary, insight, counter-signal, and expert-commentary capabilities, but decision logic, methodology applicability, narrative composition, and visual selection are not yet governed by one typed consultancy-grade story model.
- Durable process recovery does not yet amount to disaster recovery: the mutually dependent databases, artifact trees, lineage, queues, and idempotency records lack a retained consistent backup/restore drill.

## Audit Notes

- Full repository/backlog/architecture/configuration/CLI/workflow/prompt/schema/test/operations/WordPress reconciliation was refreshed on 2026-09-07 against exact committed HEAD `957ad6ceab767ac91529e461f72c6a32e0665c83`. Pre-existing uncommitted evidence-fidelity work was inspected for overlap but is not claimed as completed capability.
- The register contains **30 Active outcomes**, and each has one matching execution section with baseline, target behaviour, ordered implementation work, and measurable acceptance criteria.
- A20 and A21 are net-new first-run-success owners: A20 proves clean-room capability readiness before side effects, while A21 measures representative first-attempt conversion through review readiness and approved sandbox readback. They do not duplicate A18/A19 route hardening, A3/A10 recovery, or P12/P14 release-locked canaries.
- P16 and P17 are net-new consultancy-quality owners: P16 governs a single evidence-to-decision synthesis; P17 governs bounded adaptive composition and non-repetitive visual storytelling. P6 remains the cross-cutting human acceptance gate and P8 remains the concise public evidence surface.
- E16 owns typed source methodology/applicability semantics beneath P8/P16. R7 owns cross-store disaster restoration, which is distinct from process-level queue/checkpoint recovery and quality-evidence snapshots.
- E15 was strengthened after direct review of current `publication_strict` outputs under `out/evidence_fidelity_iab_20260907_r5`: `chart-33-0.png` and `chart-38-0.png` visibly clip attached text/source content, while `table-53-0.png` retains a near-whole-page narrative region. Their QA sidecars nevertheless record `accepted: true` with no defects, so acceptance now requires **100% human publication-ready precision**, at least **95% eligible-visual coverage**, type-aware panel/table completeness, and fail-closed rejection/escalation for the remainder.
- P3 is correctly Deferred for production-host migration rather than counted as a temporary-sandbox MVP blocker.
- Historical canonical IDs previously present only in closure prose/context remain restored to the Unified Work Register: A5, A12, A13, P0, P9, P11, E1, E2, E5, E7, R4, S1, S2, and D10.
- The obsolete statement that closed A3/A6 remained Active is removed; E3 no longer delegates current work to already-closed E7.
- C6, P11, and A14 closure wording remains narrowed to the capability/tooling actually proven so A18/A19 own current production-hardening work without contradiction.
- Public-site states distinguish implemented-but-unverified outcomes from missing implementation, and intentional sandbox HTTP from production transport requirements.
