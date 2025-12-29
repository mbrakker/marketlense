from typing import Dict, Any, Iterable

import hashlib

from src.contracts.drive import DriveDownloadRequest, DriveFile, DriveListRequest
from src.services.drive_service import (
    build_drive_client,
    download_pdf,
    list_pdfs as list_drive_pdfs,
)
from src.utils.logging import new_run_context

def drive_client(sa_path: str):
    return build_drive_client(sa_path)

def list_pdfs(drive, folder_id: str) -> Iterable[Dict[str, Any]]:
    ctx = new_run_context()
    req = DriveListRequest(schema_version="1.0", folder_id=folder_id)
    for f in list_drive_pdfs(drive, req, ctx):
        yield {
            "id": f.file_id,
            "name": f.name,
            "modifiedTime": f.modified_time,
            "md5Checksum": f.md5_checksum,
            "version": f.version,
        }

def ensure_download(drive, file_meta: Dict[str, Any], cache_dir: str) -> str:
    ctx = new_run_context()
    file = DriveFile(
        schema_version="1.0",
        file_id=file_meta.get("id", ""),
        name=file_meta.get("name", ""),
        modified_time=file_meta.get("modifiedTime"),
        md5_checksum=file_meta.get("md5Checksum"),
        version=str(file_meta.get("version")) if file_meta.get("version") is not None else None,
    )
    req = DriveDownloadRequest(schema_version="1.0", file=file, cache_dir=cache_dir)
    resp = download_pdf(drive, req, ctx)
    return resp.local_path

def effective_md5(file_meta: Dict[str, Any], local_pdf_path: str) -> str:
    return file_meta.get("md5Checksum") or _md5_for_file(local_pdf_path)

def _md5_for_file(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
