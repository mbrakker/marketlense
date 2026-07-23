# Data and Artifact Model

> **Documentation type:** Architectural
> **Canonical topic:** Data and artifact model
> **Update trigger:** Contract, schema, persistence, lineage, or output-layout changes.

External and workflow boundaries use typed dataclass contracts. JSON artifacts that have schemas are validated through the schema-validation service before persistence. At the artifact boundary, optional model-provided strategy labels are deterministically normalized to supported contract values (including approved cross-enum aliases); unsupported optional labels are omitted so they cannot invalidate otherwise grounded artifacts.

The report lifecycle retains source metadata, analysis artifacts, validation results, rendered output, and operational state. Artifact lineage records content hashes and dependency relationships so reuse and restart decisions can verify retained content rather than trust a file path alone. Invalid, stale, or missing lineage is an explicit failure condition when lineage is required.

Generated and persisted analysis output is stored beneath the configured output root; durable workflow and report metadata uses the configured state and reports databases. Treat generated output as runtime evidence, not as a replacement for this reference. Schema inventory is generated in [capability manifest](../generated/capability-manifest.md).

## Validation-run manifest

Bounded validation and release canaries retain one canonical manifest in the reports database. A manifest is created with immutable configuration, policy, workflow-run, and producer-build identities. Discovery also writes an immutable cohort-member ledger, separate from mutable execution attempts. Each entity attempt retains its stage, artifact IDs, timing, typed result, retryability, repair and idempotency dispositions. Superseded attempts remain auditable while exactly one current attempt carries the entity terminal outcome. The manifest audit derives stage totals and the final validation cohort from durable rows, reconciles member/current/terminal counts, and detects duplicate source identities and ambiguous WordPress matches; release evidence must use that audit rather than reconstructing a funnel from logs.

Model-usage events retain the runtime attribution already known at call creation: validation-run and report identity, workflow, stage, artifact family, publisher, policy namespace/hash, configuration hash, build identity, and repair attempt. These attributes are preserved as sanitised ledger metadata alongside provider tokens and cost; historic blank attributes remain explicitly historical rather than inferred.
