from pathlib import Path
import json
import logging

from unstructured.partition.pdf import partition_pdf

logger = logging.getLogger("market_lense.unstructured")


def process_pdf_with_unstructured(pdf_path: str, out_dir: str, report_name: str) -> str:
    """Run `unstructured` on `pdf_path` and save JSON result to `out_dir`.

    The output filename will use the report base name with a `.json` extension.
    Returns the path to the written JSON file.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    base = Path(report_name).stem
    result_path = out_path / f"{base}.json"

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
        raise
