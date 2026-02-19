# Agent Architecture & Coding Rules (Mandatory)

This document includes mandatory test integrity enforcement controls.

Below is a **fully integrated, production-grade rewrite** of your document.
I preserved your tone (hard constraints, enforceable), tightened definitions, and merged professional best practices **without bloating**.
This is suitable to be treated as a **canonical engineering constitution** for agents.

---

This document defines **non-negotiable architectural, coding, logging, and operational constraints** for all coding agents.

These rules are **hard constraints**, not guidelines.
Any implementation that violates them is **invalid by design**.

---

## 1. Architectural Roles (Strict Separation)

### 1.1 Data as Contract

* **All service inputs and outputs MUST be defined as `dataclass` models.**
* Each field MUST be:

  * explicitly typed
  * documented
* Dataclasses are the **single source of truth** for:

  * types
  * semantics
  * context meaning
* No implicit, undocumented, or ad-hoc fields are allowed.

#### Contract evolution rules

* Every contract MUST be versioned (`schema_version` or module-level version).
* Breaking changes REQUIRE:

  * version bump
  * explicit adapter or migration logic
* Services MUST validate both incoming and outgoing contracts.
* Returned dataclass objects MUST be fully populated according to their semantic contract.
* Returning partially populated, default-filled, or sentinel-filled fields to mask missing logic is a violation.
* If required fields cannot be produced correctly, the system MUST fail explicitly with a typed `AppError` and log the failure.

---

### 1.2 Services (I/O Layer)

A Service is the **only** place where the system touches the outside world.

#### A service module

* Solves **exactly one external task**:

  * database
  * filesystem
  * network
  * external API (OpenAI, Telegram, S3, etc.)
* Returns:

  * fully-constructed `dataclass` objects
  * or primitive structures only
* Contains:

  * no business logic
  * no orchestration logic

#### Hard requirements

* Paths, credentials, constants:

  * declared once at module top
  * never duplicated
* External calls MUST be wrapped in top-level functions.
* Services MUST validate:

  * external inputs
  * external outputs
  * contract adherence

#### Logging (mandatory, services)

* input parameters (sanitized)
* resolved configuration
* external request (metadata only)
* external response (sanitized)
* adapted output dataclass

#### Services MUST NOT

* Decide *what* to generate
* Decide *when* to retry
* Combine multiple external systems

#### Service consolidation (mandatory)

* One external system = one service module. Splitting the same system across multiple service modules is forbidden.
* Thin wrappers that merely delegate to another service for the same system are violations; consolidate into one module.
* Examples (current modules):

  * PDF libraries MUST live in a single service (e.g., `pdf_service.py`), not `pdf_utils_service.py` + `pdf_text_service.py` + `pdf_context_service.py` + `pdf_contents_service.py` + `extract_service.py`.
  * OpenAI access belongs in `openai_service.py` only; do not add `openai_*` service shards.
  * Vector store access belongs in `vector_store_service.py` only; do not split indexing/query/deletion into separate services.
  * WordPress access belongs in `wordpress_service.py` only.

---

### 1.3 Generators (Business / Domain Logic)

Generators implement **what should be produced and how**.

#### Generators

* Accept fully-formed context `dataclass` objects
* Call one or more services
* Assemble domain objects:

  * posts
  * messages
  * HTML pages
  * decisions
* Perform:

  * validation
  * completeness checks
  * semantic checks

#### Generators MUST NOT

* Access infrastructure directly
* Read files
* Call APIs
* Decide scheduling or retries
* Catch and internally retry retryable errors
* Implement backoff logic
* Suppress retryable `AppError` exceptions to re-attempt calls inside generators
* Swallow retryable errors that MUST propagate to the orchestrator

#### Logging (mandatory, generators)

* input context (serialized)
* intermediate decisions
* selected prompt file(s)
* prompt version/hash
* **exact rendered prompt text**
* model parameters
* raw model response
* post-processed output
* validation results

---

### 1.4 Orchestrators (Control Plane)

Orchestrators define **when, in what order, and with what outcome** things run.

#### Architecture definition

An orchestrator is a control-plane module that coordinates services and generators for a workflow.
It owns execution sequencing, branching, retries, and lifecycle/state transitions, while keeping domain semantics inside generators and external I/O inside services.

#### Responsibilities

* pipeline coordination
* task lifecycle management
* retries and backoff
* state transitions
* notifications

#### Orchestrators MUST

* Call generators and services
* Track task/run/span IDs
* Apply retry strategies based on error taxonomy
* Be idempotent or enforce idempotency keys

#### Orchestrators MUST NOT

* Contain domain logic
* Contain prompt text
* Transform data beyond routing

#### Logging (mandatory, orchestrators)

* pipeline start/end
* task IDs and transitions
* retry decisions and reasons
* generator/service invocations
* final status per task

---

### 1.5 Utility / Core Modules

Utilities are **pure, deterministic helpers**.

#### Rules

* Stateless
* No I/O
* No global state
* Pure functions only

#### Input / Output

* `dict`, `list`, primitives, or `DataFrame`

Logging inside utilities is discouraged; logging belongs at call sites.

---

### 1.6 Zero-Tolerance Implementation Rules (Hard Constraints)

The following rules apply to all roles (services, generators, orchestrators, utilities):

#### 1.6.1 No Placeholders (Production Integrity Rule)

Production code MUST NOT contain:

* TODO, FIXME, or stub comments implying incomplete logic
* `pass` used as placeholder behavior
* Fake return values
* Temporary constants standing in for real implementations
* Branches left unimplemented
* "Will implement later" scaffolding

If required functionality cannot be implemented fully:

* Fail explicitly with a typed `AppError`
* Log the failure
* Do not silently degrade behavior

Incomplete logic is a hard violation.

#### 1.6.2 No Monkeypatching (Integrity Rule)

Monkeypatching is forbidden in:

* Production code
* Core unit tests
* Domain logic validation tests

Tests MAY mock only true external boundaries:

* Network
* External APIs
* Time
* Randomness
* OS/process boundaries

Tests MUST NOT:

* Patch private helpers (`_internal_fn`)
* Patch core logic paths to simulate success
* Validate mocked narratives instead of real outcomes

If a test passes after removing the logic it claims to validate, the test is invalid.

#### 1.6.3 No Monolithic Scripts (Structural Integrity Rule)

The system MUST NOT contain monolithic modules.

A module is considered monolithic if it:

* Combines multiple architectural roles
* Exceeds a single clearly defined responsibility
* Mixes orchestration + domain + I/O
* Contains branching workflows across concerns

Hard constraints:

* One module = one role
* One module = one responsibility
* Cross-cutting behavior must be factored into separate modules

If a feature requires multiple responsibilities:

* Define contracts
* Implement separate modules per role
* Wire them via orchestrator

"Making it work in one file" is forbidden.

---

## 2. How to Decide What a Script Is (Non-Ambiguous)

Every module MUST be classified **before implementation**.

If a script fits **more than one role**, the design is **invalid**.

| Question answered                      | Role         |
| -------------------------------------- | ------------ |
| “How do we talk to X?”                 | Service      |
| “What should be produced and how?”     | Generator    |
| “When / in what order / retry or not?” | Orchestrator |
| “Pure transformation?”                 | Utility      |

---

## 3. Code Organization & Dependency Rules

### 3.1 Canonical Structure

```text
src/
  contracts/
  services/
  generators/
  orchestrators/
  utils/
  prompts/
```

#### Import rules

* `services` -> contracts, utils
* `generators` -> services, contracts, utils
* `orchestrators` -> generators, services, contracts, utils
* Reverse imports are forbidden.

---

### 3.2 Single-Purpose Modules

* One module = one responsibility.
* Never mix:

  * I/O
  * domain logic
  * orchestration

---

### 3.2.1 Anti-God-Module Enforcement

The following patterns are prohibited:

* Files that orchestrate + generate + call services
* Files that define contracts and business logic
* Files that both render prompts and call external APIs
* Catch-all "utils" that perform I/O

Refactoring is mandatory if:

* A module exceeds its role boundary
* Responsibilities are unclear
* Test coverage requires patching internals to isolate behavior

Architectural drift must be corrected immediately.

---

### 3.3 Explicit Inputs / Outputs

* Every function:

  * takes explicit arguments
  * returns a `dataclass` or structured dict
* Inputs MUST be normalized immediately:

  * casing
  * trimming
  * type coercion

---

## 4. Logging: “Everything Is an Event”

### 4.1 Global Rule

#### Every meaningful action MUST be logged

Errors are not special — they are just one event type.

### 4.2 Mandatory Logged Events

* function entry / exit
* received inputs (sanitized)
* normalized inputs
* configuration resolution
* prompt selection
* **exact rendered prompt**
* external calls (before + after)
* decisions and branches
* validation results
* retries and backoff
* final outputs

### 4.3 Structured Logging Rules

* Logs MUST be structured (JSON/YAML).
* Every log line MUST include:

  * `run_id`
  * `task_id`
  * `span_id`
  * module name
  * role (service / generator / orchestrator)

### 4.4 Redaction & Safety

* Secrets, tokens, PII MUST be redacted.
* Prompt logging is allowed but MUST pass redaction.
* Serialization failures:

  * logged
  * never crash execution.

---

## 5. Error Taxonomy & Recovery

### 5.1 Typed Errors

All errors MUST derive from a common base (e.g. `AppError`) with:

* `code`
* `message`
* `cause`
* `retryable`
* `severity`
* `context`

#### Error categories

* Transient I/O (retryable)
* Permanent I/O (non-retryable)
* Validation / contract violation (bug)
* Logic error (bug)

### 5.2 Retry Policy

* Retry behavior MUST be:

  * explicit
  * bounded
  * logged
* Backoff and jitter required.
* Orchestrators decide retries; generators do not.

---

## 6. Configuration & Prompt Rules

### 6.1 Configuration

* All model parameters and behavior live in YAML.
* Secrets MUST come from env or secret store.
* YAML MUST NOT contain secrets.
* Any wrapper / orchestration timeout MUST be >= the configured service/model timeout (e.g., OpenAI timeout); never set a shorter outer timeout that can preempt the app-level limit.

---

### 6.2 Prompt Storage (Hard Constraint)

* **Prompts MUST NOT be centralized.**
* Each use case gets its own namespace.

Example:

```text
prompts/
  post_generation/
    system.yaml
    user.yaml
  html_generation/
    system.yaml
    user.yaml
```

### 6.3 Prompt Services

* Prompt loading, rendering, and versioning:

  * handled only by prompt services
* Generators:

  * request prompts by name
  * never read files directly

### 6.4 Prompt Logging (Mandatory)

For every model call:

* prompt file paths
* prompt version/hash
* rendered system prompt
* rendered user prompt
* model parameters
* provider request ID (if available)

Prompt text MUST NOT be dynamically constructed outside the prompt service.
Runtime concatenation, mutation, conditional assembly, injection, or inline override of prompt text outside the prompt namespace is forbidden.

---

## 7. Determinism & Reproducibility

* Prompt rendering MUST be deterministic.
* Model parameters MUST be logged explicitly.
* If provider supports it, set and log `seed`.

If an output cannot be reproduced from logs, it is a **bug**.

---

## 8. Testing & Validation Requirements

Test integrity is a first-class architectural constraint: tests MUST be hard to fake and easy to trust.

* Utilities: unit tests mandatory
* Generators: unit tests with mocked services
* Services: integration tests (sandbox/local)
* Orchestrators: pipeline tests
* Contracts:

  * serialization round-trip tests
  * schema snapshots

### 8.1 Test Integrity Rules (Anti-Cheat, Mandatory)

These rules are not aspirational; they are enforced by CI gates and fixtures described below.
Any PR that reduces mutation score, reduces coverage on critical paths, or introduces forbidden mocking patterns MUST fail CI.
If a test can pass while the production logic is removed or replaced with a trivial stub, the test is invalid by design.

Tests MUST detect real regressions, not validate mocked narratives.

Hard constraints:

* Tests MUST assert externally observable behavior:

  * returned contracts
  * persisted state (DB/files)
  * emitted events/log fields
  * side effects
* A test is invalid if it still passes after removing the core logic it claims to verify.
* Unit tests MAY mock only true external boundaries (network, external APIs, time, randomness, OS/process boundaries).
* Tests MUST NOT mock or monkeypatch the primary logic path of the unit under test.
* Patching private/internal helpers (`_private_fn`) is forbidden. Adapter-glue tests MUST instead mock at the external boundary (service module function) and assert contract + side effects at the module boundary.
* Tautological assertions are forbidden (`assert True`, `assert 1 == 1`, "no exception" as sole assertion).
* Over-mocking is forbidden: if all meaningful collaborators are mocked, at least one integration/pipeline test MUST cover the real path.
* Retry/concurrency tests MUST assert attempt count and control behavior (backoff/sleep/order), not only final status.
* Live API calls are forbidden in unit tests; integration tests MUST be explicitly marked and excluded from default CI.
* Tests MUST NOT print or expose secrets/tokens (including partial keys).
* Removing core logic must cause at least one test failure.
* Tests validating orchestration MUST assert retry counts and state transitions — not just final status.
* At least one test per orchestrator and per service MUST assert the presence of required structured log fields (`run_id`, `task_id`, `span_id`, `role`, `module`).

Additional mandatory constraints (new):

* Tests MUST assert semantic correctness of returned dataclass contracts (no default/sentinel-filled required fields).
* Tests MUST assert error taxonomy correctness (`AppError.code`, `retryable`, `severity`) for negative paths.
* Tests MUST assert idempotency behavior when applicable (same inputs -> same persisted key / no duplicate side effects).
* Golden-file tests MUST include a strict schema validation step for serialized artifacts where schemas exist.

PR validation requirement:

* Every new behavior change MUST include:

  * at least one positive-path test
  * at least one failure/edge-path test
  * assertions on both output contract and one concrete side effect (when applicable)

CI MUST enforce (expanded):

* formatting
* typing
* tests

### 8.2 Mandatory CI Gates (Enforcement, Not Optional)

The following checks MUST run in CI and fail the PR when violated:

1) Coverage gate (targeted)

* Enforce minimum line coverage globally AND per critical package:

  * `src/orchestrators/*` (critical)
  * `src/generators/*` (critical)
  * `src/services/*` (critical)
* Coverage exemptions require explicit allowlist entries with justification.

2) Mutation testing gate (anti-cheat)

* Run mutation testing on critical business logic packages (at minimum generators + orchestrators).
* Enforce a minimum mutation score threshold; reductions MUST fail CI.
* Any surviving mutation in a changed file MUST be triaged with either:

  * a new assertion, or
  * an explicit documented exemption (rare).

3) Forbidden patching gate (static)

* Fail CI if tests contain:

  * monkeypatch usage outside external boundary mocks,
  * patching of private helpers (`._` prefixed) anywhere,
  * patching of generator/orchestrator internals,
  * patching of dataclass constructors to bypass required fields.

4) Contract round-trip gate

* For every contract dataclass added/modified:

  * serialization -> deserialization -> equality (or semantic equivalence) test is mandatory.
* Any schema-backed JSON output MUST validate against the schema in tests.

### 8.3 Required Test Fixtures & Patterns

To make integrity automatic, the test suite MUST include these shared fixtures:

* `assert_logs_have_required_fields(log_records)`
  - asserts `run_id`, `task_id`, `span_id`, `role`, `module`, `event`

* `assert_no_defaulted_required_fields(dataclass_obj)`
  - fails if required fields are empty/default/sentinel when contract requires population

* `assert_app_error(err, code=..., retryable=..., severity=...)`
  - standardizes negative-path validation of error taxonomy

* `external_boundary_mocks_only`
  - a fixture that rejects patching anything except:
    - service module top-level functions
    - network/time/random/os boundaries

* `idempotency_guard`
  - where applicable: runs the same orchestrator step twice and asserts:
    - no duplicate DB rows
    - no duplicate published posts
    - deterministic output paths/hashes

### 8.4 Minimum Required Test Types Per Layer (Hard Constraint)

* Services:
  - at least 1 integration test per service module in `tests/integration/` (marked `integration`)
  - unit tests may mock network only, not service internals

* Generators:
  - unit tests with mocked services
  - must assert:
    - prompt namespace selected + prompt hash logged
    - output contracts are complete + schema-valid where applicable
    - negative-path AppError surfaces (not swallowed)

* Orchestrators:
  - pipeline tests that assert:
    - retry attempt count
    - backoff decisions
    - state transitions
    - idempotency key behavior (or explicit idempotency enforcement)

### 8.5 "Remove-the-Logic" Sentinel Tests (Anti-Cheat)

At least one test per critical generator/orchestrator MUST be designed such that:

* If core logic is replaced with a trivial stub returning empty/default values,
  the test fails due to:
  - schema validation failure, OR
  - missing side effects, OR
  - missing required logs, OR
  - mutation-killed assertions.

CI SHOULD include static analysis checks to prevent:
  * reverse imports
  * cross-role dependency violations
  * role-mixing within modules
  * forbidden cross-layer imports

---

## 9. Documentation Rules

* Every meaningful change in code, architecture, settings options or setup must be documented in readme.

## 10. Enforcement Rules

These rules are **enforceable**.

Violations:

* Multiple roles in one module -> **invalid design**
* Missing logs -> **incomplete implementation**
* Prompt text in code -> **hard violation**
* Unrecoverable errors without notification -> **bug**
* Tests that rely on shortcuts/tautologies/over-mocking -> **invalid test design**
* Unit tests with live external calls or secret exposure -> **hard violation**
* Placeholder or stub logic -> **hard violation**
* Monkeypatch-based core test validation -> **invalid test design**
* Monolithic script creation -> **invalid architecture**
* Role-mixing within a module -> **invalid design**
* Silent degradation instead of typed error -> **bug**
* Generator-level retry logic -> **architectural violation**
* Swallowed retryable errors -> **architectural violation**

Coding agents:

* MUST stop and refactor on violations
* MUST refuse invalid designs
* MUST treat logs as first-class output
* MUST follow these rules at all times
* MUST refuse to introduce placeholder logic
* MUST split monolithic modules before extending them
* MUST implement real logic or fail explicitly
* MUST validate architectural role before adding new code
* MUST stop and refactor if structural drift is detected
* MUST propagate retryable errors to orchestrators
* MUST not introduce cross-role coupling for convenience

No shortcuts.
No architectural drift.
No hidden coupling.
