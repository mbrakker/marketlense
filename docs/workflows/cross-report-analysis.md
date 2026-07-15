# Cross-Report Analysis

> **Documentation type:** Current reference
> **Canonical topic:** Cross-report analysis workflow
> **Update trigger:** Briefing selection, projection input, validation, or publication changes.

Cross-report analysis produces Briefings from persisted report projections and evidence. It remains inside the modular monolith and reuses the established prompt, LLM, storage, idempotency, and publication boundaries.

The workflow selects bounded, source-backed input, prepares evidence deterministically, synthesizes and validates a briefing artifact, persists the result, and can route an approved package to WordPress. It does not normalize metrics across publishers or introduce a separate analytics service.

The WordPress publication target for a Briefing is `wordpress:ml_briefing`.

The CLI entrypoint is `python -m src.cli generate-cross-report-analysis`. The capability is configuration-gated; inspect [configuration](../ops/configuration.md) and [generated capability manifest](../generated/capability-manifest.md) before enabling it.
