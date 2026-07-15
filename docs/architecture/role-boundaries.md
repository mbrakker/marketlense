# Role Boundaries

> **Documentation type:** Architectural
> **Canonical topic:** Role-boundary rules
> **Update trigger:** Role, import, I/O, prompt, or error-boundary changes.

This project enforces strict module role boundaries:

- `src/services/*`: external I/O boundaries only (filesystem, API, DB, network).
- `src/generators/*`: domain assembly and validation logic.
- `src/orchestrators/*`: workflow ordering, retries, backoff, idempotency/state transitions.
- `src/contracts/*`: typed dataclass contracts for all major request/response boundaries.
- `src/utils/*`: pure deterministic helpers (no side effects).

## Allowed Dependency Direction

- `services -> contracts, utils`
- `generators -> services, contracts, utils`
- `orchestrators -> generators, services, contracts, utils`
- reverse imports are forbidden

## Hard Constraints

- No generator direct file/API access.
- No orchestrator domain/prompt logic.
- No service-side orchestration/retry policy.
- No placeholder production logic.
- No silent degradation when required fields are unavailable; raise typed `AppError`.

## Prompt Boundary

- Prompt files are loaded/rendered through prompt service APIs only.
- Generators request prompt namespaces and variables; they do not read prompt files directly.
- Prompt text, prompt hash, and rendered output are logged per model call.
