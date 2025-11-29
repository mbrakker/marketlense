# app/cli.py
import typer
from rich.console import Console
from rich.table import Table
from rich import box

from .config import load_settings
from .drive import drive_client, list_pdfs, ensure_download, effective_md5
from .openai_client import analyze_pdf
from .render import jinja_env, render_html
from .state import State
from .preview import first_page_png
from .figure import extract_best_figure_png

from .extract import collect_candidates
from .rank import rank_candidates_text_only
from .crop import crop_regions

from .normalize import normalize_report_payload


app = typer.Typer(add_completion=False, help="PDF → Structured HTML digests")
console = Console()
import logging

logger = logging.getLogger("market_lense.cli")

@app.command("ingest")
def ingest(
    folder: str = typer.Option(None, help="Override Drive folder ID"),
    limit: int = typer.Option(None, help="Max PDFs to process this run"),
):
    console.print("[cyan]Loading settings...[/cyan]")
    logger.info("Loading settings")
    s = load_settings()

    gdrive_folder_id = folder or s.gdrive_folder_id
    max_n = limit if limit is not None else s.batch_limit

    console.print("[cyan]Connecting to Google Drive...[/cyan]")
    logger.info("Connecting to Google Drive")
    drive = drive_client(s.google_sa_path)

    console.print(f"[cyan]Listing PDFs in folder {gdrive_folder_id}...[/cyan]")
    logger.info("Listing PDFs in folder %s", gdrive_folder_id)
    state = State(s.state_db)
    env = jinja_env()

    processed = 0
    table = Table(title="Processed Reports", box=box.SIMPLE_HEAVY)
    table.add_column("File")
    table.add_column("ID")
    table.add_column("MD5")
    table.add_column("HTML")

    for idx, f in enumerate(list_pdfs(drive, gdrive_folder_id), start=1):
        console.print(f"[cyan]Found file {idx}: {f['name']} ({f['id']})[/cyan]")
        logger.info("Found file %s (%s) index=%d", f.get("name"), f.get("id"), idx)

        if processed >= max_n:
            break
        try:
            console.print("[cyan]  -> downloading PDF...[/cyan]")
            logger.info("Downloading PDF %s", f.get("id"))
            pdf_path = ensure_download(drive, f, s.cache_dir)

            console.print("[cyan]  -> computing md5...[/cyan]")
            logger.info("Computing MD5 for %s", pdf_path)
            md5 = effective_md5(f, pdf_path)

            if state.already_processed(f["id"], md5):
                console.print("[yellow]  -> already processed, skipping[/yellow]")
                logger.info("Skipping already processed file %s", f.get("id"))
                continue

            console.print("[cyan]  -> sending to OpenAI...[/cyan]")
            logger.info("Sending %s to model %s (temp=%s)", pdf_path, s.openai_model, s.temperature)
            raw = analyze_pdf(pdf_path, s.openai_model, s.temperature, s.openai_api_key)
            data = normalize_report_payload(raw)

            fig_png, fig_caption = extract_best_figure_png(pdf_path, s.output_dir, f["id"])
            if fig_png:
                data["_figure_image"] = fig_png
                if fig_caption and not (data["figure"].get("evidence") or "").strip():
                    data["figure"]["evidence"] = fig_caption

            console.print("[cyan]  -> finding tables/charts...[/cyan]")
            logger.info("Finding tables/charts in %s", pdf_path)
            cands = collect_candidates(pdf_path, s.output_dir)

            if cands:
                console.print(f"[cyan]  -> ranking {len(cands)} candidates...[/cyan]")
                logger.info("Ranking %d candidate regions", len(cands))
                try:
                    ranked = rank_candidates_text_only(cands, model=s.openai_model, api_key=s.openai_api_key)
                except Exception:
                    logger.exception("Ranking failed for %s; continuing without ranks", f.get("id"))
                    ranked = []

            # Join back coords for top-N (N=3)
            id2cand = {c.id: c for c in cands}
            top_items = []
            for row in sorted(ranked, key=lambda r: r.get("score",0), reverse=True)[:3]:
                c = id2cand.get(row["id"])
                if not c: continue
                top_items.append({"id":c.id,"type":c.kind,"score":row.get("score",0),"page":c.page,"bbox":c.bbox})

            console.print("[cyan]  -> cropping top candidates...[/cyan]")
            logger.info("Cropping top candidates: %s", [i.get("id") for i in top_items])
            sliced_paths = crop_regions(pdf_path, s.output_dir, top_items)

            # Put into the data dict for the template
            # First image (if chart) → primary "Figure" image
            if sliced_paths:
                data["_figure_gallery"] = sliced_paths  # full gallery
                data["_figure_top"] = sliced_paths[0]   # first as main


            console.print("[cyan]  -> generating preview (page 1)...[/cyan]")
            logger.info("Generating preview for %s", pdf_path)
            preview = first_page_png(pdf_path, s.output_dir, f["id"])

            console.print("[cyan]  -> extracting best figure...[/cyan]")
            logger.info("Extracting best figure for %s", pdf_path)
            fig_png, fig_caption = extract_best_figure_png(pdf_path, s.output_dir, f["id"])
            if fig_png:
                data["_figure_image"] = fig_png
                if fig_caption and not (data["figure"].get("evidence") or "").strip():
                    data["figure"]["evidence"] = fig_caption

            console.print("[cyan]  -> rendering HTML...[/cyan]")
            logger.info("Rendering HTML for %s", f.get("id"))
            out_html = render_html(env, data, f["name"], f["id"], s.output_dir, preview_png=preview)

            state.record(f["id"], md5, data.get("_openai_file_id"))
            table.add_row(f["name"], f["id"], md5[:10] + "…", out_html)

            console.print(f"[green]  -> done {f['name']}[/green]")
            logger.info("Done processing %s", f.get("name"))
            processed += 1

        except Exception as e:
            console.print(f"[red]Error processing {f.get('name')}: {e}[/red]")
            logger.exception("Error processing %s", f.get("name"))

    console.print(table)
    console.print(f"[green]Done: {processed} file(s).[/green]")

def main():
    app()

if __name__ == "__main__":
    main()
