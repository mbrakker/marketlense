# Evidence Process

> **Documentation type:** Current reference
> **Canonical topic:** Quality and release evidence
> **Update trigger:** Evidence manifest, review, waiver, retention, or release-review process changes.

Release evidence is generated from executed quality-gate artifacts; it is not hand-maintained in the README. The evidence tooling creates a manifest with artifact identity, schema expectations, freshness, and commit context, then produces a review against the waiver policy.

Use the repository scripts `scripts/quality/release_evidence_manifest.py` and `scripts/quality/release_evidence_review.py` with the arguments required by CI or the release procedure. Retain generated manifests and reviews in the configured output/artifact mechanism. The waiver policy is [`release_evidence_waivers.yaml`](release_evidence_waivers.yaml).

For operational diagnostics, use structured logs and retained workflow artifacts first. See [monitoring](../ops/monitoring.md) and [recovery](../ops/recovery.md).
