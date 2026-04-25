"""
state_parser.py — Liest STATE-Doc aus Drive und extrahiert die Watchlist
mit Trigger-Definitionen.

Single Source of Truth für die Watchlist ist die Markdown-Tabelle unter
'## Watchlist-Trigger (aktive Einträge)' im STATE-Doc. Dieses Modul:
1. Holt das STATE-Doc per Drive-API
2. Parst die Watchlist-Tabelle in Python-Dicts
3. Extrahiert Trigger-Korridore (Preise), Indikator-Bezüge und Modifikatoren
4. Gibt eine Liste von WatchlistEntry-Objekten zurück

Ebenso werden Filter-Override (Sektion 4) und Ticker-Map (Sektion 1) geparst.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from googleapiclient.discovery import Resource


# Status-Werte aus STATE — was die Pipeline aktiv prüft
ACTIVE_STATUSES = {"aktiv", "pending", "paused", "beobachten"}
IGNORED_STATUSES = {"gelaufen", "these_geplatzt", "chart_not"}


@dataclass
class WatchlistEntry:
    """Ein Watchlist-Eintrag mit allen geparsten Trigger-Infos."""

    name: str  # z.B. "Commerzbank (CBK)"
    symbol: str  # Yahoo-Symbol z.B. "CBK.DE"
    direction: str  # "LONG" | "SHORT"
    trigger_raw: str  # unverarbeitete Trigger-Beschreibung
    status: str  # einer aus ACTIVE_STATUSES
    status_note: str  # freitext nach dem Statuswert

    # Extrahierte Trigger-Komponenten
    triggers: list["ParsedTrigger"] = field(default_factory=list)
    earliest_date: Optional[date] = None  # bei "nach 2026-04-30"


@dataclass
class ParsedTrigger:
    """Ein einzelner Trigger (A, B, ...) eines Watchlist-Eintrags."""

    label: str  # "A", "B", oder "" wenn unbenannt
    raw: str  # vollständiger Trigger-Text

    # Preis-Komponenten
    price_low: Optional[float] = None
    price_high: Optional[float] = None
    price_single: Optional[float] = None  # bei z.B. ">35,10€"
    price_op: Optional[str] = None  # "<", ">", "in_range", "approx"

    # Indikator-Bezüge (für später, falls nicht direkt im Korridor)
    ema_ref: Optional[str] = None  # "EMA20", "EMA50", "EMA200"

    # Modifikatoren
    require_bounce: bool = False  # "+ Bounce" oder "+ Reversal"
    require_volume: bool = False  # "Vol ≥30D-Ø"
    require_hammer: bool = False  # "Hammer"
    rsi_max: Optional[float] = None  # "RSI<60"
    rsi_min: Optional[float] = None


@dataclass
class FilterOverride:
    symbol: str
    override_type: str  # priority_long | priority_short | wait_for | disqualified
    reason: str
    valid_until: Optional[date] = None


# ============================================================
# DRIVE READING
# ============================================================

def fetch_state_doc(drive_service: Resource, state_doc_id: str) -> str:
    """Holt das STATE-Doc als Markdown-Text via Drive API.

    Unterstützt zwei Formate:
    - Google Doc (application/vnd.google-apps.document) → export als text/plain
    - Markdown-Datei (text/markdown) oder Plain-Text → direkt download
    """
    # Erst Metadaten holen, um mimeType zu erfahren
    metadata = drive_service.files().get(
        fileId=state_doc_id,
        fields="mimeType,name",
        supportsAllDrives=True,
    ).execute()
    mime_type = metadata.get("mimeType", "")

    if mime_type == "application/vnd.google-apps.document":
        # Google Doc → export als plain text
        request = drive_service.files().export_media(
            fileId=state_doc_id,
            mimeType="text/plain",
        )
    else:
        # Markdown, Plain-Text, etc. → direkt herunterladen
        request = drive_service.files().get_media(
            fileId=state_doc_id,
            supportsAllDrives=True,
        )

    # Content holen — nur EINMAL execute() rufen, dann auf bytes-Ebene weiterarbeiten
    content_bytes = request.execute()
    if not isinstance(content_bytes, bytes):
        # Drive-API hat schon string zurückgegeben (sollte selten passieren)
        return content_bytes

    # Encoding-Strategie: erst UTF-8 (Standard), dann cp1252 (Windows-Editoren),
    # dann latin-1 (kann ALLE 256 Byte-Werte decoden, garantiert kein Crash).
    # latin-1 ist eine Verlustfreie-Decoding-Strategie, falls ungewöhnliche
    # Encodings im STATE-File stecken.
    import logging
    for encoding in ("utf-8", "cp1252"):
        try:
            return content_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue

    # latin-1 als letzter Ausweg — kann nie fehlschlagen
    logging.warning(
        "STATE-Doc weder UTF-8 noch cp1252. Fallback auf latin-1. "
        "Bitte STATE-Doc auf UTF-8 umstellen für korrekte Sonderzeichen-Anzeige."
    )
    return content_bytes.decode("latin-1")


# ============================================================
# WATCHLIST PARSER
# ============================================================

def _strip_markdown_escapes(text: str) -> str:
    """Entfernt Backslash-Escapes vor Markdown-Sonderzeichen.

    Google Docs gibt Markdown-Inhalte mit Escapes wie \\#, \\>, \\<, \\*
    zurück. text/plain-Export der Drive-API kann das auch enthalten.
    Wir normalisieren hier, damit der eigentliche Parser sich nicht damit
    rumschlagen muss.
    """
    # Reihenfolge: Mehrzeichen-Sequenzen zuerst, dann Einzelzeichen
    replacements = [
        ("\\#", "#"),
        ("\\>", ">"),
        ("\\<", "<"),
        ("\\*", "*"),
        ("\\_", "_"),
        ("\\`", "`"),
        ("\\[", "["),
        ("\\]", "]"),
        ("\\(", "("),
        ("\\)", ")"),
        ("\\-", "-"),
        ("\\.", "."),
        ("\\~", "~"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def parse_watchlist(state_text: str) -> list[WatchlistEntry]:
    """Extrahiert die Watchlist-Tabelle aus dem STATE-Markdown."""
    state_text = _strip_markdown_escapes(state_text)
    # Sektion suchen: '## Watchlist-Trigger (aktive Einträge)'
    # Mehrere Varianten probieren, weil Encoding/Whitespace-Variationen vorkommen
    section_pattern = re.compile(
        r"##\s*Watchlist-Trigger\s*\(aktive\s*Einträge\)",
        re.IGNORECASE,
    )
    match = section_pattern.search(state_text)
    if not match:
        # Fallback 1: ohne Suffix '(aktive Einträge)'
        match = re.search(r"##\s*Watchlist-Trigger", state_text, re.IGNORECASE)
    if not match:
        # Fallback 2: nur 'Watchlist' alleinstehend
        match = re.search(
            r"##\s*Watchlist[\s\-]",
            state_text,
            re.IGNORECASE,
        )
    if not match:
        # Diagnose-Info ins Error-Logging schreiben
        import logging
        all_h2 = re.findall(r"^##\s+.+$", state_text, re.MULTILINE)
        logging.error(
            f"Watchlist-Trigger-Sektion nicht gefunden. "
            f"Gefundene H2-Header im STATE: {all_h2[:10]}"
        )
        raise ValueError(
            "Watchlist-Trigger-Sektion nicht im STATE gefunden — "
            f"siehe Logs für Liste der erkannten Header"
        )

    # Ab Sektionsanfang bis nächste H2-Überschrift suchen
    section_start = match.end()
    next_section = re.search(r"\n##\s+\w", state_text[section_start:])
    section_end = (
        section_start + next_section.start() if next_section else len(state_text)
    )
    section_text = state_text[section_start:section_end]

    entries: list[WatchlistEntry] = []
    lines = section_text.splitlines()
    in_table = False
    for line in lines:
        stripped = line.strip()
        # Tabellen-Zeilen erkennen: starten mit "|"
        if not stripped.startswith("|"):
            continue
        # Header und Separator-Zeilen überspringen
        if "Kandidat" in stripped and "Symbol" in stripped:
            in_table = True
            continue
        if re.match(r"^\|\s*[-:]+\s*\|", stripped):
            continue
        if not in_table:
            continue
        # Zeilen mit < 5 Pipes sind keine Datenzeilen
        cols = [c.strip() for c in stripped.split("|")]
        # erstes und letztes element sind leer durch leading/trailing pipe
        cols = [c for c in cols if c != ""]
        if len(cols) < 5:
            continue

        name, symbol, direction, trigger_raw, status_full = cols[:5]

        # Status-Wert + Note trennen: "⚠️ aktiv — Note #9"
        status_key, status_note = _parse_status_field(status_full)
        if status_key in IGNORED_STATUSES:
            # Tot-Eintrag, gehört eigentlich in Archiv — ignorieren
            continue
        if status_key not in ACTIVE_STATUSES:
            # Unerkannter Status — defensiv überspringen
            continue

        # Datum-Constraint extrahieren wenn "nach YYYY-MM-DD" im Trigger
        earliest_date = _parse_earliest_date(trigger_raw)

        # Einzelne Trigger (A, B) parsen
        triggers = _parse_triggers(trigger_raw)

        entries.append(WatchlistEntry(
            name=name,
            symbol=symbol,
            direction=direction.upper(),
            trigger_raw=trigger_raw,
            status=status_key,
            status_note=status_note,
            triggers=triggers,
            earliest_date=earliest_date,
        ))

    return entries


def _parse_status_field(status_full: str) -> tuple[str, str]:
    """Extrahiert Status-Schlüssel aus Feld wie '⚠️ aktiv — Note #9'.

    Zurückgegebene Schlüssel sind alphanumerisch (z.B. 'aktiv', 'pending').
    """
    # Emojis/Sonderzeichen am Anfang entfernen
    cleaned = re.sub(r"^[^\w]+", "", status_full).strip()
    # Bis zum Trennstrich oder Ende
    parts = re.split(r"\s+[—–-]\s+", cleaned, maxsplit=1)
    status_token = parts[0].strip().lower()
    note = parts[1].strip() if len(parts) > 1 else ""

    # Status-Token mappen
    if "aktiv" in status_token:
        return "aktiv", note
    if "pending" in status_token:
        return "pending", note
    if "paused" in status_token:
        return "paused", note
    if "beobachten" in status_token:
        return "beobachten", note
    if "gelaufen" in status_token:
        return "gelaufen", note
    if "these" in status_token or "geplatzt" in status_token:
        return "these_geplatzt", note
    if "chart" in status_token:
        return "chart_not", note
    return status_token, note


def _parse_earliest_date(trigger_raw: str) -> Optional[date]:
    """Extrahiert ISO-Datum aus 'nach YYYY-MM-DD' im Trigger-Text."""
    m = re.search(r"nach\s+(\d{4}-\d{2}-\d{2})", trigger_raw)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def _parse_triggers(trigger_raw: str) -> list[ParsedTrigger]:
    """Splittet einen Trigger-Text in einzelne Trigger A, B, ...

    Format-Beispiele die wir abdecken:
    - "A: Touch EMA50 Daily 33,40–33,60€ + Bounce · B: Daily-Close >35,10€ auf Vol ≥30D-Ø"
    - "Pullback ~59$ + 4h-Reversal (nach Gap +28.9%)"
    - "Reverse-Close ≥25,70€ ODER Hammer TH ≥25,70€"
    - "ONBERG-Story (Defense/Drohnenabwehr) — Setup ergänzen wenn relevant"
    """
    # Erst nach Trigger-Labels splitten ("A:", "B:")
    labeled = re.split(r"·\s*", trigger_raw)
    triggers: list[ParsedTrigger] = []
    for chunk in labeled:
        chunk = chunk.strip()
        if not chunk:
            continue
        # Label am Anfang: "A: ..." oder "B: ..."
        label_match = re.match(r"^([A-Z]):\s*", chunk)
        if label_match:
            label = label_match.group(1)
            content = chunk[label_match.end():].strip()
        else:
            label = ""
            content = chunk

        triggers.append(_parse_single_trigger(label, content))

    return triggers


def _parse_single_trigger(label: str, content: str) -> ParsedTrigger:
    """Parst einen einzelnen Trigger-Text in ParsedTrigger."""
    pt = ParsedTrigger(label=label, raw=content)

    # Modifikatoren erkennen (Reihenfolge: spezifisch zuerst)
    if re.search(r"\+\s*(Bounce|Reversal|Stabilisierung)\b", content, re.IGNORECASE):
        pt.require_bounce = True
    if re.search(r"Vol\s*[≥>]\s*30D[-\s]?Ø", content):
        pt.require_volume = True
    if re.search(r"\bHammer\b", content, re.IGNORECASE):
        pt.require_hammer = True

    # RSI-Bedingungen
    rsi_max_match = re.search(r"RSI[^<>]*<\s*(\d+)", content)
    if rsi_max_match:
        pt.rsi_max = float(rsi_max_match.group(1))
    rsi_min_match = re.search(r"RSI[^<>]*>\s*(\d+)", content)
    if rsi_min_match:
        pt.rsi_min = float(rsi_min_match.group(1))

    # EMA-Referenzen
    ema_match = re.search(r"\bEMA\s*(\d+)\b", content)
    if ema_match:
        pt.ema_ref = f"EMA{ema_match.group(1)}"

    # Preis-Korridor: "33,40–33,60€" oder "147,50-149,00$"
    range_match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*[–-]\s*(\d+(?:[.,]\d+)?)\s*[€$]",
        content,
    )
    if range_match:
        pt.price_low = _parse_eu_number(range_match.group(1))
        pt.price_high = _parse_eu_number(range_match.group(2))
        pt.price_op = "in_range"
        return pt

    # Single-Preis mit Operator: ">35,10€", "<36,85$", "≥25,70€"
    single_op_match = re.search(
        r"([<>≥≤])\s*(\d+(?:[.,]\d+)?)\s*[€$]",
        content,
    )
    if single_op_match:
        op = single_op_match.group(1)
        if op in ("≥", ">"):
            pt.price_op = ">"
        elif op in ("≤", "<"):
            pt.price_op = "<"
        pt.price_single = _parse_eu_number(single_op_match.group(2))
        return pt

    # Approx-Preis: "~167€", "~5,17€"
    approx_match = re.search(
        r"~\s*(\d+(?:[.,]\d+)?)\s*[€$]",
        content,
    )
    if approx_match:
        pt.price_single = _parse_eu_number(approx_match.group(1))
        pt.price_op = "approx"
        return pt

    return pt


def _parse_eu_number(s: str) -> float:
    """Konvertiert deutschen Zahlen-String '33,40' nach 33.4."""
    return float(s.replace(",", "."))


# ============================================================
# FILTER-OVERRIDE PARSER (Sektion 4)
# ============================================================

def parse_filter_overrides(state_text: str) -> list[FilterOverride]:
    """Extrahiert die FILTER-OVERRIDE-Tabelle aus Sektion 4."""
    state_text = _strip_markdown_escapes(state_text)
    section_match = re.search(r"##\s*FILTER-OVERRIDE", state_text, re.IGNORECASE)
    if not section_match:
        return []

    section_start = section_match.end()
    next_section = re.search(r"\n##\s+\w", state_text[section_start:])
    section_end = (
        section_start + next_section.start() if next_section else len(state_text)
    )
    section_text = state_text[section_start:section_end]

    overrides: list[FilterOverride] = []
    in_table = False
    for line in section_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if "Ticker" in stripped and "Override" in stripped:
            in_table = True
            continue
        if re.match(r"^\|\s*[-:]+\s*\|", stripped):
            continue
        if not in_table:
            continue
        cols = [c.strip() for c in stripped.split("|") if c.strip()]
        if len(cols) < 4:
            continue

        symbol, override_type, reason, valid_until_str = cols[:4]
        try:
            valid_until = date.fromisoformat(valid_until_str)
        except ValueError:
            valid_until = None
        overrides.append(FilterOverride(
            symbol=symbol,
            override_type=override_type.replace(" ", "_"),
            reason=reason,
            valid_until=valid_until,
        ))

    return overrides


# ============================================================
# TICKER-MAP PARSER (Sektion 1)
# ============================================================

def parse_ticker_map(state_text: str) -> dict[str, str]:
    """Liest die TICKER-MAP-Tabelle: name -> yahoo_symbol."""
    state_text = _strip_markdown_escapes(state_text)
    section_match = re.search(r"##\s*TICKER-MAP", state_text, re.IGNORECASE)
    if not section_match:
        return {}

    section_start = section_match.end()
    next_section = re.search(r"\n##\s+\w", state_text[section_start:])
    section_end = (
        section_start + next_section.start() if next_section else len(state_text)
    )
    section_text = state_text[section_start:section_end]

    mapping: dict[str, str] = {}
    in_table = False
    for line in section_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if "Wert" in stripped and "Yahoo-Symbol" in stripped:
            in_table = True
            continue
        if re.match(r"^\|\s*[-:]+\s*\|", stripped):
            continue
        if not in_table:
            continue
        cols = [c.strip() for c in stripped.split("|") if c.strip()]
        if len(cols) < 2:
            continue
        mapping[cols[0]] = cols[1]
    return mapping
