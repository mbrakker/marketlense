# GPT-5.6 Luna Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route every configured generative LLM call through GPT-5.6 Luna while preserving the separate embedding model and all safety controls.

**Architecture:** The migration is operator configuration only: model identity and pricing keys move together in the canonical application profile, with OpenRouter aliases retained for browser fallbacks.  Existing config loading, execution-policy validation, schema validation, budgets, and retries remain unchanged.  A focused regression test protects the full configured routing inventory.

**Tech Stack:** Python 3, PyYAML, pytest, OpenAI Responses API, OpenRouter.

## Global Constraints

- Use `gpt-5.6-luna` for every configured direct generative OpenAI route and `openai/gpt-5.6-luna` for every OpenRouter generative route.
- Keep `text-embedding-3-small` unchanged because it is an embedding capability, not a generative LLM route.
- Reuse existing rate-card records and configuration service boundaries; add no dependencies or provider adapters.
- Preserve bounded retry ownership, schema validation, grounding validation, budgets, and no-publication live validation safeguards.

---

### Task 1: Prove the complete route inventory before configuration migration

**Files:**
- Create: `tests/test_gpt_5_6_luna_model_migration.py`
- Read: `src/config/app.yaml`, `src/config/llm-costs.yaml`, `src/utils/model_resolver.py`

**Interfaces:**
- Consumes: canonical YAML model fields and `llm_execution_policies` consumed by the existing configuration service.
- Produces: a regression check that fails if a configured generative route is not Luna or if its pricing key cannot govern the route.

- [x] **Step 1: Write the failing test**

```python
def test_canonical_configuration_routes_every_generative_call_to_gpt_5_6_luna() -> None:
    config = yaml.safe_load(APP_CONFIG_PATH.read_text(encoding="utf-8"))
    assert config["ingest"]["openai_model"] == "gpt-5.6-luna"
    assert config["browser_download"]["openrouter_model"] == "openai/gpt-5.6-luna"
    assert all(
        policy["model"] == "gpt-5.6-luna"
        and policy["pricing_key"] == "gpt-5.6-luna"
        for name, policy in config["llm_execution_policies"].items()
        if name != "claim_embedding/generate"
    )
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_gpt_5_6_luna_model_migration.py`

Expected: FAIL because current active models are GPT-5 Mini and GPT-5 Nano.

- [x] **Step 3: Keep the test focused on observable operator routing**

```python
assert config["llm_execution_policies"]["claim_embedding/generate"]["model"] == "text-embedding-3-small"
assert "gpt-5.6-luna" in pricing
assert "openai/gpt-5.6-luna" in pricing
```

- [x] **Step 4: Re-run the targeted test and retain the expected red result**

Run: `python -m pytest -q tests/test_gpt_5_6_luna_model_migration.py`

Expected: FAIL only on pre-migration model identities or missing OpenRouter pricing.

### Task 2: Migrate configuration, document operation, and validate the live provider path

**Files:**
- Modify: `src/config/app.yaml`
- Modify: `src/config/llm-costs.yaml`
- Modify: `src/config/app.example.yaml` when it declares active model defaults
- Modify: `src/contracts/config.py` and service default fallbacks that still name an old generative model
- Modify: `docs/ops/configuration.md`
- Modify: `CONSOLIDATED_TODO.md` only if an active matching migration item exists
- Test: `tests/test_gpt_5_6_luna_model_migration.py`, `tests/test_llm_routing_policy.py`, `tests/test_llm_service.py`, `tests/test_prompt_dry_run_validation.py`

**Interfaces:**
- Consumes: the test from Task 1 and the existing direct/OpenRouter rate cards.
- Produces: a valid canonical configuration where every generative request resolves to Luna and is fully price-governed.

- [x] **Step 1: Apply the minimal configuration and fallback-default changes**

```yaml
model: "gpt-5.6-luna"
pricing_key: "gpt-5.6-luna"
openrouter_model: "openai/gpt-5.6-luna"
```

Add the existing OpenRouter price values as an enabled exact rate-card record, preserving the existing direct OpenAI Luna record. Do not change the embedding policy.

- [x] **Step 2: Run focused configuration, prompt, and provider-unit checks**

Run: `python -m pytest -q tests/test_gpt_5_6_luna_model_migration.py tests/test_llm_routing_policy.py tests/test_llm_service.py tests/test_prompt_dry_run_validation.py`

Expected: PASS with all schemas, policy coverage, and deterministic dry runs valid.

- [x] **Step 3: Run the prompt fixture corpus regression using the existing corpus**

Run: `python scripts/ci/check_prompt_fixture_regression.py --baseline docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json --config src/config/app.yaml --iterations 3`

Expected: PASS without changing or synthesizing fixtures.

- [x] **Step 4: Run bounded live validation with external publication disabled**

Run: existing live OpenAI smoke, direct and OpenRouter browser/provider canaries, and the repository’s approved isolated discovery → acquisition → ingest → publish validation profile using retained project artifacts only.

Expected: real provider requests identify GPT-5.6 Luna, schema and grounding gates pass, and publish reaches its normal no-write gate.

- [x] **Step 5: Record the current configuration behavior**

Document that all generative routes resolve to Luna and that embeddings remain on their dedicated model; include direct and OpenRouter rate-card keys and the live-validation command/profile.

- [x] **Step 6: Inspect the final scoped diff, remove only an exact completed backlog item, commit, and merge**

Run: `git diff --check`; inspect `git diff --check`, `git diff --cached`, `git status --short`, and the affected test outputs before committing. Commit the scoped result to the user-authorized `main` branch; no merge commit is needed when the checkout is already `main`.
