# Browser Use acquisition final validation — 2026-08-20

## Verdict: NOT VERIFIED

This acquisition-only replay did not complete the exact retained 30-report
cohort. It must not be used to claim an improvement, no change, or a numeric
regression. The process was deliberately interrupted only after its second
report remained non-terminal well beyond the configured 180-second model
timeout, with no completed task-scoped resource row. Letting a hung route run
indefinitely would not validate the required no-progress termination behavior.

No discovery, ingest, analysis, extraction, generation, publishing, or
WordPress stage was invoked. No report was replaced or substituted.

## Immutable cohort and baseline retained

- Cohort: all 30 members of `frozen_failed_acquisition_manifest.json`.
- Manifest content hash: `1c41324dbb009a223c8add82b7dc949e7fd59895c0137f72a599794a6882425e`.
- Manifest file SHA-256: `13602c0bc0038db4588193760158288314a4bfa943290a8c7c287caccc914ae9`.
- Exact complete baseline source: `baseline/acquisition_attempts.jsonl` and
  `baseline/diagnostic_replay.json`, copied unchanged from
  `docs/CTO_evidence/acquisition_failure_remediation_20260814_5d4c027f/diagnostic_after_credential_fix/`.
- Baseline attempts file SHA-256: `201b5672b705677cfc15a654b6f4634306c3437c441b4a489f06217a0bed27f4`.
- The manifest itself retains the exact report IDs, publishers, and canonical
  URLs. Baseline and current raw per-report records are retained verbatim.

## Current run configuration

- Commit: `e60b15166f6617f95a4cf61281a92afbaa380e82` on `main`.
- Model: `gpt-5-mini` (same model family as the baseline).
- Isolated current configuration: `current_acquisition_config.yaml`, SHA-256
  `094f1205d6aedaf239db6afcedb44b936b36060ea864a553904ab812d3c26602`.
- Identity configuration was reused without copying credentials; SHA-256
  `64a042cee68ca9cb023bdc96a9c64423d5116cbcbe48b7096202d491d9316ead`.
- Comparable bounds retained: zero retries, 240 seconds / 24 steps for the
  email-form route, and 600 seconds of mailbox polling.
- Current deterministic route and private-API promotion modes are both `write`.
  The older baseline had both disabled, so the current architecture—not the
  rejected experiment—is exercised.
- `browser_use_context_reduction_rejection.md` is copied from the current
  quality decision. No generic Browser Use context/history/state reduction
  option is present in this profile or code-path search.

## Run result and stopping condition

| Cohort position | Report | Result | Normal verification | Route / telemetry |
| --- | --- | --- | --- | --- |
| 1 | BlueCore — `fac_eda48226bd40dd9fece75890` | completed in 52.637 s | failed: retained complete on-site HTML is not a native PDF acquisition | `browser_onsite_report`; 0 Agent calls, 0 browser launches, $0.00 |
| 2 | Brand Finance — `fac_0294383b7bf86f9bcc6fbf06` | started, then externally interrupted after it remained non-terminal beyond the 180 s model timeout | unavailable; no terminal result or resource row was persisted | browser preflight/browser route began; final telemetry unavailable |
| 3–30 | remaining immutable cohort members | not started because report 2 never reached a terminal state | unavailable | unavailable |

The first result is retained at `current_acquisition_attempts.partial.jsonl`.
The second does not have a durable per-report result because the process was
stuck inside the acquisition boundary before its `finally`/ledger completion;
the absence of its resource row is itself the no-progress failure evidence.

## Comparison (directly supported metrics only)

| Metric | Complete baseline | Current replay | Comparison status |
| --- | ---: | ---: | --- |
| Cohort reports | 30 | 30 frozen; 2 started; 1 terminal | not comparable |
| Verified acquisitions | 5 | 0 among 1 terminal result | not comparable |
| Acquisition success rate | 16.67% (5/30) | unavailable | not comparable |
| Reports using Browser Use Agent | 29 | unavailable | not comparable |
| Browser Use Agent calls | 1,239 | unavailable | not comparable |
| Input tokens | 24,698,470 | unavailable | not comparable |
| Cached input tokens | 9,338,240 | unavailable | not comparable |
| Output tokens | 1,192,806 | unavailable | not comparable |
| Browser launches | 212 | unavailable | not comparable |
| Retries | 0 | unavailable | not comparable |
| Total acquisition cost | $6.459150 | unavailable | not comparable |
| Cost per verified acquisition | $1.291830 | unavailable | not comparable |
| Duration | 3,081.923 s | unavailable for the incomplete cohort | not comparable |

The current first terminal row accounts for zero Agent calls, tokens, browser
launches, retries, and cost. Those are *not* run totals because the interrupted
second report may have consumed unfinalized resources; the bundle intentionally
does not report them as a zero-cost benchmark.

## Route-resolution categories

The retained baseline resource schema records `route_family` and Agent-call
counts, not the requested mutually-exclusive final categories (HTTP/direct,
private API, browser preflight, deterministic standard form, deterministic
learned playbook, remembered blocker, Browser Use Agent). The only category
directly supported across the complete baseline is Browser Use Agent: 29 of 30
reports incurred one or more Agent calls. The incomplete current replay does
not support a cohort-level count for any category. The one completed current
report used `browser_onsite_report` with zero Agent calls, but normal artifact
verification rejected its HTML capture as a verified PDF acquisition.

## Architecture assessment

- Task-scoped resource telemetry: the completed BlueCore task produced its own
  zero-Agent resource row; the stalled Brand Finance task did not finalize one.
- Private API before browser, browser-preflight reuse, deterministic standard
  forms, learned playbooks, and remembered-blocker suppression cannot be
  assessed across the incomplete cohort.
- Browser Use Agent fallback was not used for the completed BlueCore row; the
  stalled second report entered the browser route but did not finalize Agent
  telemetry.
- No-progress termination did not produce a terminal result for report 2 within
  the configured model timeout. This blocks validation of the required current
  architecture.

## Focused deterministic checks

The following current-main checks passed after the interrupted live replay:

```
python -m pytest tests/test_acquisition_resource_telemetry.py tests/test_browser_acquisition_cache_and_autofill.py tests/test_browser_report_download_service/test_post_action_verification.py tests/test_browser_report_download_service/test_browser_preflight.py tests/test_browser_report_download_service/test_private_api_playbook.py tests/test_browser_route_playbooks.py -q
# 75 passed in 17.92s
```

These tests cover the individual telemetry, preflight, deterministic-playbook,
private-API, standard-form, and no-progress components. They do not override
the failed live-cohort completion requirement.

Against the previously retained run of the same report-acquisition scope, how
much did current main reduce Browser Use incidence, Agent calls, tokens,
browser launches, cost, and acquisition time, and did verified acquisition
success regress? **Not verified:** current main did not complete the same
cohort, so every requested reduction and success-rate comparison is unavailable
rather than estimated.
