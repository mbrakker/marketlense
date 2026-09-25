# Prompt 1 closure replay evidence — 2026-09-25

The first four fresh, isolated production-path attempts ran on implementation SHA `54745e9b19c93469f6a422df387cb842462c3fc0` (base `ebd6f3caa241344b26c5004fe78e5d817055a107`). The replay used the isolated `prompt1-closure` candidate commit. The evidence commits were pushed after the user explicitly requested it; no report was published. Each source hash matched the frozen A21 manifest. The runner used canonical queue and supervisor orchestration with fresh state per source.

## Outcomes

| Publisher | Source identity | Terminal outcome | Validation | Publish readiness | Retained claim assertion | Repairs | Calls | Input / output tokens | Cost |
|---|---|---|---|---|---|---:|---:|---:|---:|
| KPMG | `source:1ffb71d718276f8a1761fc706a2a3cb3` | `awaiting_review` | pass | pass | pass | 1 model repair event(s) | 32 | 291,196 / 39,543 | $0.048892 |
| Adjust | `source:8cb648b6bbd9dbae4ec1d915c38cf235` | `failed` | fail | fail | pass | 4 model repair event(s) | 40 | 371,154 / 60,314 | $0.066703 |
| Algolia | `source:4ea9ae5709898e763efb0945d8d4fa1e` | `awaiting_review` | pass | pass | pass | 2 model repair event(s) | 36 | 304,529 / 38,200 | $0.049270 |
| Criteo | `source:81027fd399837b2cbd3cefa2abca222b` | `failed` | fail | fail | not_executable_canonical_artifacts_missing | 1 model repair event(s) | 20 | 194,131 / 39,945 | $0.039386 |


KPMG and Algolia reached `awaiting_review`; both validation and publish readiness passed, and both retained-claim assertions passed. Adjust and Criteo did not meet the requested terminal outcome. The four attempts total **128 provider calls**, **1,161,010 input tokens**, **178,002 output tokens**, and **$0.204251**. There were no operator interventions. Automatic repair activity is recorded per source in the JSON evidence.

## CI verification

On the first candidate SHA, the render ownership plus A21 lineage suites passed (**50 passed**), including the three named A21 fixtures. The regeneration/finalisation/provenance regression suite passed (**76 passed**), including the prior 19 soft-copy/regeneration provenance regressions. The full local suite against that implementation tree reached 5,972 passed, 1 skipped, and 24 subtests passed, with four Windows-specific path/timing failures. That candidate did not have a green full CI run; the later green SHA is recorded below.

## Full GitHub CI result

GitHub CI run [36104257693](https://github.com/mbrakker/marketlense/actions/runs/36104257693) on evidence commit `0670dcedda9ba2fa6cc2a8d77db2148271e9fa6b` failed in the default pytest suite: **5,976 passed, 1 failed**. The remaining failure is the `clean` A21 full-chain case: eventual success was true and operator intervention was false, but the retained reliability entity reported `first_pass=False`. The log also contains a pypdf warning about malformed numeric token `0.00-6165227` being replaced with `0.0`. A focused Linux xdist run of the A21 module passed all four tests, so the full-suite-only cause remains under investigation.

GitHub CI run [36105838744](https://github.com/mbrakker/marketlense/actions/runs/36105838744) on diagnostic commit `b761061ff07227f4909edd33bb2818fb06e29ea8` passed static checks, the full pytest suite, coverage, and mutation execution, but failed the quality non-regression comparison: `artifact_generator.py` scored 66.7% against its 100% baseline. The surviving `Or->And` mutant was at the findings-pack type guard in `_summary_prioritized_evidence_json`. Its split module's explicit `__all__` also omitted the existing summary-evidence ordering test from the pytest facade. I added a malformed findings-pack behavior test and exported both summary-evidence tests; the focused suite now collects 79 tests and kills all three selected artifact-generator mutants (100%). The correction is recorded and verified in the subsequent full CI run below.

The correction was committed as `0144111c8ef43f2ccc74e4fdaa1c00754ff591c4`. Full CI run [36108473460](https://github.com/mbrakker/marketlense/actions/runs/36108473460) passed on that exact SHA, including **5,979 passed** in the default pytest suite and the quality regression gate. CodeQL run [36108472385](https://github.com/mbrakker/marketlense/actions/runs/36108472385) also passed. The only skipped CI step was the credential-gated WordPress staging REST check.

## Fresh production-path replay on the green SHA

On exact green SHA `0144111c8ef43f2ccc74e4fdaa1c00754ff591c4`, four fresh isolated first attempts used the frozen manifest and canonical production queue/supervisor path. Each source hash matched the manifest; no publication or operator intervention occurred. KPMG, Adjust, and Algolia reached `awaiting_review` with validation, publish readiness, and `assert_retained_soft_copy_claims_match_public_copy()` passing. Criteo terminated with `card_tldr_compact_invalid` before canonical `artifacts.json` was persisted, so its retained-copy assertion could not execute. Its failure diagnostic identifies `summary.card_tldr_compact`; the existing contract requires a complete sentence of 1–18 words. No repair call or rerun followed. Ten pypdf malformed-object warnings were retained for Criteo.

| Publisher | Source identity | Outcome | Validation / readiness | Retained-copy assertion | Calls | Input / output tokens | Cost | Repair provider calls |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | --- |
| KPMG | `source:1ffb71d718276f8a1761fc706a2a3cb3` | `awaiting_review` | pass / pass | pass | 31 | 282,124 / 37,233 | $0.046829 | 1 `validation_grounding_model_repair` |
| Adjust | `source:8cb648b6bbd9dbae4ec1d915c38cf235` | `awaiting_review` | pass / pass | pass | 33 | 295,165 / 48,083 | $0.053274 | 2 `validation_grounding_model_repair` |
| Algolia | `source:4ea9ae5709898e763efb0945d8d4fa1e` | `awaiting_review` | pass / pass | pass | 35 | 307,092 / 46,030 | $0.053439 | 2 `validation_grounding_model_repair` |
| Criteo | `source:81027fd399837b2cbd3cefa2abca222b` | `failed` (`card_tldr_compact_invalid`) | fail / fail | not executable: canonical artifacts missing | 20 | 162,423 / 39,368 | $0.035924 | 0 |

The round totals **119 provider calls**, **1,046,804 input tokens**, **170,714 output tokens**, **$0.189466**, and **1,489.969 seconds**. Both named soft-copy provenance error codes had zero retained JSON occurrences and zero usage-ledger error rows. The full scalar record, including source hashes, run references, diagnostics, repairs, and per-report metrics, is retained in [`prompt1-closure-replay-round-0144111c.json`](prompt1-closure-replay-round-0144111c.json).

## Diagnosed replay failures

- **Adjust:** one bounded targeted repair was attempted. Semantic validation ended `validation_failed`: the `numbers` rule rejected unsupported numeric claim `1016.8` in `expert_comment`; retained `validation.json` had no evidence IDs. The retained soft-copy provenance assertion passed. Publish readiness failed as a consequence.
- **Criteo:** report analysis ended `card_tldr_compact_invalid`; `summary.card_tldr_compact` did not satisfy the existing complete-sentence, 1-to-18-word contract. The canonical `artifacts.json` was never retained, so the retained-claim assertion could not execute. Publish readiness failed as a consequence. The source parser also emitted 10 repeated malformed-object warnings (`Ignoring wrong pointing object 9 0 (offset 0)`), while ingestion continued.

The initial-round failures were neither suppressed nor manually repaired. Each later green-SHA replay was a new isolated first attempt, not a retry within its original run: Adjust then passed, while Criteo failed again at compact-TLDR validation. The evidence retains exact source paths and MD5/SHA-256 identities, source identity IDs, one-attempt outcomes, failure codes, repair events, usage, cost, and isolated run references. It contains no prompts or raw provider responses.

## Acceptance status

The Prompt 1 acceptance criteria remain **not met**. Full CI is green on `0144111c`, and three of four same-SHA replays passed validation, publish readiness, and the retained-copy assertion. Criteo remains a genuine downstream artifact-generation failure: the compact TLDR contract failed before canonical artifacts were persisted. No provenance errors were observed. The failure was retained rather than retried or suppressed. A21 TODO evidence was not refreshed because the four-report criteria did not pass; A21 remains active and E13 status was not changed.

Detailed scalar results: [`prompt1-closure-replays-20260925.json`](prompt1-closure-replays-20260925.json).
