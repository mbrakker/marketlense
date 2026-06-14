# Unified LLM Service Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `src/services/llm_service.py` the single public boundary for
OpenAI, OpenRouter, generic model-call policy, and OpenAI vector-store provider
operations while retaining `openai_service.py` as a compatibility-only facade.

**Architecture:** Move the current OpenAI implementation family under a private
`_llm_service` namespace, split generic call policy and client composition into
focused modules, and add an OpenRouter client-construction capability used by
the browser-download service. Production callers use only `llm_service`; the
legacy facade delegates without owning provider logic.

**Tech Stack:** Python 3.12+, dataclasses, OpenAI SDK, browser-use/OpenRouter,
pytest, Ruff, mypy, repository architecture and mutation gates.

---

### Task 1: Lock Canonical Boundary Behavior

**Files:**
- Modify: `tests/test_llm_service.py`
- Create: `tests/test_llm_service_boundary.py`
- Modify: `tests/test_quality_command_scripts.py`

- [ ] **Step 1: Add a failing canonical-ownership test**

Add an AST-based test asserting that first-party production modules do not
import `openai_service`, except `src/services/openai_service.py` itself, and
that `vector_store_service.py` contains no `openai_service = llm_service` alias.

- [ ] **Step 2: Add failing direct-operation tests**

Verify `llm_service` exposes analysis, chat JSON, image JSON, OCR, Responses API,
and all vector-store provider operations without resolving a separate
`openai_service` module.

- [ ] **Step 3: Add a failing service-map test**

Require `docs/quality/service_boundary_map.json` to declare
`src/services/llm_service.py` as the canonical OpenAI/LLM boundary and
`src/services/_llm_service/` as its private implementation root.

- [ ] **Step 4: Run the red tests**

Run:

```powershell
python -m pytest tests/test_llm_service.py tests/test_llm_service_boundary.py tests/test_quality_command_scripts.py -q
```

Expected: fail because `llm_service` still delegates through
`openai_service`, the private `_llm_service` family does not exist, and the map
still names `openai_service.py`.

### Task 2: Move OpenAI Capabilities Under the LLM Namespace

**Files:**
- Create: `src/services/_llm_service/__init__.py`
- Move: `src/services/_openai_service/base.py` to `src/services/_llm_service/openai_shared.py`
- Move: `src/services/_openai_service/client.py` to `src/services/_llm_service/openai_client.py`
- Move: `src/services/_openai_service/chat.py` to `src/services/_llm_service/openai_chat.py`
- Move: `src/services/_openai_service/responses.py` to `src/services/_llm_service/openai_responses.py`
- Move: `src/services/_openai_service/vector_store.py` to `src/services/_llm_service/vector_store.py`
- Modify: `src/services/llm_service.py`
- Modify: `src/services/openai_service.py`

- [ ] **Step 1: Move implementation modules without changing provider behavior**

Update internal imports to the `_llm_service` namespace and retain existing
typed contracts, response adaptation, semantic caching, accounting calls,
provider error codes, and request metadata.

- [ ] **Step 2: Make `llm_service.py` the canonical facade**

Export the moved OpenAI operations directly from their semantic owners.
`llm_service` must no longer import or dynamically resolve `openai_service`.

- [ ] **Step 3: Convert `openai_service.py` to compatibility-only delegation**

Re-export the historical symbols from `llm_service`, including the supported
test/provider seam, without retaining provider implementation.

- [ ] **Step 4: Run focused OpenAI tests**

Run:

```powershell
python -m pytest tests/test_openai_chat_service.py tests/test_openai_ocr_service.py tests/test_openai_vector_store.py tests/test_llm_service.py tests/test_llm_service_boundary.py -q
```

Expected: pass with unchanged typed outputs and error taxonomy.

### Task 3: Split Generic Policy and Client Composition

**Files:**
- Create: `src/services/_llm_service/policy.py`
- Create: `src/services/_llm_service/client.py`
- Modify: `src/services/llm_service.py`
- Modify: `tests/test_llm_service.py`

- [ ] **Step 1: Add failing generic builder tests**

Require generic `build_client`, `build_client_from_callables`,
`build_client_for_settings`, and `client_policy_from_settings` APIs while
retaining old OpenAI-named aliases only for compatibility.

- [ ] **Step 2: Move policy execution**

Move retry classification, bounded backoff, rate limiting, circuit state, and
policy event emission to `policy.py`.

- [ ] **Step 3: Move client composition**

Move the policy-wrapped client and builders to `client.py`. Keep generator and
orchestrator call behavior unchanged.

- [ ] **Step 4: Run policy tests**

Run:

```powershell
python -m pytest tests/test_llm_service.py tests/integration/test_service_integrations.py -k "llm_service" -q
```

Expected: pass with exact retry counts, delays, circuit transitions, and
required structured log fields.

### Task 4: Consolidate OpenRouter Client Construction

**Files:**
- Create: `src/services/_llm_service/openrouter.py`
- Modify: `src/services/llm_service.py`
- Modify: `src/services/_browser_report_download/browser.py`
- Modify: `tests/test_llm_service.py`
- Modify: affected browser-download tests that provide a fake browser runtime

- [ ] **Step 1: Add failing OpenRouter construction tests**

Assert model, API key, referer, temperature, and timeout are passed to the
external `ChatOpenRouter` factory, secrets are absent from logs, missing keys
raise a non-retryable typed error, and provider initialization failures are
adapted to a retryable typed error.

- [ ] **Step 2: Implement the OpenRouter capability**

Add one service function that accepts the existing typed browser settings,
explicit run context, and external provider factory. Emit sanitized start,
complete, and failure events.

- [ ] **Step 3: Migrate browser runtime**

Replace direct `browser_use.ChatOpenRouter(...)` construction with the
canonical `llm_service` call. Keep Browser, Agent, lifecycle, and artifact
behavior in the browser-download service.

- [ ] **Step 4: Run browser-focused tests**

Run:

```powershell
python -m pytest tests/test_browser_report_download_doc_type_predictor.py tests/test_browser_report_download_service tests/test_report_download_orchestrator.py -q
```

Expected: pass with unchanged browser outcomes and side effects.

### Task 5: Migrate Production Callers and Vector-Store Ownership

**Files:**
- Modify: `src/services/vector_store_service.py`
- Modify: `src/services/rank_service.py`
- Modify: affected generators and orchestrators currently using OpenAI-named
  LLM builders
- Modify: `tests/test_vector_store_service.py`
- Modify: affected caller tests

- [ ] **Step 1: Migrate to generic builder names**

Change production generators, orchestrators, and service callers to the generic
LLM builder APIs. Preserve explicit injected clients used by tests.

- [ ] **Step 2: Remove misleading vector-store aliasing**

Call the canonical `llm_service` provider operations directly and update tests
to mock only the top-level service boundary.

- [ ] **Step 3: Prove no production legacy imports remain**

Run:

```powershell
rg -n "openai_service" src --glob "*.py"
```

Expected: only the compatibility facade and documentation-oriented compatibility
references remain.

- [ ] **Step 4: Run affected generator and pipeline tests**

Run the tests selected from the migrated call-site inventory, including report
pipeline, taxonomy, evidence, artifact, validation, regeneration, OCR, caption,
ranking, cross-report, and publisher screening paths.

### Task 6: Update Enforcement, Documentation, and Movement Evidence

**Files:**
- Modify: `docs/quality/service_boundary_map.json`
- Modify: `scripts/ci/check_split_symbol_links.py`
- Modify: `scripts/ci/run_mutation_gate.py`
- Modify: `docs/quality/refactor_movement_evidence.json`
- Modify: `README.md`
- Modify: `long_scripts.md`

- [ ] **Step 1: Update canonical-boundary enforcement**

Point OpenAI imports at `llm_service.py`, allow `_llm_service/` internals, and
classify `openai_service.py` only as the compatibility facade.

- [ ] **Step 2: Update split-link and mutation targets**

Replace `_openai_service` paths with `_llm_service` semantic owners and keep
public symbol-link checks for both canonical and compatibility facades.

- [ ] **Step 3: Record movement audit**

Compare moved top-level symbols against `HEAD` and record moved, unchanged,
changed, and facade-owned counts with any intentional logger/import changes.

- [ ] **Step 4: Update architecture documentation**

Document the canonical LLM boundary, provider-specific private capabilities,
browser ownership rule, and legacy facade status.

### Task 7: Regression and Live Verification

**Files:**
- Modify after success: `simplification.md`

- [ ] **Step 1: Run static and threshold gates**

Run formatting, typing, architecture imports, service-boundary map,
split-symbol links, forbidden patching, and:

```powershell
python scripts/count_long_files.py --min-lines 1000
```

No affected LLM service or affected test file may exceed 1,000 lines.

- [ ] **Step 2: Run focused and full automated suites**

Run the complete affected suite, then the repository functional suite,
coverage gate, and mutation gate. Investigate and fix regressions before
continuing.

- [ ] **Step 3: Run live OpenAI calls**

Load credentials from the existing `.env` without printing them. Run a real
strict-JSON chat call through `llm_service`, then run OCR against an existing
repository PDF. Run vector-store status when an existing configured ID is
available.

- [ ] **Step 4: Run live OpenRouter workflows**

Use the existing guarded browser-download and report-download integration
workflows with the configured OpenRouter credential. Do not create a synthetic
project fixture to substitute for existing project artifacts.

- [ ] **Step 5: Update simplification backlog only after success**

Remove the completed consolidation item and covered vector-store ownership
item. Add a new backlog item with acceptance criteria for deleting the legacy
`openai_service.py` facade after all downstream imports are proven absent.

- [ ] **Step 6: Run final verification**

Rerun the focused suite, architecture gates, line threshold scan, and
`git diff --check`. Record any unavailable live path explicitly rather than
claiming it passed.
