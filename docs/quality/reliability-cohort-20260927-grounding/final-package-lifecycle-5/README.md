# Final retained-claim package lifecycle — pinned five-report cohort

This follow-up uses exactly five reports from the frozen reliability cohort:
Merchant Risk Council, Deloitte, Emplifi, StackAdapt, and DoubleVerify. The
source files and checksums are pinned in [`frozen_cohort.json`](frozen_cohort.json).
The full 20-report cohort is not part of this measurement.

The runner uses fresh isolated state and the normal production report workflow.
It stops at publication readiness and does not perform WordPress publication.
The temporary database and full workflow output stay under the ignored `tmp/`
directory; this README will retain only sanitized scalar counts, run identities,
hashes, and typed per-report outcomes.

Invocation:

```powershell
python scripts/quality/run_frozen_reliability_cohort.py `
  --sources-manifest docs/quality/reliability-cohort-20260927-grounding/final-package-lifecycle-5/frozen_cohort.json `
  --runs-root tmp/retained-claim-package-lifecycle-5 `
  --max-duration 7200
```

Measurement evidence is added after that run completes.
