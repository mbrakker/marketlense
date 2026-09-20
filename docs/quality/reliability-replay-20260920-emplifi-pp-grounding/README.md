# Targeted real-report replay — Emplifi `validation_failed` root cause and fix verification — 2026-09-20

## Measurement identity

- Sources: the immutable, checksum-validated Emplifi member plus the
  DoubleVerify passing control from
  `scripts/quality/frozen_reliability_cohort_20.json`.
- Canonical path: `scripts.quality.ias_live_canary_runner.run_first_attempt_canary`.
  It creates fresh isolated state, submits through the production queue, and
  drains the normal supervisor. Neither run published to WordPress.
- Baseline revision: `799c93c9872c59e94dd13c3dd13d879f89ce1985` (clean tree).
- Fix under test: `2b4e9497` ("fix: ground hyphenated percentage-point units
  and surface validation_failed inner findings"), one commit, clean tree.
- Scope: two fresh real-report measurements, one per revision; no member
  substitution, manual requeue, publisher-specific handling, validation
  waiver, retry-limit change, or validation-gate weakening. Failed members
  were retained, never rerun within a round.

## Reproduced baseline failure

The baseline Emplifi run terminal-failed with the generic
`validation_failed`, no exported `failure_diagnostic`, and a final
`validation.json` whose error-severity findings were `numbers` gate flags:
`24.0` (expert_comment), `56.0` and `1000.0` (linkedin_post) "not present in
report or evidence". The retained evidence contradicts the 24 flag: finding
`finding-002` states "research time increases by 24 percentage points" and the
metric spine retains value "24 percentage points". Deterministic replay of
`validate_new_numbers` over the run's retained artifacts, evidence packs, and
cached source text reproduced the blocking `24.0` error with those inputs.

The committed final-round evidence from
`docs/quality/reliability-replay-20260920-linkedin-provenance-fix/`
(`final-full-12-mixed-sha`) shows the same report failing the same generic
code in that round via a different inner finding (`claim_support`
`weak_evidence_strong_claim` on `summary.claim_evidence_map[0]`, evidence
`strategy`), also without any exported diagnostic. Both shares of the
causal chain are deterministic and fixed generically in `2b4e9497`:

1. Quantity parsing: `_MAIN_RE` had no unit word boundary, so `percent`
   prefix-matched inside `percentage-point`; the hyphenated spelling had no
   pp/points mapping. The same source fact now canonicalizes identically
   across singular, plural, and hyphenated spellings, so retained evidence
   grounds the copy and the numbers gate no longer blocks it.
   `claim_support`'s strong-claim heuristic no longer treats an exclusivity
   word scoped by a contrast construction ("rather than treated only as
   messaging") as an overstatement, so a summary claim that faithfully
   paraphrases an explicit recommendation is not rejected.
2. Failure diagnostics: the runner reader stops discarding the retained inner
   finding when the newest failing stage record is a terminal checkpoint
   without a validation-issues document. A generic `validation_failed` now
   exports the identifier-only finding (validator rule, affected
   section/family, claim or entity ID, bounded repair attempt, redacted
   context). No source text, prompt, provider response, or message prose is
   retained; verified against the preserved failed-run state.

## Outcomes

| Member | Baseline `799c93c9` | Fix `2b4e9497` |
| --- | --- | --- |
| Emplifi | FAIL `validation_failed`, no diagnostic | [`awaiting_review`](result.json) |
| DoubleVerify (control) | — | [`awaiting_review`](control-result.json) |

The fixed Emplifi run reached `awaiting_review` with validation and
publication-readiness pass, one workflow attempt, no automatic repair, and no
operator intervention. The DoubleVerify control confirms no regression on a
previously passing member. Both result files intentionally retain identifiers,
state transitions, bounded usage, and outcome fields only.

## Focused verification

- `python -m pytest tests/test_quantity_utils.py tests/test_validation_generator.py tests/test_validation_number_temporal_context.py tests/test_frozen_reliability_cohort_runner.py tests/test_export_reliability_run_evidence.py` — 85 passed.
- `python -m pytest tests/test_soft_copy_claim_provenance.py tests/test_public_editorial_quality_generator.py` — 73 passed.
- Deterministic offline replay of the numbers gate over the preserved
  baseline-run inputs: 1 blocking error before the fix, 0 after.
