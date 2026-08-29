# DocMap-Guided Final Insights Implementation Plan

> **For agentic workers:** Execute each checked task in order with a failing focused test before production code.

**Goal:** Select a compact, evidence-grounded final-insight set whose size and thematic coverage scale with the report's supported DocMap breadth rather than an unconditional five-item bundle.

**Architecture:** Keep the existing artifact-generator boundary, model calls, schemas, and chart/table paths. Add a deterministic selector in `artifact_normalization` that derives a bounded target from substantive DocMap sections and maps candidates to their source sections through retained findings and evidence IDs. The final-insight prompts receive the target and coverage guidance; the deterministic selector remains the enforcement point for distinct-theme coverage, bounded size, and preserved candidate fields.

**Tech Stack:** Python 3.12, dataclass/JSON artifact contracts, Jinja prompt resources, pytest.

## Global constraints

- Do not alter chart or table generation, selection, rendering, or validation paths.
- Preserve existing insight records and their evidence IDs, scores, `so_what`, `now_what`, metrics, pages, and grounding validation.
- Keep final output bounded at two to seven grounded insights; do not add model calls or configuration.
- Retain explicit abstention/failure for unsupported or insufficiently grounded insight sets.

---

### Task 1: Specify DocMap-breadth selection with tests

**Files:**

- Modify: `tests/_test_artifact_generator/cases_01_validates_schema_and_evidence_ids.py`
- Modify: `tests/_test_artifact_generator/cases_02_assemble_artifacts_logs_topic_brief.py`
- Modify: `src/generators/artifact_normalization.py`

**Interfaces:**

- Consumes: normalized final candidates, normalized candidate insights, DocMap, and findings pack.
- Produces: `select_artifact_insights(...) -> list[dict[str, object]]`, retaining each selected record's existing fields.

- [ ] **Step 1: Write failing focused tests**

```python
def test_select_artifact_insights_keeps_representative_sections_for_a_broad_doc_map():
    selected = select_artifact_insights(
        final_insights=[high_score_same_section, another_same_section],
        candidate_insights=[high_score_same_section, another_same_section, growth, risk, operations, investment],
        doc_map=broad_doc_map(), evidence_packs=section_linked_findings(),
    )
    assert [item["evidence_id"] for item in selected] == ["growth", "risk", "operations", "investment"]
    assert len(selected) <= 7


def test_select_artifact_insights_keeps_a_narrow_doc_map_compact():
    selected = select_artifact_insights(
        final_insights=narrow_candidates(), candidate_insights=narrow_candidates(),
        doc_map=narrow_doc_map(), evidence_packs=section_linked_findings(),
    )
    assert 2 <= len(selected) <= 3
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `python -m pytest -q tests/test_artifact_generator.py -k "representative_sections or narrow_doc_map_compact"`

Expected: fail because the selector does not yet exist and final insights are padded to five records.

- [ ] **Step 3: Implement the minimum deterministic selector**

```python
def select_artifact_insights(*, final_insights, candidate_insights, doc_map, evidence_packs):
    target = artifact_insight_target_count(doc_map)
    ranked = _dedupe_preserving_fields([*final_insights, *candidate_insights])
    return _select_representative_themes(ranked, target, doc_map, evidence_packs)
```

Derive a section/theme key first from a matching finding's `section_id`, then from a DocMap evidence/section ID or overlapping source page, and finally from a supplied `coverage_role`. Choose one strongest candidate per available theme before considering another item from that theme; preserve model-final ordering as a tie-breaker and score only within comparable coverage choices. Require two non-empty grounded insights for the family to remain generated; cap broad reports at seven and compact narrow reports at three.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `python -m pytest -q tests/test_artifact_generator.py -k "representative_sections or narrow_doc_map_compact"`

Expected: pass; broad input keeps distinct DocMap themes and narrow input returns a compact set.

### Task 2: Wire final and regeneration selection without fixed-five padding

**Files:**

- Modify: `src/generators/_artifact_generator/generation.py`
- Modify: `src/generators/report_regeneration_generator.py`
- Modify: `src/generators/_artifact_generator/storage.py`
- Modify: `src/generators/_artifact_generator/family_policy.py`
- Modify: `src/prompts/report_vs/artifacts/insights_final/system.yaml`
- Modify: `src/prompts/report_vs/artifacts/insights_final/user.yaml`
- Modify: `src/prompts/report_vs/artifacts/regenerate/insights_final/system.yaml`
- Modify: `src/prompts/report_vs/artifacts/regenerate/insights_final/user.yaml`

**Interfaces:**

- Consumes: `artifact_insight_target_count(doc_map)` and `select_artifact_insights(...)`.
- Produces: final artifact payloads and regenerated payloads with two to seven selected grounded insights, plus the prompt variable `final_insight_target_count`.

- [ ] **Step 1: Write failing generation-level tests**

```python
def test_generate_artifacts_uses_doc_map_target_and_retains_broad_themes(tmp_path):
    payload = generate_artifacts(..., doc_map=broad_doc_map(), evidence_packs=section_linked_findings(), ...)
    assert 5 < len(payload["insights_final"]) <= 7
    assert len({item["evidence_id"] for item in payload["insights_final"]}) == len(payload["insights_final"])


def test_generate_artifacts_accepts_compact_narrow_final_insights(tmp_path):
    payload = generate_artifacts(..., doc_map=narrow_doc_map(), ...)
    assert 2 <= len(payload["insights_final"]) <= 3
    assert payload["family_status"]["insights_bundle"]["status"] == "generated"
```

- [ ] **Step 2: Run the generation-level tests and verify they fail**

Run: `python -m pytest -q tests/test_artifact_generator.py -k "doc_map_target or compact_narrow_final"`

Expected: fail because generation pads final items and semantic/family validation requires five.

- [ ] **Step 3: Implement the scoped wiring**

Pass the target to both final-insight prompt families. Replace `pad_artifact_insights` calls on the final path with the deterministic selector; retain candidate/finding fallback only as grounded candidate input. Update the semantic and family-policy minimum from five non-empty insights to two without changing JSON schema fields, evidence checks, or the legacy report-card two-insight projection. Update prompts to request the supplied target, explicit DocMap-section coverage, and no padding.

- [ ] **Step 4: Run the generation-level tests and verify they pass**

Run: `python -m pytest -q tests/test_artifact_generator.py -k "doc_map_target or compact_narrow_final"`

Expected: pass with one existing model call per final-insight family and no fabricated filler.

### Task 3: Document and validate the behavior

**Files:**

- Modify: `docs/workflows/report-processing.md`

- [ ] **Step 1: Document the current behavior**

Replace the fixed-five fallback/padding description with the two-to-seven, DocMap-breadth target; document one-per-theme selection before score tie-breaking and continued evidence/abstention safeguards.

- [ ] **Step 2: Run focused and report-generation checks**

Run: `python -m pytest -q tests/test_artifact_generator.py tests/test_report_generation*.py`

Expected: pass.

- [ ] **Step 3: Run the bounded broad report validation**

Run the repository-approved isolated report-generation validation profile with one retained broad report and inspect its `artifacts.json` final insights. Record report identity, final count, distinct DocMap themes/sections, grounding status, and skipped live behavior, if any.

- [ ] **Step 4: Completion gate, commit, and push**

Inspect `git diff --check`, `git diff`, and `git status --short`; run the applicable public editorial checks and full discovery-to-publish safe validation workflow required by repository policy. Commit only the scoped tracked files and push the current branch after all checks pass.
