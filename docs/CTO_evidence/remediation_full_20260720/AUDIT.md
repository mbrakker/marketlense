# Independent Audit — July 20 Remediation Evidence

> **Audit date:** 2026-07-21
> **Evidence bundle:** `remediation_full_20260720`
> **Audit posture:** read-only assessment of retained evidence, code, and tests
> **Overall verdict:** **not verified**

The isolated evidence pack is internally hash-consistent and its LLM total is
correct. It does not, however, contain enough run-owned funnel, WordPress
readback, log, or CI evidence to prove every July 20 claim as stated. This is
not a finding that runtime code is wrong; it is an evidence-completeness
finding. Do not describe the release as fully green or production-ready.

## Verdicts

| Area | Verdict | Evidence and limitation |
| --- | --- | --- |
| Run isolation | **verified with limitations** | The pack snapshots only `state/remediation_full_20260720` and `out/remediation_full_20260720`; no path outside those namespaces appears in its snapshot manifest. Run-owned canonical logs were not retained, and `signals.sqlite`, cost JSONL, and daily cost projections are not snapshot-inventoried by the collector. |
| Funnel reconciliation | **not verified** | Five cohort members can be identified from `published`, but there is no canonical per-entity run manifest. The isolated output contains seven semantic-validation packages and six manifests, so the cohort cannot be reconstructed solely from the pack without direct state inspection. |
| Publication | **verified with limitations** | Durable state maps five cohort file IDs to five distinct `ml_report` post IDs; three have publish idempotency outcomes and two are durable existing-post matches. The pack lacks retained authenticated WordPress response/readback records and a typed repeat-write counter. |
| Cost | **verified** | Isolated `llm_usage.sqlite`, `llm_cost_ledger.jsonl`, `llm_usage_metrics.csv`, `detailed_metrics.json`, and `executive_summary.json` reconcile exactly to 159 completed calls, 1,491,119 input tokens, 19,072 cached-input tokens, 392,222 output tokens, 1,883,341 total tokens, and $1.152941. |
| Visual quality | **partially proven** | 98 retained `.qa.json` sidecars prove chart/table crop decisions and rejection labels. No `crop_refine.json` is retained, and no retained aggregate proves semantic classification beyond chart/table or chart-to-evidence/insight linkage for the five cohort. |
| CI | **not verified** | The release record reports 122 focused tests and documentation/Ruff/diff checks, but no full-suite result is retained. `github_main_status.json` is `unavailable`, so the release is not fully green. |

## Scope isolation

The scoped bundle identifies `state/remediation_full_20260720` and
`out/remediation_full_20260720` in `evidence_run_manifest.json`; its SQLite
snapshots are `reports.sqlite`, `llm_usage.sqlite`, and `index.sqlite` below
that state directory. Artifact snapshot paths are relative to the isolated
output directory. No external report path, state database, or artifact path
was found in the pack.

The limitation is explicit: no run-owned canonical log exists at
`state/remediation_full_20260720/logs`. `log_content_leakage.json` is therefore
`unavailable`, not passed. The collector also does not inventory
`signals.sqlite` or the isolated JSONL/daily cost projections. Those omissions
do not demonstrate historical contamination, but they prevent a complete
all-input attestation.

## Reconciled publication cohort

The five cohort IDs reconstructed from the durable `published` table are:

| File ID | Sandbox post ID | Durable classification |
| --- | ---: | --- |
| `1VooWIbaZG6_RtRMcCgfU_reDZgrsit3L` | 961 | existing post matched |
| `1WSylL4_O1OrVtXA6SVTr7hjEZPbM8110` | 1757 | publish idempotency outcome retained |
| `1nrXx69QT4pqye59eEi2CS6WaoZEt9Cb5` | 1766 | publish idempotency outcome retained |
| `1iMmqocOUBzzgzM_Eqtu_NgPezptVlWi_` | 954 | existing post matched |
| `1YWo18NdOzGjRNmTG7C32gnn8dMgFJ1fg` | 1776 | publish idempotency outcome retained |

This supports three created/published outcomes and two existing matches, with
five unique post IDs. The three idempotency records retain the same post IDs on
repeat lookup; the two state matches retain `already_published` state. No
duplicate post ID is present. The evidence does **not** retain authenticated
readback response bodies or a first-class repeat-write counter, so those claims
remain limited rather than independently proven.

## Funnel and retained-output reconciliation

The cohort’s five rendered HTML packages each have a semantic pass,
public-editorial pass, and report-card manifest. The isolated output also
contains two additional validation-pass packages; one has no card manifest.
The durable queue includes earlier cancelled/dead-lettered work and one pending
analytics-projection job. These are explicit terminal or pending states, but
they are not joined by a canonical validation-run identifier.

Consequently, discovery → acquisition → ingest → analysis → render → validate
→ publish cannot be reconciled as a single five-row funnel. The evidence proves
individual retained stages, not the complete requested funnel for every
attempted entity.

## Cost comparison

| Source | Calls | Total tokens | Estimated cost (USD) | Difference from SQLite |
| --- | ---: | ---: | ---: | ---: |
| `llm_usage.sqlite` completed events | 159 | 1,883,341 | 1.152941 | 0 |
| `llm_cost_ledger.jsonl` | 159 rows | token total not retained | 1.152941 | 0 cost |
| `llm_usage_metrics.csv` / `detailed_metrics.json` | 159 | 1,883,341 | 1.152941 | 0 |
| `executive_summary.json` | 159 | 1,883,341 | 1.152941 | 0 |
| Release record | 159 | 1,883,341 | 1.152941 | 0 |

All 159 event rows have blank `workflow`, `stage`, and `report_id`; therefore
cost by workflow, stage, and report is **unavailable**, not zero.

## Visual evidence

The 98 QA sidecars contain 46 chart and 52 table candidates. They retain
accepted/rejected decisions and rejection labels, including 32
`chart_axis_or_label_clipped`, 10 edge-clipping variants, four suspicious-aspect
ratio cases, and one neighbour-contamination case. This proves crop QA executes
and rejects detectable geometry defects.

It does not prove semantic classification across photograph, infographic,
diagram, text-panel, mixed-layout, or uncertain classes; no retained
`crop_refine.json` exists. Nor does the pack retain an auditable aggregate from
candidate ID to evidence ID to final insight. Visual quality is therefore
**partially proven**.

## P0/P1 acceptance mapping

| Requirement | Code/test evidence | Live evidence | Assessment |
| --- | --- | --- | --- |
| Browser worker/doctor parity | `test_browser_runtime_contract.py` | No successful browser-required acquisition retained | implemented but not live-proven |
| Canonical path resolution | `test_config_runtime_path_resolution.py` | Isolated paths resolve, but no cross-service comparison retained | implemented but not live-proven |
| Model-policy completeness | policy/preflight tests | No retained discovery namespace preflight result | implemented but not live-proven |
| Canonical run manifest | collector manifest is bundle-level only | No per-entity stage manifest | partially implemented |
| Regeneration grounding preservation | lineage/regeneration tests | No retained targeted-regeneration lineage comparison | implemented but not live-proven |
| Pre-validation payload repair | pre-validation stage and checkpoint tests | Initial repair failure/recovery is retained only indirectly | partially implemented |
| Category-fit consistency | `test_context_category_fit_generator.py` | Category artifacts retained but no contradiction sample | implemented but not live-proven |
| Visual semantic classification | candidate contracts/QA code | Only chart/table labels retained | partially implemented |
| Crop quality | QA generator/tests | 98 retained QA decisions and rejection labels | implemented and live-proven |
| Chart-to-evidence linkage | artifact storage code | No cohort linkage aggregate retained | not assessable |
| WordPress publication | publish/idempotency tests | five durable post mappings; three publish outcomes/two matches | implemented and live-proven |
| Title normalization | public rendering tests | Passing packages, no retained field-level audit | implemented but not live-proven |
| Description quality | editorial-quality tests | passing editorial reports, no human review | implemented but not live-proven |
| Canonical/social URL | renderer/template tests | no retained URL contract readback | implemented but not live-proven |
| Public prose scaffold removal | editorial gate tests | passing gate, no sampled rendered-copy audit | implemented but not live-proven |
| Mojibake blocking | public-editorial gate tests | passing gate, no retained corruption canary | implemented but not live-proven |
| Structured-output resilience | normalization/render recovery tests | enum/manifest/checkpoint recovery exercised | implemented and live-proven |
| Stage-level LLM attribution | ledger schema and metrics | all 159 live rows have blank workflow/stage/report | partially implemented |
| Browser/crop/publication telemetry | telemetry services/tests | crop partial; browser partial; publication lacks repeat-write/readback evidence | partially implemented |

## Blockers and next validation

1. Persist one validation-run manifest with an entity/stage terminal record for
   every discovery, acquisition, repair, validation, publish, and repeat step.
2. Retain run-owned canonical logs or an access-controlled log snapshot index;
   do not use repository-wide logs as a substitute.
3. Persist typed WordPress create/match/readback/repeat-write outcomes and
   latencies per file ID.
4. Persist visual semantic class and candidate→evidence→insight linkage, plus
   crop refinement/cache outcomes.
5. Populate `workflow`, `stage`, and `report_id` in every LLM usage event.
6. Retain a full-suite and GitHub-check result tied to the release commit.

