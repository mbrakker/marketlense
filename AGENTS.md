# MarketLense Agent Engineering Policy

## 1. Scope and precedence

This policy applies to repository source, tests, configuration, CI, scripts, and documentation. Subdirectory AGENTS.md files may add narrower rules but MUST NOT weaken the root policy.

Priority is: (1) explicit task outcome, within (2) repository safety, architecture, data-integrity, and externally consequential constraints; (3) root AGENTS.md and applicable subtree rules; (4) canonical machine-readable and repository policies; (5) relevant skills; (6) detailed procedures and docs. Lower-level guidance MUST follow higher-level requirements. If the requested outcome conflicts with an invariant, identify the conflict. If written policy and executable checks disagree, inspect the evidence and resolve the smallest relevant inconsistency.

MUST is mandatory; SHOULD is the strong default. Distinguish machine-enforced rules (covered by a current working gate), objectively reviewable rules, and review-based guidance. Do not claim machine enforcement without a working gate.

## 2. Core principles

- **Inspect before changing.** For non-trivial work, inspect the relevant code, contracts, tests, configuration, documentation, and behavior. Define observable success and proportionate verification; do not broaden inspection without a reason.
- **Choose the smallest production-quality change.** Prefer fewer concepts, dependencies, options, states, fallbacks, retries, and external calls when they meet the current need. Avoid speculative features and abstractions, pass-through layers, and broad refactors without repository evidence.
- **Work autonomously on local, reversible choices.** State material assumptions and proceed. Ask only when unresolved choices materially affect public behavior, data integrity, security, credentials, irreversible work, external publication, uncontrolled spend, architecture, or product outcomes.
- **Prefer deterministic work before probabilistic calls.** Use deterministic parsing, normalization, validation, lookup, deduplication, scoring, and reuse where adequate. A model call MUST serve a current semantic purpose deterministic logic cannot adequately satisfy. Treat model output as untrusted and validate schema, grounding, completeness, provenance, and allowed side effects before use.
- **Reuse before regeneration.** Before regenerating or recalling an external system, check canonical artifacts, hashes, caches, ledgers, and idempotency records. Reuse only compatible data with valid provenance; never reuse stale or mismatched data to hide a failure.
- **Parallelize useful independent work.** Use subagents or parallel execution when available and when it materially improves speed or quality. Do not delegate tightly coupled work or create agents for ceremony.

## 3. Tools, skills, and external evidence

Use capabilities available in the current environment; do not assume a tool, plugin, MCP, or skill exists because another Codex surface supports it. Prefer repository evidence when sufficient. Use external tools for authoritative or current evidence that materially improves the work, and reuse evidence already obtained while it remains valid. Consult official OpenAI documentation before relying on changeable OpenAI API, SDK, model, or Codex behavior not established by the repository.

Use the narrowest applicable skill. Skills provide workflow guidance, not ceremony; avoid overlapping skills unless they provide complementary evidence. MarketLense routes:

- Discovery, acquisition, downloads, or browser routes: acquisition-regression
- PDF, OCR, chart, table, crop, or visual evidence: pdf-extraction-regression
- Prompts, model routing, schemas, or LLM pipeline: llm-change-eval
- Generated editorial or user-facing intelligence: editorial-output-eval
- WordPress service, theme, plugin, or published UI: wordpress-regression
- Dependency changes: dependency-upgrade
- Performance or cost optimization: speedup-proof
- Security-focused review: use the available security-audit skill when present.

## 4. Architecture boundaries

The canonical role map, import directions, I/O rules, and external-system entrypoints are in docs/quality/architecture_policy.yaml. Do not duplicate that inventory here.

- **Contracts:** MUST use versioned typed contracts at public architectural, persisted, and external payload boundaries. Public contracts MUST document field semantics and validate required data. Breaking persisted or public changes MUST have an explicit version transition and adapter or migration. Private helpers may use typed native values; do not wrap primitives without semantic value.
- **Services:** Own external I/O and safe deterministic adaptation at the boundary. Use one canonical public entrypoint per external system. Services MUST NOT own workflow sequencing, editorial decisions, retry policy, or publication policy.
- **Generators:** Own domain production and semantic transformation. They may call canonical services, but MUST NOT access infrastructure directly, read prompt files, schedule workflows, own retries, or suppress retryable errors.
- **Orchestrators:** Own sequencing, branching, workflow state, retry and recovery decisions, and idempotent coordination. They MUST NOT contain substantial domain-generation or external-client logic.
- **Utilities:** Prefer deterministic code without external I/O; utils is not a catch-all.
- **CLI and UI:** May parse and present input/output and call approved boundaries; MUST NOT duplicate domain logic or integrations.
- **Prompts and models:** Prompt resources MUST remain under src/prompts; prompt loading, rendering, composition, hashing, and validation belong to the prompt service. Code supplies structured dynamic values, not substantial prompt prose. Put genuinely tunable model parameters and routing in canonical operator configuration; keep schemas and security invariants code-owned.
- **Deployables:** Keep the modular-monolith default. New deployables MUST meet the evidence threshold in docs/quality/architecture-policy.md; review triggers are listed in architecture_policy.yaml.

## 5. Change discipline

Keep changes surgical: every changed line MUST serve the request, its required verification, or a necessary integrity correction. Do not alter unrelated behavior.

Abstract only to reduce current coupling or complexity, support real implementations, protect an unstable external boundary, or create a genuine contract seam. Do not split a coherent module just to meet a line-count preference; judge responsibility by semantics. Keep edge-case effort proportional to likelihood, impact, detectability, recoverability, and repository evidence. Do not materially worsen an existing architecture violation; address it in-scope only when necessary and bounded, otherwise record it separately.

Movement-only refactors MUST preserve public facades, outputs, prompts, provider calls, retries, cache keys, artifact paths, costs, state transitions, and side effects unless behavior change is authorized. Architecture reviews are required only for the triggers in architecture_policy.yaml and SHOULD record the need, boundary and ownership, failure/data model, simpler alternatives, validation, and rollback.

## 6. Configuration and secrets

Store local secrets and credentials in ignored, untracked .env files. Keep .env.example safe with empty or clearly fake values. Secrets MUST NOT appear in source, YAML, tests, fixtures, documentation, screenshots, logs, or errors. Application code MUST resolve secrets through src/services/config_service.py; production may inject the same environment variables through managed secrets. Tests needing real credentials may load .env only without displaying values.

Operator configuration owns genuinely tunable policy. Code owns invariants, security rules, algorithms, schema semantics, mandatory validation, and non-tunable states. Do not move ordinary logic to YAML merely to make it configurable. Outer timeouts must not pre-empt configured service timeouts.

## 7. Errors, retries, and idempotency

Expected application failures MUST use the canonical AppError taxonomy with stable code, retryability, severity, actionable context, and cause preserved where safe. Do not handle impossible contract states or add fallbacks that mask corruption. Prefer explicit failure over silent degradation unless documented policy permits partial output or abstention.

Retries MUST be explicit, bounded, and owned by orchestrators, with backoff and jitter where appropriate; hidden or nested workflow retries are prohibited. Repeatable external writes and workflow steps MUST use stable idempotency keys or equivalent duplicate-side-effect protection.

## 8. Logging, audit, and data safety

Use structured logs at meaningful boundaries: workflow transitions, external calls, retries, expensive operations, state changes, routing/cache/idempotency/validation decisions, terminal outcomes, and unexpected failures. Do not add entry/exit logs to every pure helper. Include available run_id, task_id, span_id, event, module, role, workflow, and non-sensitive entity identity.

Events MUST remain within canonical size and nesting limits. Log scalar or count-based summaries, not complete request/result contracts. Standard logs MUST NOT contain rendered prompts, source extracts, raw model responses, email content, credentials, personal data, or complete external payloads. Record audit metadata such as prompt namespace/hash, redaction hash, schema version, model parameters, request ID, token usage, validation result, and retained artifact reference.

Retain full prompts or responses only through an access-controlled audit mechanism with explicit configuration, redaction, retention, and storage ownership. Deterministic code MUST be exactly reproducible. Model-backed operations MUST be auditable, replayable from approved retained inputs and metadata, schema- and grounding-validated, and regression-evaluated; byte-identical model output is not required.

## 9. Testing and validation

Choose the narrowest verification that provides credible evidence, then expand it with behavioral, architectural, data-integrity, operational, or side-effect risk. Run relevant existing tests. Every behavior-changing code change MUST have proportionate verification; add or update tests when they provide meaningful regression protection for changed observable behavior. Material behavior normally needs a positive path and a relevant failure/edge path. Verify changed side effects. Do not add tests solely for low-risk mechanical edits, behavior-preserving refactors, comments, or typing-only changes.

Test observable behavior, not implementation stories: contracts, persisted or emitted effects, boundary interactions, logs, typed failures, retry decisions, state transitions, idempotency, and validation. Prefer pure tests, local fixtures, in-memory repositories, protocol fakes, recorded responses, local servers, and controlled integrations. Fakes or mocks may replace true external boundaries, canonical public service functions, time, randomness, or OS/process seams; never replace primary logic or every meaningful collaborator. Pytest monkeypatching, runtime global/import-time patching, and patching private helpers, dataclass constructors, or generator/orchestrator internals are forbidden; the static gate enforces detectable forms.

Real LLM/API tests are optional and excluded from the default suite. They MUST use integration or live markers and opt-in guards, credentials from .env or secure CI, bounded calls/cost/duration, sandbox/read-only or uniquely scoped reversible targets, redacted output, contract validation, and clear skips when prerequisites are absent. They MUST NOT publish, email, destructively mutate, or make uncontrolled third-party writes. Use them only when they provide evidence local tests cannot.

Match checks to the changed boundary: contracts need semantic and serialization/schema checks; services need boundary checks; generators need completeness, schema, grounding, and error checks; orchestrators need sequencing, retries, state, idempotency, and terminal outcomes; prompts need hash/fixture/schema/grounding checks; migrations need forward, idempotency, and recovery evidence. Do not weaken thresholds, tests, or gates to make work pass. Current thresholds and gate commands are in docs/quality/architecture-policy.md and docs/quality/release-gates.md.

Validation MUST reuse canonical production workflows and orchestration while isolating inputs, state, outputs, side effects, and evidence. If a component-level validation is necessary, record its limitation.

Use full or representative end-to-end validation when changes may materially affect cross-stage orchestration/state; shared or persisted contracts; discovery/acquisition routing; parsing, extraction, or evidence semantics; grounding/provenance; generated editorial intelligence; cross-stage retry, recovery, or idempotency; persistence or canonical artifact reuse; publication/readiness; shared infrastructure across stages; or a regression whose downstream effects cannot be credibly checked in isolation. For localized changes, run focused checks and affected downstream stages only. When an affected-stage check fails due to the change, it MUST be fixed and that stage plus dependent downstream stages rerun. Do not run the whole pipeline ceremonially.

During debugging, when a cohort of two or more processes is run and one or more processes fail, fix the cause and first rerun only the previously failing processes to confirm they succeed. After that focused confirmation, extend validation to the broader scope required above. If process-level isolation is not valid because of shared state or dependencies, rerun the smallest valid unit containing the failures and record why isolated reruns would be invalid.

## 10. Documentation ownership

Canonical documentation MUST be updated when a change would otherwise leave architecture, contracts/schema semantics, workflow, operator configuration, deployment/operations, externally visible behavior, supported usage, validation/recovery procedures, or a security/reliability invariant inaccurate or incomplete. Local implementation changes need no documentation when canonical docs remain accurate. Use docs/README.md to find the owner; update derived references through their canonical generator when applicable. Do not create change ledgers or duplicate procedures.

## 11. Completion

Completion claims MUST be evidence-based. Before reporting completion, inspect the final diff for scope and secret exposure, run proportionate relevant validators and checks, and report exact commands/results, skipped or unavailable checks, newly introduced versus pre-existing failures, and residual uncertainty. Claim enforcement, test success, or verified behavior only with direct evidence.

## 12. Canonical references

- Architecture and enforcement inventory: docs/quality/architecture_policy.yaml
- Architecture policy and role boundaries: docs/quality/architecture-policy.md; docs/architecture/role-boundaries.md
- Testing and release gates: docs/quality/testing.md; docs/quality/release-gates.md
- Logging and evidence: docs/quality/evidence.md
- Configuration and credentials: docs/ops/configuration.md; docs/ops/credentials.md
- Documentation map: docs/README.md
- Canonical backlog: CONSOLIDATED_TODO.md
