# Data and Artifact Model

> **Documentation type:** Architectural
> **Canonical topic:** Data and artifact model
> **Update trigger:** Contract, schema, persistence, lineage, or output-layout changes.

External and workflow boundaries use typed dataclass contracts. JSON artifacts that have schemas are validated through the schema-validation service before persistence. At the artifact boundary, optional model-provided strategy labels are deterministically normalized to supported contract values (including approved cross-enum aliases); unsupported optional labels are omitted so they cannot invalidate otherwise grounded artifacts.

The report lifecycle retains source metadata, analysis artifacts, validation results, rendered output, and operational state. Artifact lineage records content hashes and dependency relationships so reuse and restart decisions can verify retained content rather than trust a file path alone. Invalid, stale, or missing lineage is an explicit failure condition when lineage is required.

Generated and persisted analysis output is stored beneath the configured output root; durable workflow and report metadata uses the configured state and reports databases. Treat generated output as runtime evidence, not as a replacement for this reference. Schema inventory is generated in [capability manifest](../generated/capability-manifest.md).

## Validation-run manifest

Bounded validation and release canaries retain one canonical manifest in the reports database. A manifest is created with immutable configuration, policy, workflow-run, and producer-build identities. Discovery also writes an immutable cohort-member ledger, separate from mutable execution attempts. Each entity attempt retains its stage, artifact IDs, timing, typed result, retryability, repair and idempotency dispositions. Superseded attempts remain auditable while exactly one current attempt carries the entity terminal outcome. The manifest audit derives stage totals and the final validation cohort from durable rows, reconciles member/current/terminal counts, and detects duplicate source identities and ambiguous WordPress matches; release evidence must use that audit rather than reconstructing a funnel from logs.

Model-usage events retain the runtime attribution already known at call creation:
validation-run, cohort, workflow-run and report identity; publisher, workflow,
stage, artifact family, action and semantic task; prompt and policy namespace;
provider/model, cache status, tokens/cost, repair attempt; configuration/policy
hashes; and build identity. These attributes are preserved as sanitised ledger
metadata alongside provider tokens and cost. A validation-run event with a
missing required attribution is rejected at the accounting boundary; historic
blank attributes remain explicitly historical rather than inferred.

Each validation run also retains a deterministic
`validation-runs/<run-hash>/reliability_telemetry.json` artifact. It is derived
only from the immutable validation manifest and the canonical usage ledger. The
artifact measures the admitted-to-readback funnel, retains each directly
recorded failed transition, carries duration/token/cost usage before that
failure, records observed recovery, operator-intervention, and full-rerun
dispositions, and ranks failure codes in a stable Pareto order. It is rebuilt
after ingest and after publication so the retained artifact reflects the latest
manifest closure without creating a parallel telemetry store.
