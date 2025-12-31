Below is a **fully integrated, production-grade rewrite** of your document.
I preserved your tone (hard constraints, enforceable), tightened definitions, and merged professional best practices **without bloating**.
This is suitable to be treated as a **canonical engineering constitution** for agents.

---

# Agent Architecture & Coding Rules (Mandatory)

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

**Contract evolution rules**

* Every contract MUST be versioned (`schema_version` or module-level version).
* Breaking changes REQUIRE:

  * version bump
  * explicit adapter or migration logic
* Services MUST validate both incoming and outgoing contracts.

---

### 1.2 Services (I/O Layer)

A Service is the **only** place where the system touches the outside world.

**A service module:**

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

**Hard requirements**

* Paths, credentials, constants:

  * declared once at module top
  * never duplicated
* External calls MUST be wrapped in top-level functions.
* Services MUST validate:

  * external inputs
  * external outputs
  * contract adherence

**Logging (mandatory)**

* input parameters (sanitized)
* resolved configuration
* external request (metadata only)
* external response (sanitized)
* adapted output dataclass

**Services MUST NOT**

* Decide *what* to generate
* Decide *when* to retry
* Combine multiple external systems

---

### 1.3 Generators (Business / Domain Logic)

Generators implement **what should be produced and how**.

**Generators:**

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

**Generators MUST NOT**

* Access infrastructure directly
* Read files
* Call APIs
* Decide scheduling or retries

**Logging (mandatory)**

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

**Responsibilities**

* pipeline coordination
* task lifecycle management
* retries and backoff
* state transitions
* notifications

**Orchestrators MUST**

* Call generators and services
* Track task/run/span IDs
* Apply retry strategies based on error taxonomy
* Be idempotent or enforce idempotency keys

**Orchestrators MUST NOT**

* Contain domain logic
* Contain prompt text
* Transform data beyond routing

**Logging (mandatory)**

* pipeline start/end
* task IDs and transitions
* retry decisions and reasons
* generator/service invocations
* final status per task

---

### 1.5 Utility / Core Modules

Utilities are **pure, deterministic helpers**.

**Rules**

* Stateless
* No I/O
* No global state
* Pure functions only

**Input / Output**

* `dict`, `list`, primitives, or `DataFrame`

Logging inside utilities is discouraged; logging belongs at call sites.

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

```
src/
  contracts/
  services/
  generators/
  orchestrators/
  utils/
  prompts/
```

**Import rules**

* `services` → contracts, utils
* `generators` → services, contracts, utils
* `orchestrators` → generators, services, contracts, utils
* Reverse imports are forbidden.

---

### 3.2 Single-Purpose Modules

* One module = one responsibility.
* Never mix:

  * I/O
  * domain logic
  * orchestration

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

**Every meaningful action MUST be logged.**
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

**Error categories**

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

```
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

---

## 7. Determinism & Reproducibility

* Prompt rendering MUST be deterministic.
* Model parameters MUST be logged explicitly.
* If provider supports it, set and log `seed`.

If an output cannot be reproduced from logs, it is a **bug**.

---

## 8. Testing & Validation Requirements

* Utilities: unit tests mandatory
* Generators: unit tests with mocked services
* Services: integration tests (sandbox/local)
* Orchestrators: pipeline tests
* Contracts:

  * serialization round-trip tests
  * schema snapshots

CI MUST enforce:

* formatting
* typing
* tests

---

## 9. Enforcement Rules

These rules are **enforceable**.

Violations:

* Multiple roles in one module → **invalid design**
* Missing logs → **incomplete implementation**
* Prompt text in code → **hard violation**
* Unrecoverable errors without notification → **bug**

Coding agents:

* MUST stop and refactor on violations
* MUST refuse invalid designs
* MUST treat logs as first-class output
* MUST follow these rules at all times

No shortcuts.
No architectural drift.
No hidden coupling.
