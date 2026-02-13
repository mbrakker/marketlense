# Potential TODOs (Still Relevant)

## Low-Effort / High-Impact Opportunities

1. Reuse contents-page preview output when it overlaps with general preview rendering.
2. Pre-filter/compress candidate payload before LLM ranking to cut cost and prompt size.
4. Pass/propagate WordPress auth header from orchestrator to generator to remove duplicate auth-derivation logic.
5. Parallelize WordPress media uploads for image-heavy reports.
6. Extract publish-time validation JSON parsing into a shared helper/service.

## High-Impact (No Effort Limits)

1. Introduce durable, checkpointed pipeline stages to resume mid-run.
2. Centralize LLM orchestration with retry/backoff/circuit-breaker policy.
3. Build a document-processing service with memoized outputs (PDF info/text/candidates).
4. Stream LLM responses with early validation/fail-fast behavior.
5. Model the pipeline as a DAG to parallelize independent stages.
6. Move publishing to a durable queue with retry/backoff/idempotency.
7. Expand state DB to track stage artifacts + content hashes for selective reprocessing.
8. Pool PDF resources across files where thread/process safety allows.
9. Add per-stage feature flags for controlled rollout and cost governance.
