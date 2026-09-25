# DoubleVerify final closure canary — 2026-09-25

**Result: failed; DoubleVerify is not fully closed.** The exact-HEAD isolated production-path run stopped before rendering and publication readiness. No publication write was attempted. The full JSON record and retained artifact hashes are in [the closure record](doubleverify-closure-canary-20260925.json).

- Code SHA: `c89e1af249be771acb515a8d255f56c43c4b359c`
- Frozen source: `e854b71d6fb10333b47fd518a6e51cf9` (MD5); SHA-256: `99f0cc4f7787cac52b7f89eefa7659053b3703ea100b9e0522fa500c64463d7e`
- Run: `tmp/doubleverify-closure-canary-20260925/ias-first-attempt-kua5gsl0`
- Terminal: `failed`; validation `fail`; readiness `fail`
- Failure: `soft_copy_claim_provenance_coverage_invalid`
- Provider usage: 34 calls, 296835 input tokens, 52553 output tokens, estimated $0.055678
- Regeneration: `REGENERATE_ITEM/current_evidence` then `REBIND_EVIDENCE/alternative_evidence`; distinct strategy fingerprints; both candidates rolled back.
- Initial validation: artifact_quality:expert_comment, artifact_quality:summary.executive_summary, artifact_quality:summary.tldr, metrics:insights:q1-regional-ad-attention-index, public_editorial_quality.metric_label_relationship:expert_comment, public_editorial_quality.metric_label_relationship:linkedin_post
- Candidate 1 introduced unsupported title grounding; candidate 2 included unsupported numeric values `125` and `82`. Both were rejected.
- The invalid 50% Key Figure, duplicate insight, and removed insight ID were not observed in this run. Shared `global-quality-benchmarks` quarantine and the exact standalone EMEA Engagement `116` / `s7` / page 9 binding were not exercised.
- Three artifact-quality warnings and one metrics information issue were non-blocking individually; blocking validation/provenance findings prevented readiness. Repeated PDF parser pointer notices were also non-blocking.
- Rendered HTML and successful readiness output: not produced.

The fresh run did not satisfy the closure acceptance criteria. Preserve the retained run and triage the validator/regeneration failures before marking DoubleVerify closed.
