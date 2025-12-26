from pathlib import Path
import json
import logging
import os
import glob
import traceback

from unstructured.partition.pdf import partition_pdf

logger = logging.getLogger("market_lense.unstructured")


def _ensure_poppler_on_path() -> bool:
    """If a Poppler binary is present, prepend its bin to PATH and return True.
    Checks (in order):
     - `tools/poppler` in the project (for bundled binaries)
     - env vars `POPPLER_PATH` or `POPLER_HOME`
     - common Windows install locations (Program Files / Program Files (x86))
    Returns False if no Poppler binaries were found."""
    project_root = Path(__file__).resolve().parents[1]
    poppler_root = project_root / "tools" / "poppler"

    candidates = []
    # project-local bundle
    if poppler_root.exists():
        candidates += list(poppler_root.glob("**/Library/bin")) + list(poppler_root.glob("**/bin"))

    # env vars
    for env_key in ("POPPLER_PATH", "POPLER_HOME"):
        ev = os.environ.get(env_key)
        if ev:
            p = Path(ev)
            if p.exists():
                candidates.append(p)

    # common install locations on Windows
    win_paths = [
        Path(r"C:\Program Files\Poppler\Library\bin"),
        Path(r"C:\Program Files\Poppler\bin"),
        Path(r"C:\Program Files (x86)\Poppler\Library\bin"),
        Path(r"C:\Program Files (x86)\Poppler\bin"),
    ]
    for p in win_paths:
        if p.exists():
            candidates.append(p)

    # Check Winget package extraction path (LOCALAPPDATA\Microsoft\WinGet\Packages)
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        wag = Path(local_app) / "Microsoft" / "WinGet" / "Packages"
        if wag.exists():
            # look for any extracted poppler package that contains pdfinfo.exe
            for pdfinfo in wag.rglob("pdfinfo.exe"):
                candidates.append(pdfinfo.parent)

    # Deduplicate preserving order
    seen = set()
    final = []
    for c in candidates:
        s = str(c)
        if s not in seen:
            seen.add(s)
            final.append(c)

    if not final:
        return False

    bin_dir = str(final[0])
    if bin_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")

    # Also set helpful env vars used by some tools and for diagnostics
    os.environ["POPPLER_PATH"] = bin_dir
    os.environ["POPLER_HOME"] = bin_dir

    # Try to locate the pdfinfo executable and verify it runs
    pdfinfo_candidates = [
        Path(bin_dir) / "pdfinfo.exe",
        Path(bin_dir) / "pdfinfo",
    ]
    pdfinfo_path = None
    for c in pdfinfo_candidates:
        if c.exists():
            pdfinfo_path = str(c)
            break

    if pdfinfo_path:
        try:
            # run a quick version check to ensure subprocess can find and execute it
            import subprocess
            subprocess.run([pdfinfo_path, "-v"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logger.info("Found and verified pdfinfo at %s", pdfinfo_path)

            # Try to locate poppler 'share/poppler' data directory (used for nameToUnicode maps, etc.)
            # typical layout: <...>\poppler-<ver>\Library\bin --> sibling 'share\poppler'
            bin_p = Path(bin_dir)
            candidate_share = None
            # look for share/poppler in a few likely places
            for d in (bin_p.parent.parent / "share" / "poppler", bin_p.parent / "share" / "poppler"):
                if d.exists():
                    candidate_share = d
                    break
            if candidate_share:
                os.environ["POPPLER_DATA"] = str(candidate_share)
                logger.info("Set POPPLER_DATA to %s", candidate_share)

            return True
        except Exception as exc:  # pragma: no cover - system-dependent
            logger.warning("Found pdfinfo at %s but execution failed: %s", pdfinfo_path, exc)
            # fallthrough to return True since PATH is set
    else:
        # As an extra attempt, ensure 'pdfinfo' is findable via PATH
        from shutil import which
        if which("pdfinfo"):
            logger.info("pdfinfo found on PATH via which()")
            return True

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


def _partition_worker(in_pdf: str, out_path: str):
    """Top-level worker used by the timeout wrapper (Windows-friendly)."""
    try:
        from unstructured.partition.pdf import partition_pdf
        elems = partition_pdf(filename=in_pdf)
        payload = [e.to_dict() for e in elems]
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except Exception:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({"__error__": True, "trace": traceback.format_exc()}, fh)
        raise


def _partition_with_timeout(pdf_path: str, timeout_seconds: int = 120):
    """Run partition_pdf in a separate process with a timeout.

    Uses a temporary file to serialize partition output (JSON) from the worker process
    to avoid pickling complex element objects. Raises TimeoutError on timeout or
    re-raises worker exceptions.
    """
    import multiprocessing as mp
    import tempfile

    temp = tempfile.NamedTemporaryFile(prefix="unstructured_partition_", suffix=".json", delete=False)
    temp_path = Path(temp.name)
    temp.close()

    p = mp.Process(target=_partition_worker, args=(pdf_path, str(temp_path)))
    logger.info("Starting partition subprocess for %s (timeout=%ds)", pdf_path, timeout_seconds)
    p.start()
    p.join(timeout_seconds)
    if p.is_alive():
        logger.warning("Partition subprocess did not finish within %ds; terminating", timeout_seconds)
        p.terminate()
        p.join()
        # Clean up temp file and raise
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise TimeoutError(f"partition_pdf timed out after {timeout_seconds} seconds")

    # Read output file
    if not temp_path.exists():
        raise RuntimeError("partition worker did not produce output file")

    data = json.loads(temp_path.read_text(encoding="utf-8"))
    temp_path.unlink(missing_ok=True)
    if isinstance(data, dict) and data.get("__error__"):
        raise RuntimeError("partition worker raised an exception:\n" + data.get("trace", ""))
    return data


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

    # Allow timeout to be configured via env var (seconds)
    try:
        timeout = int(os.environ.get("UNSTRUCTURED_TIMEOUT", "120"))
    except ValueError:
        timeout = 120

    try:
        # Run partitioning in a subprocess with a timeout to avoid indefinite hangs
        payload = _partition_with_timeout(pdf_path, timeout_seconds=timeout)
        with open(result_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        logger.info("Wrote unstructured output to %s", result_path)
        return str(result_path)
    except TimeoutError:
        logger.warning("Unstructured partition timed out for %s after %ds", pdf_path, timeout)
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

