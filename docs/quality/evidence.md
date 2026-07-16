# Evidence Process

> **Documentation type:** Current reference
> **Canonical topic:** Quality and release evidence
> **Update trigger:** Evidence manifest, review, waiver, retention, or release-review process changes.

Release evidence is generated from executed quality-gate artifacts; it is not hand-maintained in the README. The evidence tooling creates a manifest with artifact identity, schema expectations, freshness, and commit context, then produces a review against the waiver policy.

Use the repository scripts `scripts/quality/release_evidence_manifest.py` and `scripts/quality/release_evidence_review.py` with the arguments required by CI or the release procedure. Retain generated manifests and reviews in the configured output/artifact mechanism. The waiver policy is [`release_evidence_waivers.yaml`](release_evidence_waivers.yaml).

For operational diagnostics, use structured logs and retained workflow artifacts first. See [monitoring](../ops/monitoring.md) and [recovery](../ops/recovery.md).

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
  --output-dir out/cto-review-evidence \
  --expected-commit-sha "$HEAD_SHA" \
  --require-exact-head \
  --fresh-after "$FRESH_AFTER" \
  --log-corpus-scope representative_report_processing \
  --minimum-source-canaries 5 \
  --minimum-editorial-canaries 5
```

Strict mode resolves a full 40-character HEAD before snapshots and again immediately before finalization. It requires the expected, starting, and ending SHAs to match and the worktree to be clean at both checks. Git metadata being unavailable, a dirty worktree, an invalid or mismatched expected SHA, or a moving HEAD all fail the run. This proves the bundle-generation code came from one clean repository revision. It does not prove that historical log lines were produced by that revision: standard logs have separate corpus provenance unless a log record itself contains trustworthy commit metadata.

The `--log-corpus-scope` operator declaration states what the snapshotted corpus represents: `representative_report_processing`, `post_remediation_smoke_only`, or `not_declared`. The collector records this declaration and its limitation in both the run manifest and `log_content_leakage.json`; it verifies snapshots and content coverage, not that a claimed workflow was actually run. A smoke-only bundle explicitly states that no representative report-processing workflow was executed and must not be presented as evidence of that workflow.

Every database is snapshotted with SQLite's backup API before querying; live WAL files are never copied. The collector snapshots the retained crop and report-analysis JSON evidence inputs under `--artifact-dir` before either metrics or canaries are read. It does not treat unrelated benchmark or runtime sidecars as CTO-review inputs. The collector copies only canonical `market_lense_YYYY-MM-DD.log` files from `--log-dir` into the same workspace and scans only those immutable copies, line by line. Snapshot provenance records normalized source-relative and temporary-relative paths, sizes, hashes, source modification time, parsed event timestamp bounds, line/event counts, and accessibility. Noncanonical files are ignored. In strict mode a discovered standard log that cannot be copied is a failure.

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

The JSON CTO artifacts carry one `evidence_run_id` and one `repository_commit_sha`; the manifest binds stable CSV names through the same inventory. The run manifest intentionally does not hash itself. Instead, `consistency_validation.json` records the finalized run-manifest SHA after independent validation, avoiding a circular hash. Public output paths never include a workstation root or username.

All files are first created in a temporary staging directory. The collector validates snapshot integrity, exact-head state, log-content result, summary consistency, run IDs, repository SHAs, and every inventoried file hash before publishing. It will not merge into an existing output directory; use `--replace-output` for an explicit replacement. A failing strict run leaves no partial final bundle. Temporary workspaces are removed after success and failure unless `--debug-retain-snapshots` is set; retained debug workspaces are operator diagnostics and are not publishable evidence.

For release evidence, add the passed CTO JSON artifacts through the generic manifest command. The embedded repository SHA is checked against the requested release commit when `--require-head-commit` is used; a failed leakage artifact is therefore a normal unwaived `artifact_failed` release issue.

```bash
python scripts/quality/release_evidence_manifest.py \
  --release-id "<release-id>" \
  --artifact cto_log_content_leakage=out/cto-review-evidence/log_content_leakage.json \
  --expected-schema cto_log_content_leakage=1.0 \
  --artifact cto_consistency=out/cto-review-evidence/consistency_validation.json \
  --expected-schema cto_consistency=1.0 \
  --require-head-commit
```

Ordinary CI runs the collector and release-evidence unit/contract tests but does not synthesize retained databases, report artifacts, or logs merely to manufacture a passed CTO bundle. The real strict bundle remains an operator/review action against retained state.
