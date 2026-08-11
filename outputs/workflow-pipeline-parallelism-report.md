# Workflow pipeline parallelism proof

## Verdict: REGRESSION

The proposed five-worker supervisor completed the same local durable workflow
graph with matching output and attempt digests, passing quality status, and no
provider cost. It was slower than the serial supervisor at every measured batch
size, so the production change was reverted.

| Reports | Serial median | Five-worker median | Change |
| --- | ---: | ---: | ---: |
| 1 | 2,065 ms | 3,264 ms | 58.1% slower |
| 5 | 6,098 ms | 9,536 ms | 56.4% slower |
| 10 | 11,087 ms | 12,629 ms | 13.9% slower |

The run used two warmups and seven samples per profile with a deterministic
20 ms local stage workload. It exercised actual SQLite queue claims, leases,
completion, outbox materialisation, child submissions, and typed stage
handlers. Every compared result had the same terminal graph, output digest,
semantic parent-stage lineage, one attempt per job, passing quality result, and
zero provider cost.

The benchmark harness and scheduler were discarded together because the
candidate regressed. The raw matrix artifact is retained at
`outputs/workflow-pipeline-parallelism.json` as the evidence for this rejected
experiment; it is not a repeatable benchmark against the reverted source.
