# Archived Agent-Engineering Evidence

This directory is a frozen historical record, not an active agent workflow or
benchmark entrypoint. It contains the ten-case pre-Phase-1 protocol, six
holdouts, evaluator-owned payloads, and captured score records. No repository
script, skill, CI gate, or operating policy invokes these files.

The immutable pre-Phase-1 baseline recorded 9/10 evaluator-correct cases and
85% required-verification success, with zero verified scope violations, zero
human intervention/rework, and a 216-second median across the comparable
cases. The holdouts remain preserved and were not used to tune Phase-1.

Phase-1 controls were rejected and removed. The final staged candidate was
evaluated against the same frozen ten cases and produced 8/10 evaluator-correct
cases and 75% required-verification success; it did not improve on the
baseline. The rejection record is
[`baselines/phase1-final-rejection.json`](baselines/phase1-final-rejection.json).

The retained CodeGraph and final-engineering-review JSON records are historical
rejection evidence only. MarketLense has no CodeGraph integration, agent
completion-control feature, reviewer workflow, or agent benchmark runtime.
