# Potential TODOs (Still Relevant)

## Low-Effort / High-Impact Opportunities

1. Parallelize evidence pack generation with bounded/global rate limits.
2. Reuse contents-page preview output when it overlaps with general preview rendering.
3. Pre-filter/compress candidate payload before LLM ranking to cut cost and prompt size.
4. Batch state checks where safe to reduce per-file DB round trips.
5. Avoid HTML parsing for `file_id` when DB/report metadata already provides a mapping.
6. Pass/propagate WordPress auth header from orchestrator to generator to remove duplicate auth-derivation logic.
7. Parallelize WordPress media uploads for image-heavy reports.
8. Extract publish-time validation JSON parsing into a shared helper/service.
9. Audit external scripts/docs for stale `pdf_*_service` references after `pdf_service.py` consolidation.

## High-Impact (No Effort Limits)

1. Add async vector-store indexing flow (background wait/callback strategy).
2. Introduce durable, checkpointed pipeline stages to resume mid-run.
3. Centralize LLM orchestration with retry/backoff/circuit-breaker policy.
4. Build a document-processing service with memoized outputs (PDF info/text/candidates).
5. Stream LLM responses with early validation/fail-fast behavior.
6. Model the pipeline as a DAG to parallelize independent stages.
7. Enforce schema validation gates across all generator stages.
8. Move publishing to a durable queue with retry/backoff/idempotency.
9. Expand state DB to track stage artifacts + content hashes for selective reprocessing.
10. Pool PDF resources across files where thread/process safety allows.
11. Add per-stage feature flags for controlled rollout and cost governance.
