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

The deterministic [public editorial quality gate](../quality/public-editorial-quality.md) runs before the regeneration loop and after its final attempt. Its enabled blocking findings are merged into canonical `validation.json`, while its private before/after reports retain repair eligibility and evidence IDs. A public-copy finding is regenerated only when retained source text, an explicit evidence ID, and a supported target exist; otherwise it is explicitly abstained and remains release-blocking. This preserves passing fields and prevents generic fallback copy.

Prompt fixtures and regression controls are documented in [quality testing](../quality/testing.md). Operator recovery starts with [recovery](../ops/recovery.md).

## Immutable validation cohorts and closure

Release and reliability runs use an immutable admitted cohort. The cohort is
persisted before report generation, and its content hash is the cohort ID.
Drive discovery carries the same resolved run-budget and usage-ledger path as
the later ingest pipeline, so an isolated canary cannot silently reserve shared
budget capacity before membership is frozen.
The canonical validation-run manifest records every admitted member from
`discovery`, `candidate_qualification`, and `admission_preflight` before
report-processing work, then records acquisition, source preparation and
validation, evidence, taxonomy/category structured-output repair where used,
artifact generation, validation/regeneration, rendering, final HTML
validation, publication preflight, the WordPress transaction, authenticated
readback, and unchanged-repeat publication. A failed member is never
replaced.

Each manifest record retains the validation-run and cohort IDs, report/source
identity, workflow run, attempt and parent attempt, artifact inputs/outputs,
timestamps, outcome, typed failure, repair disposition, supersession state,
idempotency state, and configuration/policy/build provenance. Terminal
outcomes are deliberately constrained to `published_verified`,
`publish_ready`, `blocked`, `permanent_failure`, `abstained`, `cancelled`, or
`superseded`. A normal audit fails closed when a current admitted member has no
such terminal outcome. The release audit additionally requires every mandatory
stage group for every final-cohort report; a terminal row alone cannot conceal
an incomplete funnel.

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
