"""
watchlist_sync.py — Synchronisiert die Watchlist aus dem Trading-Journal
(Excel) in den Watchlist-Block des STATE-Doc.

Workflow:
1. Sucht das jüngste Trading_Journal_*.xlsx im Workspace-Shared-Drive
2. Lädt es runter, liest das "Watchlist"-Sheet
3. Konvertiert Excel-Zeilen in das STATE-Markdown-Tabellenformat
4. Liest STATE-Doc, ersetzt nur die Watchlist-Sektion
5. Schreibt STATE-Doc zurück via Drive API files().update()

Aufruf in GitHub Action (vor marketdata_sync.py):
    python src/watchlist_sync.py

Erforderliche ENVs (gleich wie marketdata_sync.py):
    GDRIVE_SA_KEY     — Service-Account-JSON
    STATE_DOC_ID      — File-ID des STATE-Docs
    JOURNAL_PARENT_ID — Folder-ID, in dem das Journal liegt
                        (default: gleich BRIEFING_FOLDER_ID-Parent, also
                        Workspace-Shared-Drive Trading-Pipeline-Root)

Stand: 2026-04-29 v1
"""

from __future__ import annotations

import io
import logging
import os
import re
import sys
from datetime import date, datetime
from typing import Optional

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaInMemoryUpload, MediaIoBaseDownload
from openpyxl import load_workbook

# Module aus diesem Repo
from drive_writer import build_drive_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("watchlist_sync")


# ===========================================================================
# Excel → Watchlist-Einträge
# ===========================================================================

# Mapping erstes Emoji → Pipeline-Status
# Fallback "aktiv" wenn nichts erkannt.
EMOJI_TO_STATUS: list[tuple[str, str]] = [
    ("⚠️", "aktiv"),
    ("📅", "pending"),
    ("⏸", "paused"),
    ("👀", "beobachten"),
    ("🔍", "beobachten"),
]

# Datum aus Status extrahieren (für pending-Einträge)
_DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")


def _parse_status(raw_status: str) -> tuple[str, str]:
    """Heuristik: erstes Emoji → Pipeline-Status. Rest → kurze Note.

    Returns (status_keyword, status_note).
    """
    raw = (raw_status or "").strip()
    status = "aktiv"
    for emoji, keyword in EMOJI_TO_STATUS:
        if emoji in raw:
            status = keyword
            break

    # Note = Rest nach dem Emoji, gekürzt auf max 80 Zeichen
    note = raw
    for emoji, _ in EMOJI_TO_STATUS:
        if emoji in note:
            # Alles nach dem Emoji nehmen
            note = note.split(emoji, 1)[1].strip()
            break
    # Aufräumen: führende ":-—," entfernen
    note = note.lstrip(": -—,").strip()
    if len(note) > 80:
        note = note[:77] + "..."

    # Bei pending-Status: Datum extrahieren und voranstellen
    if status == "pending":
        m = _DATE_RE.search(raw)
        if m:
            iso_date = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
            note = f"{iso_date} — {note}" if note else iso_date

    return status, note


def _shorten_trigger(trigger: str) -> str:
    """Excel-Trigger ist Lang-Form; Pipeline und STATE-Doc-Lesbarkeit
    profitieren von Kurz-Form.

    Heuristik: bei Mehrfach-Triggern (A) ... B) ...) nur ersten Trigger
    nehmen, Rest mit "..." andeuten. Sonst auf 120 Zeichen kürzen,
    sauber an Wortgrenze.
    """
    if not trigger:
        return ""
    text = str(trigger).strip()

    # Mehrfach-Trigger: A)...B)... → nur A) zeigen plus Hinweis
    has_b = re.search(r"\bB\)\s", text)
    if text.startswith("A)") and has_b:
        text = text[: has_b.start()].rstrip(" .,;:") + " · (B) ..."

    if len(text) <= 120:
        return text
    cut = text.rfind(" ", 0, 120)
    if cut < 60:
        cut = 120
    return text[:cut].rstrip(",.;:—–-") + "…"


def _shorten_richtung(richtung: str) -> str:
    """Excel-Richtung kann Klammer-Modifier enthalten (z.B. 'LONG (Pullback)').

    Pipeline parst nur LONG/SHORT — wir nehmen das erste Wort.
    """
    if not richtung:
        return ""
    s = str(richtung).strip()
    first = s.split()[0].upper().rstrip(",.")
    if first in ("LONG", "SHORT"):
        return first
    if "LONG" in s.upper():
        return "LONG"
    if "SHORT" in s.upper():
        return "SHORT"
    return first  # KONDITIONAL etc. unverändert lassen


_VERFALL_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def _parse_verfall_date(raw: str) -> str:
    """Extrahiert das führende TT.MM.JJJJ aus dem Verfallsdatum-Feld (Spalte H)
    und normiert es auf ISO YYYY-MM-DD für den STATE-Doc.

    Das Journal-Feld enthält Datum plus Freitext-Klammer, z.B.
    '11.06.2026 (Momentum-Setup +14 HT)'. Leerer String bei fehlendem oder
    unparsbarem Datum.
    """
    if not raw:
        return ""
    m = _VERFALL_DATE_RE.search(raw)
    if not m:
        return ""
    d, mo, y = m.groups()
    try:
        return date(int(y), int(mo), int(d)).isoformat()
    except ValueError:
        return ""


def read_journal_watchlist(xlsx_bytes: bytes) -> list[dict]:
    """Liest das Watchlist-Sheet aus dem Journal und gibt Dicts zurück.

    Erwartet das aktuelle Format mit Spalten:
        Aktie | Symbol | Richtung | Entry-Trigger | These | Status | Datum
    Das Symbol-Feld ist Pflicht — Zeilen ohne Symbol werden übersprungen
    mit Warnung.
    """
    wb = load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    if "Watchlist" not in wb.sheetnames:
        raise RuntimeError(
            f"Watchlist-Sheet nicht gefunden im Journal. "
            f"Vorhandene Sheets: {wb.sheetnames}"
        )
    ws = wb["Watchlist"]

    # Header-Zeile suchen — erste Zeile mit dem Wort "Aktie" oder "Symbol"
    header_row_idx = None
    headers: list[str] = []
    for i, row in enumerate(ws.iter_rows(values_only=True), 1):
        cells = [str(c).strip().lower() if c else "" for c in row]
        if any("aktie" in c or "symbol" in c for c in cells):
            header_row_idx = i
            headers = cells
            break
    if header_row_idx is None:
        raise RuntimeError("Header-Zeile in Watchlist-Sheet nicht gefunden")

    # Spalten-Indizes finden
    def find_col(*candidates: str) -> Optional[int]:
        for cand in candidates:
            for j, h in enumerate(headers):
                if cand in h:
                    return j
        return None

    col_aktie = find_col("aktie")
    col_symbol = find_col("symbol")
    col_richtung = find_col("richtung")
    col_trigger = find_col("entry-trigger", "trigger")
    col_status = find_col("status")
    col_verfall = find_col("verfallsdatum", "verfall")

    if col_symbol is None:
        raise RuntimeError(
            "Symbol-Spalte nicht im Watchlist-Sheet gefunden. "
            "Bitte Spalte 'Symbol' anlegen mit Yahoo-Tickern (z.B. CBK.DE, AAPL)."
        )
    if col_aktie is None or col_richtung is None:
        raise RuntimeError(
            "Pflichtspalten 'Aktie' oder 'Richtung' nicht gefunden."
        )

    entries: list[dict] = []
    for row in ws.iter_rows(min_row=header_row_idx + 1, values_only=True):
        if not row or all(c is None for c in row):
            continue
        aktie = (str(row[col_aktie]).strip() if row[col_aktie] else "").strip()
        symbol = (str(row[col_symbol]).strip() if row[col_symbol] else "").strip()
        if not aktie or not symbol:
            if aktie or symbol:
                logger.warning(
                    "Zeile übersprungen — Aktie oder Symbol fehlt: "
                    "aktie=%r symbol=%r", aktie, symbol,
                )
            continue
        richtung = str(row[col_richtung]).strip() if row[col_richtung] else ""
        trigger = (
            str(row[col_trigger]).strip()
            if col_trigger is not None and row[col_trigger]
            else ""
        )
        raw_status = (
            str(row[col_status]).strip()
            if col_status is not None and row[col_status]
            else ""
        )
        raw_verfall = (
            str(row[col_verfall]).strip()
            if col_verfall is not None and row[col_verfall]
            else ""
        )

        status, note = _parse_status(raw_status)
        entries.append({
            "aktie": aktie,
            "symbol": symbol,
            "richtung": _shorten_richtung(richtung),
            "trigger": _shorten_trigger(trigger),
            "status": status,
            "note": note,
            "verfall": _parse_verfall_date(raw_verfall),
        })
    return entries


# ===========================================================================
# Markdown-Block rendern
# ===========================================================================

WATCHLIST_HEADER = "## Watchlist-Trigger (aktive Einträge)"
PFLEGE_BLOCK = """\
> **Pflege:** Tot-Einträge (✅ gelaufen, ❌ These geplatzt, 📉 Chart-not)
> aus dieser Tabelle entfernen und in Sektion "Watchlist-Archiv" verschieben.
> Pipeline ignoriert archivierte Einträge automatisch.
>
> **Status-Werte (definiert):**
> - ⚠️ aktiv — Trigger nah/in Reichweite, Pipeline meldet täglich
> - 📅 pending — Datum-Constraint noch nicht erreicht
> - ⏸ paused — Bedingung temporär nicht da (RSI/Vol/etc.)
> - 🔍 beobachten — passive (>10% entfernt), These intakt
>
> **Tot-Werte (→ Archiv):** ✅ gelaufen / ❌ These geplatzt / 📉 Chart-not bestätigt
>
> **AUTO-SYNC:** Diese Tabelle wird bei jedem Tier-A-Lauf (alle 30 Min) aus
> dem Watchlist-Sheet des Trading-Journals neu generiert. Manuelle Edits
> hier werden überschrieben — bitte Watchlist im Journal pflegen."""


def _status_emoji(status: str) -> str:
    return {
        "aktiv": "⚠️",
        "pending": "📅",
        "paused": "⏸",
        "beobachten": "🔍",
    }.get(status, "⚠️")


def render_watchlist_block(entries: list[dict], generated_at: datetime) -> str:
    """Generiert den kompletten Watchlist-Block (Header + Pflege + Tabelle)."""
    lines = [WATCHLIST_HEADER, "", PFLEGE_BLOCK, ""]
    lines.append(
        f"> _Auto-Sync zuletzt: {generated_at.strftime('%Y-%m-%d %H:%M UTC')} "
        f"({len(entries)} Einträge)_"
    )
    lines.append("")
    lines.append("| Kandidat | Symbol | Richtung | Trigger (Kurzform) | Status | Verfall |")
    lines.append("|----------|--------|----------|--------------------|--------|---------|")
    for e in entries:
        emoji = _status_emoji(e["status"])
        status_cell = f"{emoji} {e['status']}"
        if e["note"]:
            status_cell += f" — {e['note']}"
        # Pipe in Zellinhalten escapen, sonst kaputte Tabelle
        kandidat = e["aktie"].replace("|", "\\|")
        trigger = e["trigger"].replace("|", "\\|").replace("\n", " ")
        status_cell = status_cell.replace("|", "\\|")
        verfall = e.get("verfall", "").replace("|", "\\|")
        lines.append(
            f"| {kandidat} | {e['symbol']} | {e['richtung']} | {trigger} | "
            f"{status_cell} | {verfall} |"
        )
    lines.append("")
    return "\n".join(lines)


# ===========================================================================
# STATE-Doc Read / Write
# ===========================================================================

# Block-Ersetzung: alles zwischen WATCHLIST_HEADER und der nächsten Sektion
_WATCHLIST_BLOCK_RE = re.compile(
    r"(?ms)^##\s*Watchlist-Trigger.*?(?=^##\s|\Z)"
)


def replace_watchlist_block(state_text: str, new_block: str) -> str:
    """Ersetzt den bestehenden Watchlist-Block im STATE-Text.

    Findet den Block über das Header-Pattern und ersetzt bis zum nächsten
    `## ` oder Dateiende. Wenn kein Block existiert, wird der neue Block
    direkt nach `# STATE START` (oder am Anfang) eingefügt.
    """
    new_block_normalized = new_block.rstrip() + "\n\n"
    if _WATCHLIST_BLOCK_RE.search(state_text):
        return _WATCHLIST_BLOCK_RE.sub(new_block_normalized, state_text, count=1)
    # Kein Block gefunden — nach STATE-START einfügen
    start_match = re.search(r"#\s*STATE\s*START\s*\n", state_text, re.IGNORECASE)
    if start_match:
        idx = start_match.end()
        return state_text[:idx] + "\n" + new_block_normalized + state_text[idx:]
    # Notfall: ganz vorne anhängen
    return new_block_normalized + state_text


def read_state_doc(drive_service, state_doc_id: str) -> tuple[str, str]:
    """Returnt (text, mime_type)."""
    from drive_writer import _with_retry  # lokaler Import, Zyklusvermeidung
    metadata = _with_retry(
        "read_state_doc.metadata",
        lambda: drive_service.files().get(
            fileId=state_doc_id, fields="mimeType,name", supportsAllDrives=True,
        ).execute(),
    )
    mime_type = metadata.get("mimeType", "")

    if mime_type == "application/vnd.google-apps.document":
        request = drive_service.files().export_media(
            fileId=state_doc_id, mimeType="text/plain",
        )
    else:
        request = drive_service.files().get_media(
            fileId=state_doc_id, supportsAllDrives=True,
        )
    content = _with_retry("read_state_doc.content", lambda: request.execute())
    if isinstance(content, bytes):
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                return content.decode(enc), mime_type
            except UnicodeDecodeError:
                continue
    return str(content), mime_type


def write_state_doc(drive_service, state_doc_id: str, new_text: str, mime_type: str) -> None:
    """Schreibt den neuen Inhalt zurück.

    mime_type-aware (gefixt 2026-05-19, Note #68):
    - Bei Google Docs Native (`vnd.google-apps.document`): Upload als
      `text/plain`. Drive akzeptiert `text/markdown` per files().update()
      mit `uploadType=media` unzuverlässig — beobachtet HTTP 400 Bad Request
      seit ~Mitte Mai 2026, Folge: stiller Sync-Drift (CHKP-Schaden 18.05.).
      Plain-Text-Upload behält die Markdown-Syntax (## Headers, | Tabellen)
      als Klartext im Doc — state_parser liest via text/plain-Export sauber
      zurück. Im Doc-Editor sieht's roh aus, das ist akzeptabel weil der
      STATE-Doc primär von der Pipeline gelesen wird, nicht von Menschen.
    - Bei Markdown-File (`text/markdown` o.ä.): Original-mime_type beibehalten.
    """
    from drive_writer import _with_retry  # lokaler Import

    if mime_type == "application/vnd.google-apps.document":
        upload_mime = "text/plain"
    elif mime_type:
        upload_mime = mime_type
    else:
        upload_mime = "text/markdown"

    logger.info(
        "write_state_doc: target_mime=%s, upload_mime=%s, bytes=%d",
        mime_type or "unknown", upload_mime, len(new_text.encode("utf-8")),
    )

    media = MediaInMemoryUpload(
        new_text.encode("utf-8"),
        mimetype=upload_mime,
        resumable=False,
    )
    _with_retry(
        "write_state_doc",
        lambda: drive_service.files().update(
            fileId=state_doc_id,
            media_body=media,
            supportsAllDrives=True,
        ).execute(),
    )


# ===========================================================================
# Journal-Suche
# ===========================================================================

def find_latest_journal(drive_service, search_folder_id: Optional[str] = None) -> dict:
    """Sucht jüngste Trading_Journal_*.xlsx-Datei.

    Suche zuerst im angegebenen Folder (falls gesetzt), dann global im
    Account. Returnt Dict mit id, name, modifiedTime.
    """
    queries: list[str] = []
    if search_folder_id:
        queries.append(
            f"'{search_folder_id}' in parents "
            f"and name contains 'Trading_Journal' "
            f"and trashed = false"
        )
    queries.append(
        "name contains 'Trading_Journal' "
        "and mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' "
        "and trashed = false"
    )

    for q in queries:
        try:
            from drive_writer import _with_retry  # lokaler Import
            result = _with_retry(
                "find_latest_journal.list",
                lambda q=q: drive_service.files().list(
                    q=q,
                    orderBy="modifiedTime desc",
                    fields="files(id,name,modifiedTime,parents)",
                    pageSize=10,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    corpora="allDrives",
                ).execute(),
            )
            files = result.get("files", [])
            if files:
                logger.info(
                    "Journal gefunden: %s (modifiziert %s)",
                    files[0]["name"], files[0]["modifiedTime"],
                )
                return files[0]
        except HttpError as e:
            logger.warning("Drive-Search fehlgeschlagen: %s", e)
            continue

    raise RuntimeError(
        "Kein Trading_Journal_*.xlsx im Drive gefunden. "
        "Bitte Journal in den Workspace-Shared-Drive 'Trading-Pipeline' "
        "hochladen oder via Drive Desktop syncen."
    )


def download_journal(drive_service, file_id: str) -> bytes:
    """Lädt Journal als Bytes runter."""
    from drive_writer import _with_retry  # lokaler Import
    request = drive_service.files().get_media(
        fileId=file_id, supportsAllDrives=True,
    )
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        # next_chunk() macht intern auch HTTPs — bei TLS-Reset abfangen.
        _, done = _with_retry(
            "download_journal.next_chunk",
            lambda: downloader.next_chunk(),
        )
    return buf.getvalue()


# ===========================================================================
# Main
# ===========================================================================

def main() -> int:
    state_doc_id = os.environ.get("STATE_DOC_ID")
    journal_parent_id = os.environ.get("JOURNAL_PARENT_ID")  # optional

    if not state_doc_id:
        logger.error("STATE_DOC_ID env variable nicht gesetzt")
        return 1

    drive_service = build_drive_service()

    # 1. Journal finden & laden
    journal_meta = find_latest_journal(drive_service, journal_parent_id)
    journal_bytes = download_journal(drive_service, journal_meta["id"])

    # 2. Watchlist-Sheet parsen
    entries = read_journal_watchlist(journal_bytes)
    logger.info("Watchlist aus Journal: %d Einträge", len(entries))
    if not entries:
        logger.warning("Watchlist leer — Sync abgebrochen, STATE bleibt unverändert")
        return 0

    # 3. STATE-Doc lesen
    state_text, mime_type = read_state_doc(drive_service, state_doc_id)

    # 3a. Markdown-Escapes strippen (Note #68 Round 2, 2026-05-19):
    # Drive's text/plain-Export escaped Markdown-Sonderzeichen mit Backslash.
    # Ohne Strip akkumulieren bei jedem Read/Write-Cycle weitere Backslashes,
    # bis das Doc exponentiell aufbläht und Drive HTTP 400 zurückgibt.
    # state_parser hatte den Strip bereits beim Read — wir müssen ihn auch
    # hier anwenden, weil watchlist_sync das Doc nicht nur liest sondern
    # zurückschreibt.
    from state_parser import _strip_markdown_escapes
    original_len = len(state_text)
    state_text = _strip_markdown_escapes(state_text)
    if len(state_text) < original_len:
        logger.info(
            "Markdown-Escapes gestrippt: %d → %d Zeichen (%.1f%% Reduktion)",
            original_len, len(state_text),
            (original_len - len(state_text)) / original_len * 100,
        )

    # 4. Watchlist-Block neu rendern und ersetzen
    new_block = render_watchlist_block(entries, datetime.utcnow())
    new_text = replace_watchlist_block(state_text, new_block)

    if new_text == state_text:
        logger.info("Watchlist-Block unverändert — kein Update nötig")
        return 0

    # 5. STATE-Doc schreiben
    write_state_doc(drive_service, state_doc_id, new_text, mime_type)
    logger.info("STATE-Doc aktualisiert (%d Einträge synchronisiert)", len(entries))

    # 6. Sanity-Check (Note #68): Re-Read und Eintrags-Count vergleichen.
    # Drive-API kann Markdown-Uploads stumm verlieren oder konvertieren —
    # wenn das passiert, ist der Sync gescheitert, auch wenn files().update()
    # 200 OK lieferte. Lieber rote Pipeline als grüne Lüge.
    state_text_after, _ = read_state_doc(drive_service, state_doc_id)
    state_text_after = _strip_markdown_escapes(state_text_after)
    after_count = _count_watchlist_entries(state_text_after)
    if after_count != len(entries):
        raise RuntimeError(
            f"STATE-Doc-Sanity-Check fehlgeschlagen: erwartet {len(entries)} "
            f"WL-Einträge nach Write, gefunden {after_count}. "
            f"Drive-API-Drift wahrscheinlich (siehe Note #68). "
            f"Manuell prüfen: STATE_DOC_ID={state_doc_id}"
        )
    logger.info("Sanity-Check OK: %d Einträge im STATE-Doc bestätigt", after_count)
    return 0


def _count_watchlist_entries(state_text: str) -> int:
    """Zählt Datenzeilen in der Watchlist-Tabelle des STATE-Docs.

    Heuristik: nach dem WATCHLIST_HEADER alle Zeilen, die mit `|` beginnen,
    keine Separator-/Header-Zeilen sind, und nicht in einer Nachbar-Sektion
    liegen. Robust gegen text/plain-Export aus Google Docs (`##`-Headers
    bleiben als Plain-Text erhalten).
    """
    match = _WATCHLIST_BLOCK_RE.search(state_text)
    if not match:
        return 0
    block = match.group(0)
    count = 0
    for line in block.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        if "Kandidat" in s and "Symbol" in s:
            continue  # Header-Zeile
        if re.match(r"^\|\s*[-:]+\s*\|", s):
            continue  # Separator
        count += 1
    return count


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        logger.exception("Watchlist-Sync fehlgeschlagen: %s", e)
        sys.exit(1)
