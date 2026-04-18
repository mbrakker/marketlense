# Market Lense

Enterprise PDF ingestion and analysis pipeline that converts Google Drive reports into structured HTML digests using an LLM and extraction heuristics.

---

## Executive Summary

Market Lense ingests PDFs from a configured Google Drive folder, extracts text and structured visual candidates (tables/charts), calls an LLM for a strict JSON analysis, ranks and crops key visuals, renders a compact HTML digest, and can publish the digest to WordPress. The system is organized around a strict architecture with contracts, services, generators, and orchestrators to ensure reliability, observability, and testability.

Key traits:

- Contract-first data model for all external I/O boundaries.
- Service isolation for all external systems and file I/O.
- Generator logic that composes services into domain outputs.
- Orchestrator that controls sequencing, retries, and state (including publishing).
- Structured logging with run/task/span identifiers.
- Built-in validation: semantic checks plus LLM grounding with persisted reports and publish-time policy controls.
- Validation-driven targeted regeneration: after a failed validation pass, the analysis orchestrator can regenerate only the mapped failing artifact families, re-run validation, and keep the latest canonical `validation.json` for downstream render/publish policy.
- Text extractability gate: before analysis, the pipeline samples deterministic pages and aborts early with `pdf_text_unextractable` when none contain extractable text.
- OCR fallback for scanned PDFs: when the native extractability gate returns `pdf_text_unextractable` and `ingest.pdf_text.ocr_fallback.enabled=true`, the pipeline sends page-aligned PDF chunks to the OpenAI Responses API with `gpt-5-mini`, enforces structured JSON page output, renders a page-aligned text-only OCR PDF, and resumes ingestion against that OCR PDF. Visual previews, contents-page screenshots, candidate extraction, and crop/render steps still use the original cached PDF; text extraction, vector-store upload, and text-grounded analysis switch to the OCR PDF. Previously skipped `pdf_text_unextractable` rows remain skipped unless state is cleaned manually.
- DocMap validation gate: if the doc_map evidence pack is empty (no sections/title/doc_id/summary), processing halts for that PDF; the orchestrator logs a detailed summary and stores it in the state DB.
- Cached execution: PDF info/contents/text extraction are cached by md5, and analysis outputs (evidence packs, artifacts, validation, HTML, crop-refine decisions) are cached by md5 + prompt/template hashes to skip redundant work.
- Cached analysis packs are schema-validated again on cache hits before reuse, so stale evidence/artifact/validation payloads are treated as misses instead of being served forward.
- Batched state prefilter: Drive-list skip checks for `(file_id, md5)` are grouped into batch SQLite queries to reduce per-file DB round trips; per-file state checks run only when the final resolved md5 differs from the Drive md5.
- SQLite metadata/state stores use WAL mode with connection-local busy timeouts, and ingest access checks now use a lightweight schema probe so readers do not escalate to write locks while another WAL writer is active.
- Low-text resilience: text density heuristics detect PDFs with little/no extractable text and emit explicit "not available from text" artifacts + HTML notices instead of blank sections.
- Artifact reference robustness: artifact evidence IDs are canonicalized against docpacks before validation (supports comma/list-like model output and quote aliases such as `quote_1 -> q1`), preventing TL;DR/insights/quotes dropouts caused by malformed IDs.
- Deterministic TOC structure: artifacts now include authoritative `toc_entries`, built directly from eligible `doc_map.sections` in source order. Legacy `toc_topics` and `toc_topics_expanded` are compatibility projections derived from `toc_entries`, and HTML renders the Covered topics section from those deterministic entries.
- TOC integrity guard: validation now enforces one-to-one coverage between eligible DocMap sections and generated TOC structure, flags missing/duplicate/stale/out-of-order entries with machine-readable repair metadata, and targeted regeneration rebuilds `toc_entries`, `toc_topics`, and `toc_topics_expanded` deterministically from DocMap without another model call.
- HTML digest quality: rendered HTML now uses semantic sections (`header/main/section`), premium split hero layout, sticky glass navigation with scrollspy + reading progress, reveal animations (with reduced-motion fallback), signal-style insight cards, editorial quote cards, and long-text chunking for generated prose.
- HTML digests now keep report-derived metadata when the reports DB has gaps, show a compact report-identity line in the hero, emit an explicit missing-source note when no source URL was extracted, and group generated expert/social copy into a trailing appendix section.
- Figure UX: rendered digests now include a template-native figure carousel with prev/next controls, keyboard and swipe support, thumbnail rail, slide counter, and fullscreen lightbox.
- Per-image figure captioning: after artifacts are generated, the pipeline can run a fail-open multimodal captioning pass for each final cropped figure asset using the image plus compact report context (`title/publisher/region/time period`, TL;DR + executive summary, nearest DocMap section, top findings/claim-evidence highlights, and figure-local signals). Captions are stored per slide, rendered in the carousel, and audited in `report_analysis/figure_captions.json`; on failure the pipeline keeps rendering with legacy/detected/placeholder fallback captions.
- OpenAI image-call compatibility: crop-refine image requests to the Responses API now omit known unsupported params (e.g., `temperature`/`seed` on `gpt-5*`) preflight and still retain fallback retry-without-param handling for unknown model/param mismatches.
- OpenAI service consolidation: `src/services/openai_service.py` is the single OpenAI client boundary (request/response parsing, shared response-metadata adaptation, cost ledger writes, and provider error normalization). Other modules route OpenAI calls through it.
- Shared LLM orchestration: `src/services/llm_service.py` wraps model-call clients with one retry/backoff/circuit-breaker API plus optional scope-level rate limiting. Report-pipeline evidence/artifact clients and default generator LLM clients now use this shared wrapper instead of local pass-through retry wrappers.
- Local browser-download automation: `src/services/browser_report_download_service.py` remains the single public browser-download service boundary, while action-specific internals now live under `src/services/_browser_report_download/` for request preparation, prompt rendering, browser runtime execution, HTTP PDF recovery, and artifact adaptation. The download orchestrator now reuses discovery/diff candidate evidence from `PublisherInventoryCandidateTrace` instead of re-planning from the candidate URL alone: candidate `pdf_url` values are probed before browser-use, source-page hints and provenance labels are passed into the browser prompt, and browser-use only runs when discovery-aware HTTP probing cannot verify a PDF. Browser prompts are now tailored per route family (`browser_pdf_click`, `browser_email_form`, `browser_tracker_redirect`, `browser_listing_hub`, `browser_onsite_report`) so the browser agent gets different instructions for CTA clicks, gated forms, redirects, listing hubs, and on-site longreads, including an explicit rule not to submit optional lead forms when an on-page longread is already readable, an explicit wait-through for transient submit states such as `Please Wait`, and explicit guidance not to misclassify ordinary text-field issues as enum blockers. Successful and failed attempts still project the best route back into `reports_db.publishers`, but richer structured route evidence now also lands in `publisher_download_route_history` for reuse and debugging. Readiness rejection now logs explicit scores and typed rejection reasons, blocker inference ignores arbitrary article/footer text in favor of real blocker-like terminal signals, older generic email-route memories are canonicalized back to `browser_email_form`, and planner fallback now prefers form-specific browser guidance when remembered evidence shows a URL is email-gated. The browser runtime now keeps the browser session alive through post-run capture, retries bounded stabilization for transient terminal states, falls back to the active page state when browser-level HTML/title fields are empty, falls back again to the last agent-history URL/title/screenshot when `browser-use` has already reset the live session, can fall back to page-level screenshots when the browser-level screenshot hook fails, now mines document-like terminal URLs from both performance resources and DOM candidates, persists typed `network_events` inside `DownloadTerminalEvidence`, prefers stabilized terminal URL/HTML over stale agent payload when building confirmation evidence, clears reported PDF MIME metadata when no real local file exists, and now adopts real PDF artifacts produced outside the managed browser download directory (for example `save_as_pdf` temp artifacts) before validating the route result. On-site routes auto-capture local HTML artifacts when the agent omits `onsite_capture_path`, `browser_onsite_report` can fetch the final page HTML to recover a longread capture even after an unnecessary optional form submission, and paginated on-site captures now stay inferred/partial until traversal evidence or an explicit end-state shows the report is complete. Email confirmation still requires multiple signals instead of a submit click alone, and now accepts network confirmation/submission evidence when the browser runtime exposes it; fetched terminal HTML can upgrade weak transient submit states into verified `email_requested` outcomes when the final page confirms success, while unverified `pdf_download` claims that produce no artifact are now surfaced as typed claim-validation failures instead of being conflated with genuine missing-file downloads. `src/config/browser_download_identity.yaml` now supports deeper reusable form identity values plus verified publisher-specific overrides such as the seeded `bigcommerce.com` revenue selection. Current live validation confirms the direct Capgemini PDF completes as `pdf_download / downloaded`, the Brand Finance longread completes as `onsite_report / captured`, and the BigCommerce form path now completes as verified `email_delivery / email_requested` on the thank-you route. Browser task prompts are versioned in `src/prompts/browser_report_download/browser_route/`, browser form-filling values are loaded from `src/config/browser_download_identity.yaml`, and any newly encountered form field labels are appended there automatically as new keys with empty values for later completion.
- Batch acquisition auditing: `src/orchestrators/acquisition_audit_orchestrator.py` composes the existing publisher-inventory discovery flow with isolated report-download audits, reuses the accepted `current_candidates` plus discovery run-quality summary as download inputs, and writes one JSON artifact containing publisher-level and candidate-level acquisition maps for the current publishers without re-running discovery or diff logic inside the download phase.
- Publisher-inventory screening and quality now use broader publisher-agnostic route/title heuristics for buyer guides, trends, forecasts, and barometers, reject generic case-study/help/self-service/service-hub pages more aggressively, and reject bare report-collection hubs even when their landing page is structurally rich.
- Publisher-inventory discovery/screening/quality now also normalizes placeholder archive-card titles like `feature-img` back to URL slugs, follows broader report-library routes such as `publications` / `whitepapers` / `livres-blancs`, rejects generic `/service/`, `/software/`, `/who-we-help/`, and editorial detail pages more aggressively even when they sit under report/archive sources or expose generic forms/download CTAs, and keeps unreachable report-detail pages when the URL/title/source-page context still strongly identifies a real report asset.
- Direct report landing pages now seed themselves as browser-discovery candidates when the page URL is strongly report-like but the DOM only exposes navigation links, which reduces false negatives on single-report insights URLs.
- Refactor simplification layer: shared boolean/numeric coercion and list-normalization helpers now live in `src/utils/coercion.py`, shared slug-tag normalization and fail-open JSON prompt serialization live in `src/utils/tag_utils.py` and `src/utils/json_utils.py`, UI/dashboard row serialization is centralized in `src/utils/gui_utils.py`, orchestrator retry wrappers are centralized through `retry_orchestrator.run_step_with_default_policy`, and duplicate WordPress term ensure logic is consolidated into a shared internal helper.
- Evidence-pack strategy scaffolding is centralized in `src/generators/evidence_packs/base.py`: the repetitive list/scalar wrapper normalization, empty-payload factories, alias fallback, and `_cache` preservation are shared there, while each strategy module still owns its explicit field mapping and item/value transforms.
- Additional boundary cleanup: Streamlit settings/prompt rendering now routes through `src/ui/settings_page.py`, `src/services/state_service.py` is a thin canonical boundary over focused internal state modules, and the config + ingest entrypoints are phase-split so `load_settings`, `run_ingest`, and `run_ingest_file` read as explicit control-flow stages instead of monolithic implementations.
- Ops tooling cleanup: duration diagnostics now share one implementation in `scripts/duration_tools.py` (legacy entry scripts delegate to it), and legacy Streamlit config cleanup flags (`ingest.debug_candidate_gallery`, `analysis.compare`) were removed from the structured editor path.
- Streamlit dashboard read models now cache per browser session in `st.session_state` for reports/state/log/storage snapshots, and explicit refresh or mutating UI actions (ingest, publish, recategorize, cover generation, config save) invalidate the affected cached views before the next read.
- Figure quality gate: candidate visuals now pass deterministic prefilters, kind-split ranking, adaptive GPT crop refinement, and strict final cropping before HTML render. The detailed extraction, crop, and fallback heuristics live in [Technical Design Notes](#technical-design-notes).
- Candidate extraction split: `pdf_service.collect_candidates` remains the canonical PDF-candidate service boundary, while table and chart/infographic heuristics evolve in separate internal modules under `src/services/_pdf/`. Heuristic rationale and known limits are grouped in [Technical Design Notes](#technical-design-notes).
- Candidate window control: post-prefilter truncation is kind-aware so one noisy flow cannot crowd the other out before ranking. The exact prefilter, recovery, and spillover rules are documented in [Visual Candidate Pipeline](#visual-candidate-pipeline).
- Crop output safety: strict crop modes use candidate-ID outputs and conservative text-edge correction so table/chart saves do not collide and partial border text is trimmed or recovered safely. See [Ranking, Crop Refinement, and Fallback](#ranking-crop-refinement-and-fallback).
- SEO-ready HTML: rendered digests include shortened `<title>` handling, `meta description`, Open Graph/Twitter cards, optional canonical URL, JSON-LD (`Article`) structured data, explicit image `width`/`height` attributes to reduce CLS, and automatic `noindex,nofollow` on low-content fallback pages.
- Vector store is the default and only analysis path; legacy local_text prompt stuffing has been removed now that vector_store is validated.
- Taxonomy extraction now separates report-level signal tags from portal categorization: the prompt returns `primary_tags`, `secondary_tags`, a merged `taxonomy` list, and per-tag `tag_evidence` as metadata for search/filtering, while portal categories are assigned separately from report context using category definitions in `src/config/category-mappings.yaml`.
- HTML metadata chips normalize slug-style taxonomy values into readable labels (e.g., `ai-in-retail` -> `AI in Retail`) with acronym preservation loaded from `src/config/html-tag-acronyms.yaml`.
- Publish file ID resolution is DB-first: publish/publish-queue share the same HTML-path canonicalization and reports-metadata (`html_path -> file_id`) lookup helper, then fall back to HTML parsing only when mapping is unavailable.
- Publish-time validation-report parsing is centralized in `src/utils/validation.py` so the publish path maps JSON payloads to `ValidationReport` consistently before applying policy decisions.

---

## Architecture Overview

Related architecture notes:
- `docs/architecture/publisher-discovery-success-playbook.md`: scenario-driven optimization plan to improve publisher inventory discovery success rates and reduce false negatives.
- `docs/quality/deep-analysis-x10-plan-2026-04-15.md`: 50 proposal deep-analysis roadmap covering quality, stability, speed, and cost x10 opportunities by module.


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
- `publish_orchestrator.py`: publish workflow and publish-state transitions.
- `publish_queue_orchestrator.py`: publish queue snapshot assembly for UI/ops surfaces.
- `report_download_orchestrator.py`: local browser-use report acquisition with per-URL route memory, retry-aware fallback from remembered route to fresh discovery, early non-report readiness rejection, and typed outcome classification (`pdf_download`, `email_delivery`, or `onsite_report`).
- `cost_reporting_orchestrator.py`: filtered cost report + rollup orchestration.
- `ops_dashboard_orchestrator.py`: dashboard snapshot aggregation (reports/state/lock/storage).
- `candidate_extraction_orchestrator.py`, `cover_image_orchestrator.py`, `recategorize_orchestrator.py`, `wp_category_update_orchestrator.py`: feature-specific workflows.

## WordPress Subproject

The `Wordpress/` folder contains the rendering and portal layer for Market Lense:

- block theme: `wp-content/themes/marketlense`
- core domain plugin: `wp-content/plugins/marketlense-core`
- packaging, provisioning, sync, and smoke-test scripts: `Wordpress/scripts/*`

### Scope

Included:

- FSE block theme templates/parts/patterns for editorial rendering
- WordPress plugin for the report CPT/taxonomy/meta domain model
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

Primary responsibilities:

- Registers custom post type `ml_report` (`show_in_rest=true`, REST base `ml_report`)
- Registers taxonomies:
  - native WordPress `category` support on `ml_report` for public topic/archive/filter UX
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
- Homepage assembled from reorderable patterns with a consultancy-style hero, proof bands, and discovery bands
- Theme-driven editorial token system in `theme.json` with semantic enterprise-blue tokens mirrored into `assets/css/theme.css` for non-block components
- Sans-first typography roles for display, page titles, section titles, card titles, body copy, metadata, navigation, and buttons are defined centrally in `theme.json` and reinforced in `assets/css/theme.css`
- Homepage chapter anchors are standardized through `.ml-section-anchor`, `.ml-section-eyebrow`, `.ml-section-title`, and `.ml-section-rule`
- Homepage and shared editorial cards opt into a reusable premium surface system via `.ml-surface-card`
- Minimal JS only for singular report interaction parity

Current theme highlights:

- shortcode-driven header/footer navigation resolution
- a proof-led homepage hero and dynamic homepage intelligence surfaces
- a semantic enterprise-blue token foundation in `theme.json` plus `assets/css/theme.css` (`text-primary`, `text-secondary`, `text-muted`, `brand-navy`, `signal-blue`, `support-blue`, `surface-white`, `background-cool`, `border-subtle`, `shadow-premium`) while keeping legacy slugs as compatibility aliases
- a sans-first enterprise typography system in `theme.json` and `assets/css/theme.css` covering display/page/section/card/meta/nav/button roles without changing shortcode structure or homepage composition
- a reusable homepage section-anchor system (`.ml-section-anchor`, `.ml-section-eyebrow`, `.ml-section-title`, `.ml-section-rule`) so editorial chapters read as distinct premium intelligence surfaces without changing inner module grids
- a centralized premium surface-card system in `assets/css/theme.css` (`.ml-surface-card`, standard/compact padding, 12px radius, semantic border/shadow states, and 24px card gaps) applied to featured, report, signals, themes, authority, and method cards without changing shortcode logic or grid templates
- a two-column premium homepage hero in `patterns/hero-institutional.php` with native search, stronger entry hierarchy, and a right-side intelligence panel powered by the existing hero snapshot shortcode without changing shortcode/query behavior
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

- Creates/updates required pages (About, Methodology, Topics directory, Publishers directory, Submit a Report, Contact, Privacy, Terms)
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
- Primary navigation links are present in rendered output
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

The homepage hero uses a two-column proof-led composition, the proof rail is rendered by `[ml_hero_snapshot]`, homepage sections are grouped into proof and discovery bands, and the header/footer use the same home frame width as the hero and homepage section bands.

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

If root config disables WordPress TLS verification (`publish.wp.ssl_verify: false`), the Python publish service suppresses `urllib3` insecure-request warnings for those calls, but the HTTPS connection remains untrusted until the host certificate chain is fixed. The WordPress shell/Python provisioning scripts also honor `WP_SSL_VERIFY` and `WP_CA_BUNDLE_PATH`, so hosted admin/provisioning runs can match the same TLS policy as publish flows.

When the hosting layer blocks direct `/wp-content/uploads/...` access, the plugin serves attachments through a frontend proxy route (`/?ml_media=<attachment_id>`) and rewrites frontend digest content/thumbnail URLs to that proxy so uploaded media still renders publicly.

The Python publisher appends a hidden `Drive fileId: ...` marker to post content when the rendered HTML lacks one so plugin backfill and REST lookup remain deterministic for digest posts created under the core `post` type.

During publish, the pipeline writes native category IDs for report topics and `ml_publisher` term IDs for report publishers through the WordPress REST API so archive filters and directory pages stay aligned with uploaded reports.

### Maintenance Rule

Any WordPress change in this subproject must update this root README WordPress section.

## Configuration (YAML + .env)

Primary config: `src/config/app.yaml`. Missing values can be provided via `.env` (loaded by `config_service`). Secrets must come from environment variables.

For dev wiring, use `src.services.config_service.build_ingest_settings` with `IngestSettingsBuildRequest` to adapt `AppSettings` into `IngestSettings` without hand-copying fields; new config keys are picked up automatically.
`src/services/config_service.py` now resolves ingest settings through section resolvers plus reusable field specs, so env fallback, coercion, defaults, and minimum-value behavior are localized to the relevant config section instead of one long inline parsing chain.

Key fields and env overrides:

- Paths: `paths.output_dir` (`OUTPUT_DIR`, default `./out`), `paths.cache_dir` (`CACHE_DIR`, default `./cache`), `paths.state_db` (`STATE_DB`), `paths.reports_db` (`REPORTS_DB`), `paths.category_mappings` (defaults to `src/config/category-mappings.yaml`; supports context-first category profiles via `definition`, `include_when`, and `exclude_when`, plus retained taxonomy-signal groups such as `core_tags`, `supporting_tags`, `descriptor_tags`, `generic_tags`, and `negative_tags`), `paths.html_tag_acronyms` (defaults to `src/config/html-tag-acronyms.yaml`).
- Ingest: `ingest.google_sa_path` (`GOOGLE_SERVICE_ACCOUNT_JSON`), `ingest.gdrive_folder_id` (`GDRIVE_FOLDER_ID`), `ingest.openai_model` (`OPENAI_MODEL`), `ingest.batch_limit` (`BATCH_LIMIT`, default 20), `ingest.worker_limit` (`INGEST_WORKER_LIMIT`, default 2), `ingest.report_worker_limit` (`INGEST_REPORT_WORKER_LIMIT`, default 2), `ingest.temperature` (`TEMPERATURE`, default 1.0), `ingest.timeout_seconds` (`OPENAI_TIMEOUT_SECONDS`, default 600), `ingest.lock_ttl_seconds` (`INGEST_LOCK_TTL_SECONDS`, default 7200), `ingest.contents_page.*` (keywords, max_pages, min_headings, render_dpi, preview_enabled), `ingest.evidence_packs.parallel_workers` (`EVIDENCE_PACK_PARALLEL_WORKERS`, default 3), `ingest.evidence_packs.global_max_in_flight` (`EVIDENCE_PACK_GLOBAL_MAX_IN_FLIGHT`, default 2), `ingest.evidence_packs.global_min_interval_ms` (`EVIDENCE_PACK_GLOBAL_MIN_INTERVAL_MS`, default 250), `ingest.evidence_packs.doc_map_max_attempts` (`EVIDENCE_PACK_DOC_MAP_MAX_ATTEMPTS`, default 3), `ingest.evidence_packs.doc_map_retry_delay_ms` (`EVIDENCE_PACK_DOC_MAP_RETRY_DELAY_MS`, default 500), `ingest.evidence_packs.registry` (`EVIDENCE_PACK_REGISTRY`, comma-separated), `ingest.evidence_packs.enable_new_variety_packs` (`EVIDENCE_PACK_ENABLE_NEW_VARIETY_PACKS`, default `false`), `ingest.artifacts.parallel_workers` (`ARTIFACT_PARALLEL_WORKERS`, default 4), `ingest.artifacts.global_max_in_flight` (`ARTIFACT_GLOBAL_MAX_IN_FLIGHT`, default 2), `ingest.artifacts.global_min_interval_ms` (`ARTIFACT_GLOBAL_MIN_INTERVAL_MS`, default 250), `ingest.validation.regeneration_max_attempts` (`VALIDATION_REGENERATION_MAX_ATTEMPTS`, default `3`, minimum `1`).
- Shared LLM policy: `ingest.llm.retries` (default `1`), `ingest.llm.base_delay_seconds` (default `1.0`), `ingest.llm.backoff_step_seconds` (default `1.0`), `ingest.llm.jitter_seconds` (default `0.25`), `ingest.llm.circuit_breaker_failure_threshold` (default `3`), and `ingest.llm.circuit_breaker_recovery_seconds` (default `30.0`) control the shared `llm_service` wrapper used for model calls.
- PDF OCR fallback: `ingest.pdf_text.ocr_fallback.enabled`, `ingest.pdf_text.ocr_fallback.model` (default `gpt-5-mini`), `ingest.pdf_text.ocr_fallback.timeout_seconds`, `ingest.pdf_text.ocr_fallback.prompt_namespace`, `ingest.pdf_text.ocr_fallback.cache_enabled`, `ingest.pdf_text.ocr_fallback.chunk_page_count` (default `8`). OCR calls go through `src/services/openai_service.py` using the OpenAI Responses API. This fallback only runs when the native text gate would otherwise return `pdf_text_unextractable`; low-density but still extractable PDFs stay on the normal path.
- Figure captions: `ingest.figure_captions.enabled`, `ingest.figure_captions.temperature`, `ingest.figure_captions.timeout_seconds`, `ingest.figure_captions.prompt_namespace` (default `report_vs/figure_caption`), `ingest.figure_captions.max_chars` (default `500`). The bundled `src/config/app.yaml` enables this phase by default. Model resolution follows `openai_models.report_vs/figure_caption` first, then falls back to `ingest.openai_model`. The phase is fail-open: primary figures fall back to the legacy shared caption, secondary figures fall back to detected captions or the existing placeholder label.
- Browser downloads: `OPENROUTER_API_KEY` is required, `OPENROUTER_HTTP_REFERER` is optional, `browser_download.model` (`BROWSER_DOWNLOAD_MODEL`, default `openai/gpt-5-mini`), `browser_download.identity_config_path` (`BROWSER_DOWNLOAD_IDENTITY_CONFIG_PATH`, default `src/config/browser_download_identity.yaml` relative to `app.yaml`), `browser_download.temperature` (`BROWSER_DOWNLOAD_TEMPERATURE`, default `0.0`), `browser_download.timeout_seconds` (`BROWSER_DOWNLOAD_TIMEOUT_SECONDS`, default `180`), `browser_download.max_steps` (`BROWSER_DOWNLOAD_MAX_STEPS`, default `30`), `browser_download.output_dir` (`BROWSER_DOWNLOAD_OUTPUT_DIR`, default `./out/browser_downloads`), `browser_download.headed` (`BROWSER_DOWNLOAD_HEADED`, default `false`; the bundled `src/config/app.yaml` currently enables headed mode with `true`), and `browser_download.retry.*` (`BROWSER_DOWNLOAD_RETRIES`, `BROWSER_DOWNLOAD_BASE_DELAY_SECONDS`, `BROWSER_DOWNLOAD_BACKOFF_STEP_SECONDS`, `BROWSER_DOWNLOAD_JITTER_SECONDS`). The browser-download flow uses the shared `paths.state_db` to persist one remembered route summary per normalized URL, and appends newly seen form labels into the identity YAML for later manual completion.
- Browser downloads also write into `paths.reports_db` table `report_sources`. Discovery inserts one row per new diff item with `source_status='discovered'`, publisher/source-page provenance, and `discovered_on_page_number`; a later successful local PDF download upgrades the same normalized-URL row in place to `source_status='downloaded'`, filling `downloaded_at_utc` and the downloaded file `md5`.
- Publisher snapshots sourced from the Notion `REPORT SOURCES` page can be synced into `paths.reports_db` table `publishers` via `python -m src.cli sync-publishers`. The sync reads `paths.publisher_profiles` (default `Wordpress/config/publisher-profiles.json`) and replaces the current `publishers` table contents with validated snapshot rows storing `name`, `homepage`, `self_presentation`, and `insights_url`, while preserving any previously curated `google_folder` links and remembered browser-download route fields by `insights_url` and fallback publisher-name matching.
- Publish: WordPress publish settings and TLS notes are documented together in the `WordPress Subproject` section below (`publish.wp.*`, `WP_*`, and `publish.validation.policy`).
- Ranking/crop refinement: `rank.max_candidates`, `rank.selected_max` (default `5`), `rank.min_overall_score`, `rank.min_quality_score`, `rank.min_insight_score`, `rank.min_data_score`, `rank.crop_refine_enabled`, `rank.crop_refine_mode` (`adaptive|always|off`), `rank.crop_refine_page_dpi`, `rank.crop_refine_temperature`, `rank.crop_refine_timeout_seconds` (defaults to `rank.timeout_seconds` when omitted).
- Drive listing: `ingest.drive.supports_all_drives`, `ingest.drive.include_items_from_all_drives` (shared drive flags), `ingest.drive.drive_id` (shared drive scope), and `ingest.drive.list_mode` (`full` vs `metadata` to omit names until needed).
- PDF text extraction: `ingest.pdf_text.max_pages` and `ingest.pdf_text.max_chars` cap how much text is sampled per PDF; `ingest.pdf_text.min_density` (default `250` chars/page) triggers "not available from text" fallbacks when extraction is sparse; `ingest.pdf_text.sample_pages` (default `3`) controls the deterministic sample used to validate extractability before analysis.
- Model overrides: `openai_models` maps prompt namespaces (or prefixes) to model IDs. Longest-prefix match wins. Falls back to `ingest.openai_model` for most prompts and to `rank.model` for `rank_candidates` unless an override is provided.
- HTML rendering labels: `paths.html_tag_acronyms` points to a YAML file that defines `html_tag_acronyms` tokens preserved in uppercase when slug labels are humanized.

Per-step model selection (new):

- Set `openai_models` entries to pin specific prompt calls to specific models (e.g., `report_vs/artifacts/summary`, `report_vs/evidence_packs/findings`, `report_vs/validate/grounding`, `rank_candidates`, `rank_candidates/crop_refine`).
- Prefix keys apply to all nested namespaces unless a more specific key exists (e.g., `report_vs/evidence_packs` covers all evidence packs).
- Vector store: `analysis.vector_store_keep` (`VECTOR_STORE_KEEP`, default `true`) controls whether to retain caches between runs (including evidence pack reuse). Analysis uses the vector_store path only. Evidence/validation JSONs are written only to `out/<report-slug>/report_analysis/`.
- Artifact retrieval mode: `analysis.artifacts_use_vector_store` (`ARTIFACTS_USE_VECTOR_STORE`, default `false`) controls whether artifact model calls use vector-store retrieval. Default is closed-context JSON chat; set to `true` to restore legacy vector retrieval behavior.
- Validation grounding retrieval mode: `analysis.validation_grounding_use_vector_store` (`VALIDATION_GROUNDING_USE_VECTOR_STORE`, default `false`) controls whether grounding checks use vector-store retrieval. Default is closed-context JSON chat; set to `true` to restore legacy vector retrieval behavior.
- Strict schema validation: `analysis.strict_schema_validation` (`STRICT_SCHEMA_VALIDATION`, default `true`) enables hard-fail schema enforcement for evidence/docpack payloads.
- Cost tracking: `analysis.cost_ledger_path` (`COST_LEDGER_PATH`, default `./out/cost-ledger.jsonl`), `cost.daily_path` (default `./out/cost-daily.json`), `cost.pricing` (per-model pricing map used by `utils.costing`).
- Validation: `ingest.validation.data_gap_policy` (default `warn`) controls whether missing evidence/text gaps downgrade errors to warnings; `ingest.validation.regeneration_max_attempts` bounds post-validation regeneration passes and does not count the initial generation/validation pass; `publish.validation.policy` (`PUBLISH_VALIDATION_POLICY`, default `block`; set to `warn` to allow publish with issues).
- Taxonomy extraction: set `openai_models.report_vs/taxonomy` to override the tag/region/time period extractor and `ingest.taxonomy_temperature` (or `TAXONOMY_TEMPERATURE`) to control taxonomy-only sampling. The bundled prompt now returns structured central/secondary tags with evidence, biases away from adjacent platform/channel/tactic tags unless they define the whole report, and applies YAML-driven post-processing inference rules for evidence-backed tag bridges.
- Context-first category assignment: `src/generators/report_context_generator.py` deterministically compacts stored evidence packs (`doc_map`, `scope`, `methods`, `findings`, `limitations`) into a typed `ReportCategoryContext`, and `src/generators/context_category_fit_generator.py` runs a single batched model decision over category `id` / `label` / `description` / `definition` / `include_when` / `exclude_when` profiles from `src/config/category-mappings.yaml`. This is the production portal-category path; taxonomy tags remain metadata only.
- Cover images: `paths.cover_styles` points to `src/config/cover-styles.yaml` (defaults to that path). Fonts are local files; the default config uses `templates/GOTHICB.TTF` for both regular/bold. Ensure the font file exists on the host; otherwise cover rendering will fail with `cover_font_invalid`. Background image is optional; leave blank for a solid background.

Secrets (env only):

- `OPENAI_API_KEY` (required)
- `OPENROUTER_API_KEY` (required for `download-report` / browser-download automation)
- `OPENROUTER_HTTP_REFERER` (optional for OpenRouter tracking)
- `WP_APP_PASSWORD` or `WP_BEARER_TOKEN` (publishing)
- `WP_POST_TYPE` (optional publish endpoint override; current YAML sets `posts`, code fallback is `ml_report`)
- Optional provider keys (e.g., `MINERU_API_KEY`) if used.

Prompt locations:

- Vector store evidence packs: `src/prompts/report_vs/**` (`doc_map/`, `evidence_packs/{scope,methods,findings,limitations,quote_candidates,key_metrics,risk_register,recommendations,contradictions}/`)
- Artifact generation: `src/prompts/report_vs/artifacts/**` (toc, summary, insights candidates/final, quotes, expert comment, LinkedIn post)
- Artifact regeneration: `src/prompts/report_vs/artifacts/regenerate/**` (summary, insights_candidates, insights_final, quotes, expert_comment, linkedin_post)
- Taxonomy extraction: `src/prompts/report_vs/taxonomy/`

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
   - `file_service.file_stat(...)` reads exists/size/mtime and consults a `.md5.json` sidecar to avoid re-hashing cached files.
   - Before report generation, if md5 is still missing, ingest computes md5 from the cached PDF and writes/refreshes the md5 sidecar so md5-gated caches remain eligible.
   - Cache hits skip EOF checks; if Drive provides `md5Checksum`, it is compared against cached md5.
   - Drive API clients are cached per thread to keep googleapiclient/httplib2 usage thread-safe when `ingest.worker_limit > 1`.
   - `drive_service.download_pdf_to_path(...)` streams PDF bytes directly to disk while computing md5.
   - `src/services/pdf_service.py` checks for EOF marker using only tail bytes and redownloads once if missing.
   - `src/services/pdf_service.py` remains the stable public facade; its implementation is split across private capability modules under `src/services/_pdf/` (`text`, `contents`, `figures`, `crop`) to keep one PDF service role with lower regression blast radius.

5. **State management**
   - `src/services/state_service.py` maintains a SQLite store of processed file IDs and hashes.
   - If Drive provides `md5Checksum`, already-processed files are skipped before any download or hashing.
   - A separate ingest cursor (`last_successful_ingest_utc`) is recorded on successful runs and used to filter subsequent Drive listings.

6. **Report generation (per file)**
   - `src/orchestrators/report_pipeline_orchestrator.py` controls report-generation retries and delegates the actual report workflow to `src/orchestrators/report_generation_orchestrator.py`.
   - `src/orchestrators/report_generation_orchestrator.py` is the per-report control plane and sequences source, selection, analysis, and render phases:
     - `src/contracts/report_generation.py`: typed handoff contracts (`ReportRuntimeState`, `ReportSourceState`, `ReportSelectionState`, `ReportAnalysisState`).
     - `src/generators/report_source_generator.py`: PDF context bootstrap, md5-backed PDF info/contents/text caches, density/extractability checks, and base payload seeding.
     - `src/generators/report_selection_generator.py`: figure extraction, candidate prefilter/ranking, crop refinement, strict crops, and figure-gallery fallback selection.
     - `src/orchestrators/report_analysis_orchestrator.py`: vector-store lifecycle coordination, taxonomy/category resolution, evidence packs, artifacts, validation, validation-regeneration looping, and analysis snapshot persistence.
     - `src/generators/report_render_generator.py`: preview rendering, metadata DB readback, HTML cache/render, cover generation, and final `IngestOutcome` assembly.
     - Optional within-file parallelism still uses `ingest.report_worker_limit` to overlap PDF info/contents/text extraction, figure vs candidate extraction, and taxonomy vs evidence generation when enabled (default `2`).
     - **PDF info**: `pdf_service.extract_pdf_info` captures page count and sanitized PDF metadata for persistence (cached by md5 under `cache_dir/pdf_cache/`).
     - **PDF context**: `pdf_service.build_pdf_context` opens PyMuPDF and pypdf handles once; downstream services reuse them and fall back to local opens if unavailable.
     - **Contents/index detection**: scans the first pages for a contents/index section, records the page number for DB/runtime routing, and can render an internal preview asset for diagnostics (detection cached by md5 + settings).
     - **Text extraction**: `pdf_service.extract_pdf_text` extracts text from the first N pages (reusing the shared context when present) and computes text density (cached by md5 + extraction settings); if density falls below `ingest.pdf_text.min_density`, downstream artifacts short-circuit to explicit “not available from text” placeholders with HTML notices.
     - **Text extractability check**: deterministically samples `ingest.pdf_text.sample_pages` pages (seeded by file id + hash) via `pdf_service.sample_pdf_text`; if none contain extractable text, the run aborts early with `pdf_text_unextractable` before any vector store or LLM work.
     - **LLM analysis**:
       - `vector_store` mode (only path): Ensures a vector store exists (create -> upload PDF -> attach) and starts provider-side indexing first.
       - While indexing runs, the generator continues PDF-only work (figure/candidate extraction and preview rendering).
       - It waits for indexing only right before vector-dependent stages (taxonomy/evidence/artifacts) via `vector_store_service.wait_until_indexed`.
       - After indexing is ready, taxonomy/category resolution and evidence-pack generation run concurrently when `ingest.report_worker_limit > 1` (serial when `= 1`).
      - Evidence packs are generated via `src/generators/evidence_pack_generator.py`, which now stays as the orchestration entrypoint while per-pack normalization/metadata live under `src/generators/evidence_packs/*.py`. The config-driven registry (`ingest.evidence_packs.registry`) and optional variety expansion (`ingest.evidence_packs.enable_new_variety_packs`) cover `doc_map`, `scope`, `methods`, `findings`, `limitations`, `quote_candidates`, and optional `key_metrics`, `risk_register`, `recommendations`, `contradictions`. The generator now schedules work directly from `EvidencePackStrategy` objects, `doc_map` runs first as a hard gate, and remaining packs run in parallel (`ingest.evidence_packs.parallel_workers`). Global evidence-pack rate limiting is applied at the orchestrator boundary (`src/orchestrators/report_pipeline_orchestrator.py`) using `ingest.evidence_packs.global_max_in_flight` + `ingest.evidence_packs.global_min_interval_ms`.
      - Artifacts are generated via `src/generators/artifact_generator.py` using a dependency-aware parallel DAG: `toc` + `summary` + `insights_candidates` + `quotes` in parallel, then `insights_final`, then `expert_comment` + `linkedin_post` in parallel. Independent steps use `ingest.artifacts.parallel_workers`. Global artifact rate limiting is applied at the orchestrator boundary (`src/orchestrators/report_pipeline_orchestrator.py`) using `ingest.artifacts.global_max_in_flight` + `ingest.artifacts.global_min_interval_ms`. By default these artifact model calls run closed-context (`chat_json`); vector retrieval is opt-in via `analysis.artifacts_use_vector_store`.
      - Targeted regeneration is handled by `src/generators/report_regeneration_generator.py`, which performs exactly one regeneration pass against mapped failing artifact families and reuses the same artifact normalization, schema validation, evidence-reference validation, and storage behavior as the main artifact generator.
      - Regeneration target dispatch inside `report_regeneration_generator.py` is registry-driven by `target_section`, so each supported section keeps prompt namespace selection, variable assembly, normalization, and artifact-state updates in one handler path instead of a shared branch chain.
      - Artifact evidence IDs are normalized to canonical known references (`findings`, `quote_candidates`, `doc_map.sections`) before schema-reference validation; unresolved IDs are cleared rather than failing the entire artifact payload.
       - Packs are stored under `out/<report-slug>/report_analysis/*.json` and persisted in the metadata DB (`reports` table columns `vector_store_id`, `evidence_packs_json`; state DB stores `vector_store_status`, `indexed_at_utc`, `openai_file_id`, `last_error`).
       - Orchestrator logs `VECTOR_STORE_CREATED`, `VECTOR_STORE_INDEXED`, `EVIDENCE_READY`.
- Evidence packs, artifacts, validation reports, and HTML are cached by md5 + prompt/template hashes to skip repeat LLM and rendering work when inputs are unchanged. Artifact and validation caches are retrieval-mode aware, so `chat_json` and vector-retrieval outputs are isolated.
- Final `analysis_<mode>.json` snapshots preserve internal report payload metadata, including the active vector store ID, persisted analysis pack paths, and text extraction stats used by downstream diagnostics.
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
       - Evidence retrieval: validation builds overlapping evidence windows (token windows with stride), scores via hybrid lexical overlap + BM25-like term hits + quantity boost, and expands with neighbor windows to reduce page-break false negatives. Cached PDF text (`cache/pdf_cache/<md5>/text_*.json`) is included in retrieval windows when available.
       - Quote validation: verbatim quotes require normalized near-verbatim support (substring/lexical threshold). Paraphrase-labeled quotes are allowed with semantic support.
       - Semantic: LLM re-check via `src/prompts/report_vs/validate/semantic/{system,user}.yaml` (model resolved via `openai_models` longest-prefix match) that scores metric/quote support against evidence snippets and logs prompt hashes + evidence/metric/quote SHA-256. Semantic “supported” adds `info` issues; “unsupported” raises `warning|error`.
       - Grounding rubric (`src/prompts/report_vs/validate/grounding/{system,user}.yaml`): validator distinguishes `factual_claim`, `analyst_interpretation`, and `prescriptive_recommendation`. Hard fails are reserved for hallucinated entities/events, unsupported metrics, misattributed quotes, and “the report said/instructed X” misattributions; retrieval failures are tracked separately. Grounding defaults to closed-context (`chat_json`) and can be switched back to vector retrieval via `analysis.validation_grounding_use_vector_store`.
       - Parallel execution: when `ingest.report_worker_limit > 1`, the validation registry runs `semantic` as the bootstrap rule, `numbers` + `grounding` as independent rules, and `metrics` + `quotes` after semantic support is available. Issue merge order remains deterministic as `semantic -> metrics -> quotes -> numbers -> grounding` to prevent behavioral drift while keeping the large control block out of the entrypoint.
       - If validation fails after artifact generation, `report_analysis_orchestrator` can build a bounded regeneration plan from `affected_section` mappings, regenerate only the failing artifact families (or one broad retry for unmappable/global failures), and re-run validation until pass or `ingest.validation.regeneration_max_attempts` is reached.
       - Results persist to `out/<report-slug>/report_analysis/validation*.json` and flow into HTML and publish policy decisions. The canonical `validation.json` is always updated to the latest attempt used by render/publish, while regeneration snapshots are also persisted as `validation_regen_attempt_<n>.json`. When `ingest.validation.data_gap_policy` is `warn`, missing evidence/text downgrades to warnings. Schema validation is performed via `schema_validator_service`.
     - **Normalization**: `normalize_generator` enforces strict schema and list sizing.
    - **Categorization**: stored evidence packs are compacted into a `ReportCategoryContext`, then a single batched category-fit prompt evaluates all portal categories against that context using each category's `definition`, `include_when`, and `exclude_when` guidance from `src/config/category-mappings.yaml`. The selector returns at most two portal categories. Taxonomy tags are kept as metadata and do not determine category assignment.
     - **Figure selection**: `pdf_service.extract_best_figure` selects a representative visual and caption.
      - **Candidate extraction**: `pdf_service.collect_candidates` remains the single public coordination boundary for chart/table discovery, page-level extraction, and contents-page exclusion. Table extraction lives under `src/services/_pdf/table_candidates.py`; chart/infographic extraction lives under `src/services/_pdf/visual_candidates.py`; both are summarized in [Visual Candidate Pipeline](#visual-candidate-pipeline) and expanded in [Technical Design Notes](#technical-design-notes).
     - **Candidate prefilter + ranking**: deterministic prefilter removes obvious low/no-data fragments, reference-style/table-shadow leaks, and other early false positives before kind-aware truncation and LLM ranking (overall + quality + insight + data + keep/reject_reason; model resolves from `openai_models.rank_candidates` if set, else `rank.model`, then `ingest.openai_model`). The detailed prefilter, ranking, and threshold behavior is documented in [Ranking, Crop Refinement, and Fallback](#ranking-crop-refinement-and-fallback).
     - **Candidate fallback policy**: fallback crops no longer revive candidates that already failed the configured rank thresholds; fallback is limited to threshold-passing ranked candidates first, then remaining deterministic prefilter survivors by kind-balanced caps.
     - **Adaptive crop refinement**: ambiguous candidates call `rank_candidates/crop_refine` with page image context; obvious pass/reject candidates skip LLM. Ambiguous page renders are pre-rendered in parallel and crop-refine LLM work is batched per page/phase in bounded parallel mode. Crop refinement runs in two passes (coarse -> finalize) to improve edge precision and reduce clipped text artifacts, and now auto-recovers missing batched decisions with targeted single-candidate retries so partial model outputs do not silently drop valid candidates.
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
   - `src/services/config_service.py` loads WordPress settings from YAML; secrets from `.env`.
   - Produces `PublishSettings` contract.

2. **Pipeline orchestration**
   - Entry point: `src/cli.py` (`publish-wp`).
   - `src/orchestrators/publish_orchestrator.py` coordinates HTML publishing.

3. **HTML discovery**
   - `src/services/file_service.py` lists generated HTML files in `OUTPUT_DIR`.
   - `file_id` is resolved from reports metadata (`reports.html_path -> reports.file_id`) when available; HTML parsing is used only as fallback.

4. **State checks**
   - `src/services/state_service.py` verifies the report was processed and not already published.

5. **Publishing (per file)**
   - `src/generators/publish_generator.py` uploads report images, swaps image URLs to the site-side media proxy route, injects a hidden `Drive fileId` marker when the rendered HTML does not already contain one, and creates a WordPress post.
   - `src/services/wordpress_service.py` handles media and post API calls. WordPress 5xx responses now log bounded header/body diagnostics (sanitized and truncated) before retryable errors propagate, and post lookup requests fail fast on unexpected REST redirects with the redirect target logged in structured error context.

6. **State record**
   - Published posts are recorded with post ID and URL for idempotency.
   - Validation policy: `publish.validation.policy` set to `block` skips publish when validation fails/missing; `warn` logs issues but proceeds. Publish outcomes include validation status/issues.

---

## Technical Design Notes

This section keeps implementation-heavy extraction and crop heuristics out of the main workflow narrative while preserving one place to document the current design.

### Visual Candidate Pipeline

- `pdf_service.collect_candidates` is the single public PDF-candidate boundary; internal heuristics are split by capability under `src/services/_pdf/` so table and chart flows can evolve independently without creating competing service entrypoints.
- The candidate path starts with cheap page triage, skips obvious scanned-image negatives, excludes the detected contents/index page from output, and then runs table/chart discovery in parallel within `ingest.report_worker_limit`.
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

Structured logs are emitted by all services and orchestrators using `src/utils/logging.py`.
Redaction covers API keys, bearer tokens, and common PII patterns before log emission.

CLI-provided run contexts flow into the ingest orchestrator so CLI run/task IDs stay consistent across downstream orchestrator/service logs.

Every log event includes:

- `run_id`: pipeline run identifier
- `task_id`: per-file identifier
- `span_id`: per-operation span identifier
- `module`: logger name
- `role`: service / generator / orchestrator
- `event`: logical event name

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

- Prompt caching: prompt sets are cached in-memory per namespace for the duration of a process. `PromptLoadRequest` supports `reload_if_changed` (mtime check) and `force_reload` (bypass cache) when you need to pick up edited prompt files mid-run.

---

## Category mappings

- Source of truth: `src/config/category-mappings.yaml` (versioned by `schema_version`).
- Classification config: the root `classification` section now configures the legacy weighted tag-mapping path kept for audits, comparisons, and compatibility. Production portal categories are assigned by the context-first fit flow, not by tag scoring.
- Category schema: categories expose stable `id`, `label`, and `description`, and every portal-exposed category must also define `definition`, `include_when`, and `exclude_when` so the context-first classifier has explicit decision boundaries. The same mapping file still retains `core_tags`, `supporting_tags`, `secondary_supporting_tags`, `descriptor_tags`, `generic_tags`, `negative_tags`, and optional `must_have_one_of` fields for taxonomy metadata support, audits, and compatibility flows. Tag values are canonical underscore slugs end-to-end in repo config, inference rules, extracted taxonomy output, and stored taxonomy metadata. The root mapping file also supports `inference_rules` for evidence-backed tag bridges that run after extraction. Each inference rule carries a `target_category_id` for maintenance validation and an `inferred_tag` that must already exist in that category's retained scoring signals. Legacy `tags` remain supported only for backwards-compatible external mappings.
- Scoring: taxonomy tags are weighted against the scoring signal groups, diluted when the same tag appears in multiple categories, and thresholded into at most two portal categories (primary + optional secondary). `descriptor_tags` remain valid extracted metadata but do not influence category scoring or uncategorized-tag logging. Before category scoring, configured `inference_rules` can add or remove extracted tags when trigger-tag evidence matches configured context keywords. A secondary category is only rescued when it has enough strong matches plus extractor evidence across multiple sections before being stored in the metadata DB, rendered in HTML metadata, and synced to WordPress posts.
- Taxonomy prompt: allowed tags from the mapping signals are provided to `src/prompts/report_vs/taxonomy/`; the prompt now asks for central subject tags, explicit secondary themes, and short per-tag evidence rather than broad template tags. Tags present only in `descriptor_tags` may still be extracted for metadata, but they no longer affect portal categorization. Unmapped tags are appended under `uncategorized` for review.
- Maintenance: add categories with `id` (snake_case), `label`, `description`, `definition`, at least one `include_when`, and at least one `exclude_when`. Those profile fields are now required for every portal-exposed category because they drive production category assignment. Retained tag groups should stay focused: use `core_tags` for specific subject signals, keep broad report descriptors in `descriptor_tags`, move weak but category-relevant context into `generic_tags`, reserve `secondary_supporting_tags` for legitimate secondary themes, and use `negative_tags` only when a tag reliably indicates an adjacent but wrong legacy category.
- Coverage policy: if an extracted tag is a recurring high-signal subject label or an `inference_rules` trigger, it should appear in at least one retained scoring group (`core_tags`, `supporting_tags`, or `secondary_supporting_tags`) so metadata audits stay interpretable. Broad cross-domain descriptors such as `consumer_trends`, `social_media`, `digital_economy`, and `forecasts` should stay non-scoring in `descriptor_tags` or root `global_generic_tags`.
- Coverage constraints: keep every category populated with more than 10 tags, keep every tag categorized (no orphan tags), and limit any single tag to at most 5 category lists even when copied for high relevance.
- Current taxonomy highlights: `digital_payments`, `retail_logistics`, `consumer_behavior`, `business_performance`, `agentic_commerce`, plus existing advertising, commerce, CTV, social video, and measurement tracks.
- Unmapped handling: uncategorized tags are removed once mapped; if new tags appear, run `python -m src.cli recategorize` to refresh assignments and prune stale uncategorized entries.
- Mapping caching: category mappings are cached in-memory per path with optional `reload_if_changed`/`force_reload` flags on `CategoryMappingLoadRequest`. Uncategorized tag writes are batched in memory and flushed once per run by orchestrators (ingest/recategorize) to reduce YAML churn.

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
- `semantic_ids.py`: typed `RunId`, `TaskId`, and `ReportId` wrappers used by core contracts to block cross-ID reuse while preserving string-compatible JSON/state boundaries
- `validation.py`: validation requests, issues, and reports (persisted per report)
- `regeneration.py`: validation-regeneration issues, plans, attempt results, loop state, and typed single-pass request/response contracts
- `docpacks.py`: typed contracts for core/variety docpack payloads and map aliases

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

Install dev/test tooling:

```bash
pip install -r requirements-dev.txt
```

### Local browser-use

Browser Use is vendored locally at `tools/browser-use` from `https://github.com/mbrakker/browser-use` as a subordinate tool inside Market Lense.
Root project conventions and the root `AGENTS.md` are authoritative; vendored Browser Use docs and agent-instruction files are wrappers that defer to this repo.
Preserved upstream reference material lives in `tools/browser-use/UPSTREAM_README.md`, `tools/browser-use/UPSTREAM_AGENTS.md`, `tools/browser-use/UPSTREAM_CLAUDE.md`, and `tools/browser-use/UPSTREAM_CLOUD.md`.
Browser Use runtime configuration also lives in the root `.env`; the vendored subtree is wired to read `C:\Programing\Market lense\.env` instead of maintaining its own local `.env`.
To use that local source inside this project virtualenv, install it editable:

```bash
.\.venv\Scripts\python.exe -m pip install -e .\tools\browser-use
```

After installation, the CLI is available from the project virtualenv as:

```bash
.\.venv\Scripts\browser-use.exe --help
```

The repo-level report download automation uses that same local runtime through `src/services/browser_report_download_service.py`. It now plans each attempt from remembered route memory plus discovery/diff evidence, probes candidate PDFs before browser-use when discovery already exposed them, tailors browser-use prompts per route family, captures structured route steps plus blocker/terminal/on-site evidence, and stores both the best legacy projection and the richer per-attempt route history for later reuse.

For OpenRouter-backed usage, see `tools/browser-use/examples/models/openrouter.py`, which is configured to use `stepfun/step-3.5-flash:free` through `OPENROUTER_API_KEY`.

Run tests locally:

```bash
pytest
```

`pytest.ini` sets `pythonpath = .` so `src.*` imports resolve without exporting `PYTHONPATH`.
Default runs exclude `integration`-marked tests (`addopts = -m "not integration"`).
Workflow tests should prefer explicit dependency dataclasses and shared boundary fixtures over monkeypatching module globals.
Current boundary seams include `IngestBatchDependencies`, `CandidateExtractionDependencies`, and `ReportGeneratorDependencies`.
Use `tests/conftest.py` fixtures like `external_boundary_mocks_only`, `wordpress_http`, and `fake_openai` to patch only external boundaries (service entrypoints, HTTP clients, OpenAI clients, time/random/os), while leaving orchestrator and generator logic on the real path.
Touched orchestrator tests should also use `assert_logs_have_required_fields`, and remaining generator/orchestrator hotspots should move to explicit dependency seams or service-module patch points instead of patching internal module symbols directly.
Prompt text is immutable outside `src/services/prompt_service.py`: generators must render prompts through the prompt service, pass the rendered text through unchanged, and log namespace, prompt paths, hashes, rendered prompts, model params, and raw responses around each model call. `tests/test_prompt_boundaries.py` enforces the no-concatenation rule over `src/`.

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
- `python scripts/ci/run_type_check.py` (type gate, `mypy` over changed Python files under `src`, `tests`, `scripts/ci`; skips when no Python files changed unless `TYPECHECK_PATHS` is set)
- `python scripts/ci/check_forbidden_patching.py` (fails on private-helper/dataclass-constructor patching patterns in tests)
- `python -m pytest --cov=src --cov-report=xml --cov-report=term-missing` (default suite excludes integration tests and includes the direct-I/O boundary gate in `tests/test_io_boundaries.py`)
- `python scripts/ci/check_coverage.py --coverage-xml coverage.xml` (global + per-critical-package thresholds)
- `python scripts/ci/run_mutation_gate.py --json-out mutation_results.json` (mutation score gate for critical generators/services/orchestrators)
- `python scripts/ci/check_quality_regression.py --baseline docs/quality/baseline_2026-02-21.json --coverage-xml coverage.xml --mutation-json mutation_results.json --docpack-root tests/fixtures/docpacks/golden --candidate-root tests/fixtures/candidate_extraction/golden` (baseline non-regression gate)
- `python scripts/quality/compare_candidate_goldens.py --golden-root "<golden-root-1>" --golden-root "<golden-root-2>" --output-root out/candidate_golden_compare_current` (exact candidate ID/bbox/crop-hash comparison against manually curated candidate goldens)

---

## Quality Non-Regression

- Baseline snapshot: `docs/quality/baseline_2026-02-21.json`
- Baseline builder: `python scripts/quality/build_baseline.py --copy-golden --baseline-out docs/quality/baseline_2026-02-21.json`
- Golden corpus: `tests/fixtures/docpacks/golden/` (copied from `out/1/*/report_analysis`)
- Golden candidate corpus: `tests/fixtures/candidate_extraction/golden/` (copied from `out/1/*/candidates/candidates.json`, or another root via `--source-candidate-root`)
- Comparator: `scripts/ci/check_quality_regression.py` blocks merge if coverage, mutation, docpack metrics, or candidate-extraction metrics drop below baseline.
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
- `docs/quality/ineffective-choices-top50.md` (archived audit note pointing to the consolidated backlog)

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
- Related code path: `src/services/vector_store_service.py` waits for `completed` / `ready` / `indexed` and raises on timeout or failed indexing.

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
- TLS-specific controls: `WP_SSL_VERIFY` and `WP_CA_BUNDLE_PATH` are honored by the shell/Python provisioning scripts, and `publish.wp.ssl_verify` / `publish.wp.ca_bundle_path` govern the Python publish path.
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

Re-score categories for all stored reports (updates DB + uncategorized tags list):

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

`download-report` is routed through `src/orchestrators/report_download_orchestrator.py`. It looks up a remembered route in `reports_db.publishers` by matching the requested URL to `publishers.insights_url`, tries that route first when available, falls back to fresh discovery only after explicitly retryable remembered-route failures, rejects obvious non-report candidates before browser spend, and returns one of four outcomes: `downloaded`, `email_requested`, `email_required`, or `captured`.

The browser-download service now rejects weak remembered route summaries before they are stored for reuse, requires real delivery confirmation evidence before classifying an email-gated run as `email_requested`, filters obvious non-field controls out of browser identity auto-upserts, records blocker and terminal evidence in route history, and cross-checks PDF signature plus MIME/extension metadata before reporting `downloaded`. Confirmation scoring now accepts generic success states such as visible thank-you text only when combined with another independent browser signal, and routed form-heavy report pages are no longer forced into `browser_onsite_report` when the browser evidence clearly shows an email gate. When a site opens a PDF viewer wrapper instead of writing the real PDF bytes directly, the service fetches the embedded real PDF and replaces the wrapper file before reporting success; when the artifact is actually a blocked form or an on-site longread, the service can now recover that terminal state instead of forcing a fake PDF success.

Discover the current publisher insights inventory, compare it to the last Drive-backed snapshot, and print only new report links:

```bash
python -m src.cli discover-publisher-inventory https://example.com/insights
```

`discover-publisher-inventory` is routed through `src/orchestrators/publisher_inventory_orchestrator.py`. It resolves the publisher by `publishers.insights_url`, reuses remembered inventory route memory when available, preferring typed route traces and scenario summaries over the legacy prose summary, falls back only when that remembered route fails with an explicitly retryable `AppError`, traverses paginated insights sections across all reachable pages, normalizes the combined inventory, and compares it with the latest snapshot stored in that publisher's Google Drive folder. Route ordering is now planned explicitly in `src/orchestrators/_publisher_inventory_route_planner.py`, the canonical publisher inventory service delegates HTTP and browser acquisition into `src/services/_publisher_inventory_fetch_service.py` and `src/services/_publisher_inventory_browser_service.py`, and the run persists both an explicit coverage verdict and a reusable run-quality summary for future route selection and drift review. The canonical public service boundary remains `src/services/publisher_inventory_service.py`, while pure navigation-control and candidate-extraction heuristics now live in `src/services/_publisher_inventory_discovery_activity.py` so the public service module stays focused on external I/O and browser/runtime coordination. Direct PDF insights URLs are treated as a single-item inventory source without entering the browser crawler. High-confidence direct-detail HTML pages can now also short-circuit before archive traversal, even when `publisher_discovery.force_browser=true`; normal JS-heavy, tabbed, and filter-driven archives remain browser-led. The direct HTTP parser now scores each extracted candidate before accepting the `http_parse` route, drops low-confidence weak matches, tags accepted candidates with `http_parse` provenance, stops pagination when a repeated anchor fingerprint shows the crawl is looping through duplicate content, recovers report cards from custom web-component payloads such as `link="{...href...}"` plus `teaserHeader="{...headline...}"` when a publisher renders zero visible `<a>` tags in the raw HTML, and can also recover WordPress resource archives that populate cards only through `wp-admin/admin-ajax.php` by detecting the page's AJAX config and replaying the matching archive action directly. The browser route itself uses deterministic rendered-DOM traversal instead of relying on free-text LLM extraction: it waits for the page to hydrate, dismisses cookie banners by clicking only inside visible cookie/consent containers instead of generic page-wide buttons, performs a deterministic feed-hydration scroll before each extraction pass, primes the page before the first archive-state read so below-the-fold tabs and pagers are visible, treats smaller archives with a few substantial card links as real inventory surfaces instead of requiring 12+ visible anchors, expands generic archive-preview CTAs such as `View all`, `Explore all library entries`, and similar archive/library buttons when the publisher first lands on a truncated preview instead of the full archive, closes stray `about:blank` / new-tab placeholder windows opened by the local browser runtime so they cannot steal focus and freeze discovery, resets empty result sets when a page exposes generic `Reset all filters` / `Clear filters` controls, expands `Load more` pagination (including anchor-styled controls like Bain’s `a.btn` CTA), treats same-page DOM growth after a load-more click as real pagination progress even when the URL does not change, ignores duplicate same-URL load-more states when the candidate set has stopped changing so inert end-of-feed states do not churn snapshots, prefers the `Load more` control attached to the currently extracted candidate surface when a page exposes multiple unrelated result areas (for example Algolia), stops following generic `Show more` controls once they are no longer attached to the report inventory surface, clicks button-based pagers like Adobe’s bottom `Prev/Next` control, also recognizes simpler `Page X of Y` plus `Next` pagination patterns when numeric chips are absent, stops cleanly when visible result ranges show the final page (for example `190 - 194 of 194 results`), iterates report-focused tab groups generically when a publisher exposes tabs such as `Research` / `Reports` / `White papers`, only auto-follows a discovered "report listing" route when that route itself still looks like an archive/listing URL rather than a single detail page, accepts archive-card links on real archive surfaces even when the destination host differs from the publisher apex if the card itself is clearly report-like, resolves relative links back to the original insights host when the browser runtime drifts onto a mirrored host, prefers explicit on-page report filters when a publisher exposes them (for example GfK), guards against archive drift by navigating back to the requested archive when the browser lands on a single detail page instead of the inventory surface, falls back to parsing the browser's rendered HTML when visible-anchor extraction returns nothing, now also treats a browser result that only rediscovers the archive root itself as structurally empty so HTTP supplement/recovery can still run, mines those rendered HTML component payloads when the supplement contains structured `link` and headline attributes instead of anchor tags, retries the original requested URL once when the browser drifts onto a different apex host before inventory extraction succeeds, falls back to direct HTTP parsing when the browser route fails with a retryable timeout or runtime error, still falls back to HTTP when the pagination cap is hit immediately, but now treats multi-page archives that already produced real candidates as bounded browser successes instead of hard failures, and tags returned candidates with route provenance such as `browser_dom`, `browser_rendered_html_supplement`, `http_supplement`, or `http_parse_wordpress_ajax` so the completion logs show how each run was actually sourced. Candidate title extraction is also biased toward card headings when a whole card's text includes author/date/read-more chrome, and it now falls back to surrounding card text for generic CTA-only links like `Read now` / `Learn more`, which keeps `report_sources.report_name` closer to the actual asset title on card layouts that do not use semantic heading tags. The direct HTTP parser now treats a structurally empty report set as a non-retryable `publisher_inventory_http_empty` outcome so the orchestrator can move on to the stronger browser route without wasting retry budget. The default `publisher_discovery.pagination_max_pages` is now `75`, and the default browser traversal timeout is now `360` seconds, which is enough for deeper real report archives such as Quid while still keeping a bounded crawl. The diff output includes the inventory page number where each new report link was found. Before any new diff item is written into `paths.reports_db` table `report_sources`, it first passes OpenAI candidate screening from `publisher_discovery.candidate_screening`, then a deterministic landing-page quality check from `publisher_discovery.candidate_quality_check`. The default base screening model is `gpt-5-nano` with the default `temperature: 1.0`; dynamic screening now targets fewer, larger batches on deep archives, caps those dynamic batches at `35` items, truncates long titles in the prompt to keep token growth bounded, deterministically rejects obvious academy/support/webinar/video/training/editorial collection URLs before any LLM call, rejects collection-root hub URLs such as bare research/archive landings before they can crowd out real detail assets, deterministically accepts obvious report-detail URLs such as deep `/reports/`, `/whitepaper/`, `/ebooks/`, `/guide/`, `/fact-sheet/`, `/report_pages/`, strong direct-detail source URLs, and slugged report-style leaf URLs like `...-report` or `...-atlas`, treats query-string document URLs by their resolved path rather than raw string suffix alone, preserves strong editorial report-detail pages on mixed-content hubs when the path and title both indicate a real report asset, and no longer collapses distinct same-run assets just because multiple cards reuse generic CTA titles such as `Download the report` or `Learn more`. The screening prompt rejects publisher self-congratulatory accolade pieces such as "named a Leader" / "top rated" analyst-marketing pages, the screening generator applies a deterministic hard rejection for obvious publisher-success marketing titles even if the model accepts them, including medal/award style variants, collapses duplicate same-run candidates so repeated promoted tiles are queued only once, and repairs missing per-candidate LLM decisions in bounded single-item follow-up calls so large inventories do not hang or fail when the model omits one URL from a batch. The landing-page quality check then fetches the approved destinations in parallel and keeps only substantial report-like assets: direct PDFs, gated report pages, paid/publication report pages, printable long-form report pages, structured infographic/snapshot-style report pages under real report archives, slug-signaled ebook/report/guide/fact-sheet detail pages that expose real asset terms without editorial framing, dedicated report/research/whitepaper/ebook/benchmark/study/outlook/playbook pages with real document structure, and the stronger mixed-content editorial detail pages now rescued by the screening layer. It now also tolerates three bounded non-dead verification failures for already screened report-like assets: anti-bot challenge pages such as `Security Checkpoint`, transient fetch timeouts or transient HTTP statuses such as `429` on real report pages, and protected `403` responses on direct documents or report-like landing pages that still carry strong report signals; but those recovery paths no longer rescue obvious case-study or customer-story URLs, and they still reject bot-protected pages whose source title is explicitly article-labeled. It rejects dead links, missing pages, generic blog/news/article/expert-view templates whose only positive signal is a generic `report` label, informational `how to` / `what is` pages that only look report-like because they mention `reporting`, case-study or customer-story pages, legal practice-area guides, report microsite section pages such as `Conclusion`, `Executive summary`, or nested report child URLs like `/.../innovation`, research-announcement pages that only summarize a study without exposing the asset itself, generic finance/editorial section routes such as `/company-insights/`, `/market-insights/`, `/market-outlook/`, `/markets-explained/`, generic podcast/webcast/roundtable-style editorial pages even when their titles include report-like words, consumer self-service credit/report product pages that look like downloadable assets only because they advertise gated report access, and generic newsletter/contact-sales pages, and it does not let generic commercial or purchase signals rescue those editorial, self-service, or case-study routes unless the page also looks like a real report asset. It upgrades weak tile titles such as `Download report` or `Learn more` from the landing page H1 or document title before persisting the candidate. Transparency reports are no longer treated as compliance pages purely because of that phrase, so substantive report assets such as tax or PRI transparency reports can survive qualification when the rest of the page looks like a real document flow. Snapshot state is also protected against raw browser drift: if a rerun changes the raw snapshot but every raw-only delta candidate is rejected before qualification, or every screened delta candidate dies in landing-page verification while an earlier canonical snapshot already exists, the orchestrator keeps the previous snapshot canonical instead of overwriting it with noise; and on first-run archives that produce raw candidates but no qualified report assets, the run is recorded as `passed:no_report_assets` without uploading a noisy snapshot or queueing `report_sources`. The April 9, 2026 live gate confirmed the validated behavior on three distinct publishers: Capgemini as a direct-detail short-circuit success, Bain as a filter-heavy archive success, and Cardlytics as a mixed-content qualified-asset success with a stable remembered-route rerun.

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

Publisher inventory state now persists both the legacy free-text route summary and two typed memory payloads on the `publishers` row:

- `inventory_route_trace_json`
- `inventory_scenario_summary_json`

A dedicated `publisher_inventory_candidate_recovery_cache` table also stores deferred recovery outcomes for challenge/protected/transient candidate failures keyed by normalized publisher URL plus canonical candidate URL.

The three rollout flags now default to `true` in `src/config/app.yaml`:

- `enable_deferred_candidate_recovery`
- `enable_structured_route_reuse`
- `enable_preflight_classifier_and_direct_detail`

That default is deliberate and is validated by the April 9, 2026 live gate on Capgemini, Bain, and Cardlytics.

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
- `src/ui/app_pages/`: bounded page modules for overview, core operations, publisher operations, QA, observability, and configuration.
- `src/ui/settings_page.py`: config studio for `app.yaml`, operational YAML/JSON assets, prompt files, and auth/source status.
- `src/ui/run_control.py`: Streamlit-facing helpers for launching, polling, listing, canceling, and retrying persisted UI runs.
- `src/orchestrators/ui_run_control_orchestrator.py`: background run orchestration over local worker processes plus registry persistence.
- `src/services/process_service.py`: canonical local-process boundary for launch/poll/output/terminate.
- `src/services/run_registry_service.py`: SQLite-backed run registry persisted beside the state DB.
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
- `Observability`: Cost & Usage, Logs & Live Events, System & Storage, Developer & Test Tools
- `Configuration`: Settings & Prompts

Design and behavior highlights:

- Long-running workflows launched from Streamlit now run through the persisted UI run registry instead of blocking the browser session inline. The Run Center can inspect, cancel, and retry tracked jobs.
- The overview and Run Center now use card-based dashboard composition with bordered KPI rows, tighter run/history tables, and selected-run context that carries into observability pages.
- Workflow coverage now includes publisher discovery, report download, acquisition audit, publisher sync, and Drive OAuth/auth visibility in addition to ingest, candidate extraction, cover generation, publish, taxonomy, QA, and observability pages.
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

- OpenAI boundary: only `src/services/openai_service.py` constructs `OpenAI(...)` clients; all provider request/response and shared error/cost behaviors are centralized there. Vector-store create/upload/attach/status/update operations also share one internal scaffolding path for client init, structured service logs, and typed provider-error mapping while preserving explicit request/response contracts per operation.
- Vector stores: `src/services/vector_store_service.py` handles create/upload/attach/status/wait orchestration and metadata shaping, delegating provider API calls to `openai_service`; used by vector-mode generators.
- Analysis uses vector_store only; `ANALYSIS_MODE`/`USE_VECTOR_STORE` toggles are no longer needed.
- Evidence packs: `src/generators/evidence_pack_generator.py` is the entrypoint, and `src/generators/evidence_packs/*.py` contains the per-pack strategy modules used for pack metadata and normalization. Packs use `src/prompts/report_vs/**` and write JSON to `out/<report-slug>/report_analysis/*.json`; `doc_map` runs first and remaining packs run in parallel with process-wide rate limiting via `ingest.evidence_packs.*`. Validation uses strict per-pack schemas (`scope_pack`, `methods_pack`, `findings_pack`, `limitations_pack`, `quote_candidates_pack`) plus optional variety-pack schemas (`key_metrics_pack`, `risk_register_pack`, `recommendations_pack`, `contradictions_pack`).
- Analysis-pack persistence: `src/services/report_analysis_store_service.py` validates schema-backed packs before writing them to disk. Packs without a registered schema still persist normally, while invalid schema-backed payloads fail fast and are not written.
- Artifacts: `src/generators/artifact_generator.py` writes `artifacts.json` under the same analysis path, parallelizing independent steps with dependency ordering and process-wide rate limiting via `ingest.artifacts.*`.
- Cost ledger: `src/services/cost_ledger_service.py` appends JSONL entries for every LLM call and writes daily rollups (`./out/cost-ledger.jsonl`, `./out/cost-daily.json`) using per-model pricing from config. Daily rollups cache ledger file state in `cost-daily.json` so normal append-only writes update aggregates incrementally, while rewritten/amended ledgers fall back to a full rebuild.


## Pipeline Review Notes

- Discovery/download quality review (2026-03-30): `docs/quality/report-discovery-download-review-2026-03-30.md`.
- Download success playbook (2026-04-07): `docs/quality/report-download-success-playbook-2026-04-07.md`.
