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
- Batched state prefilter: Drive-list skip checks for `(file_id, md5)` are grouped into batch SQLite queries to reduce per-file DB round trips; per-file state checks run only when the final resolved md5 differs from the Drive md5.
- Low-text resilience: text density heuristics detect PDFs with little/no extractable text and emit explicit "not available from text" artifacts + HTML notices instead of blank sections.
- Artifact reference robustness: artifact evidence IDs are canonicalized against docpacks before validation (supports comma/list-like model output and quote aliases such as `quote_1 -> q1`), preventing TL;DR/insights/quotes dropouts caused by malformed IDs.
- Deterministic TOC structure: artifacts now include authoritative `toc_entries`, built directly from eligible `doc_map.sections` in source order. Legacy `toc_topics` and `toc_topics_expanded` are compatibility projections derived from `toc_entries`, and HTML renders the Covered topics section from those deterministic entries.
- TOC integrity guard: validation now enforces one-to-one coverage between eligible DocMap sections and generated TOC structure, flags missing/duplicate/stale/out-of-order entries with machine-readable repair metadata, and targeted regeneration rebuilds `toc_entries`, `toc_topics`, and `toc_topics_expanded` deterministically from DocMap without another model call.
- HTML digest quality: rendered HTML now uses semantic sections (`header/main/section`), premium split hero layout, sticky glass navigation with scrollspy + reading progress, reveal animations (with reduced-motion fallback), signal-style insight cards, editorial quote cards, and long-text chunking for generated prose.
- Figure UX: rendered digests now include a template-native figure carousel with prev/next controls, keyboard and swipe support, thumbnail rail, slide counter, and fullscreen lightbox.
- Per-image figure captioning: after artifacts are generated, the pipeline can run a fail-open multimodal captioning pass for each final cropped figure asset using the image plus compact report context (`title/publisher/region/time period`, TL;DR + executive summary, nearest DocMap section, top findings/claim-evidence highlights, and figure-local signals). Captions are stored per slide, rendered in the carousel, and audited in `report_analysis/figure_captions.json`; on failure the pipeline keeps rendering with legacy/detected/placeholder fallback captions.
- OpenAI image-call compatibility: crop-refine image requests to the Responses API now omit known unsupported params (e.g., `temperature`/`seed` on `gpt-5*`) preflight and still retain fallback retry-without-param handling for unknown model/param mismatches.
- OpenAI service consolidation: `src/services/openai_service.py` is the single OpenAI client boundary (request/response parsing, cost ledger writes, and provider error normalization). Other modules route OpenAI calls through it.
- Refactor simplification layer: shared coercion/list-normalization helpers now live in `src/utils/coercion.py`, orchestrator retry wrappers are centralized through `retry_orchestrator.run_step_with_default_policy`, and duplicate WordPress term ensure logic is consolidated into a shared internal helper.
- Ops tooling cleanup: duration diagnostics now share one implementation in `scripts/duration_tools.py` (legacy entry scripts delegate to it), and legacy Streamlit config cleanup flags (`ingest.debug_candidate_gallery`, `analysis.compare`) were removed from the structured editor path.
- Figure quality gate: candidate visuals now pass deterministic prefilters plus LLM thresholds (overall + quality + insight + data), kind-split ranking (tables and charts ranked independently), adaptive GPT crop refinement, and strict final cropping. Per-kind caps now ensure balanced outputs (up to `rank.selected_max` tables and `rank.selected_max` charts). If strict selection yields no final slices, the renderer now falls back to the best available pre-cropped candidate visuals and still enables the figure section whenever a primary extracted figure image exists.
- Candidate extraction split: `pdf_service.collect_candidates` remains the canonical PDF-candidate service boundary, while table heuristics and chart/infographic heuristics now evolve in separate internal capability modules under `src/services/_pdf/` so each flow can be upgraded without creating competing service entrypoints.
- Contextual table crop composition: stream-table candidates are first shrunk to the dominant tabular row cluster on the page, then build their final bbox from that structural core plus nearby title/note/source/statlink text blocks, while explicitly stopping at page-number/header noise and downstream body paragraphs or next-section headings. The table crop composer also restores clipped right-edge columns from overlapping tabular text, can recover clipped first columns from dense tabular text blocks when lattice extraction only catches the inner columns, preserves explicit `Table`/`Exhibit` title bands above the body, extends real overlapping footnote blocks below the body, and keeps dense infographic value panels that behave like compact tables instead of prose. When a full-width table is split across two adjacent pages, crop rendering can now prepend the explicit title band from the first page onto the continuation crop and append the footnote block from the continuation page onto the first crop, but only for strong same-table continuation pairs. This tightens valid table crops without relying on report-specific keywords.
- Prose-box rejection: bordered narrative callouts, long boxed paragraphs, bullet lists, and numbered text panels with little or no row-value signal are now rejected during table validation instead of being emitted as table candidates.
- Candidate window control: after deterministic prefiltering, `rank.max_candidates` is now applied with kind-aware truncation so one noisy flow cannot crowd the other out before ranking. The same prefilter also rejects obvious table false positives such as figure/box text blocks and reference-style text blocks before crop generation and ranking.
- Crop-refine edge guard: final LLM-refined bboxes now apply conservative padding plus text-edge correction so partial cut letters/lines at crop borders are automatically expanded (or trimmed if only tiny accidental overlap), reducing visibly clipped figure outputs.
- Strict crop output safety: final crop filenames are now candidate-ID based, preventing table/chart overwrite collisions when strict table and strict chart crops are written to the same `slices/` directory.
- Strict crop spillover control: strict crop modes additionally tighten bottom-edge partial text spillover so body paragraph fragments below a figure/table are trimmed while preserving the main visual content.
- SEO-ready HTML: rendered digests include shortened `<title>` handling, `meta description`, Open Graph/Twitter cards, optional canonical URL, JSON-LD (`Article`) structured data, explicit image `width`/`height` attributes to reduce CLS, and automatic `noindex,nofollow` on low-content fallback pages.
- Vector store is the default and only analysis path; legacy local_text prompt stuffing has been removed now that vector_store is validated.
- Taxonomy extraction now separates report-level signal tags from portal categorization: the prompt returns `primary_tags`, `secondary_tags`, a merged `taxonomy` list, and per-tag `tag_evidence` as metadata for search/filtering, while portal categories are assigned separately from report context using category definitions in `src/config/category-mappings.yaml`.
- HTML metadata chips normalize slug-style taxonomy values into readable labels (e.g., `ai-in-retail` -> `AI in Retail`) with acronym preservation loaded from `src/config/html-tag-acronyms.yaml`.
- Publish file ID resolution is DB-first: publish/publish-queue resolve `file_id` from reports metadata (`html_path -> file_id`) and fall back to HTML parsing only when mapping is unavailable.

---

## Architecture Overview

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
- `cost_reporting_orchestrator.py`: filtered cost report + rollup orchestration.
- `ops_dashboard_orchestrator.py`: dashboard snapshot aggregation (reports/state/lock/storage).
- `candidate_extraction_orchestrator.py`, `cover_image_orchestrator.py`, `recategorize_orchestrator.py`, `wp_category_update_orchestrator.py`: feature-specific workflows.

## Local WordPress Dev
WordPress local development, packaging, smoke tests, and sync workflows are documented in `Wordpress/README_WORDPRESS.md`.

For the local WordPress instance at `C:\Users\Михаил\Studio\marker-lense`, do not symlink the block theme into the local site. Some local stacks resolve theme symlinks through `/internal/symlinks/...`, which breaks `theme.json` loading in the web runtime.

Use the repo sync script instead:

```powershell
powershell -ExecutionPolicy Bypass -File .\Wordpress\scripts\sync-local-wordpress.ps1 `
  -LocalWpPath 'C:\Users\Михаил\Studio\marker-lense'
```

For near-realtime updates during theme/plugin development:

```powershell
powershell -ExecutionPolicy Bypass -File .\Wordpress\scripts\sync-local-wordpress.ps1 `
  -LocalWpPath 'C:\Users\Михаил\Studio\marker-lense' `
  -Watch
```

The WordPress subproject now uses a consultancy-style block theme with:

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
- a restrained motif/micro-interaction layer in `assets/css/theme.css` that now uses explicit shared hooks (`.ml-card`, `.ml-chip`, `.ml-link-arrow`, `.ml-button`), a tiny node-ended section rule, hero/briefing-band node motifs, calmer shared card hover states, quieter editorial link arrow movement, and consistent reduced-motion handling without changing module structure
- refined header/footer shell polish in `assets/css/theme.css` so the two-row header now reads as one integrated premium surface with a stronger brand lockup, calmer nav/current-state treatment, a more attached archive-search row, polished CTA states, and aligned footer navigation/copy without changing IA or template hierarchy
- a final responsive premium pass in `assets/css/theme.css` at `1100px` and `782px` so the header shell, hero, featured digest, signals, themes, publishers, reports grid, methodology cards, briefing band, and footer preserve hierarchy and readable spacing on tablet/mobile without changing module order or data flow
- `assets/js/reveal.js` now uses a lower IntersectionObserver threshold on compact viewports so tall homepage sections like Latest Reports still reveal correctly on mobile instead of remaining hidden
- a final finish-quality consistency pass in `assets/css/theme.css` that consolidates shared card/button/chip values, restores the missing signals-card hover treatment, aligns editorial link/focus behavior, refreshes the briefing-band/footer control surfaces, and fixes header-search shell alignment without changing query or template logic
- a richer `[ml_report_browser]` archive/search/category/publisher experience
- imported publisher profile support from Notion (`[ml_publisher_profile]`, publisher insights/homepage/icon term metadata, and `Wordpress/config/publisher-profiles.json`)
- redesigned trust and conversion pages (`About`, `Methodology`, `Contact`, `Submit a Report`)
- a native PowerShell plugin packaging script at `Wordpress/scripts/build-plugin-zip.ps1` so Windows builds do not depend on `bash.exe`/WSL
- automatic backfill of legacy report publisher/meta projections during plugin upgrade/runtime so homepage authority surfaces recover without manual post edits

To sync publisher directory/profile content from the Notion `REPORT SOURCES` workspace snapshot into WordPress term pages, run:

```bash
bash Wordpress/scripts/sync-publisher-profiles.sh
```

The sync reads `Wordpress/config/publisher-profiles.json` and updates each `ml_publisher` term with its Notion-derived homepage, self-presentation text, insights link(s), icon source, and source page identifiers.
When those provisioning scripts fall back to REST, they now auto-discover both `/wp-json/` and `?rest_route=/` API roots and honor `WP_SSL_VERIFY` / `WP_CA_BUNDLE_PATH` for hosted sites with custom TLS.

Use this root README for pipeline architecture and CLI usage; use the WordPress subproject README for all theme/plugin operations.

## Configuration (YAML + .env)

Primary config: `src/config/app.yaml`. Missing values can be provided via `.env` (loaded by `config_service`). Secrets must come from environment variables.

For dev wiring, use `src.services.config_service.build_ingest_settings` with `IngestSettingsBuildRequest` to adapt `AppSettings` into `IngestSettings` without hand-copying fields; new config keys are picked up automatically.

Key fields and env overrides:

- Paths: `paths.output_dir` (`OUTPUT_DIR`, default `./out`), `paths.cache_dir` (`CACHE_DIR`, default `./cache`), `paths.state_db` (`STATE_DB`), `paths.reports_db` (`REPORTS_DB`), `paths.category_mappings` (defaults to `src/config/category-mappings.yaml`; supports context-first category profiles via `definition`, `include_when`, and `exclude_when`, plus retained taxonomy-signal groups such as `core_tags`, `supporting_tags`, `descriptor_tags`, `generic_tags`, and `negative_tags`), `paths.html_tag_acronyms` (defaults to `src/config/html-tag-acronyms.yaml`).
- Ingest: `ingest.google_sa_path` (`GOOGLE_SERVICE_ACCOUNT_JSON`), `ingest.gdrive_folder_id` (`GDRIVE_FOLDER_ID`), `ingest.openai_model` (`OPENAI_MODEL`), `ingest.batch_limit` (`BATCH_LIMIT`, default 20), `ingest.worker_limit` (`INGEST_WORKER_LIMIT`, default 2), `ingest.report_worker_limit` (`INGEST_REPORT_WORKER_LIMIT`, default 2), `ingest.temperature` (`TEMPERATURE`, default 1.0), `ingest.timeout_seconds` (`OPENAI_TIMEOUT_SECONDS`, default 600), `ingest.lock_ttl_seconds` (`INGEST_LOCK_TTL_SECONDS`, default 7200), `ingest.contents_page.*` (keywords, max_pages, min_headings, render_dpi, preview_enabled), `ingest.evidence_packs.parallel_workers` (`EVIDENCE_PACK_PARALLEL_WORKERS`, default 3), `ingest.evidence_packs.global_max_in_flight` (`EVIDENCE_PACK_GLOBAL_MAX_IN_FLIGHT`, default 2), `ingest.evidence_packs.global_min_interval_ms` (`EVIDENCE_PACK_GLOBAL_MIN_INTERVAL_MS`, default 250), `ingest.evidence_packs.doc_map_max_attempts` (`EVIDENCE_PACK_DOC_MAP_MAX_ATTEMPTS`, default 3), `ingest.evidence_packs.doc_map_retry_delay_ms` (`EVIDENCE_PACK_DOC_MAP_RETRY_DELAY_MS`, default 500), `ingest.evidence_packs.registry` (`EVIDENCE_PACK_REGISTRY`, comma-separated), `ingest.evidence_packs.enable_new_variety_packs` (`EVIDENCE_PACK_ENABLE_NEW_VARIETY_PACKS`, default `false`), `ingest.artifacts.parallel_workers` (`ARTIFACT_PARALLEL_WORKERS`, default 4), `ingest.artifacts.global_max_in_flight` (`ARTIFACT_GLOBAL_MAX_IN_FLIGHT`, default 2), `ingest.artifacts.global_min_interval_ms` (`ARTIFACT_GLOBAL_MIN_INTERVAL_MS`, default 250), `ingest.validation.regeneration_max_attempts` (`VALIDATION_REGENERATION_MAX_ATTEMPTS`, default `3`, minimum `1`).
- PDF OCR fallback: `ingest.pdf_text.ocr_fallback.enabled`, `ingest.pdf_text.ocr_fallback.model` (default `gpt-5-mini`), `ingest.pdf_text.ocr_fallback.timeout_seconds`, `ingest.pdf_text.ocr_fallback.prompt_namespace`, `ingest.pdf_text.ocr_fallback.cache_enabled`, `ingest.pdf_text.ocr_fallback.chunk_page_count` (default `8`). OCR calls go through `src/services/openai_service.py` using the OpenAI Responses API. This fallback only runs when the native text gate would otherwise return `pdf_text_unextractable`; low-density but still extractable PDFs stay on the normal path.
- Figure captions: `ingest.figure_captions.enabled`, `ingest.figure_captions.temperature`, `ingest.figure_captions.timeout_seconds`, `ingest.figure_captions.prompt_namespace` (default `report_vs/figure_caption`), `ingest.figure_captions.max_chars` (default `500`). The bundled `src/config/app.yaml` enables this phase by default. Model resolution follows `openai_models.report_vs/figure_caption` first, then falls back to `ingest.openai_model`. The phase is fail-open: primary figures fall back to the legacy shared caption, secondary figures fall back to detected captions or the existing placeholder label.
- Publish: `publish.wp.site_url` (`WP_SITE_URL`), `publish.wp.username` (`WP_USERNAME`), `publish.wp.post_status` (`WP_POST_STATUS`, default `publish`), `publish.wp.post_type` (`WP_POST_TYPE`, fallback default `ml_report`; this repo currently sets `posts` in YAML), `publish.wp.ssl_verify` (`WP_SSL_VERIFY`, default `true`), `publish.wp.ca_bundle_path` (`WP_CA_BUNDLE_PATH`, optional CA bundle for self-signed/private certs), `publish.validation.policy` (`PUBLISH_VALIDATION_POLICY`, default `block`).
- This repo currently publishes into core WordPress posts with `publish.wp.post_type=posts`. The bundled WordPress plugin now treats digest posts with a recovered digest contract (`ml_is_digest=1` and, when available, `ml_file_id`) as first-class report content across archive/home surfaces, so report cards and intelligence modules still work even when the underlying post type is `post`.
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
- `WP_APP_PASSWORD` or `WP_BEARER_TOKEN` (publishing)
- `WP_POST_TYPE` (optional publish endpoint override; current YAML sets `posts`, code fallback is `ml_report`)
- Optional provider keys (e.g., `MINERU_API_KEY`) if used.

WordPress HTTPS note:

- Leave `publish.wp.ssl_verify` enabled in normal environments.
- For self-signed/private certificates, prefer `publish.wp.ca_bundle_path` or `WP_CA_BUNDLE_PATH` to trust a specific CA bundle.
- As a last resort for local/admin environments with a self-signed certificate, set `publish.wp.ssl_verify: false` (or `WP_SSL_VERIFY=false`) to disable TLS verification for WordPress REST calls.
- When `publish.wp.ssl_verify` is `false`, `src/services/wordpress_service.py` suppresses `urllib3`'s `InsecureRequestWarning` for those WordPress calls so CLI output stays readable; the connection is still unverified and should be treated as insecure.

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
   - Before doing any work, ingest probes `state_db` and `reports_db` for write access (SQLite `BEGIN IMMEDIATE`). If either DB is locked, the run exits early with `db_locked` to avoid partial outputs.
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
      - Evidence packs are generated via `src/generators/evidence_pack_generator.py`, which now stays as the orchestration entrypoint while per-pack normalization/metadata live under `src/generators/evidence_packs/*.py`. The config-driven registry (`ingest.evidence_packs.registry`) and optional variety expansion (`ingest.evidence_packs.enable_new_variety_packs`) cover `doc_map`, `scope`, `methods`, `findings`, `limitations`, `quote_candidates`, and optional `key_metrics`, `risk_register`, `recommendations`, `contradictions`. `doc_map` runs first as a hard gate; remaining packs run in parallel (`ingest.evidence_packs.parallel_workers`). Global evidence-pack rate limiting is applied at the orchestrator boundary (`src/orchestrators/report_pipeline_orchestrator.py`) using `ingest.evidence_packs.global_max_in_flight` + `ingest.evidence_packs.global_min_interval_ms`.
      - Artifacts are generated via `src/generators/artifact_generator.py` using a dependency-aware parallel DAG: `toc` + `summary` + `insights_candidates` + `quotes` in parallel, then `insights_final`, then `expert_comment` + `linkedin_post` in parallel. Independent steps use `ingest.artifacts.parallel_workers`. Global artifact rate limiting is applied at the orchestrator boundary (`src/orchestrators/report_pipeline_orchestrator.py`) using `ingest.artifacts.global_max_in_flight` + `ingest.artifacts.global_min_interval_ms`. By default these artifact model calls run closed-context (`chat_json`); vector retrieval is opt-in via `analysis.artifacts_use_vector_store`.
      - Targeted regeneration is handled by `src/generators/report_regeneration_generator.py`, which performs exactly one regeneration pass against mapped failing artifact families and reuses the same artifact normalization, schema validation, evidence-reference validation, and storage behavior as the main artifact generator.
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
      - **Candidate extraction**: `pdf_service.collect_candidates` finds chart/table regions, parallelizes page-level extraction (bounded by `ingest.report_worker_limit`), excludes the detected contents/index page from candidate output when present, and now routes table extraction through `src/services/_pdf/table_candidates.py` and chart/infographic extraction through `src/services/_pdf/visual_candidates.py` while keeping `src/services/_pdf/figures.py` as the single public coordination boundary. Stream-table bboxes are first shrunk to their dominant row cluster, then composed contextually with attached title/note/source blocks and hard stop rules for margin noise, body text, and next-section headings. Stream-table note attachment now falls back to nearby text blocks as well, which preserves mixed legend-plus-footnote footer blocks that do not start with `Note:` on the first line. The stream-table crop composer now also strips top page-number markers, preserves isolated trailing numeric rows that still belong to the same table, restores clipped right-edge columns when overlapping text still behaves like the same tabular grid, can recover clipped first columns from dense lattice-body text blocks, keeps wrapped footnote continuation lines, extends real overlapping note blocks below the body, preserves explicit `Table ...` / `Exhibit ...` title bands above the body, clamps internal `Table ...` titles away from preceding paragraph text, and trims internal `References`/next-heading spillover from the bottom of a crop. Candidate table crop rendering now trims top-corner page numbers again after padding so continuation-page header bands can keep a little top slack without reintroducing margin page numbers, and it can conservatively stitch a title strip / footnote strip across adjacent full-width continuation pages when the second page is clearly the same table. Table validation also rejects section-list / chapter-opener layouts, bibliography/reference blocks, boxed prose snippets, and small chart-like figure fragments that appear inside a wider figure/infographic context, while still allowing dense infographic value panels when their text behaves like a compact table rather than prose. After bbox expansion, table candidates run one more containment dedupe pass so broad stream shadows collapse into the final expanded crop that will actually be saved. Chart candidate bboxes now trim corner page-number markers on either side of the header, recognize `Infographic <n>` captions in the visual flow, tolerate dense label/value text when the clipped region still looks chart-like rather than prose, and allow dense infographic composites when their text still behaves like a visual label cloud rather than narrative prose. Oversized draw candidates are clamped to the next figure caption or section heading below when a page contains multiple visuals, and page-local chart IDs now keep the legacy-accepted visuals first so newly recovered charts append after existing IDs instead of renumbering older page matches. Chart note/source handling still reserves crop padding when clamping below note/source/statlink blocks, preventing candidate crops from reintroducing the next paragraph line.
       - **Known limitation: OECD-family heuristics**: the current extraction stack is mostly layout-based, but a few transitional heuristics still reflect the OECD Economic Outlook family used for tuning. In production code, note handling explicitly recognizes `StatLink`, and bibliography false-positive rejection still uses OECD-style reference terms such as `oecd publishing` and `publishing, paris`. These heuristics are documented as temporary and should be generalized so candidate extraction is fully publisher-agnostic.
     - **Candidate prefilter + ranking**: deterministic prefilter removes obvious low/no-data fragments, table figure/box text-block leaks, and reference-style table blocks, then applies kind-aware truncation before `rank_service` scores candidates via LLM (overall + quality + insight + data + keep/reject_reason; model resolves from `openai_models.rank_candidates` if set, else `rank.model`, then `ingest.openai_model`).
     - **Candidate fallback policy**: fallback crops no longer revive candidates that already failed the configured rank thresholds; fallback is limited to threshold-passing ranked candidates first, then remaining deterministic prefilter survivors by kind-balanced caps.
     - **Adaptive crop refinement**: ambiguous candidates call `rank_candidates/crop_refine` with page image context; obvious pass/reject candidates skip LLM. Ambiguous page renders are pre-rendered in parallel and ambiguous LLM refinement calls run in bounded parallel mode. Crop refinement now runs in two passes (coarse -> finalize) to improve edge precision and reduce clipped text artifacts.
     - **Strict cropping**: final crops are routed by visual kind (`table_strict` for tables, `chart_strict` for charts) so each class uses tailored border trimming instead of a monolithic crop mode.
    - **Zero-pass behavior**: if strict candidate selection produces no final slices, report generation falls back to ranked/prefiltered candidate crops (bounded by the same per-kind caps). If no crop fallback is usable but `extract_best_figure` already produced a primary figure image, the HTML still renders a primary-only figure section instead of hiding it.
     - **Preview rendering**: `pdf_service.render_preview` renders the first page to PNG.
      - **Cover image generation**: `cover_image_generator` resolves style from `cover-styles.yaml` using the report’s first category (falls back to `default` for styling only), while the rendered label text, title, publisher, time period, and region always come from report metadata in the DB. Cover assets are now written into the canonical report folder (`out/<report-slug>/assets/`) with length-bounded, file-id-suffixed filenames via `src/utils/cover_path_utils.py`; Streamlit preview lookup follows the same path logic with legacy-path fallback.
    - **HTML rendering**: `render_service` generates the final HTML digest with premium template UX (split hero, sticky nav + progress, section accents, signal cards, editorial quotes, figure carousel/lightbox), plus SEO metadata (OG/Twitter/canonical/JSON-LD) and explicit image dimensions. In the **Key data insights** section, cards now render only the main insight sentence (metric/source sub-lines are suppressed).
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

Retry behavior is centralized in `src/orchestrators/retry_orchestrator.py` and reused by ingest, candidate-extraction, publish, and report-pipeline orchestrators: only retryable `AppError` instances are retried, with bounded attempts and linear backoff (`1s`, `2s`, ... by default, plus optional jitter support).

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

Run tests locally:

```bash
pytest
```

`pytest.ini` sets `pythonpath = .` so `src.*` imports resolve without exporting `PYTHONPATH`.
Default runs exclude `integration`-marked tests (`addopts = -m "not integration"`).
Batch ingest and report-generator boundary tests now inject explicit dependency dataclasses (`IngestBatchDependencies`, `ReportGeneratorDependencies`) instead of monkeypatching module globals.

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
- `docs/quality/ineffective-choices-top50.md` (repository improvement backlog focused on low-effort/high-impact fixes)

---

## Runtime Requirements

Configuration lives in `src/config/app.yaml` with `.env` fallback for any missing values. Secrets come from environment variables.

- Contents/index detection is configured under `ingest.contents_page` (keywords, max_pages, min_headings, render_dpi).

Required environment variables:

- `OPENAI_API_KEY`
- `WP_APP_PASSWORD` (or `WP_BEARER_TOKEN` if using bearer auth)
- Optional: other provider keys (e.g., `MINERU_API_KEY`), `WP_USERNAME`/`WP_SITE_URL`/`WP_POST_TYPE` if not set in YAML.

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

## Streamlit Cockpit

The repository includes a full Streamlit admin/control panel aligned to `GUI-ARCHITECTURE.md`.
The entrypoint is intentionally thin and now delegates into dedicated UI + generator modules:

- `src/streamlit_app.py`: entrypoint only (page config + handoff).
- `src/ui/streamlit_pages.py`: Streamlit presentation/rendering for sidebar sections.
- `src/generators/streamlit_dashboard_generator.py`: dashboard data assembly and normalization (logs, JSON payloads, validation summaries, lock/state/report snapshots, ledger parsing, directory counts).
- `src/contracts/streamlit_dashboard.py`: dataclass contracts for Streamlit dashboard generator I/O.

Run locally:

```bash
streamlit run src/streamlit_app.py
```

Primary sidebar navigation (14 sections):

1. Cockpit Overview
2. Ingest Control
3. Candidate Extraction
4. Report Command Center
5. Cover Images
6. Analysis & Evidence
7. Validation Center
8. Publishing Control
9. Category Manager
10. Cost & Usage
11. Logs & Live Terminal
12. Settings & Prompts
13. System & Storage
14. Developer & Test Tools (disabled stub)

Design and behavior highlights:

- One dominant task per page with a consistent shell: title + status chip + primary action + filters + main data region + right-side details panel.
- Status chips are normalized to `success` / `warn` / `error` semantics for consistent operational feedback.
- Accessibility/readability defaults: captions are rendered in black and action buttons use a light-blue background for consistent contrast in the main content area.
- Interactive controls (navigation, actions, inputs, selectors) expose concise hover help with usage examples (capped at 1000 characters per tooltip).
- Pages are wired to existing contracts/services/orchestrators as source-of-truth surfaces (DB, files, config, and logs).
- Cockpit overview and publish queue views now use dedicated orchestrators (`ops_dashboard_orchestrator`, `publish_queue_orchestrator`) so UI code stays presentation-focused.
- The logs page supports structured filtering (`run_id`, `task_id`, `span_id`, `event`, `role`, `module`) and includes a terminal-style panel for UI-triggered run output history.
- The **Settings & Prompts** page now includes a full `app.yaml` editor with direct save support (optional timestamped backups), so every config key in `src/config/app.yaml` can be changed from the Streamlit UI.
- The same page now also provides a **Structured Form** tab with field-by-field widgets for all `app.yaml` sections (paths, ingest, rank, publish, analysis, cost, and model maps), designed for non-technical config editing.
- If runtime config validation fails, the UI still opens directly into **Settings & Prompts** so `app.yaml` can be fixed without leaving Streamlit.
- Extracted dashboard business logic is unit-tested in `tests/test_streamlit_dashboard_generator.py`.

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

- OpenAI boundary: only `src/services/openai_service.py` constructs `OpenAI(...)` clients; all provider request/response and shared error/cost behaviors are centralized there.
- Vector stores: `src/services/vector_store_service.py` handles create/upload/attach/status/wait orchestration and metadata shaping, delegating provider API calls to `openai_service`; used by vector-mode generators.
- Analysis uses vector_store only; `ANALYSIS_MODE`/`USE_VECTOR_STORE` toggles are no longer needed.
- Evidence packs: `src/generators/evidence_pack_generator.py` is the entrypoint, and `src/generators/evidence_packs/*.py` contains the per-pack strategy modules used for pack metadata and normalization. Packs use `src/prompts/report_vs/**` and write JSON to `out/<report-slug>/report_analysis/*.json`; `doc_map` runs first and remaining packs run in parallel with process-wide rate limiting via `ingest.evidence_packs.*`. Validation uses strict per-pack schemas (`scope_pack`, `methods_pack`, `findings_pack`, `limitations_pack`, `quote_candidates_pack`) plus optional variety-pack schemas (`key_metrics_pack`, `risk_register_pack`, `recommendations_pack`, `contradictions_pack`).
- Artifacts: `src/generators/artifact_generator.py` writes `artifacts.json` under the same analysis path, parallelizing independent steps with dependency ordering and process-wide rate limiting via `ingest.artifacts.*`.
- Cost ledger: `src/services/cost_ledger_service.py` appends JSONL entries for every LLM call and writes daily rollups (`./out/cost-ledger.jsonl`, `./out/cost-daily.json`) using per-model pricing from config.

## WordPress Rendering Environment
All WordPress subproject details live in `Wordpress/README_WORDPRESS.md`, including:

- plugin/theme structure and contracts
- local Windows sync workflow
- ZIP packaging commands
- provisioning and smoke-test scripts
- archive/directory UX behavior
- ingest-rendering parity details

Keep WordPress-specific implementation guidance centralized in the subproject README to avoid documentation drift.
