# Consolidated TODO

Last reconciled: 2026-10-08 (reviewed `main` at `207d62133cf8b94b1745c883f2e3a80536466509`).
Audit basis: the comprehensive source/status audit was performed on 2026-10-05 at `da40362f08699b37b66a9fddfae7cd43ad0f1417`; this update reconciles subsequent October 7–8 commit diffs, selected affected implementation boundaries, tests added in those commits, and the autonomous-MVP publication policy against existing backlog ownership. This is a *delta reconciliation*, not a new exhaustive source audit, passing test run, provider run, hosted smoke, human crop/editorial review or full-pipeline measurement. Retained measurements retain their original producer SHAs and cohorts. Sandbox HTTP remains intentional; hosted and human gates remain open until independently proved.

This is the repository's single, source-neutral work register. Every canonical task ID appears once in the Unified Work Register. Historical evidence may explain a closure, but it must not redefine current status.

## How to Use This Backlog

- The Unified Work Register is the canonical status source. Every `Active` row must have one matching detailed section in **Active Backlog** with a baseline, target behaviour, ordered implementation work, and acceptance criteria.
- `Deferred`, `Closed`, and `Excluded` items remain visible in the register but do not need active execution detail.
- Activate work only when the outcome and completion evidence are clear enough to execute. A separate issue/plan, named owner, target date, or review date is optional unless the work itself requires one; do not create process records solely to satisfy the backlog.
- One item owns one outcome. Merge overlapping requests into the existing owner rather than creating parallel tasks.
- `10improvements.md` is a supporting proposal catalogue, not another status ledger. Verify its premises at implementation HEAD and use the canonical owner here; a recommendation is not proof of implementation or automatic authority to activate duplicate work.
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
| Active | A15 | Complete explicit model-policy coverage and policy-effectiveness evidence | Prove fallback reachability, remove live compatibility-default calls and extend existing effectiveness evidence. |
| Closed | A16 | Durable corpus rehabilitation campaign execution | Review-gated retained-evidence campaigns enqueue idempotent repair work without public writes. |
| Active | A17 | Calibrate deterministic admission thresholds from retained preflight funnels | Produce read-only compatible-cohort threshold proposals without automatic admission changes. |
| Active | A18 | Harden discovery recall and authoritative acquisition handoff | Establish ground-truth recall, reversible candidate state, executable recovery, and a lossless authoritative qualification handoff. |
| Active | A19 | Harden acquisition routes, terminal semantics, and artifact verification | ZIP limits and read-only UID-based IMAP identity have scoped fixes; cross-route verified-artifact semantics, truthful form/mail state and economics still require proof. |
| Active | A20 | Prove clean-room capability readiness before first external work | Turn profile intent into a complete, redacted capability/dependency proof with exact remediation before any costly or mutating operation. |
| Active | A21 | Establish a representative first-attempt end-to-end reliability SLO | Recent validation, cache, queue/outbox and Signal integrity fixes require one current-HEAD first-attempt cohort and sandbox replay; opt-in auto-approval also requires release-safety reconciliation. |
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
| Closed | P12 | Release-locked sandbox publish canary | Historical isolated three-report canary at release SHA `6999c85f69fdf9ac23780b1abff0b06adf1c4979` retained authenticated readback and zero-write replay; not proof for later HEADs. |
| Closed | P13 | Make WordPress file-ID lookup independently authoritative | Authenticated immutable file-ID lookup reuses matching posts, fails closed on ambiguity, and preserves no-write reuse. |
| Closed | P14 | Retain isolated live proof of strict cohort-manifest publication binding | The recorded isolated release cohort bound only admitted members and replayed without WordPress writes; later releases require separate proof. |
| Closed | P15 | Operate canonical publish-readiness telemetry and refresh planning | Typed deterministic refresh plans route only proven minimum recovery work. |
| Active | P16 | Build a decision-grade consulting synthesis artifact | Create one evidence-bound decision model that makes implications, options, trade-offs, risks, unknowns, and conditional actions coherent across public surfaces. |
| Active | P17 | Compose adaptive, non-repetitive visual report stories | Replace one fixed content sequence with a bounded composition plan that gives each source a clear narrative and uses only E15-approved visuals. |
| Closed | E1 | Claim-embedding freshness, retention, and cost controls | Due-work selection, leases, budgets/retries, health telemetry, and live bounded embedding proof are implemented. |
| Closed | E2 | Retained-artifact benchmark | Briefing/Signal prompt-token deltas, overlap/source coverage, and no-vector fallback are measured. |
| Closed | E3 | Lineage-driven minimum regeneration | Deterministic minimum regeneration authority and render-only enforcement are implemented. |
| Closed | E4 | Executable retained PDF benchmark corpus in CI | Hash-pinned deterministic regression corpus is CI-gated; E15 owns independent human semantic crop acceptance. |
| Closed | E5 | Crop-QA scorecards and selection telemetry | Retained crop-QA sidecars support operator-only quality/clipping/storage scorecards. |
| Active | E6 | Retain a hash-pinned claim-embedding benchmark export | Persist approved vectors for reproducible zero-provider semantic benchmarking. |
| Closed | E7 | Planner-enforced artifact-family reuse | Retained render/crop/checkpoint/publication reuse is planner-enforced with plan/actual reconciliation; report-card replay checks content/source/region/style identity and all three assets before reuse. |
| Closed | E8 | Use canonical source identity to suppress duplicate research work | Exact identity/content-hash package reuse is implemented with retained evidence. |
| Closed | E9 | Materialize prompt-family outputs and route only required model calls | Implemented registered-family pre-call reuse includes newer editorial-plan identity repair; A21 owns broader interruption/first-attempt proof and E12 category-only checkpoints. |
| Active | E10 | Attest active model-pricing rates before they become stale | Keep cost attribution and spend enforcement trustworthy as provider pricing changes. |
| Closed | E11 | Measure and optimize structured-output recovery effectiveness | Historical isolated three-report cohort retained 100% first-pass structured validity, zero repair cost/tokens and active downstream gates; not universal current semantic/editorial success. |
| Active | E12 | Persist pre-category editorial context checkpoints | Extend typed recovery to genuinely category-only retries. |
| Active | E13 | Measure candidate-regeneration promotion effectiveness | Atomic/adaptive foundations exist; prove strict frozen-corpus effectiveness, scope/evidence safety and complete compatible attribution. |
| Active | E14 | Calibrate category-fit coverage from retained outcomes | Turn retained category-fit decisions into grounded mapping/prompt proposals. |
| Active | E15 | Make publication crops visually complete and repairable | Affine coordinate and invalid-bbox guards have scoped fixes; semantic completeness, directional repair, publication-DPI consistency and human-labelled production acceptance remain unproved. |
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

- **Baseline:** Model-call audit/replay contracts and a no-provider replay builder exist (`src/services/_llm_service/audit.py`). Bundles retain prompt/model/schema/cache and usage/validation fields but do not guarantee selected-evidence, execution-policy or output/artifact identities. Canonical zero-provider comparison/disposition remains unimplemented; join compatible retained artifacts safely and classify missing provenance incomplete rather than equivalent.
- **Target behaviour:** A read-only comparison command accepts two compatible replay bundles and deterministically explains whether they are equivalent, compatible-but-changed, incomplete, malformed, or materially regressed. It never calls a provider and never emits retained prompt/source/model-output content.
- **What to implement, in order:**
  1. Define one typed comparison request/response contract around baseline bundle, candidate bundle, artifact family, and optional compatibility expectations.
  2. Inventory safe bundle/linked-artifact fields; add a versioned adapter/link for retained evidence, policy, output and artifact identities. Extract only provenance-proven fields and distinguish absent, unknown and malformed values before comparison.
  3. Implement deterministic field-level classification for equivalent, expected-compatible change, material regression, missing evidence, and malformed bundle cases; bound the output and preserve stable ordering.
  4. Add a CLI/operator surface that prints the summary and references retained artifacts without provider construction or external writes.
  5. Add fixtures from real retained bundles and document the command in the existing recovery/evidence workflow rather than creating another evidence system.
- **Acceptance criteria:**
  - Equivalent bundles produce an identical deterministic result across repeated runs and no false regression.
  - Changed prompt/policy/evidence/schema/output cases identify the exact changed safe fields and artifact family without printing prompt, source, or model-response text.
  - Missing and malformed bundles fail with typed bounded diagnostics rather than partial success. Evidence/policy/output identity cannot be inferred from prompt/model equality; legacy bundles remain explicitly incomplete.
  - Tests cover equivalent, changed, missing, malformed, and deterministic-order cases and prove zero provider calls/external writes by default.

#### A15. Complete explicit model-policy coverage and policy-effectiveness evidence

- **Baseline:** Production configuration/namespace preflight, registered prompt policies and retained policy matrices already exist. Compatibility-default behavior remains where registration is not required, and empty injected policy settings can skip matrix checks; reconcile production reachability instead of asserting an observed live bypass. Legacy config adaptation is distinct from provider-call fallback. `policy-effectiveness` already projects calls, validity/cache, latency coverage, tokens/cost and regeneration counts; attributable compatible-cohort quality conclusions remain open.
- **Target behaviour:** Every reachable production model call resolves through one explicit versioned policy with no compatibility fallback. Operators can compare compatible policy cohorts for calls, validity, reuse, latency, tokens, cost, and validated-output quality without changing routing automatically.
- **What to implement, in order:**
  1. Reconcile actual provider call sites against the finite registry/preflight matrix, including registration-disabled resolution, empty injected policy settings and test-only overrides. Separate supported legacy config adaptation from live compatibility-default fallback.
  2. Replace only proved reachable provider-call compatibility fallbacks with explicit registered resolution; preserve routing/model/timeouts/retrieval/schema/retry/cache behavior and explicit test-only seams.
  3. Preserve existing startup/prompt fail-closed checks, policy identity and cache invalidation; cover any uncovered direct-call boundary rather than rebuild preflight.
  4. Extend existing policy-effectiveness output with attributable compatible-cohort sample/coverage, unavailable cost/latency/validation and validated-output quality linkage. Define actual-provider versus reuse denominators; schema validity alone is not editorial quality.
  5. Run retained-corpus and bounded live evidence for representative high-cost namespaces; produce operator-reviewable no-change/recommendation conclusions only when compatibility/sample requirements are met.
- **Acceptance criteria:**
  - No reachable provider call uses compatibility-default fallback; unregistered production namespaces fail before provider construction/I/O. Supported legacy configuration adaptation remains distinct.
  - Policy hashes invalidate incompatible cache/replay reuse while preserving valid compatible reuse.
  - Retained and bounded live checks cover all production policy families and show complete bounded effectiveness fields or explicit `insufficient_evidence`/unknown states.
  - No command automatically changes model/provider/policy from effectiveness results; existing semantic/output contracts and retry ownership remain unchanged.

#### A17. Calibrate deterministic admission thresholds from retained preflight funnels

- **Baseline:** Admission decisions and hashed funnel records exist, but compatible threshold calibration/proposals remain absent. Required-work forecasting covers configured evidence families (default `doc_map`), not the complete source-to-review-ready pipeline. Rejected-source outcomes are censored unless independently labelled/replayed; admitted-only success cannot establish false-rejection rates or safe threshold changes.
- **Target behaviour:** A read-only calibration surface compares only compatible admission cohorts, quantifies cost/work avoided versus downstream completion/validation quality, and emits threshold proposals only when minimum sample/confidence/improvement gates are met. It never mutates admission policy.
- **What to implement, in order:**
  1. Define the compatibility key for admission cohorts from preflight/policy/configuration/runtime decision hashes and exclude incompatible versions deterministically.
  2. Build a read-only funnel report for each threshold family: native-text, page/size limits, evidence-potential, duplicate/quarantine and related deterministic rejection reasons.
  3. Join bounded downstream outcomes to admitted cases so the report can show completion/validation rates and provider/vector/model work actually incurred or avoided. Declare the forecast horizon/stages and forecast-versus-actual attribution. Rejected cases stay censored/unknown without independent labels or controlled shadow replay; missing prices/excluded stages cannot become a complete zero-cost estimate.
  4. Add counterfactual threshold proposal logic with configured minimum sample, confidence, and material-improvement gates; report an impact range and abstain on weak/noisy evidence.
  5. Add CLI/tests and one bounded retained/live replay proving the report is deterministic and side-effect free.
- **Acceptance criteria:**
  - Incompatible decision versions never enter the same cohort or proposal.
  - The report exposes denominator, admitted/rejected outcomes, downstream completion/validation, and avoided provider/vector work using bounded metadata only.
  - Threshold proposals include exact compatible decision hashes, sample/confidence evidence, and counterfactual impact; insufficient evidence produces an explicit no-change result.
  - Tests prove deterministic ordering and zero model/vector/external writes; no threshold/configuration is modified automatically.

#### A18. Harden discovery recall and authoritative acquisition handoff

- **Baseline:** HTTP/browser discovery, semantic screening, landing qualification, snapshots and route memory exist. Low HTTP confidence is still filtered before screening; URL presence drives novelty, cached candidates dominate recovery and acquisition queue payloads lose qualification context. Domain/social-host matching, title-only deduplication and shrinkage checks on mixed partial refreshes add deterministic risks. Ground-truth recall, reversible decisions, executable recovery and lossless handoff remain open; incident rates are unmeasured.
- **Target behaviour:** Discovery is high-recall, reversible, and the single authority for report qualification. Acquisition receives the complete typed qualification context and decides *how* to obtain the report rather than independently re-deciding *whether* it is a report. First-run completeness and deferred recovery are explicit and executable.
- **What to implement, in order:**
  1. Retain a hash-pinned gold corpus of roughly 15–20 representative publishers and known report URLs spanning static, pagination, JS-hydrated, mixed-content, gated, multilingual, direct-PDF, and external/microsite cases; score recall and precision independently of production discovery.
  2. Convert the HTTP `0.60` confidence cutoff to ranking/triage for plausible candidates; reserve deterministic hard rejection for indisputable junk. Treat English keywords, multilingual evidence, and same-domain status as features rather than eligibility requirements. Correct compound/public-suffix host identity and exact-or-subdomain social matching; union ordinary and embedded-card observations instead of suppressing existing extraction when header anchors exist.
  3. Separate observation from decision state with lifecycle (`observed`, `screened`, `qualified`, `acquisition_attempted`, `acquired`), decision/policy hashes, reason/confidence/time, and deterministic re-screen conditions. Missing model decisions stay undecided/deferred with orchestrator-owned bounded recovery. Do not reject distinct editions/routes by title alone; merge only qualified aliases with retained route evidence.
  4. Route typed deferred-recovery recipes through the existing durable queue/remediation boundary with bounded attempts/idempotent terminal states, or remove `scheduled` terminology where no executor exists.
  5. Introduce one lossless typed qualified acquisition context carrying canonical URL/title, candidate PDF URL, source-page URLs, discovery provenance/confidence, route recommendation, and qualification/policy identity through the durable queue.
  6. Bypass the ad-hoc report-likelihood readiness classifier for discovery-qualified candidates; keep it only for direct/ad-hoc URLs that did not pass discovery.
  7. Require bounded first-run completeness proof (terminal pagination, declared total/structured source agreement, sitemap/archive corroboration, or one verification browser pass) before the first snapshot becomes authoritative. Preserve prior qualified identities on unexplained partial refresh even when one new report exists; require completeness proof before interpreting disappearance as removal.
- **Acceptance criteria:**
  - Fixed gold corpus reaches at least **97% report recall** with no material precision regression from the retained baseline; recall and precision are reported separately.
  - Mixed accepted/rejected delta fixtures prove a false negative remains eligible for later re-screening, and policy-hash changes can reconsider prior decisions without a new URL observation.
  - Plausible multilingual/external-host/report-detail cases are not hard-dropped solely for missing English tokens/domain equality; obvious junk stays deterministic/no-model.
  - At least one retained deferred-recovery case executes through the canonical durable path to `recovered|failed|held` with bounded attempts and idempotent replay.
  - The production worker receives the same candidate PDF/source-page/provenance/route evidence available to direct/audit execution.
  - Discovery-qualified candidates reach route planning without a second report-likelihood rejection; direct/ad-hoc URLs retain the fail-closed readiness guard.
  - First-run snapshots cannot become long-lived baselines without an explicit completeness proof.

#### A19. Harden acquisition routes, terminal semantics, and artifact verification

- **Baseline:** Route execution/terminal budgets, required Drive-archive preflight, retained-file/MD5 handoff and route economics exist. Cross-route structural/completion semantics remain incomplete: polling can follow `email_required` without a verified submission watermark, mailbox materialization precedes relevance/structural checks, and route/source learning can precede required archive completion. Extend these boundaries rather than rebuild browser, archive, polling or budgets.
- **Target behaviour:** Every acquisition mechanism converges on one ingest-compatible structurally verified artifact definition with truthful terminal states, bounded resource use, and mechanism-level economics. Cheap deterministic paths remain first; Browser Use stays a last resort.
- **Current scoped evidence (through 2026-10-08):** Mailbox ZIP attachments have code-owned resource ceilings and typed per-attachment failures with sibling continuation (`bafd72ed`). IMAP mailbox selection is read-only, and UID/UIDVALIDITY identity handling is covered by focused tests (`207d6213`, `src/services/mailbox_acquisition_service.py`). These are bounded slices, **not** closure of cross-route PDF verification, form-submission semantics, route economics or live-mailbox delivery proof.
- **What to implement, in order:**
  1. Correct terminal/mail semantics: only verified `email_requested` may enqueue mailbox work; `email_required` is identity/configuration hold. Carry verified form-submission timing/request identity into mailbox payloads. Split broad access blockers into rate-limit/transient, JS/WAF challenge, CAPTCHA, authentication, forbidden/access-blocked, and terminal not-found classes. Carry a verified submission event ID/timestamp and effective configuration across acquisition/mailbox queue redelivery; URL identity alone cannot identify a new request.
  2. Reuse the canonical `pdf-integrity-v1` structural checks before success, route-memory promotion, cache population, durable archive completion, or ingest handoff for HTTP, browser, mailbox/ZIP, cache, private-API and specialist PDF outputs. Distinguish `artifact_verified_locally`, `artifact_archived`, and `acquisition_complete`.
  3. Harden HTTP/cache without making them browser-first: permit one evidence-triggered browser recovery when an apparent direct PDF proves to be HTML/WAF/viewer content; rank embedded/opaque/extensionless PDF candidates from explicit candidate evidence, DOM/CTA relation, MIME/response evidence and source relation before lexical hints; revalidate mutable cache entries with available ETag/Last-Modified/final URL/content-length/version evidence.
  4. Gate browser side effects: automatic pre-LLM form submission runs only for `browser_email_form` or strong proven report-delivery form evidence; generic PDF-click pages cannot submit newsletter/contact/demo forms. Keep deterministic playbooks/private APIs ahead of Browser Use where eligible; use a generic acquisition prompt when route family is genuinely uncertain.
  5. Make listing-hub recovery exceptional/self-healing by persisting the resolved canonical detail/download target back to source/discovery state for the next run.
  6. Unify onsite/specialist completeness: one evaluator for direct HTTP/browser capture; truncated content is never complete; HTML/Markdown remain support artifacts while ingest is PDF-only; Adobe text-only output is labelled explicitly; Issuu retains all-declared-pages verification with bounded concurrency/disk streaming.
  7. Make mailbox acquisition metadata-first and bounded: rank sender/subject/timestamp/body snippet/attachment metadata/anchor text before materialization; share affinity scoring for links and attachments; bound ZIP member count/single+total decompressed bytes/compression ratio/PDF count; suppress by message+exact normalized URL+failure class; continue through bounded lower-ranked candidates after candidate-specific failures; improve IMAP filtering/windowing. Preserve signed delivery URLs, use stable provider message IDs and nonmutating IMAP reads, and schedule due polls durably instead of occupying workers during long waits; retain finite expiry/read budgets.
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

- **Baseline:** Profiles, path/LLM/prompt preflight, browser-doctor, dependency locks and canaries exist, but not one complete profile-derived capability proof. Path checks can create directories and write/delete fixed-name probes; successful policy preflight persists a matrix. These are reversible local probes, not a zero-local-write doctor. Distinguish no default external writes from uniquely scoped local probe/output writes and retain missing/skipped prerequisite evidence.
- **Target behaviour:** One capability doctor with no default external writes resolves exact intent/profile stages and capabilities before costly/mutating workflow work. Explicit local probes/proof artifacts are uniquely scoped, cleaned or declared and safe under concurrency. It distinguishes `ready`, `degraded-but-supported`, `not_required`, `not_checked` and `blocked`, retaining safe remediation and configuration/policy/build identity without exposing/changing secrets.
- **What to implement, in order:**
  1. Extend the existing pipeline-preflight contracts and orchestrator rather than adding a parallel health framework. Derive required checks from the canonical workflow/queue registry, selected run profile, planned side effects, and generated capability manifest; a stage cannot start if a required capability is absent from the proof.
  2. Add deterministic local probes for Python/locked-package compatibility, required imports and subprocess tools, configured font/template/prompt/schema assets, PDF/render/OCR availability, browser package/runtime compatibility, writable paths plus configurable free-space floor, and every canonical SQLite store's migration level, integrity, foreign keys, and bounded lock/write probe. Probes may create only uniquely named temporary files/transactions and must clean them up. Use uniquely named cleaned local probes and explicit write ownership; writability is not SQLite schema health/lockability. Consume existing R5 dependency-lock proof rather than recreate lock tooling.
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

- **Current scoped evidence (through 2026-10-08):** Semantic validation requires attributable verdicts and quotes; retryable execution errors reach bounded queue retries; OCR text cache identity binds to derived PDF checksum/extractor, and inconsistent cached PDF-text provenance is rejected (`bafd72ed`). Queue changes reconcile expired outbox leases and reject incompatible idempotency-key reuse (`207d6213`). Signal publication now retains frozen candidate manifests with checksum/readback and report-attribution fixes (`296afecb`, `2e6eae39`, `83a8d250`). Focused tests were added, but no fresh exact-HEAD full-graph, external-readback or editorial-quality acceptance was observed.

- **Baseline:** Queues/checkpoints/lineage, first-pass/recovery telemetry, final-package/readiness binding and approved idempotent publication exist. The historical `bfab37bbd1e4c194c027f14dd54817fb61f940a6` 2/20 result is no longer the latest full-cohort measurement. The [October 2–3 full20 frozen-source run](docs/quality/reliability-cohort-20260927-grounding/full20-grounding-readiness-20261002/measurement.json), producer `23fec7388553041aabcc3e1e0775abb559c6695d`, records 18 final validations/packages, 16/20 readiness passes (80%), four typed failures, 720 calls, estimated $1.321959, 8/20 bounded repairs and zero operator interventions. The subsequent [selected-four regression](docs/quality/remaining-four-finalization-20261003/measurement.json), producer `9466f4c0b718c691817a820793b4fa97ac5d8040`, records all four former failures passing validation/readiness with 134 calls. Publication was disabled in both. Combining those revisions cannot prove a single-revision 20/20 result. Neither lane proves current-HEAD fresh discovery/acquisition, no-repair conversion, human acceptance or approved publish/readback/replay. A21 stays Active; E13 owns item-scoped repair and E11 remains a scoped structured-validity milestone. Current local regression coverage verifies bounded explicit requeue and terminal handling of final-attempt lease expiry; it does not add a fresh full-graph replay or change the retained cohort results.
- **Target behaviour:** A frozen representative program measures the probability that a newly admitted source reaches an immutable `awaiting_review` package on its first submitted workflow attempt, with no operator repair, cohort substitution, ungoverned retry, or reuse of derived editorial artifacts. After explicit approval, the ready subset reaches authenticated sandbox readback and a zero-write replay. Failures remain visible in the denominator and drive shared, publisher-agnostic prevention work.
- **What to implement, in order:**
  1. Preserve implemented first-attempt/first-pass/recovery/operator/replay classifications and reconcile them with immutable final-package/report-scoped readiness. Fill missing attribution rather than build another scorecard or count internally repaired success as first-pass.
  2. Freeze a stratified cohort by reusing the A18 discovery corpus, P6 editorial cohorts, and retained acquisition-route evidence where identities remain compatible. Cover direct PDF, report-page extraction, browser, gated/mailbox, on-site capture, short/long, native/OCR, data-heavy/narrative, multi-publisher, and visual/no-usable-visual cases; add only missing strata and never select or replace members based on generated outcome.
  3. Run two bound lanes on the exact implementation SHA: a deterministic provider-free replay of retained external-boundary fixtures for the whole queue graph, and a controlled live/sandbox lane from real discovery/acquisition through source ingest, analysis, render, analytics projection, publication readiness, Signal/Briefing opportunity where eligible, explicit approval, WordPress publication, authenticated readback, and identical-package replay.
  4. Complete missing cohort-bound stage/attempt/usage/intervention and queue-health joins using existing reliability entities/transitions/Pareto. Retain exact cohort/configuration/policy/build/fixture identity and denominator/availability; unavailable attribution is never zero.
  5. Preserve the selected-four corrections, then rerun the unchanged full20 on one promoted revision before assigning a current failure Pareto. Fix only reproduced shared causes at their owner; never reimplement proven fixes, relax gates/retries, delete failed members or combine revisions into synthetic 20/20 success. Confirm previously failing processes first, then the complete required cohort.
  6. Add a release-facing SLO check with separate deterministic and controlled-live dispositions. Test both default manual approval and the *separately opted-in* `autonomous_mvp` policy-gated approval through the canonical ledger and isolated sandbox readback. Enabled code is **not** proof of public auto-publication safety: reconcile P6 editorial and E15 visual acceptance before permitting unattended public writes.
- **Acceptance criteria:**
  - The frozen cohort and stratum manifest are hash-pinned before execution, every admitted member remains in every denominator, and derived report/editorial/crop/readiness caches are empty at start; only explicitly declared immutable source/route fixtures may be reused.
  - The provider-free full-graph replay completes **100%** of eligible entities to the expected terminal state with zero orphan jobs, lost outbox events, stale-lease commits, duplicate effective side effects, or unclassified failures.
  - In the controlled live lane, at least **95%** of valid admitted sources reach `awaiting_review` on the first submitted attempt without operator intervention, at least **90%** pass publish readiness without targeted editorial regeneration, and **100%** reach a typed terminal state within configured bounds. Source-invalid/rights/credential blockers are reported separately but remain in the intake funnel.
  - After checksum-bound approval (manual by default; automatic only in the explicitly enabled policy lane), **100% of publish-ready admitted packages attempted against the healthy sandbox** receive authenticated metadata/content/media readback, and replaying identical package requests performs zero WordPress post writes; target outages remain explicit unavailable evidence, not a pass.
  - Policy-enabled approvals fail closed on warnings, stale/changed packages, unsupported or unresolved claims, incomplete assets, missing no-override provenance and disabled configuration. Before public unattended writes, document the release decision and prove or enforce holds for unresolved P6/E15 acceptance; deterministic readiness alone is not independent human quality acceptance.
  - Stage results identify first-pass, internally repaired, retried, operator-requeued, and permanently held outcomes separately with exact calls/tokens/cost/duration; no successful retry rewrites the original first-attempt result.
  - Each promoted fix improves the compatible cohort's first-attempt conversion or cost/time-to-terminal without reducing source fidelity, editorial P6 scores, E15 crop acceptance/coverage, acquisition recall, or publication safeguards; the final evidence is bound to one exact SHA and the release surface.

### 2. Public Trust and Publishing

#### P2. Harden bounded WordPress public-observability events

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

#### P4. Close public briefing, correction, and submission intake

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

#### P5. Validate and close responsive search and navigation

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

#### P6. Complete blind human editorial acceptance

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

#### P7. Fix public performance measurement and reach hosted targets

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

#### P8. Complete concise public evidence, methodology, and related-content surfaces

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

#### P10. Operate correlated public-render failure telemetry

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

#### P16. Build a decision-grade consulting synthesis artifact

- **Baseline:** Editorial plans, evidence-bound insights, deterministic executive-advisory/Decision Brief assembly, and separately generated Expert/LinkedIn copy exist. `src/generators/_artifact_generator/storage.py::build_executive_advisory_artifacts` mainly copies insight implication/action text and leaves structured rationale/impact/likelihood/mitigation empty. There is no persisted `decision_synthesis` family or governed audience-context contract. Historical P6 score matrices are partial human evidence, not consultancy-quality closure. The source-linked decision model, coherent cross-surface projections and comparative outcome proof remain open. Cross-report source selection now recomputes publisher diversity from immutable base scores and has shuffled-order regression coverage; this deterministic control-flow result is not human evidence of synthesis quality.
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

#### P17. Compose adaptive, non-repetitive visual report stories

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

### 3. Evidence Quality and Reuse

#### E6. Retain a hash-pinned claim-embedding benchmark export

- **Baseline:** Claim embeddings and bounded live A/B tooling exist; the A/B output intentionally omits vectors. `semantic_evidence_preselection_benchmark.py` accepts supplied vector JSON offline but lacks governed model/dimension/corpus/content-hash validation and uses vector-norm ordering rather than production semantic selection. Approved retained export and zero-provider production-equivalent comparison remain open, not another embedding service/provider benchmark.
- **Target behaviour:** A bounded, retention-governed, hash-pinned benchmark export contains only approved vector identifiers/content hashes/vectors and enough model/dimension provenance to reproduce semantic ranking and compare against lexical fallback entirely offline.
- **What to implement, in order:**
  1. Define a versioned benchmark-export schema containing opaque claim/vector identity, content hash, embedding model/dimensions/version, vector, corpus identity and generation/hash provenance—no claim/source text.
  2. Add a controlled export path from the retained benchmark corpus that validates vector count/dimensions and writes an immutable manifest/hash.
  3. Load and validate the governed export in existing offline tooling before provider routing; reject/abstain on model/dimension/corpus/content-hash/version mismatch.
  4. Use the canonical production preselection/ranking boundary for zero-provider semantic-versus-lexical coverage, preserving corpus/export/model/dimension identity. Supplied-vector norm ordering or fake vectors cannot establish semantic retrieval closure.
  5. Document retention/update policy so a model/dimension/corpus change creates a new export rather than silently mutating the baseline.
- **Acceptance criteria:**
  - Export is hash-pinned, versioned, reproducible and contains no claim/report text or credentials.
  - CI can execute semantic ranking/coverage on the fixed corpus with **zero provider calls** and detect hash/dimension/model incompatibility.
  - Semantic versus lexical fallback metrics are retained with exact corpus/export identity and deterministic results.
  - A changed corpus/model/dimension cannot reuse an incompatible export silently.

#### E10. Attest active model-pricing rates before they become stale

- **Baseline:** Enabled pricing governance blocks missing/invalid, explicitly held and explicitly expired configured rates before provider I/O, with cached-input/key/version attribution. Source/version/effective metadata exists, but proactive review/expiration attestation and reviewed cost-transition evidence remain absent. Approval, effective-date and mandatory review-age semantics are not enforced by the resolver; date labels do not prove rates stale or incorrect.
- **Target behaviour:** Operators get a bounded read-only freshness/coverage report for every active production-priced route and an explicit reviewed rate-card transition with before/after cost impact. No scraped/unreviewed rate becomes active automatically.
- **What to implement, in order:**
  1. Enumerate effective production model/provider pricing keys from the same reachable policy inventory used by A15. Reuse reachable model-policy inventory and expose exact aliases/pricing keys; missing approval/review/expiry metadata is unavailable, not inferred.
  2. Add a read-only attestation command reporting active, expiring, stale, held, missing, source/version/effective/review dates and coverage status without network scraping by default.
  3. Add deterministic before/after cost recomputation for recent canonical usage when an operator proposes a reviewed rate change; retain the old/new version/source and impact summary.
  4. Keep activation as an explicit reviewed configuration/rate-card change and preserve fail-before-provider behavior when the attestation is not valid. Preserve existing fail-before-provider behavior and add reviewed transition/activation semantics; do not auto-activate scraped rates or infer expiry from effective-date labels.
  5. Add tests for missing, expired, held, changed, cached-input and unknown-route pricing states.
- **Acceptance criteria:**
  - Every reachable priced production route appears in the attestation as active/expiring/stale/held/missing with source/version metadata.
  - Unknown, expired, held, or missing rates cannot silently execute as zero-cost or bypass spend authority.
  - A reviewed rate transition retains before/after estimates on recent canonical usage and an explicit operator acknowledgement; no command activates rates automatically.
  - Tests cover effective-date/freshness boundaries and cached-input pricing where applicable.

#### E12. Persist pre-category editorial context checkpoints

- **Baseline:** Source/selection/vector checkpoints and prompt-family materialization already reuse compatible taxonomy/evidence/category outputs; E9's August 27 case proves narrower call avoidance. Recovery still starts before combined analysis rather than from a versioned pre-category checkpoint. Explicit context/planner proof that category-only recovery runs only category work and deterministic dependents remains open.
- **Target behaviour:** A versioned, lineage-validated checkpoint immediately before category fitting makes a genuine category-only recovery reuse all valid upstream taxonomy/evidence context and execute only the category model family plus its deterministic dependents.
- **What to implement, in order:**
  1. Define the pre-category checkpoint contract from approved taxonomy/evidence references, source/selection/vector identities, prompt/policy/schema/config hashes, and required compatibility metadata—no raw prompt duplication. Reference existing compatible family materializations/hashes rather than duplicate their payloads or introduce another reuse store.
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

- **Baseline:** Exact writable paths/minimal patches, retained-claim diagnostics, deterministic corrections, typed alternative evidence, one-call private decisions, retry deltas/strategy memory and repeated-candidate rejection are implemented. The frozen benchmark and scorecard exist; the remaining deficit is demonstrated safety/effectiveness, complete compatible denominators and repair-attributed usage, not absence of these foundations.
- **Target behaviour:** Existing atomic/adaptive regeneration must demonstrate reliable legal repairs while preserving the existing fail-closed promotion boundary. Every repair starts from the last promoted artifact, diagnoses the exact failing item/field and protected facts, chooses the cheapest safe repair action, changes only explicitly allowed paths, validates deterministic factual compatibility before the full gates, and records a machine-readable before/after failure delta. A rolled-back candidate never becomes the next baseline, but its strategy, evidence choices, resolved/persisting/introduced failures, and mutation scope inform the next attempt so retries deliberately use a different safe strategy rather than repeating the same failure. Deterministic corrections run without a model; model regeneration is reserved for source-grounded semantic/prose repair; unsupported items are removed/abstained rather than repeatedly paraphrased. Success is measured on a hash-pinned corpus of real historical repair failures.
- **What to implement, in order:**
  1. Preserve the atomic/protected-field, deterministic-first, promoted-baseline isolation, typed RepairDelta and strategy/candidate repetition safeguards in contracts, planner, generator and validation loop. Triage current frozen-scope/evidence/provenance failures through canonical production boundaries; do not expand legal scope or weaken validators to manufacture success.
  2. Retain every original frozen case, distinguishing currently reproducible, no-longer-reproducible, attempted, abstained, failed and strictly successful. Complete candidate/case/attempt identities and repair-attributed calls/tokens/cost/latency; whole-workflow usage and unavailable attribution are separate.
  3. Obtain an unchanged, version-compatible before/after measurement on one promoted revision; fix reproduced scope/evidence introductions and assert expected protected/derived leaf behavior. A final-validation pass, promoted candidate, removed unsupported item or no-longer-reproducible case is not automatically strict repair success.
  4. Confirm previously failing cases first, then rerun the required immutable failure corpus and affected downstream workflow canary with publication disabled. Preserve independent scorecard labels, exact identities, safety thresholds and unavailable comparisons; close only when every criterion below has proof.

**Latest retained measurement:** The October 1 replay at producer `eae746de7a6595b6dbddfcc69d7ad9ca8b26d2b6` retains seven unchanged frozen cases: four currently reproducible and three no longer reproducing. Strict success@1/@3 is 0/4, with nine candidate attempts, eight rollbacks and one promotion. The frozen scorecard records six out-of-scope attempts, seven unsupported-evidence introduction attempts, 18 new hard failures across eight attempts and one provenance/lineage introduction attempt. DoubleVerify's validation pass/promotion exceeded the frozen scope and is not strict success. Historical comparisons are identity-incompatible; no paired gain or residual-odds reduction is proven. Whole-replay usage is 165 calls and estimated $0.415041; complete repair attribution remains unavailable for Mobile. The separate IAS first-attempt canary passed readiness with 46 calls, publication disabled, and did not prove repair effectiveness. See the [result](docs/quality/e13-repair-benchmark/results/2026-10-01-eae746de.json), SHA-256 `08ba6900f921d839f6e34d509c0e41b4ec3091db70c329da486b97685b09efd6`, and [owning benchmark evidence](docs/quality/e13-repair-benchmark/README.md) for prior September measurements, exact commands and identities. E13 remains Active.

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

- **Baseline:** Model fitting, deterministic inclusion/exclusion/centrality, supported rescue and repair/abstention records exist, with field-preserving fixtures and stage/outcome/failure `category_outcomes.csv` exports. Compatible-cohort scoring of valid exclusions versus unresolved gaps, selection/rescue distributions, attributable usage and recurring concepts—and review-only proposals—remains absent.
- **Target behaviour:** A bounded read-only category-fit scorecard identifies where deterministic mappings or prompts can improve grounded coverage and reduce unnecessary repair without forcing legitimate out-of-taxonomy reports into a category.
- **What to implement, in order:**
  1. Define compatibility cohorts from taxonomy/mapping version, prompt/model/policy, schema/validator and relevant configuration identities.
  2. Aggregate nonempty selection, explicit-uncategorized, selected-count distribution, deterministic rescue, repair rate, validation outcome, latency, tokens and cost by compatible identity. Extend current category-stage/usage exports; do not create a parallel outcome ledger or count regression fixtures as compatible-cohort calibration.
  3. Retain explicit exclusions/out-of-taxonomy outcomes separately from unresolved mapping gaps so the scorecard does not optimize against valid abstention.
  4. Rank recurring uncovered semantic concepts and excess-repair causes using bounded concept/rule IDs and produce reviewable mapping/prompt proposals only above sample/confidence gates.
  5. Validate a proposed mapping/prompt change through retained and bounded live compatible cohorts using the existing gates; do not mutate taxonomy automatically.
- **Acceptance criteria:**
  - Scorecard reports complete denominators and separates selected, explicit-uncategorized, explicit-exclusion, rescue and repair outcomes.
  - Incompatible taxonomy/mapping/prompt/model/policy cohorts are never merged.
  - Proposals are bounded to mapping/prompt review and include sample/confidence evidence; no automatic taxonomy/policy change occurs.
  - Retained/bounded live evidence demonstrates a measured increase in **grounded** nonempty selection or a reduction in unnecessary category-repair calls with no increase in invalid/forced assignments, or records a justified no-change result.

#### E15. Make publication crops visually complete and repairable

- **Baseline (updated 2026-10-08):** Detection/ranking/refinement, raster QA/sidecars and escalation exist. The October 8 crop patch (`207d6213`) adds finite/ordered bbox validation, displayed-page affine transforms back to canonical PDF coordinates and guards against near-page expansion, with focused transform/invalid-bbox tests. These geometry tests do not discharge historical semantic clipping, incomplete QA or destructive inward-refinement risks. A human-labelled `publication_strict` corpus, completeness/coverage measurement, final publication-DPI proof and verified directional repair remain open; no fresh human visual audit was performed.
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

- **Baseline:** Explicit methods/limitations prompts, extraction strategies, family status, validation and free-text presentation exist. `src/schemas/methods_pack.schema.json` and `normalize_methods` still admit arbitrary objects; limitations normalization collapses structures to strings. Typed fact-level page/span identities, finite incomplete/conflict states and claim/action applicability links are absent. Retained PDF goldens include legacy tool-call-shaped methods and non-current limitation shapes; they are compatibility fixtures, not independently labelled methodology-quality evidence. E16 owns the underlying facts/constraints; P8 owns presentation and P16 decision logic.
- **Target behaviour:** Material methodology, scope, limitation, and uncertainty facts are versioned, source-linked, and machine-checkable. Missing disclosure remains an explicit unknown rather than an inferred weakness or invented fact. Claims and decision guidance are qualified or withheld when the evidence's population, geography, period, definition, method, or uncertainty does not support the proposed interpretation.
- **What to implement, in order:**
  1. Build a retained, human-labelled corpus spanning surveys/panels, market sizing, financial/administrative data, modelled forecasts, experiments, interviews/thought leadership, mixed-method reports, and reports with no usable method section. Label explicit sample/base, population, geography, fieldwork/data period, collection mode, weighting, coverage, metric definition, model/forecast basis, source-stated uncertainty, limitation, conflict, and applicability facts with exact evidence locations.
  2. Replace loose methods/limitations with a versioned typed contract and legacy adapter. Use finite `reported`, `not_reported`, `not_applicable`, `conflicting` and extraction-incomplete/unknown states. `not_reported` requires sufficient source coverage; legacy strings cannot acquire fabricated authoritative page/span roots.
  3. Extend existing methods/limitations prompt/extraction/reuse boundaries without another model step. Reject tool-call/operator/scaffold objects before accepting domain facts. Parse dates, samples, geographies, bases, units and definitions deterministically where adequate; validate probabilistic output against approved source roots and preserve abstention.
  4. Derive finite, explainable applicability/evidence-strength outcomes for the claims and decisions that depend on these facts. Record reason codes and the relevant scope mismatch or unknown; do not manufacture statistical confidence intervals, methodological quality scores, or causal strength when the source does not provide the inputs.
  5. Make claim validation, P16 decision synthesis, summaries/expert commentary, and cross-report comparison consume the same applicability constraints. P8 projects a concise safe subset publicly; internal provenance, diagnostics, and unsupported inferred judgments remain non-public.
  6. Add contract round-trip/schema snapshots, legacy-artifact migration tests, labelled-corpus extraction/grounding tests, contradiction/scope-mismatch fixtures, thin-source abstention fixtures, and retained expert-review evidence on the exact implementation SHA.
- **Acceptance criteria:**
  - Every accepted reported methodology/limitation fact has exact approved-source evidence identity and page/span provenance; no accepted fact invents sample size, fieldwork, weighting, geography, definition, uncertainty, model basis, or limitation.
  - On the retained labelled corpus, explicitly stated material facts achieve at least **95% recall**, while **100% of facts admitted to public or decision synthesis are human-verified correct and source-supported**; misses/rejections are reported separately so precision cannot be raised by suppressing the corpus.
  - Missing or ambiguous disclosure produces a typed unknown/conflict with an actionable reason, never a fabricated value, unqualified quality score, or silent assumption.
  - Independent source labels establish methodology accuracy; legacy PDF goldens remain compatibility tests. Tool/operator objects are never facts, and failed/incomplete extraction cannot be counted as source silence. Report extraction, completeness, applicability and compatibility denominators separately.
  - Every material claim or action whose applicability is limited by population, geography, period, definition, method, or uncertainty is explicitly qualified or withheld; incompatible scopes are never merged into one comparable trend.
  - Two independent methodology reviewers reach at least **90% agreement** with the system's supported/limited/unknown decisions on the retained cohort, with disagreements retained by reason code for remediation.
  - The change adds no provider call beyond the existing evidence/methods generation path, preserves legacy artifact readability through the declared transition, and passes schema, grounding, claim-validation, P6/P8/P16, readiness, and publication-projection tests.

### 4. Release Integrity and Architectural Enforcement

#### R1. Publish release-evidence reviews where reviewers work

- **Baseline:** The strict CTO collector already retains finite representative/smoke/not-declared scope, freshness and producer provenance. GitHub's bounded summary reports review/queue disposition and names an artifact, but does not expose a canonical bundle link or propagate runtime scope to PR/release reviewers. Remaining work is surface integration and truthful mismatch/unavailable disposition, not rebuilding collection/taxonomy.
- **Target behaviour:** The PR/release surface directly exposes exact-tested-HEAD evidence status, link/reference to the archived bundle, final approval/unwaived result, and declared runtime-corpus scope without copying unbounded evidence into comments/summaries.
- **What to implement, in order:**
  1. Define a small release-review surface contract: tested SHA, build/release run ID, review status, unwaived issue count, queue/runtime evidence status, corpus scope label, and stable artifact/reference link.
  2. Extend current CI/release automation to publish that bounded contract on the relevant PR/release surface while keeping the existing job summary/artifact as source of detail.
  3. Reuse the collector's finite corpus-scope/freshness/provenance contract and propagate it to reviewers. Keep collector/runtime producer identities separate; smoke, missing capture or an operator declaration is not representative workflow proof.
  4. Fail/mark unavailable on exact-HEAD mismatch, missing canonical evidence, expired/unavailable artifact, or unwaived failure rather than showing a green summary. Consume canonical review disposition/provenance rather than treating renderer-local HEAD or missing scope as approval.
  5. Update README/release docs and tests for bounds, mismatch, scope labels and issue retention.
- **Acceptance criteria:**
  - A reviewer can see the exact tested SHA, final evidence disposition, unwaived issue count and canonical bundle reference without opening raw CI logs.
  - Mismatch/unavailable evidence is explicitly non-green and cannot be mistaken for approval.
  - Runtime evidence clearly states whether it is smoke-only or representative; the label is retained with provenance.
  - Surface content is bounded and does not duplicate raw evidence/private diagnostics; all unwaived issues remain accessible in the canonical bundle.
  - Tests cover exact-HEAD match/mismatch, unavailable evidence, representative/smoke labels and bounded summary behavior.

#### R2. Enforce role boundaries, direct-I/O discipline, and controlled module growth

- **Baseline:** CI enforces imports, external-library ownership, role-I/O, movement evidence and quality floors. Role-I/O allowlists already validate exact path/rule, owner/expiry and reject expiration; no entries currently exist. Named behavior-coverage gaps and consistent reason/creation/symbol scope across facade/waiver exceptions remain open. Reconcile policy `expires_on` versus gate `expires` semantics rather than create another waiver system.
- **Target behaviour:** New first-party architecture drift fails before merge unless covered by a narrowly scoped, documented, expiring waiver with an owner/reason. Pure/inaccessible boundaries are not forced into meaningless integration tests, and no generic governance layer is added.
- **What to implement, in order:**
  1. Audit current architecture/service-boundary coverage and identify only concrete uncovered first-party boundaries with external/stateful behavior or high drift risk.
  2. Extend/reconcile existing waiver/allowlist records: preserve exact path/rule owner/expiry checks, add missing reason/creation and symbol scope where relevant, and align canonical expiry field semantics; no parallel waiver mechanism.
  3. Extend the existing CI architecture gate so a targeted uncovered boundary or new exception fails unless a valid narrow waiver exists.
  4. Reuse expired/missing-owner failures and add only currently uncovered broader-scope/reason/facade behavior cases, without demanding meaningless tests for pure/inaccessible helpers.
  5. Add docs/tests using representative violations, valid waivers, expiry and pure-boundary exclusions.
- **Acceptance criteria:**
  - A known targeted service-boundary coverage gap fails CI without a valid waiver.
  - Every new waiver has owner, reason, exact scope and expiry; expired or widened scope fails.
  - Pure or genuinely inaccessible boundaries are not required to add fake integration tests solely for coverage.
  - Existing public facades/external-effect ownership remain unchanged unless separately approved.
  - Tests prove target violations, valid exceptions, expiry and deterministic diagnostics.

#### R3. Restore service quality coverage above the retained baseline

- **Baseline:** `docs/quality/baseline_2026-02-21.json`, generated July 12 under a legacy filename, records services 82.5763%. CI enforces this historical threshold alongside the separate 75% floor. The artifact lacks producer SHA, command/environment and passing-run provenance; no current coverage/regression was measured here. Preserve the enforced threshold and obtain one attributable exact-commit full-suite/gate baseline with meaningful behavior coverage. Focused behavior coverage now also protects exact-nanosecond checksum-sidecar freshness, corrupt-lock diagnosis, and atomic same-key idempotency checksum conflicts; these checks do not refresh the exact-commit full-suite coverage baseline.
- **Target behaviour:** Behavior-focused tests protect high-risk stateful/external paths; passing exact-commit CI retains at least the enforced historical service threshold and supplies a fully attributable baseline without other domain regressions.
- **What to implement, in order:**
  1. Run/inspect exact current coverage by service module and rank uncovered behavior by operational risk, focusing first on ledger/recovery, browser-worker lifecycle, artifact lineage and other durable external/stateful paths.
  2. Add tests that assert returned contracts, persisted state, retries/idempotency/failure handling or boundary calls—not lines executed solely for coverage.
  3. Re-run focused suites and then the full CI/coverage command on one exact commit; retain the measured global/contracts/generators/orchestrators/services/control-plane values.
  4. Fix real regressions exposed by the tests without adding exemptions or lowering the 75% floor.
  5. Refresh the baseline only from passing exact-commit suite/gates with producer SHA, commands/environment, domain values and input artifact hashes. The historical threshold remains enforced until a justified attributable replacement passes.
- **Acceptance criteria:**
  - `src/services` coverage is **not below 82.5763%** on the retained passing exact-commit full-suite measurement and increases where the selected behavior tests add meaningful protection.
  - Global/generator/orchestrator coverage does not regress from its retained release baseline.
  - Added tests cover observable contracts/state/failure behavior; no coverage-only dead paths, exclusions, or lowered thresholds are introduced.
  - Baseline artifact records exact SHA, command/environment and measured values and is updated only after all relevant tests/gates pass.

#### R6. Review bounded-log reduction telemetry and remediate recurring callers

- **Baseline:** Python logging bounds payloads and retains reduction metadata under `fields.log_payload_reduced` in the original reduced event (`src/utils/logging.py`), not a separate event. Recurring-caller percentile/grouping/remediation aggregation remains absent. Use metadata-only evidence without reconstructing discarded values; P2 owns PHP emission safety.
- **Target behaviour:** Release/operator evidence shows where bounded-log reduction is occurring, how large attempted events are, and which modules/events repeatedly trigger reduction, without retaining/reconstructing discarded content. Recurring callers become explicit remediation work.
- **What to implement, in order:**
  1. Define a read-only aggregation contract for reduction count, module/event, attempted-size percentiles, retained-size/budget status, time window/build identity and bounded caller identity.
  2. Aggregate only fields.log_payload_reduced metadata plus bounded original event/module/run/build identity. Derive retained size from the safe serialized event only if needed and document it; never reconstruct dropped values.
  3. Add deterministic thresholds for “recurring caller” and map threshold breaches to an owner/existing backlog/remediation reference rather than auto-mutating logging code.
  4. Integrate the scorecard into release evidence/operator review with explicit zero-event state.
  5. Add redaction/content tests using source/prompt/browser/model-like payloads and verify the aggregate cannot contain them.
- **Acceptance criteria:**
  - Release evidence reports reduction count, event/module grouping and attempted-size percentiles with explicit zero state.
  - Scorecard contains no source text, prompts, model output, browser terminal text, credentials or discarded raw values.
  - Recurring callers above threshold are linked to an owner/remediation item and remain reviewable; no automatic weakening of event bounds occurs.
  - Aggregation is deterministic for the same retained log set and tests prove redaction preservation.

#### R7. Prove recoverable backups and full-state disaster restoration

- **Baseline:** Process recovery exists. The strict evidence collector already uses SQLite backup, hashes/provenance and atomic evidence-bundle finalization. These are review primitives, not an operational cross-store backup set, runtime restorable marker, empty-target restore or lost-host drill. Reuse suitable primitives while proving independent operational consistency and safe resume. The idempotency read boundary now rejects malformed or wrongly shaped retained outcomes with a typed nonretryable integrity error and preserves the row; the cross-store backup and restore drill remains unproven.
- **Target behaviour:** A backup is considered restorable only when one manifest proves a consistent, complete, integrity-checked snapshot of all required state. Restore occurs into an empty isolated target, validates schema/lineage/artifact closure before activation, and produces a reviewable resume plan. It never silently overwrites live state or replays WordPress, Drive, browser, mailbox, or model side effects.
- **What to implement, in order:**
  1. Inventory the canonical databases, WAL/sidecar requirements, artifact/source roots, queue/checkpoint/idempotency state, configuration/schema identities, and publication references required for each supported recovery profile. Classify sensitive/source material, retention, ownership, and dependencies; exclude reproducible caches only when the manifest records how they are safely rebuilt.
  2. Define a versioned backup-set manifest with snapshot ID/time, producer SHA, profile, schema versions, queue/checkpoint watermarks, database and artifact hashes/sizes, referential dependencies, retention/access-control metadata, and a final completeness marker. Standard logs retain only bounded identifiers/counts/hashes, never backed-up content or secrets.
  3. Implement consistent snapshot creation behind the existing filesystem/database service boundaries: coordinate writers, use SQLite's supported online backup/transaction semantics, copy immutable files only after referenced state is fixed, verify each member, and write the completeness marker last. Any interruption leaves an identifiable non-restorable set rather than a plausible partial backup. Reuse suitable SQLite snapshot/hash/atomic-finalization primitives while separately proving coordinated operational referential closure; do not turn the review collector into a recovery manager.
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

- **Baseline:** PDF visual families are decomposed behind compatibility facades. Inspect `_visual_heuristics/shared.py` parent-namespace injection and reciprocal facade/child imports as a concrete coupling candidate; historical file counts are not a current measurement or refactor mandate. Preserve the audit-first/no-significant-change exit and canonical PDF boundary.
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

- **Baseline:** `Archive_Browser` and `Publisher_Directory` already own archive/directory behavior through stable Shortcodes delegation/render registration. The catch-all retains navigation/homepage/topic/publisher-profile/entity concerns and unreachable old report-browser/briefing bodies. Complete live-family ownership and cleanup with runtime equivalence; do not re-extract completed owners or preserve dead code solely for string tests.
- **Target behaviour:** Coherent shortcode families have explicit feature ownership behind a stable registration/compatibility facade. Public shortcode names, hooks, output contracts, query behavior and CSS/JS handles do not change as a result of the refactor.
- **What to implement, in order:**
  1. Inventory remaining live shortcode families, their actual helper callers and unreachable former archive bodies; credit existing Archive_Browser/Publisher_Directory ownership.
  2. Keep stable tags/registration/public-render facade; start with an independent remaining live family instead of re-extracting completed archive/directory owners.
  3. Extract family-owned rendering/query helpers into feature-specific classes/modules while keeping shared primitives genuinely shared and WordPress-native.
  4. Preserve all existing shortcode tags, action/filter registration, asset handles, GET/query semantics and rendered markup unless a separate approved behavior item owns a change.
  5. Prove runtime markup/query/hook/asset equivalence, move source-inspection tests to canonical owners, then remove obsolete bodies/helpers only after live caller checks.
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

## October 7–8 Implementation Reconciliation

Committed implementation slices below do **not** close entire outcomes or establish a current-HEAD live benchmark. Supporting `10improvements.md` proposals retain their canonical owner here:

- **Semantic validation, OCR/text provenance, ZIP safety (`bafd72ed`, October 7):** VER-01/VER-04 and ING-02/ING-06 map to **A21**; ACQ-07 maps to **A19**.
- **Explicit autonomous-approval policy (`87add22f`, October 7):** maps to **A21/publication release safety** with P6/E15 independent quality criteria. Test default-manual and opt-in policy modes separately.
- **Lock fencing and cover identity (`64b1f94f`, October 8):** CODE-04/CODE-05 have OS-lock/owner-token fixes; report-card identity strengthens Closed **E7**. Process-level locking does not close **R7** disaster restoration.
- **Frozen Signal candidate manifests and projection integrity (`296afecb`, `2e6eae39`, `83a8d250`, October 8):** snapshot identity, grounding checks and source attribution strengthen **P15/A21**; they do not prove live Signal publication/readback.
- **Mailbox UID, outbox recovery, queue idempotency, editorial-plan reuse, crop transforms (`207d6213`, October 8):** ACQ-02 maps to **A19**; CODE-03/CODE-09 to **A21**; ART-02 strengthens Closed **E9**; CROP-05 to **E15**. Real-mailbox validation, full-graph replay and human visual/editorial acceptance remain unproven.

## Guardrails

- Never normalize cross-publisher metrics with incompatible definitions, geography, methodology, or time period.
- Never publish incomplete public pages for later enrichment; preview/draft is allowed only outside the public release surface.
- Never invent identity attributes for acquisition forms; map only configured, verified values.
- Never lower private-API promotion thresholds automatically.
- Never publish OCR, model, crop, vector, validation, filesystem, stack-trace, or other operator diagnostics as public product content.
- WordPress remains a rendering/publication boundary for intelligence; do not move report intelligence generation into the theme/plugin.

### Non-negotiable publishing guardrail

**Implemented behaviour versus release permission:** Base configuration requires manual approval. The explicitly selected `autonomous_mvp` overlay enables checksum-bound, policy-gated approval of clean report/briefing packages through the existing ledger, outbox, WordPress idempotency and readback (`87add22f`); the current Signal candidate path is manually held by its override marker. This implementation is **not** evidence that P6 editorial acceptance, E15 visual acceptance or A21 full-graph first-attempt/readback proof are complete. Unattended public production writes remain a release hold until source safety, no internal-ID leakage, crop completeness, editorial quality, duplicate suppression, recovery/rollback and reliable WordPress readback have been independently demonstrated and explicitly approved. Sandbox-only canaries are not blanket production authorization.

## Current-State Evidence

- Canonical workflow-control, budgets, recovery, model-policy routing, source identity, artifact lineage, publish readiness, and idempotent WordPress publication boundaries are implemented with retained evidence. Manual approval remains the base default; the explicit `autonomous_mvp` overlay adds gated automatic approval, not a waiver of unresolved public release-quality gates.
- WordPress has baseline public render safety, private inbox persistence, responsive navigation/search/filter implementation, and authenticated draft/readback support. P2 still requires a bounded/redacted PHP event contract; P4/P5/P10 retain specific implementation/interaction and hosted operational proof gaps rather than requiring these baseline capabilities to be rebuilt.
- `sync-wordpress-intelligence` has retained evidence for **64 public content entities** — 47 reports, 5 briefings, and 12 signals — **plus 29 publishers**. Do not describe that as 64 total entities.
- HTTPS on the temporary sandbox is intentionally deferred to production-host migration under P3; it is not counted as an autonomous-MVP implementation blocker.
- P6 is an editorial human-acceptance outcome, not an automated-gate implementation gap.
- P7 is not closeable until its measurement semantics distinguish HTTP probe timing from real browser DOM/load timing and report baseline regression separately from target attainment.
- CI covers formatting, typing, architecture/import checks, forbidden patching, hygiene, coverage, mutation, prompt regression, release-evidence archival, PDF candidate/crop/trend gates, public report-quality gates, and WordPress staging verification when configured.
- Current preflight, browser-doctor, synthetic smoke, queue recovery, exact-HEAD canaries, and editorial cohorts provide valuable partial proofs, but no single profile-derived doctor or representative first-attempt SLO yet proves that a clean installation can complete the selected workflow without operator repair.
- Existing reports have strong evidence, summary, insight, counter-signal, and expert-commentary capabilities, but decision logic, methodology applicability, narrative composition, and visual selection are not yet governed by one typed consultancy-grade story model.
- Durable process recovery does not yet amount to disaster recovery: the mutually dependent databases, artifact trees, lineage, queues, and idempotency records lack a retained consistent backup/restore drill.

## Audit Notes

- The comprehensive audit was 2026-10-05 at `da40362f08699b37b66a9fddfae7cd43ad0f1417`. The 2026-10-08 delta reconciliation inspected affected commits, code and runbooks through `207d62133cf8b94b1745c883f2e3a80536466509`; it does not claim a complete new source audit, live run, deployment or independent acceptance.
- The register contains **30 Active outcomes**, and each has one matching execution section with baseline, target behaviour, ordered implementation work, and measurable acceptance criteria.
- All 89 register IDs retain their statuses: **30 Active, 44 Closed, 12 Deferred and 3 Excluded**. New scoped fixes strengthen existing A19/A21/E9/E15 ownership, but do not close their broader acceptance where Active. No new standalone owner or generic DAG/adaptive-concurrency activation is justified by the inspected changes.
- A21 distinguishes the latest full20 frozen-source result (16/20 readiness at `23fec738`) from its selected-four follow-up (4/4 at `9466f4c0`) and the separate five-report performance lane. They are different revisions/scopes, not a synthetic 20/20 or fresh discovery-to-publication SLO. Reproduce residuals on one current revision before assigning a current failure Pareto.
- The frozen20 manifest has platform-sensitive LF/CRLF byte identities in this checkout versus the retained measurement. Future runs must declare canonical bytes or semantic JSON identity and retain measured manifest/member/source hashes; historical hashes must not be rewritten or reported as current-checkout byte verification.
- E13's latest owning replay is October 1 at `eae746de`, with strict success 0/4 among four reproducible cases from seven retained cases. Its implemented atomic/adaptive machinery and separate normal canary do not satisfy the unchanged repair-safety/effectiveness thresholds.
- R3's 82.5763% threshold is historically retained and CI-enforced, not a fresh exact-HEAD coverage result. Human attribution/rubric/output identity under P6, PHP event safety under P2 and scoped hosted proof remain unresolved. Readiness hashes are integrity checksums, not authorization signatures.
- Documentation/backlog checks validate structure/ownership, not runtime acceptance. The October 5 audit could not execute focused pytest (`No module named pytest`); the October 8 delta reconciliation did not run tests or any live provider, mailbox, browser, publication, hosted smoke, human review or disaster-restoration drill. Tests added in the inspected commits are not counted as freshly passing.
- A20 and A21 are net-new first-run-success owners: A20 proves clean-room capability readiness before side effects, while A21 measures representative first-attempt conversion through review readiness and approved sandbox readback. They do not duplicate A18/A19 route hardening, A3/A10 recovery, or P12/P14 release-locked canaries.
- P16 and P17 are net-new consultancy-quality owners: P16 governs a single evidence-to-decision synthesis; P17 governs bounded adaptive composition and non-repetitive visual storytelling. P6 remains the cross-cutting human acceptance gate and P8 remains the concise public evidence surface.
- E16 owns typed source methodology/applicability semantics beneath P8/P16. R7 owns cross-store disaster restoration, which is distinct from process-level queue/checkpoint recovery and quality-evidence snapshots.
- E15's historical September 7 visual review found clipped chart text/source content and a near-whole-page table crop under `out/evidence_fidelity_iab_20260907_r5` despite accepted QA sidecars. Those observations are not a fresh visual audit of this HEAD. The required **100% human publication-ready precision**, at least **95% eligible-visual coverage**, type-aware completeness and fail-closed remainder remain open until a new labelled production-path measurement proves them.
- P3 is correctly Deferred for production-host migration rather than counted as a temporary-sandbox MVP blocker.
- Historical canonical IDs previously present only in closure prose/context remain restored to the Unified Work Register: A5, A12, A13, P0, P9, P11, E1, E2, E5, E7, R4, S1, S2, and D10.
- The obsolete statement that closed A3/A6 remained Active is removed; E3 no longer delegates current work to already-closed E7.
- C6, P11, and A14 closure wording remains narrowed to the capability/tooling actually proven so A18/A19 own current production-hardening work without contradiction.
- Public-site states distinguish implemented-but-unverified outcomes from missing implementation, and intentional sandbox HTTP from production transport requirements.
