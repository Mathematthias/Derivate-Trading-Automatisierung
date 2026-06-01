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
    expiry_date: Optional[date] = None  # Verfallsdatum (Spalte H, Patch 5)


@dataclass
class ParsedTrigger:
    """Ein einzelner Trigger (A, B, ...) eines Watchlist-Eintrags."""

    label: str  # "A", "B", oder "" wenn unbenannt
    raw: str  # vollständiger Trigger-Text

    # Journal-Gate-Emoji (3-Trigger-Schema, 2026-05-23): das 🚦-Ampel-Emoji
    # aus dem Watchlist-Sheet — 🟢 scharf / 🟡 beobachten / ⏳ wartet / 🔴 tot.
    # watchlist_sync schreibt es als Präfix direkt vor den A)/B)/C)-Marker;
    # die filter_engine überspringt 🔴- und ⏳-Trigger bei der Auswertung.
    # None = kein Gate im Trigger-Text (Alt-STATE-Docs / ·-Fallback).
    gate: Optional[str] = None

    # Preis-Komponenten
    price_low: Optional[float] = None
    price_high: Optional[float] = None
    price_single: Optional[float] = None  # bei z.B. ">35,10€"
    price_op: Optional[str] = None  # "<", ">", "in_range", "approx"

    # Indikator-Bezüge (für später, falls nicht direkt im Korridor)
    ema_ref: Optional[str] = None  # "EMA20", "EMA50", "EMA200"

    # Modifikatoren
    require_bounce: bool = False  # "+ Bounce" oder "+ Reversal"
    require_volume: bool = False  # "Vol ≥30D-Ø", "Vol >Avg-20d", "Vol ≥ 1,2× Avg" etc.
    vol_multiplier: Optional[float] = None  # bei "1,2× Avg" → 1.2; bei "≥30D-Ø" → None (= 1.0)
    require_hammer: bool = False  # "Hammer" / "Reverse-Close"
    # Verdeckt-BEREIT-Blindfleck (2026-06-01): Timeframe der Reverse-/Bounce-
    # Bedingung. "4h" = explizit auf Sub-Daily spezifiziert → der Daily-
    # Kerzen-Check im filter_engine kann sie NICHT abbilden und darf darum
    # nicht als harter Block (NAHE) zählen, sondern als manueller 4h-Handcheck
    # (→ conditions_pending → BEREIT*). None = Daily/Default, harter Block bleibt.
    reverse_tf: Optional[str] = None
    is_touch: bool = False  # "Daily-Touch ...", "Touch EMA50 ..." — Punkt-Touch-Logik
    rsi_max: Optional[float] = None  # "RSI<60"
    rsi_min: Optional[float] = None

    # Zonen-Semantik (Task 5, 2026-05-22): wie ist eine Trigger-Zone zu lesen,
    # wenn der Kurs ÜBER der Obergrenze steht?
    #   "breakout" → durchgelaufen, R:R erodiert, Setup tot
    #   "pullback" → Rücksetzer noch nicht tief genug, weiter warten
    #   None       → unbekannt → Evaluator behält Alt-Verhalten (kein Durchgelaufen-Check)
    zone_kind: Optional[str] = None

    # Stop-Loss (Lektion-4-SL-Guard, 2026-05-22, Note #88/#89/#92):
    #   sl_kind = 'fix'           → numerisches Fix-Level, sl_value gesetzt
    #   sl_kind = 'entry_relativ' → SL ist 1,5×ATR ab Entry → per Definition konform
    #   sl_kind = 'pattern'       → SL als Kerzen-/ATR-4h-/Prozent-Funktion → 1D-ATR-Check n/a
    #   sl_kind = None            → kein SL im Trigger-Text gefunden
    # Der filter_engine-Check rechnet nur bei sl_kind='fix' SL-Abstand ÷ ATR(14).
    sl_kind: Optional[str] = None
    sl_value: Optional[float] = None


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
            mimeType="text/markdown",
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
    """Entfernt Backslash-Escapes vor Markdown-Sonderzeichen — iterativ.

    Google Docs gibt Markdown-Inhalte mit Escapes wie \\#, \\>, \\<, \\*
    zurück. text/plain-Export der Drive-API kann das auch enthalten.

    ITERATIV (Note #68 Round 2, 2026-05-19): Bei jedem erfolgreichen
    Read/Write-Cycle escaped Drive die bereits escapeten Backslashes
    erneut, was zu exponentieller Eskalation führt (\\~ → \\\\~ → \\\\\\\\~ ...).
    Aktuelles STATE-Doc hatte 12 Backslashes vor `~`. Iterativ strippen
    bis Konvergenz, max 30 Iterationen als Safety-Belt.

    Reihenfolge pro Iteration: erst `\\\\` → `\\` (Backslash-Backslash zu
    einem), dann einzelne `\\<sonderzeichen>` → `<sonderzeichen>`.
    """
    specials = "#><*_`[]().~-"
    prev = None
    iterations = 0
    while prev != text and iterations < 30:
        prev = text
        # Erst: doppelte Backslashes auflösen
        text = text.replace("\\\\", "\\")
        # Dann: einzelne Escape-Sequenzen
        for char in specials:
            text = text.replace(f"\\{char}", char)
        iterations += 1
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
        # An nicht-escapten Pipes splitten — ein escaptes `\|` gehört zum
        # Zellinhalt (z.B. die (a)/(b)/(c)-Aufzählung in einem Trigger-Text)
        # und darf die Spaltenzuordnung nicht verschieben. Danach `\|` → `|`
        # un-escapen. watchlist_sync escaped beim Rendern jede Zelle; ohne
        # dieses Gegenstück verlöre die Pipeline jeden Eintrag mit Pipe im
        # Trigger-Feld still (Sanity-Count zählt Zeilen, nicht Spalten).
        cols = [
            c.strip().replace("\\|", "|")
            for c in re.split(r"(?<!\\)\|", stripped)
        ]
        # Nur die durch die Rand-Pipes erzeugten Leer-Zellen am Anfang/Ende
        # entfernen — INNERE Leerzellen behalten (die Verfall-Spalte darf
        # leer sein, sonst verschiebt sich die Spaltenzuordnung). Patch 5.
        if cols and cols[0] == "":
            cols = cols[1:]
        if cols and cols[-1] == "":
            cols = cols[:-1]
        if len(cols) < 5:
            continue

        name, symbol, direction, trigger_raw, status_full = cols[:5]

        # 6. Spalte Verfall — nur in neuen STATE-Docs vorhanden (Patch 5).
        # Alte 5-Spalten-Tabellen liefern hier nichts → expiry_date bleibt None.
        expiry_raw = cols[5] if len(cols) >= 6 else ""
        expiry_date: Optional[date] = None
        if expiry_raw:
            try:
                expiry_date = date.fromisoformat(expiry_raw)
            except ValueError:
                expiry_date = None

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
            expiry_date=expiry_date,
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


def _strip_sl_tp(text: str) -> str:
    """Entfernt SL/TP/R:R/ATR-Hinweise aus einem Trigger-Chunk, damit sie
    nicht als Preis-Operator missgedeutet werden.

    Beispiele:
    - "Daily-Close >380$. SL <370$. TP1 392$, TP2 404$. R:R 1,2 / 2,4"
      → "Daily-Close >380$.  .  ,  . "
    - "→ SL <51,50$ (unter 52W-Tief), TP1 56,13$ (R:R ~2,5)"
      → "→  (unter 52W-Tief),  ( ~2,5)"  (R:R-Anker weg, "~2,5" ohne € unschädlich)
    """
    # SL <X€ / SL X€ / SL ≤X% etc. — \b verhindert Treffer mitten in Wörtern
    text = re.sub(
        r"\bSL\s*[<>≤≥]?\s*-?\d+(?:[.,]\d+)?\s*[€$%]?",
        "",
        text,
    )
    # TP1 X€, TP X€, TP2 X$ etc.
    text = re.sub(
        r"\bTP\d*\s*[<>≤≥]?\s*-?\d+(?:[.,]\d+)?\s*[€$%]?",
        "",
        text,
    )
    # R:R 1,2 / 2,4  oder  R:R ~2,5  oder  R:R primär 1,8
    text = re.sub(
        r"\bR:R\b(?:\s+\w+)?\s*[~≈]?\s*\d+(?:[.,]\d+)?(?:\s*/\s*\d+(?:[.,]\d+)?)?",
        "",
        text,
    )
    # ATR-Hinweise wie "(-1,2ATR)" oder "-1.2ATR"
    text = re.sub(r"-?\d+[.,]\d+\s*ATR\b", "", text)
    return text


# 🚦-Ampel-Emojis des Watchlist-Schemas — als Character-Class für den Splitter.
_GATE_EMOJI_CLASS = "🟢🟡⏳🔴"


def _split_into_triggers(trigger_raw: str) -> list[tuple[str, str, str]]:
    """Splittet einen Trigger-Text in [(gate, label, content), ...].

    `gate` ist das optionale 🚦-Ampel-Emoji (🟢/🟡/⏳/🔴), das watchlist_sync
    im 3-Trigger-Schema direkt vor den A)/B)/C)-Marker schreibt — leerer
    String, wenn keins vorhanden ist (Alt-STATE-Docs, ·-Fallback).

    Erkennt Label-Marker (A:, A), Trigger A:, Trigger A)) und den alten
    ·-Separator. Vermeidet false Matches auf Phrasen wie "Trigger A (Pullback"
    (kein `:` oder `)` direkt hinter dem Buchstaben).

    Whitelist auf A–E, damit "R:R", "Q4", etc. nicht als Label getriggert werden.
    """
    # Label-Marker: Anker, optionales Gate-Emoji, optional "Trigger ", dann
    # A–E, dann ) oder :, dann Whitespace.
    label_pattern = re.compile(
        r"(?:^|[\s\.:])([" + _GATE_EMOJI_CLASS + r"]\s*)?(?:Trigger\s+)?([A-E])[\)\:]\s+"
    )
    matches = list(label_pattern.finditer(trigger_raw))

    if matches:
        result: list[tuple[str, str, str]] = []
        for i, m in enumerate(matches):
            gate = (m.group(1) or "").strip()
            label = m.group(2)
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(trigger_raw)
            # `·` mit in den rstrip-Satz: beim ` · `-Join der Trigger landet das
            # Trennzeichen sonst am Chunk-Ende des vorhergehenden Triggers.
            chunk = trigger_raw[start:end].strip().rstrip(".,;:· ")
            if chunk:
                result.append((gate, label, chunk))
        return result

    # Kein Label-Marker: alter ·-Separator als Fallback
    parts = re.split(r"\s+·\s+", trigger_raw)
    return [("", "", p.strip()) for p in parts if p.strip()]


def _parse_triggers(trigger_raw: str) -> list[ParsedTrigger]:
    """Splittet einen Trigger-Text in einzelne Trigger A, B, ...

    Format-Beispiele die wir abdecken:
    - "A: Touch EMA50 Daily 33,40–33,60€ + Bounce · B: Daily-Close >35,10€ auf Vol ≥30D-Ø"
    - "A) Reverse-Kerze (Hammer) ~240€ + RSI 1D <35 + Volumen ≥ 0,9× Avg"
    - "Trigger A: 4h-Bearish-Engulfing ODER Reverse-Close in Zone ..."
    - "Pullback ~59$ + 4h-Reversal (nach Gap +28.9%)"
    - "Reverse-Close ≥25,70€ ODER Hammer TH ≥25,70€"
    """
    chunks = _split_into_triggers(trigger_raw)
    triggers: list[ParsedTrigger] = []
    for gate, label, content in chunks:
        triggers.append(_parse_single_trigger(label, content, gate))
    return triggers


def _detect_zone_kind(content: str) -> Optional[str]:
    """Bestimmt die Zonen-Semantik eines Triggers (Task 5 — Hybrid-Ansatz C).

    Reihenfolge:
    1. Expliziter Tag `[breakout]` / `[pullback]` (auch `-zone`-Suffix) — Vorrang.
    2. Schlüsselwort-Heuristik als Fallback — greift NUR bei Eindeutigkeit:
       breakout-Wörter XOR pullback-Wörter. Bei beiden oder keinem → None.
    3. None → Evaluator behält Alt-Verhalten (kein Durchgelaufen-Check).

    None ist die sichere Rückfallebene: lieber keine Durchgelaufen-Logik als
    eine falsch geratene — ein falsches zone_kind bedeutet entweder "totes
    Setup erscheint als BEREIT" oder "lebender Pullback wird totgesagt".
    """
    # 1. Expliziter Tag — hat immer Vorrang
    tag = re.search(r"\[\s*(breakout|pullback)(?:-zone)?\s*\]", content, re.IGNORECASE)
    if tag:
        return tag.group(1).lower()

    # 2. Heuristik — bewusst konservativ, nur bei Eindeutigkeit
    has_breakout = bool(re.search(r"\b(?:breakout|ausbruch)\w*", content, re.IGNORECASE))
    has_pullback = bool(re.search(r"\b(?:pullback|touch|r[uü]cksetzer)\w*", content, re.IGNORECASE))
    if has_breakout and not has_pullback:
        return "breakout"
    if has_pullback and not has_breakout:
        return "pullback"

    # 3. Mehrdeutig oder kein Marker → None
    return None


def _extract_sl(content: str) -> tuple[Optional[str], Optional[float]]:
    """Extrahiert SL-Art und ggf. SL-Level aus einem Trigger-Chunk.

    Lektion-4-SL-Guard (Note #88/#89/#92, 2026-05-22). Drei erkennbare Fälle
    plus None:

    1. **entry-relativ** — Text enthält `entry-relativ` oder `Entry ±1,5×ATR`.
       → ('entry_relativ', None). Per Konstruktion 1,5×ATR ab Entry → konform.
    2. **Pattern/Sonder-Konvention** — SL als Funktion einer Kerze
       (`SL = Reverse-Kerzen-Hoch + 1,0×ATR-4h`), ATR-4h-Konvention oder
       prozentualer SL (`SL 5%`). → ('pattern', None). 1D-ATR-Check nicht
       anwendbar → der filter_engine markiert das als 'skip'.
    3. **Fix-Level** — `SL <245€` / `SL >3,55$` / `SL 232`. Operator und
       Währungssuffix optional, deutsche Dezimalkomma-Notation wird beachtet.
       → ('fix', float).
    4. Kein SL im Text → (None, None).

    Reihenfolge ist wichtig: entry-relativ zuerst (kann das Wort ATR enthalten),
    dann Pattern, dann numerisches Fix-Level. Ein parenthetischer Kommentar wie
    `SL <125€ (unter 52W-Tief)` bleibt korrekt 'fix' — das Fix-Muster wird am
    Anfang des SL-Ausdrucks verankert geprüft, der Klammerzusatz ignoriert.
    """
    # 1. entry-relativ — höchste Priorität
    if re.search(r"entry[\s\-]?relativ", content, re.IGNORECASE):
        return ("entry_relativ", None)
    if re.search(
        r"\bEntry\s*[-−+±]\s*\d+(?:[.,]\d+)?\s*[×x]?\s*ATR",
        content,
        re.IGNORECASE,
    ):
        return ("entry_relativ", None)

    # SL-Ausdruck isolieren: ab 'SL' (optional ':'/'=') bis Satz-/Token-Grenze.
    m = re.search(
        r"\bSL\b\s*[:=]?\s*(.*?)(?:\.\s|;|$|\bTP\d|\bR:R\b)",
        content,
        re.IGNORECASE | re.DOTALL,
    )
    if not m or not m.group(1).strip():
        return (None, None)
    sl_expr = m.group(1).strip()

    # 2. Pattern/Sonder-Konvention — kerzenbasiert oder ATR-4h
    if re.search(r"ATR", sl_expr, re.IGNORECASE) and re.search(
        r"4h", sl_expr, re.IGNORECASE
    ):
        return ("pattern", None)
    if re.search(
        r"Kerze|Hammer|Reverse|Wick|Docht|Engulfing",
        sl_expr,
        re.IGNORECASE,
    ):
        return ("pattern", None)

    # 3. Fix-Level — Operator/Währung optional, am Anfang des SL-Ausdrucks
    fix = re.match(
        r"[<>≤≥]?\s*(-?\d+(?:[.,]\d+)?)\s*([€$%]?)",
        sl_expr,
    )
    if fix:
        if fix.group(2) == "%":
            # prozentualer SL: relativ, kein numerisches Fix-Level → skip
            return ("pattern", None)
        try:
            return ("fix", _parse_eu_number(fix.group(1)))
        except ValueError:
            return (None, None)

    # SL-Ausdruck beginnt nicht numerisch (z.B. '= EMA200', 'unter Vortagstief')
    return ("pattern", None)


def _parse_single_trigger(label: str, content: str, gate: str = "") -> ParsedTrigger:
    """Parst einen einzelnen Trigger-Text in ParsedTrigger.

    `content` enthält den vollen Trigger inkl. SL/TP/R:R/ATR-Hinweisen.
    `gate` ist das optionale 🚦-Ampel-Emoji des 3-Trigger-Schemas (leerer
    String → kein Gate). Die Preis-Heuristiken arbeiten auf einer SL/TP-
    bereinigten Variante, damit z.B. "Daily-Close >380$. SL <370$" nicht
    "<370$" als price_op fängt. Modifikator-Erkennung (Bounce, Vol, Hammer,
    RSI, EMA) läuft weiter auf dem rohen content, weil dort nichts kollidiert.
    """
    pt = ParsedTrigger(label=label, raw=content, gate=gate or None)

    # Zonen-Semantik bestimmen (Task 5) — Hybrid: Tag mit Vorrang, sonst Heuristik
    pt.zone_kind = _detect_zone_kind(content)

    # SL-Art + ggf. Fix-Level extrahieren (Lektion-4-SL-Guard, 2026-05-22)
    pt.sl_kind, pt.sl_value = _extract_sl(content)

    # === Modifikatoren auf RAW content (kollidieren nicht mit SL/TP) ===

    if re.search(r"\+\s*(Bounce|Reversal|Stabilisierung)\b", content, re.IGNORECASE):
        pt.require_bounce = True

    # Vol-Erkennung — breit gefasst:
    #   "Vol ≥30D-Ø", "auf Vol ≥30D-Ø"           (alt)
    #   "Vol >Avg-30d", "Volumen >Avg-20d"       (Avg-Nd)
    #   "Volumen ≥ 1,2× Avg-20d"                 (Multiplier + Avg)
    #   "Volumen ≥ 0,9× Avg"                     (Multiplier ohne -Nd)
    vol_match = re.search(
        r"Vol(?:umen)?\s*[≥>=]+\s*"
        r"(?:(\d+(?:[.,]\d+)?)\s*[×x]\s*)?"          # optionaler Multiplier
        r"(?:30D|Avg|Average|Ø)",
        content,
    )
    if vol_match:
        pt.require_volume = True
        if vol_match.group(1):
            try:
                pt.vol_multiplier = _parse_eu_number(vol_match.group(1))
            except ValueError:
                pt.vol_multiplier = None

    if re.search(r"\b(Hammer|Reverse-Close|Bullish-Engulfing|Engulfing|Bounce-Close)\b",
                 content, re.IGNORECASE):
        pt.require_hammer = True

    # Sub-Daily-Reverse-Erkennung (Verdeckt-BEREIT-Blindfleck, 2026-06-01):
    # Ist die Reverse-/Bounce-Bedingung explizit auf 4h spezifiziert
    # ("4h-Reverse-Close", "4h-Bearish-Engulfing", "4h-Reversal",
    # "4h-EMA20-Reclaim"), kann der Daily-Kerzen-Check sie nicht abbilden.
    # Markieren → filter_engine wertet den fehlenden Daily-Reverse dann als
    # manuellen 4h-Handcheck (conditions_pending) statt als harten Block.
    # NUR im Entry-/Bedingungsteil VOR 'SL' suchen, damit ATR-4h-/Kerzen-
    # Referenzen in der SL-Definition keine Falsch-Positive erzeugen
    # (z.B. Daily-Reverse-Trigger mit "SL = Reverse-Hoch + 1,0×ATR-4h").
    _cond_part = re.split(r"\bSL\b", content, maxsplit=1, flags=re.IGNORECASE)[0]
    if (pt.require_hammer or pt.require_bounce) and re.search(
        r"4h[\s\-]{0,3}(?:(?:Bull|Bear)\w*|EMA\d*|SMA\d*)?[\s\-]{0,3}"
        r"(?:Reverse|Reversal|Hammer|Engulf\w*|Bounce-Close|Reclaim)"
        r"|(?:Reverse|Reversal|Hammer|Engulf\w*|Bounce-Close|Reclaim)[^.]{0,20}4h",
        _cond_part, re.IGNORECASE,
    ):
        pt.reverse_tf = "4h"

    # Touch-Operator: "Daily-Touch", "Touch EMA50", "Touch ...€"
    # Wird unten beim Preis-Parsing als is_touch markiert, wenn ein Preis
    # ohne expliziten Operator auftaucht.
    has_touch_word = bool(re.search(r"\bTouch\b", content, re.IGNORECASE))

    # RSI
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

    # === Preis-Heuristiken auf SL/TP-bereinigter Variante ===
    price_text = _strip_sl_tp(content)

    # Preis-Korridor: "33,40–33,60€" oder "147,50-149,00$"
    range_match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*[–-]\s*(\d+(?:[.,]\d+)?)\s*[€$]",
        price_text,
    )
    if range_match:
        pt.price_low = _parse_eu_number(range_match.group(1))
        pt.price_high = _parse_eu_number(range_match.group(2))
        pt.price_op = "in_range"
        return pt

    # Single-Preis mit Operator: ">35,10€", "<36,85$", "≥25,70€", "≤60€"
    single_op_match = re.search(
        r"([<>≥≤])\s*(\d+(?:[.,]\d+)?)\s*[€$]",
        price_text,
    )
    if single_op_match:
        op = single_op_match.group(1)
        if op in ("≥", ">"):
            pt.price_op = ">"
        elif op in ("≤", "<"):
            pt.price_op = "<"
        pt.price_single = _parse_eu_number(single_op_match.group(2))
        return pt

    # Approx-Preis: "~167€", "~5,17€" — mit oder ohne Klammer
    approx_match = re.search(
        r"~\s*(\d+(?:[.,]\d+)?)\s*[€$]",
        price_text,
    )
    if approx_match:
        pt.price_single = _parse_eu_number(approx_match.group(1))
        pt.price_op = "approx"
        if has_touch_word:
            pt.is_touch = True
        return pt

    # Touch-Punkt ohne Operator und ohne ~: "Daily-Touch 52,33$" oder
    # "Touch EMA50 1D 33,40€". Wenn das Touch-Wort drinsteht und ein Preis
    # mit Währung auftaucht, behandeln wir den als Touch-Approx.
    if has_touch_word:
        touch_match = re.search(
            r"(\d+(?:[.,]\d+)?)\s*[€$]",
            price_text,
        )
        if touch_match:
            pt.price_single = _parse_eu_number(touch_match.group(1))
            pt.price_op = "approx"
            pt.is_touch = True
            return pt

    return pt


def _parse_eu_number(s: str) -> float:
    """Konvertiert Zahl-String zu float — robust gegen deutsche und englische Notation.

    Beispiele:
    - "33,40"  → 33.40  (deutsches Dezimalkomma)
    - "1.000"  → 1000   (deutsches Tausendertrennzeichen, 3 Nachkommastellen)
    - "147.50" → 147.50 (englisches Dezimal, 2 Nachkommastellen)
    - "974.41" → 974.41 (englisches Dezimal, 2 Nachkommastellen)
    - "1.000,50" → 1000.50 (deutsche Notation mit Tausender + Dezimal)
    - "1,000.50" → 1000.50 (englische Notation mit Tausender + Dezimal)
    """
    s = s.strip()

    # Fall 1: Komma drin → deutsche Notation
    # "1.000,50" → Punkte sind Tausender, Komma ist Dezimal
    # "33,40"    → nur Komma, ist Dezimal
    if "," in s:
        return float(s.replace(".", "").replace(",", "."))

    # Fall 2: Kein Komma, mehrere Punkte → englische Tausender-Notation
    # "1,000,000" wäre englisch, aber wir hätten dann ein Komma gesehen
    # Hier: "1.000.000" wäre theoretisch möglich (deutsch ohne Dezimal), selten
    if s.count(".") > 1:
        return float(s.replace(".", ""))

    # Fall 3: Genau ein Punkt — Heuristik nach Anzahl Nachkommastellen
    if "." in s:
        parts = s.split(".")
        # Genau 3 Nachkommastellen → wahrscheinlich Tausender im deutschen Format
        # "1.000" → 1000, "974.413" wäre selten und müsste explizit konsistent sein
        if len(parts[1]) == 3 and len(parts[0]) <= 3:
            return float(s.replace(".", ""))
        # Sonst Dezimalpunkt
        return float(s)

    # Fall 4: Keine Trennzeichen
    return float(s)


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
