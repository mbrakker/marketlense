# Prompt 1 closure replay evidence — 2026-09-25

The four fresh, isolated production-path first attempts ran on implementation SHA `54745e9b19c93469f6a422df387cb842462c3fc0` (base `ebd6f3caa241344b26c5004fe78e5d817055a107`). The replay used the isolated `prompt1-closure` candidate commit. Publication followed the later explicit user instruction; replay outcomes below remain unchanged. Each source hash matched the frozen A21 manifest. The runner used canonical queue and supervisor orchestration, fresh state per source, and did not publish.

## Outcomes

| Publisher | Source identity | Terminal outcome | Validation | Publish readiness | Retained claim assertion | Repairs | Calls | Input / output tokens | Cost |
|---|---|---|---|---|---|---:|---:|---:|---:|
| KPMG | `source:1ffb71d718276f8a1761fc706a2a3cb3` | `awaiting_review` | pass | pass | pass | 1 model repair event(s) | 32 | 291,196 / 39,543 | $0.048892 |
| Adjust | `source:8cb648b6bbd9dbae4ec1d915c38cf235` | `failed` | fail | fail | pass | 4 model repair event(s) | 40 | 371,154 / 60,314 | $0.066703 |
| Algolia | `source:4ea9ae5709898e763efb0945d8d4fa1e` | `awaiting_review` | pass | pass | pass | 2 model repair event(s) | 36 | 304,529 / 38,200 | $0.049270 |
| Criteo | `source:81027fd399837b2cbd3cefa2abca222b` | `failed` | fail | fail | not_executable_canonical_artifacts_missing | 1 model repair event(s) | 20 | 194,131 / 39,945 | $0.039386 |


KPMG and Algolia reached `awaiting_review`; both validation and publish readiness passed, and both retained-claim assertions passed. Adjust and Criteo did not meet the requested terminal outcome. The four attempts total **128 provider calls**, **1,161,010 input tokens**, **178,002 output tokens**, and **$0.204251**. There were no operator interventions. Automatic repair activity is recorded per source in the JSON evidence.

## CI verification

On the exact candidate SHA, the render ownership plus A21 lineage suites passed (**50 passed**), including the three named A21 fixtures. The regeneration/finalisation/provenance regression suite passed (**76 passed**), including the prior 19 soft-copy/regeneration provenance regressions. The full local suite against the same implementation tree reached 5,972 passed, 1 skipped, and 24 subtests passed, with four Windows-specific path/timing failures; full CI has not been certified green on this candidate SHA.

## Diagnosed failures

- **Adjust:** one bounded targeted repair was attempted. Semantic validation ended `validation_failed`: the `numbers` rule rejected unsupported numeric claim `1016.8` in `expert_comment`; retained `validation.json` had no evidence IDs. The retained soft-copy provenance assertion passed. Publish readiness failed as a consequence.
- **Criteo:** report analysis ended `card_tldr_compact_invalid`; `summary.card_tldr_compact` did not satisfy the existing complete-sentence, 1-to-18-word contract. The canonical `artifacts.json` was never retained, so the retained-claim assertion could not execute. Publish readiness failed as a consequence. The source parser also emitted 10 repeated malformed-object warnings (`Ignoring wrong pointing object 9 0 (offset 0)`), while ingestion continued.

Neither failure was suppressed, manually repaired, or rerun. The results JSON retains exact source paths and MD5/SHA-256 identities, source identity IDs, one-attempt outcomes, failure codes, repair events, usage, cost, and isolated run references. It contains no prompts or raw provider responses.

## Acceptance status

The Prompt 1 replay acceptance criteria are **not met**: only two of four reports reached `awaiting_review`, and only three reports had canonical artifacts on which the retained-claim assertion could run. The observed workflow error codes contain no `soft_copy_claim_provenance_bindings_incomplete` or `soft_copy_claim_provenance_coverage_invalid` errors. This record does not certify full CI on the candidate SHA; CI was not run before the explicit publication instruction, and the two genuine downstream failures remain visible. A21 TODO evidence was therefore not refreshed and A21 remains active. E13 status was not changed.

Detailed scalar results: [`prompt1-closure-replays-20260925.json`](prompt1-closure-replays-20260925.json).
