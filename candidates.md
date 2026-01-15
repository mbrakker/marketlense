Below is a thorough, implementation-aware answer grounded in the current pipeline so you can see exactly where to tighten candidate search for “best data figure” selection (especially for LinkedIn visuals) while minimizing mistakes like single-row tables or partial infographic crops.

---

## Current Pipeline (What the code does today)

1. **Candidate extraction (charts + tables):**
   * **Charts** are discovered only via embedded PDF images, filtered by bounding-box size/shape and a nearby caption check (e.g., “figure”, “chart”, “graph”, etc.). This means *vector charts* or shapes drawn as PDF paths are **not** captured. The metadata stored for charts is fairly light (area fraction and aspect ratio).【F:src/services/candidate_extraction_service.py†L17-L116】
   * **Tables** are extracted with pdfplumber’s line-based table detection and only a **3-row preview** is captured. There is no minimum row/column requirement or data-density scoring at extraction time.【F:src/services/candidate_extraction_service.py†L119-L173】

2. **Ranking candidates (LLM):**
   * The ranker receives a compact JSON payload per candidate: id, type, page, meta, caption, and a short table preview. There’s no explicit signal for “single row table”, “tiny crop”, “graphic fragment”, or “multi-panel infographic.”【F:src/generators/report_generator.py†L477-L486】
   * The prompt is very lightweight: “select most interesting charts/tables … percentages, deltas, KPIs.” It doesn’t enforce minimum data density, multi-row requirement, or avoid fragments.【F:src/prompts/rank_candidates/user.yaml†L1-L8】

3. **Final figure selection:**
   * Only **top 3 ranked** candidates are cropped and used to fill the figure gallery; the top ranked item becomes the primary LinkedIn image figure metadata and evidence.【F:src/generators/report_generator.py†L587-L623】

---

## Improvements: What to change and why (to reduce visual mistakes)

### 1) **Extraction: Capture more *complete* and *data-rich* candidates**

**A. Add table validity + richness checks before ranking**
* Right now tables can be tiny or 1-row and still get extracted. Add filters like:
  * `min_rows >= 2` and `min_cols >= 2`
  * cell text density or numeric density thresholds
  * drop tables with mostly empty cells  
This would prevent “single row table” candidates from ever reaching ranking.【F:src/services/candidate_extraction_service.py†L119-L173】

**B. Include richer table metadata**
* Extract and store:
  * `rows`, `cols`
  * % of numeric cells (to emphasize data-driven tables)
  * total character count  
Then pass these into the ranker. Right now only `rows_peek` (0–3) is retained, which isn’t strong enough for quality filtering.【F:src/services/candidate_extraction_service.py†L147-L171】【F:src/generators/report_generator.py†L477-L486】

**C. Add vector-graphic detection**
* `_extract_charts` only uses `page.get_images()`, so vector charts (common in PDFs) can be missed entirely. Incorporate `page.get_drawings()` or rasterize page segments around detected “Figure/Exhibit” text anchors to catch vector-only graphics.【F:src/services/candidate_extraction_service.py†L59-L116】

---

### 2) **Ranking: Make the model understand “visual + data-dense + complete”**

**A. Expand candidate JSON to include quality signals**
* Add fields such as:
  * chart/table area fraction
  * aspect ratio
  * row/col count
  * numeric density
  * caption length / presence
  * proximity to “Figure X” text blocks  
These are already partially calculated but not exposed to ranking (only `meta` and limited preview are passed).【F:src/services/candidate_extraction_service.py†L89-L115】【F:src/generators/report_generator.py†L477-L486】

**B. Update the ranking prompt to penalize weak visuals**
* Prompt should explicitly *down-rank*:
  * single-row tables
  * fragments of multi-panel infographics
  * tiny or low-data graphics  
Your current prompt is too high-level to enforce these constraints.【F:src/prompts/rank_candidates/user.yaml†L1-L8】

---

### 3) **Post-ranking validation: Verify the crop is “LinkedIn-ready”**

**A. Add a crop-quality check**
* After cropping, verify:
  * image pixel dimensions (avoid tiny crops)
  * OCR/number density (ensure data-driven)
  * detect if crop is too “sparse” (e.g., blank white with a logo)  
Right now the pipeline simply accepts the top crop and uses it as the featured figure without a quality gate.【F:src/generators/report_generator.py†L587-L623】

**B. Fallback logic**
* If the top candidate fails quality checks, automatically fall back to the next ranked candidate(s). This is the simplest way to avoid “bad top image” for LinkedIn posts.【F:src/generators/report_generator.py†L587-L623】

---

### 4) **Handle diverse report styles (infographics, dashboards, “figure blocks”)**

**A. Wider detection for “figure blocks”**
* The caption checks currently depend on nearby text with keywords. Infographics often embed labels inside the graphic, not in adjacent text blocks. If possible:
  * add OCR on candidate crops
  * search for digit density inside the crop
  * use layout analysis to detect multi-panel figures  
This will reduce missing “best infographic” candidates that don’t use standard captions.【F:src/services/candidate_extraction_service.py†L41-L116】

**B. Scale capture for multi-panel infographics**
* If a “figure block” is composed of multiple adjacent images or vector segments, current extraction will likely capture only one panel. Group nearby image regions into a single candidate to avoid partial screenshots (e.g., cluster images within a small distance in the same page).【F:src/services/candidate_extraction_service.py†L59-L116】

---

## Concrete “Next Steps” Roadmap (aligned with current architecture)

1. **Extraction Phase**
   * Add row/col counts + numeric density for tables, and hard filter 1-row or low-density tables.【F:src/services/candidate_extraction_service.py†L119-L173】
   * Add vector/graphic capture for non-image charts (drawings or figure-anchor rasterization).【F:src/services/candidate_extraction_service.py†L59-L116】

2. **Ranking Phase**
   * Pass new metadata to `candidates_json` for ranking.【F:src/generators/report_generator.py†L477-L486】
   * Update `rank_candidates` prompt to explicitly penalize single-row tables / tiny fragments / low-data visuals.【F:src/prompts/rank_candidates/user.yaml†L1-L8】

3. **Post-Ranking Validation**
   * Add a “crop QA” step before selecting top figure for LinkedIn output.【F:src/generators/report_generator.py†L587-L623】
