# Frozen five-report verified-facts E2E acceptance

Run date: 2026-11-05
Producer SHA: `d02897a91e2f1773c611ade56c41f3af41ec2661`
Run identity: `frozen-reliability-t1n2mc7x`
Authoritative source manifest: `frozen_cohort.json`

This is the provider-backed run of the exact frozen five-report cohort:
Capgemini Research Institute, Activate, KPMG, Reuters Institute and Adjust.
Each member used an isolated fresh state under the verified-facts architecture;
publication, WordPress writes and cross-report analysis were disabled. The run
was executed after the producer SHA was fixed and no production code or prompt
was changed during the experiment.

## Invocation and aggregate outcome

```text
python -u scripts/quality/run_frozen_reliability_cohort.py \
  --sources-manifest docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json \
  --runs-root C:\ml-frozen-five-live-d02897a9-retry-20261105 \
  --sources-root C:\Programing\Market lense \
  --max-duration 7200 \
  --verified-facts-architecture
```

| Measure | Result |
| --- | ---: |
| Reports admitted | 5 / 5 |
| Admission evaluations / admitted / quarantined | 10 / 10 / 0 |
| Terminal outcomes | 1 awaiting review, 4 failed |
| Final HTML artifacts | 1 |
| Provider calls | 1,002 |
| Input tokens | 7,846,389 |
| Output tokens | 1,275,698 |
| Estimated cost | $1.517342 |
| Wall-clock | 11,224.594 s |
| Automatic targeted repairs | 9 across 3 reports |
| Workflow retries | 0 |
| Operator interventions | 0 |
| Publication attempts / writes | 0 / 0 |

The authoritative `cohort_result.json` is complete and mutually exclusive: the
Reuters report reached `awaiting_review` with validation and publication
readiness passing; Capgemini, Activate, KPMG and Adjust failed closed during
validation. The run verdict is **FAIL** and Step 2 readiness is **NO-GO**.

## Per-report terminal ledger

| Report | Calls | Cost | Seconds | Terminal result | Failure / output |
| --- | ---: | ---: | ---: | --- | --- |
| Capgemini | 127 | $0.348167 | 2,377.532 | failed | public semantic review; no HTML |
| Activate | 486 | $0.423778 | 3,918.371 | failed | grounding with 36 unresolved retained claims; no HTML |
| KPMG | 114 | $0.217314 | 1,405.377 | failed | omitted report limitations; no HTML |
| Reuters Institute | 105 | $0.202846 | 1,327.291 | awaiting review | validation/readiness pass; HTML retained |
| Adjust | 170 | $0.325237 | 2,196.023 | failed | public semantic review after 3 targeted repairs; no HTML |

No unsupported retained factual claim was marked verified. Failed members did
not promote their retained claims to final public output.

## Independent review

`independent_review.json` records source identity, the terminal ledger and the
physical-page audit. All five source PDFs were locally hash-checked and their
physical page counts are retained in `source_identity_manifest.json`. Only
Reuters produced final HTML, so only Reuters has a final public-output factual
review; the other four are explicitly unavailable rather than treated as
passes. Reuters pages 12, 15, 17, 24 and 33 were checked against the final
wording, including the population, base, period and category relationships.
The final HTML contains no `verified-fact:`, `evidence_id`, `evidence-id` or
`source_pack` identifiers.

The comparison with the previous retained package (`verified-facts-20261105-95379`)
is observational, not a causal improvement claim: provider calls rose from 914
to 1,002, cost from $0.937278 to $1.517342 and wall-clock from 9,202.773 s to
11,224.594 s. Final HTML increased from zero to one, but four reports still
failed and provider/runtime differences prevent attributing that change solely
to code.

## Retained artifacts and exclusions

`artifact_manifest.json` inventories every runtime file with its runtime path,
committed path (when retained), size, SHA-256 and exclusion reason. Safe report
analysis JSON/JSONL, checkpoints, validation/audit projections, exporter views,
HTML and derived PNGs are retained. Raw workflow databases, provider caches,
raw usage ledgers and local runtime configuration are excluded and listed with
hashes/reasons. Original PDF bytes are excluded; their retrieval references,
hashes and page counts remain in the source identity manifest.

The first dirty-worktree invocation and the environment-blocked preflight are
recorded in `run_invocation_failures.json`. The protected unrelated
`Wordpress/dist/marketlense.zip` modification was preserved and never staged,
changed or removed.

The aggregate exporter projection is under `export/cohort/`; per-report safe
projections are under `export/reports/<report-id>/`. The per-report exporter
has a known terminal-row retention gap for Reuters because its local
`reports.sqlite` attempt row has blank terminal fields; the authoritative
`cohort_result.json` is used for terminal outcome and readiness.

Evidence link after push: [verified-facts-20261105-d02897a9](https://github.com/mbrakker/marketlense/tree/codex/fix-retained-insight-evidence-validation/docs/quality/reliability-cohort-20261001-next-five/verified-facts-20261105-d02897a9)

Do not start Step 3 from this run. The four failed members require targeted
root-cause work and a fresh controlled rerun before promotion.
