# DoubleVerify Expert View safe-removal replay — 2026-09-25

The exact retained canary artifacts were replayed under fix commit `eb273a46d421ffc65662671e6d7da43fae3b84d4`. The original source canary on `c89e1af249be771acb515a8d255f56c43c4b359c` ended with `soft_copy_claim_provenance_coverage_invalid` for `expert_comment`; it retained candidate audits 1 and 2 but no candidate 3.

The retained Expert View issues then selected this distinct ladder:

1. `REGENERATE_ITEM/current_evidence`
2. `REBIND_EVIDENCE/alternative_evidence`
3. `REMOVE_CLAIM/safe_removal`

At strategy 3, Expert View became empty, all 4 stale Expert View claims were retired, retained-claim coverage passed, and the former terminal error did not recur. Candidate validation passed with zero issues; the candidate audit status was `pass` with outcome `candidate`. The safe-removal path made zero model calls.

- Candidate: `tmp/doubleverify-safe-removal-replay-20260925/ias-first-attempt-3dq_dgex/output/dv-qualityandattentionbenchmark-q1-2026-pdf/report_analysis/artifacts_regen_candidate_3.json`
- Candidate SHA-256: `dab61f52511ff4ecc5694047be723d92d08cd9de143efb481b60e8b2329acd2d`
- Replay root: `tmp/doubleverify-safe-removal-replay-20260925/ias-first-attempt-3dq_dgex`
- Full audit and hashes: [JSON replay record](doubleverify-safe-removal-replay-20260925.json)

This was a deterministic retained-artifact replay; it did not run a live report or publication.
