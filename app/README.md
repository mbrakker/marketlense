# pdf_to_html

Small utility to convert a single PDF to HTML using Marker (marker-pdf) with LLM (OpenAI) enabled.

Installation

1. Install package dependencies and Marker:

```bash
pip install -r requirements.txt
pip install marker-pdf
```

2. Ensure you have an OpenAI API key available as an environment variable:

Linux / macOS:

```bash
export OPENAI_API_KEY=sk-...
```

app package

This README documents the `app` package, how to run it, required environment variables, and a short description of each module.

Overview

Market Lense ingests PDFs from a Google Drive folder, extracts text & candidate tables/charts, sends text to an LLM (OpenAI) for structured analysis, ranks and crops interesting figures/tables, and renders a compact HTML digest per PDF.

Quick start

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Set required environment variables (example names used by `app.config`):

- GOOGLE_SERVICE_ACCOUNT_JSON — path to service account JSON for Google Drive access
- GDRIVE_FOLDER_ID — Drive folder to scan for PDFs
- OPENAI_API_KEY — OpenAI API key
- (optional) OPENAI_MODEL, BATCH_LIMIT, OUTPUT_DIR, CACHE_DIR, STATE_DB, TEMPERATURE

3. Run the CLI to ingest PDFs:

```bash
python -m app.cli --limit 10
```

Module reference

Below is a concise description of each top-level module and the primary functions it provides.

- app/cli.py — Command-line entrypoint. Implements the `ingest` command that orchestrates the full pipeline (download, analyze, extract figures/tables, rank, crop, render, and record state). Uses `typer` and rich for console output.

- app/config.py — Loads runtime settings from environment variables (via dotenv). Provides `load_settings()` which returns a frozen `Settings` dataclass.

- app/drive.py — Google Drive helpers: `drive_client()` to create an authenticated Drive client, `list_pdfs()` to iterate PDFs in a folder, `ensure_download()` to download into cache preserving names, and `effective_md5()` / `md5_for_file()` utilities.

- app/openai_client.py — Wraps calling the OpenAI Chat API. `analyze_pdf()` extracts text from the first pages and requests a strict JSON analysis per an internal schema.

- app/normalize.py — `normalize_report_payload()` coerces the model JSON into the expected shape so templates and downstream steps do not crash.

- app/preview.py — Renders the first page of a PDF to a PNG for use as a preview image: `first_page_png()` returns a path relative to the output HTML.

- app/figure.py — Heuristics to pick a single representative figure from a PDF. `extract_best_figure_png()` returns a relative PNG path and inferred caption.

- app/extract.py — Finds candidate charts and tables in a PDF. `collect_candidates()` returns a list of `Candidate` objects built from `extract_charts()` and `extract_tables()`.

- app/candidates.py — Data class `Candidate` describing a table/chart candidate (id, kind, page, bbox, preview_text, etc.) and `to_public()` helper.

- app/rank.py — Uses the LLM to rank candidate regions by interest/insightfulness. Main function: `rank_candidates_text_only()` which returns a list of scored objects.

- app/crop.py — `crop_regions()` crops the top candidate regions to PNG slices stored under the HTML output directory (slices/).

- app/render.py — Jinja2 rendering helpers: `jinja_env()` and `render_html()` which writes final HTML files into the configured output directory using templates/report.html.j2.

- app/state.py — Lightweight SQLite-backed state: `State` records processed Drive file IDs, MD5s, timestamps and optional OpenAI file IDs to avoid reprocessing.

- app/logging_config.py — `setup_logging()` configures Rich-formatted logging for the package.

- app/util.py — Small utilities: `slugify()` for filenames and a retry decorator `retry()`.

PDF-to-HTML helper (optional)

The subpackage app/pdf_to_html provides a small utility to run Marker (marker-pdf) with LLM support when you need a direct PDF→HTML converter. Use:

```bash
python -m app.pdf_to_html.convert path/to/report.pdf --output-dir ./out
```

Notes

- Output is written to OUTPUT_DIR (default ./out); images are placed in out/assets and crops in out/slices so the rendered HTML can reference them relatively.
- The system expects `marker_single` on PATH only if you use the pdf_to_html.convert utility.
- Keep secrets out of source; prefer environment variables or a .env file.

If you'd like, I can also expand any module's documentation, add docstrings, or generate a top-level CONTRIBUTING.md with run/test steps.
