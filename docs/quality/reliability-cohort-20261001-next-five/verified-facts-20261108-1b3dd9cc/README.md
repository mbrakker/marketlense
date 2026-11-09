# Activate + Adjust verified-facts E2E

Run date: 2026-11-08/09

Producer SHA: `1b3dd9cc1e8be6f7a69a09de2f262ad267dbffce`

This is the required isolated provider-backed two-report run for the exact
frozen cohort members Activate and Adjust. The original PDFs were hash-checked
in the authorized local source workspace and are not committed. Safe exported
state, artifact projections and terminal ledgers are under `export/`.

## Outcome

| Measure | Result |
| --- | ---: |
| Reports admitted | 2 / 2 |
| Terminal outcomes | 2 failed |
| Provider calls | 631 |
| Input tokens | 2,550,227 |
| Output tokens | 500,061 |
| Estimated cost | $0.537231 |
| Wall-clock | 5,029.563 s |
| Automatic repairs | 0 |
| WordPress writes | 0 |

Activate stopped at `editorial_plan_invalid` after the allowed two recovery
attempts for that artifact family. No verified-facts artifact or final HTML
was generated for Activate. Adjust admitted 10/10 verified facts with zero
quarantined facts and exact source SHA verification, but stopped at one
grounding result recorded as unresolved. The retained PDF directly supports
the claim on physical pages 27 and 29; the first-run false unresolved was
caused by an explicit model absence marker (`Not specified`) being counted as
a material unknown protected value.

No unsupported material claim was marked verified, no candidate was promoted,
and no publication/readiness approval or WordPress write occurred.

## Safe evidence

* `cohort_result.json` is the authoritative mutually exclusive terminal ledger.
* `source_identity_manifest.json` records source hashes and physical page counts.
* `execution_config_identity.json` records the exact runner policy without
  secrets or raw runtime configuration.
* `export/reports/` contains the repository safe projections from
  `export_reliability_run_evidence.py`; raw provider caches, databases, ledgers
  and PDF bytes are excluded.

The rerun after the contract correction is retained separately at
`verified-facts-20261109-6e61264a`. It stopped earlier at the provider/editorial
plan contract and therefore did not exercise the corrected grounding result.

Verdict: **PARTIAL / NO-GO** for Step 2 live acceptance. Do not start Step 3.
