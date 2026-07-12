"""
drive_writer.py — Schreibt Markdown-Files in den Drive Trading/Briefing-Ordner

Nutzt Service-Account-Credentials aus Environment-Variable GDRIVE_SA_KEY.
Schreibt als text/markdown mit disableConversionToGoogleType=true (das ist
in den V1.5-Routinen erprobt — verhindert Stream-Idle-Timeouts bei
Google-Doc-Konvertierung).

Robustheit (seit 2026-05-13): Drive-API-Calls laufen durch `_with_retry`,
das transiente TLS/HTTP-Fehler (SSLEOFError, ConnectionError, HttpError 5xx,
HttpError 429) mit exponentiellem Backoff wiederholt. Hintergrund:
Pipeline-Crash 2026-05-13 mit `ssl.SSLEOFError: EOF occurred in violation
of protocol` beim `files().create().execute()` — die Gegenseite hatte den
TLS-Stream ohne close_notify gekappt, vermutlich Google-Side-Load-Balancer.
yfinance-Pull war erfolgreich (305/306), Crash erst beim Drive-Upload.
"""

from __future__ import annotations

import io
import json
import logging
import os
import random
import socket
import ssl
import time
from typing import Callable, Optional, TypeVar

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaInMemoryUpload, MediaIoBaseDownload

logger = logging.getLogger(__name__)

# Drive-API Scopes
SCOPES = ["https://www.googleapis.com/auth/drive"]

# Retry-Konfiguration
RETRY_MAX_ATTEMPTS = 4         # 1 Initial + 3 Retries
RETRY_BASE_SECONDS = 1.5       # Exponential-Backoff Basis (1.5, 3, 6, 12 ...)
RETRY_JITTER_SECONDS = 0.5     # Plus Random-Jitter, vermeidet Stampede

# Welche Exceptions retry-würdig sind. SSLEOFError ist eine OSError-Subklasse
# aus dem stdlib `ssl`-Modul. ConnectionError fängt z.B. ConnectionReset.
# socket.timeout ist Timeout-Klasse. HttpError unten gesondert auf Status-Codes.
_RETRYABLE_EXCEPTIONS = (
    ssl.SSLEOFError,
    ssl.SSLError,
    ConnectionError,        # umfasst ConnectionResetError, ConnectionAbortedError, etc.
    socket.timeout,
    TimeoutError,
    OSError,                # Catch-all für Low-Level-Netzwerk
)

T = TypeVar("T")


def _with_retry(operation_name: str, fn: Callable[[], T]) -> T:
    """Führt einen Drive-API-Call mit Exponential-Backoff-Retry aus.

    Retry-würdig sind:
      - TLS-Probleme (SSLEOFError, SSLError)
      - Connection-Probleme (ConnectionError, OSError, timeout)
      - HttpError 5xx (Server-Side-Issue)
      - HttpError 429 (Rate-Limit)

    Nicht-retry: 4xx außer 429 (echte API-Fehler — fehlende Berechtigung,
    falscher Folder, etc.), JSON-Decode-Fehler, etc.
    """
    last_exc: Optional[BaseException] = None
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            return fn()
        except _RETRYABLE_EXCEPTIONS as e:
            last_exc = e
            if attempt == RETRY_MAX_ATTEMPTS:
                logger.error(
                    f"{operation_name}: final retry failed after {attempt} attempts "
                    f"({type(e).__name__}: {e})"
                )
                raise
            wait = RETRY_BASE_SECONDS ** attempt + random.uniform(0, RETRY_JITTER_SECONDS)
            logger.warning(
                f"{operation_name}: attempt {attempt}/{RETRY_MAX_ATTEMPTS} failed "
                f"({type(e).__name__}: {e}) — retrying in {wait:.1f}s"
            )
            time.sleep(wait)
        except HttpError as e:
            last_exc = e
            status = getattr(getattr(e, "resp", None), "status", None)
            if status in (429,) or (isinstance(status, int) and 500 <= status < 600):
                if attempt == RETRY_MAX_ATTEMPTS:
                    logger.error(
                        f"{operation_name}: final retry failed after {attempt} attempts "
                        f"(HTTP {status})"
                    )
                    raise
                wait = RETRY_BASE_SECONDS ** attempt + random.uniform(0, RETRY_JITTER_SECONDS)
                logger.warning(
                    f"{operation_name}: attempt {attempt}/{RETRY_MAX_ATTEMPTS} failed "
                    f"(HTTP {status}) — retrying in {wait:.1f}s"
                )
                time.sleep(wait)
            else:
                # 4xx ≠ 429: nicht retry-würdig
                raise
    # Defensive: sollte nicht erreicht werden
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"{operation_name}: retry loop ended without result or exception")


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

    result = _with_retry(
        f"write_markdown_file({filename})",
        lambda: drive_service.files().create(
            body=body,
            media_body=media,
            fields="id,name,parents",
            supportsAllDrives=True,
        ).execute(),
    )

    file_id = result["id"]
    logger.info(f"  Wrote {filename} → file_id {file_id}")
    return file_id


def write_json_file(
    drive_service,
    parent_folder_id: str,
    filename: str,
    content: str,
) -> str:
    """Schreibt JSON-Content (bereits serialisierter String) als Datei in den
    Drive-Ordner. Analog zu write_markdown_file, aber mimeType application/json.

    Returns:
        File-ID der neu erstellten Datei.
    """
    body = {
        "name": filename,
        "parents": [parent_folder_id],
        "mimeType": "application/json",
    }

    media = MediaInMemoryUpload(
        content.encode("utf-8"),
        mimetype="application/json",
        resumable=False,
    )

    result = _with_retry(
        f"write_json_file({filename})",
        lambda: drive_service.files().create(
            body=body,
            media_body=media,
            fields="id,name,parents",
            supportsAllDrives=True,
        ).execute(),
    )

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
    results = _with_retry(
        f"cleanup_old_files.list({filename_prefix})",
        lambda: drive_service.files().list(
            q=query,
            orderBy="createdTime desc",
            fields="files(id,name,createdTime)",
            pageSize=100,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora="allDrives",
        ).execute(),
    )
    files = results.get("files", [])
    if len(files) <= keep_count:
        return 0

    to_delete = files[keep_count:]
    deleted = 0
    already_gone = 0
    for f in to_delete:
        try:
            _with_retry(
                f"cleanup_old_files.delete({f['name']})",
                # default-arg bindet f früh — kein late-binding-Problem in der Schleife
                lambda f=f: drive_service.files().delete(
                    fileId=f["id"],
                    supportsAllDrives=True,
                ).execute(),
            )
            deleted += 1
        except HttpError as e:
            # 404 = File ist schon weg (manueller Cleanup, API-Cache-Lag,
            # parallele Pipeline-Instanz). Idempotent OK, kein Fehler.
            if e.resp.status == 404:
                logger.debug(f"  Already gone: {f['name']}")
                already_gone += 1
            else:
                logger.warning(f"  Failed to delete {f['name']}: {e}")
        except Exception as e:
            logger.warning(f"  Failed to delete {f['name']}: {e}")
    if deleted:
        logger.info(f"  Cleaned up {deleted} old {filename_prefix} files")
    if already_gone:
        logger.info(
            f"  Skipped {already_gone} already-gone {filename_prefix} files "
            f"(idempotent — listing was stale)"
        )
    return deleted


def read_latest_json_file(
    drive_service,
    parent_folder_id: str,
    filename_prefix: str,
) -> Optional[dict]:
    """Liest das neueste JSON-File mit gegebenem Prefix und gibt es als dict.

    Für den Tier-A-Digest-Lauf, der die frischesten PITCHES-{EU,US}.json aus
    den Tier-B/C-Läufen einliest. Robust: fehlt das File oder schlägt der
    Download fehl, wird None zurückgegeben (Digest läuft dann ohne Pitches,
    Chat fällt auf GAMECHANGER-Fetch zurück).
    """
    query = (
        f"'{parent_folder_id}' in parents "
        f"and name contains '{filename_prefix}' "
        f"and trashed = false"
    )
    try:
        results = _with_retry(
            f"read_latest_json_file.list({filename_prefix})",
            lambda: drive_service.files().list(
                q=query,
                orderBy="createdTime desc",
                fields="files(id,name)",
                pageSize=5,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora="allDrives",
            ).execute(),
        )
        files = results.get("files", [])
        if not files:
            logger.info(f"read_latest_json_file: kein File fuer Prefix {filename_prefix}")
            return None
        file_id = files[0]["id"]
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(
            buf,
            drive_service.files().get_media(fileId=file_id, supportsAllDrives=True),
        )
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return json.loads(buf.getvalue().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 — bewusst tolerant, Digest darf nicht crashen
        logger.warning(f"read_latest_json_file({filename_prefix}) fehlgeschlagen: {e}")
        return None
