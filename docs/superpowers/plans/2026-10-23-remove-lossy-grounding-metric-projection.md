# Remove Lossy Grounding Metric Projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure verified semantic grounding receives the complete canonical verified fact and evidence without changing normal-mode grounding or weakening fail-closed validation.

**Architecture:** Keep `grounding_payload()` as the canonical verified-mode assembly boundary. Preserve the existing validated fact object, expose only the fact records referenced by each grounding batch, and leave legacy request construction unchanged. Bump the existing grounding validator/cache identity because the rendered verified input contract changes.

**Tech Stack:** Python, Pydantic/dataclass contracts already used by MarketLense, YAML prompt resources, pytest, Ruff, mypy, and the repository prompt-fixture regression script.

## Global Constraints

- Preserve user-owned dirty changes in `src/generators/artifact_normalization.py` and do not stage or edit them.
- Do not add an LLM call, validator, service, ranking framework, database, or parallel verified-fact representation.
- Do not expand the fixed metric-field list; verified mode must pass the authoritative metric object unchanged.
- Keep source identity, evidence IDs, physical pages, spans, hashes, and fail-closed validation intact.
- Keep normal-mode payloads and prompt inputs unchanged.
- Do not publish or mutate canonical artifacts or WordPress.

## Task 1: Add failing verified-mode regressions first

- [ ] Extend the existing verified-facts validation tests with an unfamiliar nested metric field, composite observations, forecast assumptions, and a conflicting final artifact metric.
- [ ] Assert the verified payload uses the canonical metric object exactly, retains the canonical proposition/evidence identity, and excludes final-only metric data.
- [ ] Add a batch-input assertion that the complete canonical fact is available to the grounding request.
- [ ] Keep an explicit normal-mode assertion that the new verified-only context is absent.
- [ ] Run the focused tests and confirm the new tests fail for the current lossy projection.

## Task 2: Pass the complete canonical fact through verified grounding

- [ ] In `grounding_payload()`, use a deep copy of the validated authoritative metric object only in verified mode; leave the current normal-mode projection untouched.
- [ ] Add the existing validated canonical facts to the internal verified grounding payload, keyed by their existing evidence/fact identity, without trusting artifact metric fields.
- [ ] Update `_grounding_batches()` to include only canonical facts referenced by that batch so unrelated facts are not added to the prompt.
- [ ] Update the verified authority instructions in the existing grounding system prompt to bind each evidence ID to its complete canonical fact, including unknown nested metric fields, proposition, qualifiers, and provenance.
- [ ] Bump the existing grounding validator identity so retained semantic results and caches cannot reuse pre-change inputs; rely on the existing relevant-input hash and prompt hash for the remaining cache identity.

## Task 3: Verify the focused behavior

- [ ] Run the new tests and all affected grounding, verified-fact, evidence-binding, and prompt tests.
- [ ] Run Ruff and mypy on the affected modules.
- [ ] Run the unchanged prompt-fixture regression gate and record namespace token/cost deltas.
- [ ] Inspect retained Criteo and DoubleVerify canonical facts/editorial claims and replay them through the existing provider-free or retained-input workflow where artifacts are available; do not manufacture fixtures or force verdicts.

## Task 4: Document and deliver

- [ ] Update the existing Step 2 quality report with the exact information-loss boundary, before/after payload shape, Criteo/DoubleVerify outcomes, and measured token/cost impact or an explicit measurement limitation.
- [ ] Review the diff for scope and secret exposure, run the required final checks, commit only intended files, and push the branch.
- [ ] Report the commit SHA, hosted CI result, tests, factual outcomes, and remaining blockers without claiming live improvement beyond the evidence collected.

---

## Verification commands

```powershell
pytest -q tests/test_verified_facts_validation_authority.py tests/test_grounding_protected_facts.py tests/test_prompt_dry_run_validation.py
ruff check src/generators/validation/grounding.py src/contracts/claim_validation.py tests/test_verified_facts_validation_authority.py
mypy src/generators/validation/grounding.py src/contracts/claim_validation.py
python scripts/ci/check_prompt_fixture_regression.py --baseline docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json --config src/config/app.yaml --iterations 3
```
