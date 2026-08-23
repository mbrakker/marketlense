# Initial 30-report Browser Use acquisition validation — 2026-08-23

## Verdict: VERIFIED IMPROVEMENT

Current `main` replayed the exact immutable 30-report cohort from the retained
initial acquisition validation. It ran acquisition only: no discovery, ingest,
analysis, extraction, generation, publishing, or WordPress work. Every report
remained in the denominator and only normal
`artifact_verification.verified_usable_artifact == true` counted as a success.

## Retained comparability evidence

- Frozen 30-report manifest: `../browser_rendered_pdf_validation_20260821_080508/baseline_manifest.json`, SHA-256 `13602C0BC0038DB4588193760158288314A4BFA943290A8C7C287CACCC914AE9`; embedded manifest hash `1c41324dbb009a223c8add82b7dc949e7fd59895c0137f72a599794a6882425e`.
- Exact baseline records: `../browser_rendered_pdf_validation_20260821_080508/baseline_30_report_replay.json`, SHA-256 `D3B4116B29EA04BF2CED61D9F1F56BB45F30FED505FC108ABE2FBBA9FBD811C3`.
- Current raw records (local source used to derive the committed projection): `../../../out/browser_acquisition_initial30_final_20260823_173237/current_replay/acquisition_attempts.jsonl`, SHA-256 `F471E3519146BC151042770ABEF5AD76BE449E68B37B0A2788BEFA473E7F357D`.
- Committed, sanitized canonical projection: [acquisition_evidence_projection.json](sanitized_projection/acquisition_evidence_projection.json), SHA-256 `8757C559483FB12A352A41D79EB6DD70E07902FC4973CC43A6DC9AC8887EFEFF`. It retains scalar per-candidate resource evidence and reproducible aggregate views without URLs, browser paths, route prose, identity values, or raw model/browser data.
- Current commit: `b463da172bf11a05d453ac64c0e1616a8f2e52b6`.
- Current configuration: `../../../src/config/app.browser_acquisition_initial30_final_20260823_173237.yaml`, SHA-256 `03D9976B8254352EAB2DA1A86FEFBDCBEB7D0036F24B8A8B3F15656BA84AB794`.
- Current replay configuration hash (including the resolved identity profile): `d854cc01bf4dbdbea7e3e7ca3ccffe85f64457cd8361ae7f8896d56043739726`.

The profile retained `gpt-5-mini`, zero retries, the 240-second/24-step
`browser_email_form` budget, write-mode learned route/private-API playbook
promotion, a 600-second mailbox limit, and no generic Browser Use
context-reduction experiment. Each candidate ran in a disposable process with
a 720-second supervisor envelope (the configured service limit plus cleanup
grace).

## Baseline versus current

| Metric | Baseline | Current | Change |
| --- | ---: | ---: | ---: |
| Attempted reports | 30 | 30 | 0 |
| Verified acquisitions | 3 | 23 | +20 |
| Acquisition success rate | 10.00% | 76.67% | +66.67 pp |
| Browser Use Agent reports | 5 | 3 | -2 (-40.00%) |
| Browser Use Agent calls | 23 | 17 | -6 (-26.09%) |
| Input tokens | 455,391 | 374,955 | -80,436 (-17.66%) |
| Cached input tokens | 173,440 | 134,528 | -38,912 (-22.44%) |
| Output tokens | 26,039 | 25,103 | -936 (-3.59%) |
| Browser launches | 21 | 10 | -11 (-52.38%) |
| Retries | 0 | 0 | 0 |
| Total acquisition cost | $0.126904 | $0.113676 | -$0.013228 (-10.42%) |
| Cost per verified acquisition | $0.042301 | $0.004942 | -$0.037359 (-88.32%) |
| Total acquisition duration | 5,970.490 s | 1,238.497 s | -4,731.993 s (-79.26%) |

## Verified route resolutions

| Resolution path | Count |
| --- | ---: |
| HTTP/direct | 20 |
| Private API | 0 |
| Browser preflight | 2 |
| Deterministic standard form | 0 |
| Deterministic learned playbook | 0 |
| Remembered blocker | 0 |
| Browser Use Agent | 1 |

The 20 HTTP/direct successes comprise 18 verified direct browser captures and
two report-page PDF link probes. Browser preflight resolved the Criteo and
Adjust PDF probes. Browser Use Agent resolved one GWI PDF click (five calls).
The evidence contains no verified acquisition attributed to private API,
deterministic form completion, learned playbooks, or remembered blockers; those
paths were not credited as successes. Task-scoped resource telemetry is present
for every record. The two remaining Agent failures were retained as bounded
`browser_download_agent_timeout` results rather than upgraded to success.

See [per_report_results.md](per_report_results.md) for the exact cohort and
current route/result for every report.

## Committed raw-evidence projection

The final 30-cohort evidence now retains the sanitized, canonical projection in
GitHub rather than requiring the local `out/` JSONL for failure diagnosis:

- [per-candidate attempts](sanitized_projection/sanitized_attempts.json)
- [failure Pareto](sanitized_projection/failure_pareto.json)
- [per-route metrics](sanitized_projection/route_metrics.json)
- [baseline-versus-current metrics](sanitized_projection/before_after.json)
- [seven remaining failures](sanitized_projection/remaining_failures.json)
- [cohort and SHA-256 consistency checks](sanitized_projection/consistency.json)

The projection was generated without an acquisition rerun from the two retained
hashed inputs. Regenerate it with:

```text
python scripts/quality/acquisition_evidence_projection.py \
  --current-jsonl out/browser_acquisition_initial30_final_20260823_173237/current_replay/acquisition_attempts.jsonl \
  --baseline-json docs/CTO_evidence/browser_rendered_pdf_validation_20260821_080508/baseline_30_report_replay.json \
  --output-dir docs/CTO_evidence/browser_acquisition_initial30_final_20260823_175952/sanitized_projection \
  --expected-current-sha256 F471E3519146BC151042770ABEF5AD76BE449E68B37B0A2788BEFA473E7F357D
```

Against the previously retained run of the same report-acquisition scope,
current main reduced Browser Use incidence by 2 reports, Agent calls by 6,
input/cached/output tokens by 80,436/38,912/936, browser launches by 11, cost
by $0.013228, and acquisition time by 4,731.993 seconds. Verified acquisition
success did not regress: it improved from 3/30 to 23/30.
