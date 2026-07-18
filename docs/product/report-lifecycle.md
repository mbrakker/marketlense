# Report Lifecycle

> **Documentation type:** Current reference
> **Canonical topic:** Report lifecycle
> **Update trigger:** Acquisition, processing, validation, or publication flow changes.

```text
Source discovery -> acquisition -> queue handoff -> ingest -> selection -> analysis -> render -> projection -> review -> publication
                       |                                      |
                       +-> retained state, checkpoints, and lineage <-+
```

1. Discovery, acquisition, mailbox delivery, and ingest are durable logical queues.
2. A verified acquired artifact creates deterministic governed ingest work; mailbox delivery retains its own request/watermark state.
3. Report work is handed off at `source_prepared`, `selection_complete`, `analysis_complete`, and `render_complete` checkpoints.
4. Rendering fans out independently to analytics projection, covers, and publication readiness.
5. Publication remains an immutable package readiness decision followed by human approval and asynchronous WordPress work.

The state and reports databases retain workflow state, checkpoints, artifact lineage, and operational observations. A resume request is accepted only when the retained checkpoint and lineage are usable. Detailed stage behavior is in [workflows](../workflows/report-processing.md); queue lifecycle and operations are in [asynchronous workflow queue](../architecture/asynchronous-workflow-queue.md); retry and resume ownership is in [workflow control](../architecture/workflow-control.md).
