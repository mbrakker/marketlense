---
name: llm-change-eval
description: Verify MarketLense prompts, model routing, structured schemas, or LLM pipeline changes; not for deterministic PDF or browser-only work.
---

# LLM change evaluation

Use after changing `src/prompts`, prompt rendering/materialization, model
policy, provider adapters, output schemas, or LLM retry/accounting behavior.

## Entry points and invariants

- `src/services/prompt_service.py` owns prompt loading, rendering, hashing, and
  validation; prompt resources stay under `src/prompts/`.
- `src/services/llm_service.py` is the canonical provider boundary; routing is
  operator configuration, while output schemas and safety checks remain code.
- Preserve schema validation, grounding/provenance, bounded retry ownership,
  redacted audit metadata, and deterministic validation without credentials.

## Inspect and verify

Read the changed prompt namespace, contract in `src/contracts/prompts.py` or
the relevant LLM contract, policy/configuration, and the behavioral fixture.
Run only the relevant focused checks:

```powershell
python -m pytest -q tests/test_prompt_service.py tests/test_prompt_dry_run_validation.py
python -m pytest -q tests/test_llm_service.py tests/test_llm_routing_policy.py
python -m pytest -q tests/test_prompt_fixture_corpus_regression.py
python scripts/ci/check_prompt_fixture_regression.py --baseline docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json --config src/config/app.yaml --iterations 3
```

Use a marked, bounded live canary only for provider compatibility that fixtures
cannot prove. Record prompt namespace/hash, schema and grounding result, model
metadata, token/cost availability, and skipped live checks. Completion requires
the matching fixture evidence and the normal completion-gate result.
