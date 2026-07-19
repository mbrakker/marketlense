# Validation and Regeneration

> **Documentation type:** Current reference
> **Canonical topic:** Validation and regeneration workflow
> **Update trigger:** Validation policy, schema, regeneration routing, or publication gate changes.

Generated report artifacts are checked for contract completeness, schema validity, and configured semantic and grounding requirements. Validation results are persisted with the report artifacts.

When a repair is supported, the workflow maps validation issues to the narrowest appropriate artifact family and revalidates the result. Retry and backoff are controlled by orchestration; generators surface typed errors rather than retrying provider calls themselves. Publication policy determines whether unresolved validation issues block WordPress side effects.

The deterministic [public editorial quality gate](../quality/public-editorial-quality.md) runs before the regeneration loop and after its final attempt. Its enabled blocking findings are merged into canonical `validation.json`, while its private before/after reports retain repair eligibility and evidence IDs. A public-copy finding is regenerated only when retained source text, an explicit evidence ID, and a supported target exist; otherwise it is explicitly abstained and remains release-blocking. This preserves passing fields and prevents generic fallback copy.

Prompt fixtures and regression controls are documented in [quality testing](../quality/testing.md). Operator recovery starts with [recovery](../ops/recovery.md).

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
