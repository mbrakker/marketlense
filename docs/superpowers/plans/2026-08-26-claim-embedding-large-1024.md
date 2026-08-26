# Claim Embedding Large-1024 Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move production claim embeddings to `text-embedding-3-large` at exactly 1,024 dimensions while preserving durable queue, retry, budget, and accounting behavior.

**Architecture:** Keep the existing provider service and claim-embedding orchestrator. Add an explicit requested dimension to their typed contracts, include it in the durable embedding identity, validate it at provider and persistence boundaries, and batch only independently leased rows in the existing sequential workflow.

**Tech Stack:** Python 3, OpenAI Embeddings API, SQLite, Pytest, YAML.

## Global Constraints

- Production claim embeddings use `text-embedding-3-large` with exactly `1024` dimensions.
- Old `text-embedding-3-small` vectors must never satisfy the new model/version/dimension identity.
- Preserve content hashes, idempotency, leases, queue transitions, retry ownership, pricing/accounting, and bounded budgets.
- Run a bounded live A/B benchmark on retained MarketLense claims; retain only non-secret scalar evidence.

---

### Task 1: Provider dimension contract

**Files:**
- Modify: `src/contracts/openai.py`
- Modify: `src/services/_llm_service/embeddings.py`
- Test: `tests/test_openai_vector_store.py`

**Interfaces:**
- Consumes: `OpenAIEmbeddingRequest(dimensions: int)`.
- Produces: `OpenAIEmbeddingResponse.dimensions` only after every returned vector has that exact length.

- [ ] **Step 1: Write the failing test**

```python
assert fake_openai.calls["embeddings.create"] == [{
    "model": "text-embedding-3-large", "input": ["first claim", "second claim"], "dimensions": 1024,
}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_openai_vector_store.py -k embeddings`
Expected: FAIL because the provider request lacks `dimensions`.

- [ ] **Step 3: Write minimal implementation**

```python
resp = client.embeddings.create(model=request.model, input=inputs, dimensions=request.dimensions)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests/test_openai_vector_store.py -k embeddings`
Expected: PASS.

### Task 2: Durable 1024-dimension identity and batched queue execution

**Files:**
- Modify: `src/contracts/analytics_projection.py`
- Modify: `src/orchestrators/claim_embedding_orchestrator.py`
- Modify: `src/services/_analytics_store/claim_embeddings.py`
- Modify: `src/services/_analytics_store/queue_remediation.py`
- Test: `tests/test_claim_embedding_persistence.py`
- Test: `tests/test_claim_embedding_queue_remediation.py`

**Interfaces:**
- Consumes: `ClaimEmbeddingWorkflowRequest(dimensions=1024, batch_size=...)`.
- Produces: one provider request per admitted chunk; every persisted embedded record has dimensions/vector length `1024` and a dimension-qualified UID.

- [ ] **Step 1: Write failing tests**

```python
assert request.dimensions == 1024
assert len(provider_requests) == 1
assert len(provider_requests[0].inputs) == 2
assert persisted_record.dimensions == len(persisted_record.vector) == 1024
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_claim_embedding_persistence.py tests/test_claim_embedding_queue_remediation.py`
Expected: FAIL because rows are requested one at a time and persistence accepts non-1024 vectors.

- [ ] **Step 3: Write minimal implementation**

```python
for batch in chunks(individually_leased_rows, request.batch_size):
    response = create_embeddings(request_for(batch), ctx)
    for row, vector in zip(batch, response.embeddings, strict=True):
        persist(success_record(row, vector))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_claim_embedding_persistence.py tests/test_claim_embedding_queue_remediation.py`
Expected: PASS.

### Task 3: Canonical settings, CLI defaults, pricing, documentation, and live benchmark

**Files:**
- Modify: `src/config/app.yaml`
- Modify: `src/config/llm-costs.yaml`
- Modify: `src/_cli/claim_embedding.py`
- Modify: `src/orchestrators/_workflow_queue_handlers/analytics.py`
- Create: `scripts/quality/claim_embedding_ab_benchmark.py`
- Modify: `docs/architecture/asynchronous-workflow-queue.md`
- Modify: `docs/ops/configuration.md`
- Modify: `docs/quality/benchmarks.md`
- Test: `tests/test_claim_embedding_ab_benchmark.py`

**Interfaces:**
- Consumes: retained local claim rows and a small hand-authored query/relevance set selected from those rows.
- Produces: a JSON evidence artifact containing scalar provider calls, claims/sec, p50/p95 latency, total time, MRR/recall@k, token-normalized cost, and vector byte counts for both lanes.

- [ ] **Step 1: Write a failing benchmark validation test**

```python
assert result.lanes["batched_large"].provider_calls < result.lanes["unbatched_small"].provider_calls
assert result.lanes["batched_large"].dimensions == 1024
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest -q tests/test_claim_embedding_ab_benchmark.py`
Expected: FAIL because the benchmark implementation is absent.

- [ ] **Step 3: Implement the bounded real-data benchmark and canonical configuration**

```python
for lane in lanes:
    vectors, timings, usage = embed_retained_claims(lane)
    quality = evaluate_cosine_ranking(vectors, queries)
    write_scalar_artifact(lane, quality, timings, usage)
```

- [ ] **Step 4: Run focused tests, live benchmark, and documentation generation**

Run: `python -m pytest -q tests/test_claim_embedding_ab_benchmark.py tests/test_claim_embedding_persistence.py tests/test_claim_embedding_queue_remediation.py tests/test_openai_vector_store.py`
Run: `python scripts/quality/claim_embedding_ab_benchmark.py --reports-db reports.sqlite --output-json out/claim-embedding-ab-benchmark-2026-08-26.json`
Run: `python scripts/docs/generate_references.py`
Expected: tests pass; benchmark records actual provider usage without publishing or queue writes.
