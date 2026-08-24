# Final Engineering Review finding contract

Each reviewer returns JSON-compatible objects only. A finding is eligible for
parent synthesis only when all required fields are present.

```json
{
  "reviewer": "correctness",
  "title": "Short concrete defect",
  "severity": "high",
  "confidence": 90,
  "introduced_status": "introduced",
  "evidence": [
    {
      "path": "repository-relative-path",
      "line": 42,
      "change_evidence": "What the changed code does"
    }
  ],
  "impact": "Observable bad result",
  "basis": "Reproduction, contract, policy rule, or missing behavioral proof"
}
```

`reviewer` is exactly `correctness`, `architecture_simplicity`, or
`regression_testing`. `introduced_status` is `introduced`, `pre_existing`, or
`uncertain`. Confidence is an integer from 0 through 100. The parent reports
only introduced findings with confidence at least 85.

Evidence must identify a current repository-relative file and line in the
review snapshot. `change_evidence` explains why the issue is in the submitted
diff rather than merely nearby code. `impact` and `basis` must be specific
enough for the parent to independently verify. Style preferences, possible
future cleanup, generic caution, and findings without a concrete consequence
are invalid.

For a controlled historical benchmark run, the evaluator—not the reviewer—may
record a reduced finding object:

```json
{
  "schema_version": "1.0",
  "findings": [
    {
      "case_id": "FER-COR-001",
      "finding_id": "bounded-no-progress-polling",
      "confidence": 90,
      "introduced_status": "introduced",
      "evidence_paths": ["src/services/example.py"]
    }
  ]
}
```

The scorer counts a useful bug only once when its case ID, accepted finding ID,
confidence, introduced status, and required evidence path all match. Any other
high-confidence introduced finding is a false positive. Low-confidence,
pre-existing, and uncertain reports are recorded as suppressed rather than
counted as useful.
