# Market Lense

Enterprise PDF ingestion and analysis pipeline that converts Google Drive reports into structured HTML digests using an LLM and extraction heuristics.

---

## Executive Summary

Market Lense ingests PDFs from a configured Google Drive folder, extracts text and structured visual candidates (tables/charts), calls an LLM for a strict JSON analysis, ranks and crops key visuals, renders a compact HTML digest, and can publish the digest to WordPress. The system is organized around a strict architecture with contracts, services, generators, and orchestrators to ensure reliability, observability, and testability.

Key traits:

- Contract-first data model for all external I/O boundaries.
- Service isolation for all external systems and file I/O.
- Browser-report runtime isolation: `src/services/_browser_report_download/browser.py` remains the private coordinator behind the canonical browser-download service, while terminal-state stabilization, terminal asset/evidence capture, bounded timeout recovery, worker transport, and browser session lifecycle mechanics live under `src/services/_browser_report_download/_browser_runtime/`.
- Browser-report HTTP isolation: `src/services/_browser_report_download/http.py` remains the private compatibility surface, while PDF transfer, page-PDF probing, gate probing, onsite capture, and shared HTTP/HTML evidence live in `_http/` capability modules behind the canonical browser-report service boundary. Visible HTML evidence sanitization excludes `script` and `style` blocks even when their closing tags contain whitespace or trailing malformed tag content, so hidden confirmation or CTA tokens cannot affect terminal classification.
- Report-download workflow isolation: `src/orchestrators/report_download_orchestrator.py` remains the public facade and `_report_download_orchestrator/workflow.py` remains its sequencing coordinator, while dependency construction, candidate readiness, failed-attempt forensics, route promotion, idempotent persistence, and optional Drive archival live in focused private sibling modules.
- Generator logic that composes services into domain outputs.
- Orchestrator that controls sequencing, retries, and state (including publishing).
- Structured logging with run/task/span identifiers plus end-to-end trace IDs and nested span metadata.
- Built-in validation: semantic checks plus LLM grounding with persisted reports and publish-time policy controls.
- Validation retrieval performance: evidence windows store precomputed character n-gram vectors and norms, and `retrieve_evidence_windows` uses bounded top-k selection so metrics, quotes, numbers, grounding, and regeneration repair share faster deterministic evidence lookup.
- Validation-driven targeted regeneration: after a failed validation pass, the analysis orchestrator can regenerate only the mapped failing artifact families, re-run validation, and keep the latest canonical `validation.json` for downstream render/publish policy. Rule-level failures with pack-style sections now also route to explicit repair actions where supported, so semantic failures repair insights plus quotes and numeric/metric/quote/claim failures avoid a broad all-family retry when a narrower target is known.
- Report-analysis orchestration isolation: `src/orchestrators/report_analysis_orchestrator.py` remains the public analysis coordinator, while bounded artifact scheduling, vector-store readiness polling, payload completeness checks, validation/regeneration execution, and regeneration-plan mapping live in focused private `_report_analysis_orchestrator/` owner modules without changing prompt, retry, validation, or cost behavior.
- Confidence-scored family outputs: every evidence pack now persists a typed `family_status` record with `status`, `confidence_score`, `policy_action`, and `reason`, and generated artifact families do the same at the top level of `artifacts.json`. Low-confidence summary/insights families abstain into explicit validation regeneration targets instead of shipping weak output; quote families require a real verbatim source, and quote-only abstentions now publish as warning-level omitted-quote notices instead of forcing fake quotation text. Soft editorial families such as `expert_comment` and `linkedin_post` can also abstain with warning-level omission notices that render transparently in the HTML digest.
- Text extractability gate: before analysis, the pipeline samples deterministic pages, computes per-page plus document-level native-text confidence, and still aborts early with `pdf_text_unextractable` when none of the sampled pages contain extractable text.
- OCR fallback for scanned PDFs: with `ingest.pdf_text.ocr_fallback.enabled=true`, the source phase stays native-first, logs native sample confidence plus density, and falls back to OCR only when the sampled native text is blank, weak, sparse, or explicitly forced by `ingest.pdf_text.ocr_fallback.policy=always`. Visual previews, contents-page screenshots, candidate extraction, and crop/render steps still use the original cached PDF; text extraction, vector-store upload, and text-grounded analysis switch to the OCR PDF.
- Structured OCR validation accepts intentionally blank OCR pages while still requiring a non-empty page list, and OCR fallback text validation now uses the structured OCR page contract instead of random rendered-page sampling. This lets scanned PDFs with blank trailing pages pass when the OCR output contains usable text elsewhere.
- DocMap validation gate: if the doc_map evidence pack is empty (no sections/title/doc_id/summary), processing halts for that PDF; the orchestrator logs a detailed summary and stores it in the state DB. A `doc_map_empty:no_content` outcome is retried through the DocMap retry policy when text validation passed, so transient model no-content results do not permanently mask extractable reports.
- Cached execution: PDF info/contents/text extraction are cached by md5, and analysis outputs (evidence packs, artifacts, validation, HTML, crop-refine decisions) are cached by md5 + prompt/template hashes to skip redundant work.
- Durable report-generation checkpoints: source, selection, analysis, and render stages persist versioned checkpoints under `out/.checkpoints/report_generation/<file_id>/` with artifact references and restart payloads. The report pipeline can restart from the `analysis_complete` semantic boundary and re-render/project without rerunning source extraction, vector-store indexing, ranking, evidence packs, artifact generation, or validation.
- Deterministic PDF artifact fingerprints: preview PNGs, crop-refine page renders, and saved crop PNGs now reuse existing artifacts when a page-content fingerprint plus artifact identity, settings, and PyMuPDF/cache-version fingerprints still match. The sidecar metadata lives next to the artifact, reruns can keep unaffected page/figure outputs warm even when another page in the document changes, and cache-hit/store logs emit the key, source artifact, and validity reason.
- PDF crop isolation: `src/services/_pdf/crop.py` remains the internal compatibility facade behind `pdf_service`, while image trimming/composition, crop geometry guards, table-continuation stitching, crop-region artifact writes, crop-refine rendering, and preview rendering live in focused private `_crop/` modules without changing artifact fingerprints, filenames, render settings, or crop ordering.
- Drive listing efficiency: `src/services/drive_service.py` now streams Drive file pages incrementally instead of materializing full page sets up front, caches recursive folder-scope expansion with TTL-based invalidation, and bounds thread-scoped Drive client reuse with expiring max-size caches so long-lived runs do not accumulate stale clients.
- Report-source cache loading: `src/generators/report_source_cache.py` now centralizes the repeated PDF info / contents / extracted-text cache path resolution plus hit/miss/write logging, while `report_source_generator` keeps explicit typed payload validation for each cached phase.
- Cached analysis packs are schema-validated again on cache hits before reuse, so stale evidence/artifact/validation payloads are treated as misses instead of being served forward. Cached artifact payloads also refresh current family policy on read and clear now-abstained artifact families before reuse.
- Atomic artifact writes: analysis packs, rendered HTML, semantic response cache files, HTML/source cache JSON, and cost-ledger artifacts now write through atomic temp-file replacement in `src/services/file_service.py`, so interrupted writes do not leave partial final files behind and stale `*.tmp-write-*` leftovers are cleaned on later writes.
- Orchestrator step idempotency: `src/services/idempotency_service.py` persists step scope, logical key, input checksum, serialized outcome, and artifact references in SQLite so duplicate side-effecting orchestrator steps can reuse prior outcomes instead of duplicating external writes; checksum mismatches raise a typed non-retryable error instead of silently reusing stale side effects. Current coverage map: `publish_orchestrator` protects the WordPress publish step, `report_download_orchestrator` protects publisher-route history writes, browser-identity config updates, report-source rows, and Drive archive uploads, and `publisher_inventory_orchestrator` protects run-quality history writes, deferred-recovery cache rows, publisher-state updates, discovery test-status updates, snapshot uploads, and discovered report-source rows.
- Batched state prefilter: Drive-list skip checks for `(file_id, md5)` are grouped into batch SQLite queries to reduce per-file DB round trips; per-file state checks run only when the final resolved md5 differs from the Drive md5. Previous `doc_map_empty:*` states with passing text validation and progress-only states without a final text-validation verdict are selected for retry instead of being treated as fully processed.
- SQLite metadata/state stores use WAL mode with connection-local busy timeouts, and ingest access checks now use a lightweight schema probe so readers do not escalate to write locks while another WAL writer is active.
- SQLite schema migrations now run through `src/services/sqlite_migration_service.py`, which is the schema authority for `state_db`, `reports_db`, and `ui_run_registry`. Each database persists a `schema_version` row plus ordered `schema_migration_ledger` entries, and service startup applies only pending migrations while logging migration IDs and durations with the active run context. Legacy schema upgrades, rollback-on-failure, and idempotent reruns are covered in the service test suite.
- Low-text resilience: text density heuristics detect PDFs with little/no extractable text and emit explicit "not available from text" artifacts + HTML notices instead of blank sections.
- Artifact reference robustness: artifact evidence IDs are canonicalized against docpacks before validation (supports comma/list-like model output and quote aliases such as `quote_1 -> q1`), preventing TL;DR/insights/quotes dropouts caused by malformed IDs.
- Claim-span grounding: summary `claim_evidence_map` entries now carry normalized `evidence_spans` derived deterministically from known evidence packs/doc-map sections, validation rejects summary claims that lack a bound evidence ID/span path, and rendered HTML exposes compact public citation micro-lines using safe evidence ID, report page, and citation labels when available for summary claims, insights, and quotes while suppressing local artifact IDs and path-like citation targets. Unknown quote speakers now render as `<Publisher name> expert team`.
- Deterministic TOC structure: artifacts now include authoritative `toc_entries`, built directly from eligible `doc_map.sections` in source order. Legacy `toc_topics` and `toc_topics_expanded` are compatibility projections derived from `toc_entries`, and HTML renders the Covered topics section from those deterministic entries.
- TOC integrity guard: validation now enforces one-to-one coverage between eligible DocMap sections and generated TOC structure, flags missing/duplicate/stale/out-of-order entries with machine-readable repair metadata, logs `artifact_topic_brief_mapping_audit` diagnostics for mapped and unmapped `toc_topics_expanded` topic briefs, and targeted regeneration rebuilds `toc_entries`, `toc_topics`, and `toc_topics_expanded` deterministically from DocMap without another model call.
- HTML digest quality: rendered HTML now uses semantic sections (`header/main/section`), premium split hero layout, sticky glass navigation with scrollspy + reading progress, reveal animations (with reduced-motion fallback), signal-style insight cards, editorial quote cards, and long-text chunking for generated prose.
- Modernized report rendering: `render_service` now builds a normalized presentation view from the analysis payload plus resolved evidence packs, while the HTML template is split into shared macros and shared CSS. Metadata now sits directly below TL;DR, executive content renders as concise bullets, editorial cards expose methodology/coverage/findings/limitations/contacts/ordered chapters when available, and image tags resolve real `width`/`height` plus conditional `srcset`/`sizes` from sibling asset variants.
- HTML digests now keep report-derived metadata when the reports DB has gaps, show a compact report-identity line in the hero, emit an explicit missing-source note when no source URL was extracted, and group generated expert/social copy into a trailing appendix section.
- Public source provenance now resolves original acquisition URLs from `report_sources` when analysis payloads are blank, carries them through typed report projection, Briefing, and Signal contracts, and renders public citations as report/page labels instead of evidence IDs, crop/cache paths, or local artifact targets.
- Figure UX: rendered digests now include a template-native figure carousel with prev/next controls, keyboard and swipe support, thumbnail rail, slide counter, and fullscreen lightbox.
- Figure loading: the lead figure in the carousel now renders with eager/high-priority image loading so below-the-fold visual evidence does not disappear in static captures or delayed browser paint scenarios.
- Sticky digest navigation: the report shell keeps `overflow: visible` so the sticky section navigation and reading-progress bar continue to pin during scroll instead of being disabled by container clipping.
- Per-image figure captioning: after artifacts are generated, the pipeline can run a fail-open multimodal captioning pass for each final cropped figure asset using the image plus compact report context (`title/publisher/region/time period`, TL;DR + executive summary, nearest DocMap section, top findings/claim-evidence highlights, and figure-local signals). Captions are stored per slide, rendered in the carousel, and audited in `report_analysis/figure_captions.json`; on failure the pipeline keeps rendering with legacy/detected/placeholder fallback captions.
- OpenAI image-call compatibility: crop-refine image requests to the Responses API now omit known unsupported params (e.g., `temperature`/`seed` on `gpt-5*`) preflight and still retain fallback retry-without-param handling for unknown model/param mismatches.
- OpenAI service consolidation: `src/services/openai_service.py` is the single OpenAI client boundary (client construction, request/response parsing, shared response-metadata adaptation, usage-accounting emission, and provider error normalization). Cost ledger persistence for those calls is owned by `src/services/openai_accounting_service.py`, which delegates ledger append/rollup writes to `src/services/cost_ledger_service.py`.
- Shared LLM orchestration: `src/services/llm_service.py` wraps model-call clients with one retry/backoff/circuit-breaker API plus optional scope-level rate limiting. Report-pipeline evidence/artifact clients and default generator LLM clients now use this shared wrapper instead of local pass-through retry wrappers.
- Artifact LLM scheduling is owned by `src/orchestrators/report_analysis_orchestrator.py`: the artifact generator now emits deterministic render tasks and executes serially unless the orchestrator supplies a bounded executor. The orchestrator applies `artifact_parallel_workers` and `artifact_global_max_in_flight`, logs `artifact_step_batch_start` / `artifact_step_batch_complete` with the effective budget, and propagates step failures back to the artifact stage without creating generator-owned thread pools.
- Canonical LLM call path: production generators, report-pipeline orchestration, ranking/crop-refine, OCR/image-call dependency wiring, and vector-store provider adapters now enter model/provider calls through `src/services/llm_service.py`. The shared boundary exposes the default OpenAI-backed client builder, preserves the public monkeypatch seam for tests, and logs provider/cache/budget-policy context together with retry, rate-limit, and circuit-breaker decisions for each wrapped model call.
- OpenAI semantic response caching: JSON, image JSON, OCR, and vector-store response requests can opt into deterministic cache files under the configured cache directory. Cache keys include prompt/context/model parameters plus image/PDF/vector-store fingerprints, and figure ranking/crop-refine calls enable the cache through the report settings cache path.
- Refusal-aware retry handling: OpenAI content-filter/refusal/policy, auth, bad-request, and other permanent provider errors are normalized into typed non-retryable `AppError` codes, and the shared LLM retry wrapper logs the concrete retry decision code before retrying or failing.
- UI-run replay tooling: background UI worker runs now persist `state/ui_runs/<run_id>/replay_manifest.json` with the recorded request payload, sanitized config fingerprint, source-tree fingerprint, prompt-tree fingerprint, result summary, and artifact hashes. `python -m src.cli replay-run --run-id <run_id> [--registry-path ...]` replays the recorded UI run, blocks on source/prompt/config drift, and writes a delta report under `state/ui_runs/<run_id>/replays/` for incident response.
- Local browser-download automation: `src/services/browser_report_download_service.py` remains the single public browser-download service boundary, while action-specific internals now live under `src/services/_browser_report_download/` for request preparation, prompt rendering, browser runtime execution, HTTP PDF recovery, artifact adaptation, and deterministic pre-browser doc-type prediction. Artifact finalization retains one coordinating entrypoint in `artifact.py`; its PDF materialization, on-site capture, terminal classification, evidence verification, and recovery capabilities are grouped privately under `_browser_report_download/_artifact/` without changing route behavior or external-call ownership. The download orchestrator now reuses discovery/diff candidate evidence from `PublisherInventoryCandidateTrace` instead of re-planning from the candidate URL alone: candidate `pdf_url` values are probed before browser-use, source-page hints and provenance labels are passed into the browser prompt, and browser-use only runs when discovery-aware HTTP probing cannot verify a PDF. A lightweight pre-browser predictor now logs a structured score, reason, and probe URL for every attempt, unwraps direct PDF targets exposed through redirect/query parameters before browser startup, and can promote report-detail HTML pages into the embedded-PDF probe even when no explicit browser route hint was provided. Browser task instructions now live entirely in the prompt namespace at `src/prompts/browser_report_download/browser_route/`; the service passes only structured variables such as identity entries, remembered route steps, route-family labels, and discovery trace fields into `prompt_service`, and the logged browser-download prompt event now captures those prompt variables together with prompt paths, hashes, rendered prompt text, and model parameters. Browser prompts are now tailored per route family (`browser_pdf_click`, `browser_email_form`, `browser_tracker_redirect`, `browser_listing_hub`, `browser_onsite_report`) so the browser agent gets different instructions for CTA clicks, gated forms, redirects, listing hubs, and on-site longreads, including an explicit rule not to submit optional lead forms when an on-page longread is already readable, an explicit wait-through for transient submit states such as `Please Wait`, and explicit guidance not to misclassify ordinary text-field issues as enum blockers. Remembered browser-route reuse now carries both the stored summary and the stored structured route steps into the next prompt, so successful actions such as cookie acceptance plus extract/capture can be replayed deterministically instead of being reduced to one prose hint. Known remembered on-site extract routes can now also short-circuit through direct HTML capture before browser-use starts, which turns stable public longreads into fast deterministic `onsite_report` successes instead of spending the full browser timeout budget. Successful and failed attempts still project the best route back into `reports_db.publishers`, but richer structured route evidence now also lands in `publisher_download_route_history` for reuse and debugging. The store derives ranked per-route-family policy signals from exact-URL history and same-publisher/domain history, including verified successes, confidence, recent outcomes, and typed blocker reasons, so the planner can put URL-proven strategies first and publisher-proven strategies ahead of static URL heuristics when enough cross-report evidence exists. Readiness rejection now logs explicit scores and typed rejection reasons, blocker inference ignores arbitrary article/footer text in favor of real blocker-like terminal signals, older generic email-route memories are canonicalized back to `browser_email_form`, and planner fallback now prefers form-specific browser guidance when remembered evidence shows a URL is email-gated. The browser runtime now keeps the browser session alive through post-run capture, stabilizes terminal states with route-family quorum checks over URL/title changes, DOM text, network events, observed document URLs, and download artifacts instead of relying on blind fixed sleeps, falls back to the active page state when browser-level HTML/title fields are empty, falls back again to the last agent-history URL/title/screenshot when `browser-use` has already reset the live session, can fall back to page-level screenshots when the browser-level screenshot hook fails, now mines document-like terminal URLs from both performance resources and DOM candidates, persists typed `network_events` inside `DownloadTerminalEvidence`, prefers stabilized terminal URL/HTML over stale agent payload when building confirmation evidence, clears reported PDF MIME metadata when no real local file exists, and now adopts real PDF artifacts produced outside the managed browser download directory (for example `save_as_pdf` temp artifacts) before validating the route result. Browser agent runs now execute with an explicit outer timeout, always isolate live browser-use execution in a worker subprocess outside pytest so stalled asyncio/browser teardown cannot block the orchestrator process, log the worker dispatch/request/response lifecycle, use a managed per-run browser profile directory inside the report download folder instead of leaking `browser-use-user-data-dir-*` temp profiles into `%TEMP%`, skip locked stale managed profile directories during pre-run cleanup instead of aborting the next attempt, prune stale browser-use temp directories before launch, remove newly created browser-use temp fallbacks after each run, prime browser-use timing fields before forced stop so pre-start shutdown cannot raise cloud-event timing errors, suppress reconnect teardown during post-run capture, clear the browser-use CDP reconnect target before intentional shutdown, await cancelled browser-use reconnect tasks so worker teardown does not leak pending asyncio tasks, keep teardown mode active until the next live reconnect instead of scheduling shutdown-time auto-reconnects, map BrowserStart watchdog timeouts to a typed retryable service error, and clear stale blocker codes when a verified artifact was actually captured. Empty browser results can now fall back to a direct HTML fetch of the terminal or attempt URL so longreads such as DataReportal pages can still be recovered as `onsite_report` captures even when browser-use returns no structured JSON. On-site routes auto-capture local HTML artifacts when the agent omits `onsite_capture_path`, `browser_onsite_report` can fetch the final page HTML to recover a longread capture even after an unnecessary optional form submission, and paginated on-site captures now stay inferred/partial until traversal evidence or an explicit end-state shows the report is complete. Browser-route retries are also stricter now: a non-retryable browser failure on a remembered browser route no longer falls through into generic fallback steps, and a browser timeout or a `browser_download_route_summary_too_weak` failure on a planned browser step is treated as terminal for that step instead of replaying the same browser route immediately. Email confirmation still requires multiple signals instead of a submit click alone, and now accepts network confirmation/submission evidence when the browser runtime exposes it; fetched terminal HTML can upgrade weak transient submit states into verified `email_requested` outcomes when the final page confirms success, while unverified `pdf_download` claims that produce no artifact are now surfaced as typed claim-validation failures instead of being conflated with genuine missing-file downloads. `src/config/browser_download_identity.yaml` supports reusable form identity values plus optional host-scoped form value overrides loaded as configuration data rather than hardcoded download-flow branches. Browser form-filling values are loaded from `src/config/browser_download_identity.yaml`, and any newly encountered form field labels are appended there automatically as new keys with empty values for later completion.
- Browser worker console hygiene: the browser-use worker subprocess now runs with explicit UTF-8 stdio settings, its stdout/stderr is captured instead of inheriting the parent terminal, and only a sanitized ASCII diagnostic excerpt is surfaced on worker failures. Rendered browser prompts redact configured identity values in logs while the raw prompt still reaches the browser worker, and the per-run worker request payload is discarded after normal completion or timeout so identity material is not retained in browser-download artifacts.
- Browser-download stall recovery hardening now polls completed browser-use history while the agent thread is still alive, so a terminal `done` result can return before stalled cleanup consumes the full timeout. It also treats completed browser-use history, partial email-form lookup failures, partial business-email-domain rejections, and cached terminal browser state as terminal service results instead of letting cleanup, lookup-assist, or LLM step stalls surface as `browser_download_agent_timeout`; after the configured agent budget is reached, stop handling now uses a short poll because completed-history recovery already runs during the live polling loop. The prompt now tells browser-use to return `blocked_email_domain` immediately when the configured email is rejected as non-business, rather than retrying the same value. The lookup-assist and terminal-salvage paths are bounded, generic HTTP anti-bot access challenges are classified as typed `blocked_captcha` results before browser-use spend on email-form routes, empty-page failures map to retryable `browser_download_page_not_loaded`, unverified remembered routes are marked as weak prompt memory, and configured Location/Country autocomplete failures are preserved as `blocked_unknown_required_enum` rather than being collapsed to missing identity data. The April 21, 2026 Mintel live run confirms the current terminal behavior: `email_delivery / email_required` with `blocked_unknown_required_enum` for the unresolved Location autocomplete, not a browser-process stall, and seeds reusable Mintel role/department/industry/location identity overrides in `src/config/browser_download_identity.yaml`.
- Browser-download route validation now avoids several live-run stall amplifiers found in the April 21, 2026 random report probe. Tracker detection uses exact host/path tokens so ordinary publisher hosts are not misrouted, weak email-route memory only influences fallback when it contains actionable form/download evidence, `/reports/<detail>` URLs are no longer treated as listing hubs purely because the slug is short, generic whitepaper/ebook/download/register paths route directly to email-form planning instead of wasting a browser-PDF attempt, and singular `/insight/<slug>` plus guide/playbook/research-style URLs route to onsite capture. The service now probes report-detail candidate HTML for direct onsite capture before browser-use when the fetched page is a real article, materializes browser-use temp PDFs and missing onsite captures into the managed download directory before temp cleanup, fetches observed terminal document URLs including relative `.pdf` links before accepting a blocked form result, repeats that PDF completion pass after terminal HTML recovery when the initial browser payload was too thin or too large to inline, ignores worker metadata JSON as candidate downloads, and uses token-aware non-report marker checks so words such as `self-expression` do not block report salvage.
- Browser-download PDF recovery now also includes a generic landing-page PDF-link probe before browser-use. For PDF-oriented and email-form routes, the service fetches the landing-page HTML, extracts embedded `.pdf` links, keeps only links relevant to the landing-page URL/title tokens, and downloads the verified PDF directly. This removes unnecessary browser-use spend when the real PDF URL is already present in the report HTML without using publisher-specific URL constructors.
- Browser-download terminal evidence now has a Marketlense-owned raw-CDP escape hatch inside `src/services/_browser_report_download/cdp.py`, adapted from the small browser-harness `cdp()` pattern without importing or shelling out to browser-harness. The allowlist is intentionally narrow: `Runtime.evaluate` may read bounded terminal performance state, `Page.captureScreenshot` may persist a terminal screenshot when browser-use screenshot hooks fail, `Page.printToPDF` may persist a browser-rendered PDF capture for verified printable on-site report pages, `Target.getTargetInfo` may inspect focused-target identity for diagnostics, and `Target.getTargets` / `Target.attachToTarget` / `Target.detachFromTarget` may create and clean up a transient evidence-only session when browser-use session state is unavailable. Print-to-PDF capture is bound to the verified final page URL and fails closed when Chrome exposes only a startup, blank, or otherwise mismatched target. Generated print captures stay classified as `onsite_report` artifacts with `onsite_capture_format=browser_rendered_pdf` plus `browser_rendered_pdf_capture` / `not_publisher_supplied_pdf` evidence labels, so they are never reported as publisher-supplied `pdf_download` files. CDP calls log method, allowlist reason, target/session IDs, result status, `run_id`, `task_id`, and `span_id`; required CDP failures raise typed `AppError` values, while optional terminal-evidence probes log failures and keep the normal browser-use route as the source of actions.
- Browser-download terminal inspection now uses the approved Marketlense-owned helper surface in `src/services/_browser_report_download/helpers.py`, adapted from browser-harness `page_info`, `capture_screenshot`, and `js` patterns without a runtime dependency on browser-harness. `helpers.py` remains the stable private compatibility facade, while page state diagnostics live in `_browser_report_download/_helpers/state.py`, JavaScript inspection lives in `_helpers/inspection.py`, and screenshot/autocomplete interactions live in `_helpers/interaction.py`. The helpers stay inside the existing browser-download service boundary, return typed contracts from `src/contracts/_browser_download/helpers.py`, log structured start/complete/failure events, and do not read prompts, choose retries, or orchestrate workflows. The live browser runtime now routes terminal page-info and screenshot capture through those helpers, giving debugger-visible source labels and screenshot provenance for post-run evidence.
- Browser-download terminal evidence now also promotes JavaScript dialog and `beforeunload` states into typed `BrowserDownloadDialogEvidence` records. The implementation adapts browser-harness dialog-drain practice plus the vendored browser-use popup watchdog: already auto-closed popup messages are surfaced from browser-use runtime state, while pending/frozen dialogs are drained through allowlisted `Page.enable` / `Page.javascriptDialogOpening` / `Page.handleJavaScriptDialog` CDP handling. Alerts are accepted to unblock terminal capture, confirm/prompt dialogs are dismissed and marked `policy_rejected`, and `beforeunload` is accepted only in the explicit teardown path; all dialog evidence records type, sanitized message, action, validation status, and CDP target/session IDs when Chrome exposes them.
- Browser-download target hygiene now adapts browser-harness tab hygiene into the existing CDP helper boundary. Before terminal evidence screenshots, the runtime filters internal Chrome/devtools/about/omnibox-style targets, resolves the verified final-page target when available, checks `Page.getLayoutMetrics` for zero-size surfaces, logs a typed `BrowserDownloadTargetHygieneResult`, and uses `Target.activateTarget` plus browser-use focus repair when headed/persistent evidence needs the intended tab visible. A rejected zero-size or mismatched target fails closed for diagnostics instead of silently capturing the wrong tab.
- Browser-download gated-form recovery now includes a Marketlense-owned `browser_helper_form_autocomplete` helper adapted from browser-harness keyboard/input patterns without a runtime dependency on browser-harness. The helper types configured identity values through keyboard-style `KeyboardEvent` and `InputEvent` dispatch, selects visible autocomplete/dropdown/native-select options, verifies the persisted input value after blur before submission, logs selected/unresolved fields, and preserves unresolved required enum controls as typed `blocked_unknown_required_enum` blockers instead of generic browser failures.
- Browser-download JavaScript inspection now uses a safer browser-harness-style `js()` wrapper with sync and async helper entrypoints. The wrapper accepts top-level `return`, awaits promise-returning snippets, reports sanitized snippets, maps thrown JavaScript errors into typed helper failures with line/column fields when the browser exposes them, and stringifies non-JSON-serializable results instead of failing inspection. Browser-download terminal resource collection and preflight rendered-DOM/event-drain probes now use this wrapper instead of ad hoc `page.evaluate` calls.
- Browser-use route steps now carry mandatory post-action verification fields on `BrowserDownloadRouteStep`: `expected_evidence`, `observed_evidence`, and `verification_status`. The browser-download artifact service derives expected evidence from each meaningful action, reuses terminal evidence categories such as screenshot, page info, network event, artifact, DOM hash, and confirmation text, logs one verification verdict per step, and raises `browser_download_route_step_verification_missing` before returning a partially evidenced browser result.
- Browser-download runs now include a bounded browser preflight before full browser-use agent launch for browser route families. The preflight lives inside `src/services/_browser_report_download/preflight.py`, uses a short Marketlense-owned browser-use session to open the execution URL, collect page info, run a small rendered-DOM JS probe, and drain resource-event URLs, then either downloads a rendered direct PDF as `browser_preflight_js_pdf_probe` or logs escalation evidence for the full agent. Preflight metrics log avoided agent calls, duration, candidate counts, escalation reason, and a per-run false-negative sample once the full agent outcome is known.
- Browser-download route playbooks now live as independent YAML files under `src/playbooks/browser_routes/`, with the format documented beside them. The browser-download service loads fresh playbooks before browser-use prompt rendering, selects matches by host/path marker plus route family, logs selected `playbook_id@version` values, and falls back to normal discovery or raises `browser_route_playbook_stale` according to `browser_download.route_playbook_stale_policy`. Validated successful browser route results can be promoted into reviewable playbook file updates with version/history metadata and a unified diff.
- Browser-download playbooks can now carry network-learned private API evidence in separate `src/playbooks/browser_routes/private_api/*.yaml` files, adapted from browser-harness domain-skill rules for durable endpoint/request-shape capture. Verified browser runs now replay safe same-host GET endpoint candidates without cookies or auth headers, derive JSON pointers only when the response yields the verified PDF URL, store repeated observations in the report-store private-API candidate ledger, and automatically promote only after the configured success/source thresholds. Operators can still promote reviewed evidence with `python -m src.cli promote-private-api-playbook --request-json <path>`, where the JSON payload is a `BrowserRoutePrivateApiPromotionRequest`. Promotion requires repeated validated success, documented request shape, response JSON pointer, accepted statuses, and explicit fallback route family. Before browser-use launches, the service can validate a selected private API endpoint, extract a PDF URL, verify the artifact through the existing direct-PDF downloader, and log playbook ID/version, endpoint pattern, validation result, and fallback reason when the endpoint is stale.
- Report-download recovery planning now records typed recovery classes and decisions on every route-plan step, logs blocked browser-to-HTTP recovery classes, and only adds browser-to-HTTP PDF probing after browser-derived candidates when the candidate has distinct HTTP/PDF signal. Mixed-content hub candidates are rejected with `candidate_rejected_mixed_content_hub` before acquisition, while remembered on-site report routes and strong report-detail candidates still keep their direct HTML capture recovery paths.
- Report-download archival hardening now preflights required Google Drive archival before acquisition starts, refreshes OAuth credentials through the canonical Drive service when possible, verifies the target folder can accept child files, creates a missing publisher archive folder under the configured Drive parent and persists it back to `reports_db.publishers.google_folder`, uses short atomic temp names for long Windows artifact paths, scopes source-record and Drive-upload idempotency by checksum, and deduplicates equivalent local artifact paths before Drive upload, so expired credentials, missing scopes, unwritable folders, missing publisher folders, repeat browser captures with changed generated PDFs, same-named screenshots, or path aliases do not crash or duplicate archive uploads.
- Review follow-up hardening makes private-API auto-promotion bookkeeping fail-soft after a successful report acquisition: candidate-ledger and promotion-marker `AppError` failures are logged with structured skip reasons without aborting the completed download. Cross-report boundaries now reject non-contract roots, malformed numeric limits, and explicitly blank required model/prompt settings; projection upserts persist report `time_period`, source reads filter on that period rather than projection timestamps, and category IDs remain alongside display labels so ID-based selection stays consistent through generator re-filtering.
- Browser-download gated-form handling now avoids browser-use on obvious lead-form report pages. Route planning sends generic report/resource detail URLs that look like downloadable assets to the email-delivery route after the embedded-PDF probe, static HTML preflight detects common form providers and report CTAs, route-confirmed email pages that time out during static fetch are classified as bounded `email_required` outcomes, and email-route preflight budgets are shorter than general PDF probing so slow gated pages do not consume the browser runtime. The April 21, 2026 `random10_20260421_fresh7` live run confirmed 10 typed terminal results with 0 app errors, 0 browser-use timeouts, and 0 browser-use launches.
- Batch acquisition auditing: `src/orchestrators/acquisition_audit_orchestrator.py` composes the existing publisher-inventory discovery flow with isolated report-download audits, reuses the accepted `current_candidates` plus discovery run-quality summary as download inputs, and writes one JSON artifact containing publisher-level and candidate-level acquisition maps for the current publishers without re-running discovery or diff logic inside the download phase.
- Publisher-inventory screening and quality now use broader publisher-agnostic route/title heuristics for buyer guides, trends, forecasts, and barometers, reject generic case-study/help/self-service/service-hub pages more aggressively, and reject bare report-collection hubs even when their landing page is structurally rich.
- Publisher-inventory candidate screening remains exposed through `src/generators/publisher_inventory_candidate_screening_generator.py`, while shared marker normalization, deterministic prefilter/fallback policy, response merge/dedupe policy, and LLM batch/repair execution now live in focused private `_publisher_inventory_candidate_screening/` modules without changing prompt payloads, batch sizing, model-call count, or decision ordering.
- Publisher-inventory discovery/screening/quality now also normalizes placeholder archive-card titles like `feature-img` back to URL slugs, follows broader report-library routes such as `publications` / `whitepapers` / `livres-blancs`, rejects generic `/service/`, `/software/`, `/who-we-help/`, and editorial detail pages more aggressively even when they sit under report/archive sources or expose generic forms/download CTAs, and keeps unreachable report-detail pages when the URL/title/source-page context still strongly identifies a real report asset.
- Publisher-inventory discovery falls back from an empty HTTP parse to the next available route before finalizing a publisher run, so sites that need rendered-browser discovery are not marked empty after the first parser returns no report candidates.
- Direct report landing pages now seed themselves as browser-discovery candidates when the page URL is strongly report-like but the DOM only exposes navigation links, which reduces false negatives on single-report insights URLs.
- Report-download route planning treats report-detail URLs with digital-year slugs as on-site report capture candidates and attaches explicit extract/capture steps, allowing public longreads to become durable acquired artifacts instead of timing out in a generic browser route.
- Refactor simplification layer: shared boolean/numeric coercion and list-normalization helpers now live in `src/utils/coercion.py`, shared slug-tag normalization and fail-open JSON prompt serialization live in `src/utils/tag_utils.py` and `src/utils/json_utils.py`, UI/dashboard row serialization is centralized in `src/utils/gui_utils.py`, orchestrator retry wrappers are centralized through `retry_orchestrator.run_step_with_default_policy`, and duplicate WordPress term ensure logic is consolidated into a shared internal helper.
- Evidence-pack strategy scaffolding is centralized in `src/generators/evidence_packs/base.py`: the repetitive list/scalar wrapper normalization, empty-payload factories, alias fallback, and `_cache` preservation are shared there, while each strategy module still owns its explicit field mapping and item/value transforms.
- Additional boundary cleanup: Streamlit settings/prompt rendering now routes through `src/ui/settings_page.py`, `src/services/state_service.py` is a thin canonical boundary over focused internal state modules, and the config + ingest entrypoints are phase-split so `load_settings`, `run_ingest`, and `run_ingest_file` read as explicit control-flow stages instead of monolithic implementations.
- Ops tooling cleanup: duration diagnostics now share one implementation in `scripts/duration_tools.py` (legacy entry scripts delegate to it), and legacy Streamlit config cleanup flags (`ingest.debug_candidate_gallery`, `analysis.compare`) were removed from the structured editor path.
- Streamlit dashboard read models now cache per browser session in `st.session_state` for reports/state/log/storage snapshots, and explicit refresh or mutating UI actions (ingest, publish, recategorize, cover generation, config save) invalidate the affected cached views before the next read.
- Figure quality gate: candidate visuals now pass deterministic prefilters, kind-split ranking, adaptive GPT crop refinement, and strict final cropping before HTML render. The detailed extraction, crop, and fallback heuristics live in [Technical Design Notes](#technical-design-notes).
- Candidate extraction split: `pdf_service.collect_candidates` remains the canonical PDF-candidate service boundary. `table_heuristics.py` is the stable internal compatibility surface over `_table_heuristics/{policy,models,layout,regions,screening}.py`; `visual_heuristics.py` is the stable facade over `_visual_heuristics/{chart_layout,panel_text,panel_geometry,panel_detection,collectors}.py`; and `visual_candidates.py` is the stable facade over `_visual_candidates/{raster,screening,extraction}.py`. Heuristic rationale and known limits are grouped in [Technical Design Notes](#technical-design-notes).
- Table candidate dedupe uses a page-local spatial lookup inside `_table_heuristics/screening.py` for both pdfplumber candidates and the final table merge in `table_candidates.py`, so dense reports avoid repeated full scans while preserving the existing IOU, containment, ranked-overlap, and inner-lattice preference rules.
- Typed candidate features: extracted table/chart candidates now carry a versioned `CandidateFeatures` contract used by ranking, crop-refine prompts, and deterministic prefilters. The contract includes OCR density, normalized visual entropy, and chart/table confidence signals; legacy candidate metadata remains as a compatibility projection.
- Shared raster probe cache: visual bbox analysis reuses page-local raster renders and derived white/dark/saturation/edge profiles for repeated candidate inspections, with hit/miss counters included in extraction stats.
- Shared page-artifact cache: `pdf_service.build_pdf_context` now seeds a reusable per-page PDF artifact cache, and visual extraction, table extraction, and crop/refine passes reuse the same parsed text-block/page-state data through that shared context instead of rebuilding it on each pass.
- Candidate window control: post-prefilter truncation is kind-aware so one noisy flow cannot crowd the other out before ranking. The ranker now also sends a compact per-kind signal payload instead of the full candidate feature contract, with generator logs capturing legacy-vs-compact payload chars, estimated input tokens, and estimated input cost deltas for each ranking batch. The exact prefilter, recovery, and spillover rules are documented in [Visual Candidate Pipeline](#visual-candidate-pipeline).
- Crop output safety: strict crop modes use candidate-ID outputs and conservative text-edge correction so table/chart saves do not collide and partial border text is trimmed or recovered safely. See [Ranking, Crop Refinement, and Fallback](#ranking-crop-refinement-and-fallback).
- Candidate crop reuse: when `out/<report>/candidates/candidates.json` already contains fallback crop paths, report selection now reuses those persisted `candidates/*.png` assets before attempting a new legacy crop pass, and only crops the missing fallback candidates.
- SEO-ready HTML: rendered digests include shortened `<title>` handling, `meta description`, Open Graph/Twitter cards, optional canonical URL, JSON-LD (`Article`) structured data, explicit image `width`/`height` attributes to reduce CLS, and automatic `noindex,nofollow` on low-content fallback pages.
- Vector store is the default and only analysis path; legacy local_text prompt stuffing has been removed now that vector_store is validated.
- Vector-store lifecycle cleanup: `vector_store_service` exposes canonical delete/prune operations, retention cleanup runs from the ingest orchestrator, and `analysis.vector_store_retention_days` defaults to `30` days. When `analysis.vector_store_keep=false`, the per-run vector store is deleted after report generation and the persisted state is not kept as a reusable vector cache.
- Taxonomy extraction now separates report-level signal tags from portal categorization: the prompt returns `primary_tags`, `secondary_tags`, a merged `taxonomy` list, and per-tag `tag_evidence` as metadata for search/filtering, while portal categories are assigned separately from report context using category definitions in `src/config/category-mappings.yaml`.
- HTML metadata chips normalize slug-style taxonomy values into readable labels (e.g., `ai-in-retail` -> `AI in Retail`) with acronym preservation loaded from `src/config/html-tag-acronyms.yaml`.
- Publish file ID resolution is DB-first: publish/publish-queue share the same HTML-path canonicalization and reports-metadata (`html_path -> file_id`) lookup helper, then fall back to HTML parsing only when mapping is unavailable. Targeted publish runs can also pass explicit HTML paths, which allows live repair/publish verification for a known artifact set without depending on alphabetic output-directory ordering.
- Publish HTML reuse: the publish orchestrator now carries a typed `PublishHtmlSnapshot` with loaded HTML, parsed file ID/title/body, and discovered image sources so each publish attempt reads an HTML artifact at most once and the generator does not reparse the same payload for media, title, or body extraction.
- Publish media upload safety: oversized raster assets are resized and converted to optimized JPEG payloads in memory before WordPress media upload, with original/optimized dimensions and byte counts logged. Smaller assets and non-image payloads are uploaded unchanged.
- Publish-time validation-report parsing is centralized in `src/utils/validation.py` so the publish path maps JSON payloads to `ValidationReport` consistently before applying policy decisions.

---

## Architecture Overview

Related architecture notes:
- `docs/architecture/publisher-inventory-orchestrator-decomposition-review.md`: semantic split review for the publisher-inventory public orchestrator and its private owner modules.
- `docs/architecture/publisher-discovery-success-playbook.md`: scenario-driven optimization plan to improve publisher inventory discovery success rates and reduce false negatives.
- `docs/quality/deep-analysis-x10-plan-2026-04-15.md`: 50 proposal deep-analysis roadmap covering quality, stability, speed, and cost x10 opportunities by module.
- `docs/quality/repository-analysis-exclusions.md`: shared exclusions for repository analysis tools so generated, vendored, temporary, cache, replay, and local reproduction trees do not pollute maintainability signals.
- `wordpress_implementation_map.md`: concise map of the WordPress theme, plugin shortcode surfaces, reusable CSS systems, and smoke scripts tied to front-end template changes, including the canonical Briefings and Signals shortcode entrypoints.


The codebase follows a strict layered architecture under `src/`:

```text
src/
  contracts/         # Dataclass contracts for inputs/outputs
  services/          # External I/O services (Drive, OpenAI, files, etc.)
  generators/        # Domain logic (report generation)
  orchestrators/     # Control plane / pipelines
  utils/             # Pure helpers (no I/O)
  prompts/           # LLM prompt templates (YAML)
```

### Roles

- **Contracts**: Define schema and shape of inputs/outputs at service boundaries. No logic.
- **Contract family facades**: Large contract surfaces keep one public module boundary, while semantic dataclass families can live under same-name internal subfolders. Current examples include `src/contracts/publisher_inventory.py` with `src/contracts/_publisher_inventory/*`, `src/contracts/browser_download.py` with `src/contracts/_browser_download/*`, and `src/contracts/report_store.py` with `src/contracts/_report_store/*`.
- **Implementation family facades**: Large first-party service, generator, and orchestrator surfaces keep their original public import path as a facade while semantic implementation families live under a same-name internal folder. Current examples include `src/services/config_service.py` over `src/services/_config_service/*`, `src/services/openai_service.py` over `src/services/_openai_service/*`, `src/services/publisher_inventory_service.py` over `src/services/_publisher_inventory_service/*`, `src/generators/artifact_generator.py` over `src/generators/_artifact_generator/*`, and `src/orchestrators/report_download_orchestrator.py` over `src/orchestrators/_report_download_orchestrator/*`.
- **Services**: Only I/O. Talk to external APIs, filesystem, databases, or system resources. No business logic.
- **Schema validation**: JSON schema loading/validation is treated as I/O and lives in `src/services/schema_validator_service.py`.
- **Generators**: Compose services and enforce domain rules (e.g., which charts are selected, how outputs are structured).
- **Orchestrators**: Define when and in what order things happen, including retries and state transitions.
- **Utils**: Pure deterministic functions (no I/O, no global state).

Current control-plane modules in `src/orchestrators/` include:

- `ingest_orchestrator.py`: batch-level ingest control (locking, DB access checks, worker fanout, cursor updates).
- `ingest_file_orchestrator.py`: single-file ingest execution (cache/download/EOF checks, report pipeline call, state writes).
- `report_pipeline_orchestrator.py`: report-generation pipeline boundary with retry-aware control around report generation.
- `report_generation_orchestrator.py`: source -> selection -> analysis -> render sequencing for a single report.
- `report_analysis_orchestrator.py`: vector-store analysis control including taxonomy/evidence/artifacts/validation and the bounded validation-regeneration loop.
- Report generation and report analysis are intentionally entered through those orchestrators; deprecated generator-level sequencing stubs have been removed so callers do not depend on a misleading compatibility API.
- `publish_orchestrator.py`: publish workflow and publish-state transitions.
- `publish_queue_orchestrator.py`: publish queue snapshot assembly for UI/ops surfaces.
- `report_download_orchestrator.py`: local browser-use report acquisition with per-URL route memory, retry-aware fallback from remembered route to fresh discovery, early non-report readiness rejection, and typed outcome classification (`pdf_download`, `email_delivery`, or `onsite_report`).
- `cost_reporting_orchestrator.py`: filtered cost report + rollup orchestration.
- `ops_dashboard_orchestrator.py`: dashboard snapshot aggregation (reports/state/lock/storage).
- `candidate_extraction_orchestrator.py`, `cover_image_orchestrator.py`, `recategorize_orchestrator.py`, `wp_category_update_orchestrator.py`: feature-specific workflows.

### Intelligence Entity and Navigation Model

Market Lense is organized around intelligence objects, not implementation objects. The public product model is defined by the entities users navigate, cite, compare, and trust; the pipeline, projections, WordPress metadata, and persisted artifacts are implementation layers behind those entities.

Primary public navigation:

```text
Reports | Topics | Signals | Briefings | Publishers
```

Secondary public discovery surfaces:

```text
Figures | Regions | Time Periods | Methodology
```

Operator/admin surfaces:

```text
Sources | Runs | Validation | Publishing Queue | Cost
```

Figures, Regions, and Time Periods support discovery across the primary navigation. Sources, Runs, Validation, Publishing Queue, and Cost are operational surfaces and should not be treated as public navigation. Data Points are internal metric/evidence records that power user-facing Figures, including key figures in a report.

Canonical entity definitions:

- **Report**: the atomic source-backed content unit. A report represents one validated source digest and must retain source attribution, publisher, evidence references, validation status, time period, geography, topic assignments, and the generated HTML artifact used for publication.
- **Topic**: a stable editorial domain. Public language should say Topics even when WordPress internally uses native categories. Raw tags are metadata; Topics are navigable editorial destinations with explicit definitions, inclusion rules, and exclusion rules.
- **Signal**: a navigation-worthy market movement, pattern, shift, risk, opportunity, contradiction, or weak signal. Signals are first-class intelligence entities, not only homepage modules. A Signal must remain evidence-backed by Reports and Data Points, and contradictory or low-confidence support must be represented explicitly.
- **Briefing**: the executive synthesis layer. Cross-report analysis, weekly updates, topic deep dives, trend analyses, publisher landscapes, category updates, competitive signals, and executive memos should be exposed publicly as Briefings rather than hidden inside report pages.
- **Publisher**: a source organization. Publisher surfaces should show source profile, coverage topics, latest reports, related signals, freshness, and source links where those relationships are recoverable. Publisher self-description must remain separate from Market Lense assessment.
- **Data Point**: an internal metric/evidence record such as a metric, statistic, quote, claim, figure caption, methodology note, or limitation. Data Points power Signals, Briefings, search, trust, and user-facing Figures. Public WordPress language should normally say Figures, Key Figures, or Key figures in report rather than Data Points.
- **Source**: an operator-facing acquisition candidate. A discovered URL is not a Report until acquisition, extraction, validation, and artifact generation have succeeded. Operators should be able to inspect acquisition route, outcome, blocker reason, and whether the Source became a report, an onsite capture, an email-required item, a rejection, or a failure.
- **Methodology**: the trust and process layer. Methodology explains how Market Lense ingests, extracts, validates, scores, abstains, publishes, and exposes limitations. It should distinguish deterministic checks from LLM judgments and disclose weak text, OCR-derived content, validation warnings, and abstention states.

Entity relationship model:

```text
Publisher
  -> publishes Sources
        -> become Reports
              -> assigned to Topics
              -> contain Data Points
              -> produce Signals
              -> feed Briefings

Topic
  -> groups Reports
  -> groups Signals
  -> anchors Briefings

Signal
  -> supported by Data Points
  -> derived from Reports
  -> summarized in Briefings

Briefing
  -> synthesizes Reports
  -> organizes Signals
  -> cites Data Points
  -> spans Topics and Publishers
```

Public entity pages must expose only validated generated HTML artifacts and approved metadata or projections. WordPress is the publication layer, not the intelligence-generation layer. WordPress must not generate new report interpretation, new signals, evidence maps, cross-report synthesis, metric normalization, uncertainty claims, publisher authority claims, or freshness claims. Those outputs must come from validated pipeline artifacts or approved recoverable projections.

Report pages and report cards should link to related Topics, Signals, Publishers, Figures, and Briefings when those relationships are recoverable. Topic, Signal, Publisher, Figure, and Briefing pages should be assembled from approved projections and validated artifacts rather than inferred at render time.

### Cross-Report Analysis Scope Fence

Cross-report analysis is a bounded extension of the existing modular monolith and produces the public-facing **Briefing** entity family. The first implementation stays inside the current `src/` deployable and must not introduce a new top-level package, standalone worker, separately deployed service, peer analytics database boundary, peer WordPress client, or parallel publication subsystem.

Role boundaries:

- Contracts: `src/contracts/cross_report_analysis.py` and `src/contracts/signal_candidates.py`.
- Existing services reused: `src/services/analytics_store_service.py` for projected SQLite reads plus durable Signal candidate read/write, `src/services/report_analysis_store_service.py` for ingestion artifact-pack writes, `src/services/prompt_service.py` for prompt loading/rendering/versioning, `src/services/llm_service.py` for model calls, `src/services/file_service.py` for artifact writes, `src/services/idempotency_service.py` for duplicate-run protection, and the existing publish boundary for WordPress side effects.
- Generators: `src/generators/cross_report_analysis_input_generator.py` remains the compatibility facade for deterministic source/theme/evidence preparation, with focused internals under `src/generators/_cross_report_analysis_input/`; `src/generators/signal_candidate_generator.py` turns scored signals and agreement groups into durable candidate/group contracts; `src/generators/report_signal_artifact_generator.py` builds ingestion-time Signal extraction requests and `signals.json` artifact payloads without I/O; `src/generators/cross_report_analysis_generator.py` handles synthesis and deterministic artifact validation; `src/generators/cross_report_publish_html.py` assembles report-style cross-report publish HTML.
- Orchestrators: `src/orchestrators/report_generation_orchestrator.py` runs ingestion-time Signal artifact generation after successful analytics projection; `src/orchestrators/cross_report_analysis_orchestrator.py` owns Briefing sequencing, retries, idempotency, persistence, and optional publication routing; `src/orchestrators/signal_candidate_orchestrator.py` owns deterministic Signal candidate extraction and storage from already-projected reports.
- Prompt namespace: `src/prompts/cross_report_analysis/synthesis/`.
- CLI command: `python -m src.cli generate-cross-report-analysis`.
- Tests: contract round trips and invalid-input taxonomy in `tests/test_cross_report_analysis_contracts.py`, config loading coverage in `tests/test_config_service.py`, generator tests for selection/synthesis semantics, orchestrator pipeline tests for retry/idempotency/logging, and analytics-store SQLite integration tests for projected-data reads.

First-release non-goals: no metric normalization, unit conversion, or cross-publisher statistical harmonization; no new WordPress plugin or custom post-type dependency; no global semantic/vector retrieval product over `vector_projection_queue`; no new deployable worker, microservice, package, or external search service.

The cross-report contract family starts in `src/contracts/cross_report_analysis.py` with schema version `1.0`. It defines the request, orchestrator request, theme candidate, selected theme, source report candidate, selected source report, projected-data read request/response, evidence reference, signal score and signal-score result, evidence agreement group/result, raw metric reference, generated section, generated analysis result, validation result, persisted analysis artifact, cross-report publish package, publish request summary, publish result summary, and orchestrator outcome contracts. Required semantic fields are validated by `validate_cross_report_contract`, which raises non-retryable `AppError(code="cross_report_contract_invalid")` when a contract is incomplete, uses an unsupported schema version, or passes `None` for list-typed fields; empty lists remain allowed where the contract marks them optional.

Projected cross-report source reads use the canonical analytics-store boundary: `src/services/analytics_store_service.py::read_cross_report_projected_data`. The service reads the existing projection tables (`reports`, projected claims/findings/quotes/metrics/tags/categories, and `vector_projection_queue`) documented in [Analytics Projection Foundation](#analytics-projection-foundation) and returns `CrossReportProjectedDataReadResponse` dataclasses rather than raw SQLite rows. Supported filters include publisher name/id, projection/report date range, category id/label, tag, requested content class, and minimum projection status. The response carries source candidates, evidence references, raw metric references, per-entity projection content hashes, and excluded-report counts for downstream selection and readiness logging. Legacy projected rows with blank publishers or unscoped entity IDs are adapted at this service boundary into deterministic publisher fallbacks and stable `report_id:kind:id` evidence/metric IDs before contracts reach generators.

Deterministic source selection starts in `src/generators/cross_report_analysis_input_generator.py::select_cross_report_source_reports`; implementation now lives in `_cross_report_analysis_input/source_selection.py` behind that facade. The generator accepts a typed `CrossReportAnalysisRequest` plus `CrossReportProjectedDataReadResponse`, cleans request filters, validates and normalizes `YYYY-MM-DD` date bounds before comparison, scores candidates by filter/topic relevance, evidence density, recency, and publisher diversity, applies the configured `max_source_reports` cap, and returns a `CrossReportSourceSelectionResult` with ranked selected sources, rejected candidates, normalized filters, grouped exclusion counts, and structured ranking logs. Invalid dates fail closed with `AppError(code="cross_report_date_filter_invalid")`. Selection uses only projected metadata and source-bound evidence counts; it does not perform semantic/vector retrieval or metric normalization.

Projection readiness is enforced before synthesis inputs are selected. Non-diagnostic requests reject candidates whose `projection_status` is not `projected`, record grouped exclusion reasons such as `projection_status_failed` or `projection_status_not_projected`, and raise non-retryable `AppError(code="cross_report_no_projected_sources")` when no projected source remains. Diagnostic requests may inspect failed or missing projections, but that path is explicitly represented by the request contract and logged by the generator.

Automatic theme choice is exposed through `select_cross_report_theme`, with implementation in `_cross_report_analysis_input/theme_selection.py`. Explicit-topic requests produce a selected theme from the operator topic and already-selected sources. Auto-theme requests, or requests with an empty topic and `auto_theme=true`, build deterministic tag/category candidates from selected projected sources, score them by evidence density, source-publisher coverage, recency, and novelty, and return `CrossReportThemeSelectionResult` with ranked candidates, the selected theme, score components, source report IDs, and structured logs. Tag and category axes are validated independently so a tag-only or category-only projected source set remains eligible instead of failing contract validation. No model call is used for theme choice.

The theme selector supports a bounded variety policy before synthesis. Recent artifact loading runs only for automatic theme selection; explicit-topic requests do not read historical artifacts. When a recent-artifacts root is provided for automatic selection, the generator reads prior `analysis.json` metadata through `file_service.list_directory` and `file_service.read_text`, applies the configured `theme_rotation_window_days`, excludes old, undated, and invalid-date artifacts from rotation penalties with structured skip counts, and down-ranks repeated theme IDs, tags, and categories by lowering the novelty component and attaching explicit repetition risks such as `recent_theme_repetition` or `recent_category_repetition:retail`. Theme score weights for density, diversity, recency, novelty, and filter fit are function parameters so orchestrator/config wiring can tune the policy without changing prompt or model behavior.

`validate_cross_report_publishability` is the deterministic gate before synthesis or publication. It checks minimum selected source reports, minimum distinct publishers, minimum evidence items, duplicate-theme risk, explicit metric-normalization dependency risks, and publish-mode validation prerequisites. Failed gates raise non-retryable `AppError(code="cross_report_publishability_failed")` unless the request is diagnostic or carries `override_publishability=true`; override results are logged and returned with `override_applied=true` plus the preserved issue list.

Evidence-bearing synthesis inputs are assembled by `assemble_cross_report_analysis_inputs`, with evidence assembly, signal scoring, and agreement grouping implemented in `_cross_report_analysis_input/evidence_signals.py`. It reuses the selected-source and projected-read contracts, keeps only evidence and raw metrics from selected reports, deduplicates repeated evidence rows by `(report_id, evidence_id)` so source-local IDs can coexist across reports, applies `max_evidence_items` before prompt rendering, groups selected evidence IDs by report, and logs dropped rows by reason. Raw metrics remain source-bound facts with original `raw_value`, `unit`, `context`, and metadata; the analytics-store read boundary adapts metric IDs from projection `metric_uid` values so identical source labels such as `metric-1` do not collide across reports.

Lightweight signal scoring is handled by `score_cross_report_signals` in the same generator boundary. It reuses the selected theme and bounded evidence inputs, builds deterministic taxonomy/text candidates, matches fallback text on token or phrase boundaries so short labels such as `AI` do not match unrelated words, disambiguates generated signal IDs after slug normalization, and scores recurrence, publisher diversity, recency, taxonomy fit, quote/finding support, and contradiction presence with `cross_report_analysis.signal_score_weights` from YAML. Raw metric magnitudes, units, and values are explicitly ignored for ranking and remain source-bound appendix inputs; the returned `CrossReportSignalScoreResult` records `raw_metric_policy="raw_metrics_preserved_without_normalization"` and logs selected signal components for auditability.

Evidence agreement grouping is handled by `group_cross_report_evidence_agreement`. It uses selected signal evidence plus selected source metadata to label prompt-ready groups as `convergent`, `divergent`, or `thin_coverage` before synthesis. Divergence requires opposed directional language on non-overlapping evidence IDs across multiple reports and publishers, so mixed language inside one evidence row does not create synthetic cross-source disagreement. Thin coverage is carried forward when a signal has only one report or publisher, and each prompt uncertainty input includes the group label, evidence IDs, source report IDs, agreement type, and deterministic uncertainty reasons.

Durable Signal candidates are built after deterministic signal scoring and agreement grouping. `src/contracts/signal_candidates.py` defines schema-versioned `SignalCandidate`, `SignalCandidateGroup`, store/read, and extraction outcome contracts. Candidates retain type, title, source-backed summary, confidence, strength, support level, explicit caveats, source report IDs, evidence IDs, source refs with projected table/entity/page lineage, raw scoring context, validation status, and generated timestamp. `src/generators/signal_candidate_generator.py` rejects unsupported candidates without source-backed evidence, classifies support as single-report, multi-report convergent, multi-report divergent, or weak coverage, and preserves raw metric policy/context without normalizing metrics. `src/services/analytics_store_service.py::upsert_signal_candidates` and `read_signal_candidates` persist/read candidates and groups in SQLite tables `signal_candidates` and `signal_candidate_groups`; ingestion stores them in the dedicated Signal base configured by `paths.signal_store_db` (default `./state/signals.sqlite`) while projected evidence remains sourced from `paths.reports_db`. Idempotent reruns update stable IDs and remove stale rows only for the same extraction request. `src/orchestrators/signal_candidate_orchestrator.py::run_signal_candidate_extraction` coordinates projected-data reads, source/theme/evidence selection, signal scoring, agreement grouping, candidate generation, and store writes with structured transition logs.

In normal report ingestion, Signal generation runs after analytics projection succeeds because projected claims/findings/quotes are the canonical grounding source. `src/orchestrators/report_generation_orchestrator.py` builds a single-report Signal extraction request, reads projected evidence from `reports_db`, stores approved candidates/groups in `signal_store_db`, and writes a `signals.json` pack through `report_analysis_store_service` under the same `out/<report>/report_analysis/` artifact lifecycle as `artifacts.json` and `validation.json`. The `signals.json` payload records the source report ID, ingestion run/task IDs, projected reports DB, reusable Signal store DB, extraction request ID, candidate/group counts, support levels, accepted Signal kinds, operating rules, candidate/group contracts, artifact path, and artifact hash. The rendered `IngestOutcome.evidence_packs` and render-stage checkpoint include the `signals` pack path.

Cross-report synthesis prompts live in the dedicated `src/prompts/cross_report_analysis/synthesis/` namespace and render only structured, bounded JSON inputs: request metadata, selected theme, selected sources, signal scores, evidence agreement groups, evidence references, raw metric appendix, and generation policy. The prompt now asks for an industry-expert, boardroom-ready editorial article while preserving the same evidence-only JSON contract and citation rules. The dry-run fixture in `src/prompts/_dry_run_fixtures.yaml` covers realistic divergent evidence and raw metrics, and the prompt fixture corpus baseline records the `cross_report_analysis` family at 2,369 tokens with an estimated fixture cost of `$0.002167`.

`src/generators/cross_report_analysis_generator.py::generate_cross_report_analysis` performs synthesis through the existing prompt and LLM service boundaries. It validates typed cross-report inputs, renders the synthesis namespace through `prompt_service`, logs prompt paths/hashes/rendered text/model parameters, checks the rendered system plus user prompt length before any model call, makes one bounded JSON model call through `llm_service`, logs the raw response, and adapts the payload into `CrossReportGeneratedAnalysisResult`, the internal generated-analysis contract behind public Briefings. The adapter canonicalizes known projected `entity_uid` citations back to the selected `evidence_id` values because projections expose both identifiers to the model, rejects alias collisions before adaptation with `AppError(code="cross_report_analysis_evidence_alias_collision")`, and still rejects genuinely unknown citations. The generator fails closed with non-retryable typed errors when the model returns no JSON, empty sections, over-budget rendered prompts, unknown evidence IDs, or unknown raw metric IDs. Unsupported `source_notes` payloads are omitted from evidence-backed sections rather than being auto-attributed to arbitrary evidence.

Deterministic artifact validation runs in the same generator module through `validate_cross_report_generated_analysis`. It checks generated sections, evidence maps, cited evidence IDs, prompt budget characters, and metric-normalization language before persistence or publication. Unknown evidence IDs, sections without evidence, empty evidence maps, prompt-budget breaches, or phrases such as normalized averages across publishers raise non-retryable `AppError(code="cross_report_analysis_validation_failed")` after logging the structured `CrossReportValidationResult`.

`src/orchestrators/cross_report_analysis_orchestrator.py::run_cross_report_analysis` is the control-plane entrypoint for generation. It blocks execution when `cross_report_analysis.enabled=false`, rejects automatic or empty-topic theme selection when `cross_report_analysis.auto_theme_enabled=false`, reads projected data through `analytics_store_service`, runs deterministic selection/theme/evidence/signal/agreement generators, passes `theme_rotation_window_days` plus the cross-report artifact root into automatic theme selection, enforces the configured prompt input character cap before prompt rendering or model calls, loads prompt hashes through `prompt_service`, checks `idempotency_service` before model synthesis, and owns retry/backoff for retryable service or generator failures through `retry_orchestrator.run_with_retry`. Its idempotency material includes material version `2.0`, the validated request, projected-data request, output root, evidence/signal/prompt caps, publish target route, selected report IDs, selected projection content hashes, prompt hashes, generation-relevant config fingerprint, model, temperature, timeout, seed, cache-enabled flag, auto-theme gate, theme-rotation window, and schema version, so changed observable outputs, policy controls, or projection content invalidate the cache. Idempotency logs include the material version, material field list, and miss diagnostics for output-affecting controls.

Cross-report cost controls are configured under `cross_report_analysis` in `src/config/app.yaml`: `max_source_reports`, `max_evidence_items`, `max_prompt_chars`, `model`, `temperature`, `timeout_seconds`, `cache_enabled`, `auto_theme_enabled`, `theme_rotation_window_days`, `min_theme_source_publishers`, `publish_enabled`, `publish_requires_validation_pass`, and `signal_score_weights`. Budget gates raise non-retryable `AppError(code="cross_report_prompt_budget_exceeded")` with prompt size, cap, evidence limit or rendered prompt size, request id, and operator action when bounded evidence input or rendered prompts are too large. Structured logs include source selection, theme selection, publishability checks, evidence assembly, signal scoring, agreement grouping, prompt hashes/rendered prompts, retry decisions, idempotency checks/reuse, artifact writes, and publish decisions.

Validated generation persists a deterministic local artifact at `out/cross_report_analysis/<analysis_slug>/analysis.json` or the CLI-specified output root. The orchestrator builds a `CrossReportAnalysisArtifact` with schema version, generated timestamp, request fingerprint, idempotency key, selected report IDs, projection content hashes, prompt hashes, config fingerprint, validation status, generated result, validation result, publish package, and publish summaries, then writes it through `file_service.write_bytes` so the write is atomic and reviewable.

After deterministic validation passes, `src/generators/cross_report_analysis_generator.py::build_cross_report_publish_package` creates a `CrossReportPublishPackage` with publish-ready Briefing title, slug, excerpt, body HTML, full review HTML, source report map, evidence reference appendix, raw metric appendix, uncertainty/divergence notes, prompt hashes, validation hash, artifact hash, category/tag labels, machine-readable metadata, and default target route `wordpress:ml_briefing`. The HTML is assembled through `src/generators/cross_report_publish_html.py` using the same digest-style shell as ingested report pages: hero, sticky section navigation, executive synthesis, strategic read-through cards, source map, uncertainty notes, evidence references, and raw metric appendix. The generated HTML includes a `data-market-lense-publish-entity="true"` JSON script containing `schema_version`, `entity_type`, `source_artifact_id`, `canonical_route_intent`, and `publish_eligible`, so the publish path can route the artifact from the artifact contract rather than a filename or caller branch. The package is still built for review in non-live modes, but it fails closed with `AppError(code="cross_report_publish_validation_failed")` when `cross_report_analysis.publish_requires_validation_pass=true` and validation did not pass.

Publication stays inside the existing publish control plane. The cross-report orchestrator decides the operator mode and delegates `publish_dry_run` or `publish_live` to `src/orchestrators/publish_orchestrator.py::publish_cross_report_package`; that path reuses the existing `publish_generator` and WordPress service boundary instead of introducing a peer WordPress client. The canonical publish route map is metadata-driven: `report` plus `wordpress:ml_report` routes to `ml_report` and the Reports section/template, `briefing` plus `wordpress:ml_briefing` routes to `ml_briefing` and the Briefings section/template, and `signal` plus `wordpress:ml_signal` routes to `ml_signal` and the Signals section/template. Missing, unsupported, ineligible, or entity/route-mismatched metadata fails with typed publish errors and structured logs instead of publishing to a default section. `publish_cross_report_package` maps `wordpress:ml_briefing` to the bundled `ml_briefing` REST post type for lookup and create calls, passes the package slug through to the WordPress create payload, resolves package category labels into native category terms, resolves package tag labels into native tags, and resolves source publisher labels into `ml_publisher` terms. It leaves the configured report post type untouched. Its live idempotency key includes selected theme ID, selected report IDs, artifact hash, validation hash, prompt hashes, target route, and WordPress post type, so unchanged live publishes reuse the same canonical outcome instead of creating duplicate posts. If WordPress already contains the same cross-report `file_id` but the current package checksum has no matching publish idempotency record, live publish fails with `AppError(code="cross_report_publish_existing_post_checksum_mismatch")` instead of silently skipping changed content. If a live `wordpress:ml_briefing` publish returns a permalink outside `/briefings/`, the publish result is an error with `AppError(code="cross_report_briefing_url_mismatch")`, preventing cross-report Briefings from landing in Reports or unclassified post routes.

Grounded Signal posts use the same projected-data and publish boundaries without exposing Briefing contracts as the public Signal contract. `src/generators/signal_post_generator.py::build_signal_publish_projection` reads `CrossReportProjectedDataReadResponse` from `analytics_store_service`, prefers approved stored `SignalCandidateReadResponse` candidates/groups when available, otherwise selects approved projected claims/findings/quotes across distinct source reports, requires topic/category relationships, and returns `SignalPublishProjection` with schema version `1.0`, deterministic title/slug, summary/body HTML, evidence IDs, source report IDs, topic IDs/labels, tag labels, publisher labels, confidence, uncertainty, validation status, stable pseudo file ID, and target route `wordpress:ml_signal`. Stored candidate reuse preserves candidate IDs, group IDs, support levels, and caveats in the generated Signal body. Insufficient evidence, missing source coverage, or missing topic/category relationships fail closed with `AppError(code="signal_grounding_insufficient")`.

`src/orchestrators/signal_post_orchestrator.py::run_signal_post_workflow` is the Signal control-plane entrypoint. It builds a projected-data read request against the analytics store, reads approved stored Signal candidates from `SignalPostWorkflowRequest.signal_store_db` when provided (falling back to the reports DB for compatibility), delegates Signal construction to the generator, and routes `publish_dry_run` or `publish_live` through `src/orchestrators/publish_orchestrator.py::publish_signal_projection`. That adapter converts the approved Signal projection into the existing publish package shape only at the publish boundary, maps `wordpress:ml_signal` to the bundled `ml_signal` REST post type, resolves topics into native categories, tags into WordPress tags, and publishers into `ml_publisher` terms, passes the deterministic slug through to WordPress, and validates live readback placement by rejecting published URLs outside `/signals/` with `AppError(code="signal_publish_url_mismatch")`. Dry-run output exposes the exact target route, post type, slug, category slugs, tag slugs, and publisher taxonomy slugs without creating a WordPress post.

Publication modes are:

- `generate_only`: generate, validate, persist review HTML and artifact, and mark publication as not requested.
- `validate_only`: generate, validate, persist review HTML and artifact, and explicitly skip publication.
- `publish_dry_run`: build the publish package and route through the publish orchestrator without WordPress side effects. The CLI prints the target route, target post type, target slug, category slugs, tag slugs, and publisher taxonomy slugs that would be used.
- `publish_live`: requires `cross_report_analysis.publish_enabled=true`, requires a passed validation result, loads normal `PublishSettings`, and then performs the WordPress side effect through the existing publish boundary. Live output prints the same payload classification plus the WordPress post ID and `/briefings/.../` URL.

The focused CLI command is `python -m src.cli generate-cross-report-analysis`. It accepts `--topic`, `--auto-theme`/`--no-auto-theme`, comma-separated `--category`, `--tag`, and `--publisher` filters, `--date-start`, `--date-end`, `--max-report-count`, `--max-evidence-items`, `--max-prompt-chars`, `--publish-mode`, `--output-root`, `--idempotency-db`, and optional `--request-id`. If neither auto-theme flag is provided, the CLI uses `cross_report_analysis.auto_theme_enabled` as the request default; the orchestrator still enforces `cross_report_analysis.enabled` and the auto-theme gate before reading data. Without `--request-id`, the command derives a stable request id from normalized inputs so repeated unchanged runs can hit orchestration idempotency. Successful runs print the artifact path, selected theme, selected report count, validation status, publication mode, target route, target post type, target slug, category/tag/taxonomy classification, WordPress post ID/URL when available, idempotency reuse, and cost summary when available; typed `AppError` failures are printed as `Error [code]: message`.

Example:

```bash
python -m src.cli generate-cross-report-analysis \
  --topic "AI adoption" \
  --auto-theme \
  --category Retail \
  --tag AI \
  --date-start 2026-05-01 \
  --date-end 2026-05-31 \
  --max-report-count 2 \
  --max-prompt-chars 80000 \
  --publish-mode generate_only \
  --output-root ./out
```

Safe rollout for operators is: run `generate_only` for artifact review, run `publish_dry_run` to verify publish routing and package metadata without WordPress side effects, then enable `cross_report_analysis.publish_enabled=true` in YAML and run `publish_live` only after validation is passing and the target WordPress settings are confirmed. `publish_live` remains blocked by configuration by default.

Live Briefing publication uses the same command path:

```bash
python -m src.cli generate-cross-report-analysis \
  --topic "AI adoption" \
  --auto-theme \
  --publish-mode publish_live \
  --output-root ./out
```

First-release non-goals: no metric normalization, unit conversion, or cross-publisher statistical harmonization; no separate WordPress plugin beyond the bundled Market Lense plugin; no global semantic/vector retrieval product over `vector_projection_queue`; no new deployable worker, microservice, package, or external search service.

Troubleshooting notes:

- Empty eligible report sets fail as `cross_report_no_projected_sources`; inspect filters, date range, `minimum_projection_status`, and `excluded_report_counts` in the logs.
- Projection failures remain in the analytics projection foundation; use diagnostic mode only for inspection, and fix failed projection rows before publishable synthesis.
- Prompt budget caps fail before model spend as `cross_report_prompt_budget_exceeded`; reduce `--max-report-count`, use `--max-evidence-items`, narrow filters, use `--max-prompt-chars`, or raise `cross_report_analysis.max_prompt_chars`.
- Validation failures raise `cross_report_analysis_validation_failed`; inspect missing evidence IDs, empty section/evidence-map issues, prompt-budget values, and metric-normalization language in the logged validation result.
- Idempotency reuse is expected on unchanged reruns. If a rerun does not reuse the prior outcome, compare selected report IDs, projection content hashes, prompt hashes, model parameters, schema version, and generation config fingerprint in the artifact.

## WordPress Subproject

The `Wordpress/` folder contains the rendering and portal layer for Market Lense:

- block theme: `wp-content/themes/marketlense`
- core domain plugin: `wp-content/plugins/marketlense-core`
- packaging, provisioning, sync, and smoke-test scripts: `Wordpress/scripts/*`

### Public Entity Model

The WordPress public navigation follows the README entity model: Reports, Topics, Signals, Briefings, and Publishers.

- Reports use the existing `ml_report` custom post type at `/reports/`, while legacy digest posts in core `post` remain supported through recovered digest metadata.
- Signals use the `ml_signal` custom post type and the canonical route `wordpress:ml_signal`. The durable Signal publish projection is `src/contracts/wordpress_entities.py::SignalPublishProjection` with schema version `1.0`, title, slug, summary/body HTML, evidence IDs, source report IDs, topic IDs/labels, tag labels, publisher labels, confidence, uncertainty, validation status, stable pseudo file ID, and target route.
- Briefings use the `ml_briefing` custom post type and the canonical route `wordpress:ml_briefing`. Briefing content is not generated by a duplicate WordPress generator; it is the existing `CrossReportPublishPackage` from cross-report analysis.
- `/signals/` and `/briefings/` are page-compatible archive landings rendered by block templates and shortcodes, and CPT archives are also available for sites that do not provision those pages.
- Signal and Briefing detail pages use the `single-ml_signal.html` and `single-ml_briefing.html` block templates.

### Scope

Included:

- FSE block theme templates/parts/patterns for editorial rendering
- WordPress plugin for the Report, Signal, Briefing, and publisher taxonomy domain model
- ZIP packaging scripts for backoffice installation
- local sync, provisioning, and smoke-test scripts

Excluded:

- Docker/runtime stack
- Python ingest/publish orchestration logic in `src/`

### Runtime Expectation

This repo does not ship a local WordPress runtime. Use an existing local or hosted WordPress 6.6+ / PHP 8.2 environment, then install the packaged plugin/theme ZIPs through WP Admin.

### Current Structure

```text
Wordpress/
  config/
    publisher-homepages.json
    publisher-profiles.json
  wp-content/
    themes/
      marketlense/
        style.css
        theme.json
        functions.php
        screenshot.png
        assets/{css,js}
        templates/*
        parts/*
        patterns/*
    plugins/
      marketlense-core/
        marketlense-core.php
        uninstall.php
        readme.txt
        includes/*
  scripts/
    build-theme-zip.sh
    build-plugin-zip.sh
    build-plugin-zip.ps1
    provision-site-structure.sh
    seed-publisher-homepages.sh
    sync-publisher-profiles.sh
    smoke-test.sh
  dist/
```

### Plugin Contract

Plugin slug: `marketlense-core`

Current plugin package version: `1.2.10`. Deploy this package or newer when the
live WordPress REST schema must expose `ml_signal` and `ml_briefing`; older or
stale deployed payloads can still report the same plugin slug while exposing
only `ml_report`.

Primary responsibilities:

- Registers custom post type `ml_report` (`show_in_rest=true`, REST base `ml_report`)
- Registers custom post types `ml_signal` and `ml_briefing` (`show_in_rest=true`, REST bases `ml_signal` and `ml_briefing`)
- Registers taxonomies:
  - native WordPress `category` support on `ml_report`, `ml_signal`, and `ml_briefing` for public topic/archive/filter UX
  - `ml_publisher`
- Keeps legacy `ml_topic` taxonomy data internal only for backward compatibility; it is not a public archive/filter surface
- Registers publisher term metadata:
  - `ml_publisher_homepage`
  - `ml_publisher_insights_url`
  - `ml_publisher_icon_source`
  - `ml_publisher_notion_page_id`
  - `ml_publisher_notion_page_url`
- Registers and exposes report metadata keys:
  - `ml_file_id`
  - `ml_publisher_name`
  - `ml_time_period`
  - `ml_region`
- Synchronizes metadata/taxonomy projections from published digest content and existing tags/categories on save
- Treats the canonical public IA as Reports, Topics, Signals, Briefings, and Publishers. Current WordPress internals may still implement those surfaces through `ml_report`, native categories, publisher terms, shortcodes, and approved projections; WordPress must not synthesize new intelligence at render time.
- Provides shortcodes:
  - `[ml_report_browser]`
  - `[ml_home_metrics]`
  - `[ml_hero_snapshot]`
  - `[ml_featured_digest]`
  - `[ml_intelligence_signals]`
  - `[ml_strategic_themes]`
  - `[ml_publisher_authority]`
  - `[ml_topics_directory]`
  - `[ml_publishers_directory]`
  - `[ml_publisher_profile]`

### Theme Contract

The block theme is organized as an editorial intelligence portal:

- Full-site editing templates and template parts for header, footer, archives, trust pages, search, and ingest-first singles
- Homepage assembled from reorderable patterns with a search-first institutional hero, proof bands, and discovery bands
- Public product navigation is Reports, Topics, Signals, Briefings, and Publishers, with Figures, Regions, Time Periods, and Methodology as secondary discovery/trust surfaces. Signal and Briefing surfaces are product destinations even when the current theme exposes them first through homepage modules or generated publish packages.
- Theme-driven editorial token system in `theme.json` with semantic enterprise-blue tokens mirrored into `assets/css/theme.css` for non-block components
- Sans-first typography roles for display, page titles, section titles, card titles, body copy, metadata, navigation, and buttons are defined centrally in `theme.json` and reinforced in `assets/css/theme.css`
- Homepage chapter anchors are standardized through `.ml-section-anchor`, `.ml-section-eyebrow`, `.ml-section-title`, and `.ml-section-rule`
- Homepage and shared editorial cards opt into a reusable premium surface system via `.ml-surface-card`
- Minimal JS only for singular report interaction parity

Current theme highlights:

- shortcode-driven header/footer navigation resolution
- a search-first homepage hero and dynamic homepage intelligence surfaces
- a semantic enterprise-blue token foundation in `theme.json` plus `assets/css/theme.css` (`text-primary`, `text-secondary`, `text-muted`, `brand-navy`, `signal-blue`, `support-blue`, `surface-white`, `background-cool`, `border-subtle`, `shadow-premium`) while keeping legacy slugs as compatibility aliases
- a sans-first enterprise typography system in `theme.json` and `assets/css/theme.css` covering display/page/section/card/meta/nav/button roles without changing shortcode structure or homepage composition
- a reusable homepage section-anchor system (`.ml-section-anchor`, `.ml-section-eyebrow`, `.ml-section-title`, `.ml-section-rule`) so editorial chapters read as distinct premium intelligence surfaces without changing inner module grids
- a centralized premium surface-card system in `assets/css/theme.css` (`.ml-surface-card`, standard/compact padding, 12px radius, semantic border/shadow states, and 24px card gaps) applied to featured, report, signals, themes, authority, and method cards without changing shortcode logic or grid templates
- a two-column homepage hero in `patterns/hero-institutional.php` with native search as the primary above-the-fold action, compact `[ml_home_metrics]`, and a right-side intelligence panel powered by the existing hero snapshot shortcode without changing shortcode/query behavior
- a signal-list treatment for `This Week in Intelligence` so topic rows use premium intelligence cues (`.ml-signals-column`, `.ml-signal-row`, `.ml-signal-indicator`) instead of generic badge/bar styling while preserving topic order, counts, and shortcode queries
- a premium strategic-theme discovery treatment so taxonomy cards use lighter surfaces, stronger title/count hierarchy, and directional affordance cues without changing topic ordering or taxonomy shortcode queries
- a publisher-authority presentation upgrade so institutional source cards use a vertically stacked name/meta hierarchy, lighter premium surfaces, and internal profile-link pills without changing publisher ordering, counts, or shortcode queries
- a homepage `Signal of the moment` card that rotates a full-text report key-data insight with direct report attribution
- shortcode-driven premium homepage latest-report cards with a fixed archive information stack (date, period, title, publisher, metrics, excerpt, CTA), consistent 4:3 covers, a longer archive-specific excerpt source, an 8-line reserved TLDR area, and inline digest CTAs instead of the older Query-block grid
- a flagship Featured Digest module with a two-column editorial cover/content layout, a top-right fixed badge column for insights/quotes/topics aligned to the publish/publisher/period rows, a stronger 30px title, a compact 3-line summary, limited topic display, and labeled insight bullets sourced from existing report data without changing featured-report selection logic
- a more procedural `How It Works` methodology band with numbered step markers, stronger step-title/support hierarchy, equal-height premium cards, and an icon-free institutional presentation without changing the underlying copy or structure
- a restrained motif/micro-interaction layer in `assets/css/theme.css` that uses explicit shared hooks (`.ml-card`, `.ml-chip`, `.ml-link-arrow`, `.ml-button`), a tiny node-ended section rule, hero/briefing-band node motifs, calmer shared card hover states, quieter editorial link arrow movement, and consistent reduced-motion handling without changing module structure
- refined header/footer shell polish in `assets/css/theme.css` so the two-row header now reads as one integrated premium surface with a stronger brand lockup, calmer nav/current-state treatment, a more attached archive-search row, polished CTA states, and aligned footer navigation/copy without changing IA or template hierarchy
- a final responsive premium pass in `assets/css/theme.css` at `1100px` and `782px` so the header shell, hero, featured digest, signals, themes, publishers, reports grid, methodology cards, briefing band, and footer preserve hierarchy and readable spacing on tablet/mobile without changing module order or data flow
- `assets/js/reveal.js` now uses a lower IntersectionObserver threshold on compact viewports so tall homepage sections like Latest Reports still reveal correctly on mobile instead of remaining hidden
- a final finish-quality consistency pass in `assets/css/theme.css` that consolidates shared card/button/chip values, restores the missing signals-card hover treatment, aligns editorial link/focus behavior, refreshes the briefing-band/footer control surfaces, and fixes header-search shell alignment without changing query or template logic
- a richer `[ml_report_browser]` archive/search/category/publisher experience
- imported publisher profile support from Notion (`[ml_publisher_profile]`, publisher insights/homepage/icon term metadata, and `Wordpress/config/publisher-profiles.json`)
- redesigned trust and conversion pages (`About`, `Methodology`, `Contact`, `Submit a Report`)
- a native PowerShell plugin packaging script at `Wordpress/scripts/build-plugin-zip.ps1` so Windows builds do not depend on `bash.exe`/WSL
- automatic backfill of legacy report publisher/meta projections during plugin upgrade/runtime so homepage authority surfaces recover without manual post edits

### Provision Site IA

After plugin/theme activation, provision the editorial IA:

```bash
bash Wordpress/scripts/provision-site-structure.sh
bash Wordpress/scripts/seed-publisher-homepages.sh
bash Wordpress/scripts/sync-publisher-profiles.sh
```

What `provision-site-structure.sh` does:

- Creates/updates required pages (About, Methodology, Topics directory, Signals, Briefings, Publishers directory, Submit a Report, Contact, Privacy, Terms)
- Publishes pages idempotently
- Uses static block-theme template parts for navigation; it does not create classic menu locations
- Falls back to REST when `wp-cli` is unavailable
- Auto-discovers both `/wp-json/` and `?rest_route=/` style REST roots

What `seed-publisher-homepages.sh` does:

- Reads `Wordpress/config/publisher-homepages.json`
- Ensures current publisher terms exist in `ml_publisher`
- Upserts `ml_publisher_homepage` term meta
- Is idempotent and safe to rerun
- Falls back to REST when `wp-cli` cannot access a local WP core
- Auto-activates `marketlense-core` in REST mode when needed

What `sync-publisher-profiles.sh` does:

- Reads `Wordpress/config/publisher-profiles.json`
- Ensures current publisher terms exist in `ml_publisher`
- Upserts the full publisher profile contract onto each term
- Uses REST so large icon/data URI payloads and long descriptions sync safely
- Inlines remote publisher icons to `data:image/...` payloads when possible
- Is idempotent and safe to rerun after refreshing the Notion-derived JSON snapshot

`publisher-profiles.json` is generated from the Notion `REPORT SOURCES` snapshot and captures icon source, publisher name, homepage link, self-presentation text, and insights/report link per publisher.

When the provisioning scripts fall back to REST, they auto-discover both `/wp-json/` and `?rest_route=/` API roots and honor `WP_SSL_VERIFY` / `WP_CA_BUNDLE_PATH` for hosted sites with custom TLS.

### Local Windows Workflow

If your local WordPress runtime cannot safely follow theme symlinks, keep the local theme/plugin as real directories and sync from the repo instead of linking.

For the local WordPress instance at `C:\Users\Михаил\Studio\marker-lense`, do not symlink the block theme into the local site. Some local stacks resolve theme symlinks through `/internal/symlinks/...`, which breaks `theme.json` loading in the web runtime.

One-shot sync:

```powershell
powershell -ExecutionPolicy Bypass -File .\Wordpress\scripts\sync-local-wordpress.ps1 `
  -LocalWpPath 'C:\Users\Михаил\Studio\marker-lense'
```

Watch mode:

```powershell
powershell -ExecutionPolicy Bypass -File .\Wordpress\scripts\sync-local-wordpress.ps1 `
  -LocalWpPath 'C:\Users\Михаил\Studio\marker-lense' `
  -Watch
```

Notes:

- The script mirrors repo changes into the local theme/plugin directories with `robocopy /MIR`
- `-SyncTarget theme` or `-SyncTarget plugin` limits sync to one side
- The local target directories must be real directories, not symlinks/junctions
- This avoids block-theme `theme.json` failures caused by local stacks that resolve symlinks through `/internal/symlinks/...`

### Build ZIPs For WP Admin Upload

From repo root:

```bash
bash Wordpress/scripts/build-plugin-zip.sh
bash Wordpress/scripts/build-theme-zip.sh
```

From PowerShell on Windows, you can build the plugin archive without `bash.exe` / WSL:

```powershell
powershell -ExecutionPolicy Bypass -File .\Wordpress\scripts\build-plugin-zip.ps1
```

Build scripts use `zip` when available and automatically fall back to Python (`python` / `python3` / `py`) or local virtualenv interpreters when `zip` is not installed.

On Windows in this workspace, repo-local helper shims are also available under `tools/`: `php`, `composer`, and `wp` point to `tools/php82/php.exe` plus the user-space PHAR installs in `%USERPROFILE%\.local\bin`.

Outputs:

```text
Wordpress/dist/marketlense-core.zip
Wordpress/dist/marketlense.zip
```

Install order in WordPress Admin:

1. `Plugins -> Add New -> Upload Plugin` -> upload `marketlense-core.zip` -> activate.
2. `Appearance -> Themes -> Add New -> Upload Theme` -> upload `marketlense.zip` -> activate.
3. Run IA/data provisioning from this repo:
   `bash Wordpress/scripts/provision-site-structure.sh`
   `bash Wordpress/scripts/seed-publisher-homepages.sh`
   `bash Wordpress/scripts/sync-publisher-profiles.sh`

### Smoke Test

If `wp-cli` is available:

```bash
bash Wordpress/scripts/smoke-test.sh
```

What it validates:

- Plugin `marketlense-core` is installed and can activate
- Theme `marketlense` is installed and can activate
- Required theme templates exist
- REST endpoints resolve for `ml_report` and `ml_publisher`
- Front page, report archive, report filter URLs, and required site pages return HTTP `200`
- Topics and publishers directory shortcodes render
- Primary navigation links for Reports, Topics, Signals, Briefings, and Publishers are present in rendered output
- Front page editorial sections render
- A published `ml_report` URL returns HTTP `200` (seeded if missing)

Optional environment controls:

- `WP_CLI_BIN` (default `wp`)
- `WP_PATH`
- `WP_CLI_FLAGS`
- `PROVISION_STRUCTURE`
- `SEED_PUBLISHERS`
- `WP_SITE_URL`
- `WP_USERNAME`
- `WP_APP_PASSWORD` or `WP_BEARER_TOKEN`
- `WP_SSL_VERIFY`
- `WP_CA_BUNDLE_PATH`

If `wp-cli` is unavailable, smoke test exits with a skip message.

### Automated Verification

The repo includes a minimal WordPress verification harness for CI and local use:

```bash
python scripts/ci/check_wordpress_subproject.py
```

What it validates:

- no hardcoded root-relative internal links remain in theme `parts/`, `patterns/`, or `templates/`
- no public `taxonomy-ml_topic.html` template is shipped
- PHP syntax for theme/plugin PHP files
- shell syntax for `Wordpress/scripts/*.sh`
- optional live smoke test only when `RUN_WORDPRESS_SMOKE=1` and `wp-cli` is available

The main CI workflow runs this harness automatically after installing PHP CLI.

### Archive and Directory UX

- `templates/archive-ml_report.html`, `templates/archive.html`, `templates/category.html`, `templates/taxonomy-ml_publisher.html`, and `templates/search.html` route through the richer shortcode-based report browser instead of plain `core/query` grids
- `templates/archive.html` intentionally mirrors the reports archive browser as a hierarchy fallback because the widened archive can fall back from the CPT-specific block template to the generic archive template in WordPress
- `templates/taxonomy-ml_publisher.html` renders `[ml_publisher_profile]` above the archive browser so each publisher term page can expose the imported icon, homepage CTA, and insights CTA
- Publisher archive/profile icon rendering falls back to a monogram when a remote image source fails
- `[ml_report_browser]` owns filtering, sort order, result summaries, active-filter chips, and the responsive archive layout for archive/search/topic/publisher views
- Older `?ml_topic=<slug>` links remain accepted and still map onto native categories
- Homepage editorial sections remain shortcode-driven intelligence components
- `marketlense-core` applies its registered `ml_*` shortcodes during block rendering when template/pattern output leaves a raw shortcode unresolved
- On activation and on the first runtime after upgrade, `marketlense-core` backfills missing report metadata and publisher taxonomy projections for existing `ml_report` posts and digest-style core `post` entries
- `templates/page-topics-directory.html` renders `[ml_topics_directory]`
- `templates/page-publishers-directory.html` renders `[ml_publishers_directory]` with publisher homepage CTAs, trimmed self-presentation copy, and optional insights links
- The publishers directory is term-driven, so synced publishers remain visible even before they have published reports attached
- In WP Admin, publisher management uses a dedicated `Market Lense Reports -> Publishers` screen instead of native taxonomy `edit-tags.php`
- `templates/category.html` routes native category archives through the same report browser, so topic archive pages stay limited to uploaded reports
- No dedicated `taxonomy-ml_topic.html` template is shipped; topic browsing is category-first
- Digest content can now live in either `ml_report` or core `post`; front-end report surfaces scope to entries carrying the recovered digest contract

### Responsive Layout Defaults

The `marketlense` theme uses an explicit reading frame and a wider discovery frame in `theme.json`:

- `settings.layout.contentSize`: `48rem`
- `settings.layout.wideSize`: `82rem`

The homepage hero uses a two-column search-first composition, native WordPress search is the primary action, `[ml_home_metrics]` and `[ml_hero_snapshot]` render above the first proof band, homepage sections are grouped into proof and discovery bands, and the header/footer use the same home frame width as the hero and homepage section bands.

### `ml_report` Ingest Rendering

Published ingest reports render in an ingest-first mode in the single template:

- `parts/single-content.html` is the single source of truth for singular report content rendering
- `templates/single-ml_report.html` and `templates/single.html` both route through that shared template part
- `assets/css/theme.css` contains a scoped parity layer under `.ml-ingest-report-content`
- `assets/js/report-interactions.js` covers stripped interactive behavior and is enqueued only for `ml_report` and legacy default `post` singular views
- Reveal panels are fail-open
- Publish HTML source rewriting swaps digest image URLs to same-origin frontend media proxy paths and strips `srcset` / `sizes` from those proxy-backed images so hosted frontend rendering stays deterministic
- Legacy frontend JS removes broken `srcset` when older posts contain mixed absolute/relative image attributes

This keeps the WordPress article view aligned with the latest ingest-generated HTML report styling and behavior after upload.

### Pipeline Integration

Publishing remains controlled by Python orchestration in `src/`:

```powershell
python -m src.cli publish-wp
python -m src.cli update-wp-categories
```

WordPress credentials and publish controls come from root `.env` / `app.yaml`:

- `WP_SITE_URL`
- `WP_USERNAME`
- `WP_APP_PASSWORD` or `WP_BEARER_TOKEN`
- `WP_POST_STATUS`
- `WP_POST_TYPE`
- `WP_SSL_VERIFY`
- `WP_CA_BUNDLE_PATH`

This repo currently publishes into core WordPress posts with `publish.wp.post_type=posts`. The bundled WordPress plugin treats digest posts with a recovered digest contract (`ml_is_digest=1` and, when available, `ml_file_id`) as first-class report content across archive/home surfaces, so report cards and intelligence modules still work even when the underlying post type is `post`.

The checked-in `publish.wp.site_url` value targets `https://marketlense.medianewsonline.com` so publish flows and follow-on tooling stop reinforcing the legacy `http` scheme.

If root config disables WordPress TLS verification (`publish.wp.ssl_verify: false`), the Python publish service suppresses `urllib3` insecure-request warnings for those calls, but the HTTPS connection remains untrusted until the host certificate chain is fixed. `WP_SSL_VERIFY` and `WP_CA_BUNDLE_PATH` override the checked-in publish TLS settings for the Python publish path, and the WordPress shell/Python provisioning scripts honor the same variables so hosted admin/provisioning runs can match publish flows.

When the hosting layer blocks direct `/wp-content/uploads/...` access, the plugin serves attachments through a frontend proxy route (`/?ml_media=<attachment_id>`) and rewrites frontend digest content/thumbnail URLs to that proxy so uploaded media still renders publicly.

The Python publisher appends a hidden `Drive fileId: ...` marker to post content when the rendered HTML lacks one so plugin backfill and REST lookup remain deterministic for digest posts created under the core `post` type.

During publish, the pipeline writes native category IDs for report topics and `ml_publisher` term IDs for report publishers through the WordPress REST API so archive filters and directory pages stay aligned with uploaded reports.

### Maintenance Rule

Any WordPress change in this subproject must update this root README WordPress section.

## Configuration (YAML + .env)

Primary config: `src/config/app.yaml`. It now contains environment-neutral repo defaults only and is the canonical source of truth for default non-secret settings. Missing values can be provided via `.env` (loaded by `config_service`) or a local/profile YAML overlay. Secrets must come from environment variables.

Bootstrap / override order:

- `src/config/app.yaml`: committed neutral defaults.
- `MARKET_LENSE_CONFIG_PATH=/abs/or/relative/app.yaml`: replace the base config file entirely.
- `MARKET_LENSE_CONFIG_PROFILE=<name>`: if the selected base file is named `app.yaml`, load sibling overlay `app.<name>.yaml` on top of it.
- `app.local.yaml`: if present next to the selected `app.yaml`, load it last as the highest-precedence local overlay.
- `src/config/app.example.yaml`: starter overlay showing the environment-specific keys that should move out of committed defaults.

For dev wiring, use `src.services.config_service.build_ingest_settings` with `IngestSettingsBuildRequest` to adapt `AppSettings` into `IngestSettings` without hand-copying fields; new config keys are picked up automatically.
`src/services/config_service.py` now resolves ingest settings through section resolvers plus reusable field specs, so env fallback, coercion, defaults, and minimum-value behavior are localized to the relevant config section instead of one long inline parsing chain.
Capability-specific loaders such as browser-download, publisher-inventory discovery, and WordPress publish settings use the same `MARKET_LENSE_CONFIG_PATH` bootstrap resolution as the main app settings loader, so isolated task runs and alternate config files do not fall back to `src/config/app.yaml`.
Config editing is also split by concern behind the same canonical boundary: `src/services/config_service.py` remains the public service for `app.yaml` reads/writes and browser-download identity upserts, while `src/services/_config_service/app_document.py` owns app-document editor I/O, `src/services/_config_service/identity.py` owns browser identity normalization plus upsert planning, and `src/services/_config_service/yaml_mapping.py` owns config-specific YAML parsing/merge helpers. The settings UI still calls the canonical service boundary, and structured asset editing remains on `src/services/config_asset_service.py`.
The same facade-plus-family pattern now also applies to several other large boundaries: `src/services/report_store_service.py`, `src/services/state_service.py`, `src/services/publisher_inventory_service.py`, `src/orchestrators/report_download_orchestrator.py`, and `src/orchestrators/publisher_inventory_orchestrator.py` remain the discoverable public files. Their split implementation families live under same-name internal subfolders such as `src/services/_report_store_service/`, `src/services/_state_service/`, `src/services/_publisher_inventory_service/`, `src/orchestrators/_report_download_orchestrator/`, and `src/orchestrators/_publisher_inventory_orchestrator/`. For report-store specifically, the canonical facade now delegates semantic families for metadata, publishers, sources, download routes, and inventory state/run-quality handling while connection, serialization, and route-policy helpers stay private to that one service boundary; schema creation and upgrades are owned by `src/services/sqlite_migration_service.py`.

Key fields and env overrides:

- Paths: `paths.output_dir` (`OUTPUT_DIR`, default `./out`), `paths.cache_dir` (`CACHE_DIR`, default `./cache`), `paths.state_db` (`STATE_DB`), `paths.reports_db` (`REPORTS_DB`), `paths.category_mappings` (defaults to `src/config/category-mappings.yaml`; supports context-first category profiles via `definition`, `include_when`, and `exclude_when`, plus retained taxonomy-signal groups such as `core_tags`, `supporting_tags`, `descriptor_tags`, `generic_tags`, and `negative_tags`), `paths.html_tag_acronyms` (defaults to `src/config/html-tag-acronyms.yaml`).
- Ingest: `ingest.google_sa_path` (`GOOGLE_SERVICE_ACCOUNT_JSON`), `ingest.gdrive_folder_id` (`GDRIVE_FOLDER_ID`), `ingest.openai_model` (`OPENAI_MODEL`), `ingest.batch_limit` (`BATCH_LIMIT`, default 20), `ingest.worker_limit` (`INGEST_WORKER_LIMIT`, default 2), `ingest.report_worker_limit` (`INGEST_REPORT_WORKER_LIMIT`, default 2), `ingest.temperature` (`TEMPERATURE`, default 1.0), `ingest.timeout_seconds` (`OPENAI_TIMEOUT_SECONDS`, default 600), `ingest.lock_ttl_seconds` (`INGEST_LOCK_TTL_SECONDS`, default 7200), `ingest.contents_page.*` (keywords, max_pages, min_headings, render_dpi, preview_enabled), `ingest.evidence_packs.parallel_workers` (`EVIDENCE_PACK_PARALLEL_WORKERS`, default 3), `ingest.evidence_packs.global_max_in_flight` (`EVIDENCE_PACK_GLOBAL_MAX_IN_FLIGHT`, default 2), `ingest.evidence_packs.global_min_interval_ms` (`EVIDENCE_PACK_GLOBAL_MIN_INTERVAL_MS`, default 250), `ingest.evidence_packs.doc_map_max_attempts` (`EVIDENCE_PACK_DOC_MAP_MAX_ATTEMPTS`, default 3), `ingest.evidence_packs.doc_map_retry_delay_ms` (`EVIDENCE_PACK_DOC_MAP_RETRY_DELAY_MS`, default 500), `ingest.evidence_packs.registry` (`EVIDENCE_PACK_REGISTRY`, comma-separated), `ingest.evidence_packs.enable_new_variety_packs` (`EVIDENCE_PACK_ENABLE_NEW_VARIETY_PACKS`, default `false`), `ingest.artifacts.parallel_workers` (`ARTIFACT_PARALLEL_WORKERS`, default 4), `ingest.artifacts.global_max_in_flight` (`ARTIFACT_GLOBAL_MAX_IN_FLIGHT`, default 2), `ingest.artifacts.global_min_interval_ms` (`ARTIFACT_GLOBAL_MIN_INTERVAL_MS`, default 250), `ingest.validation.regeneration_max_attempts` (`VALIDATION_REGENERATION_MAX_ATTEMPTS`, default `3`, minimum `1`).
- Shared LLM policy: `ingest.llm.retries` (default `1`), `ingest.llm.base_delay_seconds` (default `1.0`), `ingest.llm.backoff_step_seconds` (default `1.0`), `ingest.llm.jitter_seconds` (default `0.25`), `ingest.llm.circuit_breaker_failure_threshold` (default `3`), and `ingest.llm.circuit_breaker_recovery_seconds` (default `30.0`) control the shared `llm_service` wrapper used for model calls.
- PDF OCR fallback: `ingest.pdf_text.ocr_fallback.enabled`, `ingest.pdf_text.ocr_fallback.policy` (`native_first_selective` or `always`), `ingest.pdf_text.ocr_fallback.model` (default `gpt-5-mini`), `ingest.pdf_text.ocr_fallback.timeout_seconds`, `ingest.pdf_text.ocr_fallback.prompt_namespace`, `ingest.pdf_text.ocr_fallback.cache_enabled`, `ingest.pdf_text.ocr_fallback.chunk_page_count` (default `8`). OCR calls go through `src/services/openai_service.py` using the OpenAI Responses API and only run when the native confidence/density gate fails or policy explicitly forces OCR.
- Figure captions: `ingest.figure_captions.enabled`, `ingest.figure_captions.temperature`, `ingest.figure_captions.timeout_seconds`, `ingest.figure_captions.prompt_namespace` (default `report_vs/figure_caption`), `ingest.figure_captions.max_chars` (default `500`). The bundled `src/config/app.yaml` keeps this phase disabled unless you opt in via config/env override. Model resolution follows `openai_models.report_vs/figure_caption` first, then falls back to `ingest.openai_model`. The phase is fail-open: primary figures fall back to the legacy shared caption, secondary figures fall back to detected captions or the existing placeholder label.
- Browser downloads: `OPENROUTER_API_KEY` is required, `OPENROUTER_HTTP_REFERER` is optional, `browser_download.model` (`BROWSER_DOWNLOAD_MODEL`, default comes from `src/config/app.yaml`), `browser_download.identity_config_path` (`BROWSER_DOWNLOAD_IDENTITY_CONFIG_PATH`, default `src/config/browser_download_identity.yaml` relative to `app.yaml`), `browser_download.temperature` (`BROWSER_DOWNLOAD_TEMPERATURE`, default `0.0`), `browser_download.timeout_seconds` (`BROWSER_DOWNLOAD_TIMEOUT_SECONDS`, default `180`), `browser_download.max_steps` (`BROWSER_DOWNLOAD_MAX_STEPS`, default `30`), `browser_download.output_dir` (`BROWSER_DOWNLOAD_OUTPUT_DIR`, default `./out/browser_downloads`), `browser_download.headed` (`BROWSER_DOWNLOAD_HEADED`, default `false`), `browser_download.drive_upload.enabled` (`BROWSER_DOWNLOAD_DRIVE_UPLOAD_ENABLED`, default `true`), `browser_download.drive_upload.required` (`BROWSER_DOWNLOAD_DRIVE_UPLOAD_REQUIRED`, default `true`), `browser_download.drive_upload.parent_folder_id` (`BROWSER_DOWNLOAD_DRIVE_UPLOAD_PARENT_FOLDER_ID`, falling back to `ingest.gdrive_folder_id` / `GDRIVE_FOLDER_ID`), `browser_download.failure_forensics.enabled` (`BROWSER_DOWNLOAD_FAILURE_FORENSICS_ENABLED`, default `true`), `browser_download.failure_forensics.policy` (`BROWSER_DOWNLOAD_FAILURE_FORENSICS_POLICY`, `copy_artifacts` or `metadata_only`), and `browser_download.retry.*` (`BROWSER_DOWNLOAD_RETRIES`, `BROWSER_DOWNLOAD_BASE_DELAY_SECONDS`, `BROWSER_DOWNLOAD_BACKOFF_STEP_SECONDS`, `BROWSER_DOWNLOAD_JITTER_SECONDS`). The browser-download flow uses the shared `paths.state_db` to persist one remembered route summary per normalized URL, appends newly seen form labels into the identity YAML for later manual completion, preflights required Google Drive archival before expensive acquisition, uploads successful local terminal artifacts to the resolved publisher `google_folder` when Drive archival is enabled, creates and records a publisher-named folder when the publisher row has no folder, and persists failed-attempt forensic packs beside the per-URL download directory when failure forensics are enabled.
- Browser-download session reuse: `browser_download.session_reuse.enabled` (`BROWSER_SESSION_REUSE_ENABLED`, default `false`), `mode` (`BROWSER_SESSION_REUSE_MODE`, `developer_canary` or `same_publisher_batch`), `session_key` (`BROWSER_SESSION_REUSE_KEY`), `publisher_scope` (`BROWSER_SESSION_REUSE_PUBLISHER_SCOPE`), `ttl_seconds` (`BROWSER_SESSION_REUSE_TTL_SECONDS`), `base_dir` (`BROWSER_SESSION_REUSE_BASE_DIR`), `cleanup_expired` (`BROWSER_SESSION_REUSE_CLEANUP_EXPIRED`, default `true`), and `allow_cross_publisher` (`BROWSER_SESSION_REUSE_ALLOW_CROSS_PUBLISHER`, default `false`) control bounded reusable browser profiles for developer canaries and same-publisher batches.
- Browser downloads also write into `paths.reports_db` table `report_sources`. Discovery inserts one Source row per new diff item with `source_status='discovered'`, publisher/source-page provenance, and `discovered_on_page_number`; a later successful local PDF download upgrades the same normalized-URL row in place to `source_status='downloaded'`, filling `downloaded_at_utc` and the downloaded file `md5`. Successful downloads now receive a typed deterministic report-value score over five dimensions (`market_insight_depth`, `evidence_specificity`, `decision_relevance`, `recency_timeliness`, `source_authority_originality`), with `report_value_score`, `report_value_band`, `report_value_score_json`, and `report_value_scored_at_utc` persisted back to the same Source row for later publisher-resource ranking. A Source remains an acquisition candidate until the downstream report pipeline produces a validated Report artifact.
- Publisher resource quality ranking: `publisher_discovery.resource_quality_ranking.*` controls whether qualified discovery candidates are reordered by rolling report-value consistency before new `report_sources` rows are queued. The policy logs score window, sample size, confidence, rank score, and demotion reason per resource; defaults are enabled with a 5-report window, minimum sample size of 2, weights of `0.35` consistency / `0.50` average score / `0.15` confidence, and low-average demotion below `45.0`.
- Publisher snapshots sourced from the Notion `REPORT SOURCES` page can be synced into `paths.reports_db` table `publishers` via `python -m src.cli sync-publishers`. The sync reads `paths.publisher_profiles` (default `Wordpress/config/publisher-profiles.json`) and replaces the current `publishers` table contents with validated snapshot rows storing `name`, `homepage`, `self_presentation`, and `insights_url`, while preserving any previously curated `google_folder` links and remembered browser-download route fields by `insights_url` and fallback publisher-name matching.
- Publish: WordPress publish settings and TLS notes are documented together in the `WordPress Subproject` section below (`publish.wp.*`, `publish.media_upload_workers`, `WP_*`, `PUBLISH_MEDIA_UPLOAD_WORKERS`, and `publish.validation.policy`).
- Ranking/crop refinement: `rank.max_candidates`, `rank.selected_max` (default `5`), `rank.min_overall_score`, `rank.min_quality_score`, `rank.min_insight_score`, `rank.min_data_score`, `rank.crop_refine_enabled`, `rank.crop_refine_mode` (`adaptive|always|off`), `rank.crop_refine_page_dpi`, `rank.crop_refine_temperature`, `rank.crop_refine_timeout_seconds` (defaults to `rank.timeout_seconds` when omitted).
- Drive listing: `ingest.drive.supports_all_drives`, `ingest.drive.include_items_from_all_drives` (shared drive flags), `ingest.drive.drive_id` (shared drive scope), and `ingest.drive.list_mode` (`full` vs `metadata` to omit names until needed).
- PDF text extraction: `ingest.pdf_text.max_pages` and `ingest.pdf_text.max_chars` cap how much text is sampled per PDF; `ingest.pdf_text.min_density` (default `250` chars/page) feeds both downstream "not available from text" handling and the OCR confidence gate; `ingest.pdf_text.sample_pages` (default `3`) controls the deterministic sample used to validate extractability before analysis; `ingest.pdf_text.native_confidence_threshold` and `ingest.pdf_text.native_page_confidence_threshold` tune the aggregated and per-page native-text confidence gate.
- Model overrides: `openai_models` maps prompt namespaces (or prefixes) to model IDs. Longest-prefix match wins. Falls back to `ingest.openai_model` for most prompts and to `rank.model` for `rank_candidates` unless an override is provided.
- HTML rendering labels: `paths.html_tag_acronyms` points to a YAML file that defines `html_tag_acronyms` tokens preserved in uppercase when slug labels are humanized.

Per-step model selection (new):

- Set `openai_models` entries to pin specific prompt calls to specific models (e.g., `report_vs/artifacts/summary`, `report_vs/evidence_packs/findings`, `report_vs/validate/grounding`, `rank_candidates`, `rank_candidates/crop_refine`).
- Prefix keys apply to all nested namespaces unless a more specific key exists (e.g., `report_vs/evidence_packs` covers all evidence packs).
- Vector store: `analysis.vector_store_keep` (`VECTOR_STORE_KEEP`, default `true`) controls whether to retain caches between runs (including evidence pack reuse). `analysis.vector_store_retention_days` (`VECTOR_STORE_RETENTION_DAYS`, default `30`) prunes kept vector stores after that many days; set it to `0` to disable expiry cleanup. Analysis uses the vector_store path only. Evidence/validation JSONs are written only to `out/<report-slug>/report_analysis/`.
- Artifact retrieval mode: `analysis.artifacts_use_vector_store` (`ARTIFACTS_USE_VECTOR_STORE`, default `false`) controls whether artifact model calls use vector-store retrieval. Default is closed-context JSON chat; set to `true` to restore legacy vector retrieval behavior.
- Validation grounding retrieval mode: `analysis.validation_grounding_use_vector_store` (`VALIDATION_GROUNDING_USE_VECTOR_STORE`, default `false`) controls whether grounding checks use vector-store retrieval. Default is closed-context JSON chat; set to `true` to restore legacy vector retrieval behavior.
- Strict schema validation: `analysis.strict_schema_validation` (`STRICT_SCHEMA_VALIDATION`, default `true`) enables hard-fail schema enforcement for evidence/docpack payloads.
- Cost tracking: `analysis.cost_ledger_path` (`COST_LEDGER_PATH`, default `./out/cost-ledger.jsonl`), `cost.daily_path` (default `./out/cost-daily.json`), and `cost.pricing_path` (default `./src/config/llm-costs.yaml`). Per-model LLM pricing now lives in `src/config/llm-costs.yaml` and is used by `utils.costing`.
- Cross-report analysis: `cross_report_analysis.enabled` (default `false`), `max_source_reports` (default `6`), `max_evidence_items` (default `48`), `max_prompt_chars` (default `60000`), `prompt_namespace` (default `cross_report_analysis/synthesis`), `model` (default `gpt-5-mini`), `temperature` (default `1.0`), `timeout_seconds` (default `600`), `cache_enabled` (default `true`), `auto_theme_enabled` (default `true`), `theme_rotation_window_days` (default `30`), `min_theme_source_publishers` (default `2`), `publish_enabled` (default `false`), and `publish_requires_validation_pass` (default `true`). The config loader rejects invalid non-positive generation limits with non-retryable `AppError(code="cross_report_analysis_config_invalid")` instead of clamping them. These limits are cost controls and operator gates: disabled generation stops before projected-data reads, disabled auto-theme requires an explicit topic with automatic selection off, source/evidence/prompt caps are enforced before synthesis spends model tokens, orchestration idempotency allows unchanged runs to reuse generated artifacts without another model call, and live publication remains disabled unless explicitly enabled. `generate-cross-report-analysis` provides request-scoped overrides for topic, auto-theme, filters, date range, max report count, publish mode, idempotency database, and output root, while YAML remains the durable default and upper-bound control surface.
- Validation: `ingest.validation.data_gap_policy` (default `warn`) controls whether missing evidence/text gaps downgrade errors to warnings; `ingest.validation.regeneration_max_attempts` bounds post-validation regeneration passes and does not count the initial generation/validation pass; `publish.validation.policy` (`PUBLISH_VALIDATION_POLICY`, default `block`; set to `warn` to allow publish with issues).
- Taxonomy extraction: set `openai_models.report_vs/taxonomy` to override the tag/region/time period extractor and `ingest.taxonomy_temperature` (or `TAXONOMY_TEMPERATURE`) to control taxonomy-only sampling. The bundled prompt now returns structured central/secondary tags with evidence, biases away from adjacent platform/channel/tactic tags unless they define the whole report, and applies YAML-driven post-processing inference rules for evidence-backed tag bridges.
- Context-first category assignment: `src/generators/report_context_generator.py` deterministically compacts stored evidence packs (`doc_map`, `scope`, `methods`, `findings`, `limitations`) into a typed `ReportCategoryContext`, and `src/generators/context_category_fit_generator.py` runs a single batched model decision over category `id` / `label` / `description` / `definition` / `include_when` / `exclude_when` profiles from `src/config/category-mappings.yaml`. This is the production portal-category path; taxonomy tags remain metadata only.
- Cover images: `paths.cover_styles` points to `src/config/cover-styles.yaml` (defaults to that path). Fonts are local files; the default config uses `templates/GOTHICB.TTF` for both regular/bold. Ensure the font file exists on the host; otherwise cover rendering will fail with `cover_font_invalid`. Background image is optional; leave blank for a solid background.

Secrets (env only):

- `OPENAI_API_KEY` (required)
- `OPENROUTER_API_KEY` (required for `download-report` / browser-download automation)
- `OPENROUTER_HTTP_REFERER` (optional for OpenRouter tracking)
- `WP_APP_PASSWORD` or `WP_BEARER_TOKEN` (publishing)
- `WP_POST_TYPE` (optional publish endpoint override; bundled config default is `ml_report`)
- Optional provider keys (e.g., `MINERU_API_KEY`) if used.

Prompt locations:

- Vector store evidence packs: `src/prompts/report_vs/**` (`doc_map/`, `evidence_packs/{scope,methods,findings,limitations,quote_candidates,key_metrics,risk_register,recommendations,contradictions}/`)
- Artifact generation: `src/prompts/report_vs/artifacts/**` (toc, summary, insights candidates/final, quotes, expert comment, LinkedIn post)
- Artifact regeneration: `src/prompts/report_vs/artifacts/regenerate/**` (summary, insights_candidates, insights_final, quotes, expert_comment, linkedin_post)
- Taxonomy extraction: `src/prompts/report_vs/taxonomy/`
- Cross-report synthesis: `src/prompts/cross_report_analysis/synthesis/` (configured by `cross_report_analysis.prompt_namespace`)

Prompts are YAML (system/user), hashed and logged by `src/services/prompt_service.py`.

---

## End-to-End Flow (Ingest)

1. **Configuration load**
   - `src/services/config_service.py` loads YAML from `src/config/app.yaml` and ensures required paths exist.
   - Missing values fall back to `.env` (for example Drive folder ID, service account path, and WordPress site/user).
   - Secrets (OpenAI and WordPress tokens) come from `.env`.
   - Produces `AppSettings` contract.

2. **Pipeline orchestration**
   - Entry point: `src/cli.py`.
   - `src/orchestrators/ingest_orchestrator.py` coordinates run-level ingest flow (locks, DB checks, list/fanout, cursor transitions).
   - `src/orchestrators/ingest_file_orchestrator.py` handles per-file execution inside the ingest worker pool.
   - Per-file cache eligibility is logged via `report_cache_prereq` (`md5_present`, `vector_store_keep`, `eligible`), with an explicit event when `vector_store_keep=false` disables analysis-cache reuse.
   - Before doing any work, ingest probes `state_db` and `reports_db` with a lightweight SQLite schema-read access check after applying WAL/busy-timeout settings. If either DB is locked even for that probe, the run exits early with `db_locked` to avoid partial outputs.
   - Per-file processing runs in a bounded worker pool controlled by `ingest.worker_limit` (default `2`).

3. **Drive discovery**
   - `src/services/drive_service.py` lists PDF files in the target Drive folder.
   - Discovery is recursive: PDFs in nested subfolders are included.
   - Produces `DriveFile` contracts.
   - Supports shared-drive scoping (`drive_id` + `corpora=drive`) and configurable `supportsAllDrives`/`includeItemsFromAllDrives`.
   - Metadata-only listing (`ingest.drive.list_mode=metadata`) skips names until a file is actually processed.
   - State skip prefiltering batches Drive metadata checks (`state_service.already_processed_batch`) for files that already include `md5Checksum`, reducing SQLite round trips during listing.
   - If an ingest cursor exists, listings filter on `modifiedTime > last_successful_ingest_utc` for full runs; limited runs ignore the cursor and instead scan newest-first until they find unprocessed PDFs.

4. **Download + integrity check**
   - Cache paths are keyed by `file_id` (not file name) under `cache_dir`.
   - `file_service.file_stat(...)` reads exists/size/mtime (and can hash on demand), while `file_cache_service.resolve_md5_sidecar(...)` owns `.md5.json` sidecar pathing, load/validation, and stat reconciliation so ingest orchestration consumes typed cache answers instead of parsing sidecar JSON directly.
   - Before report generation, if md5 is still missing, ingest computes md5 from the cached PDF and `file_cache_service.write_md5_sidecar(...)` writes or refreshes the sidecar so md5-gated caches remain eligible.
   - Cache hits skip EOF checks; if Drive provides `md5Checksum`, it is compared against cached md5.
   - Drive API clients are cached per thread to keep googleapiclient/httplib2 usage thread-safe when `ingest.worker_limit > 1`.
   - `drive_service.download_pdf_to_path(...)` streams PDF bytes directly to disk while computing md5.
   - `src/services/pdf_service.py` checks for EOF marker using only tail bytes and redownloads once if missing.
   - `src/services/pdf_service.py` remains the stable public facade; its implementation is split across private capability modules under `src/services/_pdf/` (`text`, `contents`, `figures`, `crop`) to keep one PDF service role with lower regression blast radius. PDF figure extraction keeps `src/services/_pdf/figures.py` as a compatibility facade while focused owners under `src/services/_pdf/_figures/` handle page triage, chart/table pruning, candidate collection, and legacy best-figure image selection.

5. **State management**
   - `src/services/state_service.py` maintains a SQLite store of processed file IDs and hashes.
   - If Drive provides `md5Checksum`, already-processed files are skipped before any download or hashing.
   - A separate ingest cursor (`last_successful_ingest_utc`) is recorded on successful runs and used to filter subsequent Drive listings.

6. **Report generation (per file)**
   - `src/orchestrators/report_pipeline_orchestrator.py` controls report-generation retries and delegates the actual report workflow to `src/orchestrators/report_generation_orchestrator.py`.
   - `src/orchestrators/report_generation_orchestrator.py` is the per-report control plane and sequences source, selection, analysis, and render phases:
     - `src/contracts/report_generation.py`: typed handoff contracts (`ReportRuntimeState`, `ReportSourceState`, `ReportSelectionState`, `ReportAnalysisState`).
     - `src/generators/report_source_generator.py`: PDF context bootstrap, md5-backed PDF info/contents/text caches, density/extractability checks, and base payload seeding.
     - `src/generators/report_selection_generator.py`: canonical selection-phase facade; semantic families now live under `src/generators/_report_selection_generator/` for ranking, crop refinement, and figure-gallery fallback selection while the public entrypoint stays discoverable.
     - `src/orchestrators/report_analysis_orchestrator.py`: vector-store lifecycle coordination, taxonomy/category resolution, evidence packs, artifacts, validation, validation-regeneration looping, and analysis snapshot persistence.
     - `src/generators/report_render_generator.py`: preview rendering, metadata DB readback, HTML cache/render, cover generation, and final `IngestOutcome` assembly.
     - Optional within-file parallelism still uses `ingest.report_worker_limit` to overlap PDF info/contents/text extraction, figure vs candidate extraction, and taxonomy vs evidence generation when enabled (default `2`).
     - **PDF info**: `pdf_service.extract_pdf_info` captures page count and sanitized PDF metadata for persistence (cached by md5 under `cache_dir/pdf_cache/`).
     - **PDF context**: `pdf_service.build_pdf_context` opens PyMuPDF and pypdf handles once; downstream services reuse them and fall back to local opens if unavailable.
     - **Contents/index detection**: scans the first pages for a contents/index section, records the page number for DB/runtime routing, and can render an internal preview asset for diagnostics (detection cached by md5 + settings).
     - **Text extraction**: `pdf_service.extract_pdf_text` extracts text from the first N pages (reusing the shared context when present) and computes text density (cached by md5 + extraction settings); low density still feeds explicit “not available from text” placeholders downstream, and now also contributes to the OCR confidence gate.
     - **Text extractability check**: deterministically samples `ingest.pdf_text.sample_pages` pages (seeded by file id + hash) via `pdf_service.sample_pdf_text`, computes per-page/document native confidence scores, and recommends OCR when the sampled native text is blank or too weak to trust. Hard no-text cases still raise `pdf_text_unextractable` before vector-store or broader LLM work.
     - **LLM analysis**:
       - `vector_store` mode (only path): Ensures a vector store exists (create -> upload PDF -> attach) and starts provider-side indexing first.
       - While indexing runs, the generator continues PDF-only work (figure/candidate extraction and preview rendering).
       - It waits for indexing only right before vector-dependent stages (taxonomy/evidence/artifacts), but the polling/backoff now lives in `src/orchestrators/report_analysis_orchestrator.py` using the shared retry policy while `vector_store_service.get_vector_store_status(...)` stays a single status-fetch boundary.
       - After indexing is ready, taxonomy/category resolution and evidence-pack generation run concurrently when `ingest.report_worker_limit > 1` (serial when `= 1`).
      - Evidence packs are generated via `src/generators/evidence_pack_generator.py`, which now stays as the orchestration entrypoint while per-pack normalization/metadata live under `src/generators/evidence_packs/*.py`. The config-driven registry (`ingest.evidence_packs.registry`) and optional variety expansion (`ingest.evidence_packs.enable_new_variety_packs`) cover `doc_map`, `scope`, `methods`, `findings`, `limitations`, `quote_candidates`, and optional `key_metrics`, `risk_register`, `recommendations`, `contradictions`. The generator now schedules work directly from `EvidencePackStrategy` objects, `doc_map` runs first as a hard gate, and remaining packs run in parallel (`ingest.evidence_packs.parallel_workers`). Global evidence-pack rate limiting is applied at the orchestrator boundary (`src/orchestrators/report_pipeline_orchestrator.py`) using `ingest.evidence_packs.global_max_in_flight` + `ingest.evidence_packs.global_min_interval_ms`.
      - Artifacts are generated via the canonical `src/generators/artifact_generator.py` facade over `src/generators/_artifact_generator/*`, using a dependency-aware parallel DAG: `toc` + `summary` + `insights_candidates` + `quotes` in parallel, then `insights_final`, then `expert_comment` + `linkedin_post` in parallel. Independent steps use `ingest.artifacts.parallel_workers`. Global artifact rate limiting is applied at the orchestrator boundary (`src/orchestrators/report_pipeline_orchestrator.py`) using `ingest.artifacts.global_max_in_flight` + `ingest.artifacts.global_min_interval_ms`. By default these artifact model calls run closed-context (`chat_json`); vector retrieval is opt-in via `analysis.artifacts_use_vector_store`.
      - Targeted regeneration is handled by `src/generators/report_regeneration_generator.py`, which performs exactly one regeneration pass against mapped failing artifact families and reuses the same artifact normalization, schema validation, evidence-reference validation, and storage behavior as the main artifact generator.
      - Regeneration target dispatch inside `report_regeneration_generator.py` is registry-driven by `target_section`, so each supported section keeps prompt namespace selection, variable assembly, normalization, and artifact-state updates in one handler path instead of a shared branch chain.
      - Artifact evidence IDs are normalized to canonical known references (`findings`, `quote_candidates`, `doc_map.sections`, and `key_metrics` when that pack is enabled) before schema-reference validation; unresolved IDs are cleared rather than failing the entire artifact payload.
       - Packs are stored under `out/<report-slug>/report_analysis/*.json` and persisted in the metadata DB (`reports` table columns `vector_store_id`, `evidence_packs_json`; state DB stores `vector_store_status`, `indexed_at_utc`, `openai_file_id`, `last_error`).
       - Orchestrator logs `VECTOR_STORE_CREATED`, `VECTOR_STORE_INDEXED`, `EVIDENCE_READY`.
- Evidence packs, artifacts, validation reports, and HTML are cached by md5 + prompt/template hashes to skip repeat LLM and rendering work when inputs are unchanged. Artifact and validation caches are retrieval-mode aware, so `chat_json` and vector-retrieval outputs are isolated.
- Final `analysis_<mode>.json` snapshots preserve internal report payload metadata, including the active vector store ID, persisted analysis pack paths, and text extraction stats used by downstream diagnostics.
      - Durable checkpoints are written through `file_service` after `source_prepared`, `selection_complete`, `analysis_complete`, and `render_complete`. Each `PipelineStageCheckpoint` stores `schema_version`, pipeline/file/stage identifiers, artifact references, and the semantic state needed for the supported restart boundary.
      - Semantic restart currently supports `resume_from_stage="analysis_complete"` through `run_report_generation(...)` and `run_report_pipeline(...)`. That path reads the checkpoint, reconstructs the source/selection/analysis contracts, re-renders HTML, re-runs analytics projection, and writes a fresh `render_complete` checkpoint without repeating upstream LLM/API stages.
      - DocMap retries/fallback: `doc_map` generation performs JSON-from-text fallback (including fenced blocks/extracted object) in the generator, but retryable `AppError` failures are propagated (not converted into fallback payloads) so retry/backoff policy is owned by `src/orchestrators/report_pipeline_orchestrator.py`. Retry attempts are bounded by `ingest.evidence_packs.doc_map_max_attempts` and use jittered backoff.
       - DocMap validation: if the `doc_map` pack remains empty after retries/fallback (no sections/title/doc_id/summary), the report is halted for that PDF and the error is logged/recorded with a summary persisted to the state DB.
      - DocMap normalization: responses wrapped under `docmap`/`doc_map`/`docMap` are unwrapped; `document.title`/`document.publisher` + `structure` are normalized into canonical top-level `title`/`publisher`/`sections`; document-level alias fields such as `document_title`/`document_summary`/`document_publisher` are also mapped into canonical schema keys; when canonical metadata is still missing, `title`/`publisher` fall back to deterministic derivation from report filename patterns and publisher suffixes in document titles (for example `... — Publisher 2025`); missing `doc_id` is filled with the report ID; top-level and section summaries normalize aliases such as `brief`/`overview`; section `key_points` normalize aliases such as `keyPoints`/`highlights`/`bullets`; mixed object/string/list shapes are coerced into canonical schema types (string summaries, string key-points, integer pages, string references) before schema validation; section `id`s (and `pages` from `page`) are auto-generated/coerced before schema validation.
      - DocMap completeness warning: when any populated section has an empty brief (`sections[].summary`), the generator logs `doc_map_completeness_warning` with coverage ratios; processing continues.
       - Reports DB metadata sourcing: `reports.title` is written from `doc_map.title` (fallback to file-derived title only when doc_map title is empty), `reports.publisher` is sourced from `doc_map.publisher` or `doc_map.organization`, `reports.file_name` stores the source PDF filename, and `reports.time_period` is normalized to canonical discrete values only: `YYYY`, `Mon YYYY`, `Qn YYYY`; when multiple periods are present they are stored as a comma-separated list (for example `2025, 2026` or `Q1 2026, Q2 2026, Q3 2026`). Non-period annotation text (for example parenthetical notes like fieldwork context) is stripped, and only recognized period tokens are persisted/returned. During HTML render, `title`/`publisher`/`time_period` are read from `reports` DB metadata only.
       - Taxonomy extraction: `src/generators/taxonomy_generator.py` uses `src/prompts/report_vs/taxonomy/` to extract central report tags plus region/time_period from the vector store; taxonomy output is cached at `out/<report-slug>/report_analysis/taxonomy.json` when `md5` is available and `analysis.vector_store_keep=true`.
     - **Validation**: `src/generators/validation_generator.py` is now a thin entrypoint over a registry-driven rule runner in `src/generators/validation/` (`semantic`, `metrics`, `quotes`, `numbers`, `grounding`) with deterministic ordering and rule-ID-prefixed failures:
       - Canonical normalization: shared `normalize_text()` / `normalize_for_lookup()` (`src/utils/text_normalization.py`) are used for quote matching, numeric parsing, and evidence retrieval indexing.
       - Generic quantity grounding: `src/utils/quantity.py` parses comparator + value + unit family + magnitude + timeframe across `%`, `pp`, currencies (`$ € £ ¥`, `k/m/b/bn/mn`), ratios (`1 in 10`, `x`), ranges, rates (`YoY/MoM/CAGR`), counts (`N=`), and date/quarter tokens.
       - Canonical quantity matching: validator accepts equivalent numeric surface forms (e.g. `37.0` / `37%` / `0.37` in percent context, `$3M` / `3 million USD`, `>10` with explicit USD-billions context, range overlap, approx/comparator compatibility, rounding tolerance by unit family).
       - Figure/new-number checks compare numeric values in a unit-agnostic way (unit labels are ignored for those checks), reducing false fails from `%`/currency/count unit wording differences.
       - Section policy: `strict` (`insights`, `quotes`, claims/metrics), `soft` (`expert_comment`, `linkedin_post`), `mixed` (`summary`). Soft sections allow interpretation/recommendations; unsupported quantities are warning-by-default unless clearly metric-attributed.
       - Evidence retrieval: validation builds overlapping evidence windows (token windows with stride), stores precomputed character n-gram counts/norms on each `EvidenceWindow`, scores via hybrid lexical overlap + BM25-like term hits + quantity boost, selects candidates with bounded top-k retrieval, and expands with neighbor windows to reduce page-break false negatives. Cached PDF text (`cache/pdf_cache/<md5>/text_*.json`) is included in retrieval windows when available.
       - Quote validation: verbatim quotes require normalized near-verbatim support (substring/lexical threshold). Paraphrase-labeled quotes are allowed with semantic support.
       - Semantic: LLM re-check via `src/prompts/report_vs/validate/semantic/{system,user}.yaml` (model resolved via `openai_models` longest-prefix match) that scores metric/quote support against evidence snippets and logs prompt hashes + evidence/metric/quote SHA-256. Semantic “supported” adds `info` issues; “unsupported” raises `warning|error`.
       - Grounding rubric (`src/prompts/report_vs/validate/grounding/{system,user}.yaml`): validator distinguishes `factual_claim`, `analyst_interpretation`, and `prescriptive_recommendation`. Hard fails are reserved for hallucinated entities/events, unsupported metrics, misattributed quotes, and “the report said/instructed X” misattributions; retrieval failures are tracked separately. Grounding defaults to closed-context (`chat_json`) and can be switched back to vector retrieval via `analysis.validation_grounding_use_vector_store`.
      - Parallel execution: when `ingest.report_worker_limit > 1`, the validation registry runs `toc_integrity`, `family_confidence`, `claim_support`, and `semantic` as bootstrap rules, `numbers` + `grounding` as independent rules, and `metrics` + `quotes` after semantic support is available. Issue merge order remains deterministic as `toc_integrity -> family_confidence -> claim_support -> semantic -> metrics -> quotes -> numbers -> grounding` to prevent behavioral drift while keeping the large control block out of the entrypoint.
       - If validation fails after artifact generation, `report_analysis_orchestrator` can build a bounded regeneration plan from `affected_section`, explicit `repair_target`, and known `rule_id` mappings, regenerate only the failing artifact families (or one broad retry for truly unmappable/global failures), and re-run validation until pass or `ingest.validation.regeneration_max_attempts` is reached. Each regeneration attempt logs target details, regenerated sections, artifact paths, and a top-level artifact diff summary for before/after review; unsupported explicit repair targets fail closed with a typed `AppError`.
       - Results persist to `out/<report-slug>/report_analysis/validation*.json` and flow into HTML and publish policy decisions. The canonical `validation.json` is always updated to the latest attempt used by render/publish, while regeneration snapshots are also persisted as `validation_regen_attempt_<n>.json`. When `ingest.validation.data_gap_policy` is `warn`, missing evidence/text downgrades to warnings. Schema validation is performed via `schema_validator_service`.
     - **Normalization**: `normalize_generator` enforces strict schema and list sizing.
    - **Categorization**: stored evidence packs are compacted into a `ReportCategoryContext`, then a single batched category-fit prompt evaluates all portal categories against that context using each category's `definition`, `include_when`, and `exclude_when` guidance from `src/config/category-mappings.yaml`. The selector returns at most two portal categories, which are exposed publicly as Topics. Taxonomy tags are kept as metadata and do not determine category assignment.
     - **Figure selection**: `pdf_service.extract_best_figure` selects a representative visual and caption.
      - **Candidate extraction**: `pdf_service.collect_candidates` remains the single public coordination boundary for chart/table discovery, page-level extraction, and contents-page exclusion. Table extraction lives under `src/services/_pdf/table_candidates.py`; `src/services/_pdf/table_heuristics.py` preserves its compatibility surface while private capability modules in `src/services/_pdf/_table_heuristics/` own policy, models, layout analysis, region formation, and screening. `src/services/_pdf/visual_candidates.py` preserves the chart/infographic compatibility surface while `_visual_candidates/raster.py`, `screening.py`, and `extraction.py` own raster qualification, false-positive screening, and extraction coordination; shared geometric heuristics remain behind `src/services/_pdf/visual_heuristics.py`. Visual candidate extraction now builds one per-page relationship lookup for xref/block/panel/heading candidates and reuses it for side-by-side sibling, oversized-wrapper, panel-shadow, stacked-panel, neighbor-bound, and internal-caption checks instead of repeatedly scanning every page candidate.
     - **Candidate prefilter + ranking**: deterministic prefilter removes obvious low/no-data fragments, reference-style/table-shadow leaks, low-confidence visual fragments, and other early false positives before kind-aware truncation and LLM ranking. Rank prompts receive both the full typed feature payload and a compact `quality_signals` block (`ocr_density`, `visual_entropy`, `chart_confidence`, `table_confidence`) alongside overall + quality + insight + data + keep/reject_reason scoring; model resolves from `openai_models.rank_candidates` if set, else `rank.model`, then `ingest.openai_model`. The detailed prefilter, ranking, and threshold behavior is documented in [Ranking, Crop Refinement, and Fallback](#ranking-crop-refinement-and-fallback).
     - **Candidate fallback policy**: fallback crops no longer revive candidates that already failed the configured rank thresholds; fallback is limited to threshold-passing ranked candidates first, then remaining deterministic prefilter survivors by kind-balanced caps.
     - **Adaptive crop refinement**: ambiguous candidates call `rank_candidates/crop_refine` with page image context; obvious pass/reject candidates skip LLM. Ambiguous page renders are pre-rendered in parallel and crop-refine LLM work is batched per page/phase in bounded parallel mode. Crop refinement runs in two passes (coarse -> finalize) to improve edge precision and reduce clipped text artifacts, and now auto-recovers missing batched decisions with targeted single-candidate retries so partial model outputs do not silently drop valid candidates. Missing-decision recovery keeps deterministic missing-ID ordering while using one per-phase candidate lookup instead of repeated recovery scans.
     - **Strict cropping**: final crops are routed by visual kind (`table_strict` for tables, `chart_strict` for charts) so each class uses tailored border trimming instead of a monolithic crop mode. Chart/text edge-guard cleanup now caps inward trim distance so long external prose lines cannot carve out a large portion of an otherwise valid chart.
    - **Zero-pass behavior**: if strict candidate selection produces no final slices, report generation falls back to ranked/prefiltered candidate crops (bounded by the same per-kind caps). Legacy fallback candidate crops and `extract_best_figure` are now deferred until that strict path actually fails, so debug-grade crop inspection can stay available without forcing the normal path to pre-crop every candidate. If no crop fallback is usable but `extract_best_figure` produces a primary figure image, the HTML still renders a primary-only figure section instead of hiding it.
     - **Preview rendering**: `pdf_service.render_preview` renders the first page to PNG. When the detected contents page is page 1, the render stage reuses the existing contents preview asset instead of rendering the same page twice.
      - **Cover image generation**: `cover_image_generator` resolves style from `cover-styles.yaml` using the report’s first category (falls back to `default` for styling only), while the rendered label text, title, publisher, time period, and region always come from report metadata in the DB. Cover assets are now written into the canonical report folder (`out/<report-slug>/assets/`) with length-bounded, file-id-suffixed filenames via `src/utils/cover_path_utils.py`; Streamlit preview lookup follows the same path logic with legacy-path fallback.
    - **HTML rendering**: `render_service` generates the final HTML digest with premium template UX (split hero, sticky nav + progress, section accents, signal cards, editorial quotes, figure carousel/lightbox), plus SEO metadata (OG/Twitter/canonical/JSON-LD) and explicit image dimensions. The service reuses one module-scoped Jinja environment so repeated renders stay deterministic without rebuilding template state on every call. In the **Key data insights** section, cards now render only the main insight sentence (metric/source sub-lines are suppressed).
   - If the reports DB already has `html_path` for the same `file_id` + md5 and the HTML exists on disk, the orchestrator skips report generation.

7. **State record**
   - The orchestrator records completion or failure state after each report generation attempt (including `doc_map_empty` and `pdf_text_unextractable` errors). DocMap failures persist a `doc_map_summary_json` payload for debugging.

---

## End-to-End Flow (Publish to WordPress)

1. **Configuration load**
   - `src/services/config_service.py` remains the canonical configuration service facade; semantic resolver families for paths, ingest, OpenAI/LLM, browser download, publisher discovery, publish, validation, analysis, and Drive live under `src/services/_config_service/`. Secrets still come from `.env`.
   - Produces `PublishSettings` contract.

2. **Pipeline orchestration**
   - Entry point: `src/cli.py` (`publish-wp`).
   - `src/orchestrators/publish_orchestrator.py` coordinates HTML publishing.

3. **HTML discovery**
   - `src/services/file_service.py` lists generated HTML files in `OUTPUT_DIR`.
   - Generated HTML is parsed into `PublishHtmlSnapshot`, including the typed publish entity metadata embedded in the artifact. The metadata is the routing contract for the WordPress post type, front-end section, and template.
   - `file_id` is resolved from reports metadata (`reports.html_path -> reports.file_id`) when available, then from the HTML marker, then from `PublishEntityMetadata.source_artifact_id` for non-report public artifacts.

4. **State checks**
   - `src/services/state_service.py` verifies the report was processed and not already published.

5. **Publishing (per file)**
   - `src/orchestrators/publish_orchestrator.py` now builds one publish-run preflight snapshot for the selected HTML set: file IDs, validation state, processed-state presence, existing WordPress post lookups, and resolved category/tag/publisher term IDs are prepared once before per-file publish decisions run.
   - The preflight validates `PublishEntityMetadata` before any WordPress call. Supported routes are `report -> ml_report`, `briefing -> ml_briefing`, and `signal -> ml_signal`; missing, unknown, ineligible, or mismatched metadata produces a typed publish error and a structured log event.
   - `src/generators/publish_generator.py` consumes the orchestrator-resolved WordPress auth header, accepts optional pre-resolved WordPress term IDs from that preflight snapshot, uploads report images with bounded parallelism, swaps image URLs to the site-side media proxy route, injects a hidden `Drive fileId` marker when the rendered HTML does not already contain one, and creates a WordPress post.
  - `src/services/wordpress_service.py` handles media and post API calls through one shared internal request executor. The executor reuses pooled `requests.Session` connections per host when direct request transports are not patched, preserves the existing `requests.get/post` test seam, and carries pooled-session metadata plus bounded/sanitized response diagnostics into structured logs and retryable `AppError.context` for publish, taxonomy, tag, and media flows.

6. **State record**
   - Published posts are recorded with post ID and URL for idempotency.
   - Validation policy: `publish.validation.policy` set to `block` skips publish when validation fails/missing; `warn` logs issues but proceeds. Publish outcomes include validation status/issues.

---

## Technical Design Notes

This section keeps implementation-heavy extraction and crop heuristics out of the main workflow narrative while preserving one place to document the current design.

### Visual Candidate Pipeline

- `pdf_service.collect_candidates` is the single public PDF-candidate boundary; internal heuristics are split by capability under `src/services/_pdf/` so table and chart flows can evolve independently without creating competing service entrypoints. `src/services/_pdf/visual_heuristics.py` stays as the geometric heuristic facade over chart-layout, panel-detection, and chart-collection families, while `src/services/_pdf/visual_candidates.py` stays as the extraction compatibility facade over raster qualification, deterministic screening, and extraction coordination.
- The candidate path starts with scored page triage, excludes the detected contents/index page from output, and then runs table/chart discovery in parallel within `ingest.report_worker_limit`. `ingest.candidate_page_gate` configures the page-value threshold and recall floor; each evaluated page logs its score, action, and deterministic reasons so operators can see when low-signal pages were skipped or re-included for recall.
- Deterministic prefiltering removes obvious non-data fragments before ranking, including figure/box text leaks, reference-style table blocks, narrative callouts, and weak table-shadow/chart-shadow overlaps.
- Kind-aware truncation is applied after deterministic prefiltering so noisy table pages cannot starve chart candidates or vice versa before LLM ranking.

### Table Crop Composition Heuristics

- Stream-table candidates are first reduced to the dominant tabular row cluster, then expanded with nearby title, note, source, and statlink text while hard-stopping at margin noise, page-number/header bands, downstream body prose, and next-section headings.
- Table recovery is intentionally layout-based: it can restore clipped right-edge columns, recover dense first-column text when lattice extraction misses it, preserve explicit `Table` or `Exhibit` title bands, keep wrapped footnotes, and extend real overlapping footer blocks below the body.
- Table validation rejects prose-shaped layouts such as boxed narratives, bullet lists, section-list pages, front matter, bibliography blocks, and decorative figure fragments; dense infographic value panels are still allowed when their text behaves like compact tabular data.
- Continuation handling is conservative: full-width adjacent-page tables can stitch a title strip or footnote strip across pages only when the second page is a strong same-table continuation.

### Chart and Infographic Recovery Heuristics

- Chart candidates trim page-number/header noise, recognize captioned visuals plus captionless slide/deck charts, and recover infographic cards whose headline may live inside the card rather than above it.
- Panel recovery is deliberately local: shared titles can claim aligned sibling panels, but cross-panel text attachment is clamped so one title or label line cannot swallow the whole page.
- The visual flow tolerates dense chart-like labels and compact instruction-card structures, can preserve a drawing-backed prose side card when it is part of the same chart panel, and prunes chart candidates that are really overlapping table shadows.
- Cleanup favors publisher-agnostic layout signals over report-family keywords, but the current stack still includes a few transitional heuristics such as explicit `StatLink` handling and OECD-style bibliography terms; those should be generalized over time.

### Ranking, Crop Refinement, and Fallback

- Ranked selection is kind-split: tables and charts are scored independently with overall, quality, insight, and data signals before thresholding and per-kind caps are applied.
- Ambiguous candidates enter a two-pass crop-refinement flow (coarse then finalize) using page-image context; obvious keep/reject cases skip the extra LLM round trip.
- Final crop saving is candidate-ID based so strict table/chart outputs cannot overwrite each other in the shared `slices/` directory.
- Conservative edge correction expands partially clipped border text when needed and trims small spillover fragments when they clearly belong to surrounding body prose rather than the figure itself.
- If strict selection yields no usable final slices, fallback is bounded: threshold-passing ranked candidates are preferred first, then remaining deterministic survivors by balanced kind caps, and finally the HTML can still render a primary-only figure section when `extract_best_figure` produced a usable lead visual.

---

## Logging and Observability

Structured logs are emitted by all services, generators, and orchestrators using `src/utils/logging.py`.
Redaction covers API keys, bearer tokens, and common PII patterns before log emission.

CLI-provided run contexts flow into the ingest orchestrator so CLI run/task IDs stay consistent across downstream orchestrator/service logs.

CLI rich exception rendering keeps local variables out of terminal tracebacks; structured logs remain the supported diagnostic surface and pass through the normal redaction path. CLI failure handling uses Typer's public exit contract so validation, replay, and UI-worker failures preserve nonzero exit behavior across supported Typer releases.

Every log event includes:

- `run_id`: pipeline run identifier
- `task_id`: per-file identifier
- `span_id`: per-operation span identifier
- `trace_id`: end-to-end trace identifier shared by nested spans in one run
- `parent_span_id`: parent operation span for tree reconstruction
- `span_name`: human-readable trace span name
- `span_depth`: zero-based nesting depth
- `timestamp_utc`: event timestamp used for trace timing
- `module`: logger name
- `role`: service / generator / orchestrator
- `event`: logical event name

`RunContext` remains backwards-compatible for older call sites, but `new_run_context(...)` now creates a root trace and `child_context(...)` preserves that trace while linking each child span to its parent. Operators can inspect one run as a tree without stitching raw logs manually:

```bash
python -m src.cli trace-run --run-id <run_id> --log-path logs/market_lense_YYYY-MM-DD.log
python -m src.cli trace-run --trace-id <trace_id> --json
```

The trace inspector uses `src/generators/trace_generator.py` to group structured log events into span summaries with event counts, parent/child edges, and observed duration in milliseconds.
It also validates trace integrity while building the read model:

- `valid=false` means at least one required structured log field is missing or a span references a parent span that is absent from the selected event set.
- `trace_event_missing_required_field` and `trace_event_empty_required_field` identify malformed log events by `span_id`, event index, and field name.
- `trace_orphan_span` identifies broken parent/child relationships, usually caused by filtering a trace too narrowly or by a context propagation bug.
- Workflow coverage summarizes detected `report`, `publish`, and `cross_report` stages and marks a stage complete only when orchestrator, generator, and service roles all appear in the same reconstructed workflow tree.

For incident review, start with `--run-id` to see the whole run. Use `--task-id` only after confirming that the narrower filter does not create expected orphan diagnostics by excluding parent spans.

UI-run worker orchestration also records replay metadata beside the registry DB:

- `state/ui_runs/<run_id>/replay_manifest.json`: original request payload, sanitized config snapshot/fingerprint, source-tree fingerprint, prompt-tree fingerprint, result summary, and artifact hashes.
- `state/ui_runs/<run_id>/replays/replay_report_<timestamp>.json`: comparison report produced by `replay-run`, including drift gates plus field-by-field output deltas against the original run.

Examples:

- `openai_analyze_start`
- `openai_prompts_loaded`
- `drive_download_complete`
- `report_generate_complete`

---

## Error Taxonomy and Retries

All external I/O services raise `AppError` with attributes:

- `code`
- `message`
- `cause`
- `retryable`
- `severity`
- `context`

Retry behavior is centralized in two places by role: `src/orchestrators/retry_orchestrator.py` handles workflow retries for ingest/publish/report orchestration, while `src/services/llm_service.py` handles shared model-call retries/backoff/circuit-breaking (plus optional scope-level rate limiting) before retryable `AppError` failures are surfaced back to orchestrators.

---

## Prompt Management

Prompts are stored in YAML by namespace:

```text
src/prompts/report_vs/doc_map/          # vector_store doc map
src/prompts/report_vs/evidence_packs/   # vector_store packs (scope/methods/findings/limitations/quote_candidates/key_metrics/risk_register/recommendations/contradictions)
src/prompts/report_vs/artifacts/        # artifact sections (toc, summary, insights, quotes, expert comment, LinkedIn)
src/prompts/report_vs/figure_caption/   # multimodal per-image figure captioning
src/prompts/report_vs/artifacts/regenerate/  # targeted regeneration prompts per artifact family
```

Prompts are rendered with Jinja2 (`{{ variable }}`), loaded and hashed by `src/services/prompt_service.py`, and logged with their SHA256 hashes for reproducibility.

- Prompt caching: prompt sets are cached in-memory per namespace for the duration of a process. Prompt namespace listing uses an in-memory manifest and validates known prompt-directory mtimes instead of rescanning the whole prompt tree on steady-state reads. `PromptLoadRequest` supports `reload_if_changed` (nanosecond mtime check) and `force_reload` (bypass cache) when you need to pick up edited prompt files mid-run.
- Repository-wide prompt dry-run validation: `src/services/prompt_service.py` now exposes a prompt dry-run validator that renders every discovered prompt namespace against declarative fixture inputs in `src/prompts/_dry_run_fixtures.yaml`. `tests/test_prompt_dry_run_validation.py` is the CI gate: it fails when a namespace is missing fixture coverage, when a fixture references a stale namespace, or when a prompt render hits missing variables or invalid template syntax before runtime.
- Prompt fixture performance/cost baseline: `src/prompts/_dry_run_fixtures.yaml` now also carries benchmark metadata per namespace (`expected_output_tokens`, OCR calls, browser attempts, and optional tool calls). `scripts/quality/build_prompt_fixture_corpus_baseline.py` writes the committed versioned baseline at `docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json`, and `scripts/ci/check_prompt_fixture_regression.py` compares the live corpus against that baseline with per-family deltas for runtime, tokens, OCR calls, browser attempts, and estimated cost. Aggregate runtime uses a larger absolute tolerance than each per-family runtime check because the corpus total sums all fixture families; token, OCR, browser-attempt, and cost deltas remain exact or tightly bounded. Temporary budget regressions must be recorded with owner/reason/expiry in `docs/quality/prompt_fixture_corpus_allowlist.yaml`.

---

## Category mappings

- Source of truth: `src/config/category-mappings.yaml` (versioned by `schema_version`).
- Category policy: production portal categories are the implementation layer for public Topics and are assigned only by the context-first fit flow, which evaluates compacted report evidence against each category's `definition`, `include_when`, and `exclude_when` profile. The former weighted taxonomy tag scorer has been removed, so taxonomy tags remain metadata and prompt vocabulary rather than a competing category engine.
- Category schema: categories expose stable `id`, `label`, and `description`, and every portal-exposed category must also define `definition`, `include_when`, and `exclude_when` so the context-first classifier has explicit decision boundaries. The same mapping file still retains `core_tags`, `supporting_tags`, `secondary_supporting_tags`, `descriptor_tags`, `generic_tags`, `negative_tags`, and optional `must_have_one_of` fields for taxonomy metadata support, audits, and compatibility flows. Tag values are canonical underscore slugs end-to-end in repo config, inference rules, extracted taxonomy output, and stored taxonomy metadata. The root mapping file also supports `inference_rules` for evidence-backed tag bridges that run after extraction. Each inference rule carries a `target_category_id` for maintenance validation and an `inferred_tag` that must already exist in that category's retained subject-signal groups. Legacy `tags` remain supported only for backwards-compatible external mappings and do not assign portal categories.
- Taxonomy inference: configured `inference_rules` can add or remove extracted tags when trigger-tag evidence matches configured context keywords. These rules refine taxonomy metadata before it is stored and before context-first categorization consumes the report context, but they do not score or select portal categories.
- Taxonomy prompt: allowed tags from the mapping signals are provided to `src/prompts/report_vs/taxonomy/`; the prompt now asks for central subject tags, explicit secondary themes, and short per-tag evidence rather than broad template tags. Tags present only in `descriptor_tags` may still be extracted for metadata, but they no longer affect portal categorization.
- Maintenance: add categories with `id` (snake_case), `label`, `description`, `definition`, at least one `include_when`, and at least one `exclude_when`. Those profile fields are required for every portal-exposed category because they drive production category assignment. Retained tag groups should stay focused: use `core_tags` for specific subject signals, keep broad report descriptors in `descriptor_tags`, move weak but category-relevant context into `generic_tags`, reserve `secondary_supporting_tags` for legitimate secondary themes, and use `negative_tags` only when a tag reliably indicates an adjacent but wrong category.
- Coverage policy: if an extracted tag is a recurring high-signal subject label or an `inference_rules` trigger, it should appear in at least one retained subject-signal group (`core_tags`, `supporting_tags`, or `secondary_supporting_tags`) so metadata audits stay interpretable. Broad cross-domain descriptors such as `consumer_trends`, `social_media`, `digital_economy`, and `forecasts` should stay in `descriptor_tags` or category-local `generic_tags`.
- Coverage constraints: keep every category populated with more than 10 tags, keep every tag categorized (no orphan tags), and limit any single tag to at most 5 category lists even when copied for high relevance.
- Current taxonomy highlights: `digital_payments`, `retail_logistics`, `consumer_behavior`, `business_performance`, `agentic_commerce`, plus existing advertising, commerce, CTV, social video, and measurement tracks.
- Unmapped handling: the mapping loader still reads any existing root `uncategorized` review records from the YAML file, but runtime categorization no longer mutates the mapping file. Mapping maintenance is an explicit config-editing step.
- Mapping caching: category mappings are cached in-memory per path with optional `reload_if_changed`/`force_reload` flags on `CategoryMappingLoadRequest`.

---

## Contracts and Schemas

Key contracts live under `src/contracts/`:

- `config.py`: `AppSettings`
- `drive.py`: Drive file and request/response contracts
- `openai.py`: OpenAI request/response contracts
- `pdf_text.py`: PDF text extraction contracts
- `prompts.py`: Prompt load/render contracts
- `report_models.py`: `ReportPayload`, `Quote`, `Figure`, etc.
- `report_assets.py`: request/response contracts for figure, preview, crop, ranking, etc.
- `publish.py`: publish settings, requests, and outcomes
- `state.py`: state store contracts
- `wordpress.py`: WordPress request/response and auth settings
- `pdf_context.py`: shared PDF context (PyMuPDF + pypdf handles) and build request/response contracts
- `pdf_utils.py`: EOF check and PDF info (page count + metadata) contracts
- `report_store.py`: report metadata upsert/get/list contracts, including page count and flattened PDF metadata
- `semantic_ids.py`: typed `RunId`, `TaskId`, `ReportId`, `PublisherId`, and `EntityUid` wrappers used by core contracts to block cross-ID reuse while preserving string-compatible JSON/state boundaries
- `analytics_projection.py`: canonical report/entity projection rows, projection status/failure requests, and vector-ready queue contracts
- `validation.py`: validation requests, issues, and reports (persisted per report)
- `regeneration.py`: validation-regeneration issues, plans, attempt results, loop state, and typed single-pass request/response contracts
- `docpacks.py`: typed contracts for core/variety docpack payloads and map aliases

---

## Analytics Projection Foundation

After the rendered report outcome has been successfully assembled, `src/orchestrators/report_generation_orchestrator.py` invokes `src/orchestrators/analytics_projection_orchestrator.py`. The projection pass maps existing DocMap, FindingsPack, KeyMetricsPack, taxonomy, context-category fit, artifacts, validation, and figure payloads into normalized SQLite tables plus `vector_projection_queue`. These projections are the implementation layer for the intelligence entity model: source sections, findings, claims, metrics, quotes, figures, tags, and categories become recoverable Report, Topic, Signal, Briefing, Publisher, Figure, Region, and Time Period inputs without making WordPress responsible for inference.

The projection is additive. Existing JSON packs, audit artifacts, vector-store-first analysis, and HTML rendering remain the source behavior. Projection failures are persisted on the `reports` row with `projection_status='failed'`, attempt count, and typed error fields, then logged as `analytics_projection_failed_nonblocking` without blocking the processed HTML outcome.

Projection-owned tables include `report_sections`, `report_findings`, `report_metrics`, `report_quotes`, `report_claims`, `report_tags`, `report_categories`, `report_figures`, and `vector_projection_queue`. `report_id` is the existing Drive file ID, and `source_file_id` is not stored separately when it would duplicate `report_id`. Projected metrics, quotes, claims, methodology notes, and limitations are internal Data Points; public metric/statistic surfaces should use Figure, Key Figure, or Key figures in report language and preserve raw value, unit, source report, publisher, and evidence reference. Durable Signal candidates and groups are derived only from projected evidence, retain source table/entity/page lineage and raw source caveats, and are stored in the separate Signal base tables `signal_candidates` and `signal_candidate_groups` until the Signal publish workflow turns them into `SignalPublishProjection` output.

`vector_projection_queue` stages future embedding work with deterministic `entity_uid`, canonical `text_payload`, `content_hash`, metadata JSON, `content_class`, and `embedding_status` constrained to `pending`, `embedded`, or `failed`. The queue does not implement global retrieval yet.

Implementation notes live in `docs/quality/analytics-projection-foundation.md`.

---

## Schemas (JSON)

Location: `src/schemas/`

- `doc_map.schema.json`: DocMap schema for `doc_id`/`title`/`summary` plus structured `sections[]` (`id`, `title`, required `summary`, required `key_points`, `pages`, `references`).
- `scope_pack.schema.json`, `methods_pack.schema.json`, `findings_pack.schema.json`, `limitations_pack.schema.json`, `quote_candidates_pack.schema.json`: strict per-pack schemas for core evidence packs.
- `key_metrics_pack.schema.json`, `risk_register_pack.schema.json`, `recommendations_pack.schema.json`, `contradictions_pack.schema.json`: strict schemas for variety packs.
- `artifacts.schema.json`: artifacts/toc/summary/insights/quotes/expert_comment/linkedin payload shape.
- `validation_report.schema.json`: structure for validation results.
- `taxonomy.schema.json`: taxonomy extractor response schema for tags/regions/time_period.
- Union `type` arrays are validated as true unions (for example `["string", "null"]` now accepts either a string or `null` and rejects other types).

Schema validation is performed by `src/services/schema_validator_service.py` and logged per pack.

---

## Testing

Test suites live under `tests/` (unit + contract + integration marker support):

- `test_validation.py`: contract validation helpers
- `test_normalize_service.py`: normalization behavior
- `test_cli.py`: CLI wiring
- `test_orchestrator_retry.py`: retry behavior
- `test_publish_orchestrator.py`: publish orchestration
- `test_html_utils.py`: HTML parsing helpers
- `test_artifact_generator.py`: artifact JSON generation/validation
- `test_report_regeneration_generator.py`: targeted regeneration generator behavior, prompt payloads, and error propagation
- `test_regeneration_contracts.py`: regeneration contract round-trip and required-field coverage
- `test_io_boundaries.py`: AST boundary gate that fails on direct filesystem/network I/O usage in `src/generators/*` and `src/utils/*`
- `test_render_service_artifacts.py`: HTML sections for artifact rendering
- `contracts/test_contract_roundtrip.py`: dataclass serialization/deserialization round-trip gate for `src/contracts/*`
- Large behavior suites now live in same-name test packages with local shared builders, for example `tests/test_browser_report_download_service/*`, `tests/test_pdf_figures_service/*`, and `tests/test_publisher_inventory_service/*`. Their package `__init__.py` files re-export local builders to preserve existing helper imports used by adjacent tests.

Install dev/test tooling:

```bash
pip install -r requirements-dev.txt
```

The dev requirements include third-party type stub packages used by the full-repo mypy gate and the narrow browser-use support dependencies exercised by default unit tests, including `pydantic-settings` for vendored browser-use configuration imports and `aiohttp` for the local browser watchdog CDP readiness probe; run this install before local `scripts/ci/run_type_check.py` or `pytest` checks so local dependency state matches CI.

### Local browser-use

Browser Use is vendored locally at `tools/browser-use` from `https://github.com/mbrakker/browser-use` as a subordinate tool inside Market Lense.
Root project conventions and the root `AGENTS.md` are authoritative; vendored Browser Use docs and agent-instruction files are wrappers that defer to this repo.
Preserved upstream reference material lives in `tools/browser-use/UPSTREAM_README.md`, `tools/browser-use/UPSTREAM_AGENTS.md`, `tools/browser-use/UPSTREAM_CLAUDE.md`, and `tools/browser-use/UPSTREAM_CLOUD.md`.
Browser Use runtime configuration also lives in the root `.env`; the vendored subtree is wired to read `C:\Programing\Market lense\.env` instead of maintaining its own local `.env`.
The vendored copy also carries local CodeQL remediations for Market Lense CI: startup/setup logs avoid config-derived secret values, sensitive-data placeholder logs report counts and sanitized hosts only, example HTML-to-text conversion uses an HTML parser, and URL assertions use parsed hostnames instead of substring checks. Keep these hardening patches when refreshing the vendored tree, or port them upstream before replacing it.
To use that local source inside this project virtualenv, install it editable:

```bash
.\.venv\Scripts\python.exe -m pip install -e .\tools\browser-use
```

After installation, the CLI is available from the project virtualenv as:

```bash
.\.venv\Scripts\browser-use.exe --help
```

The repo-level report download automation uses that same local runtime through `src/services/browser_report_download_service.py`. It now plans each attempt from remembered route memory plus discovery/diff evidence, probes candidate PDFs before browser-use when discovery already exposed them, tailors browser-use prompts per route family, captures structured route steps plus blocker/terminal/on-site evidence, and stores both the best legacy projection and the richer per-attempt route history for later reuse. Verified or recovered successful browser-route results can also be promoted into reviewable YAML playbooks under `src/playbooks/browser_routes/` when `browser_download.route_playbook_promotion_mode` is `dry_run` or `write`; the orchestrator logs the selected mode, skip reason or playbook path, version, and review-diff line count. Private-API playbook promotion is automatic when `browser_download.private_api_playbook_promotion_mode` is `dry_run` or `write`: the orchestrator inspects verified downloaded browser results, asks the browser-download service to replay safe endpoint candidates, records threshold progress in `publisher_private_api_candidates`, and writes YAML only after `private_api_playbook_min_success_count` and `private_api_playbook_min_distinct_source_urls` are both met. The manual `python -m src.cli promote-private-api-playbook --request-json <path>` command remains available for reviewed backfills and one-off operator promotions.

Developer browser diagnostics are available through `python -m src.cli browser-doctor`. The command is self-contained in Marketlense tooling, adapts the browser-harness setup/doctor pattern for browser-use, checks profile/download writability, starts browser-use, verifies CDP and a real page target, activates the verification tab, attempts one bounded stale-connection cleanup, and logs each check without adding self-healing to production browser-download paths. Bounded browser session/profile reuse is opt-in through `browser_download.session_reuse` or `browser-doctor --reuse-*`, supports only `developer_canary` and `same_publisher_batch` modes, requires an explicit session key, publisher scope, and TTL, rejects cross-publisher reuse by default, and logs reuse resolution/finalization while production acquisition remains isolated by default.

For OpenRouter-backed usage, see `tools/browser-use/examples/models/openrouter.py`, which is configured to use `stepfun/step-3.5-flash:free` through `OPENROUTER_API_KEY`.

Run tests locally:

```bash
pytest
```

`pytest.ini` sets `pythonpath = .` so `src.*` imports resolve without exporting `PYTHONPATH`.
Default runs exclude `integration`-marked tests (`addopts = -m "not integration"`).
Workflow tests should prefer explicit dependency dataclasses and shared boundary fixtures over monkeypatching module globals.
Current boundary seams include `IngestBatchDependencies`, `CandidateExtractionDependencies`, and the capability-scoped report-generation contracts: `ReportSourceDependencies`, `ReportSelectionDependencies`, `ReportAnalysisDependencies`, `FigureCaptionDependencies`, and `ReportRenderDependencies`. `ReportGenerationDependencies` now exists only as the top-level orchestrator wiring container that groups those scoped contracts, while the concrete dependency families live under `src/generators/_report_generation_dependencies/` and `src/generators/report_generation_dependencies.py` remains the single public facade.
Use `tests/conftest.py` fixtures like `external_boundary_mocks_only`, `wordpress_http`, and `fake_openai` to patch only external boundaries (service entrypoints, HTTP clients, OpenAI clients, time/random/os), while leaving orchestrator and generator logic on the real path.
Touched orchestrator tests should also use `assert_logs_have_required_fields`, and remaining generator/orchestrator hotspots should move to explicit dependency seams or service-module patch points instead of patching internal module symbols directly.
Prompt text is immutable outside `src/services/prompt_service.py`: generators must render prompts through the prompt service, pass the rendered text through unchanged, and log namespace, prompt paths, hashes, rendered prompts, model params, and raw responses around each model call. Prompt rendering caches compiled Jinja templates by prompt path, hash, and text so repeated dry-run validation avoids recompilation without changing prompt output. `tests/test_prompt_boundaries.py` enforces the no-concatenation rule over `src/`.

Run the live OpenAI smoke test explicitly (opt-in):

```bash
RUN_OPENAI_SMOKE_TEST=1 OPENAI_API_KEY=... pytest -m integration tests/integration/test_openai_smoke.py
```

Run the live OpenAI OCR integration explicitly (opt-in):

```bash
RUN_OPENAI_OCR_INTEGRATION=1 OPENAI_API_KEY=... pytest -m integration tests/integration/test_service_integrations.py -k openai_service_live_ocr_guarded
```

CI gates (see `.github/workflows/ci.yml`):

- `python scripts/ci/check_formatting.py` (format gate, `ruff format --check` over changed Python files under `src`, `tests`, `scripts`; skips when no Python files changed unless `FORMAT_PATHS` is set)
- `python scripts/ci/check_risk_policy.py` (diff-aware risk classifier; exports stricter coverage/mutation thresholds for contract and critical-layer changes in GitHub Actions)
- `python scripts/ci/check_split_symbol_links.py` (static split-boundary export/linking gate; run after facade/internal module splits such as `_config_service`, `_openai_service`, or `_pdf/_visual_heuristics` refactors and before mypy)
- `python scripts/ci/run_type_check.py` (type gate, full-repo `mypy` over `src` by default with `docs/quality/mypy_baseline.json` tracking existing debt; set `TYPECHECK_CHANGED_ONLY=1` only for an explicit fast path, and use `--update-baseline` after triaging ownership/expiry for baseline changes)
- `python scripts/ci/check_architecture_imports.py` (static cross-layer import gate for contracts/services/generators/orchestrators/utils)
- `python scripts/ci/check_forbidden_patching.py` (fails on private-helper/dataclass-constructor patching patterns in tests)
- `python scripts/ci/check_repository_hygiene.py` (fails on tracked temp/runtime artifacts, local credentials, logs, coverage outputs, and oversized generated files unless explicitly allowlisted in `docs/quality/repository_hygiene_allowlist.yaml`)
- `python scripts/ci/check_quality_ledger.py` (validates monthly initiative ownership, baseline/current/target metrics, review dates, and stalled-work decisions in `docs/quality/initiative_ledger.yaml`)
- `python scripts/ci/check_remediation_runbooks.py` (validates top typed-failure runbooks, alert labels, and dry-run remediation hooks in `docs/ops/failure_remediation.yaml`)
- `python scripts/ci/check_backlog_source.py` (enforces `CONSOLIDATED_TODO.md` as the only active backlog source)
- `python scripts/ci/check_contract_schemas.py --snapshot docs/quality/contract_schemas.json` (dataclass contract schema snapshot gate; run with `--update` after approved contract changes)
- `python -m pytest --cov=src --cov-report=xml --cov-report=term-missing` (default suite excludes integration tests and includes the direct-I/O boundary gate in `tests/test_io_boundaries.py`)
- `python scripts/ci/check_coverage.py --coverage-xml coverage.xml` (global + per-critical-package thresholds)
- `python scripts/ci/run_mutation_gate.py --json-out mutation_results.json` (mutation score gate for critical generators/services/orchestrators)
- `python scripts/ci/check_quality_regression.py --baseline docs/quality/baseline_2026-02-21.json --coverage-xml coverage.xml --mutation-json mutation_results.json --docpack-root tests/fixtures/docpacks/golden --candidate-root tests/fixtures/candidate_extraction/golden` (baseline non-regression gate)
- `python scripts/quality/compare_candidate_goldens.py --golden-root "<golden-root-1>" --golden-root "<golden-root-2>" --output-root out/candidate_golden_compare_current` (exact candidate ID/bbox/crop-hash comparison against manually curated candidate goldens)
- `python scripts/quality/run_health_scorecard.py <log_path> --run-id <run-id>` (local/live-run health summary for latency, retries, validation failures, and cost warnings)

PR governance:

- `.github/CODEOWNERS` assigns review ownership by bounded context.
- `.github/pull_request_template.md` includes the mandatory architecture and validation checklist.

---

## Quality Non-Regression

- Baseline snapshot: `docs/quality/baseline_2026-02-21.json`
- Baseline builder: `python scripts/quality/build_baseline.py --copy-golden --baseline-out docs/quality/baseline_2026-02-21.json`
- Golden corpus: `tests/fixtures/docpacks/golden/` (copied from `out/1/*/report_analysis`)
- Golden candidate corpus: `tests/fixtures/candidate_extraction/golden/` (copied from `out/1/*/candidates/candidates.json`, or another root via `--source-candidate-root`)
- Comparator: `scripts/ci/check_quality_regression.py` blocks merge if coverage, mutation, docpack metrics, or candidate-extraction metrics drop below baseline.
- Monthly initiative ledger: `docs/quality/initiative_ledger.yaml` records owner, baseline/current/target metric, review date, and decision for active quality initiatives; `docs/quality/monthly_quality_review.md` is the recurring review agenda.
- Operational remediation registry: `docs/ops/failure_remediation.yaml` maps top typed failure classes to runbooks, alert labels, and bounded dry-run remediation hooks; `docs/ops/top_failure_runbooks.md` holds the operator playbooks and drill metadata.
- Feature controls:
  - `ingest.evidence_packs.registry`
  - `ingest.evidence_packs.enable_new_variety_packs`
  - `analysis.strict_schema_validation`
- Recommended rollout progression for strict schema/new variety packs: `10% -> 50% -> 100%` corpus canary.

See:

- `CONSOLIDATED_TODO.md` (canonical backlog, including the merged ineffective-choices audit intake)
- `docs/quality/non-regression-policy.md`
- `docs/docpacks/pack-specs.md`
- `docs/docpacks/prompt-authoring.md`
- `docs/architecture/role-boundaries.md`
- `docs/testing/integrity-rules.md`

---

## Runtime Requirements

Configuration lives in `src/config/app.yaml` with `.env` fallback for any missing values. Secrets come from environment variables.

- Contents/index detection is configured under `ingest.contents_page` (keywords, max_pages, min_headings, render_dpi).

Required environment variables:

- `OPENAI_API_KEY`
- `OPENROUTER_API_KEY` for browser-download automation
- `WP_APP_PASSWORD` (or `WP_BEARER_TOKEN` if using bearer auth)
- `GOOGLE_SERVICE_ACCOUNT_JSON` when `ingest.drive.auth_mode=service_account`
- `GOOGLE_OAUTH_CLIENT_JSON` and `GOOGLE_OAUTH_TOKEN_JSON` when `ingest.drive.auth_mode=oauth_user`
- Optional: other provider keys (e.g., `MINERU_API_KEY`), `WP_USERNAME`/`WP_SITE_URL`/`WP_POST_TYPE` if not set in YAML.

Drive auth modes:

- `service_account`: suitable for Shared Drives or service-account-readable folders.
- `oauth_user`: suitable for personal Google Drive and any workflow that must read/write as your Google user account.

---

## Troubleshooting

Start with the structured logs: every failure path logs `run_id`, `task_id`, `span_id`, `event`, and the `AppError.code`. For per-report analysis issues, also inspect `out/<report-slug>/report_analysis/` for `doc_map.json`, `artifacts.json`, `validation.json`, and any `*_regen_attempt_*.json` snapshots.

### Deterministic Replay By `run_id`

Use replay for any background UI run that already has a `run_id` in `ui_runs.sqlite`:

```bash
python -m src.cli replay-run --run-id <run_id>
python -m src.cli replay-run --run-id <run_id> --registry-path <path-to-ui_runs.sqlite>
```

Replay workflow:

- Load `state/ui_runs/<run_id>/replay_manifest.json`.
- Recompute current source-tree, prompt-tree, and sanitized config fingerprints.
- Stop early with `blocked_drift` if the code, prompts, or config no longer match the original run.
- Re-execute the original UI worker payload when the environment still matches.
- Write `state/ui_runs/<run_id>/replays/replay_report_<timestamp>.json` with field-by-field deltas for status, error fields, result summary, and artifact hashes.

Operational note:

- Replay re-runs the original UI workflow, so treat side-effecting run types such as publish or acquisition tasks as real executions. Use a non-production copy of the environment when you need a safe incident drill.

### `db_locked`

- Meaning: ingest checked SQLite DB access up front after applying WAL mode and refused to start because `state_db`, `reports_db`, or both were still locked even for the lightweight schema probe.
- Typical fix: stop the other process holding the DB, close any GUI/DB browser session, or wait for the other run to finish before starting a new ingest.
- Related code path: `src/orchestrators/ingest_orchestrator.py` raises `db_locked` before any report work begins.

### `ingest_locked`

- Meaning: another ingest run already holds the ingest lock file, so the orchestrator exits instead of running two overlapping ingests.
- Typical fix: wait for the active run to finish, or clear a stale lock only after confirming no ingest process is still active.
- Related code path: `src/orchestrators/ingest_orchestrator.py`, `src/services/lock_service.py`.

### `pdf_text_unextractable`

- Meaning: the deterministic sampled pages contained no extractable text, so the report was rejected before vector-store or artifact generation.
- Typical fix: verify the source PDF is not image-only, confirm the sampled pages are representative, or enable OCR fallback with `ingest.pdf_text.ocr_fallback.enabled=true` if scanned PDFs are expected.
- Where to look: logs include `text_extractability_checked` / `text_extractability_failed` with sampled pages and character counts.

### `pdf_text_ocr_failed`

- Meaning: OCR fallback was attempted but failed to produce a usable page-aligned OCR PDF with extractable text.
- Typical fix: confirm `OPENAI_API_KEY` is set, the configured OCR model is valid, and the source PDF can be split/read successfully. If OCR keeps failing on one file, inspect whether the PDF is corrupted or image quality is too poor.
- Related code path: `src/generators/pdf_text_ocr_generator.py`, `src/generators/report_source_generator.py`.

### `doc_map_empty`

- Meaning: the `doc_map` evidence pack came back empty or normalized into an empty payload, so analysis stops for that report.
- Typical fix: inspect `out/<report-slug>/report_analysis/doc_map.json` when present, review the logged `doc_map_empty:<reason>` message, and verify the source PDF has enough recoverable section structure after text extraction/OCR.
- Additional signal: the state DB stores `doc_map_summary_json` for these halted reports.

### Validation Failed Or Publish Blocked

- Meaning: `validation.json` did not end in `status=pass`, or publish was blocked because `publish.validation.policy=block`.
- Typical fix: inspect `out/<report-slug>/report_analysis/validation.json` first, then compare against `artifacts.json` and any `artifacts_regen_attempt_*.json` / `validation_regen_attempt_*.json` snapshots to see whether regeneration already tried to repair the failure.
- Config lever: set `publish.validation.policy=warn` only if you intentionally want publish to continue with validation issues.

### `vector_store_index_timeout` Or `vector_store_index_failed`

- Meaning: the OpenAI vector store was created and attached, but indexing never reached a ready state or returned an explicit failed status.
- Typical fix: retry the run, confirm `OPENAI_API_KEY` is present, and check whether provider-side indexing latency is temporarily high. If timeouts are recurrent, inspect the logged `last_status` and vector-store metadata in state/report DB records.
- Related code path: `src/orchestrators/report_analysis_orchestrator.py` polls `vector_store_service.get_vector_store_status(...)` under the shared retry policy and raises on timeout or failed indexing.

### OpenAI Credential Or Response Errors

- Common codes: `openai_missing_api_key`, `vector_store_missing_api_key`, `openai_client_init_failed`, `openai_response_invalid_json`, `openai_response_validation_failed`.
- Typical fix: confirm `OPENAI_API_KEY` is set in the shell that launched the process, verify the installed OpenAI client is usable in the current environment, and inspect the logged prompt/response metadata when a model returns invalid or schema-breaking JSON.
- Where it shows up: general analysis, OCR fallback, crop refinement, and vector-store operations all route through `src/services/openai_service.py`.

### Drive Auth Or Config Errors

- Common codes: `drive_sa_path_missing`, `drive_folder_id_missing`, `drive_list_failed`, `drive_metadata_failed`, `drive_download_failed`.
- Typical fix: confirm the service account JSON path exists, the target Drive folder/file ID is correct, and the service account has access to the folder or shared drive being queried.
- Where it shows up: `src/services/drive_service.py` validates these inputs before listing/downloading.

### WordPress Auth, TLS, Redirect, Or REST Errors

- Common codes: `wp_post_lookup_redirected`, `wp_post_client_error`, `wp_post_server_error`, `wp_media_client_error`, `wp_media_server_error`, plus matching taxonomy/tag lookup/create errors.
- Typical fix: confirm `WP_SITE_URL`, `WP_USERNAME`, and `WP_APP_PASSWORD` or `WP_BEARER_TOKEN` are correct; ensure the site is serving the expected REST root without redirect loops; and fix the server certificate chain before relying on `publish.wp.ssl_verify=false`.
- TLS-specific controls: `WP_SSL_VERIFY` and `WP_CA_BUNDLE_PATH` are honored by the shell/Python provisioning scripts and override `publish.wp.ssl_verify` / `publish.wp.ca_bundle_path` for the Python publish path.
- Extra signal: WordPress 5xx and redirect failures log bounded response headers/body excerpts to make REST misroutes and hosting issues visible.

### Smoke Test Skipped

- Meaning: `Wordpress/scripts/smoke-test.sh` exits successfully with a skip message when `wp-cli` is not available.
- Typical fix: install `wp-cli`, point `WP_CLI_BIN` at it if needed, and set `WP_PATH` when the target WordPress runtime is not the current directory.
- CI note: the optional live smoke test only runs when `RUN_WORDPRESS_SMOKE=1` and `wp-cli` is available.

### Report Payload Or Artifact Contract Incomplete

- Common codes: `report_payload_incomplete`, `artifact_contract_incomplete`, `artifact_inputs_unavailable`.
- Meaning: the pipeline produced a semantically incomplete payload or artifact even after normalization/regeneration safeguards.
- Typical fix: inspect `artifacts.json`, `validation.json`, and the logs around the failing stage to identify which required fields were empty or degraded to sentinel text such as `not available from text`.

---

## CLI Usage

Primary entrypoint (defaults to `ingest` if no subcommand):

```bash
python -m src.cli ingest --limit 10
```

Publish generated HTML to WordPress:

```bash
python -m src.cli publish-wp --limit 10
```

Re-score categories for all stored reports (updates DB category assignments):

```bash
python -m src.cli recategorize
```

Update WordPress categories for already-published posts to match the latest mappings/DB:

```bash
python -m src.cli update-wp-categories
```

Summarize LLM spend by date or run (using `cost_ledger_path` + `cost_daily_path` from config):

```bash
python -m src.cli cost-report --date YYYY-MM-DD
python -m src.cli cost-report --run-id <run_id>
```

`cost-report` is routed through `src/orchestrators/cost_reporting_orchestrator.py`, which centralizes filtered report generation and daily rollup orchestration.

Download a report from a landing page with the local vendored `browser-use` runtime:

```bash
python -m src.cli download-report https://example.com/report
python -m src.cli download-report https://example.com/report --delivery-email analyst@example.com
```

`download-report` is routed through `src/orchestrators/report_download_orchestrator.py`. It looks up a remembered route in `reports_db.publishers` by matching the requested URL to `publishers.insights_url`, tries that route first when available, now passes both the remembered route summary and remembered structured route steps into the browser prompt, short-circuits stable remembered on-site extract routes through direct HTML capture when that is sufficient, falls back to fresh discovery only after explicitly retryable remembered-route failures, rejects obvious non-report candidates before browser spend, and returns one of four outcomes: `downloaded`, `email_requested`, `email_required`, or `captured`.

The browser-download service now rejects weak remembered route summaries before they are stored for reuse, requires real delivery confirmation evidence before classifying an email-gated run as `email_requested`, filters obvious non-field controls out of browser identity auto-upserts, records blocker and terminal evidence in route history, and cross-checks PDF signature plus MIME/extension metadata before reporting `downloaded`. Confirmation scoring now accepts generic success states such as visible thank-you text only when combined with another independent browser signal, and routed form-heavy report pages are no longer forced into `browser_onsite_report` when the browser evidence clearly shows an email gate. When a site opens a PDF viewer wrapper instead of writing the real PDF bytes directly, the service fetches the embedded real PDF and replaces the wrapper file before reporting success; when the artifact is actually a blocked form or an on-site longread, the service can now recover that terminal state instead of forcing a fake PDF success. Browser-download HTTP probes and direct artifact fetches now run through `src/services/_http_acquisition.py`, which reuses pooled per-host sessions, applies bounded response policies, and preserves typed route-specific failures in the acquisition logs. Failed report-download attempts now also emit a typed forensic pack JSON under the per-URL browser download root, carrying the failing route-plan step, classified error metadata, bounded terminal evidence, and either copied or metadata-only artifact references according to `browser_download.failure_forensics.policy`.

For on-site report routes, finalization also recovers browser agent results that reference a missing relative capture artifact by fetching the verified terminal HTML URL, validating it as report-like HTML, and materializing the capture before strict route classification.

Discover the current publisher insights inventory, compare it to the last Drive-backed snapshot, and print only new report links:

```bash
python -m src.cli discover-publisher-inventory https://example.com/insights
```

`discover-publisher-inventory` is routed through `src/orchestrators/publisher_inventory_orchestrator.py`. It resolves the publisher by `publishers.insights_url`, reuses remembered inventory route memory when available, preferring typed route traces and scenario summaries over the legacy prose summary, falls back only when that remembered route fails with an explicitly retryable `AppError`, traverses paginated insights sections across all reachable pages, normalizes the combined inventory, and compares it with the latest snapshot stored in that publisher's Google Drive folder. Route ordering is now planned explicitly in `src/orchestrators/_publisher_inventory_orchestrator/route_planner.py`, and the public orchestrator delegates private helper ownership to `_publisher_inventory_orchestrator/dependencies.py`, `idempotency.py`, `snapshot_io.py`, `snapshot_records.py`, `candidate_flow.py`, and `runtime.py` without adding a second workflow entrypoint; `snapshot_records.py` owns the real snapshot-upload and `report_sources` side effects after candidate qualification. The canonical publisher inventory service delegates HTTP and browser acquisition into `src/services/_publisher_inventory_service/fetch_service.py` and `src/services/_publisher_inventory_service/browser_service.py`, and the run persists both an explicit coverage verdict and a reusable run-quality summary for future route selection and drift review. Publisher-inventory traces remain SQLite/KPI memory rather than YAML playbooks because they describe archive traversal scenarios, not terminal report-acquisition actions; promotion to `src/playbooks/browser_routes/` is intentionally limited to verified report-download browser routes with terminal evidence. The canonical public service boundary remains `src/services/publisher_inventory_service.py`, while pure navigation-control and candidate-extraction heuristics now live in `src/services/_publisher_inventory_service/discovery_activity.py`, browser DOM script builders now live in `src/services/_publisher_inventory_service/browser_scripts.py`, and typed traversal-state/metric helpers now live in `src/services/_publisher_inventory_service/browser_traversal_state.py` so the public service module stays focused on external I/O and browser/runtime coordination. `src/services/_publisher_inventory_service/workflow.py` remains the internal coordinator and compatibility surface; deterministic preflight scenario classification lives in `preflight.py`, and deterministic browser traversal, rendered-HTML supplement extraction, interaction waits, and browser-route HTTP supplement recovery live in `browser_flow.py`. Direct PDF insights URLs are treated as a single-item inventory source without entering the browser crawler. High-confidence direct-detail HTML pages can now also short-circuit before archive traversal, even when `publisher_discovery.force_browser=true`; normal JS-heavy, tabbed, and filter-driven archives remain browser-led. The direct HTTP parser now scores each extracted candidate before accepting the `http_parse` route, drops low-confidence weak matches, tags accepted candidates with `http_parse` provenance, stops pagination when a repeated anchor fingerprint shows the crawl is looping through duplicate content, recovers report cards from custom web-component payloads such as `link="{...href...}"` plus `teaserHeader="{...headline...}"` when a publisher renders zero visible `<a>` tags in the raw HTML, and can also recover WordPress resource archives that populate cards only through `wp-admin/admin-ajax.php` by detecting the page's AJAX config and replaying the matching archive action directly. Publisher-inventory preflight probes, HTTP page fetches, supplement fetches, and WordPress AJAX/script fetches now share `src/services/_http_acquisition.py`, which pools per-host sessions and applies bounded response capture before the discovery logic inspects the results. The browser route itself uses deterministic rendered-DOM traversal instead of relying on free-text LLM extraction: it waits for the page to hydrate, dismisses cookie banners by clicking only inside visible cookie/consent containers instead of generic page-wide buttons, performs a deterministic feed-hydration scroll before each extraction pass, primes the page before the first archive-state read so below-the-fold tabs and pagers are visible, treats smaller archives with a few substantial card links as real inventory surfaces instead of requiring 12+ visible anchors, expands generic archive-preview CTAs such as `View all`, `Explore all library entries`, and similar archive/library buttons when the publisher first lands on a truncated preview instead of the full archive, closes stray `about:blank` / new-tab placeholder windows opened by the local browser runtime so they cannot steal focus and freeze discovery, resets empty result sets when a page exposes generic `Reset all filters` / `Clear filters` controls, expands `Load more` pagination (including anchor-styled controls like Bain’s `a.btn` CTA), treats same-page DOM growth after a load-more click as real pagination progress even when the URL does not change, ignores duplicate same-URL load-more states when the candidate set has stopped changing so inert end-of-feed states do not churn snapshots, prefers the `Load more` control attached to the currently extracted candidate surface when a page exposes multiple unrelated result areas (for example Algolia), stops following generic `Show more` controls once they are no longer attached to the report inventory surface, clicks button-based pagers like Adobe’s bottom `Prev/Next` control, also recognizes simpler `Page X of Y` plus `Next` pagination patterns when numeric chips are absent, stops cleanly when visible result ranges show the final page (for example `190 - 194 of 194 results`), iterates report-focused tab groups generically when a publisher exposes tabs such as `Research` / `Reports` / `White papers`, only auto-follows a discovered "report listing" route when that route itself still looks like an archive/listing URL rather than a single detail page, accepts archive-card links on real archive surfaces even when the destination host differs from the publisher apex if the card itself is clearly report-like, resolves relative links back to the original insights host when the browser runtime drifts onto a mirrored host, prefers explicit on-page report filters when a publisher exposes them (for example GfK), guards against archive drift by navigating back to the requested archive when the browser lands on a single detail page instead of the inventory surface, falls back to parsing the browser's rendered HTML when visible-anchor extraction returns nothing, now also treats a browser result that only rediscovers the archive root itself as structurally empty so HTTP supplement/recovery can still run, mines those rendered HTML component payloads when the supplement contains structured `link` and headline attributes instead of anchor tags, retries the original requested URL once when the browser drifts onto a different apex host before inventory extraction succeeds, falls back to direct HTTP parsing when the browser route fails with a retryable timeout or runtime error, still falls back to HTTP when the pagination cap is hit immediately, but now treats multi-page archives that already produced real candidates as bounded browser successes instead of hard failures, and tags returned candidates with route provenance such as `browser_dom`, `browser_rendered_html_supplement`, `http_supplement`, or `http_parse_wordpress_ajax` so the completion logs show how each run was actually sourced. Candidate title extraction is also biased toward card headings when a whole card's text includes author/date/read-more chrome, and it now falls back to surrounding card text for generic CTA-only links like `Read now` / `Learn more`, which keeps `report_sources.report_name` closer to the actual asset title on card layouts that do not use semantic heading tags. The direct HTTP parser now treats a structurally empty report set as a non-retryable `publisher_inventory_http_empty` outcome so the orchestrator can move on to the stronger browser route without wasting retry budget. The default `publisher_discovery.pagination_max_pages` is now `75`, and the default browser traversal timeout is now `360` seconds, which is enough for deeper real report archives such as Quid while still keeping a bounded crawl. The diff output includes the inventory page number where each new report link was found. Before any new diff item is written into `paths.reports_db` table `report_sources`, it first passes OpenAI candidate screening from `publisher_discovery.candidate_screening`, then a deterministic landing-page quality check from `publisher_discovery.candidate_quality_check`. The default base screening model is `gpt-5-nano` with the default `temperature: 1.0`; dynamic screening now targets fewer, larger batches on deep archives, caps those dynamic batches at `35` items, truncates long titles in the prompt to keep token growth bounded, deterministically rejects obvious academy/support/webinar/video/training/editorial collection URLs before any LLM call, rejects collection-root hub URLs such as bare research/archive landings before they can crowd out real detail assets, deterministically accepts obvious report-detail URLs such as deep `/reports/`, `/whitepaper/`, `/ebooks/`, `/guide/`, `/fact-sheet/`, `/report_pages/`, strong direct-detail source URLs, and slugged report-style leaf URLs like `...-report` or `...-atlas`, treats query-string document URLs by their resolved path rather than raw string suffix alone, preserves strong editorial report-detail pages on mixed-content hubs when the path and title both indicate a real report asset, and no longer collapses distinct same-run assets just because multiple cards reuse generic CTA titles such as `Download the report` or `Learn more`. The screening prompt rejects publisher self-congratulatory accolade pieces such as "named a Leader" / "top rated" analyst-marketing pages, the screening generator applies a deterministic hard rejection for obvious publisher-success marketing titles even if the model accepts them, including medal/award style variants, collapses duplicate same-run candidates so repeated promoted tiles are queued only once, and repairs missing per-candidate LLM decisions in bounded single-item follow-up calls so large inventories do not hang or fail when the model omits one URL from a batch. The landing-page quality check then fetches the approved destinations in parallel and keeps only substantial report-like assets: direct PDFs, gated report pages, paid/publication report pages, printable long-form report pages, structured infographic/snapshot-style report pages under real report archives, slug-signaled ebook/report/guide/fact-sheet detail pages that expose real asset terms without editorial framing, dedicated report/research/whitepaper/ebook/benchmark/study/outlook/playbook pages with real document structure, and the stronger mixed-content editorial detail pages now rescued by the screening layer. It now also tolerates three bounded non-dead verification failures for already screened report-like assets: anti-bot challenge pages such as `Security Checkpoint`, transient fetch timeouts or transient HTTP statuses such as `429` on real report pages, and protected `403` responses on direct documents or report-like landing pages that still carry strong report signals; but those recovery paths no longer rescue obvious case-study or customer-story URLs, and they still reject bot-protected pages whose source title is explicitly article-labeled. It rejects dead links, missing pages, generic blog/news/article/expert-view templates whose only positive signal is a generic `report` label, informational `how to` / `what is` pages that only look report-like because they mention `reporting`, case-study or customer-story pages, legal practice-area guides, report microsite section pages such as `Conclusion`, `Executive summary`, or nested report child URLs like `/.../innovation`, research-announcement pages that only summarize a study without exposing the asset itself, generic finance/editorial section routes such as `/company-insights/`, `/market-insights/`, `/market-outlook/`, `/markets-explained/`, generic podcast/webcast/roundtable-style editorial pages even when their titles include report-like words, consumer self-service credit/report product pages that look like downloadable assets only because they advertise gated report access, and generic newsletter/contact-sales pages, and it does not let generic commercial or purchase signals rescue those editorial, self-service, or case-study routes unless the page also looks like a real report asset. It upgrades weak tile titles such as `Download report` or `Learn more` from the landing page H1 or document title before persisting the candidate. Transparency reports are no longer treated as compliance pages purely because of that phrase, so substantive report assets such as tax or PRI transparency reports can survive qualification when the rest of the page looks like a real document flow. Snapshot state is also protected against raw browser drift: if a rerun changes the raw snapshot but every raw-only delta candidate is rejected before qualification, or every screened delta candidate dies in landing-page verification while an earlier canonical snapshot already exists, the orchestrator keeps the previous snapshot canonical instead of overwriting it with noise; and on first-run archives that produce raw candidates but no qualified report assets, the run is recorded as `passed:no_report_assets` without uploading a noisy snapshot or queueing `report_sources`. The April 9, 2026 live gate confirmed the validated behavior on three distinct publishers: Capgemini as a direct-detail short-circuit success, Bain as a filter-heavy archive success, and Cardlytics as a mixed-content qualified-asset success with a stable remembered-route rerun.

Audit current publisher acquisition paths with one batch run:

```bash
python -m src.cli audit-acquisition-paths --publisher-limit 5 --candidate-limit-per-publisher 10
python -m src.cli audit-acquisition-paths --delivery-email analyst@example.com
```

`audit-acquisition-paths` is routed through `src/orchestrators/acquisition_audit_orchestrator.py`. It lists the current publishers from `paths.reports_db`, runs the existing publisher-inventory discovery flow for each publisher to refresh current candidate inventory plus discovery provenance, audits each current candidate with the existing `download-report` flow against an isolated per-run audit database, and writes one JSON artifact under `out/acquisition_audit/<timestamp>/acquisition_audit.json`. The artifact contains both publisher-level and candidate-level acquisition maps, including discovery provenance, observed acquisition route/outcome, and recommended future flow per publisher/report.

On Windows, the vendored `browser-use` local browser watchdog now launches Chromium with `stdout/stderr` redirected to `DEVNULL` instead of `PIPE`. The discovery/download flows control the browser over CDP and never consume browser stdio, so this avoids `_ProactorBasePipeTransport.__del__` shutdown noise and unclosed transport leaks after headed runs.

The vendored local browser watchdog now also waits for forced `BrowserStopEvent` shutdown to finish its `BrowserKillEvent` cleanup before the event bus is torn down, and its Windows cleanup path terminates the full Chrome subprocess tree instead of only the launcher PID. This prevents repo-owned `chrome.exe` children using `browser-use-user-data-dir-*` temp profiles from surviving after discovery/download runs.

Snapshot behavior:

- `publishers.google_folder` is required; the command fails explicitly when it is missing.
- The latest snapshot index and remembered extraction route summary are stored on the `publishers` row in `reports_db`.
- The `publishers.inventory_run_quality_json` and `publishers.inventory_run_quality_updated_at` columns store the latest reusable run-quality summary, including outcome, quality band, review flag, and recommended next route.
- The `publishers.discovery_test_status` column stores the latest known discovery-check outcome for that publisher, using values like `passed` or `failed:<error_code>`.
- Snapshot artifacts are uploaded as immutable JSON files named like `publisher_inventory_snapshot__YYYYMMDDTHHMMSSZ.json` inside the publisher folder.
- If the normalized snapshot hash matches the previous snapshot hash, no new snapshot file is uploaded and the diff is empty.
- Snapshot payloads record the traversed page list and each item's `discovered_on_page_number`.
- New diff items are upserted into `report_sources` by normalized landing URL with `source_status='discovered'`; when the browser-download flow later succeeds for the same URL, that row is upgraded in place instead of creating a duplicate source record.

Run the one-time local browser consent flow for personal Google Drive OAuth and store the refreshable token JSON:

```bash
python -m src.cli drive-oauth-login --client-json ./google_oauth_client.json --token-json ./google_oauth_token.json
```

`drive-oauth-login` is routed through `src/services/drive_service.py`. It uses the standard installed-app OAuth flow, opens the local browser, and writes an authorized-user token JSON that the Drive service can later refresh headlessly.

`google_oauth_client.json` and `google_oauth_token.json` are local secret material. Keep them in the repo root only for local development and do not commit them; `.gitignore` excludes both files by default.

Sync publisher/source metadata from the checked-in Notion snapshot into the reports database:

```bash
python -m src.cli sync-publishers
python -m src.cli sync-publishers --snapshot-path .\\Wordpress\\config\\publisher-profiles.json
```

`sync-publishers` is routed through `src/orchestrators/publisher_sync_orchestrator.py`. It validates the snapshot JSON, then replaces the `publishers` table inside `paths.reports_db` with the validated rows.

Extract chart/table candidates without running LLM analysis (writes JSON + crops):

```bash
python -m src.cli extract-candidates --limit 10
python -m src.cli extract-candidates --file-id <drive_file_id>
python -m src.cli extract-candidates --pdf "C:\\path\\report.pdf"
```

Vector-store ingest is the default mode. This reuses existing vector stores when `VECTOR_STORE_KEEP=true`, otherwise creates/attaches/waits per file and writes packs to `out/<report-slug>/report_analysis/`.

CLI options summary:

- `--limit`: optional integer across batch commands.
- `--folder`: optional Drive folder override for ingest.

### Publisher Discovery Config

Publisher inventory discovery is configured under `publisher_discovery` in `src/config/app.yaml`.

Supported keys:

- `model`, `temperature`, `timeout_seconds`, `max_steps`, `headed`
- `force_browser`
- `enable_deferred_candidate_recovery`
- `enable_structured_route_reuse`
- `enable_preflight_classifier_and_direct_detail`
- `prompt_namespace`
- `output_dir`
- `pagination_max_pages`
- `http_timeout_seconds`
- `command_time_budget_seconds`
- `retry.retries`, `retry.base_delay_seconds`, `retry.backoff_step_seconds`, `retry.jitter_seconds`

Any omitted browser settings fall back to the existing `browser_download` section so the discovery flow can share the same OpenRouter/browser defaults without duplicating mandatory configuration.

Browser-render inventory traversal now adapts the browser-harness nested-scroll practice inside the existing publisher inventory browser scripts: each extraction pass still begins with the document hydration scroll, then probes bounded nested and virtualized scroll containers, records the consumed scroll surface in `PublisherInventoryRouteTrace.scroll_surface`, records whether candidate anchors changed, and stops on stable DOM/candidate fingerprints instead of looping through inert virtualized feeds.

Publisher inventory state now persists both the legacy free-text route summary and two typed memory payloads on the `publishers` row:

- `inventory_route_trace_json`
- `inventory_scenario_summary_json`

A dedicated `publisher_inventory_candidate_recovery_cache` table also stores deferred recovery outcomes for challenge/protected/transient candidate failures keyed by normalized publisher URL plus canonical candidate URL.

Publisher insights URLs are persisted with a normalized lookup key in `reports_db.publishers.normalized_insights_url`. The column is backfilled during metadata DB schema migration, indexed with `idx_publishers_normalized_insights_url`, and used for publisher route, inventory, and Drive-folder lookups so duplicate normalized URLs resolve deterministically to the lowest publisher row id.

Discovery run-quality outcomes are also appended to `publisher_inventory_route_history`. `get_publisher_inventory_state` derives ranked host-level `inventory_route_policy` signals from that history so cold sibling publisher URLs can start with the route kind that has already succeeded for the same host, while still falling back on retryable errors.

The three rollout flags now default to `true` in `src/config/app.yaml`:

- `enable_deferred_candidate_recovery`
- `enable_structured_route_reuse`
- `enable_preflight_classifier_and_direct_detail`

That default is deliberate and is validated by the April 9, 2026 live gate on Capgemini, Bain, and Cardlytics.

Rollout guardrails are emitted on every publisher run via `publisher_inventory_rollout_guardrails_evaluated`. The canary sequence is `Capgemini direct-detail -> Bain filtered archive -> Cardlytics mixed-content hub -> remembered-route rerun`, then a 10-publisher mixed batch before broad operation. Required KPIs are: coverage verdict not `undercoverage_regression` or `unreachable_delta_failure`; `qualified_new_report_count <= screened_new_report_count <= raw_new_report_count`; run-quality `requires_review=false`; stable `scenario_class` and `candidate_provenance_counts`; and deferred-recovery volume reviewed when scheduled. Roll back by disabling the three rollout flags, or by setting `publisher_discovery.force_browser=true` for a publisher cohort, whenever the guardrail log reports `kpi_guardrail_status="review_required"` on representative canaries or false-positive review finds broadened generic blog/article acceptance.

When `publisher_discovery.force_browser=true`, normal archive discovery still stays browser-led. The validated exception is that direct PDF and high-confidence direct-detail HTML scenarios can short-circuit before browser traversal, while JS-heavy, tabbed, or filter-driven archives continue to use the visible headed browser route.

`publisher_discovery.command_time_budget_seconds` is the hard per-publisher workflow budget. The orchestrator trims downstream discovery/screening/quality timeouts to the remaining budget and fails explicitly when that budget is exhausted, so long-running archives persist a typed discovery status instead of hanging until an external shell timeout.

### Drive Auth Config

Drive access is configured under `ingest.drive` in `src/config/app.yaml`.

Supported keys:

- `auth_mode`: `service_account` or `oauth_user`
- `oauth_client_path`
- `oauth_token_path`
- `supports_all_drives`
- `include_items_from_all_drives`
- `drive_id`
- `list_mode`

For personal Google Drive, set:

```yaml
ingest:
  drive:
    auth_mode: "oauth_user"
    oauth_client_path: "./google_oauth_client.json"
    oauth_token_path: "./google_oauth_token.json"
```

In `oauth_user` mode, the Drive service reads and refreshes the authorized-user token JSON automatically for list/download/upload calls. In `service_account` mode, it continues to use `ingest.google_sa_path`.

## Streamlit Cockpit

The repository includes a Streamlit control panel aligned to `GUI-ARCHITECTURE.md`.
The entrypoint is thin and the UI is now split into grouped multi-page surfaces plus a persisted run-control layer:

- `src/streamlit_app.py`: entrypoint only, grouped `st.navigation(...)`, runtime state bootstrap, theme load.
- `src/ui/app_pages/`: bounded page modules for overview, core operations, publisher operations, QA, strategy outputs, observability, and configuration.
- `src/ui/streamlit_pages.py`: compatibility facade for legacy imports; page-owned helpers live in neutral modules so page owners do not import the facade.
- `src/ui/_streamlit_pages/`: shared Streamlit runtime/read-model/structured-config helpers used across page families without reintroducing one page-owner monolith.
- `src/ui/settings_page.py`: config studio for `app.yaml`, operational YAML/JSON assets, prompt files, and auth/source status.
- `src/ui/run_control.py`: Streamlit-facing helpers for launching, polling, listing, canceling, and retrying persisted UI runs.
- `src/orchestrators/ui_run_control_orchestrator.py`: background run orchestration over local worker processes plus registry persistence.
- `src/services/process_service.py`: canonical local-process boundary for launch/poll/output/terminate.
- `src/services/run_registry_service.py`: SQLite-backed run registry persisted beside the state DB. The same registry now also maintains a typed dead-letter ledger plus action history for failed background runs, including triage category, inferred stage, publisher/report identity hints, and last artifact links.
- `src/services/config_asset_service.py`: canonical YAML/JSON/text asset editor boundary with validation and optional backups.
- `src/generators/streamlit_dashboard_generator.py`: read-model assembly for dashboard/log/storage views.

Run locally:

```bash
streamlit run src/streamlit_app.py
```

Grouped sidebar navigation:

- `Overview`: Cockpit Overview, Run Center
- `Core operations`: Ingest Control, Candidate Extraction, Cover Images, Publishing & Taxonomy
- `Publisher operations`: Publisher Discovery, Report Download Lab, Acquisition Audit, Publisher Sync, Auth & External Access
- `Content QA`: Report Command Center, Analysis & Evidence, Validation Center
- `Strategy outputs`: Strategy Outputs
- `Observability`: Cost & Usage, Logs & Live Events, System & Storage, Developer & Test Tools
- `Configuration`: Settings & Prompts

The Streamlit cockpit is an operator/admin surface. It manages Sources, Runs, Validation, Publishing Queue, Cost, configuration, and operational diagnostics; it is not the canonical public navigation model used by the WordPress portal.

Design and behavior highlights:

- Long-running workflows launched from Streamlit now run through the persisted UI run registry instead of blocking the browser session inline. The Run Center can inspect, cancel, retry, and discard tracked jobs, and failed runs auto-enter a dead-letter workflow with typed triage categories instead of remaining ambiguous `failed` rows.
- The overview and Run Center now use card-based dashboard composition with bordered KPI rows, tighter run/history tables, selected-run context that carries into observability pages, and dead-letter backlog plus age-trend views for operator triage.
- Workflow coverage now includes publisher discovery, report download, acquisition audit, publisher sync, and Drive OAuth/auth visibility in addition to ingest, candidate extraction, cover generation, publish, taxonomy, QA, and observability pages.
- Strategy Outputs compares codebase capabilities against Streamlit coverage and adds guided controls, charts, and indicators for cross-report Briefings, durable Signal candidates, Signal post workflows, and UI-run replay.
- The configuration surface now covers `app.yaml`, category mappings, cover styles, browser download identity, publisher snapshot JSON, and prompt YAML files through service-backed editors with validation, diff visibility, and optional backups.
- The config studio defaults to four task-oriented workspaces: `Common`, `Assets`, `Prompts`, and `Advanced`, so routine operator changes no longer open on the raw YAML editor by default.
- Selected run IDs now flow into observability surfaces such as cost and log filters, and selected report IDs persist across the report/analysis pages.
- Native theming now lives in `.streamlit/config.toml`; injected CSS is limited to a small set of component-level helpers such as status chips, panels, steppers, and the terminal surface.
- If runtime config validation fails, the UI still opens directly into **Settings & Prompts** so `app.yaml` can be fixed without leaving Streamlit.

## Output Layout

Default output structure:

```text
./out/
  <report-name>.html
  <report-name>/
    assets/
      <report-name>.png
    slices/
      <report-name>.png
      <report-name>1.png
    candidates/
      <report-name>.png
      <report-name>1.png
    thumbs/
      <report-name>.png
  candidates/
    <report_id>/
      candidates.json
  <report-name>/
    report_analysis/
      doc_map.json
      scope.json
      methods.json
      findings.json
      limitations.json
      quote_candidates.json
      key_metrics.json                  # optional (flagged)
      risk_register.json                # optional (flagged)
      recommendations.json              # optional (flagged)
      contradictions.json               # optional (flagged)
      artifacts.json
      figure_captions.json
      artifacts_regen_attempt_1.json   # optional, latest-attempt snapshot naming pattern
      validation.json
      validation_regen_attempt_1.json  # optional, latest-attempt snapshot naming pattern
```

---

## Migration Notes

Marker-based PDF-to-HTML conversion has been removed.

---

## Support and Extension Points

To extend the system:

- Add new services in `src/services` and define contracts in `src/contracts`.
- Add new prompts in `src/prompts/<use_case>/`.
- Add new generators to compose services into outputs.
- Add orchestrators for new pipelines or batch flows as needed.

---

## Security and Compliance

- Secrets must not be committed to source control.
- Use `.env` locally and environment variables in CI/CD.
- Prompt logs are structured and should be routed to secure logging sinks in production.

---

## Vector Store & Cost Tracking Highlights

- OpenAI boundary: only the canonical `src/services/openai_service.py` facade exposes provider operations; client/cache/metadata, chat/analyze, response/OCR, and vector-store operation families live under `src/services/_openai_service/*`. Usage accounting is emitted as a typed `OpenAIUsageAccountingRequest` and persisted through `src/services/openai_accounting_service.py`, keeping cost-ledger side effects outside the provider client boundary. Vector-store create/upload/attach/status/update operations also share one internal scaffolding path for client init, structured service logs, and typed provider-error mapping while preserving explicit request/response contracts per operation.
- Vector stores: `src/services/vector_store_service.py` handles create/upload/attach/status/delete/prune lifecycle operations and metadata shaping, delegating provider API calls to `openai_service`; used by vector-mode generators and retention cleanup.
- Analysis uses vector_store only; `ANALYSIS_MODE`/`USE_VECTOR_STORE` toggles are no longer needed.
- Evidence packs: `src/generators/evidence_pack_generator.py` is the entrypoint, and `src/generators/evidence_packs/*.py` contains the per-pack strategy modules used for pack metadata and normalization. Packs use `src/prompts/report_vs/**` and write JSON to `out/<report-slug>/report_analysis/*.json`; `doc_map` runs first and remaining packs run in parallel with process-wide rate limiting via `ingest.evidence_packs.*`. Validation uses strict per-pack schemas (`scope_pack`, `methods_pack`, `findings_pack`, `limitations_pack`, `quote_candidates_pack`) plus optional variety-pack schemas (`key_metrics_pack`, `risk_register_pack`, `recommendations_pack`, `contradictions_pack`).
- Analysis-pack persistence: `src/services/report_analysis_store_service.py` validates schema-backed packs before writing them to disk. Packs without a registered schema still persist normally, while invalid schema-backed payloads fail fast and are not written.
- Artifacts: `src/generators/artifact_generator.py` writes `artifacts.json` under the same analysis path, parallelizing independent steps with dependency ordering and process-wide rate limiting via `ingest.artifacts.*`.
- Cost ledger: `src/services/cost_ledger_service.py` appends JSONL entries for every LLM call and writes daily rollups (`./out/cost-ledger.jsonl`, `./out/cost-daily.json`) using per-model pricing from `src/config/llm-costs.yaml` or the configured `cost.pricing_path`. Daily rollups cache ledger file state in `cost-daily.json` so normal append-only writes update aggregates incrementally, while rewritten/amended ledgers fall back to a full rebuild.


## Pipeline Review Notes

- Discovery/download quality review (2026-03-30): `docs/quality/report-discovery-download-review-2026-03-30.md`.
- Download success playbook (2026-04-07): `docs/quality/report-download-success-playbook-2026-04-07.md`.
