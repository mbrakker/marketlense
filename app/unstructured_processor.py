from pathlib import Path
import json
import logging
import os
import glob
import traceback

from unstructured.partition.pdf import partition_pdf

logger = logging.getLogger("market_lense.unstructured")


def _ensure_poppler_on_path() -> bool:
    """If a Poppler binary is present under `tools/poppler`, prepend its bin to PATH and return True.
    Returns False if no Poppler binaries were found."""
    project_root = Path(__file__).resolve().parents[1]
    poppler_root = project_root / "tools" / "poppler"
    if not poppler_root.exists():
        return False
    # Look for common bin paths
    candidates = list(poppler_root.glob("**/Library/bin")) + list(poppler_root.glob("**/bin"))
    if not candidates:
        return False
    bin_dir = str(candidates[0])
    if bin_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    return True


def _fallback_extract_text_with_pymupdf(pdf_path: str):
    """Extract per-page text using PyMuPDF as a fallback when Unstructured can't run."""
    import fitz
    payload = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text")
            payload.append({"type": "page", "page": i, "text": text})
    return payload


def process_pdf_with_unstructured(pdf_path: str, out_dir: str, report_name: str) -> str:
    """Run `unstructured` on `pdf_path` and save JSON result to `out_dir`.

    The output filename will use the report base name with a `.json` extension.
    Returns the path to the written JSON file.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    base = Path(report_name).stem
    result_path = out_path / f"{base}.json"

    # Ensure Poppler is available if bundled in repo
    _ensure_poppler_on_path()

    try:
        elements = partition_pdf(filename=pdf_path)
        # Convert elements to plain dicts for JSON serialization
        payload = [e.to_dict() for e in elements]
        with open(result_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        logger.info("Wrote unstructured output to %s", result_path)
        return str(result_path)
    except Exception:
        logger.exception("Unstructured processing failed for %s", pdf_path)
        # Fallback: try simple text extraction via PyMuPDF so we still produce an output artifact
        try:
            payload = _fallback_extract_text_with_pymupdf(pdf_path)
            with open(result_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            logger.info("Wrote fallback text output to %s", result_path)
            return str(result_path)
        except Exception:
            logger.error("Fallback text extraction also failed for %s: %s", pdf_path, traceback.format_exc())
            raise

