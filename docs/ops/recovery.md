# Recovery

> **Documentation type:** Operational procedure
> **Canonical topic:** Workflow recovery
> **Update trigger:** Failure taxonomy, checkpoint/resume behavior, or remediation runbook changes.

1. Start with `python -m src.cli remediations` and identify the remediation ID, state, typed error code, next action, attempt budget, checkpoint, and runbook. Raw diagnostics are operator-only ledger data, not a required starting point.
2. Confirm the failure category and whether it is retryable; do not repeat permanent failures without fixing the prerequisite.
3. Inspect the execution plan, preflight output, and relevant retained checkpoint before launching another side effect. A missing, stale, corrupt, or lineage-free checkpoint is a blocker, not a resume target.
4. Confirm idempotency evidence before publication, Drive-family, email-request, or any other external write. If proof is missing, keep the record in `operator_action_required`.
5. Use the smallest safe restart or explicit workflow command after correcting the cause. The base configuration keeps recovery gated; the reviewed `autonomous_mvp` overlay enables only the documented finite allowlist and does not authorize unbounded retries or unknown-error recovery.
6. Resolve or supersede the durable remediation record when the operator action is complete; do not delete historical retry logs.

The [top failure runbooks](top_failure_runbooks.md) contain typed failure-specific checks and bounded remediation commands. `docs/ops/failure_remediation.yaml` is the machine-validated runbook registry.

Local workflow locks are reclaimed when their owner PID is no longer alive;
permission-denied inspection remains conservative and falls back to the
configured TTL. This prevents a terminated local ingest process from blocking
a safe retry for the full lock window without stealing a lock held by a running
process.

## Frozen-cohort configuration provenance recovery

When a frozen cohort rejects replay because its configuration hash cannot be
recreated, retain the original manifest and record the interruption. Create a
separate, linked recovery manifest only through the canonical ingest
orchestrator recovery operation. A producer or policy change requires its own
explicit operator opt-in; policy transition is reserved for a reviewed
run-blocking reliability correction and must not alter admission inputs. All
report IDs, checksums, source identities, publishers, and ordered members must
be copied unchanged. The operation records the old and new validation
identities, source manifest, policy and producer transitions, reason,
timestamp, and a redacted effective-settings snapshot.

## Failure-specific report recovery

`src/orchestrators/failure_recovery_registry.py` is the finite recovery matrix
for report-generation and publication failures. It records the narrow retry
scope, maximum attempt, required validated checkpoint, reusable artifacts,
invalidations, action, terminal fallback, and bounded avoided-work estimate in
the durable remediation row. A typed entry is enqueued automatically only when
the exact checkpoint, its lineage/hash proof, and every required reusable
artifact are already retained. Otherwise the same row is held for an operator;
it never falls back to source preparation or vector-store creation.

| Typed failure | Only recovery action | Required checkpoint | Terminal fallback |
| --- | --- | --- | --- |
| `taxonomy_invalid_json` / `taxonomy_schema_invalid` | Taxonomy from retained selection/vector state | `selection_complete` | `permanent_failure` |
| `category_fit_contradiction` | Category fit from retained selection/vector state | `selection_complete` | `permanent_failure` |
| `unsupported_material_claim` | Affected insights/claim family plus its required validation | `analysis_complete` | `permanent_failure` |
| `final_html_internal_identifier` | Render and deterministic revalidation | `analysis_complete` | `permanent_failure` |
| `missing_report_card_manifest` | Rebuild card assets/manifest and render validation | `analysis_complete` | `permanent_failure` |
| `wordpress_readback_failed` | GET-only WordPress readback/reconciliation | `publication_preflight` | `blocked` |

The bounded reaper validates the proof again immediately before execution,
uses the existing execution-plan lease for report artifacts, increments the
durable attempt count once, and finishes as `resolved`, `deferred`, or typed
`terminal`. It converts executor exceptions to the rule's terminal fallback;
it does not leave a recovery row stranded in `retrying`. Targeted local report
repair does not need a publication idempotency key; the only WordPress action
is the GET-only lookup. Publication writes still require their existing
idempotency proof and human approval.

Run one approved, feature-gated pass with:

```powershell
python -m src.cli remediation-reap
```

The command reports resolved/deferred/terminal counts, avoided stages, and
avoided provider calls. The ledger retains `avoided_token_estimate` and
`avoided_cost_estimate_usd`; these remain `unpriced` rather than guessed until
the canonical usage ledger has a defensible per-family baseline.

## Read-only remediation soak and activation gate

The remediation ledger is the canonical workflow-wide failure backlog. UI
dead-letter rows remain compatibility data until an explicit migration is
approved. A soak observes the ledger only: it does not claim a lease, release
a lease, execute a repair, or alter historical transitions.

Before considering execution, generate the coverage inventory and runbook
validation, then retain the command output for each normal production
execution window under review:

```powershell
python scripts/quality/generate_remediation_coverage.py
python scripts/quality/generate_budget_authority_coverage.py
python scripts/ci/check_remediation_runbooks.py
$stamp = Get-Date -Format "yyyyMMddTHHmmss"
python -m src.cli remediation-soak | Tee-Object "out/ops/remediation-soak-$stamp.txt"
python -m src.cli remediation-opportunities | Tee-Object "out/ops/remediation-opportunities-$stamp.json"
```

The retained evidence must identify the repository revision, observed state
database, UTC observation time, and coverage report. It must demonstrate all
of the following before an operator approves any execution-enabled change:

1. The generated coverage report lists every production workflow as covered or
   explicitly exempted.
2. Current remediation IDs are unique. A nonzero `deduplicated records` count
   is evidence that repeated observations converged on an existing record, not
   that duplicate current records exist.
3. There are no stale leases, no missing runbook mappings, and every eligible
   record is understood. Records outside the exact automatic allowlist remain
   `operator_action_required`. A legacy `pending` record carrying
   `mark_terminal_blocker` is projected as held by the read-only soak; it is
   never reported as lease-eligible.
4. A representative sample proves checkpoint validity, lineage presence,
   attempt/cooldown enforcement, and idempotency proof for every external
   side-effect class. Public publishing, mail submission, and other external
   writes remain held without proof.
5. The activation decision, exact allowlisted workflow/error/action triples,
   review date, and rollback owner are retained with the soak output.

The base `workflow_control.remediation_reaper.execution_enabled` remains
`false`. The reviewed `autonomous_mvp` overlay turns it on with a two-record
per-pass limit and authorizes only the documented allowlist. Roll back by
selecting the base profile or setting the gate to `false`; recording and
operator visibility remain active.

## Budget-deferred work recovery

Budget deferrals are visible through `python -m src.cli deferred-work`. New
queue-worker deferrals use the canonical `budget_deferred` job state; the
legacy ledger is retained only for historical records and compatibility.
Hand off supported legacy report-generation rows explicitly before running
workers:

```powershell
python -m src.cli queue-migrate-deferred-work --yes
```

The handoff verifies the retained PDF, creates a deterministic `source_ingest`
job with the original due time, remaining attempt budget, plan hash and lineage
key, and leaves the old ledger row readable. Repeating the command returns the
same effective job. Rows for an unsupported legacy workflow, missing retained
artifact, or exhausted legacy attempt budget remain visible as `unresolved` in
the command output; they are never silently discarded or guessed into another
workflow.

The reviewed `autonomous_mvp` overlay activates the bounded legacy reaper for
the finite adapter inventory below. It does not alter the queue's normal
`budget_deferred` lifecycle and it does not enable normal queue-worker batches.
Do not run it alongside a migration of the same legacy record; use the
canonical queue controls, retry state, and remediation flow for all new work.

| Durable recovery source | Workflow / scope | Automatic action | Fail-closed result |
| --- | --- | --- | --- |
| Legacy deferred-work ledger | `report_generation` | Resume only the enforced `latest_safe` checkpoint/family with retained PDF, hash, and lineage proof | Hand off to remediation; never fresh-restart PDF/OCR/extraction/model work |
| Legacy deferred-work ledger | `report_download` | Submit canonical durable `report_acquisition.v1` job | Remediation-held if retained URL/idempotency proof is missing |
| Legacy deferred-work ledger | `publisher_inventory` | Submit canonical durable `publisher_discovery.v1` job | Remediation-held if retained publisher URL/idempotency proof is missing |
| Legacy deferred-work ledger | Any other workflow | None | Explicit remediation hold (`workflow_resume_handler_missing`) |
| Durable workflow queue | Any registered queue job in `budget_deferred` | Existing canonical queue worker claims the due job | Existing queue attempt/budget/dead-letter policy; no recovery adapter |
| Remediation ledger | Exact report-generation failure registry and GET-only WordPress readback | Existing typed remediation executor | Terminal or operator-held when checkpoint, lineage, action, budget, or idempotency proof fails |

Every invocation first rechecks the canonical budget, then rebuilds the
minimal plan and validates reusable artifacts. It retains the work identity,
workflow/adapter, due time, plan hash, reusable-artifact kinds/count, attempt
count, terminal result, and bounded reason in durable state and structured
events. It preserves the original idempotency key and uses a SQLite lease, so a
second worker cannot execute the same record. A continued `defer` is
rescheduled after the configured delay; `pause` and `stop` always enter
actionable remediation rather than becoming a new pending retry. Set the
feature flag back to `false` for rollback: queued records remain intact for
inspection and manual recovery.

For report processing, checkpoint resume is orchestrator-owned and validates retained artifacts and lineage. Do not manually edit checkpoint state to bypass validation. For publication recovery or rollback, use [WordPress operations](wordpress.md).

## Durable workflow queue recovery

Use the queue control plane for accepted asynchronous work. It is separate from
the remediation ledger: the queue owns normal due work, retries, leases, and
outbox materialisation; remediation remains the terminal/operator boundary.

```powershell
python -m src.cli queue-health
python -m src.cli queue-inspect-job <job-id>
python -m src.cli queue-release-expired-leases
python -m src.cli queue-reconcile
python -m src.cli queue-materialize-outbox
```

Pause a queue with a reason before an incident investigation. Drain mode stops
new claims while preserving durable work. `queue-requeue --yes` is only for a
blocked or dead-letter job after its retained input and idempotency proof have
been checked; it never resets product-domain state. See [asynchronous workflow
queue](../architecture/asynchronous-workflow-queue.md) for the state machine
and approval-to-publication rules.
