# Frozen five-report verified-facts E2E acceptance

Run date: 2026-11-05
Producer SHA: `95379a8decc5d4f1ca814170619e832c8bacf95f`
Run identity: `frozen-reliability-oboqn82y`
Authoritative manifest: `docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json`

This is the required provider-backed run of the exact frozen cohort: Capgemini,
Activate, KPMG, Reuters Institute and Adjust. It used the fixed producer SHA,
the retained source PDFs, the verified-facts architecture, a fresh run root,
no shared batch, no publication flag and no WordPress writes. No production
code or prompts were changed during the experiment, and no report was rerun
after a terminal failure.

## Command and aggregate outcome

```text
python -u scripts/quality/run_frozen_reliability_cohort.py \
  --sources-manifest docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json \
  --runs-root C:\ml-frozen-five-live-95379-20261105 \
  --sources-root C:\Programing\Market lense \
  --max-duration 7200 \
  --verified-facts-architecture
```

| Measure | Result |
| --- | ---: |
| Reports admitted | 5 / 5 |
| Terminal complete | 0 / 5 |
| Terminal failed | 5 / 5 |
| Final HTML artifacts | 0 |
| Provider calls | 914 |
| Input tokens | 4,168,035 |
| Output tokens | 840,654 |
| Estimated cost | $0.937278 |
| Wall-clock | 9,202.773 s |
| Automatic repairs | 0 |
| Workflow retries | 0 |
| Operator interventions | 0 |
| Publication attempts / writes | 0 / 0 |

Terminal outcomes are mutually exclusive and come directly from
`cohort_result.json`: four `artifact_final_insight_coverage_invalid` failures
and one `validation_failed` failure. The overall verdict is **FAIL** and the
Step 2 readiness verdict is **NO-GO**. This run must not be presented as a
successful frozen-cohort acceptance.

## Per-report ledger

| Report | Calls | Cost | Duration | Terminal outcome | Public output |
| --- | ---: | ---: | ---: | --- | --- |
| Capgemini | 95 | $0.124882 | 1,291.421 s | `artifact_final_insight_coverage_invalid` | none |
| Activate | 470 | $0.270949 | 3,585.285 s | `artifact_final_insight_coverage_invalid` | none |
| KPMG | 95 | $0.144853 | 1,165.343 s | `artifact_final_insight_coverage_invalid` | none |
| Reuters Institute | 94 | $0.165084 | 1,431.846 s | `artifact_final_insight_coverage_invalid` | none |
| Adjust | 160 | $0.231510 | 1,728.878 s | `validation_failed` | no HTML; artifact only |

Capgemini, Activate, KPMG and Reuters stopped before final artifact and HTML
generation because final insight coverage validation failed. Activate also had
one unsupported evidence-fidelity result. Adjust completed verified-fact
admission (9 admitted, 1 quarantined, 10 evaluated), exact source-hash
validation and artifact generation, then failed public editorial quality:
e-commerce and finance findings were repeated across public roles and the
GenAI finding omitted source limitations (timeframe, geography and denominator).
The failure was broad and non-repairable; no automatic repair was attempted.

## Independent source and editorial review

`independent_review.json` records the per-report review and the physical-page
audit. The Adjust PDF hash is exactly
`ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3`, with 41
physical pages. Pages 3, 9, 19, 21, 27, 29, 34, 35 and 36 were inspected
against the seven retained Adjust insights. The source text supports the
reported numeric relationships and the GenAI small-group qualifier, but the
run is still rejected because its final public editorial package was not
distinct and complete.

The four reports without final output are explicitly marked unavailable; their
retained findings and evidence-fidelity records are not treated as final
editorial evidence. There are no independently confirmed unsupported material
claims marked verified because no report reached publication readiness.

## Retained artifacts and exclusions

`artifact_manifest.json` is the machine-readable inventory of the retained
safe projection. It records runtime-relative path, committed repository path,
size, SHA-256 and status/reason for every generated runtime artifact, including
the provider-free preflight, exporter projections, checkpoints, report
analysis, validation records and derived PNGs. Raw workflow databases,
provider caches, raw usage ledgers and local runtime state are listed as
excluded with hashes and reasons; they are not committed. Original source PDF
bytes are also excluded. Their MD5/SHA-256/page-count identity and local
retrieval references are in `source_identity_manifest.json`.

The first dirty-worktree setup failure and the preflight environment block are
recorded in `run_invocation_failures.json`. The protected unrelated
`Wordpress/dist/marketlense.zip` change was preserved and was never staged.

Evidence link after push: [verified-facts-20261105-95379](https://github.com/mbrakker/marketlense/tree/codex/fix-retained-insight-evidence-validation/docs/quality/reliability-cohort-20261001-next-five/verified-facts-20261105-95379)

## Next action

Do not start Step 3 from this run. The next production work is to investigate
the general final-insight coverage failure and the Adjust public-distinctness
failure using the retained artifacts, then rerun only the affected reports
under the repository's normal failure-recovery policy. No such fixes were
made as part of this acceptance experiment.
