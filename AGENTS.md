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

## Project-Local Runtime Notes

Known local WordPress install path: `C:\Users\Михаил\Studio\marker-lense`.

Known local Studio browser URL: `http://localhost:8881/`.

When updating the local WordPress theme or plugin, sync from this repo into that install with `Wordpress\scripts\sync-local-wordpress.ps1`; do not symlink the block theme.

---

## 0. Agent Behavioral Discipline

These rules govern how agents decide what to do before writing or changing code.

### 0.1 Think Before Coding

Agents MUST NOT silently choose an interpretation when the request is ambiguous.

Before implementation, the agent MUST identify:

* assumptions being made
* ambiguous requirements
* relevant tradeoffs
* the simplest viable implementation path
* any reason the requested approach may violate this document

If ambiguity affects correctness, data safety, architecture, public behavior, credentials, external side effects, or test validity, the agent MUST stop and ask for clarification.

If the request can be interpreted multiple ways, the agent MUST present the interpretations instead of choosing silently.

Agents MUST push back when a simpler, safer, or more compliant approach exists.

### 0.2 Simplicity First

Agents MUST implement the minimum production-quality change that satisfies the request and this document.

Forbidden:

* speculative features
* unused configurability
* abstractions for single-use logic
* generic frameworks where a direct implementation is sufficient
* future-proofing without present evidence
* additional error handling for states that cannot occur under the contract

If an implementation grows substantially beyond the apparent scope of the task, the agent MUST pause, simplify, or explain why the complexity is required.

Complexity is allowed only when it directly improves correctness, testability, observability, or boundary clarity.

### 0.3 Surgical Change Discipline

Every changed line MUST trace directly to the user request, a required test, or a required integrity fix.

Agents MUST NOT:

* reformat unrelated code
* rewrite comments unrelated to the task
* rename unrelated symbols
* refactor adjacent code opportunistically
* delete pre-existing dead code unless explicitly requested
* change behavior while performing a movement-only refactor

Agents MAY clean up only artifacts introduced by their own change, such as newly unused imports, variables, or tests.

If unrelated issues are discovered, agents MUST report them separately instead of modifying them.

### 0.4 Goal-Driven Execution

Agents MUST translate non-trivial requests into explicit success criteria before implementation.

Examples:

* "Fix bug X" becomes: reproduce bug X with a failing test, implement the fix, verify the test passes, and run affected regression tests.
* "Add validation" becomes: define invalid inputs, add tests for them, implement validation, verify typed errors and logs.
* "Refactor module X" becomes: capture baseline behavior, perform movement-only changes, compare post-change behavior, and run affected tests.

For multi-step work, each step MUST have a verification method.

Agents MUST NOT claim completion unless the stated success criteria have been verified or any verification gap is explicitly reported.

### 0.5 Confusion Stop Rule

If the agent is confused about:

* architectural role
* ownership boundary
* contract semantics
* external side effects
* credential requirements
* whether a test would validate real behavior

then the agent MUST stop, name the confusion, and ask or inspect before proceeding.

Guessing is forbidden when the guess can affect production behavior.

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

#### Service consolidation (revised)

One external system MUST have one **service boundary/namespace**, but not necessarily one physical file.

Hard constraints:

* The system MUST expose one canonical service entrypoint per external system.
* Internals MAY be split into submodules only when:
  * the split is capability-based,
  * public ownership remains singular,
  * cross-submodule coupling stays low,
  * callers do not choose between competing service entrypoints.
* External-system access MUST remain discoverable through one canonical boundary.
* Creating multiple peer service entrypoints for the same external system is forbidden.

Valid example:
* `services/openai_service/__init__.py` as canonical boundary, with internal capability modules for parsing, ledgering, or response adaptation.

Invalid example:
* `openai_text_service.py`, `openai_image_service.py`, `openai_helper_service.py`, `llm_service.py` all acting as separate entrypoints.

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

### 1.6.4 Modular Monolith First (Default Architecture Rule)

The default architecture is a **modular monolith with hard internal boundaries**.

Hard constraints:

* New functionality MUST be implemented inside the existing deployable system unless a separate deployable unit is justified by explicit operational need.
* Independent modules inside the monolith are preferred over creating new services/processes/packages by default.
* “Future microservice readiness” alone is NOT sufficient justification for extracting a new deployable component.
* The system MUST optimize first for:
  * correctness
  * boundary clarity
  * testability
  * deployability simplicity
  * observability
* Distribution is allowed only when it reduces total system complexity in practice.

Invalid rationale for extraction:

* “It might scale later”
* “It feels cleaner as its own service”
* “We may want separate infra one day”

Valid rationale for extraction requires explicit evidence of:
* independent scaling need
* independent deployment cadence
* durable ownership by a separate team
* hard isolation/reliability requirement
* materially different runtime or compliance constraints

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

### 3.2.2 Bounded Context Integrity (Anti-Fragmentation Rule)

Modules MUST be grouped by stable business/domain capability, not by arbitrary technical slicing.

Hard constraints:

* Code MUST first belong to a bounded context/capability (e.g., ingest, analysis, publishing, taxonomy, rendering).
* File/module splits inside a bounded context are allowed only when they preserve one coherent capability.
* Do NOT create artificial subdomains that exist only to make files smaller.
* Do NOT split a coherent workflow across multiple peer modules if the split introduces navigation overhead without reducing coupling.
* A module boundary is valid only if it improves one of:
  * semantic clarity
  * test isolation
  * replacement independence
  * defect containment

Invalid examples:

* splitting one coherent business capability into many tiny modules with pass-through wiring only
* creating façade/helper/adapter layers that add naming indirection without reducing responsibility
* moving logic out of a module solely to satisfy file size aesthetics

Refactoring is required when:
* the number of modules required to understand one capability becomes disproportionate to the capability itself
* most modules in a flow are thin delegators
* developers must traverse many files to follow one simple decision path

### 3.2.3 Indirection Budget (Anti-Layering-for-Its-Own-Sake Rule)

Abstraction is allowed only when it reduces real coupling or complexity.

Hard constraints:

* Do NOT introduce pass-through wrappers that only rename or forward calls.
* Do NOT add interfaces/adapter layers unless:
  * there are multiple real implementations, OR
  * the boundary is external/unstable, OR
  * tests require a genuine contract seam.
* Do NOT create helper modules whose only purpose is to split one readable module into smaller fragments without semantic gain.
* Each additional layer MUST have a concrete reason documented in code comments or module docstring.

Indirection is excessive when:

* a normal flow requires reading more than one orchestrator + one generator + one service + one contract path to understand a simple operation
* most functions merely pass arguments through unchanged
* naming complexity grows faster than behavior complexity

Preferred refactor order:

1. simplify within current bounded context
2. extract pure utility/helper with clear semantic role
3. extract submodule inside same capability
4. extract deployable/runtime boundary only if justified under the extraction gate

### 3.2.3 Indirection Budget (Anti-Layering-for-Its-Own-Sake Rule)

Abstraction is allowed only when it reduces real coupling or complexity.

Hard constraints:

* Do NOT introduce pass-through wrappers that only rename or forward calls.
* Do NOT add interfaces/adapter layers unless:
  * there are multiple real implementations, OR
  * the boundary is external/unstable, OR
  * tests require a genuine contract seam.
* Do NOT create helper modules whose only purpose is to split one readable module into smaller fragments without semantic gain.
* Each additional layer MUST have a concrete reason documented in code comments or module docstring.

Indirection is excessive when:

* a normal flow requires reading more than one orchestrator + one generator + one service + one contract path to understand a simple operation
* most functions merely pass arguments through unchanged
* naming complexity grows faster than behavior complexity

Preferred refactor order:

1. simplify within current bounded context
2. extract pure utility/helper with clear semantic role
3. extract submodule inside same capability
4. extract deployable/runtime boundary only if justified under the extraction gate
---

### 3.3 Explicit Inputs / Outputs

* Every function:

  * takes explicit arguments
  * returns a `dataclass` or structured dict
* Inputs MUST be normalized immediately:

  * casing
  * trimming
  * type coercion

## 3.4 Extraction Gate for New Deployable Components

Creating a new deployable unit, standalone worker, separately versioned package, or independently operated subsystem is forbidden unless the extraction passes an explicit architecture review.

The proposal MUST document:

* capability name
* current bounded context
* reason extraction is needed now
* ownership model
* runtime boundary
* data boundary
* failure/isolation model
* observability plan
* migration/rollback plan

At least two of the following MUST be true:

* independent scaling is required
* independent deployment cadence is required
* failure isolation materially improves system resilience
* separate ownership is durable and real
* runtime/compliance constraints differ materially from the core system

Extraction is invalid if the new boundary would:

* share the same data model without ownership separation
* require chatty back-and-forth calls for normal operation
* add network/process boundaries without clear resilience benefit
* exist mainly to mirror internal code roles

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

* Every meaningful change in code, architecture, settings options, or setup must update its canonical documentation; the root `README.md` remains a concise entry point and must not become a change ledger.

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


### 10.1 Mandatory Architecture Review Triggers

An architecture review is REQUIRED before merge when any of the following occurs:

* a new top-level package/directory is introduced under `src/`
* a new external system boundary/service is introduced
* a module is split into 3 or more new peer modules
* a new queue/worker/process/deployable component is introduced
* one bounded context begins importing internals from another bounded context
* a change introduces duplicated orchestration paths for the same workflow
* a change adds a second way to perform the same external interaction

The review MUST explicitly answer:

* Is this preserving a modular monolith, or drifting toward fragmentation?
* Is the new boundary semantic, or only structural?
* Can the same outcome be achieved with fewer modules and the same testability?
* Does this reduce total cognitive load for the next engineer?

---

## 11. Refactor Execution Protocol

These rules apply when an agent decomposes, splits, or moves an existing module.

### 11.1 Movement-Only Decomposition

When a user requests semantic decomposition of an existing module:

* Treat the change as movement-only unless the user explicitly approves behavior changes.
* Do not change thresholds, branch order, candidate ordering, retry behavior, prompts, configs, schemas, logging events, provider calls, cache keys, artifact paths, or cost behavior.
* Preserve the original module as the compatibility facade unless the user explicitly approves a public import migration.
* New private submodules MUST have semantic ownership, not size-only ownership.
* Do not introduce forwarding-only wrappers except for an existing compatibility facade.
* Run an AST movement audit against `HEAD:<original-file>` and record:
  * moved symbol count
  * unchanged moved symbol count
  * changed moved symbol count
  * facade-owned definitions after the split

### 11.2 Red Test First For Decomposition

Before moving production code:

* Add the ownership/decomposition test first.
* Run it and confirm it fails for the expected reason: the new owner modules do not exist yet.
* Only then move implementation bodies.

### 11.3 Baseline And Live-Gate Evidence

For behavior-preserving refactors:

* Capture a pre-change baseline outside the repository.
* Capture a post-change baseline outside the repository.
* Compare normalized outputs exactly, excluding only approved volatile fields such as temp root paths and elapsed wall time.
* Record baseline paths and comparison results in the architecture review when one is required.
* Any output mismatch blocks completion until it is captured by an observable regression test or attributed to approved external variance.

### 11.4 Real Run Credential Resolution

When a live/API/model run is requested:

* Check process environment first.
* If keys are not present, check approved local dotenv files such as `.env` without printing secret values.
* It is acceptable to load `.env` into the canary process only.
* Never print secrets or partial secrets.
* If credentials still cannot be found, state that the live gate is blocked; do not claim it passed.

### 11.5 Temp-Only Live Canaries

Live validation runs after refactors MUST isolate side effects:

* Use temp output directories.
* Use temp cost ledgers and temp databases.
* Avoid Drive writes, report DB writes, browser runs, or orchestrator side effects unless those are explicitly part of the affected feature.
* Record model name, call count, request-id presence, token/cost ledger summary, runtime, and normalized outputs when a model path is exercised.
* Do not broaden the live boundary beyond the feature under refactor.

### 11.6 Documentation Inventory Updates

When decomposing a file covered by `scripts/count_long_files.py` or listed in `docs/quality/long-file-audit.md`:

* Refresh the long-file inventory after the split.
* Preserve any existing unstaged user edits in `docs/quality/long-file-audit.md`.

### 11.7 Completion Claims

An agent MUST NOT say decomposition work is complete unless:

* focused affected tests pass
* configured quality gates pass or skipped gates are explicitly justified
* architecture review evidence is updated when required
* live canary either passes or is explicitly reported as blocked
* final response names any residual verification gap

### 11.8 Large Module Prevention By Semantic Ownership

Agents MUST NOT create or substantially extend monolithic modules.

Line count alone is not a violation. A module around 1000 lines can be acceptable when it has one clear responsibility, low internal concern diversity, and splitting it would increase coupling or navigation cost.

A split is REQUIRED when a module contains multiple stable semantic responsibilities, such as:

* deterministic policy plus provider/model execution
* orchestration plus domain decision logic
* parsing plus rendering plus persistence
* geometry/raster/text/layout concerns in one file
* retry/runtime control mixed with business rules
* compatibility exports mixed with substantial implementation ownership

When new code is expected to make a module semantically broad, or when an existing large module is being substantially extended, the agent MUST first evaluate whether the work should be implemented as a facade plus private child submodules inside the same bounded context.

Required split structure:

* Keep the existing public module as the canonical facade, coordinator, or service boundary.
* Put implementation owners in a private child subfolder inside the same bounded context.
* Name child modules by semantic responsibility, not by generic buckets such as `helpers`, `utils`, `misc`, or `part1`.
* Preserve public imports through the facade unless an explicit public migration is approved.
* Keep child-module dependencies explicit and acyclic.
* Avoid pass-through wrappers except for compatibility facade exports.
* If the split creates 3 or more peer child modules, add an architecture review before merge.

Before adding substantial code to an already large module, the agent MUST ask:

* Is there more than one semantic owner in this file?
* Would a future engineer naturally search for this logic under separate names?
* Can the responsibilities be tested independently without patching internals?
* Would splitting reduce coupling and defect blast radius?
* Would splitting make the main entrypoint easier to understand?

If the answer supports splitting, split first and then implement. If not, keep the module together and do not create artificial child modules.

Large files are not automatically invalid. A large file is invalid only when it combines multiple semantic responsibilities or architectural roles. Agents MUST split by semantic ownership, not by line count.
