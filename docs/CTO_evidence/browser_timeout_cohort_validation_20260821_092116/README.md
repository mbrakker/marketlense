# Browser timeout cohort validation — 2026-08-21

## Verdict: REGRESSION

This is an acquisition-only replay of the exact 15 records that terminated as
`browser_download_agent_timeout` in the retained 2026-08-20 replay. No
discovery, ingest, analysis, extraction, generation, publishing, or WordPress
stage was run. Normal artifact verification was unchanged: only
`artifact_verification.verified_usable_artifact == true` counts as a verified
acquisition, and all failed reports remain in the denominator.

The one-event-loop handoff let Browser Use perform Agent work for three reports,
which proves that the former pre-Agent session-loop failure was removed. It did
not improve acquisition: each Agent task remained pending during Browser Use
shutdown until the existing worker deadline produced the same typed timeout.

## Retained baseline and comparable current run

- Exact frozen source manifest: `../acquisition_failure_remediation_20260814_5d4c027f/failed_acquisition_manifest.json`
  (SHA-256 `13602C0BC0038DB4588193760158288314A4BFA943290A8C7C287CACCC914AE9`).
- Exact baseline records: `../browser_acquisition_final_validation_rerun_20260820_e60b1516/current_replay/acquisition_attempts.jsonl`
  (SHA-256 `C695010527AA4B67DE69D36632772E3104A67107F5C09EDC302714BCC7EC0D7B`).
- Current commit: `5ed5ce2df432503aa8a5a992ee5b0c671e9db2ca`.
- Current run: `3bba1f75-ae41-471c-ac53-b4e26edb1f69`.
- Current acquisition records: `current_replay/acquisition_attempts.jsonl`
  (SHA-256 `B16694BC2A0C6C31FEB0473D803DA04F35CE52E65679C38AE5A42CC4C7D02C47`).
- Profile: `src/config/app.browser_acquisition_timeout_validation_20260821_092116.yaml`
  (SHA-256 `C1D845C1808BE148801DFA12446D9C6BCCCE1F35A2A599772180C15446E3A33A`);
  model `gpt-5-mini`, zero retries, 240-second/24-step `browser_email_form`
  budget, and no generic Browser Use context-reduction experiment.

`baseline_evidence.json` retains immutable baseline paths and hashes;
`comparison.json` contains the machine-readable comparison; and
`per_report_results.md` lists every replayed report.

## Baseline versus current

| Metric | Baseline | Current | Change |
| --- | ---: | ---: | ---: |
| Attempted reports | 15 | 15 | 0 |
| Verified acquisitions | 0 | 0 | 0 |
| Acquisition success rate | 0.00% | 0.00% | 0.00 pp |
| Browser Use Agent reports | 0 | 3 | +3 |
| Browser Use Agent calls | 0 | 14 | +14 |
| Input tokens | 0 | 320,956 | +320,956 |
| Cached input tokens | 0 | 115,840 | +115,840 |
| Output tokens | 0 | 14,949 | +14,949 |
| Browser launches | 15 | 15 | 0 |
| Retries | 0 | 0 | 0 |
| Total acquisition cost | $0.000000 | $0.084074 | +$0.084074 |
| Cost per verified acquisition | not defined | not defined | not comparable |
| Acquisition duration | 5,168.898 s | 5,293.932 s | +125.034 s (+2.42%) |

No report passed normal artifact verification. Therefore all verified route
resolution counts are zero: HTTP/direct, private API, browser preflight,
deterministic standard form, deterministic learned playbook, remembered blocker,
and Browser Use Agent.

## Interpretation

All 15 current records end with `browser_download_agent_timeout` on the
`browser_email_form` route. The three Agent-bearing records are Criteo (3
calls), Adjust (6), and Jungle Scout Cosmetics (5). They show action progress
before Browser Use shutdown; the retained terminal records show the stopped
Agent task did not return before the worker deadline. This is a post-Agent
cleanup timeout, not the former no-Agent timeout, but it is still an
acquisition failure and is not counted as an improvement.

Against the previously retained run of the same 15-report acquisition scope,
current main reduced none of Browser Use incidence, Agent calls, tokens, browser
launches, cost, or acquisition time. Incidence increased from 0 to 3 reports,
Agent calls from 0 to 14, input/cached/output tokens from 0 to
320,956/115,840/14,949, cost by $0.084074, and time by 125.034 seconds; browser
launches were unchanged. Verified acquisition success did not regress because
it was 0/15 in both runs. The verdict is **REGRESSION** because the requested
timeout/acquisition improvement was not demonstrated.
