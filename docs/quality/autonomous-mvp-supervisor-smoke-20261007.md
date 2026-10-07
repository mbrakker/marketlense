# Autonomous MVP supervisor smoke

**Run:** 2026-10-07 14:49 UTC · **Implementation commit:** `edd544006328c76eeb61200efc9162918f981346` · **Profile:** `autonomous_mvp`
**Procedure:** [Autonomous MVP runbook](../ops/autonomous-mvp.md)

The isolated smoke used a fresh SQLite state database and a temporary copy of
the base configuration with the committed autonomous overlay selected. It
invoked the production CLI twice with:

```powershell
python -m src.cli supervise-workflows --once
```

The queue started with one pending job and one leased job whose lease had
expired. Both were registered `briefing_opportunity.v1` jobs. The first healthy
pass exited `0`, recovered the expired lease, completed both jobs, and reported
no deferred jobs or errors. Both jobs ended `succeeded` with one attempt each.

Submitting the first job again with the same idempotency key returned the
existing job (`created=false`). The replay pass exited `0`, was healthy, and
completed no work. Both jobs remained succeeded with one attempt each, and the
effective opportunity row count remained two. No external provider calls or
operator intervention occurred.

Raw machine-readable output and the isolated state database are retained in the
local ignored path `out/ops/autonomous-mvp-supervisor-smoke-20261007T144916Z/`.
The smoke used the real supervisor CLI, queue persistence, lease recovery, and
registered handler; the deterministic handler needed no API or LLM call.
