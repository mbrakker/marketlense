# Data and Artifact Model

> **Documentation type:** Architectural
> **Canonical topic:** Data and artifact model
> **Update trigger:** Contract, schema, persistence, lineage, or output-layout changes.

External and workflow boundaries use typed dataclass contracts. JSON artifacts that have schemas are validated through the schema-validation service before persistence.

The report lifecycle retains source metadata, analysis artifacts, validation results, rendered output, and operational state. Artifact lineage records content hashes and dependency relationships so reuse and restart decisions can verify retained content rather than trust a file path alone. Invalid, stale, or missing lineage is an explicit failure condition when lineage is required.

Generated and persisted analysis output is stored beneath the configured output root; durable workflow and report metadata uses the configured state and reports databases. Treat generated output as runtime evidence, not as a replacement for this reference. Schema inventory is generated in [capability manifest](../generated/capability-manifest.md).
