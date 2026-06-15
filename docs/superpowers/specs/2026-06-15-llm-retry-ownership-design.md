# LLM Retry Ownership Design

## Goal

Make orchestrators the sole owners of retries and backoff while keeping LLM
services responsible for one external attempt, rate limiting, circuit breaking,
provider adaptation, and typed error propagation.

## Current Problem

`llm_service` currently has an explicit retry loop, OpenAI clients inherit SDK
automatic retries, and OpenRouter browser clients default to ten SDK retries.
Several workflows also use `retry_orchestrator.run_with_retry`. A single
retryable provider failure can therefore multiply external calls and exceed the
workflow timeout budget without one authoritative attempt count.

## Ownership Model

### Services

Each public LLM service operation performs at most one provider request.

Services continue to own:

- credential and request validation;
- provider client construction;
- request and response adaptation;
- scope-level rate limiting;
- circuit-breaker state;
- typed `AppError` classification and propagation;
- deterministic pre-call omission of parameters already known to be unsupported.

Services do not own:

- transient retries;
- retry delay, backoff, or jitter;
- replaying a request after the provider rejects an unknown parameter.

OpenAI and OpenRouter clients are constructed with `max_retries=0`.

### Orchestrators

Orchestrators continue to use `retry_orchestrator.run_with_retry` for retryable
workflow failures. Their logs are the authoritative retry record and include the
attempt number, error code, retryability, and delay decision.

Generators continue to propagate retryable `AppError` values unchanged.

## Compatibility

The existing settings dataclasses retain the `llm_retry_*` fields to avoid an
unversioned contract break. Their retry count becomes a compatibility field
whose only valid value is zero. Configuration loading rejects a nonzero
`ingest.llm.retries` or publisher-discovery LLM retry count with a typed,
non-retryable configuration error.

Delay, backoff, and jitter compatibility fields resolve to zero and have no
service execution effect.

`LLMClientPolicy` retains its retry fields for source compatibility. The service
ignores them and logs:

- `retry_owner: orchestrator`;
- `service_attempt_limit: 1`;
- configured legacy retry count.

This guarantees one service attempt even for an older caller that constructs a
policy with a nonzero retry count.

## Timeout Rule

Provider timeout remains the per-attempt timeout. Any workflow performing
multiple attempts must have an outer budget large enough for its configured
attempt count and delays. Existing orchestrator time-budget enforcement remains
unchanged; tests assert that the service does not sleep or consume retry delay.

## Testing

- A service-level retryable failure produces one provider call, no sleep, no
  `llm_call_retry` event, and an `llm_call_failed` event naming orchestrator
  ownership.
- An orchestrator around that service performs exactly its configured number of
  attempts and owns all retry sleeps/events.
- OpenAI and OpenRouter client factories receive `max_retries=0`.
- Unknown unsupported OpenAI parameters produce one request and a typed
  non-retryable provider error; known unsupported parameters are omitted before
  the request.
- Nonzero service retry configuration fails explicitly.
- Existing rate-limit and circuit-breaker tests remain green.
- Live OpenAI, OpenRouter, OCR, vector-store, and affected workflow checks run
  through existing project artifacts and configuration.

## Risks Controlled

- No new retry framework or service boundary is introduced.
- Prompt text, models, response contracts, caches, vector-store behavior, and
  artifact paths remain unchanged.
- The service cannot silently multiply provider calls through SDK defaults.
- Compatibility fields prevent an unversioned dataclass/schema deletion.

