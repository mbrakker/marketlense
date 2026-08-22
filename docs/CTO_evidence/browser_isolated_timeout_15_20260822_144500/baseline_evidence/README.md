# Browser timeout cohort final acquisition validation — 2026-08-22

## Verdict: REGRESSION

This is an acquisition-only replay of the exact frozen 15-report cohort whose
retained baseline records terminated with `browser_download_agent_timeout`.
No discovery, ingest, analysis, extraction, generation, publishing, or
WordPress work was run. Normal artifact verification was unchanged: only
`verified_usable_artifact == true` counts as success, and every failure remains
in the denominator.

## Evidence and comparable settings

- Frozen manifest: `baseline_manifest.json` — SHA-256 `13602C0BC0038DB4588193760158288314A4BFA943290A8C7C287CACCC914AE9`.
- Baseline source: `baseline_all_attempts.jsonl` — SHA-256 `C695010527AA4B67DE69D36632772E3104A67107F5C09EDC302714BCC7EC0D7B`; the exact 15 records are selected by `browser_download_agent_timeout`.
- Current result: `current_acquisition_attempts.jsonl` — SHA-256 `31AC9B6A382401B205E8444B0A5177491A9F0B4CA96BEF10AA08757729DB4CAC`.
- Current commit: `e5f02f0347fe7cda131994f8c4efedd8c545dc57`.
- Configuration: `configuration.yaml` — SHA-256 `9C77C4A99100C1AE501FB6379F39A31FD88CC846AE1704F508D82B67453105F9`; `gpt-5-mini`, zero retries, 240-second/24-step `browser_email_form` budget, disabled route/private-API playbook promotion, and no generic Browser Use context-reduction experiment.
- The configured identity profile was present locally; its values are not retained in this evidence pack.

## Baseline versus current

| Metric | Baseline | Current | Change |
| --- | ---: | ---: | ---: |
| Attempted reports | 15 | 15 | 0 |
| Verified acquisitions | 0 | 0 | 0 |
| Acquisition success rate | 0.00% | 0.00% | 0.00 pp |
| Browser Use Agent reports | 0 | 2 | +2 |
| Browser Use Agent calls | 0 | 14 | +14 |
| Input / cached / output tokens | 0 / 0 / 0 | 329,367 / 127,744 / 14,790 | +329,367 / +127,744 / +14,790 |
| Browser launches | 15 | 15 | 0 |
| Retries | 0 | 0 | 0 |
| Total acquisition cost | $0.000000 | $0.083183 | +$0.083183 |
| Cost per verified acquisition | not defined | not defined | not comparable |
| Acquisition duration | 5,168.898 s | 5,228.627 s | +59.729 s (+1.16%) |

## Per-report results and route

Every report used the `browser_email_form` route and ended
`browser_download_agent_timeout`; none passed artifact verification. Browser
Use Agent was used only for Criteo (3 calls) and Adjust (11 calls).

| Candidate | Publisher | Agent calls | Verified | Duration |
| --- | --- | ---: | --- | ---: |
| fac_fa1889b4c19f0f238659145e | Criteo | 3 | no | 344.808 s |
| fac_0ef70242a602b9ed7641c056 | Adjust | 11 | no | 345.184 s |
| fac_3e630244e5c22fe8fa787255 | GWI | 0 | no | 356.970 s |
| fac_4da62bac17be2e7185090695 | GWI | 0 | no | 352.449 s |
| fac_c0e4c925c1ed4ce6149711b8 | GWI | 0 | no | 382.871 s |
| fac_6f994caaf9a413e4038f18f1 | GWI | 0 | no | 349.607 s |
| fac_79d2b1c0c59436f8eacd7de4 | Jungle Scout | 0 | no | 343.750 s |
| fac_057817530e711866e5fea457 | Jungle Scout | 0 | no | 344.649 s |
| fac_74ff8c2c4382773a4f8d5f55 | Jungle Scout | 0 | no | 343.709 s |
| fac_80dc158f27be79e08f090b8c | Jungle Scout | 0 | no | 344.830 s |
| fac_c21286d0bf9647749fa4dae3 | Jungle Scout | 0 | no | 346.591 s |
| fac_6dae1d79b7340a3e0fd5055b | Jungle Scout | 0 | no | 343.503 s |
| fac_248c234f4d797e8eca595ff3 | Jungle Scout | 0 | no | 342.557 s |
| fac_0a2d080a0bcc92e54f50e171 | Jungle Scout | 0 | no | 342.951 s |
| fac_05b9e5cae6b0bbaf35801e27 | Jungle Scout | 0 | no | 344.208 s |

Verified-route resolution counts: HTTP/direct 0; private API 0; browser
preflight 0; deterministic standard form 0; deterministic learned playbook 0;
remembered blocker 0; Browser Use Agent 0.

Against the previously retained run of the same report-acquisition scope,
current main reduced none of Browser Use incidence, Agent calls, tokens,
browser launches, cost, or acquisition time. Incidence rose by 2 reports,
Agent calls by 14, input/cached/output tokens by 329,367/127,744/14,790, cost
by $0.083183, and duration by 59.729 seconds; launches were unchanged.
Verified acquisition success did not regress because it remained 0/15.
