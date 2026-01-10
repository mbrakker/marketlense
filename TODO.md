# TODO

1. Upgrade validator to perform semantic comparisons (reduce word-by-word false positives).
   - Current checks in `src/generators/validation_generator.py` rely on substring/regex matching (`_metric_value_supported`, `_contains_token`, `_validate_quotes`) and miss paraphrases/stem variants. Add semantic comparison (embeddings or LLM re-check) against evidence snippets to cut false negatives/positives while keeping schema validation intact.
2. Upgrade all prompts.
   - Prompt namespaces live under `src/prompts/**` (report_generation, report_vs/{doc_map,evidence_packs,artifacts,validate}, rank_candidates). Refresh wording, safety, and output formats; ensure variables match renderer usage in `prompt_service` and bump schema/version hashes for logging.
3. Parallelize report processing.
   - `run_ingest` in `src/orchestrators/ingest_orchestrator.py` processes PDFs serially and blocks on OpenAI calls. Add bounded concurrency per file while keeping lock semantics, and preserve cost ledger/state-db writes without races.
4. Make GPT model selection flexible per prompt call.
   - App-wide model comes from `AppSettings.openai_model` (plus `rank_model`), reused across generators/services. Introduce per-namespace model overrides (e.g., grounding vs. artifacts vs. ranking) and thread them through generator calls to `openai_service`, logging model choice per span.
5. Combine redundant services to reduce excessive service proliferation.
   - PDF I/O is split across `pdf_utils_service`, `pdf_text_service`, `pdf_context_service`, `pdf_contents_service`, and `extract_service` while using the same pypdf/fitz handles. Consolidate into a single PDF service per AGENTS rules (one external system per module) and refactor callers.
6. Update `AGENTS.md`.
   - Embed the service-consolidation rule above and align examples with current module names (PDF, OpenAI/vector store, WordPress). Clarify that thin wrappers and split services (e.g., multiple PDF modules) violate the constitution.
7. Add cost tables.
   - `cost_ledger_service` rolls up JSON and `generate_cost_report` exposes totals, but no tabular artifacts are emitted/published. Add HTML/CLI tables for daily/run rollups and link paths in `README.md`; optionally persist under `out/` for monitoring.
8. Add vector store logging to avoid recreating entries.
   - `vector_store_service.create_vector_store` is called (e.g., in `golden_set_orchestrator`) without persisting IDs; repeated runs create new stores. Record vector_store_id per report in state DB or report store, log reuse vs. create, and respect `analysis.vector_store_keep`.
9. Add categories/tags to vector store records.
   - Vector store metadata is empty/default; no taxonomy or tags from `ReportPayload`/category mappings are propagated. Include categories/regions/time_period as metadata on create/attach so queries can filter and deletion/reuse works by tag.
10. Create a GUI.
    - Only `src/cli.py` exists. Provide a minimal web/desktop UI to trigger ingest/publish, view progress logs, inspect artifacts, cost tables, and vector store status.
11. Add vector store deletion support.
    - No delete API in `vector_store_service`; flag `vector_store_keep` is unused for cleanup. Add delete/prune operations (vector store + files) and orchestrator hooks to avoid orphaned stores.
12. Define and enforce cost limits.
    - Costs are tracked (`cost_ledger_path`, `cost_daily_path`, pricing in `app.yaml`) but not enforced. Add config thresholds (per-run/day) and guardrails in orchestrators before OpenAI calls, with blocking/warning behavior and logging.
13. Refine HTML and deduplicate repeated blocks.
    - `templates/report.html.j2` contains repeated preview/figure handling and inline styling. Extract reusable blocks/macros, de-duplicate preview/gallery logic, and ensure consistent metadata rendering to reduce drift.
14. Refine figure candidates and ranker to avoid low-data images.
    - Current figure selection relies on extracted candidates and ranking (see `figure_service`, `rank_service`, and `extract_service` plus cropping). Add an image analysis step (OCR/content density/heuristics) to filter low-text/low-chart pages, improve table/chart detection and cropping, and feed richer features into the ranker to reduce weak visuals.
15. Add infographics creator for HTML design and LinkedIn posts.
    - Beyond text rendering, there is no infographic generation pipeline. Add a generator/service to produce simple infographics/hero visuals for HTML and LinkedIn artifacts, wired into rendering and artifact generation flows.
16. Support multiple prompts per process for variations/expert roles.
    - Today each step uses a single prompt set per namespace. Add a mechanism to run multiple prompt variants per step (e.g., different expert personas or stylistic variants), collect outputs, and select/ensemble or expose them, while keeping prompt logging/versioning intact.
