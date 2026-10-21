# Verified Claims ten-report acceptance package

## Executive verdict

**PARTIAL.** The exact frozen ten-report source identities were processed from retained source artifacts through live Step2 shadow verification, and a fresh GPT-6 Luna High claim-level editorial review was run. The evidence does not support closing Step1/E18 repeatability, P6 or Step3.

## Run identity

- Step1 isolated cohort result: `tmp/ten-full/frozen-reliability-9kx4zae9/cohort_result.json` (producer commit `38a71ec705755f279dac2cba6a73adb1090e3f17`).
- Step2 shadow result: `tmp/step2-ten-live/result.json`; model `gpt-6-luna`, reasoning `high`.
- Independent review: `tmp/ten-editorial-review/manifest.json`; model `gpt-6-luna`, reasoning `high`.
- Source manifest: `scripts/quality/frozen_reliability_cohort_10.json`; all ten expected SHA-256 values matched.

## Measured outcomes

- Step1: 10/10 terminal cohort records; 59 selected candidates.
- Step2: 120 provider calls, 1879961 total tokens, $0.212434, 935.903 seconds; outcomes {"failed_verification": 1, "skipped": 0, "unresolved": 0, "verified_after_retry": 0, "verified_first_pass": 58, "verified_total": 58}.
- Independent review: 58 calls, 946469 total tokens, $0.115553, 605.152 seconds; decisions {"approved": 57, "revision_required": 1, "unresolved": 1}.
- Side effects: shadow-only; no canonical mutation and no publication write.

## Package contents

- [Cohort manifest](cohort-manifest.json) — ten frozen identities, expected/actual hashes, page counts and resolved source paths.
- [Step1 selection ledger](step1-selection-ledger.json) — candidate pools, selected IDs, final wording, evidence fidelity status, metrics, pages and spans.
- [Step1 root-cause analysis](step1-root-cause-analysis.md) — diagnosis and justified production changes.
- [Step2 verification ledger](step2-verification-ledger.json) — original/final claims, correction and verification attempts, outcomes and bindings.
- [Editorial scorecard](editorial-scorecard.md) and [structured scorecard](editorial-scorecard.json) — fresh claim-level review.
- [Repeatability analysis](repeatability-analysis.md) — independent-run limits and identity comparisons.
- [Acceptance summary](acceptance-summary.md) — mutually exclusive outcomes and remaining gates.

The package intentionally excludes PDFs, caches, raw provider responses and large logs. Retained run paths, artifact hashes, prompt/model metadata and usage ledgers remain available in the ignored `tmp/` run roots for reproducibility in this workspace.
