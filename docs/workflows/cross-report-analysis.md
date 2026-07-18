# Cross-Report Analysis

> **Documentation type:** Current reference
> **Canonical topic:** Cross-report analysis workflow
> **Update trigger:** Briefing selection, projection input, validation, or publication changes.

Cross-report analysis produces Briefings from persisted report projections and evidence. It remains inside the modular monolith and reuses the established prompt, LLM, storage, idempotency, and publication boundaries.

The workflow selects bounded, source-backed input, prepares evidence deterministically, synthesizes and validates a briefing artifact, persists the result, and can route an approved package to WordPress. It does not normalize metrics across publishers or introduce a separate analytics service.

The WordPress publication target for a Briefing is `wordpress:ml_briefing`.

Queue-driven Briefings are formed only from a durable opportunity with a frozen
set of projected source-content hashes. The generation worker filters the
canonical analytics read to that immutable set, writes and validates the
Briefing package, then enqueues card-cover rendering. Cover rendering creates
the checksum-bearing package considered by publication readiness. A later
source change is collected by a subsequent opportunity; it never mutates the
running Briefing. The shared path preserves raw source-linked metrics and does
not normalize metrics across publishers.

The opportunity worker includes the complete bounded generation configuration
in the child compatibility hash. A prompt, evidence-bound, or selection-policy
change therefore creates new eligible work with the same frozen evidence while
an identical delivery remains deduplicated. Re-running a frozen opportunity
repairs a missing outbox event without changing its source manifest.

The CLI entrypoint is `python -m src.cli generate-cross-report-analysis`. The capability is configuration-gated; inspect [configuration](../ops/configuration.md) and [generated capability manifest](../generated/capability-manifest.md) before enabling it.
