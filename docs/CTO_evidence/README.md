# CTO evidence pack

Prompt 2 code/test HEAD verified: `94ab4e632b2279af74b921dcdae3a3400e35f240`. Collector/projector revision: `e3ba5c76765f48b4403a2ef5774fb2194d16489b`. The pack contains 24 independent declared runs and 4 historical telemetry snapshots.

Run-scoped metrics remain separate in each bundle. `complete` means the manifest-required evidence classes were present; it does not mean the workload passed a product-level acceptance test. Historical runs are never relabeled as current-HEAD evidence.

## Coverage matrix

| Evidence area | Status | Limitation |
|---|---|---|
| correctness validation | **partial** | No current-HEAD full report end-to-end cohort. |
| publication readiness | **partial** | Package readiness passed 16/16 rules with zero unsupported/unresolved factual counts; the artifact predates final HEAD. |
| factual quality controls | **partial** | No current-HEAD full report factual-quality evaluation; reviewer rubric is unavailable. |
| performance | **partial** | No matched performance benchmark on current HEAD; artifact-DAG baseline conflict prevents a delta. |
| provider timing | **partial** | Provider profiles are historical and do not establish current-HEAD end-to-end latency. |
| resource usage cost | **partial** | Per-subject cost attribution is incomplete in several cohorts; no current-HEAD full-run cost evidence. |
| concurrency | **partial** | Mixed pre-fix/current source is reduced to candidate-only; no causal before/after claim. |
| critical path | **partial** | One report only; not current-HEAD evidence. |
| retry attempt history | **partial** | No current-HEAD per-report product retry history. |
| reuse | **partial** | Counters show zero reuse and no immutable subject/claim mapping; speedup is not established. |
| acquisition | **partial** | No current-HEAD acquisition run; one source is a byte-identical alias and is not duplicated. |
| visual qa | **partial** | Associated PNGs were not retained; visual artifact bytes are unavailable. |
| editorial review | **partial** | Reviewer attribution and versioned rubric are unavailable; bundle is incomplete. |
| publication side effects | **partial** | One sandbox draft create is retained from pre-fix SHA 1997e34; exact-final-HEAD replay/readback succeeded with zero extra writes. |
| idempotency readback | **proven** | Exact-final-HEAD replay made zero writes and authenticated readback matched content/metadata; operational requeue recovered the earlier dead letter. |
| immutable subject coverage | **partial** | Some aggregate profiles and side-effect runs have no per-subject identity. |
| exact repository sha | **proven** | Historical SHA bindings identify historical code; only current-head-integrity is current HEAD. |
| current head full end to end | **partial** | Exact-head CI and replay/readback passed; a fresh post create on final HEAD was not observed. |
| current head provider cost | **not_applicable** | This verification run did not invoke providers, so provider cost is not applicable to it. |
| production publication run | **not_evaluated** | No new production publication workload was run. |

## Declared runs

| Run | Tested SHA | Subjects | Completeness / disposition | Missing classes | Bundle SHA-256 |
|---|---|---:|---|---|---|
| `acquisition-final30` | `69f55aa4ed1a` | 30 | complete / not_evaluated | — | `2d19ff63d71dee25085f7da25704f9ba6c221fca6a683f04026e62e3333a1e45` |
| `acquisition-initial30` | `b463da172bf1` | 30 | complete / not_evaluated | — | `aa63694a1944b9058911e8143354c1306c5bb5dcf1ec51c56f480c29bbf8f03b` |
| `acquisition-previous-current` | `69f55aa4ed1a` | 30 | complete / not_evaluated | — | `9a288c650233ba6dbf9b68a426a7f6f8381cce3be32db9ae78bb015d81456922` |
| `artifact-dag-candidate-20261006` | `39e5f42386de` | 0 | complete / not_evaluated | — | `fcdab868d21c85321d87cf7af1e767df3a63041641a532e2c95d0c83d23fc410` |
| `cohort-ias-per-report-timeout-20261002` | `06e58098a6a8` | 7 | complete / not_evaluated | — | `a69a62c3d8797526026f66040df7b62a5529c5fbb523d2c53ab7810b77e0c9e1` |
| `cohort-reliability-cohort-20260914-bfab37bb` | `bfab37bbd1e4` | 20 | complete / not_evaluated | — | `08015860ad0ed55fc979cd69026c41502c96d36c56424232f2588698b3bdd88f` |
| `cohort-reliability-cohort-20260919-a21-final` | `c89c545d649a` | 20 | complete / not_evaluated | — | `99a3538cf00d8aca6530013724a7ff5440415a7f2d64ad9f146202f5ea44ffc0` |
| `cohort-reliability-cohort-20260920-a21-final` | `89b4fc4c1159` | 20 | complete / not_evaluated | — | `02cbb544c96978d0181359451b2db86427cf0a449b117afc7eed6847999a82a6` |
| `cohort-reliability-cohort-20260927-grounding` | `8a05e2d25a7b` | 20 | complete / not_evaluated | — | `005a0725f26a1a00a9e4dae8c84866c940ea60b55d843400be73c96095c024d9` |
| `cohort-reliability-cohort-20260927-grounding-postfix-cohort-result` | `55cd01815d97` | 20 | complete / not_evaluated | — | `6155c30e48aa9788fc1e50de7c709de5b90c1674600f9bce5c2bdc3bdf36407d` |
| `cohort-reliability-cohort-20261001-batch3-finalization` | `11ca2ce3e73c` | 5 | complete / not_evaluated | — | `07371c7310022cf85cec0e8bb89421933a67767503a508312ee4c543e205a569` |
| `cohort-reliability-cohort-20261001-batch3-finalization-before-cohort-result` | `5fe10a5da22f` | 5 | complete / not_evaluated | — | `b0ce18a2e0e1752aa04f0a06f0ea44875d11e8cfd125622cc5bde43a6e7268dd` |
| `cohort-reliability-cohort-20261001-next-five` | `469c13c15d0d` | 5 | complete / not_evaluated | — | `a530814b746d90d4169ff08ffc7f57bfbd5344f2fef870eaaa654117978fab88` |
| `cohort-reliability-cohort-20261001-next-five-before-cohort-result` | `365c342ba3ff` | 5 | complete / not_evaluated | — | `eca64b13c1e9579f0228e67dc53c59f62563abfce2a5f3427af9180e2571d582` |
| `cohort-report-agnostic-prompt-repair-20261001` | `eae746de7a65` | 5 | complete / not_evaluated | — | `b096c0fb636053aebf3a37855a9de0e55e9572bb6c804928d0f513fc186570c9` |
| `current-head-integrity-20261007` | `94ab4e632b22` | 4 | complete / pass | — | `c79170852a7004bedfd1c62e82000340c4859fde9169774dc3344236a54e8487` |
| `file-search-comparison-20261003` | `be70355a28b8` | 5 | complete / not_evaluated | — | `7c96014fc0f534a127fc24f36386c2897fe42b7b3f598c66fb74d83e69c75c62` |
| `grounding-concurrency-candidate-20261006` | `a1f2affcb4dd` | 0 | complete / not_evaluated | — | `0304d8dd076f6c365e94d0ce3866d66a152e92333b3ab2bd8f1f956bfe2fa71b` |
| `human-editorial-review-20260901` | `56628ad76f86` | 5 | incomplete / not_evaluated | reviewer_attribution, rubric_identity | `b58b487b2cd31cdbf14346e50ee5b598f9991df9a3fb188182e271caf6108956` |
| `provider-critical-path-20261006` | `9b3b3c39c5a4` | 1 | complete / not_evaluated | — | `023db8608f006b32edc5b79569329b4f0006d031a02408bc348928eb40e565a3` |
| `provider-latency-20261006` | `bf10ac8870f3` | 1 | complete / not_evaluated | — | `a7baba3b84958400def4437a1d372249beb250209de48c29d4314f04eed97787` |
| `validation-reuse-follow-up-20261006` | `1ec67ff185bf` | 0 | complete / not_evaluated | — | `c95d8691d0ce4eee9f2703c8e6ea0f6d807907955585b3c012eb4328e7a1acc4` |
| `visual-crop-qa-20261006` | `39e5f42386de` | 3 | incomplete / not_evaluated | source_visual_artifacts | `b2833c5c42e581c9d21067e274e809ef21de9b890015f80b974017000459d914` |
| `wordpress-publication-attempt-20260811` | `0bdd91998e39` | 0 | incomplete / not_evaluated | authenticated_readback, idempotency | `bb55d7bb9fcc9bd4aa6571c7a500184ea61004e34c724b3fbfb7bd5b7a1f369d` |

## Current-HEAD evidence

Prompt 2 code/test HEAD `94ab4e632b2279af74b921dcdae3a3400e35f240` passed the focused autonomous-publication and WordPress queue/readback tests (78 passed), the local default suite (6,811 passed, 1 skipped, 0 failed), and GitHub CI run `37696738821` (6,812 passed, 0 skipped, 0 failed). Coverage, mutation, release-evidence, architecture/boundary/docs/schema/WordPress gates and CodeQL run `37696738765` passed. The optional dedicated `WP_STAGING_*` CI gate was skipped; the operator-designated sandbox was separately exercised.

A report package retrieved from Google Drive passed all 16 publication-readiness rules with zero unresolved or unsupported factual claims. One autonomous policy actor approved the exact package checksum and policy/config identity; one approval and one durable WordPress outbox event were retained. The sandbox contains one `ml_report` draft and one effective WordPress create.

The initial create happened on pre-fix SHA `1997e34f3558301f11d9ca7b5f78a7dc7c1a8835`; the worker dead-lettered because the queue report create path skipped authenticated readback. Commit `62b12c79` fixed that path. After exact-head CI passed, the same package was operationally requeued and replayed on final code SHA `94ab4e63`; the worker revalidated approval/checksum, authenticated readback succeeded, and the replay made zero additional WordPress writes. A fresh authenticated readback using the persisted exact content/metadata expectation verified every required check. No human publication approval or production write occurred. The operational requeue was required to recover the pre-fix dead letter, so this does not prove a no-intervention first attempt or a fresh post create on final HEAD.

The first CI failure after the readback fix was a stale `SimpleNamespace` FileStat test fake that omitted `mtime_ns`; production raised `AttributeError` before reaching the retry assertion. The fake now supplies the complete response contract. No test, validation, readiness, checksum, approval, idempotency, or CI gate was weakened.
## Provenance and privacy

`evidence_inventory.json` records source paths, original/source hashes, embedded SHA claims, manifest-bound SHA endpoints, field-supported classes, publicized derivatives, and limitations. Raw report/publisher identifiers, local absolute paths, report content, private URLs, and provider request IDs are excluded from canonical source derivatives and bundles. Some crop-QA and editorial inputs were locally retained under ignored `out/` before this pack; their publicized derivatives and original hashes are now committed, while the original inputs were not repository-retained.

## Remaining autonomous-MVP gaps

The sandbox evidence establishes one policy-approved draft create, exact-checksum approval, authenticated content/metadata readback, and zero-write identical-package replay. The initial create occurred before the final readback fix and required operational requeue; a fresh create on final HEAD is not claimed. Current-HEAD full report generation/factual-quality, performance, and provider-timing evidence also remain incomplete, so the broader autonomous MVP assessment remains blocked.

## Verification

Run `python scripts/quality/verify_cto_evidence_pack.py` to check every manifest, bundle parse/round-trip, source hash, SHA binding, verification record, inventory record, index entry, and privacy scan.

## Collector and bundle contract

`cto_evidence_bundle.json` is the canonical bounded contract produced by `scripts/quality/collect_cto_review_evidence.py`. A collection without `--run-manifest` reports a historical system snapshot and does not assign a workload disposition. A declared run keeps its exact tested SHA, immutable subjects, required criteria, outcomes, run-scoped measurements, and limitations separate from `historical_state`. Historical SQLite and artifact telemetry never contributes to run totals or criteria.

Run manifests use schema version `1.0`, repository-relative hash-pinned source paths, full tested SHAs, immutable subject hashes, declared stage scope, and optional comparison identities and invariants. Start and end timestamps are timezone-aware and supplied together; use `null` for both when the producer did not retain them. The projector requires `exact_repository_sha`; it recognizes declaration classes `immutable_subjects`, `configuration_identity`, `stage_scope`, `run_timestamps`, `external_side_effect_policy`, and `source_integrity`. Producer adapters add classes such as `outcomes`, `resource_usage`, `provider_timing`, `quality`, `comparison`, and `external_actions`. A missing required source or measurement is unavailable or incomplete; a content or identity contradiction is invalid. Comparisons report candidate-minus-baseline deltas and preserve `causal_attribution: not_established`.

Runtime telemetry is derived only from immutable SQLite and retained-artifact snapshots. Each historical metric declares `observed`, `partial`, or `unavailable`; unavailable means the measurement was not retained, not zero. The legacy `executive_summary.json` contains historical collector totals for reconciliation; use each canonical bundle for run results.

## Fresh collection

Write a new snapshot to a separate, previously unused output directory. This keeps the committed evidence pack intact:

```powershell
$evidenceHeadSha = git rev-parse HEAD
$freshAfter = "<current-run-start-ISO-8601>"
python scripts/quality/collect_cto_review_evidence.py --state-dir state --artifact-dir out --log-dir logs --output-dir out/cto_evidence_collection --expected-commit-sha $evidenceHeadSha --require-exact-head --fresh-after $freshAfter --log-corpus-scope representative_report_processing --include-github-status
```

To project one retained workload or benchmark, add `--run-manifest docs/CTO_evidence/runs/<run-id>/run_manifest.json`. The manifest names producer artifacts and their hashes; the collector verifies those bytes and projects supported formats without rewriting producer results. Keep the manifest and every source artifact inside the repository root. Unsupported formats and absent measurements remain explicit gaps.

The GitHub status snapshot is opt-in because it performs an external read. It records the tested revision separately from latest `main`, and returns an explicit unavailable status when it cannot be collected.
