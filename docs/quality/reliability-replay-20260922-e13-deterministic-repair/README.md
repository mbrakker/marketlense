# E13 deterministic and adaptive repair — completion replay — 2026-09-22

## Measurement identity

- Final implementation SHA: `dda61ad4` (ladder: `fc6712a3`, identity-exhaustion
  fix: `753cd746`, planned-strategy-key rejection: `dda61ad4`).
- Execution path: `scripts/quality/run_ias_first_attempt_canary.py` runner
  semantics through `scripts.quality.ias_live_canary_runner.run_first_attempt_canary`
  — each immutable frozen-cohort source is submitted through the normal
  production queue and supervisor in fresh isolated state. No run published to
  WordPress, requeued a report, reused an editorial artifact, raised a retry
  limit, added a validator waiver, or widened mutation scope.
- Sources: the checksum-verified Bigcommerce, Capgemini Research Institute,
  DHL eCommerce, SimilarWeb, and Contentstack members of
  `scripts/quality/frozen_reliability_cohort_20.json`.
- Per-report runner results and bounded repair-lineage projections are
  committed under [`results/`](results/), tagged with the implementation SHA
  that produced them. Local run state under `tmp/` is intentionally not
  committed, consistent with the repository reliability-evidence policy.

## What was implemented (E13 remaining scope)

1. **Deterministic repair actions (zero model calls).** Canonical report
   identity (`metadata.title`, `metadata.publisher`) is copied from the
   retained doc-map identity; an exact failed quote is restored verbatim from
   its retained quote candidate; protected insight metric fields
   (value/unit/timeframe/geography/cohort/denominator/observation status) are
   copied from the retained same-stable-ID candidate. Identity corrections
   travel with the candidate as bounded payload overrides (`title`/`publisher`
   only), are validated with it, and are promoted or dropped with it.
2. **metadata.title routing hole fixed.** A `metadata.title` /
   `metadata.publisher` grounding failure maps to the new `report_identity`
   target with `COPY_CANONICAL_SOURCE_VALUE`; keyword-guessing and broad
   family regeneration can no longer capture it.
3. **Typed compatibility scorer** (`src/generators/evidence_compatibility.py`)
   replaces both lexical-only fallbacks. It reuses
   `compare_protected_fact_texts` and ranks by entity/subject, metric value
   and unit, geography, cohort/denominator, timeframe, observed/forecast
   status, source-page proximity, and a strictly bounded lexical tiebreak.
   Conflicting or quarantined evidence can never win; without compatible
   relevant evidence the repair abstains. Fixtures prove same-number/
   wrong-geography, wrong-period, wrong-cohort, wrong-denominator, and
   forecast-vs-observed alternatives are rejected or ranked below the
   compatible evidence (`tests/test_evidence_compatibility.py`).
4. **Genuinely distinct strategy ladder per failure class:**
   deterministic canonical correction → rewrite from current valid evidence →
   rebind to the best compatible retained alternative → remove/abstain.
   Report identity has exactly one correction and one safe abstention. Every
   attempt restarts from the last promoted artifact, and the attempt's
   strategy fingerprint records the repair action, strategy, and evidence the
   generator actually selected; executed planned keys are rejected on
   rollback, and a re-detected equivalent fingerprint stops the loop with a
   typed log instead of burning further attempts.
5. **Candidate→final insight mutation eliminated (DHL/SimilarWeb shape).**
   `select_artifact_insights` deterministically restores the chosen
   candidate's protected factual fields when a same-stable-ID final insight
   drifted, in both initial generation and repair.

## Per-report replay outcomes

| Report | Implementation SHA | Initial failure (this replay) | Repair actions observed | Terminal result | Calls / tokens in / out / cost |
| --- | --- | --- | --- | --- | --- |
| Bigcommerce | `fc6712a3` | none — first-attempt validation pass | none required | `awaiting_review`; validation pass; readiness pass | 26 / 224,260 / 27,540 / USD 0.0779 |
| Capgemini Research Institute | `dda61ad4` | none — first-attempt validation pass (one earlier `dda61ad4` round and one `753cd746` round were blocked before analysis by the pre-existing `soft_copy_claim_provenance_coverage_invalid`/`bindings_incomplete` artifact-finalization defect, recorded below) | none required this round | `awaiting_review`; validation pass; readiness pass | 31 / 310,764 / 32,008 / USD 0.1006 |
| DHL eCommerce | `dda61ad4` | none — first-attempt validation pass | none required this round | `awaiting_review`; validation pass; readiness pass | 32 / 257,335 / 31,185 / USD 0.0886 |
| SimilarWeb | `753cd746` | none — first-attempt validation pass | none required | `awaiting_review`; validation pass; readiness pass | 31 / 208,300 / 33,684 / USD 0.0818 |
| Contentstack | `dda61ad4` | none — first-attempt validation pass | none required | `awaiting_review`; validation pass; readiness pass | 29 / 292,252 / 29,383 / USD 0.0934 |

Single-run model variance dominates these reports' historical grounding
failures: under the repaired pipeline all five retained terminal outcomes are
`awaiting_review` with zero operator interventions and no widened scope. The
deterministic repair paths themselves were demonstrated live in the
intermediate rounds retained below; the focused suites prove every
deterministic path and rejection rule deterministically.

## Live deterministic-repair demonstrations (intermediate rounds)

- **Canonical identity repair — Capgemini @ `fc6712a3`**
  ([`results/capgemini-fc6712a3-lineage.json`](results/capgemini-fc6712a3-lineage.json)).
  The loop planned `COPY_CANONICAL_SOURCE_VALUE` / `canonical_identity` on the
  `metadata.title` grounding failure and copied the canonical source title
  ("What matters to today's consumer 2026") with zero model calls, resolving 3
  validation failures. The candidate was rolled back fail-closed when the
  grounding model still rejected the canonical title, and this round exposed
  that the executed deterministic strategy was repeated across attempts 2–3
  under the generic ladder label — fixed by `753cd746` (identity ladder ends
  in `safe_abstain`; exhausted targets stop the plan) and `dda61ad4` (executed
  planned strategy keys are rejected after rollback).
- **Protected-metric repair — DHL @ `753cd746`**
  ([`results/dhl-753cd746-lineage.json`](results/dhl-753cd746-lineage.json)).
  The loop planned `CORRECT_PROTECTED_FACT` / `canonical_metric_copy` and
  copied the retained candidate metric fields with zero model calls, resolving
  one protected-fact failure before the candidate was rolled back on newly
  introduced grounding findings. The same round re-confirmed the planned-key
  rejection hole that `dda61ad4` closed; the `dda61ad4` rerun reached
  `awaiting_review` in one attempt.

## Pre-existing blocker recorded (out of E13 scope)

Several rounds (including two Capgemini rounds and one Bigcommerce round) were
blocked before analysis by the artifact-finalization defects
`soft_copy_claim_provenance_bindings_incomplete` /
`soft_copy_claim_provenance_coverage_invalid`, the same pre-existing cause as
the 19 failing tests in `tests/test_report_regeneration_generator.py` at
baseline `45456150` (verified by `git stash`). These are stochastic
artifact-finalization failures on the A21 soft-copy stream, not E13 repair
failures; they fail closed with typed codes, consume no repair attempts, and
are reported here for ownership rather than fixed in this change.

## Verification

- `python -m pytest tests/test_report_regeneration_generator.py
  tests/test_evidence_compatibility.py tests/test_artifact_normalization.py
  tests/test_regeneration_contracts.py tests/test_validation_repair_scorecard.py
  tests/test_claim_validation_generator.py tests/test_lineage_regeneration.py
  tests/test_public_editorial_quality_generator.py
  tests/test_public_editorial_identity.py
  tests/test_report_analysis_orchestrator_decomposition.py` — 179 passed, 19
  failed; the 19 are the pre-existing baseline failures verified identical
  under `git stash` at `45456150`.
- `python -m pytest tests/test_validation_queue_lineage.py` — 3 passed,
  including the A21 full-chain repair fixture (durable queue → targeted repair
  → render → readiness).
- Broader `-k "regeneration or soft_copy or validation_queue or
  analysis_orchestrator or claim_validation or artifact"` slice — 638 passed,
  same 19 pre-existing failures.
- `python scripts/ci/run_type_check.py` — full-repo mypy baseline matched
  (0 errors).
- `python scripts/ci/check_ruff_lint.py`, `check_formatting.py`,
  `check_architecture_imports.py`, `check_role_io_boundaries.py`,
  `check_forbidden_patching.py`, `check_bounded_logging.py`,
  `check_service_boundary_map.py` — all passed at the implementation SHA.
- No retry limit was raised (`validation_regeneration_max_attempts` stays 3),
  no validator was weakened, no mutation scope was widened, and no
  report-specific exception was added.


