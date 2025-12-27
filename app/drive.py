from typing import Dict, Any, Iterable, Optional
from pathlib import Path
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from googleapiclient.http import MediaIoBaseDownload
import io
import hashlib
import os
import re
import unicodedata

def drive_client(sa_path: str):
    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    creds = Credentials.from_service_account_file(sa_path, scopes=scopes)
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def list_pdfs(drive, folder_id: str) -> Iterable[Dict[str, Any]]:
    q = f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false"
    page_token: Optional[str] = None
    while True:
        resp = drive.files().list(
            q=q,
            fields="files(id,name,modifiedTime,md5Checksum,version),nextPageToken",
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        for f in resp.get("files", []):
            yield f
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

def ensure_download(drive, file_meta: Dict[str, Any], cache_dir: str) -> str:
    """Download file to cache_dir using the original Drive file name when possible.

    Keeps the original PDF name (sanitized). If a file with the same name exists
    and its checksum matches, it is reused. If the name exists but is different
    content, a numeric suffix is appended.
    """
    # Prefer the provided original filename
    raw_name = file_meta.get("name") or f"{file_meta['id']}.pdf"

    # Normalize unicode, remove path segments and unsafe chars
    name = os.path.basename(raw_name)
    name = unicodedata.normalize("NFKD", name)
    # Keep only a safe subset of characters
    name = re.sub(r"[^A-Za-z0-9._ \-()]", "_", name).strip()
    # Ensure .pdf extension
    if not name.lower().endswith(".pdf"):
        name = name + ".pdf"

    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    candidate = cache_path / name

    # If file exists, check if it's same by md5; if so, reuse
    if candidate.exists():
        try:
            existing_md5 = md5_for_file(str(candidate))
            drive_md5 = file_meta.get("md5Checksum")
            if drive_md5 and existing_md5 == drive_md5:
                return str(candidate)
        except Exception:
            # If any error, fall back to potentially downloading or renaming
            pass

    # If name exists but different, find a non-colliding name
    if candidate.exists():
        base = candidate.stem
        suffix = 1
        while True:
            new_name = f"{base}-{suffix}.pdf"
            candidate = cache_path / new_name
            if not candidate.exists():
                break
            suffix += 1

    # Download to candidate path
    req = drive.files().get_media(fileId=file_meta["id"])
    with open(candidate, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            status, done = downloader.next_chunk()

    return str(candidate)

def md5_for_file(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def effective_md5(file_meta: Dict[str, Any], local_pdf_path: str) -> str:
    # Some Drive sources may not expose md5Checksum (Team Drives / versions); fallback to local hash.
    return file_meta.get("md5Checksum") or md5_for_file(local_pdf_path)
