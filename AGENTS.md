# MarketLense Agent Engineering Policy

## 1. Scope and precedence

This policy governs coding agents working in this repository. It applies to source, tests, configuration, CI, scripts, and documentation. Subdirectory `AGENTS.md` files may add narrower rules for their subtree but may not weaken this policy.

Policy hierarchy, from highest-level guidance to implementation detail:

1. `AGENTS.md` — concise execution rules for agents.
2. `docs/quality/architecture_policy.yaml` — canonical machine-readable architecture and enforcement inventory.
3. Focused policy and procedure documents — testing, logging, refactoring, live validation, documentation, and operations.
4. CI scripts and workflows — executable checks for rules that can be verified reliably.

User instructions define the requested outcome. Repository policy defines how that outcome may be implemented. When human-readable and executable policy disagree, inspect repository evidence and correct the conflict; do not preserve ambiguity. A rule is machine-enforced only when a working CI check covers it. Otherwise it is review-based.

Requirement levels are used deliberately:

- **MUST** means mandatory and objectively reviewable or machine-enforced.
- **SHOULD** means the strong default; deviation requires repository evidence recorded in the change.
- **MAY** means permitted.

## 2. Operating principles

### 2.1 Evidence before change

Before a non-trivial change, inspect the relevant code, contracts, tests, configuration, documentation, and recent behavior. Do not invent repository details. Translate the request into observable success criteria and give each material step a verification method.

When inspection resolves ambiguity, continue without asking. Ask only when an unresolved choice materially affects public behavior, data loss, irreversible migration, security, credentials, external publication, uncontrolled spend, incompatible architecture, or materially different product outcomes.

For local, reversible, testable decisions, choose the simplest viable interpretation, state any material assumption, implement, and validate.

### 2.2 Simplicity and minimum scope

Implement the smallest production-quality change that satisfies the requested behavior, existing contracts, current architecture, relevant tests, and operational constraints.

Do not add:

- speculative features or future-proofing without current evidence;
- generic frameworks for one current use case;
- interfaces with one implementation unless an unstable external boundary or genuine test seam requires one;
- unused configuration or optional modes without a current use case;
- persistence layers, queues, workers, processes, services, packages, or databases without demonstrated operational need;
- factories, registries, adapters, facades, or strategies that only rename or forward calls;
- defensive branches for states prohibited by current contracts;
- compatibility layers for unsupported historical behavior;
- broad refactors when a local correction is sufficient.

Every added layer, module, option, state, fallback, retry path, dependency, and external call needs a concrete current reason. When two designs are correct, prefer fewer concepts, modules, options, state transitions, dependencies, and calls; simpler tests; and clearer failure behavior.

### 2.3 Deterministic before probabilistic

Use deterministic parsing, normalization, validation, lookup, deduplication, scoring, and reuse before invoking an LLM or other probabilistic system. A probabilistic call MUST have a current semantic purpose that deterministic code cannot satisfy adequately.

Model outputs are untrusted external data. Validate schema, grounding, completeness, provenance, and allowed side effects before use. Do not use an LLM to conceal missing deterministic logic or contract failures.

### 2.4 Reuse before regeneration

Before regenerating or recalling an external system, check canonical persisted artifacts, hashes, caches, ledgers, and idempotency records. Reuse only when provenance and compatibility are valid. Never reuse stale or mismatched data merely to avoid a failure.

### 2.5 Safe autonomy and clarification threshold

Proceed autonomously on repository-local, reversible, in-scope work. Report material assumptions and tradeoffs, but do not turn routine naming or internal structure into blockers. Stop when authority is missing for an irreversible or externally consequential action.

## 3. Architecture boundaries

The role map, import directions, permitted I/O, and canonical external-system entrypoints live in `docs/quality/architecture_policy.yaml`. Do not duplicate that inventory here.

### 3.1 Contracts

Use versioned typed contracts at public architectural boundaries and persisted or external payload boundaries. Public contracts MUST document field semantics and validate required data. Breaking persisted or public changes require an explicit version transition and adapter or migration.

Do not require a dataclass for every private helper or scalar result. Private helpers MAY use well-typed native values when clearer. Do not create a contract merely to wrap one primitive without semantic value.

### 3.2 Services

Services own external I/O and infrastructure interaction, including filesystem, database, network, external APIs, browser runtime, email, PDF/OCR infrastructure, and model providers. Deterministic adaptation needed to communicate safely with the external system belongs inside its service boundary.

Services MUST NOT own workflow sequencing, domain editorial decisions, retry policy, or publication policy. One external system has one canonical public boundary; capability-based private modules MAY exist behind it.

### 3.3 Generators

Generators own domain production and semantic transformation. They MAY call canonical services. They MUST NOT directly access external infrastructure, read prompt files, own workflow scheduling or retries, or suppress retryable errors.

### 3.4 Orchestrators

Orchestrators own sequencing, branching, explicit workflow state, retry decisions, recovery, and idempotent coordination. They MUST NOT contain substantial domain-generation logic or external-client implementation.

### 3.5 Utilities

Utilities SHOULD be deterministic and free from external I/O. `utils` is not a catch-all for misplaced service, domain, or orchestration logic.

### 3.6 CLI and UI

CLI and UI code MAY parse input, present output, and call approved orchestrator or service boundaries. They MUST NOT duplicate domain logic or external integration implementations.

### 3.7 Prompts and model boundaries

Prompt resources remain under `src/prompts`. Prompt loading, rendering, composition, hashing, and validation belong to the prompt service. Code MAY supply structured dynamic values but MUST NOT embed substantial prompt prose outside approved prompt resources.

Model parameters and routing policy belong in canonical operator configuration where they are genuinely tunable. Output schemas and security invariants remain code-owned.

### 3.8 Modular-monolith rule

The default architecture is one deployable modular monolith with explicit internal boundaries. A new deployable unit requires an architecture review and current evidence for at least two material needs: independent scaling, independent deployment cadence, hard failure isolation, genuinely separate ownership, or materially different runtime/compliance requirements. “Future readiness” is not evidence.

## 4. Change discipline

### 4.1 Surgical changes

Every changed line MUST trace to the request, required validation, or a necessary integrity correction. Do not reformat, rename, delete, or refactor unrelated code. Report unrelated issues separately.

### 4.2 No speculative abstractions

Abstract only when it reduces current coupling or complexity, supports multiple real implementations, protects an unstable external boundary, or creates a genuine contract seam. Pass-through layers and artificial subdomains are prohibited.

### 4.3 Rare edge-case proportionality

Effort for an edge case MUST be proportional to probability, impact, detectability, recoverability, and repository evidence. Handle a rare case when it creates security exposure, data loss/corruption, irreversible side effects, observed runtime failures, an explicit contract obligation, or is inexpensive without distorting the main design.

Otherwise document the limitation, fail explicitly when appropriate, and avoid building a large mechanism around a theoretical or easily recoverable case.

### 4.4 Refactoring and decomposition

Do not materially worsen an existing architectural violation. Correct it in the current task only when necessary for safe implementation and reasonably bounded. Otherwise preserve scope, record the issue, and create or reference a separate remediation item.

Line count alone is not a violation; semantic responsibility is primary. Do not split a coherent module merely to reduce length or create thin forwarding modules. A movement-only refactor MUST preserve public facades, outputs, prompts, provider calls, retries, cache keys, artifact paths, costs, state transitions, and side effects unless behavior change is explicitly authorized.

### 4.5 Architecture-review triggers

Use only the triggers in `docs/quality/architecture_policy.yaml`. A review records the current need, boundary and ownership, failure/data model, simpler alternatives, validation, and rollback. Do not require unrelated refactoring or ceremonial review for ordinary feature work.

## 5. Configuration and secrets

Local secrets and credentials MUST be stored in `.env`. This includes API keys, OAuth secrets and refresh tokens, passwords, mailbox or WordPress credentials, sensitive browser identities, and private service tokens.

- `.env` MUST be ignored and untracked.
- Secret values MUST NOT appear in source, YAML, tests, fixtures, documentation, screenshots, logs, or errors.
- `.env.example` MUST list required names using empty or clearly fake values and MUST be safe to commit.
- Application code MUST resolve secrets through the canonical configuration service.
- Tests needing real credentials MAY load `.env` without displaying values.
- Production MAY inject the same environment-variable interface through deployment-managed secrets; `.env` is not itself a production secret manager.

Operator configuration contains genuinely tunable policy. Code owns invariants, security rules, algorithms, schema semantics, mandatory validation, and non-tunable states. Do not move ordinary logic into YAML merely to make it configurable. Outer timeouts MUST NOT pre-empt configured service timeouts.

## 6. Error handling, retries, and idempotency

Expected application failures MUST use the canonical `AppError` taxonomy with stable code, retryability, severity, actionable context, and preserved cause where safe. Do not add handling for impossible contract states or fallback behavior that masks corruption.

Retries MUST be explicit, bounded, and owned by orchestrators. Backoff and jitter apply where appropriate. Nested or hidden retries are prohibited. Repeatable external writes and workflow steps MUST use stable idempotency keys or equivalent duplicate-side-effect protection.

Prefer explicit failure over silent degradation unless documented product policy permits abstention or partial output.

## 7. Logging, audit, and data safety

Structured logs are required at meaningful operational boundaries: workflow transitions, external calls, retries, expensive operations, state mutations, idempotency/cache/route/validation decisions, terminal outcomes, and unexpected failures. Do not add entry/exit logs to every pure helper.

Operational events SHOULD include available `run_id`, `task_id`, `span_id`, event, module, role, workflow, and relevant non-sensitive entity identity.

Standard logs MUST NOT contain complete rendered prompts, source extracts, raw model responses, email content, credentials, personal data, or complete external payloads. Record prompt namespace/hash, redaction hash, schema version, model and parameters, request ID, token usage, validation outcome, and retained audit-artifact reference instead.

Every standard structured event MUST remain within the canonical byte, collection, and nesting limits. Call sites MUST log explicit scalar/count-based summaries rather than serializing complete first-party request or result contracts; retained artifact references are preserved as paths or hashes. The guard may reduce an oversized event and emit only bounded reduction metadata, never discarded content.

Full prompt or response retention is allowed only through a dedicated access-controlled audit mechanism with explicit configuration, redaction, retention policy, and storage ownership.

Exact reproducibility is required for deterministic code. Model-backed operations must be auditable, replayable from retained approved inputs and metadata, schema validated, grounding validated, and regression evaluated; byte-identical LLM output is not required.

## 8. Testing policy

### 8.1 Test behaviour, not implementation stories

Tests verify observable behavior: returned contracts, persisted state, generated artifacts, approved external-boundary interactions, high-value events, retry counts, state transitions, idempotency, and validation failures. A test that still passes when its core behavior is removed is invalid.

Every code change MUST update the corresponding test suite in the same change set. Tests MUST cover the changed observable behavior, relevant failure or edge behavior, and any changed side effect; a documentation, policy, or other non-code-only edit is the sole exception.

Use the lowest-cost test that provides credible evidence. Test depth and edge coverage SHOULD be proportional to change risk. New behavior normally needs a positive path and a meaningful failure or edge path; add side-effect assertions when side effects exist.

### 8.2 Mocking policy

Prefer deterministic pure tests, in-memory repositories, local fixtures, protocol fakes, recorded responses, local HTTP servers, sandbox services, and real integration tests over mocks.

Mocks or fakes MAY replace true external boundaries, time, randomness, OS/process boundaries, or canonical public service functions when they are the smallest reliable seam. They MUST NOT replace the primary logic under test, private helpers, dataclass constructors, generator/orchestrator internals, or every meaningful collaborator. Assert both outcome and relevant interaction or side effect.

### 8.3 Monkeypatch prohibition

Monkeypatching is forbidden throughout repository-owned tests. This includes pytest `monkeypatch`/`MonkeyPatch`, modifying module globals at runtime, patching private helpers, altering import-time objects to bypass dependency flow, and replacing internal generator or orchestrator functions. Use explicit dependency injection, approved public-boundary fakes/mocks, subprocess tests, or a local integration boundary.

The static forbidden-patching gate enforces reliably detectable forms. Architectural intent remains review-based where static detection would be noisy.

### 8.4 Live LLM and API tests

Real LLM and external API calls are allowed in controlled integration or live tests. They are never required in the default fast suite.

Such tests MUST:

- use explicit `integration` or `live` markers and opt-in guards;
- load credentials from `.env` or a secure CI environment;
- bound request count, tokens, duration, and expected cost;
- use sandbox/read-only targets or uniquely scoped reversible writes;
- avoid publishing, emailing, destructive mutation, or uncontrolled third-party writes;
- redact prompts, payloads, responses, and secrets from output;
- validate contracts and record non-sensitive provider metadata;
- skip clearly when credentials or opt-in are absent.

Use live calls only when they provide evidence mocks cannot: provider compatibility, authentication, schema adherence, model routing, or end-to-end boundary health. See `docs/quality/testing.md`.

### 8.5 Required validation by change type

- Pure logic: focused unit tests and typing/linting.
- Contract: semantic validation plus serialization round trip and schema snapshot where applicable.
- Service: boundary tests; controlled integration for provider behavior when warranted.
- Generator: service fake or controlled integration; output completeness, schema, grounding, and error propagation.
- Orchestrator: sequencing, retry count, state transitions, idempotency, and terminal logs.
- Prompt: namespace/hash, fixture regression, schema/grounding validation, and bounded live canary only when needed.
- Migration: forward behavior, idempotency, rollback/recovery evidence, and representative persisted data.
- Documentation/policy/CI: targeted validator tests and the corresponding executable gate.

Coverage, mutation, typing, formatting, architecture, and repository-hygiene thresholds are defined by executable policy and release gates. Do not weaken a threshold or test merely to make a change pass.

### 8.6 End-to-end validation after significant code work

After any significant code change, agents MUST run the current bounded validation workflow through discovery, acquisition, ingest, and publish, in that order. The run MUST use the repository's approved isolated or otherwise safe profile and retain the normal validation and publication safeguards; it MUST NOT publish, email, or make uncontrolled external writes merely to satisfy this requirement.

Agents MUST investigate and fix every error produced by that validation run that is attributable to the change, then rerun the affected stage and all downstream stages. Do not report the work complete until the full discovery-to-publish validation run passes. If an error cannot be fixed because it requires unavailable credentials, an external-system repair, or user authority, report the exact error and blocker rather than treating the validation as successful.

## 9. Documentation ownership

Every code change MUST be reflected in the corresponding documentation pack under `docs/`, selected through `docs/README.md`, in the same change set. Before coding, identify that pack; update its canonical document to describe the current behavior, boundary, workflow, configuration, validation, or operational consequence, and regenerate derived references through their canonical script when applicable. The root README is an orientation page, not a change ledger and not the mandatory destination for every change.

Do not duplicate a canonical procedure across documents. Link to it. Historical plans and reviews record decisions but do not override current policy.

## 10. Completion and reporting

Completion claims MUST be evidence-based. Before reporting done:

1. inspect the final diff for scope and secret exposure;
2. run the narrowest relevant validators and affected tests;
3. after significant code work, run and pass the required discovery, acquisition, ingest, and publish validation workflow;
4. run broader fast gates in proportion to risk;
5. report exact commands and results, including skipped or unavailable checks;
6. distinguish newly introduced failures from pre-existing failures;
7. state residual risks, human-review rules, and any unverified external behavior.

Do not claim a rule is enforced, a test passed, or behavior was verified without direct evidence.

## 11. Detailed policy references

- Machine-readable architecture and enforcement: `docs/quality/architecture_policy.yaml`
- Architecture explanation: `docs/quality/architecture-policy.md`
- Testing and live validation: `docs/quality/testing.md`
- Release and quality gates: `docs/quality/release-gates.md`
- Evidence and completion records: `docs/quality/evidence.md`
- Refactoring and repository boundaries: `docs/architecture/role-boundaries.md`
- Configuration ownership: `docs/ops/configuration.md`
- Credentials and secret handling: `docs/ops/credentials.md`
- Documentation map: `docs/README.md`
- Canonical backlog: `CONSOLIDATED_TODO.md`
