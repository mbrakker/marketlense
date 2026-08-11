# Consolidated TODO

Last audited: 2026-08-11

This is the repository's single, source-neutral work register. Every task is evaluated by its current codebase evidence and project decision—not by where it was first proposed. Equivalent tasks are merged under one owner; deferred, closed, and excluded work stays visible in the same register.

## How to Use This Backlog

- An item is activated only after an owner, baseline, target, and review date are recorded in its implementation plan or issue.
- One item owns one outcome. Overlapping requests are merged here rather than tracked in parallel.
- Every implementation follows `AGENTS.md`: preserve role boundaries, use typed contracts, avoid placeholders and private-helper patching, and verify behavior with real boundary tests.
- Remove an item when every stated completion check is met. Move its short evidence to **Recently Closed**.

| Priority | Execution lane | Goal |
| --- | --- | --- |
| 1 | Autonomous safety and cost control | Make unattended runs inspectable, bounded, and recoverable. |
| 2 | Public trust and publishing | Make the public site accurate, safe, responsive, and ready for operator review. |
| 3 | Evidence quality and reuse | Turn retained evidence, embeddings, lineage, and crop QA into measurable decisions. |
| 4 | Release integrity | Make release evidence and architecture enforcement visible and reliable. |
| 5 | Boundary simplification | Reduce real control-plane and service complexity without behavior drift. |

## Unified Work Register

All work is listed below in one register. `Active` items have detailed completion checks in **Active Backlog**. `Deferred`, `Closed`, and `Excluded` are not lower-class sources; they are simply the current evidence-based outcome for the same planning standard.

| Status | ID | Work item | Current outcome / merge target |
| --- | --- | --- | --- |
| Closed | A1 | Single autonomous supervisor, read-only `PipelinePlan`, and mandatory workflow-control authority | Plan authorization is enforced by CLI/UI control payloads; retained plan run and full regression passed. |
| Closed | A2 | Configured run profiles | Seven typed profiles now resolve identically in plan, CLI, and UI payloads. |
| Closed | A3 | Workflow-wide remediation-ledger rollout | The 31-workflow coverage matrix, fail-closed bounded reaper, read-only soak, and strict retained evidence bundle passed. |
| Closed | A4 | Quarantine irreparably malformed Drive PDFs | Deterministic structural validation, durable quarantine, and retained-file revalidation are active. |
| Closed | A6 | Budget-manager closeout and operational proof | Live Drive, OpenAI vector-store, and LLM calls recorded actual use; next governed calls were stopped before provider I/O and strict evidence passed. |
| Closed | A5 | Business-email, CAPTCHA, anti-bot, terminal-evidence, and avoided-browser-spend route policy | TTL-bound route policy now avoids browser/mailbox work for retained hard blockers and allows explicit revalidation. |
| Closed | A10 | Budget-deferred-work recovery and operator requeue | Autonomous-MVP recovery is enabled only for three proof-bound adapters; unsupported work remains held. |
| Closed | A11 | Ledger-driven recurring-failure prevention and operator prioritization | Read-only deterministic remediation-opportunity report groups recurring failures and holds every item without a runtime executor. |
| Closed | A7 | Budget-aware model routing, compaction, and failure-class fallback | YAML routing, anchor-preserving compaction, same-provider fallback, retained-corpus evidence gate, and regression coverage are active. |
| Active | A8 | Compare retained model-call replay bundles | Standalone read-only regression outcome. |
| Closed | A9 | Canonical report-source identity and publication provenance | Schema v19 immutable observations, deterministic source resolution, safe public projection, render-only invalidation, and live idempotent source capture passed. |
| Closed | P1 | Publish snapshot naming and synchronous idempotent publishing | Public/UI terminology now says Publish Readiness; the compatibility alias preserves callers and synchronous review-gated publishing remains unchanged. |
| Closed | A14 | Calibrate acquisition policy from retained route economics | Read-only compatible cohort statistics and thresholded operator proposals are active. |
| Active | A15 | Complete explicit model-policy coverage and policy-effectiveness evidence | Extend hash-pinned controls and measured cost/quality evidence to every production model namespace. |
| Active | A17 | Calibrate deterministic admission thresholds from retained preflight funnels | Produce compatible-cohort, read-only threshold proposals without automatically admitting a source. |
| Closed | A16 | Durable corpus rehabilitation campaign execution | Review-gated retained-evidence campaigns now queue idempotent repair work without public writes. |
| Active | P2 | Harden bounded public-observability events | Narrow log-event size-bound hardening for public-facing boundaries. |
| Active | P3 | Resolve hosted-site trust blockers | Safe-error boundary completed; hosted trust outcome remains. |
| Active | P10 | Operate correlated public-render failure telemetry | Hosted release-observability outcome. |
| Active | P12 | Release-locked sandbox publish canary | Repeatedly prove manifest-backed report recovery and final sandbox publication on a small, spend-governed real-report cohort. |
| Active | P14 | Restrict cohort-manifest publication to its admitted artifacts | Make the manifest an authoritative publish candidate boundary, not only a final audit boundary. |
| Active | P15 | Operate canonical publish-readiness telemetry and refresh planning | Turn hash-bound readiness failures and staleness into measurable, safe rerender work. |
| Closed | P13 | Make WordPress file-ID lookup independently authoritative | Authenticated immutable file-ID lookup now matches remote posts from isolated state, fails closed on ambiguity, and preserves no-write reuse. |
| Active | P4 | Close public briefing, correction, and submission intake | Implemented; close after hosted smoke proves the live intake routes. |
| Active | P5 | Finish responsive search and navigation | Responsive public-workflow outcome. |
| Active | P6 | Raise report-card and evidence-exhibit editorial quality | Release gate is implemented and live-validated; blind human editorial acceptance remains. |
| Active | P7 | Improve hosted public-site performance without contract loss | Measured public-performance outcome. |
| Active | P8 | Complete concise public evidence, methodology, and related-content surfaces | Public evidence/discovery outcome. |
| Active | E6 | Retain a hash-pinned claim-embedding benchmark export | Semantic benchmark coverage outcome. |
| Active | E10 | Attest active model-pricing rates before they become stale | Keep cost attribution and spend enforcement trustworthy as provider pricing changes. |
| Active | E11 | Measure and optimize structured-output recovery effectiveness | Turn central recovery-attempt telemetry into bounded quality and cost improvements. |
| Active | E14 | Calibrate category-fit coverage from retained outcomes | Turn category-fit decisions into grounded mapping and recovery improvements. |
| Active | E13 | Measure candidate-regeneration promotion effectiveness | Turn retained candidate lineage and promotion outcomes into bounded repair-quality improvements. |
| Active | E8 | Use canonical source identity to suppress duplicate research work | Canonical source identity reuse outcome. |
| Active | E9 | Materialize prompt-family outputs and route only their required model calls | Prompt-family repair and model-call reduction outcome. |
| Closed | E3 | Lineage-driven minimum regeneration | Remains closed; E7 owns expansion beyond the proven rendered-HTML family. |
| Active | E12 | Persist pre-category editorial context checkpoints | Extend typed recovery from source/vector reuse to genuinely single-family taxonomy and category-fit retries. |
| Closed | E4 | Executable retained PDF benchmark corpus in CI | Retained corpus is hash-pinned and CI-gated; local release-equivalent run passed. |
| Active | R1 | Publish release-evidence reviews where reviewers work | Reviewer-surface outcome, including exact-tested-HEAD linkage and runtime-corpus expansion. |
| Active | R2 | Enforce role boundaries, direct-I/O discipline, and controlled module growth | Architecture enforcement outcome. |
| Active | R3 | Restore service quality coverage above the retained baseline | Retained-baseline outcome. |
| Active | R6 | Review bounded-log reduction telemetry and remediate recurring callers | Operator feedback outcome for attempted oversized standard events. |
| Closed | R5 | Hash-verified dependency lock artifacts | Native Ubuntu CPython 3.12 wheelhouse and offline hash-locked install are verified. |
| Active | S3 | Simplify the PDF visual-heuristics boundary | Canonical PDF-boundary outcome. |
| Active | S4 | Give WordPress shortcodes semantic ownership | WordPress boundary outcome. |
| Deferred | D1 | Full report-generation DAG scheduler | Revisit when profiling shows material idle dependency time beyond simple parallelism. |
| Deferred | D2 | Streaming Drive prefetch queue and worker-safe PDF context pooling | Revisit when batches wait on Drive while worker capacity is idle. |
| Deferred | D3 | Adaptive concurrency and route-specific worker buffers | Revisit when sustained runs show throttling, SQLite contention, or browser saturation. |
| Deferred | D4 | Multi-provider failover | Revisit when outages create measurable failed-run volume or a service-level commitment requires it. |
| Deferred | D5 | Same-publisher warm workers/session reuse | Revisit when same-publisher volume justifies session-isolation risk. |
| Deferred | D6 | Arbitrary generic DAG or due-work scheduler | The implemented typed durable workflow queue owns new work and budget deferrals; keep a user-configurable scheduler deferred. |
| Closed | D7 | Complete queue-backed publication coverage and live recovery proof | Typed Signal/Briefing/cover/readiness/WordPress workers, Strategy Outputs UI submission, deferred-work handoff, architecture enforcement, recovery, and controlled live provider/dry-run WordPress evidence are retained. |
| Deferred | D8 | LinkedIn persona variants and comparative positioning | Revisit when an active distribution workflow measures their value. |
| Deferred | D9 | Golden-output prompt evaluation and broader prompt-family scoring | Revisit when the existing fixture corpus cannot detect a measured quality regression. |
| Deferred | D10 | Browser executor, static DOM scan, prompt-payload reduction, and route playbook tuning | Revisit when route telemetry identifies a measurable cost/latency gap not covered by A5. |
| Deferred | D11 | Root pre-commit, declarative quality-gate manifest, stricter mypy/Ruff, and hygiene scorecards | Revisit when current CI/quality-policy evidence proves a specific enforcement gap. |
| Deferred | D12 | Governed staging WordPress publish/projection canary | Revisit when a non-public staging site and a named human approver are available; use the typed publish/projection queues to verify a real post readback and projection mutation without public release risk. |
| Closed | C1 | Cached-provider accounting reconciliation corpus | Real `provider_hit` fixture and cached-token tamper rejection are in the CI-covered ledger path. |
| Closed | C2 | Bounded multimodal crop-QA escalation | Typed escalation generator and deterministic no-model default are implemented and tested. |
| Closed | C3 | Lazy model construction, ranking/crop shortcuts, prefetch, and route prompt improvements | Landed behind existing boundaries with retained regression evidence. |
| Closed | C4 | Capability maps and autonomous release/remediation summaries | Generated capability maps and autonomous smoke evidence are present. |
| Closed | C5 | Prompt partials/schema snippets and prompt fixture regression | Landed with dry-run and corpus validation. |
| Closed | C6 | Core discovery, mailbox acquisition, signal persistence, and claim-embedding persistence | Durable paths, fallback behavior, and focused tests are present. |
| Closed | C7 | Logging content-exposure controls | Redaction, deterministic bounds, retained-content checks, and regression coverage are active; P2 and R6 retain hardening and monitoring. |
| Closed | C8 | CTO evidence-collector integrity | Snapshot, exact-HEAD, provenance, consistency, and inventory validation are implemented; R1 owns runtime-corpus expansion. |
| Excluded | X1 | Draft HTML published before enrichment | Public progressive enrichment is not permitted. |
| Excluded | X2 | Automatic lower private-API promotion thresholds | Conservative thresholds remain mandatory. |
| Excluded | X3 | Invented acquisition-form identity facts or public pipeline diagnostics | Only verified identity facts may be mapped; diagnostics remain operator-only. |

## Recently Closed

- **A10 — Budget-deferred-work recovery and operator requeue (2026-08-10):** The reviewed `autonomous_mvp` configuration overlay enables the one-shot supervisor plus bounded deferred-work and remediation reapers at two records per pass, without enabling queue-worker batches or a second scheduler. The only legacy deferred-work adapters are `report_generation`, `report_download`, and `publisher_inventory`; unknown workflows remain remediation-held. Report recovery now forbids `latest_safe` fresh fallback, so invalid checkpoint proof cannot restart PDF/OCR/extraction/model work. Structured recovery events retain adapter, due time, plan hash, reused-artifact summary, attempt, terminal result, and bounded reason. Focused recovery/configuration tests passed (61). A retained real render recovery resolved from `analysis_complete` with one attempt and zero new provider calls/cost, avoiding source preparation, selection, analysis, PDF/OCR/crop, vector, analysis-model, and validator-model work. Real report-download and publisher-inventory recovery handoffs each converged on one durable pending canonical queue job across repeated submissions. Existing E11 owns recovery-effectiveness measurement, so no duplicate follow-up task was added.

- **Task 1 — Fixed cohort and execution-limit semantics (2026-07-26):** Ingest now exposes distinct `--cohort-size`, `--attempt-limit`, `--success-target`, and `--cohort-manifest` controls; the legacy `--limit` remains only as an explicit deprecated attempt-limit alias and cannot be combined with its replacement. New schema-`1.1` cohort manifests freeze immutable Drive members before model-backed report work and retain each report ID, canonical source identity, deterministic selection reason, configuration hash, policy hash, cohort ID, and derived validation-run ID. Replay recomputes and verifies both identities so tampered membership fails closed, while schema-`1.0` manifests remain readable. Fixed-cohort and attempt-limit failures stay in the denominator and never trigger replacement; only explicit `--success-target` may continue selection. Focused regression coverage proves manifest replay, identity changes on membership changes, tamper rejection, distinct CLI controls, and the failed-member/no-replacement case. A fresh isolated real Drive/OpenAI run froze a one-report cohort before 22 provider calls (144,203 tokens; $0.114671); its independent category-fit gate failure remained the sole cohort denominator member with zero replacements, and a second manifest replay selected no substitute. P12 owns the significant next step of repeat sandbox publishing, while P14 owns manifest-authoritative publication selection, so no duplicate follow-up item was added.

- **Task 9 — Validation-run attribution and reliability telemetry (2026-07-26):** Settings startup resolves the complete finite production model-policy namespace inventory and rejects an unknown or uncovered route before provider I/O; run preflight retains the resolved namespace/provider/model/full-policy matrix. Validation-run model usage also fails closed without complete validation/cohort/workflow/report/publisher identity; workflow/stage/artifact/action/semantic-task context; prompt/policy namespaces; provider/model/cache/token/cost/repair data; and configuration/policy/build provenance. Ingest and publication materialize the same deterministic manifest-and-ledger-derived reliability artifact, with the complete admitted-to-readback funnel, per-transition failure code/count/duration/usage/recovery/intervention/rerun metrics, and stable failure Pareto. Publication continues to verify the existing signed `publish_readiness.json` instead of reinterpreting a report package. A fresh isolated Drive/OpenAI run (52 attributed calls, 474,235 tokens, $0.309298) and its guarded publish pass exercised both artifact writes; the live failure telemetry exposed and then verified the optional-repair-skip accounting correction. The active E11 recovery-effectiveness item remains the significant follow-on owner, so no duplicate backlog item was added.

- **Task 8 — Canonical publish-readiness gate (2026-07-26):** Report rendering now persists one signed, hash-bound `publish_readiness.json` decision over the exact final HTML and normalized WordPress projection. It records report/artifact/HTML/projection/configuration/policy/revision hashes, all rule results, classified provenance, and expiry/staleness conditions. The canonical gate requires final semantic and grounding success, consistent category decisions, retained material-claim evidence, promoted regeneration, and complete accepted-crop-to-evidence-to-insight-to-caption-to-takeaway linkage. It blocks internal identifiers, raw evidence/OCR text, mojibake, placeholders, mechanical scaffolding, repeated boilerplate, broken local assets, private paths or Drive URLs, filename-style titles, duplicated years, unresolved truncation, and unsafe source provenance across visible and metadata surfaces. Weak, text-only, unaccepted, and unlinked figure cards are omitted without changing crops. Publication verifies the retained artifact before every WordPress preflight action and verifies the actual media-substituted projection; it no longer reinterprets validation artifacts independently. A real retained provider-produced Mintel package passed the gate with matching final HTML and projection hashes and zero rendered visual/chart cards, removing its four retained weak-evidence cards. The focused affected regression suite passed 117 tests.
- **Task 6 — Grounding-safe atomic regeneration (2026-07-26):** Regeneration now persists `artifacts_regen_candidate_<attempt>.json` and a schema-backed candidate audit before touching `artifacts.json`. Schema, evidence-ID, source-page, deterministic lineage, grounding, semantic, and public-editorial validation all pass before the canonical atomic store promotes the candidate; the prior artifact remains recoverable until that replacement succeeds. Unsupported, numerically inconsistent, contradicted, invalid-comparison, missing-material-evidence, and hallucinated-evidence-ID findings now block readiness, as does a grounding-provider failure unless the complete deterministic candidate check passed. Audits retain material claim/insight identity, original/candidate evidence IDs and pages, issue codes, scope, before/after hashes, and promotion/rollback outcome. A real retained provider-produced artifact passed as an unchanged candidate, while a hallucinated-ID candidate was blocked with the canonical SHA-256 unchanged. A fresh isolated Drive/LLM run admitted one 140-page, 6.20 MB source and made 20 real model calls (98,380 input / 38,925 output tokens, $0.102448); it correctly stopped at the unrelated category-fit policy gate, and the zero-candidate publish preflight made no WordPress write. The full regression suite passed (4,810 tests plus 20 subtests).
- **Task 5 — Failure-specific checkpoint recovery (2026-07-24):** A finite, typed recovery registry now maps taxonomy JSON/schema, category-fit contradiction, unsupported material claim, final-HTML internal identifier, missing card manifest, and WordPress readback failures to their retryability, scope, one-attempt ceiling, required checkpoint, reusable artifacts, invalidations, next action, and typed terminal fallback. The durable remediation ledger auto-enqueues only rules with current validated proof, revalidates that proof immediately before execution, preserves run/report/artifact/budget identity, and terminates rather than looping after a failed attempt. The report and publishing paths supply the retained checkpoint/lineage evidence; the adapter performs targeted report repair or GET-only WordPress reconciliation. A real retained-report recovery rerendered and revalidated only the final HTML, resolved its durable job, issued zero provider calls, consumed zero new tokens/cost, and avoided source preparation, selection, analysis, PDF/OCR/crop/vector/model/validator work. Relative to that report's retained 23-call analysis run, this avoided replaying 112,670 input tokens, 47,271 output tokens, and $0.121702 observed model spend. The fresh current-policy discovery→acquisition→ingest→publish workflow passed with an authenticated zero-write WordPress reuse, and the full suite passed (4,795 tests plus 20 subtests).
- **Task 4 — Unified structured-output recovery (2026-07-24):** All required report JSON families now use one typed, schema-constrained execution service: document map, taxonomy, category fit, evidence packs, report artifacts, cover semantics, and semantic/grounding validation. It normalizes Unicode/fences, parses deterministically, validates and normalizes the canonical schema, performs one deterministic repair, one original-response/exact-error model repair, one source-evidence regeneration, then records either an explicit downstream-contract abstention or a typed terminal failure. Each attempt retains report/family, attempt, error class, provider/model, tokens, cost, and final disposition; empty output cannot become a successful artifact. Existing retained Stocksy empty document-map/taxonomy artifacts are covered by regression tests. A real fixed Drive cohort initially exposed two OpenAI strict-schema incompatibilities (`oneOf` and persisted-only fields); the provider projection now converts disjoint unions to `anyOf` and omits storage-owned fields while canonical validation remains unchanged. The same cohort then completed discovery through ingestion and rendering with real model calls, validation, targeted recovery/regeneration, one draft WordPress write/readback, and a zero-write idempotent repeat.
- **Task 3 — Deterministic admission preflight (2026-07-24):** A typed, versioned preflight now gates every acquired source before vector-store creation, evidence generation, OCR, or editorial model work. It deterministically records supported-PDF and readable-structure checks, native-text and configured size/page thresholds, exact duplicate identity and near-title signal, quarantine, source/publisher/title/URL identity, evidence-family potential, canonical runtime dependencies/paths, model-policy coverage, and a budget forecast. The retained decision hash and bounded input summary are persisted both in the admission funnel and fixed cohort manifest; rejected sources remain visible in that funnel but are skipped and excluded from the ingest-reliability denominator. A fresh 24-page, 8.31 MB live Drive source was admitted with a `0.008281 USD` forecast, completed the full report pipeline, and its controlled WordPress draft creation and strict idempotent repeat passed with no second write. Focused admission-to-publication regression coverage passed (146 tests).
- **P13 — Authoritative WordPress file-ID lookup (2026-07-23):** The canonical authenticated lookup now validates each returned post against immutable `ml_file_id`/content provenance and fails closed if more than one active post matches. A fresh isolated-state one-report canary matched an existing remote post without a local publish-idempotency record, performed zero WordPress writes, completed authenticated readback, recorded a reused repeat publication, and passed full validation-manifest closure. Focused ambiguity/no-write coverage and the full suite passed.
- **P0/P1 remediation and sandbox end-to-end validation (2026-07-20):** The canonical runtime/path/policy and public-editorial remediation package was exercised against an isolated real-report namespace. The final recovery makes a missing report-card manifest invalidate render reuse, rebuilds the required assets/manifest, and treats blocked public metadata as a typed render error. Optional card placeholders now normalize to omission rather than leaking or blocking valid public cards; `--force-report-cards` requests the analysis checkpoint only for an existing rendered package, while new files take the normal pipeline. The 60-minute report-analysis lease and spend-only budget profile were active. A five-report live Drive cohort completed in 46.23 minutes; every package passed semantic and editorial validation and had all three card assets. Canonical sandbox publication created three new posts, reused two existing posts, and a repeat made zero new writes through durable idempotency. The affected regression suite passed 122 tests; the isolated ledger recorded 159 completed LLM calls, 1,883,341 tokens, and $1.152941 estimated spend, below the $6 cap.
- **A16 — Durable corpus rehabilitation campaign execution (2026-07-19):** Reports schema v23 persists immutable candidate classification, source checksum/reference, immutable reusable-artifact IDs, campaign/approval hashes, planned-unavailable versus actual cost, and item-level queue identity. Submission rereads the current retained corpus before each queue handoff and holds changed evidence; it uses the canonical maintenance queue rather than reimplementing repair. The real retained-corpus canary classified 99 reports (25 reusable, 36 lineage-incomplete, 38 provenance-incomplete), approved one eligible report with 115 reusable artifacts, and idempotently retained one `artifact_repair` queue job across a second submission. It made zero provider calls, recorded $0 actual cost, and made no public write.
- **A14 — Calibrate acquisition policy from retained route economics (2026-07-19):** The read-only route-economics command groups only policy-compatible publisher/route cohorts and reports count, verified-success rate, median/p95 elapsed time, browser/model cost, incomplete-field state, and avoided operations. It emits proposals only above deterministic sample/improvement thresholds and never mutates routing or history. A live StackAdapt direct-PDF canary reached the canonical PDF budget stop before provider I/O, persisted one complete 3,860 ms/$0 resource envelope, and correctly returned `no_recommendation: insufficient_direct_sample`; focused route-policy and telemetry regression tests passed.
- **A4 — Quarantine irreparably malformed Drive PDFs (2026-07-19):** The deterministic `pdf-integrity-v1` gate now checks PDF header, EOF, parser opening, page count, and byte hashes before extraction, OCR, or model work. A matching unchanged Drive checksum is skipped from durable state; a valid replacement supersedes the old active record. The real retained Capgemini benchmark PDF passed the operator revalidation path (540,430 bytes, 15 pages) and recorded a `cleared` state with no provider call. Focused structural, migration, ingest-stop, durable-state, and operator CLI tests passed.
- **A2 — Configured run profiles (2026-07-19):** `safe_default`, `fast_cached`, `repair_failed`, `publish_ready`, `browser_acquisition`, `cost_saver`, and `high_quality` are parsed from the canonical YAML controls, resolved deterministically with a profile hash, and carried through plan, CLI, and UI execution payloads. The live `plan --profile browser_acquisition` resolved the expected browser-safe controls, while tests cover recommendation, explicit override, invalid profile, incompatible profile, and CLI/UI identity.
- **A11 — Ledger-driven recurring-failure prevention and operator prioritization (2026-07-19):** `remediation-opportunities` now groups canonical records by workflow, failed stage, typed error, proposed action, retryability, and runbook coverage. It emits only bounded record IDs and opaque source/publisher hashes with recurrence, age, attempted operation/cost, checkpoint/idempotency proof counts, deterministic priority reasons, and an explicit `held_unregistered` disposition. The live retained ledger reported 24 records in 15 groups; its most recurrent group had eight records and was held because its runbook mapping and execution proof were absent. No remediation record, provider call, or external side effect was changed.
- **D7 — Queue-backed publication coverage and live recovery proof (2026-07-18):** All critical queues have registered non-compatibility handlers and architecture tests prohibit direct major-stage chaining and UI subprocess ownership. A controlled live Briefing used real projected evidence from two publishers, one real model call (8,796 input / 3,460 output tokens), a frozen manifest, durable cover/readiness completion, and an explicit approval-driven `wordpress_publish --dry-run` with zero WordPress write. A live Signal root completed one candidate stage plus eight independent generation, cover, and readiness paths. The legacy deferred-work adapter preserves rows while routing new work through the shared lifecycle. D12 owns the separate staging-only verified WordPress post/projection canary.
- **E7 — Planner-enforced artifact-family reuse (2026-07-17):** Enforce mode now covers retained render, crop, checkpointed analysis/validator, combined crop-plus-analysis, publication preflight, and cross-report reads with a persisted plan/actual reconciliation, report-artifact lease, canonical lineage replacement, and requested-family dependency scoping. Real retained-report replays matched every planned stage/call/side effect: the final post-fix render-only canary completed in 1.190 s (1.190 s audited) with exactly `render_complete`, `html_render`, and checkpoint/HTML writes; crop-only completed in 15.760 s (15.513 s audited) with only crop QA/render and HTML render; and a real model-policy repair issued 17 LLM calls (134,969 input / 40,241 output tokens, estimated $0.114225) while retaining source extraction. The final HTML was complete (77,911 bytes, 469 tags, five images, no `undefined`). A temporary normal-policy replay rejected an incomplete payload before rendering or publication, and a later normal-policy repair completed in 245.980 s with a matched audit. A final full fresh rebuild was correctly stopped by canonical PDF budget authority before provider I/O; no budget bypass was attempted.
- **A3 — Workflow-wide remediation-ledger rollout (2026-07-17):** The generated 31-workflow matrix is CI-checked. A controlled typed `provider_timeout` persisted one remediation record across two submissions; the bounded reaper inspected it once and held it as `operator_action_required` without an executor or external side effect. The read-only soak reported one created, one deduplicated, zero stale, zero eligible, and one held record with no missing runbook mapping. Strict evidence bundle `21a046e89de64aa3a4fcc73250e74074` passed on exact commit `3da3d70e4b202cd2be4f206347982b9d55c94a13`.
- **A6 — Budget-manager closeout and operational proof (2026-07-17):** The public vector-store service now forwards a typed `RunBudget` and preserves canonical budget-stop errors. A live Drive list, OpenAI vector-store create/delete, and minimal OpenAI JSON call completed under canonical authority; ledger evidence recorded one Drive read, one vector create, one vector cleanup, and 168 LLM tokens. The next Drive and vector calls were blocked before provider I/O. Temporary vector stores were removed. The strict exact-HEAD bundle passed.
- **A9 — Canonical report-source identity and publication provenance (2026-07-17):** Reports schema v19 stores immutable, hash-addressed source observations and deterministic resolutions; it preserves v18 compatibility, projects safe source fields to analytics, report cards, and WordPress, and invalidates only rendering/publication when source metadata changes. A live Julius Baer landing page returned HTTP 200 with 218,676 bounded HTML bytes; its existing retained PDF benchmark resolved verified source provenance, while an exact repeat produced no duplicate observation. No LLM call or production write was made.
- **A12 — Complete configured model-pricing coverage for spend budgets (2026-07-18):** The canonical rate card now pins active OpenAI routes to an effective version/source, separately bills cached input, and holds unpriced or unapproved routes before provider I/O. Usage events project cost by report, workflow, prompt namespace, artifact family, and publisher. A bounded live OpenAI embedding recorded 49 input tokens, $0.000001 estimated spend, and complete claim-embedding attribution; the SQLite ledger and JSONL/daily projections reconciled exactly across 1,206 events.
- **E1 — Claim-embedding freshness, retention, and cost controls (2026-07-18):** The existing queue now uses deterministic due-work selection, expiring atomic leases, rechecks before provider I/O, bounded retries/budgets, and a health surface with age percentiles, throughput, drain estimate, failure reasons, model drift, and avoided calls. A live one-row OpenAI canary embedded one valid claim with no duplicate work; queue depth fell from 2,648 to 2,647 and content-hash skips rose from four to five. Historic non-claim rows remain explicitly `unknown_requires_review`, not silently embedded.
- **P11 — Verified acquisition-to-ingest handoff and live proof (2026-07-19):** Direct, browser, and mailbox acquisition now share one verified file/MD5/source-identity handoff that upserts the canonical report record and enqueues idempotent `source_ingest` work. A live authenticated Drive PDF download (6,203,358 bytes, MD5 verified) reached `analysis_complete` through the retained artifact with 21 real model calls and no public write. The same closeout added bounded acquisition resource telemetry and route suppression; live direct, browser, and mailbox canaries recorded their actual resource envelopes without a Drive or WordPress write.
- **C8 — CTO evidence-collector integrity (2026-07-17):** The strict collector snapshots retained inputs, validates exact repository HEAD, checks log-content coverage, run IDs, provenance, summary consistency, and every inventoried file hash before publishing. It fails closed without a partial final bundle. R1 owns expansion of the retained runtime corpus, not collector integrity.
- **C7 — Logging content exposure (2026-07-16):** Standard events apply deterministic byte, depth, node, collection, and text bounds; report and browser terminal events emit scalar summaries with retained audit references; CI rejects direct `fields=asdict(...)` serialization. Focused report/logging and browser suites passed, as did guarded live browser and OpenAI runs. P2 retains the narrow public-boundary size-limit hardening and R6 owns ongoing reduction-telemetry review.
- **A7 (2026-07-14):** The retained 15-report corpus is now a required no-provider routing gate across 30 configured prompt routes. It confirms explicit policy selection, same-provider constraints, and zero lost retained evidence IDs; focused routing/compaction/fallback tests and the full suite pass.
- **R5 (2026-07-15):** The canonical lock records SHA-256 hashes for all 177 active Ubuntu CPython 3.12 artifacts, including `numpy==2.4.2` from its official manylinux wheel. CI installs with `--require-hashes`; a native official-PyPI wheelhouse passed an offline clean install, while a tampered NumPy hash failed before package installation.
- **R4 (2026-07-15):** Publication reads canonical SQLite usage plus projection status; normal bounded lag is accounted, while missing, invalid, or material lag stops the final public write without triggering a rebuild.
- **E5 (2026-07-15):** Retained crop-QA sidecars now form operator-only scorecards and selection telemetry, including deterministic quality/clipping/storage comparisons with no public diagnostic rendering.
- **E3 (2026-07-16):** Lineage-driven minimum regeneration is now the deterministic authority for report and publication repair. It captures current compatibility, persists plan/actual audits, fails historic provenance closed, exposes validated cross-report claim/evidence/summary/chart/metadata reads, and has a render-only enforcement path. A retained provider-backed full run completed in 208.51 seconds; the subsequent enforced render-only replay completed in 0.87 seconds with source, selection, analysis, model, projection, and WordPress work avoided. E3 remains closed; E7 owns all further artifact-family reuse expansion.
- **E2 (2026-07-15):** The retained-artifact benchmark reports Briefing and Signal prompt/token deltas, overlap, source/citation coverage, and explicitly records the deterministic fallback when no retained embedding export exists.
- **P9 (2026-07-15):** The retained public-advisory benchmark now compares a saved baseline and emits typed per-insight source-grounded repair proposals or explicit abstentions without altering public rendering.
- **S1/S2 (2026-07-15):** Canonical service-boundary and publish/ingest facade audits remain CI-enforced; focused decomposition regression coverage preserves the existing routing, retries, state transitions, and external-effect contracts.
- **P1 (2026-07-14):** `build_publish_readiness_snapshot` is the canonical UI/ops boundary, with the old queue-named callable retained only as a compatibility alias. Publish remains synchronous, idempotent, and review-gated; focused tests and the full suite pass.
- **Public WordPress safe-error boundary (2026-07-14):** Public shortcode rendering now returns a branded correlated HTTP 500 section on forced report, publisher, archive, or generic shortcode exceptions, while the private structured event retains exception details. The real local Studio route `/publisher/not-extracted/` changed from an incorrect 200 report archive to the branded 404; homepage, reports, and publisher directory remained HTTP 200 with no public diagnostic signatures.

## Screenshot Baseline Completion Evidence

The original ten-item screenshot baseline is complete in the committed implementation. Its broader successor work remains Active above only where it adds new scope beyond that baseline (for example hosted HTTPS in P3, full intake flows in P4, or visual screenshot comparison plus accessible mobile-menu interaction in P5).

- **Public quality gate (2026-07-14):** The real local Studio site passed the new Playwright-backed responsive gate on the homepage, reports archive, and a retained report detail at 390px, 768px, and 1440px: 9/9 checks had no horizontal overflow and no visible broken image. The same live site passed the public SEO/performance gate across seven public routes with HTTP 200, complete canonical/social metadata, and no configured threshold violations.
- **Core safety, budget, recovery, route-memory, lineage, retained-benchmark, WordPress projection, LLM routing, and publication-gate baseline (2026-07-14):** The implementation is covered by the committed typed contracts and control paths. A focused regression run passed 50 tests across run budgets, canonical LLM accounting, UI-run recovery, artifact lineage, publication, and retained report quality. The underlying A3/A6/E3 implementation evidence remains retained; A3 and A6 are active only for bounded rollout and operational proof, while E7 owns any E3 expansion.

## Active Backlog

### 1. Autonomous Safety and Cost Control

#### A15. Complete explicit model-policy coverage and policy-effectiveness evidence

- **Title:** Complete explicit model-policy coverage and policy-effectiveness evidence
- **Impact 5 / effort: 2**
- **Context:** Settings startup now resolves the finite reachable production namespace inventory before provider use, and `policy-effectiveness` emits bounded execution-identity cohorts from the canonical ledger. The 2026-07-19 unknown-namespace failure is historical evidence for this guard, not a current description of the path. Remaining work is to retire the compatibility adapter for every reachable namespace and retain enough compatible production evidence to make the report decision-useful.
- **Benefit:** Every materially expensive model call can be governed by an auditable policy and operators can safely identify policies that reduce cost or improve validated output quality.
- **Risks to avoid:** Preserve each namespace's current semantic contract, provider boundary, retry ownership, and cache compatibility; do not infer a policy from one noisy run or change routing autonomously.
- **Success criteria:**

- Eliminate compatibility fallback for every reachable production namespace while preserving the current versioned output, timeout, retrieval, and structured-output controls; an unregistered reachable namespace must continue to fail at preflight.
- Keep `policy-effectiveness` bounded and complete for compatible execution identities, including provider calls, validated-output rate, cache reuse, elapsed time, tokens, and cost, without retaining prompts, sources, or model output.
- Retained-corpus and bounded live checks prove policy hashes invalidate incompatible cache reuse, preserve output contracts, and produce an operator-reviewable cost or quality conclusion without autonomous policy changes.

#### A17. Calibrate deterministic admission thresholds from retained preflight funnels

- **Title:** Calibrate deterministic admission thresholds from retained preflight funnels
- **Impact 5 / effort: 2**
- **Context:** Versioned admission decisions now retain compatible configuration, policy, runtime, source-size/page/text, duplicate, evidence-potential, forecast, and outcome metadata. Operators can see rejection counts but cannot yet compare compatible cohorts to tell whether the configured native-text, size/page, or evidence-potential thresholds are optimally preventing downstream cost without discarding viable reports.
- **Benefit:** Reviewable, evidence-based threshold proposals can reduce avoidable acquisition, vector, and model spend while preserving a high-quality source pool and the deterministic fail-closed boundary.
- **Risks to avoid:** Never mutate admission configuration automatically, merge incompatible policy/preflight versions, use source text or prompts in the report, or treat a small/noisy cohort as a policy recommendation.
- **Success criteria:**

- A read-only command groups only compatible retained decision cohorts and reports bounded outcome funnels, downstream provider/vector work avoided, and admitted-source completion/validation rates.
- It emits threshold proposals only after configured minimum sample and confidence/improvement gates, with the exact compatible decision hashes and counterfactual impact range retained for operator review.
- Tests cover incompatible-version exclusion, insufficient samples, deterministic ordering, and zero model/vector/external-write behavior; a bounded live replay produces an operator-reviewable no-change or recommendation result.

#### A8. Compare retained model-call replay bundles

- **Title:** Compare retained model-call replay bundles
- **Impact 4 / effort: 2**
- **Context:** Model-call replay bundles are retained, but comparing prompt, contract, evidence, and output changes currently requires manual inspection across artifacts and logs.
- **Benefit:** Regression evidence becomes reviewable without live calls, cost, or log archaeology.
- **Risks to avoid:** Keep comparison deterministic and bounded; do not invoke providers by default.
- **Success criteria:**

- The command compares deterministic fields, schema validity, prompt hashes, and selected evidence without provider calls by default.
- Output is bounded, reproducible, and links regressions to artifact family and remediation.
- Tests cover equivalent, changed, missing, and malformed bundles, including deterministic output ordering and zero-provider-call default execution.

### 2. Public Trust and Publishing

#### P2. Harden bounded public-observability events

- **Title:** Harden bounded public-observability events
- **Impact 4 / effort: 1**
- **Context:** Shared structured logging already has deterministic event-size limits and generic regression coverage, but public intake and public-render boundary events need a narrow contract check as their fields evolve. R6 owns aggregate reduction telemetry; this item owns the per-event size and content-safety guard at those public boundaries.
- **Benefit:** Public-facing workflows retain useful correlation and outcome signals without allowing a new high-cardinality field, user submission, or exception detail to make a standard event oversized or content-bearing.
- **Risks to avoid:** Do not create a second logger, retain dropped content, or expose private diagnostics in a public artifact. Use the canonical log schema and scalar summaries, hashes, or retained-artifact references.
- **Success criteria:**

- Public intake and public-render success/failure events remain at or below the canonical byte limit with maximum-size representative fields.
- Focused tests prove that oversized submissions and exception-like inputs preserve the correlation/outcome summary while omitting user text, paths, stack details, and discarded values.
- A bounded reduction remains visible to R6 without duplicating telemetry storage or changing the public response contract.

#### P3. Resolve hosted-site trust blockers

- **Title:** Resolve hosted-site trust blockers
- **Impact 5 / effort: 2**
- **Context:** Live public-site checks found HTTPS failure and HTTP sitemap URLs. The public rendering failure boundary and branded handling of the legacy `/publisher/not-extracted/` sentinel are complete.
- **Benefit:** Transport, safe errors, and reliable navigation meet the baseline expected of a trust-positioned research product.
- **Risks to avoid:** Verify staging and production separately and never disclose stack traces, paths, or diagnostics publicly.
- **Success criteria:**

- HTTP redirects to successful HTTPS; robots and sitemap URLs are canonical HTTPS.
- Hosted smoke evidence covers transport, representative pages, and sitemap behavior in both staging and production.

#### P10. Operate correlated public-render failure telemetry

- **Title:** Operate correlated public-render failure telemetry
- **Impact 4 / effort: 2**
- **Context:** The public shortcode boundary now emits the stable `marketlense_public_render_failure` event with a correlation ID, route, entity context, and private exception diagnostics, but hosted release evidence does not yet aggregate or alert on those events.
- **Benefit:** A bad public projection can be identified and repaired from one correlation ID before it becomes a repeated visitor-facing outage, without publishing diagnostic detail.
- **Risks to avoid:** Keep exception messages, traces, filesystem paths, and identifiers in private logs only; do not add a public diagnostics route.
- **Success criteria:**

- Hosted smoke records a bounded count of boundary failures and correlation IDs without serializing private exception fields into artifacts available to visitors.
- Release evidence distinguishes zero failures, expected injected failures, and unexpected render failures by route/entity type.
- Tests prove log redaction, deterministic aggregation, and that no public response or public artifact contains a stack/path signature.

#### P4. Close public briefing, correction, and submission intake

- **Title:** Close public briefing, correction, and submission intake
- **Impact 5 / effort: 2**
- **Context:** `Request a briefing`, `Send a correction`, and submission CTAs now collect structured requests through the approved boundary. The remaining closeout is hosted smoke evidence for the live routes, validation, delivery/persistence, and confirmation behavior.
- **Benefit:** Visitors can convert, correct, or submit sources through a trustworthy route that gives operators usable context, with closure based on the deployed behavior rather than implementation alone.
- **Risks to avoid:** Collect only necessary data, preserve redacted logging, and do not treat a local or simulated result as hosted proof.
- **Success criteria:**

- Correction and submission forms collect only the documented, necessary fields and present confirmation/error states.
- Requests use an approved service boundary with redacted structured logging.
- Hosted smoke checks prove each CTA route, validation, empty/spam rejection, successful persistence/delivery, and confirmation state in the deployed environment; then move P4 to Recently Closed.

#### P5. Finish responsive search and navigation

- **Title:** Finish responsive search and navigation
- **Impact 4 / effort: 3**
- **Context:** Visual QA found search overflow, cramped archive controls, an unfinished mobile menu, a stray list artifact, tall hero stacking, and clipped header-search text.
- **Benefit:** Search and navigation remain credible and usable on the screens where users actually discover and evaluate content.
- **Risks to avoid:** Do not alter archive-query semantics or projection contracts while changing theme behavior.
- **Success criteria:**

- No horizontal overflow, clipping, overlap, or unusable search/filter controls on homepage, search, archive, detail, contact, and submit views.
- Mobile navigation has accessible open/close and focus behavior with an intentional panel/backdrop.
- Retained visual-smoke screenshots cover each key view at phone, tablet, and desktop widths and are compared for regressions.

#### P6. Raise report-card and evidence-exhibit editorial quality

- **Title:** Raise report-card and evidence-exhibit editorial quality
- **Impact 4 / effort: 3**
- **Context:** The canonical hash-bound `publish_readiness.json` now validates the exact final HTML and WordPress projection, including semantic/grounding state, material evidence, accepted crop lineage, public-source provenance, metadata, and internal-leakage checks. It replaces publication-side heuristic rechecks; retained before/after diagnostics still request only evidence-grounded repairs. The remaining acceptance is qualitative human review.
- **Benefit:** High-value research reads as analyst-curated while retaining deterministic evidence provenance and auditability.
- **Risks to avoid:** Do not fabricate claims, hide evidence provenance, or substitute automated scores for the specified blind human assessment.
- **Success criteria:**

- Public copy rejects raw figure labels, OCR fragments, generic boilerplate, required-field placeholders, and internal identifiers.
- Blank/low-information thumbnails use deterministic covers or validated source previews.
- Audit identifiers remain available without being reader-facing labels; regression checks fail known leakage patterns in rendered output.
- Three independent blind evaluators assess 30 paired public reports with median readability, decision usefulness, evidence clarity, and appropriate certainty at least 4/5, and an explicit record of any outlier/appeal decision.

#### P12. Release-locked sandbox publish canary

- **Title:** Release-locked sandbox publish canary
- **Impact 5 / effort: 2**
- **Context:** The 2026-07-20 bounded sandbox run processed five reports, created or matched posts, and repeated with zero new writes. It predates the release-locked cohort-manifest workflow, so it is useful transaction evidence but not the recurring, immutable-cohort release proof this item requires.
- **Benefit:** A small, real, manifest-backed cohort catches render-reuse, card-asset, WordPress-readback, and idempotency regressions before a release affects a wider report set.
- **Risks to avoid:** Run only against the named sandbox and isolated state; require explicit approval, canonical spend authority, the existing validation/editorial gates, a fixed low cohort cap, and retained non-sensitive evidence. Never turn this into production auto-publishing.
- **Success criteria:**

- A release command selects a small, diverse, already-authorized real-report cohort and records deterministic cohort identity, configuration/policy hashes, and spend forecast before work begins.
- Every member must pass semantic validation, public editorial quality, complete manifest/asset checks, canonical publish readback, and a repeat idempotency lookup; any failure stops the cohort and preserves the failed evidence.
- Retained evidence compares the cohort's actual calls/tokens/spend, elapsed time, package completeness, created-versus-reused posts, and typed failures with the approved forecast; focused tests cover target isolation and no-write behavior when approval is absent.

#### P14. Restrict cohort-manifest publication to its admitted artifacts

- **Title:** Restrict cohort-manifest publication to its admitted artifacts
- **Impact 5 / effort: 1**
- **Context:** `publish-wp --cohort-manifest` now resolves the admitted members' retained HTML references instead of scanning `output_dir`, and applies a cohort-membership filter before publication. The remaining gap is a stricter one-to-one compatibility check: a changed mapping must fail rather than being silently excluded, and the resolved candidate set still needs a retained hash and isolated live proof.
- **Benefit:** The immutable cohort becomes the authoritative candidate set, preventing unrelated drafts from being preflighted or published and making bounded canaries safer to run in shared artifact namespaces.
- **Risks to avoid:** Preserve the existing no-manifest bulk-publish behavior, canonical artifact/path validation, approval gates, idempotency lookup, and fail-closed handling for missing or ambiguous cohort artifacts.
- **Success criteria:**

- With `--cohort-manifest`, resolve each admitted member to exactly one compatible current HTML artifact and fail before any WordPress call on a missing, stale, ambiguous, mismatched, or unexpectedly excluded member.
- Focused tests prove a shared output directory cannot preflight or write a non-cohort artifact, and that a changed report-store/HTML mapping fails closed while valid cohort reuse, authenticated readback, and repeat-publication semantics remain unchanged.
- A bounded isolated live cohort retains a candidate-set hash and shows only admitted report IDs in publication-preflight and WordPress manifest records.

#### P15. Operate canonical publish-readiness telemetry and refresh planning

- **Title:** Operate canonical publish-readiness telemetry and refresh planning
- **Impact 5 / effort: 2**
- **Context:** Each report now has a hash-bound final-readiness decision, but operators cannot yet aggregate current, stale, failed, and expiring decisions into an evidence-backed refresh plan. Re-rendering or re-analysis solely to discover that status would add unnecessary provider spend.
- **Benefit:** Operators can prioritize only the reports whose rendered package has genuinely become stale or failed a specific final-publication rule, preserving validated analysis and avoiding speculative full-pipeline rework.
- **Risks to avoid:** Keep the view read-only; do not auto-regenerate, bypass expiry, publish, or use the status as a substitute for human approval. A refresh recommendation must preserve source, configuration, policy, and artifact provenance.
- **Success criteria:**

- A deterministic read-only cohort report aggregates readiness status, failed rule IDs, staleness cause, expiry, and artifact/configuration/policy/revision mismatches without loading private prose into standard logs.
- It proposes the narrowest safe recovery boundary (render-only, artifact regeneration, or full re-ingest) from existing provenance and never creates a WordPress write or provider call while planning.
- Focused tests and one bounded retained-artifact run prove that a current ready package is excluded, a changed final HTML is identified as render-only, and a changed evidence/configuration/policy input is escalated appropriately.

#### P7. Improve hosted public-site performance without contract loss

- **Title:** Improve hosted public-site performance without contract loss
- **Impact 4 / effort: 3**
- **Context:** The hosted gate measures stable SEO/performance baselines, but homepage, report archive, and signal archive response-start and DOM-complete values remain materially above documented targets.
- **Benefit:** Existing measurement drives real discovery and research performance gains rather than merely preventing further regression.
- **Risks to avoid:** Do not weaken metadata, public contracts, archive completeness, or projection boundaries to gain speed.
- **Success criteria:**

- Homepage, reports, briefings, signals, methodology, contact, and submit pages improve against `config/public_site_baselines.yaml` without increased page weight or request count.
- Remaining target gaps are measured and documented.
- Hosted evidence confirms canonical URLs, Open Graph, Twitter metadata, archive completeness, and representative page contracts remain intact after optimisation.

#### P8. Complete concise public evidence, methodology, and related-content surfaces

- **Title:** Complete concise public evidence, methodology, and related-content surfaces
- **Impact 5 / effort: 3**
- **Context:** Rendering already redacts canonical IDs and exposes claim-support labels, but lacks a compact source/excerpt/limitation contract and the first useful approved relationship links.
- **Benefit:** Decision-useful evidence and discovery improve trust while keeping OCR, model, crop, and vector diagnostics operator-only.
- **Risks to avoid:** Remain concise and source-grounded; fail closed when approved data is missing.
- **Success criteria:**

- Claim support can show source report, publisher, page, concise excerpt, limitation, and original link where approved.
- Methodology shows scope, source pages, material limitations, and evidence state.
- Report pages start with deterministic related report, briefing, topic, and publisher links; tests prove redaction and fail-closed behavior when approved data is absent.

### 3. Evidence Quality and Reuse

#### E6. Retain a hash-pinned claim-embedding benchmark export

- **Impact 4 / effort: 2**
- **Context:** The semantic-selection benchmark correctly falls back when a retained corpus has no persisted vectors, so it cannot yet measure real semantic ranking on the fixed corpus.
- **Benefit:** A bounded, redacted export makes semantic quality and prompt savings reproducible without live embedding calls.
- **Success criteria:** Persist a hash-pinned, retention-governed benchmark export containing only approved vector IDs/content hashes/vectors; benchmark it in CI and compare semantic coverage against lexical fallback without provider calls.

#### E10. Attest active model-pricing rates before they become stale

- **Title:** Attest active model-pricing rates before they become stale
- **Impact 5 / effort: 1**
- **Context:** Cost-governed routes fail closed when canonical pricing is missing, stale, invalid, or explicitly held. The bundled OpenAI GPT-5.6 family rates were refreshed on 2026-08-11, but price-source review, expiry visibility, and the reviewed-rate transition remain manual operator work.
- **Benefit:** Spend estimates and report-level attribution remain trustworthy as providers update model pricing, without restoring silent zero-cost execution.
- **Risks to avoid:** Do not scrape or activate a provider rate automatically; preserve explicit operator approval, effective dates, source provenance, and the existing hold-before-I/O behavior.
- **Success criteria:**

- A bounded read-only check reports active, expiring, stale, held, and missing route rates against configured production routes with version/source metadata only.
- Operator acknowledgement creates a reviewed rate-card transition with before/after estimates for recent canonical usage; activation remains an explicit configuration change.
- Tests prove unknown, expired, held, and changed-rate routes cannot silently bypass canonical spend authority.

#### E11. Measure and optimize structured-output recovery effectiveness

- **Title:** Measure and optimize structured-output recovery effectiveness
- **Impact 5 / effort: 2**
- **Context:** Validation-run reliability artifacts now retain an attributed cohort funnel and per-attempt usage, repair, and failure data. They are not yet the compatible cross-run recovery scorecard required to compare first-pass success, repair/regeneration use, abstentions, latency, tokens, and cost by artifact and policy identity.
- **Benefit:** Identify the highest-value schema, prompt, and provider fixes that improve first-pass validity and lower repair/regeneration cost without weakening schema or abstention contracts.
- **Risks to avoid:** Aggregate only bounded metadata and never raw prompts, evidence, or model responses. Group by compatible artifact schema, provider, model, and policy versions. Produce operator recommendations and alerts only; do not automatically change routing, prompts, or failure policy.
- **Success criteria:**

- A read-only report groups compatible runs by artifact family and reports first-pass success, deterministic-repair success, model-repair success, regeneration success, abstention, terminal failure, latency, tokens, and cost.
- The report identifies the dominant classified error classes and provider-schema incompatibilities without exposing retained content.
- Configurable alert thresholds create actionable operator findings, not automatic behavior changes.
- A retained and live cohort demonstrate a material first-pass-validity or recovery-cost improvement driven by a measured finding.

#### E14. Calibrate category-fit coverage from retained outcomes

- **Title:** Calibrate category-fit coverage from retained outcomes
- **Impact 5 / effort: 2**
- **Context:** Category fitting now reconciles model advice with deterministic inclusion, exclusion, and centrality rules, can select up to five grounded categories, and preserves supported assignments without unnecessary repair. Operators still lack a compatible-cohort view of selection coverage, rescue and repair use, selected-category distribution, and the mapping concepts responsible for uncategorized outcomes.
- **Benefit:** A bounded scorecard can identify high-value mapping and prompt improvements that increase evidence-backed category coverage while reducing unnecessary model repairs, latency, and spend.
- **Risks to avoid:** Aggregate only category IDs, rule IDs, decision/count outcomes, model and policy hashes, and bounded usage metadata; never retain raw report context, prompts, or model responses. Do not automatically add mappings, weaken explicit exclusions, or turn a legitimate out-of-taxonomy report into a forced category.
- **Success criteria:**

- A read-only compatible-cohort report shows nonempty-selection rate, explicit-uncategorized rate, selected-count distribution, deterministic-rescue rate, repair rate, validation outcome, latency, tokens, and cost by mapping/prompt/model/policy identity.
- The report ranks recurring uncovered semantic concepts and excess-repair causes as operator-reviewable mapping or prompt proposals, while retaining explicit-exclusion outcomes separately.
- A retained and bounded live cohort demonstrates a measured increase in grounded nonempty selection or a reduction in unnecessary category-repair calls, with no automatic taxonomy or policy change.

#### E13. Measure candidate-regeneration promotion effectiveness

- **Title:** Measure candidate-regeneration promotion effectiveness
- **Impact 5 / effort: 2**
- **Context:** Candidate regeneration now retains atomic promotion/rollback state, evidence lineage, source-page continuity, validation issue codes, transformation scope, and before/after hashes. Operators cannot yet compare compatible candidate cohorts to identify which repair target or prompt reliably improves grounded output versus repeatedly rolling back.
- **Benefit:** A bounded, evidence-safe cohort view can prioritize the repair prompts and deterministic checks that increase successful grounded promotion while avoiding repeated model spend on candidates that cannot pass lineage or source-page policy.
- **Risks to avoid:** Aggregate only hashes, bounded counts, rule/target identifiers, and version-compatible policy metadata; never emit raw prompts, source extracts, candidate text, or model responses. Produce recommendations only and never auto-relax a blocking groundability rule.
- **Success criteria:**

- A read-only report groups compatible candidate audits by repair target, issue class, schema/policy/prompt identity, and promotion/rollback outcome, with attempt count, remapping/lost-evidence counts, source-page failures, latency, tokens, and cost.
- The report identifies high-confidence rollback patterns and separately reports valid evidence remappings and abstentions, without treating either as ungrounded content.
- Retained and bounded live cohorts demonstrate at least one operator-reviewable reduction in repeated failed repair calls or an improvement in promotion rate, with no automatic prompt, routing, or validation-policy change.

#### E12. Persist pre-category editorial context checkpoints

- **Title:** Persist pre-category editorial context checkpoints
- **Impact 5 / effort: 3**
- **Context:** Task 5 now reuses validated source, selection, and vector-store artifacts for taxonomy/category recovery, but the analysis pipeline materializes taxonomy and evidence context inside one pre-category execution boundary. A durable checkpoint immediately before category fitting would let category-only recovery avoid even the unrelated taxonomy/evidence provider calls while preserving current proof and lineage requirements.
- **Benefit:** A category-fit failure can regenerate exactly its one editorial family, then deterministically assemble only its dependent artifacts, reducing recovery latency, model calls, and spend on real report cohorts.
- **Risks to avoid:** Preserve the existing source/vector identity, taxonomy/evidence hashes, validation contracts, and bounded recovery ceilings. Do not retain raw prompts or duplicate the report-analysis orchestration boundary.
- **Success criteria:**

- Persist a versioned, lineage-validated pre-category checkpoint containing only the approved taxonomy/evidence references and their compatibility hashes.
- Make taxonomy and category recovery plans name their exact model family and required deterministic downstream work; fail closed when any retained context is stale or incomplete.
- A retained-report live recovery and focused tests prove category-only recovery makes no source, vector, taxonomy, or evidence provider call and records measured avoided tokens/cost.

#### E8. Use canonical source identity to suppress duplicate research work

- **Title:** Use canonical source identity to suppress duplicate research work
- **Impact 5 / effort: 2**
- **Context:** Schema v19 now produces stable canonical source IDs and metadata hashes for the same report observed through different routes, but selection, analytics, and cross-report retrieval do not yet consume that identity as a deduplication and filter key.
- **Benefit:** Equivalent publisher URLs and repeated downloads can reuse validated evidence and avoid duplicate parsing, embedding, and model work while making source/publisher/date filters precise.
- **Risks to avoid:** Never merge merely similar titles; require a canonical identity backed by content hash or publisher-verifiable evidence, retain all observations, and leave conflicts visible for operator review.
- **Success criteria:**

- Selection and cross-report retrieval can filter by canonical source ID, publisher, and verified publication date without exposing private provenance.
- Equivalent identities reuse validated retained artifacts and record avoided parsing/embedding/model calls; conflicting or unknown identity remains non-reusable.
- Retained-corpus and bounded live evidence measure duplicate-work suppression, false-merge prevention, and zero unintended public writes.

#### E9. Materialize prompt-family outputs and route only their required model calls

- **Title:** Materialize prompt-family outputs and route only their required model calls
- **Impact 5 / effort: 3**
- **Context:** Prompt-family outputs are now typed, hash-pinned materializations; the planner names required and reused families, and enforced repair reconciles its actual family calls against the plan. The prior 17-call composite repair is now the baseline to beat, not the current architecture. What remains is representative retained and bounded live evidence of the claimed saving.
- **Benefit:** Prompt, validator, and advisory changes can regenerate the one affected family plus deterministic downstream assembly, reducing LLM time and spend while retaining E7's plan/actual enforcement.
- **Risks to avoid:** Preserve immutable evidence, validation, claims, and rendered-HTML dependency edges; do not duplicate model routing, bypass the LLM ledger, or treat an incomplete family as reusable.
- **Success criteria:**

- Preserve typed, hash-pinned per-family materializations and their direct dependencies under the current report-analysis boundary; planner and executor must continue to reconcile required, reused, and actual family calls.
- Retained-corpus and bounded live comparisons demonstrate a material call/time/cost reduction against the 17-call composite baseline, while preserving semantic validation and zero unplanned side effects.
- Record scope, policy/prompt identities, actual ledger usage, and the reason for any no-improvement result so an operator can distinguish an unsupported repair family from a failed saving claim.

### 4. Release Integrity and Architectural Enforcement

#### R1. Publish release-evidence reviews where reviewers work

- **Title:** Publish release-evidence reviews where reviewers work
- **Impact 3 / effort: 2**
- **Context:** CI now generates the release-evidence review and appends a bounded GitHub job summary with the exact tested SHA, queue-evidence status, and unwaived issues. The remaining work is to make the archived-bundle link and final approval state available on the relevant PR/release surface, and to expand the strict retained runtime corpus with an explicit representativeness label.
- **Benefit:** Release readiness, the exact tested revision, and the scope of runtime evidence are visible where reviewers already work, reducing missed evidence and review latency.
- **Risks to avoid:** Keep summaries bounded and links stable while preserving all unwaived issue detail. Do not imply that a smoke-only corpus proves representative report processing.
- **Success criteria:**

- Keep the CI review and bounded job summary linked to the exact tested HEAD or an explicit unavailable/mismatch result.
- PR/release automation links the archived bundle and final approval status to the reviewed commit.
- The retained runtime corpus expands under the existing strict collector with declared scope/provenance; inline review distinguishes representative processing from smoke-only evidence.
- README distinguishes inline review from full archived evidence, and tests cover bounded summaries, exact-HEAD mismatch, runtime-corpus scope, and unwaived detail retention.

#### R2. Enforce role boundaries, direct-I/O discipline, and controlled module growth

- **Title:** Enforce role boundaries, direct-I/O discipline, and controlled module growth
- **Impact 4 / effort: 3**
- **Context:** CI already enforces role imports, direct-I/O ownership, service-boundary mapping, forbidden patching, refactor-movement evidence, coverage, mutation, and repository hygiene. The remaining gaps are targeted: require evidence for missing service-boundary coverage where it matters, and turn approved facade/waiver exceptions into narrow, expiring, owner-accountable records without creating generic governance noise.
- **Benefit:** Architectural constraints prevent drift before merge instead of relying on manual review and retrospective refactors.
- **Risks to avoid:** Use narrow, expiry-owned waivers and avoid noisy generic governance checks.
- **Success criteria:**

- New gates target first-party files only and require owner, reason, and expiry for every new waiver.
- A targeted service-boundary coverage gap is a failure unless explicitly waived; do not infer an integration-test requirement for pure or inaccessible boundaries.
- Documentation explains adding and retiring a waiver; tests prove the targeted violations fail and valid waivers expire as intended.

#### R3. Restore service quality coverage above the retained baseline

- **Title:** Restore service quality coverage above the retained baseline
- **Impact 4 / effort: 3**
- **Context:** The committed baseline currently records `src/services` coverage of 82.5763%, above the enforced 75% floor. The former 82.9680% comparison target has no retained baseline artifact in this repository, so it cannot serve as a verifiable acceptance threshold. Recent service growth still needs behavior-focused coverage and a clean, exact-commit full-suite measurement before the baseline is reset.
- **Benefit:** The retained quality baseline continues to reflect real protection for durable external and stateful boundaries.
- **Risks to avoid:** Add behavior tests with observable contracts or state; do not weaken floors, add exemptions, or add coverage-only paths.
- **Success criteria:**

- New behavior-focused coverage prioritizes ledger recovery, browser-worker lifecycle, and artifact-lineage failure paths.
- Assertions cover returned contracts or persisted state, not coverage-only paths.
- The quality baseline is refreshed only by a passing full CI run, records its exact SHA and measured service coverage, and demonstrates no reduction in global/generator/orchestrator coverage.

#### R6. Review bounded-log reduction telemetry and remediate recurring callers

- **Title:** Review bounded-log reduction telemetry and remediate recurring callers
- **Impact 4 / effort: 2**
- **Context:** Standard structured logging now bounds nested values and emits `log_payload_reduced` only when an event exceeds the byte contract, but operators do not yet aggregate those events to distinguish legitimate high-cardinality summaries from callers that still attempt to serialize domain payloads.
- **Benefit:** Repeated source/model/browser payload attempts become measurable remediation work, preserving useful operational summaries while reducing log volume and accidental content-retention risk.
- **Risks to avoid:** Aggregate only bounded metadata, hashes, event/module identifiers, and counts; never reconstruct discarded content or create a second unrestricted log store.
- **Success criteria:**

- Release evidence reports reduction-event count, event/module grouping, attempted-size percentiles, and zero-content samples.
- A thresholded review identifies recurring callers and links them to an owner or remediation item without exposing discarded values.
- Tests prove deterministic aggregation, redaction preservation, and that the scorecard cannot contain source text, prompts, model output, browser terminal text, or credentials.

### 5. Boundary Simplification

All work in this lane is movement-only unless behavior change receives explicit approval. Public facades, order, retries, idempotency, logs, and side effects must remain stable.

#### S3. Simplify the PDF visual-heuristics boundary

- **Title:** Simplify the PDF visual-heuristics boundary
- **Impact 4 / effort: 4**
- **Context:** The visual-heuristics, panel-detection, visual-candidate, crop, and table families have already been decomposed behind compatibility facades and documented movement evidence. This item no longer authorizes a broad facade cleanup; it owns only a measured remaining coupling that demonstrably obscures the canonical PDF boundary.
- **Benefit:** A smaller semantic surface keeps the PDF capability navigable, replaceable, and testable without scattering external-library access.
- **Risks to avoid:** Preserve candidate/crop outputs, artifact paths, and the one canonical external/library boundary.
- **Success criteria:**

- Identify a specific remaining coupling with a dependency or ownership audit before changing it; retain compatibility facades that preserve approved callers.
- Keep visual heuristics capability-owned and testable behind the canonical PDF boundary.
- Equivalence tests preserve candidate/crop behavior, artifact paths, cache semantics, and benchmark signatures.

#### S4. Give WordPress shortcodes semantic ownership

- **Title:** Give WordPress shortcodes semantic ownership
- **Impact 4 / effort: 4**
- **Context:** The WordPress shortcode class owns several unrelated public surfaces, making it difficult to isolate presentation changes and trace a shortcode to its feature contract.
- **Benefit:** Shortcode behavior becomes understandable by stable feature ownership rather than one catch-all class.
- **Risks to avoid:** Do not add navigation-only layers or alter public hooks/output during a movement-only refactor.
- **Success criteria:**

- Each extracted unit owns a coherent shortcode family and documents why the boundary reduces coupling.
- Public shortcode behavior, output, and WordPress hooks remain unchanged.
- PHP/runtime tests cover each public surface and compatibility facade, proving unchanged output and hook registration.

## Guardrails

- Never normalize cross-publisher metrics with incompatible definitions, geography, methodology, or time period.
- Never publish incomplete public pages for later enrichment; preview/draft is allowed only outside the public release surface.
- Never invent identity attributes for acquisition forms; map only configured, verified values.
- Never lower private-API promotion thresholds automatically.
- Never publish OCR, model, crop, vector, or validation diagnostics as public product content.

### Non-negotiable publishing guardrail

Automation may plan, resume, retry, repair, validate, render, draft, hold, and notify. It must not public-auto-publish until retained evidence demonstrates safe claims, no internal-ID leakage, stable crop acceptance, stable WordPress updates, duplicate suppression, rollback, and consistent editorial quality.

## Current-State Evidence

- A1 plan-first authority is now typed and checksum-bound across CLI/UI control payloads. A retained publish plan emitted no external mutation; a live zero-item publish invocation authorized before correctly failing local missing-credential validation; the full suite passed 3,888 tests in 461.92 seconds.
- A5 acquisition hard-blocker policy now reuses TTL-bound publisher route history, checks configured identity/mailbox facts, and avoids browser/mailbox work for fresh exact CAPTCHA/domain blocks unless `revalidate_route_policy` is explicitly requested. A retained CAPTCHA record confirmed the behavior; focused route/acquisition tests passed 40/40.
- Canonical LLM accounting uses SQLite with deterministic JSONL/daily projections, reconciliation, replay suppression, task-median forecasting, and configured OpenAI day guardrails.
- The retained CI accounting corpus now includes valid, invalid, replay-suppressed, and real cached-provider (`provider_hit`) events; cached-token tampering is rejected by reconciliation tests. This closes the former cached-provider corpus task.
- Claim embeddings, stale/no-embedding fallback, bounded semantic preselection, durable Signal artifacts, artifact lineage storage, and lineage invalidation are present.
- Workflow-control intent/preflight, UI dead letters, mailbox acquisition, resume checkpoints, prompt dry runs, provider decisions, and deterministic JSON-chat compaction are present.
- Public report rendering exposes approved advisory/metric-spine data while redacting canonical IDs; strict crop acceptance emits typed QA sidecars.
- WordPress report, briefing, and signal entities have REST draft/readback verification; `sync-wordpress-intelligence` now projects 64 retained local public entities (47 reports, 5 briefings, 12 signals, and 29 publishers) through the authenticated plugin route, while missing/invalid projections render neutral values. Hosted HTTPS/error handling, intake, responsive UI, and editorial leakage remain active public-site gaps.
- CI runs formatting, typing, architecture/import checks, forbidden-patching checks, hygiene, coverage, mutation, prompt regression, release-evidence archival, hash-pinned PDF candidate/crop/trend gates, public report-quality gates, and WordPress staging verification when configured.

## Audit Notes

- This register replaces duplicated simplification context, migrated x100 intake, and repeated launch plans with source-neutral status rows. No task is excluded because of its origin.
- The active backlog contains 28 outcome-owned items. Deferred, closed, and excluded rows remain visible above; any newly discovered work must be merged into an existing outcome or justified as a new one.
