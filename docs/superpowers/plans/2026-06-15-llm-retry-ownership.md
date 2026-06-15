# LLM Retry Ownership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce one provider attempt in LLM services and make orchestrators the sole retry/backoff owners.

**Architecture:** Reuse the existing `llm_service` policy wrapper for rate limiting and circuit breaking but remove its retry loop. Disable OpenAI/OpenRouter SDK retries at client construction, reject nonzero service retry configuration, and retain existing orchestrator retry execution as the only replay mechanism.

**Tech Stack:** Python dataclasses, OpenAI SDK, vendored browser-use OpenRouter client, pytest, structured JSON logging.

---

### Task 1: Prove Single-Attempt Service Ownership

**Files:**
- Modify: `tests/test_llm_service.py`
- Modify: `tests/integration/test_service_integrations.py`

- [ ] Replace the service retry-success test with a failure test that configures
  legacy retries, raises a retryable `AppError`, and asserts one provider call,
  zero sleeps, no `llm_call_retry` event, and `retry_owner=orchestrator`.
- [ ] Add an integration-shaped test that wraps the single-attempt client in
  `retry_orchestrator.run_with_retry` and asserts exactly two service calls and
  one orchestrator sleep for one configured retry.
- [ ] Run the tests and confirm they fail because the service currently retries.

### Task 2: Remove Service and SDK Retry Execution

**Files:**
- Modify: `src/services/_llm_service/policy.py`
- Modify: `src/services/_llm_service/openai_client.py`
- Modify: `src/services/_llm_service/openrouter.py`
- Modify: `src/services/_llm_service/openai_shared.py`
- Modify: `src/services/_llm_service/openai_chat.py`
- Modify: `src/services/_llm_service/openai_responses.py`
- Modify: `tests/test_openai_vector_store.py`
- Modify: `tests/test_llm_service.py`

- [ ] Replace the policy retry loop with one rate-limited, circuit-protected
  call and immediate error propagation.
- [ ] Add `retry_owner`, `service_attempt_limit`, and legacy retry configuration
  fields to service start/failure/complete logs.
- [ ] Construct OpenAI clients with `max_retries=0`.
- [ ] Construct OpenRouter clients with `max_retries=0`.
- [ ] Replace reactive unsupported-parameter retry with a single provider call;
  retain known pre-call parameter omission.
- [ ] Run focused service/provider tests until green.

### Task 3: Enforce Configuration Ownership

**Files:**
- Modify: `src/config/app.yaml`
- Modify: `src/services/_config_service/openai.py`
- Modify: `src/contracts/config.py`
- Modify: `src/contracts/ingest.py`
- Modify: `src/contracts/_publisher_inventory/settings.py`
- Modify: `tests/test_config_service.py`
- Modify: `tests/test_report_pipeline_orchestrator.py`

- [ ] Add a failing config test for nonzero `ingest.llm.retries`.
- [ ] Change current configuration defaults to zero service retries and zero
  service retry delays.
- [ ] Raise typed non-retryable `llm_service_retry_config_forbidden` for a
  nonzero service retry count.
- [ ] Update compatibility-field documentation to state that orchestrators own
  retries.
- [ ] Update report-pipeline assertions to prove the created LLM clients have a
  one-attempt service policy.
- [ ] Run config and pipeline tests until green.

### Task 4: Document and Verify Ownership

**Files:**
- Modify: `README.md`
- Modify: `simplification.md`

- [ ] Document that services perform one attempt and SDK retries are disabled.
- [ ] Document that only orchestrator retry events represent request replay.
- [ ] Run focused LLM, config, report-pipeline, cross-report, OCR, vector-store,
  and browser tests.
- [ ] Run full pytest with coverage, mutation, typing, architecture, formatting,
  boundary, and line-count gates.
- [ ] Run fresh live OpenAI JSON, existing-PDF OCR, persisted vector-store,
  OpenRouter completion, and affected browser workflow checks.
- [ ] Remove the completed simplification item only after every required check
  succeeds.

