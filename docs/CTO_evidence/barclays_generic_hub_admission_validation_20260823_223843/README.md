# Barclays generic-hub admission validation — 2026-08-23

## Scope and verdict

**VERIFIED IMPROVEMENT** for admission efficiency. This is a one-candidate,
acquisition-only replay of the frozen historical target
`fac_9d4d17626b51fdefb56842cb`:
`https://www.ib.barclays/research.html`. No discovery, report substitution,
ingest, analysis, extraction, generation, publishing, or WordPress work ran.

The candidate remains an acquisition failure because it is a generic,
title-less research/listing page rather than a report-detail source. The
improvement is that the deterministic admission gate now rejects it before
route-memory lookup, browser preflight, or Browser Use; it does not weaken
artifact verification or count the candidate as a successful acquisition.

## Retained inputs and provenance

- Frozen source manifest: [frozen_failed_acquisition_manifest.json](../browser_acquisition_final_validation_20260820_e60b1516/frozen_failed_acquisition_manifest.json), SHA-256 `13602C0BC0038DB4588193760158288314A4BFA943290A8C7C287CACCC914AE9`.
- Exact baseline candidate record: [initial 30-cohort result](../browser_acquisition_initial30_final_20260823_175952/per_report_results.md); raw replay was `out/browser_acquisition_initial30_final_20260823_173237/current_replay/diagnostic_replay.json`, SHA-256 `9F196D4FE9480B3F34420D3556B3E16577DF120FECF2166AFA658AF63FC290B2`.
- Validation `HEAD`: `8ada9894ba32b54d1e93c468afe54c29aed8a5c9`; the tested uncommitted implementation diff was `5b2dcc9d5867194ca3496b22d79107425f38982e`.
- Configuration: [configuration.yaml](configuration.yaml), isolated paths, the current resolved identity profile, `gpt-5-mini`, zero retries, and the retained 240-second/24-step browser-email budget. No generic Browser Use context-reduction experiment was enabled.
- Current replay: [diagnostic_replay.json](current_replay/diagnostic_replay.json), SHA-256 `6D2FBC7BD57ADF537C7F9098C967375896217E2C3BCC206F18194AB6B3035B6A`.

## Exact comparison

| Metric | Retained 30-cohort attempt | Current replay | Change |
| --- | ---: | ---: | ---: |
| Attempted candidates | 1 | 1 | 0 |
| Verified acquisitions | 0 | 0 | 0 |
| Route/result | `browser_listing_hub` / Agent timeout | admission rejection: `candidate_rejected_mixed_content_hub` | no arbitrary report selected |
| Browser Use Agent calls | 8 | 0 | -8 |
| Browser launches | 1 | 0 | -1 |
| Input tokens | 176,160 | 0 | -176,160 |
| Cached input tokens | 71,680 | 0 | -71,680 |
| Output tokens | 5,559 | 0 | -5,559 |
| Retries | 0 | 0 | 0 |
| Acquisition cost | $0.039031 | $0.000000 | -$0.039031 |
| Candidate acquisition duration | 228.170 s | 0.001 s | -228.169 s |
| Normal artifact verification | failed | failed (no artifact) | unchanged |

The current record has no resource-attempt row because the request stopped
before an acquisition resource was created. That is evidence of zero browser
and model use, not missing telemetry. The process-isolated supervisor completed
normally; no external page was opened.

## Behavioral boundary

The readiness classifier now removes a terminal file extension before testing a
collection-root segment. Thus `research.html` is treated equivalently to
`research`, while a specific public report-detail URL remains eligible for the
normal deterministic direct/PDF/rendering paths. The regression test uses the
same URL fallback title produced by the retained replay and asserts rejection
before even the route-memory dependency can run.

Focused checks:

```text
pytest -q tests/test_report_download_orchestrator.py -k "frozen_barclays_research_hub_before_acquisition or rejects_mixed_content_hub_candidate"
# 2 passed

python scripts/quality/acquisition_failure_remediation.py replay ... --candidate-id fac_9d4d17626b51fdefb56842cb
# 1 candidate, deterministic admission rejection, no resource attempts
```
