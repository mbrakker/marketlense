# Potential TODOs (Combined Improvement Lists)

## Low-Effort / High-Impact Opportunities
1. Pre-check "already processed" using Drive MD5 to skip downloads before cache/IO work.
2. Pass a page-size/limit into Drive listing to stop early and reduce API calls.
3. Cache/reuse the Drive client within a run to avoid repeated client construction.
4. Stream Drive downloads directly to disk to avoid double buffering in memory.
5. Avoid repeated MD5 hashing on cache hits by persisting or reusing known hashes.
6. Skip EOF checks on cache hits (only check after fresh download).
7. Add bounded parallelism in ingest per-file processing.
8. Parallelize evidence pack generation (rate-limited).
9. Preload evidence-pack prompts once per run to reduce repeated filesystem checks.
10. Reuse the contents-page preview when it overlaps with the general preview render.
11. Cache category mappings for the entire ingest run to reduce repeated reloads.
12. Pre-filter candidates before LLM ranking to reduce prompt size and cost.
13. Short-circuit artifact/validation calls when text density is “not available.”
14. Batch state checks to reduce per-file DB calls.
15. Consolidate retry/backoff logic across orchestrators for consistency.
16. Avoid HTML parsing to determine file_id; use report metadata or DB mappings instead.
17. Pass WordPress auth header into publish generator to avoid re-deriving it.
18. Parallelize WordPress media uploads for image-heavy reports.
19. Share category mapping cache between publish and WP-category update flows.
20. Extract validation JSON parsing into a small service/helper for reuse.
21. Audit external scripts/docs for legacy `pdf_*_service` imports after consolidation into `pdf_service.py`.

## High-Impact (No Effort Limits)
1. Parallelize ingest with a bounded worker pool plus idempotent locks.
2. Add async vector-store indexing with background wait/callbacks.
3. Introduce durable, checkpointed pipeline stages to resume mid-run.
4. Centralize LLM orchestration with retry/backoff and circuit-breakers.
5. Batch/parallelize evidence packs with global rate limiting.
6. Create a document-processing service with memoized outputs (PDF info, text, candidates).
7. Stream LLM responses with early validation for faster failures.
8. Model the pipeline as a DAG to parallelize independent steps.
9. Cache compiled prompt templates for faster rendering.
10. Enforce schema validation at each generator stage, not only evidence packs.
11. Add budget enforcement for LLM usage per run/report.
12. Introduce input compression or summarization for candidate ranking.
13. Async image uploads with retryable tasks for WordPress publishing.
14. Move publishing to a durable queue with retry/backoff and idempotency.
15. Expand state DB to track stage artifacts and content hashes for selective reprocessing.
16. Pool PDF resources (PyMuPDF/pypdf) across files to reduce overhead.
17. Centralize retry/backoff policy into shared infrastructure.
18. Extract a report-assembly service to simplify generator responsibilities.
19. Add a low-text/low-evidence fast path to skip expensive LLM steps.
20. Add feature flags per pipeline stage for safe rollouts and cost control.
