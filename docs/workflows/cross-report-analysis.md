# Cross-Report Analysis

> **Documentation type:** Current reference
> **Canonical topic:** Cross-report analysis workflow
> **Update trigger:** Briefing or Signal selection, projection input, validation, or publication changes.

Cross-report analysis produces Briefings from persisted report projections and evidence. It remains inside the modular monolith and reuses the established prompt, LLM, storage, idempotency, and publication boundaries.

The workflow selects bounded, source-backed input, prepares evidence deterministically, synthesizes and validates a briefing artifact, persists the result, and can route an approved package to WordPress. It does not normalize metrics across publishers or introduce a separate analytics service.

Projected raw metrics preserve the source value and its unit when supplied. A
metric whose value already contains its display unit may have an empty separate
unit field; this remains a valid cross-report input and is never assigned a
guessed unit.

Source reports are ranked from relevance, evidence density, and recency. Each
selection round adds a `0.75` diversity bonus once to publishers not yet
represented, starting from the unchanged base score; the same-publisher reason
is used once a publisher has been selected. Ties are resolved by score,
case-folded publisher, report date, and report ID. Candidate order does not
change the selected sources or decision reasons.

The WordPress publication target for a Briefing is `wordpress:ml_briefing`.

Signal candidate extraction is also deterministic and uses the persisted
projected source, candidate, category, and evidence records; Signal publication
does not add a model call. A candidate group can remain semantically approved
for review while being held from publication. Before `signal_generation` is
queued, the candidate stage records one publication manifest with its exact
candidate IDs, source report IDs, evidence IDs, topic, and per-source category
IDs. The group must meet the configured minimum source and evidence counts and
have a category relationship for every source. Those minimums cannot be lower
than two source reports and two evidence items. A held group carries a typed
reason and is not queued.

The complete semantic candidate and group snapshot, including projected source
content hashes and evidence/category relationships, is retained immutably in
the reports database and addressed by its SHA-256 manifest identity. Later
extraction can update the current candidate view without rebinding a queued
generation job. Identical topics in different groups retain distinct slugs,
file IDs, package paths, covers, and idempotency identities while keeping the
human-readable title. Published source metadata resolves each publisher by its
exact report ID; missing attribution remains blank.

The generation worker reads only the frozen candidate, source, and evidence
IDs from that manifest. It does not select a replacement set under separate
limits. If a frozen source, evidence row, category relationship, or compatible
request filter has changed before generation, the worker fails with a typed
manifest reason; it does not publish a reduced grounding set. Generated Signal
provenance retains the exact source report and evidence IDs from the manifest.

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
