# Criteo and Adjust closure canary — 25 September 2026

The exact frozen PDFs from `docs/quality/reliability-cohort-20260919-a21-final/frozen_cohort.json` were used. Their MD5 hashes matched the manifest, and their SHA-256 hashes matched the previous replay. Each report started in a new isolated directory and ran through the canonical queue/supervisor production path. Publication was disabled. The structured record with paths, hashes, strategy fingerprints, and acceptance results is [`closure-canary-criteo-adjust-20260925.json`](closure-canary-criteo-adjust-20260925.json).

| Report | Tested SHA | Result | Validation / readiness | Canonical artifact | Provider calls |
| --- | --- | --- | --- | --- | ---: |
| Criteo | `009bb1c6fc139c55610b9b457f888a8180c81427` | `awaiting_review` | pass / pass | retained; SHA-256 `ba5199ba6dfed06150c801a4ecfad6f3b39ee71840d3b589ace3021d11d09aa2` | 22 |
| Adjust, first run | `009bb1c6fc139c55610b9b457f888a8180c81427` | failed during third candidate assembly | fail / fail | initial artifact retained | 37 |
| Adjust, second run | `93bdc9e5fdcc1d1e892dcfb92f731b665bdbcef8` | failed after identity strategies exhausted | fail / fail | initial artifact retained | 38 |
| Adjust, final fresh run | `bb693e95b36453bb2111a5ba1b0f1bc83a816c0b` | `awaiting_review` | pass / pass | retained; SHA-256 `d9b35ae2003fd1dcf3cc43bf3af1134463ee1fb216c5acc8bf781b5ebd265988` | 36 |

## Criteo

The prior replay failed with `card_tldr_compact_invalid` before retaining `artifacts.json`. This run retained the canonical artifact, passed validation and readiness, and ended at `awaiting_review`. Its compact TLDR is a complete 18-word sentence: “In the US, 94% of media agency professionals agreed their brand clients should explore new digital media channels.” The 94% claim is bound to retained evidence `channel-exploration-and-retail-roi`, page 5. No regeneration candidate was needed. Provenance coverage passed. Summary abstention was not exercised because a valid source-backed summary was generated. The parser repeated ten `Ignoring wrong pointing object 9 0 (offset 0)` warnings seen in the prior replay; ingestion completed.

## Adjust attempt and stop sequence

The prior replay recorded one targeted repair followed by a `numbers` failure on unsupported `1016.8` in `expert_comment`. That record retained no candidate audits, strategy fingerprints, repair memory, or stop condition, so the exact historical reason for stopping after one repair cannot be proven retrospectively.

The first fresh run on `009bb1c6` showed that the repair loop did continue: `REGENERATE_ITEM/current_evidence` was rejected and rolled back, then `REBIND_EVIDENCE/alternative_evidence` was rejected and rolled back. Both have distinct retained fingerprints and candidate audits. It then planned `REMOVE_CLAIM/safe_removal`; its third distinct fingerprint was reconstructed deterministically from retained validation and rejection memory. Candidate assembly raised `soft_copy_claim_provenance_coverage_invalid` before saving an audit. The root cause was stale LinkedIn claim provenance after family-wide safe removal when a claim-level numeric error and family-level quality warning occurred together. A one-line provenance-clear fix and focused regression test were committed as `93bdc9e5`.

The second fresh run on that fix attempted `COPY_CANONICAL_SOURCE_VALUE/canonical_identity` and `ABSTAIN/safe_abstain`; both candidates were rolled back after grounding failures. The planner then returned `skip`: these were the two available materially distinct report-identity strategies. The three-attempt limit is a ceiling, so stopping after two here is expected. No equivalent rejected strategy was repeated, and the evidence did not justify changing loop control.

The final fresh run attempted `COPY_CANONICAL_SOURCE_VALUE/canonical_identity` once. Candidate validation passed, its audit retained 38 evidence-lineage entries including 23 soft-copy claims, and the candidate was promoted. The report ended at `awaiting_review` with validation and readiness passing. The canonical artifact contains no `1016.8`. Its retained numeric factual copy is supported by selected source evidence; the LinkedIn sentence about 5% session growth and session length falling from 10.04 to 9.6 minutes appears verbatim in `ecommerce-finding-keeping-users`, pages 27 and 29. Provenance coverage passed.

A controlled deterministic candidate check on the final frozen-source artifacts replaced that source-backed `10.04` with `1016.8` in a factual LinkedIn sentence. The candidate gate rejected it with `regeneration_claim_support`; the rolled-back audit retained the changed claim ID, selected evidence ID, pages 27 and 29, and the failure rule. This check is a component probe, not an additional live regeneration attempt. Candidate soft-copy lineage was added in `bb693e95`; its focused tests cover unsupported value, supported value, and wrong-year cases.

## Remaining checker discrepancy and next step

An independent `validate_retained_claims` call on the final Adjust artifact reports `not_publishable` (four unsupported factual and 11 unresolved results). Two numeric flags come from a direction check that calls an exact source sentence incompatible because it mentions both rising sessions and falling session length. The previous successful Adjust replay on `0144111c` had the same class of independent checker failure (five unsupported factual and 15 unresolved results). Production validation and readiness both pass; the independent checker is not a required publishing gate in this path. This is a pre-existing false positive to investigate separately before making that checker mandatory. No runtime change was made after both final canaries passed.

Both observed live failures are closed by these canaries. The next recommended step is the full 20-report regression cohort.

## Verification

- Initial focused suite: 159 passed.
- After the safe-removal correction: 213 relevant tests passed.
- After the audit-lineage correction: 213 relevant tests and 52 lineage/contract tests passed.
- Final focused command: `py -3.12 -m pytest -q tests/test_report_regeneration_generator.py tests/test_regeneration_candidate.py tests/test_soft_copy_claim_provenance.py tests/test_soft_copy_finalization.py` — 122 passed in 6.41 seconds.
- Both final canonical `artifacts.json` files, `validation.json`, readiness files, candidate audits, strategy fingerprints, provider events, and retained provenance were inspected. The deterministic `1016.8` probe was rejected with audit lineage. `git diff --check` was clean. No report was published.
