# Validation and Regeneration

> **Documentation type:** Current reference
> **Canonical topic:** Validation and regeneration workflow
> **Update trigger:** Validation policy, schema, regeneration routing, or publication gate changes.

Generated report artifacts are checked for contract completeness, schema validity, and configured semantic and grounding requirements. Validation results are persisted with the report artifacts.

When a repair is supported, the workflow maps validation issues to the narrowest appropriate artifact family and revalidates the result. Retry and backoff are controlled by orchestration; generators surface typed errors rather than retrying provider calls themselves. Publication policy determines whether unresolved validation issues block WordPress side effects.

The deterministic [public editorial quality gate](../quality/public-editorial-quality.md) runs before the regeneration loop and after its final attempt. Its enabled blocking findings are merged into canonical `validation.json`, while its private before/after reports retain repair eligibility and evidence IDs. A public-copy finding is regenerated only when retained source text, an explicit evidence ID, and a supported target exist; otherwise it is explicitly abstained and remains release-blocking. This preserves passing fields and prevents generic fallback copy.

Prompt fixtures and regression controls are documented in [quality testing](../quality/testing.md). Operator recovery starts with [recovery](../ops/recovery.md).
