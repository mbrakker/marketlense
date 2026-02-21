# Testing Integrity Rules

## Required Test Layers

- utilities: unit tests
- generators: unit tests with mocked services
- services: integration tests (marked `integration`)
- orchestrators: pipeline tests

## Anti-Cheat Requirements

- Assert observable outcomes (contracts, side effects, persisted state, logs).
- Do not patch generator/orchestrator internals or private helpers.
- Do not rely on tautological assertions.
- Retry tests must assert attempt count and control behavior.
- Idempotency-sensitive paths must verify no duplicate side effects.

## Shared Fixtures

Implemented in `tests/conftest.py`:

- `assert_logs_have_required_fields`
- `assert_no_defaulted_required_fields`
- `assert_app_error`
- `idempotency_guard`

## Structured Logging Assertions

At least one test per service/orchestrator should assert logs include:

- `run_id`
- `task_id`
- `span_id`
- `role`
- `module`
- `event`

## Contract and Schema Checks

- dataclass round-trip tests for changed/added contracts
- schema validation in pack/artifact/validation tests
- negative-path AppError taxonomy assertions for key failures
