# Evidence Process

> **Documentation type:** Current reference
> **Canonical topic:** Quality and release evidence
> **Update trigger:** Evidence manifest, review, waiver, retention, or release-review process changes.

Release evidence is generated from executed quality-gate artifacts; it is not hand-maintained in the README. The evidence tooling creates a manifest with artifact identity, schema expectations, freshness, and commit context, then produces a review against the waiver policy.

Use the repository scripts `scripts/quality/release_evidence_manifest.py` and `scripts/quality/release_evidence_review.py` with the arguments required by CI or the release procedure. Retain generated manifests and reviews in the configured output/artifact mechanism. The waiver policy is [`release_evidence_waivers.yaml`](release_evidence_waivers.yaml).

For operational diagnostics, use structured logs and retained workflow artifacts first. See [monitoring](../ops/monitoring.md) and [recovery](../ops/recovery.md).

## CTO Review Evidence Bundles

`scripts/quality/collect_cto_review_evidence.py` creates a point-in-time CTO-review bundle from retained state. It snapshots each collector SQLite input with the SQLite backup API before querying it; live WAL files are never copied. Relevant crop-quality artifacts are copied into the same temporary workspace before their metrics are read. The workspace is removed after both successful and failed runs unless `--debug-retain-snapshots` is explicitly set.

Run it from the repository root:

```powershell
python scripts/quality/collect_cto_review_evidence.py --state-dir state --artifact-dir out --output-dir out/cto-review-evidence
```

The existing CSV filenames remain stable. The collector additionally writes:

- `detailed_metrics.json`: finalized structured input for summary derivation;
- `executive_summary.json`: totals derived only from that finalized detail;
- `snapshot_manifest.json`: database and crop-artifact snapshot provenance;
- `evidence_run_manifest.json`: run identity, repository state, configuration hash, runtime, and manifest hash;
- `consistency_validation.json`: a passed validation result.

Every output carries one `evidence_run_id`. Snapshot provenance records normalized source paths, temporary-relative snapshot paths, sizes, SHA-256, schema/table metadata, maximum timestamps, source journal mode, integrity checks, and foreign-key checks. Public output paths never include a workstation root or username.

The collector fails closed when a required source database is unavailable, a snapshot is corrupt, an expected artifact is missing, a manifest hash or repository SHA disagrees, a run ID is reused, or executive counts/tokens/costs differ from detailed artifacts. Monetary aggregation uses decimal arithmetic; cost equality allows only the documented `0.000001` USD tolerance. Optional state databases are explicitly recorded as unavailable rather than fabricated.

Reproducibility means the database-backed and crop metrics in one bundle all derive from the immutable temporary snapshots created for that run. It does not mean that a second run receives the same run ID, timestamps, operating-system metadata, or repository dirty-state marker. A debug-retained workspace is an operator diagnostic and must not be published as release evidence.
