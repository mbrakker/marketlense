# Inspection notes

* Exact producer: `878a989c83614a719516d398480dcb7ab8dafb1c`.
* Exact run: `frozen-reliability-5vvjxo83`.
* Source hashes and physical-page counts are recorded in
  `source_identity_manifest.json`; source PDF bytes are not retained here.
* The first two-report attempt at the same producer also failed Activate at
  final insight coverage. A focused retry of the previously failing reports
  was therefore run, as required by the repository validation policy.
* Activate stopped at `artifact_final_insight_coverage_invalid` during initial
  selection after selecting 3 of 10 eligible candidates. Grounding, final
  HTML, and downstream factual outcomes are unavailable for this report.
* Adjust completed the full verified-facts path. It admitted 10/10 facts,
  reached initial and post-regeneration grounding, used one bounded
  structured-output recovery sequence, and finished with validation/readiness
  pass. Three automatic targeted repairs were recorded by the run ledger.
* Adjust final HTML was inspected for internal identifiers and material numeric
  relationships against the original PDF. The rendered output contains no
  internal evidence identifiers. No unsupported or unresolved retained factual
  claim was promoted.
* The exact historical target IDs from the preceding failed run were not
  re-emitted by this retry's remapped artifact IDs; the current run therefore
  cannot claim a direct live re-evaluation of those two identifiers. The
  corresponding contract regressions remain covered by the focused tests, and
  the Adjust live grounding path passed without a forced semantic verdict.
* No publication, WordPress write, operator intervention, or application-level
  artifact reuse occurred.

## Verdict

The implementation-level grounding contract and candidate persistence fixes are
exercised by focused tests and by the successful Adjust path. The frozen
two-report acceptance remains **PARTIAL / NO-GO** because Activate failed at an
earlier provider-dependent selection-coverage gate. This evidence does not
justify calling the live cohort green or starting Step 3.
