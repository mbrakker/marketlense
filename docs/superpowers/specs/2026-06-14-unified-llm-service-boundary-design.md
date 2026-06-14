# Unified LLM Service Boundary Design

**Status:** Approved on 2026-06-14

**Goal:** Consolidate OpenAI, OpenRouter, and generic model-call ownership behind
one canonical, semantically split `llm_service` boundary without changing
provider behavior or moving browser automation into the LLM service.

## Scope

- `src/services/llm_service.py` becomes the only canonical public LLM/provider
  entrypoint.
- OpenAI chat JSON, image JSON, OCR, Responses API, and vector-store provider
  calls move under the private `src/services/_llm_service/` capability family.
- OpenRouter model-client construction moves from browser-download runtime code
  into the private LLM capability family.
- Generic retry, backoff, rate limiting, circuit breaking, and provider-policy
  logging remain service-owned and move into focused private modules.
- Production callers migrate to `llm_service`.
- `src/services/openai_service.py` remains a compatibility facade during this
  change and delegates to `llm_service`.

Browser lifecycle, browser-use agent execution, artifact capture, and download
classification remain owned by `browser_report_download_service`. The browser
service receives an OpenRouter client constructed by the LLM boundary.

## Architecture

`src/services/llm_service.py` is a small canonical facade. Private modules are
split by stable semantic ownership:

- `policy.py` owns retry classification, backoff, rate limiting, and circuit
  breaker execution.
- `client.py` owns the policy-wrapped generic model client and configured client
  builders.
- `openai.py` exposes OpenAI chat, image, OCR, Responses API, and analysis
  operations through the existing typed contracts.
- `openrouter.py` validates OpenRouter configuration and constructs the
  browser-use OpenRouter model client.
- `vector_store.py` exposes OpenAI vector-store provider operations through the
  existing typed contracts.

Existing OpenAI implementation code may be moved without behavior changes from
`src/services/_openai_service/` into these semantic owners. No pass-through
peer provider service is introduced.

## Compatibility

`src/services/openai_service.py` remains import-compatible and re-exports the
existing public OpenAI symbols by delegating to `llm_service`. Production code
must not import this facade after migration. Tests that specifically verify
legacy compatibility may continue to import it.

The service-boundary CI map is updated so `llm_service.py` is canonical and
both `_llm_service/` and the compatibility facade are explicitly classified.
A separate simplification backlog item will track complete removal of
`openai_service.py` after downstream compatibility usage is proven absent.

## Data And Errors

Existing versioned OpenAI request and response dataclasses remain unchanged.
The generic LLM policy contracts remain the policy source of truth. OpenRouter
client construction receives explicit typed browser-download settings and
returns the provider client required by browser-use.

Existing OpenAI `AppError` codes, retryability, severity, response adaptation,
usage accounting, semantic caching, and structured log fields remain stable.
OpenRouter construction failures gain typed, sanitized `AppError` values and
structured LLM-service events.

## Testing

TDD coverage must prove:

- `llm_service` directly owns chat JSON, image JSON, OCR, Responses API,
  analysis, and vector-store calls.
- the compatibility `openai_service` facade returns identical typed contracts;
- retryable and non-retryable provider errors retain their taxonomy;
- OpenRouter construction is performed by `llm_service`, not browser runtime;
- browser execution receives the constructed client without changing agent
  behavior;
- required structured log fields remain present;
- the service-boundary map rejects new direct provider entrypoints;
- affected first-party source and test files remain below 1,000 physical lines.

Tests mock only provider/network/process boundaries. Movement-only provider code
is audited against the pre-change implementation where practical.

## Verification

Run focused provider, LLM policy, vector-store, browser-download, generator, and
report-pipeline tests, followed by formatting, typing, architecture gates, the
full functional suite, coverage, and mutation checks required by the repository.

Live verification uses existing repository artifacts and configured credentials:

1. Run a real OpenAI strict-JSON chat call through `llm_service`.
2. Run the existing guarded OCR integration against an existing project PDF.
3. Exercise vector-store status or lifecycle behavior when an existing configured
   vector-store identifier is available.
4. Run the existing OpenRouter-backed browser-download integration against its
   existing local fixture and affected report-download workflow.

Failures are fixed with a red regression test and the affected live workflow is
rerun. No synthetic project fixture is created to claim live success.

## Backlog Disposition

After automated and live verification succeeds:

- remove the completed “Consolidate OpenAI and LLM service boundaries” item from
  `simplification.md`;
- remove overlapping completed vector-store ownership wording when its
  acceptance criteria are covered by this change;
- add a new explicit item to remove the legacy `openai_service.py` compatibility
  facade once repository and downstream imports are proven absent.
