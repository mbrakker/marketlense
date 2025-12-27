Purpose
-------
Short, actionable guidance for AI coding agents working on this repo so they can be productive immediately.

High-level architecture (big picture)
-------------------------------------
- The CLI orchestrator is [../app/cli.py](../app/cli.py) — it implements the `ingest` flow which: list PDFs from Google Drive → download → compute md5 → LLM analysis → extract figures/tables → rank → crop → render HTML → record state.
- Key modules and responsibilities:
  - [../app/drive.py](../app/drive.py) — Google Drive access + safe download and checksum logic.
  - [../app/openai_client.py](../app/openai_client.py) — extracts first ~5 pages of text, calls OpenAI Chat Completions in JSON mode, and validates the strict JSON schema.
  - [../app/extract.py](../app/extract.py), [../app/figure.py](../app/figure.py), [../app/candidates.py](../app/candidates.py) — locate candidate charts/tables and build `Candidate` objects.
  - [../app/rank.py](../app/rank.py) — uses LLM to rank candidates; saves raw model outputs to `debug/` when requested.
  - [../app/crop.py](../app/crop.py) and [../app/preview.py](../app/preview.py) — create PNG assets used by the templates.
  - [../app/render.py](../app/render.py) and [../templates/report.html.j2](../templates/report.html.j2) — Jinja2 rendering; paths are written to `OUTPUT_DIR`.
  - [../app/state.py](../app/state.py) — SQLite state to avoid re-processing (file_id + md5).

Project-specific conventions and patterns
--------------------------------------
- Many image/path helpers return paths relative to the final HTML output root — example: `first_page_png()` returns `assets/<file>.png` and `crop_regions()` returns `slices/<id>.png`. Templates expect these relative paths.
- Functions that work with PDFs accept an optional `doc` parameter (a `fitz.Document`) so callers can open the file once and pass `doc=doc` to avoid repeated I/O. See [../app/cli.py](../app/cli.py) for the pattern used across `extract_best_figure_png(..., doc=doc)`, `collect_candidates(..., doc=doc)`, and `crop_regions(..., doc=doc)`.
- LLM output is treated defensively:
  - [../app/openai_client.py](../app/openai_client.py) requests JSON mode and validates schema server-side; [../app/normalize.py](../app/normalize.py) coerces missing/ill-typed fields into safe defaults.
  - [../app/rank.py](../app/rank.py) defensively accepts either a bare list or an object with `results/data/items` and will write raw responses to `debug/` when `debug_dir` is provided.
- Candidate IDs follow the `chart-<page>-<idx>` or `table-<page>-<idx>` convention and are exposed via `Candidate.to_public()` in [../app/candidates.py](../app/candidates.py).

External integrations & dependencies
----------------------------------
- Google Drive via a service account JSON: `drive_client(sa_path)` in [../app/drive.py](../app/drive.py). Discovery cache is disabled (note `cache_discovery=False`).
- OpenAI SDK usage: code uses `openai.OpenAI` (SDK v2 style) and calls `chat.completions.create(..., response_format={"type":"json_object"})` — maintain that pattern to ensure strict JSON.
- PDF/image libs: `PyMuPDF (fitz)`, `pdfplumber`, and `Pillow` are used heavily; prefer reusing opened `fitz.Document` to reduce memory/IO.

Runtime / developer workflows (how to run & debug)
-----------------------------------------------
- Install deps: `pip install -r requirements.txt` (see [../app/README.md](../app/README.md)).
- Required env vars (loaded via dotenv in [../app/config.py](../app/config.py)):
  - `GOOGLE_SERVICE_ACCOUNT_JSON`, `GDRIVE_FOLDER_ID`, `OPENAI_API_KEY`
  - Optional overrides: `OPENAI_MODEL`, `BATCH_LIMIT`, `OUTPUT_DIR`, `CACHE_DIR`, `STATE_DB`, `TEMPERATURE`.
- Typical run: `python -m app.cli ingest --limit 10` (entrypoint in [../app/cli.py](../app/cli.py)).
- Debugging LLM outputs: `rank_candidates_text_only(..., debug_dir="debug")` will write raw ranking responses to `debug/` named `rank_raw_<ts>.txt`.
- To force re-processing a Drive file, remove or edit the SQLite state in the configured `STATE_DB` (default `./state/index.sqlite`) or remove the row for that `file_id` in [../app/state.py](../app/state.py).

Important gotchas for agents
----------------------------
- Templates expect relative image paths (not absolute) — preserving the relative-return convention is critical for correct links in generated HTML.
- The code assumes drive file metadata may omit `md5Checksum`; `effective_md5()` falls back to local hashing. Tests or fixes touching drive logic should preserve that fallback.
- Prompts in `../app/rank.py` are in Russian; maintain language context if you edit ranking prompts.
- Many heuristics (figure/table selection) are tuned with numeric thresholds (area fraction, aspect ratios). When changing them, include rationale and new tests/visual samples.

Files to inspect for concrete examples
------------------------------------
- CLI orchestration: [../app/cli.py](../app/cli.py)
- OpenAI integration & schema: [../app/openai_client.py](../app/openai_client.py)
- Candidate extraction: [../app/extract.py](../app/extract.py) and [../app/figure.py](../app/figure.py)
- Cropping & preview path conventions: [../app/crop.py](../app/crop.py), [../app/preview.py](../app/preview.py)
- State & dedup: [../app/state.py](../app/state.py)

Next steps / questions
----------------------
- Do you want sample unit tests covering `normalize_report_payload()` and candidate ID shapes? Any other areas to expand in these instructions?
