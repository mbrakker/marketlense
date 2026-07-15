# Report Lifecycle

> **Documentation type:** Current reference
> **Canonical topic:** Report lifecycle
> **Update trigger:** Acquisition, processing, validation, or publication flow changes.

```text
Source discovery -> acquisition -> ingest -> analysis -> validation -> render -> publication
                       |                                      |
                       +-> retained state, checkpoints, and lineage <-+
```

1. Discovery records report candidates and publisher context.
2. Acquisition obtains a PDF, delayed mailbox delivery, or permitted on-site report capture.
3. Ingest validates source material, extracts text and visual candidates, and invokes the report pipeline.
4. Analysis produces schema-validated evidence packs and editorial artifacts.
5. Validation blocks or targets regeneration according to configured policy.
6. Rendering produces the report HTML and associated assets.
7. Publication sends approved artifacts and projections through the WordPress boundary.

The state and reports databases retain workflow state, checkpoints, artifact lineage, and operational observations. A resume request is accepted only when the retained checkpoint and lineage are usable. Detailed stage behavior is in [workflows](../workflows/report-processing.md); retry and resume ownership is in [workflow control](../architecture/workflow-control.md).
