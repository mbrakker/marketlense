# Activate + Adjust verified-facts E2E retry

Run date: 2026-11-09
Producer SHA: `878a989c83614a719516d398480dcb7ab8dafb1c`
Run identity: `frozen-reliability-5vvjxo83`

This is the focused provider-backed retry for the exact frozen Activate and
Adjust members after the grounding-contract and candidate-identity correction.
The source PDFs were independently hash-checked in the authorized source
workspace and are not committed. The report projections under `export/reports/`
were produced by the repository exporter. Raw provider responses, caches,
private databases, usage ledgers and source PDF bytes are excluded.

## Outcome

| Measure | Result |
| --- | ---: |
| Reports admitted | 2 / 2 |
| Terminal outcomes | 1 failed / 1 awaiting review |
| Verified-facts admission | 20 / 20 facts admitted; 0 quarantined |
| Provider calls | 622 |
| Input / output tokens | 2,447,546 / 517,983 |
| Estimated cost | $0.521839 |
| Wall-clock | 4,949.126 s |
| Automatic repairs | 3 (Adjust) |
| Structured-output recovery calls | 2 (Adjust) |
| WordPress writes | 0 |

## Per-report outcome

| Report | Calls | Cost | Duration | Terminal outcome | HTML |
| --- | ---: | ---: | ---: | --- | --- |
| Activate | 442 | $0.242112 | 2,844.141 s | failed at `initial_selection` / `artifact_final_insight_coverage_invalid` | absent |
| Adjust | 180 | $0.279727 | 2,104.985 s | `awaiting_review`; validation/readiness pass | present |

Activate selected 3 of 10 eligible insights and failed the existing final
insight coverage gate before grounding. It produced no final HTML, so no live
grounding or editorial claim outcome is asserted for that report. This is the
same upstream provider/editorial-coverage class observed in the preceding
retained cohort, not a grounding-contract failure.

Adjust admitted all 10 verified facts and reached grounding both before and
after editorial regeneration. The bounded structured-output recovery completed
on its second attempt; three existing targeted repairs were recorded. It ended
with 0 unsupported and 0 unresolved retained factual claims, passed publication
readiness, and produced the final HTML projection.

## Adjust inspection

The final artifact contains five selected source-backed insights. The original
PDF identity is `source:8cb648b6bbd9dbae4ec1d915c38cf235` with SHA-256
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3` and 41
physical pages. The selected findings retain page/evidence bindings for pages
9/40, 18, 23, 26/29 and 35/37. The final HTML contains no `verified-fact:`,
`insight:`, `soft_copy:`, `evidence_id` or `claim_id` identifiers.

Independent review found the material numeric relationships in the HTML
consistent with the retained canonical facts: hyper-casual install/session
shares (29.1% / 15.3%), gaming partners per app (6 in 2024 / 5.3 in 2025),
e-commerce downloads (4.36B to 6.35B; >45%), and finance installs/sessions
(-4% / +21%). The finance retention item remains explicitly directional where
the source plot does not support an exact value. Commercial implications are
bounded and do not promote the reported efficiency gain to a general causal
effect.

## Evidence and verdict

* `cohort_result.json` is the authoritative mutually exclusive terminal ledger.
* `source_identity_manifest.json` records both expected source hashes and page counts.
* `execution_config_identity.json` records the isolated runner policy.
* `export/reports/` contains sanitized admission, stage, recovery, failure,
  readiness and usage projections.
* `inspection_notes.md` records the implementation attribution and limitations.

Verdict: **PARTIAL / NO-GO** for the two-report live acceptance. The corrected
grounding contract is exercised successfully by Adjust, but Activate remains
blocked before grounding by provider-dependent insight coverage. No claim of a
two-report pass or broad live selection improvement is made. Step 3 must not
start.
