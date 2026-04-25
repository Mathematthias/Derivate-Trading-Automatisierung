"""
drive_writer.py — Schreibt Markdown-Files in den Drive Trading/Briefing-Ordner

Nutzt Service-Account-Credentials aus Environment-Variable GDRIVE_SA_KEY.
Schreibt als text/markdown mit disableConversionToGoogleType=true (das ist
in den V1.5-Routinen erprobt — verhindert Stream-Idle-Timeouts bei
Google-Doc-Konvertierung).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

logger = logging.getLogger(__name__)

# Drive-API Scopes
SCOPES = ["https://www.googleapis.com/auth/drive"]


def build_drive_service():
    """Erzeugt ein authentifiziertes Drive-API-Resource-Object.

    Liest Service-Account-Key aus GDRIVE_SA_KEY-Env-Variable.
    """
    sa_key_json = os.environ.get("GDRIVE_SA_KEY")
    if not sa_key_json:
        raise RuntimeError(
            "GDRIVE_SA_KEY environment variable not set. "
            "In GitHub Actions: Settings → Secrets → Actions → GDRIVE_SA_KEY"
        )
    try:
        sa_info = json.loads(sa_key_json)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"GDRIVE_SA_KEY is not valid JSON: {e}")

    credentials = service_account.Credentials.from_service_account_info(
        sa_info, scopes=SCOPES
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def write_markdown_file(
    drive_service,
    parent_folder_id: str,
    filename: str,
    content: str,
) -> str:
    """Schreibt Markdown-Content als Datei in den Drive-Ordner.

    Returns:
        File-ID der neu erstellten Datei.
    """
    body = {
        "name": filename,
        "parents": [parent_folder_id],
        "mimeType": "text/markdown",
    }

    media = MediaInMemoryUpload(
        content.encode("utf-8"),
        mimetype="text/markdown",
        resumable=False,
    )

    result = drive_service.files().create(
        body=body,
        media_body=media,
        fields="id,name,parents",
        supportsAllDrives=True,
    ).execute()

    file_id = result["id"]
    logger.info(f"  Wrote {filename} → file_id {file_id}")
    return file_id


def cleanup_old_files(
    drive_service,
    parent_folder_id: str,
    filename_prefix: str,
    keep_count: int = 10,
) -> int:
    """Löscht alte Files mit gegebenem Prefix, behält die neuesten keep_count.

    Verhindert Drive-Verstopfung bei 30-Min-Frequenz.
    Returns Anzahl gelöschter Files.
    """
    query = (
        f"'{parent_folder_id}' in parents "
        f"and name contains '{filename_prefix}' "
        f"and trashed = false"
    )
    results = drive_service.files().list(
        q=query,
        orderBy="createdTime desc",
        fields="files(id,name,createdTime)",
        pageSize=100,
    ).execute()
    files = results.get("files", [])
    if len(files) <= keep_count:
        return 0

    to_delete = files[keep_count:]
    deleted = 0
    for f in to_delete:
        try:
            drive_service.files().delete(fileId=f["id"]).execute()
            deleted += 1
        except Exception as e:
            logger.warning(f"  Failed to delete {f['name']}: {e}")
    if deleted:
        logger.info(f"  Cleaned up {deleted} old {filename_prefix} files")
    return deleted
