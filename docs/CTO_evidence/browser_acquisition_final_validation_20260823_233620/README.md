# Final Browser Use acquisition validation — 2026-08-23

## Verdict: VERIFIED IMPROVEMENT

Current `main` replayed the exact immutable 30-report acquisition cohort from
the strongest retained comparable replay (23/30 verified). The run stopped
after acquisition: it did not run discovery, ingest, analysis, extraction,
generation, publishing, or WordPress.

Only normal `artifact_verification.verified_usable_artifact == true` counts as
an acquisition. All 30 frozen candidates remain in the denominator.

## Evidence and comparability

- Exact frozen cohort: [baseline manifest](baseline_evidence/baseline_manifest.json),
  SHA-256 `13602C0BC0038DB4588193760158288314A4BFA943290A8C7C287CACCC914AE9`.
- Original 3/30 retained baseline: [baseline 30-report replay](baseline_evidence/baseline_30_report_replay.json),
  SHA-256 `D3B4116B29EA04BF2CED61D9F1F56BB45F30FED505FC108ABE2FBBA9FBD811C3`.
- Strongest previous comparable run: [retained 23/30 evidence](baseline_evidence/previous_23_of_30/README.md).
  Its exact local diagnostic input had SHA-256 `9F196D4FE9480B3F34420D3556B3E16577DF120FECF2166AFA658AF63FC290B2`;
  the copied sanitized projection is retained with it.
- Current raw acquisition JSONL SHA-256: `EEDA4016F19971AC1A823BEB14A95FC44361AD5674DC3ED33B0C85EA8E29FD4F`.
- Candidate-set and raw-hash validation: [consistency](previous_vs_current_projection/consistency.json).
  It records 30/30 candidates, an exact set match, a matching current hash, and
  six current failures consistent with the aggregate metrics.
- Tested commit: `69f55aa4ed1afd167e2c8f27e2ee4d7488c65333`.
- Current replay profile: [configuration.yaml](configuration.yaml), SHA-256
  `16C1B8544F911881D53A32FF2BC77D5A60E75D97F83D0975F707D24DD356950C`.
  It resolved to `gpt-5-mini`, temperature `0.0`, zero retries, a 240-second /
  24-step `browser_email_form` cap, 600-second mailbox polling, and per-candidate
  720-second isolated supervision. Generic Browser Use context reduction was not
  enabled.

The identity profile was intentionally upserted by the acquisition workflow
mid-replay: it changed from SHA-256
`538A5110B26CD7564DB3594D736B80F92726070E53FFA5D46836D12953C7E93E` to
`4965598B2CD37CCB1A80008865D63A43DAD87CAB1F97301B56152BCAC519982D` after
candidate 15. The profile's form-field learning is part of the validated
deterministic-before-Agent architecture; both resulting task configuration
hashes (`0ae754…` for candidates 1–15 and `5b51ac…` for 16–30) are retained in
the sanitized per-attempt output. Model, retry policy, route budgets, and cohort
were unchanged.

## Previous 23/30 replay versus current

| Metric | Previous | Current | Change |
| --- | ---: | ---: | ---: |
| Attempted reports | 30 | 30 | 0 |
| Verified acquisitions | 23 | 24 | +1 |
| Acquisition success rate | 76.67% | 80.00% | +3.33 pp |
| Browser Use Agent reports | 3 | 2 | -1 (-33.33%) |
| Browser Use Agent calls | 17 | 8 | -9 (-52.94%) |
| Input tokens | 374,955 | 177,626 | -197,329 (-52.63%) |
| Cached input tokens | 134,528 | 62,976 | -71,552 (-53.19%) |
| Output tokens | 25,103 | 9,730 | -15,373 (-61.24%) |
| Browser launches | 10 | 9 | -1 (-10.00%) |
| Retries | 0 | 0 | 0 |
| Total acquisition cost | $0.113676 | $0.049697 | -$0.063979 (-56.28%) |
| Cost per verified acquisition | $0.004942 | $0.002071 | -$0.002871 (-58.10%) |
| Acquisition duration | 1,238.497 s | 983.643 s | -254.854 s (-20.58%) |

The machine-readable comparison is retained at
[before_after.json](previous_vs_current_projection/before_after.json), with
per-route metrics, failure Pareto, remaining failures, and sanitized
per-candidate results beside it.

## Verified resolution paths

| Resolution path | Verified reports |
| --- | ---: |
| HTTP/direct (19 deterministic on-site captures plus 2 report-page PDF probes) | 21 |
| Private API | 0 |
| Browser preflight | 2 |
| Deterministic standard form | 0 |
| Deterministic learned playbook | 0 |
| Remembered blocker | 0 |
| Browser Use Agent | 1 |

The lone verified Agent fallback was GWI `fac_3e630244e5c22fe8fa787255`, which
resolved a publisher PDF click in three calls. All three current GWI email-form
results failed normal artifact verification and are not credited. The generic
Barclays research hub was rejected before acquisition with zero browser or model
work; it is retained as a failure and is not misclassified as a remembered
blocker resolution.

## Architecture evidence

- Task-scoped resource envelopes are present for 29 externally evaluated
  acquisition attempts; the generic Barclays hub was rejected at admission with
  zero external work and retains an explicit terminal record instead.
- Browser preflight resolved two reports with zero Agent calls. Direct/on-site
  and report-page deterministic routes resolved 21 reports before Agent fallback.
- The three standard-form attempts ran without Agent calls, but ended
  `email_required`; they remain failures. No private-API, learned-playbook, or
  remembered-blocker resolution occurred in this cohort, so the replay makes no
  unsupported hit-rate claim for those paths.
- Agent fallback was bounded to two reports and eight calls. The unresolved Brand
  Finance landing-page target terminated as a normal bounded Agent timeout; no
  generic context-reduction experiment was introduced.

Focused current-main deterministic checks passed for the architecture paths not
resolved by this live cohort: task resource telemetry and remembered-blocker
suppression, private-API-before-Agent routing, browser preflight, learned route
playbooks, deterministic standard-form helpers, and no-progress termination.
The two focused commands completed with 22 and 68 passing tests respectively.

See [per_report_results.md](per_report_results.md) for every candidate's route
and verification result. The exact report/URL list is retained in the copied
[frozen manifest](baseline_evidence/baseline_manifest.json).

Against the previously retained run of the same report-acquisition scope,
current main reduced Browser Use incidence by 1 report, Agent calls by 9,
input/cached/output tokens by 197,329/71,552/15,373, browser launches by 1,
cost by $0.063979, and acquisition time by 254.854 seconds. Verified acquisition
success did not regress: it improved from 23/30 to 24/30.
