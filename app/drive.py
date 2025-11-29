from typing import Dict, Any, Iterable, Optional
from pathlib import Path
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from googleapiclient.http import MediaIoBaseDownload
import io
import hashlib

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
    path = Path(cache_dir) / f"{file_meta['id']}.pdf"
    if not path.exists():
        req = drive.files().get_media(fileId=file_meta["id"])
        with open(path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, req)
            done = False
            while not done:
                status, done = downloader.next_chunk()
    return str(path)

def md5_for_file(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def effective_md5(file_meta: Dict[str, Any], local_pdf_path: str) -> str:
    # Some Drive sources may not expose md5Checksum (Team Drives / versions); fallback to local hash.
    return file_meta.get("md5Checksum") or md5_for_file(local_pdf_path)
