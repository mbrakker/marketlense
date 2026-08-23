# Evidence Process

> **Documentation type:** Current reference
> **Canonical topic:** Quality and release evidence
> **Update trigger:** Evidence manifest, review, waiver, retention, or release-review process changes.

Release evidence is generated from executed quality-gate artifacts; it is not hand-maintained in the README. The evidence tooling creates a manifest with artifact identity, schema expectations, freshness, and commit context, then produces a review against the waiver policy.

Use the repository scripts `scripts/quality/release_evidence_manifest.py` and `scripts/quality/release_evidence_review.py` with the arguments required by CI or the release procedure. Retain generated manifests and reviews in the configured output/artifact mechanism. The waiver policy is [`release_evidence_waivers.yaml`](release_evidence_waivers.yaml).

CI also runs `scripts/quality/generate_workflow_queue_evidence.py` against a temporary SQLite database. It requires an expected full commit SHA, checks that HEAD is unchanged before and after generation, and records only queue record IDs and scalar counts. The fixed scenario proves submission, lease/start, completion, one downstream outbox event and materialisation, expired-lease recovery, a bounded retry, a budget deferral, and a dry-run publication-approval handoff. The artifact is required in the release manifest and is included in `release-evidence-bundle`.

This deterministic queue evidence confirms queue semantics at the exact tested revision; it does **not** demonstrate live production throughput, provider behavior, or a public WordPress write. The GitHub job summary explicitly preserves that distinction and bounds any listed unwaived issues.

For operational diagnostics, use structured logs and retained workflow artifacts first. See [monitoring](../ops/monitoring.md) and [recovery](../ops/recovery.md).

The bounded workflow-queue foundation record is retained in
[workflow-queue-foundation-evidence-2026-07-18.md](workflow-queue-foundation-evidence-2026-07-18.md).

## CTO Review Evidence Bundles

`scripts/quality/collect_cto_review_evidence.py` creates a point-in-time CTO-review bundle from retained state. A strict CTO review uses an exact repository HEAD, not merely the best-effort Git marker retained by legacy collection.

Run the strict operator procedure from the repository root after representative report processing has completed. The `FRESH_AFTER` value is an operator-provided, timezone-aware timestamp for that review run; use a current value, not a permanently checked-in date.

```bash
HEAD_SHA="$(git rev-parse HEAD)"
FRESH_AFTER="<current-run-start-ISO-8601>"
python scripts/quality/collect_cto_review_evidence.py \
  --state-dir state \
  --artifact-dir out \
  --log-dir logs \
  --output-dir docs/CTO_evidence \
  --expected-commit-sha "$HEAD_SHA" \
  --require-exact-head \
  --fresh-after "$FRESH_AFTER" \
  --log-corpus-scope representative_report_processing \
  --minimum-source-canaries 5 \
  --minimum-editorial-canaries 5 \
  --include-github-status \
  --replace-output
```

Strict mode resolves a full 40-character HEAD before snapshots and again immediately before finalization. It requires the expected, starting, and ending SHAs to match and the worktree to be clean at both checks. Git metadata being unavailable, a dirty worktree, an invalid or mismatched expected SHA, or a moving HEAD all fail the run. This proves the bundle-generation code came from one clean repository revision. Standard structured log contexts additionally retain a producer commit when `MARKET_LENSE_PRODUCER_COMMIT` is supplied, but a collector revision and a historical producer revision remain distinct evidence.

The final check excludes only the collector's own temporary staging directory when that directory is created beneath the repository. Any other tracked or untracked worktree change still fails strict collection.

The `--log-corpus-scope` operator declaration states what the snapshotted corpus represents: `representative_report_processing`, `post_remediation_smoke_only`, or `not_declared`. Strict representative processing requires timezone-aware `--fresh-after` before any snapshot; omission fails rather than creating a false pass. The leakage artifact records `freshness_state` as `passed`, `failed`, `unverified`, or `not_required`, separately from the content-leakage result. The collector verifies snapshots and content coverage, not that a claimed workflow was actually run. A smoke-only bundle explicitly states that no representative report-processing workflow was executed and must not be presented as evidence of that workflow.

For an isolated historical run whose canonical logs were not retained in that
namespace, use `--allow-unavailable-run-logs` with an empty run-owned log
directory. This preserves strict repository, database, artifact, and canary
integrity checks while recording log-content and freshness evidence as
`unavailable`; it never substitutes repository-wide logs or claims a leakage
pass.

Every database is snapshotted with SQLite's backup API before querying; live WAL files are never copied. The collector snapshots the retained crop and report-analysis JSON evidence inputs under `--artifact-dir` before either metrics or canaries are read. It does not treat unrelated benchmark or runtime sidecars as CTO-review inputs. The collector copies only canonical `market_lense_YYYY-MM-DD.log` files from `--log-dir` into the same workspace and scans only those immutable copies, line by line. Snapshot provenance records normalized source-relative and temporary-relative paths, sizes, hashes, source modification time, parsed event timestamp bounds, line/event counts, and accessibility. Noncanonical files are ignored. In strict mode a discovered standard log that cannot be copied is a failure.

Acquisition and browser CSV metrics are derived from the task-scoped `reports.acquisition_attempt_resources` records, not from legacy `publisher_download_route_history`. They retain publisher, route family, terminal outcome, elapsed time, cost, Browser Use model calls and tokens, browser launches and activity, retries, and mailbox/Drive activity. Legacy route history remains historical routing evidence only and is not a fallback input for current acquisition metrics.

The log-content assessment takes deterministic representative samples from two categories:

- source-report text from retained page/source-style fields, source-backed evidence-pack excerpts, and document-map section summaries;
- generated editorial text from retained `artifacts.json` fields such as LinkedIn posts, expert comments, TLDRs, and executive summaries.

It normalizes Unicode and whitespace, rejects short, boilerplate, placeholder, title-only, and identifier-only fields, then deterministically orders and spreads selected paragraphs across reports. Defaults require five source and five editorial canaries, with at most 25 in each class. Missing canaries, no standard logs, or no log at or after `--fresh-after` produce `incomplete`; they never become a zero-match pass.

Raw snapshotted log lines are compared deterministically, including unstructured and JSON-escaped records. A match is either a whole normalized paragraph or two independent long windows from the same paragraph in one log record. The evidence never stores a paragraph, matching log line, raw source, or raw editorial text. It stores only bounded metadata, normalized-text hashes, and redacted match location and structured-event identifiers.

The existing CSV filenames remain stable. The collector additionally writes:

- `detailed_metrics.json`: finalized structured input for summary derivation;
- `executive_summary.json`: totals derived only from that finalized detail;
- `snapshot_manifest.json`: database, retained-artifact, and standard-log snapshot provenance;
- `log_content_leakage.json`: versioned canary coverage and redacted matching result (`passed`, `failed`, or `incomplete`);
- `evidence_run_manifest.json`: exact repository provenance, configuration, snapshot-manifest hash, and canonical file inventory with byte counts and SHA-256 values;
- `consistency_validation.json`: compact checks, exact-head outcome, repository SHA, and finalized run-manifest hash.

The JSON CTO artifacts carry one `evidence_run_id` and one `repository_commit_sha`; the manifest binds stable CSV names through the same inventory. It records the collector Python/OS separately from bounded producer-commit observations in historical structured logs; historical producer runtime version is explicitly `not_retained` when absent. The run manifest intentionally does not hash itself. Instead, `consistency_validation.json` records the finalized run-manifest SHA after independent validation, avoiding a circular hash. Public output paths never include a workstation root or username.

The canonical output location is [`docs/CTO_evidence/`](../CTO_evidence/README.md). In addition to the existing integrity, log-leakage, detailed, summary, and CSV artifacts, every bundle writes these machine-readable CTO artifacts:

- `workflow_to_remediation_coverage.json`, `artifact_lineage_completeness.json`, and `architecture_manifest.json` for commit-bound repository evidence;
- `source_identity_schema.json`, `editorial_rule_catalog.json`, and `effective_run_profile_matrix.json` for the public policy and configured execution surface;
- `github_main_status.json` for the exact tested commit's check/PR state, the latest main commit, and their explicit revision-match relationship when `--include-github-status` is passed; and
- `runtime_telemetry.json` for acquisition, browser, cost, OCR, crop, plan-divergence, deferred-work, remediation, embedding, WordPress, editorial-quality, and public-page evidence.

The lineage artifact reports each family separately: total, active, superseded,
complete-active, active-only completeness, all-history completeness, required
field missing counts, and processing/schema version distributions. Incomplete
historical rows are not silently promoted; reuse remains blocked unless the
canonical lineage boundary can prove every required field.

The collector reports a metric as `available`, `partial`, `empty`, or `unavailable`. `partial` and `unavailable` are explicit retained-data limitations, not zeroes or inferred successes. In particular, the current stores do not prove per-report browser traces, cache hit/miss rates, cost attribution across every side effect, WordPress duplicate/rollback rates, human editorial ratings, or hosted public-page telemetry until those values are retained by their owning boundaries.

Execution-plan telemetry reads the production writer's
`divergence_json.reconciliation_status` as the canonical result. A populated
reconciliation object is normal for both matches and divergences. Older rows
without that status are compared using unordered planned/actual stages, call
categories, and side effects: only unplanned work diverges; malformed or
incomplete historical values remain explicitly `unreconciled`.

All files are first created in a temporary staging directory. The collector validates snapshot integrity, exact-head state, log-content result, summary consistency, run IDs, repository SHAs, and every inventoried file hash before publishing. It will not merge into an existing output directory; use `--replace-output` for an explicit replacement. A failing strict run leaves no partial final bundle. Temporary workspaces are removed after success and failure unless `--debug-retain-snapshots` is set; retained debug workspaces are operator diagnostics and are not publishable evidence.

For release evidence, add the passed CTO JSON artifacts through the generic manifest command. The embedded repository SHA is checked against the requested release commit when `--require-head-commit` is used; a failed leakage artifact is therefore a normal unwaived `artifact_failed` release issue.

```bash
python scripts/quality/release_evidence_manifest.py \
  --release-id "<release-id>" \
  --artifact cto_log_content_leakage=docs/CTO_evidence/log_content_leakage.json \
  --expected-schema cto_log_content_leakage=1.0 \
  --artifact cto_consistency=docs/CTO_evidence/consistency_validation.json \
  --expected-schema cto_consistency=1.0 \
  --require-head-commit
```

Ordinary CI runs the collector and release-evidence unit/contract tests but does not synthesize retained databases, report artifacts, or logs merely to manufacture a passed CTO bundle. The real strict bundle remains an operator/review action against retained state.

For a frozen validation cohort, `scripts/quality/export_reliability_run_evidence.py`
adds run-specific funnel, terminal-outcome, failure, recovery, publication, and
cost-attribution views beneath that bundle. It is read-only with respect to
runtime state and exports bounded identifiers and scalar metrics only. It must
not be used to infer a successful publication when publication-stage records
are absent.

### Reusable sanitized acquisition-assessment projection

When a completed acquisition assessment has a retained raw current JSONL and a
comparable retained baseline JSON, use
`scripts/quality/acquisition_evidence_projection.py` to make the diagnostic
views reviewable from the committed evidence directory. This is a read-only
evidence transformation: it **must not** rerun discovery, acquisition, browser
automation, mailbox polling, or any downstream stage.

The inputs are the exact current JSONL, the exact baseline JSON containing its
`records` list, and the known SHA-256 of the current JSONL. Retain the output
under `docs/CTO_evidence/<assessment>/sanitized_projection/`:

```text
python scripts/quality/acquisition_evidence_projection.py \
  --current-jsonl <retained-current>/acquisition_attempts.jsonl \
  --baseline-json <retained-baseline>/baseline_replay.json \
  --output-dir docs/CTO_evidence/<assessment>/sanitized_projection \
  --expected-current-sha256 <retained-current-sha256>
```

The generated canonical projection contains only candidate and publisher IDs,
tested commit/configuration hashes, route and terminal reason, normal artifact
verification/source-format fields, scalar duration/browser/Agent/token/cost/
mailbox/Drive metrics, and aggregate views. It omits URLs, local paths,
screenshots, form values, raw browser content, and model output. It writes a
per-candidate projection, failure Pareto, route metrics, baseline-versus-
current metrics, remaining failures, and a consistency record. The consistency
record proves the input hashes, candidate counts, exact candidate-set equality,
and agreement between the remaining-failure list and aggregate metrics.

An input-hash mismatch is a hard error. A candidate-set mismatch remains
explicit in the output so an assessor can diagnose it, but the baseline and
current run are not comparable and must not be used to claim an improvement.
Commit the resulting views, their input references/hashes, and the invocation
in the assessment README; do not commit the raw JSONL when it contains
non-sanitized runtime data.

The retained partial record for the 2026-08-13 frozen 20-report run is
[reliability-run-2026-08-13.md](reliability-run-2026-08-13.md). It records a
blocked sandbox publication target explicitly and is not release evidence.

## A9/A3/A6 representative operational evidence

Before a strict bundle used to close source provenance, remediation, or budget
authority work, regenerate the two matrices, retain a read-only remediation
soak, and run the credential-gated provider smoke when its opt-in is present.
The provider smoke is a bounded real call; a missing credential or opt-in is a
blocked validation, never a synthetic substitute.

```powershell
python scripts/quality/generate_remediation_coverage.py
python scripts/quality/generate_budget_authority_coverage.py
python -m src.cli remediation-soak
$env:RUN_OPENAI_SMOKE_TEST = "1"
python -m pytest tests/integration/test_openai_smoke.py -m integration -q
```

Record the run ID, report/source IDs or hashes, decision statuses, reservation
reconciliation status, and persisted actual-use counts in the evidence notes.
Do not include source HTML, report paragraphs, prompts, provider responses, or
credentials. The strict collector remains the exact-head authority for the
resulting snapshots and log-content assessment.
