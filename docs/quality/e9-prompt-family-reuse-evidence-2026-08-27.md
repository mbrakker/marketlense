# E9 Prompt-Family Reuse Evidence — 2026-08-27

> **Evidence type:** bounded retained-corpus/live report-generation measurement
> **Scope:** report analysis and rendering only; no publication action was invoked.

This record captures the controlled retained-corpus measurement used for E9.
It contains only scalar accounting data and opaque runtime identifiers; the
canonical, per-call evidence remains in the isolated usage ledger at
`state/p12_p14_canary_20260826/llm_usage.sqlite`.

## Case

- Retained source: `1zt4RcZ-7dFNtf9zVWK2kUMpqJMSouUGn`
- Source content identity: `8ef1021c332aa85ba008da58ff8ec866`
- Isolated profile: `p12_p14_canary_20260826`
- Baseline run: `8c48cb67-7851-4bc1-b533-787e168b8eea`
- Retained replay: `6995d91a-8140-4713-85ef-75d89859fa69`

The baseline was a complete report-generation pass. The replay had the same
source and effective model/prompt inputs. It retained valid extraction,
taxonomy, evidence, category-fit, and cover-semantics families, then entered
the existing minimum-regeneration flow because the retained editorial/validation
output did not satisfy the unchanged quality gates. This is a required repair,
not a cache miss treated as a hit.

| Metric | Baseline | Retained replay | Change |
| --- | ---: | ---: | ---: |
| Model calls | 17 | 8 | -9 (52.9%) |
| Input tokens | 131,302 | 69,998 | -61,304 (46.7%) |
| Output tokens | 14,837 | 8,142 | -6,695 (45.1%) |
| Estimated cost | $0.044064 | $0.023770 | -$0.020294 (46.1%) |
| Provider-call span | 90.3 s | 59.4 s | -30.9 s (34.2%) |
| Families regenerated | 17 | 8 | -9 |

The replay avoided calls for `taxonomy`, `doc_map`, five evidence packs,
`context_category_fit`, and `cover_semantics`. It regenerated only the six
editorial families marked by the existing recovery plan plus the two validation
families. The ledger has complete provider/model, prompt namespace, token, cost,
and execution-time attribution for all actual calls.

The same corpus was also run through the fresh-primary and subsequent-repair
paths. Its model output continued to trip the existing editorial/grounding
gates, so it is intentionally not presented as a zero-call compatible replay.
That behavior demonstrates fail-closed retention: an output that has not passed
the unchanged gates is never reused merely to reduce spend. Deterministic
focused tests cover the stable compatible replay and successful-regeneration
convergence cases.
