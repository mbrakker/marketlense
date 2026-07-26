# Validation and Regeneration

> **Documentation type:** Current reference
> **Canonical topic:** Validation and regeneration workflow
> **Update trigger:** Validation policy, schema, regeneration routing, or publication gate changes.

Generated report artifacts are checked for contract completeness, schema validity, and configured semantic and grounding requirements. Validation results are persisted with the report artifacts.

When a repair is supported, the workflow maps validation issues to the narrowest appropriate artifact family and revalidates the result. Retry and backoff are controlled by orchestration; generators surface typed errors rather than retrying provider calls themselves. Publication policy determines whether unresolved validation issues block WordPress side effects.

Provider enum formatting is normalized deterministically before artifact schema
validation: case, spaces, and hyphens are canonicalized only to an already
approved enum token. This does not expand the allowed semantic vocabulary;
unknown values still fail closed.

The deterministic [public editorial quality diagnostics](../quality/public-editorial-quality.md) run before the regeneration loop and after its final attempt. They retain repair eligibility and evidence IDs and may route scoped regeneration, but they are not an independent release decision. After the final render, the canonical `publish_readiness.json` evaluates the exact HTML and normalized WordPress projection together with the final semantic/grounding report, category decisions, evidence lineage, accepted crop linkage, promotion state, provenance, and metadata surfaces. Publication consumes that signed/hash-bound artifact instead of rereading `validation.json` as a second policy. A public-copy finding is regenerated only when retained source text, an explicit evidence ID, and a supported target exist; otherwise it is explicitly abstained and final readiness remains failed. This preserves passing fields and prevents generic fallback copy.

Prompt fixtures and regression controls are documented in [quality testing](../quality/testing.md). Operator recovery starts with [recovery](../ops/recovery.md).

## Immutable validation cohorts and closure

Release and reliability runs use an immutable admitted cohort. The cohort is
persisted before report generation, and its content hash is the cohort ID.
Its validation-run ID is separately derived from that cohort ID together with
the admission configuration hash, policy hash, and producer-build identity.
Consequently, replay is idempotent only for the same complete provenance; a
stale cohort fails before report or provider work and must be refrozen under
the current policy rather than being silently rebound to a new run.
Drive discovery carries the same resolved run-budget and usage-ledger path as
the later ingest pipeline, so an isolated canary cannot silently reserve shared
budget capacity before membership is frozen.
The canonical validation-run manifest records every admitted member from
`discovery`, `candidate_qualification`, and `admission_preflight` before
report-processing work in a separate immutable member ledger. It then records
acquisition, source preparation and validation, evidence generation, a generic
structured-output-repair disposition, taxonomy, category fit, artifact
generation, regeneration, grounding and semantic validation, rendering, final
HTML validation, ingestion, publication preflight, WordPress lookup and write,
authenticated readback, and unchanged-repeat publication. A failed member is
never replaced; stages that are unsafe after an earlier terminal failure retain
an explicit `blocked` result.

Each manifest record retains the validation-run and cohort IDs, report/source
identity, workflow run, attempt and parent attempt, artifact inputs/outputs,
timestamps, outcome, typed failure, repair disposition, supersession state,
idempotency state, and configuration/policy/build provenance. Terminal
outcomes are deliberately constrained to `published_verified`,
`publish_ready`, `blocked`, `permanent_failure`, `abstained`, `cancelled`, or
`superseded`. A normal audit fails closed when a current admitted member has no
such terminal outcome. For a local run without an injected commit identity,
stage and OpenAI-usage records use the explicit `workspace` producer identity
so they remain consistent with the cohort manifest; missing cohort, report,
source, configuration, or policy provenance still fails closed. The release
audit additionally requires every mandatory stage group for every final-cohort
report; a terminal row alone cannot conceal an incomplete funnel. It rejects a
closed run when frozen/current/terminal totals do not reconcile, a member has
disappeared, attempts overlap, two reports share a source identity, or one
report has multiple active WordPress matches. A `published_verified` terminal
state additionally needs a successful reuse-marked repeat publication.

## Retained claim validation

Before publication readiness, a report may require a deterministic retained
claim-validation package. `python -m src.cli validate-retained-claims` reads
only an existing `artifacts.json` and optional retained evidence-pack JSON,
then writes evidence references, supported/unresolved factual claim counts,
and a stable package hash. Exact numeric and quote checks run without a model;
only unresolved descriptive or causal claims can be sent to an injected
semantic-validation boundary. The command does not re-ingest a source or make
provider calls.

When a queue payload sets `claim_validation_required`, publication readiness
accepts only a readable package in `awaiting_review` with zero unsupported and
unresolved factual claims. This is a pre-publication gate, not automatic
publication approval.

## Grounding-safe candidate regeneration

Regeneration never writes a repaired payload directly to `artifacts.json`.
Each attempt first persists the schema-backed candidate as
`artifacts_regen_candidate_<attempt>.json`. Before it can become current, the
workflow requires artifact-schema validation, canonical evidence-ID validation,
source-page validation against retained evidence, deterministic material
claim/insight lineage comparison, grounding validation, semantic validation,
and the public-editorial check. The corresponding validation result is retained
under `validation_regen_candidate_<attempt>.json`; a candidate failure cannot
replace either canonical artifact or canonical validation output.

The deterministic candidate check is complete only when all evidence IDs,
source pages, and material lineage relationships validate. A grounding-provider
failure is release-blocking unless that complete deterministic check passed. In
all cases, material claims classified as unsupported, numerically inconsistent,
contradicted, using an invalid comparison, missing material evidence, or citing
a hallucinated evidence ID are blocking failures. An explicitly declared,
schema-valid family abstention is retained as abstention rather than being
mistaken for lost evidence; it remains subject to the normal publication policy.

Every candidate writes a schema-backed
`regeneration_candidate_audit_<attempt>.json`. It records the original
claim/insight identity, original and candidate evidence IDs and source pages,
validation issue codes, transformation scope, before/after canonical hashes,
candidate/current artifact paths, and whether the attempt was promoted or
rolled back. Promotion uses the canonical atomic artifact store only after every
gate passes, so the prior current artifact stays recoverable until the atomic
replacement succeeds. A failed candidate remains retained for diagnosis while
the existing current artifact remains publishable only if it independently
satisfies readiness policy.
