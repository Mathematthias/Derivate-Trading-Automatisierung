"""
pipeline_utils.py — Helper für Phase-4-Pipeline-Integration.

Parst die von der GitHub-Action erzeugten Markdown-Files (MARKETDATA-FULL,
CANDIDATES) aus dem Workspace Drive und liefert strukturierte Daten an die
Routinen 7 (Morgen-Briefing), 8 (News-Scan), 8b (Hidden Catalyst) und
8c (Insider-Verkäufe).

Drive-Aufruf passiert im Tool-Calling-Layer (außerhalb dieses Moduls). Die
Funktionen erwarten den File-Content als String und die Drive-Metadata als
Dict. Vollständiges Workflow-Beispiel: references/pipeline-integration.md.

Konventionen:
- Drive-`read_file_content` liefert escaped Markdown (\\#\\#) — wird via
  _unescape_drive_markdown bereinigt. Alternativ liefert
  `download_file_content` saubere Bytes (utf-8); dann ist das Unescaping
  unnötig (idempotent — kann trotzdem aufgerufen werden).
- Alle Timestamps werden als UTC verarbeitet, Drive liefert ISO-8601 mit Z.
- Frische-Thresholds und Ausfall-Definition: Konstanten oben.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

# Frische-Schwellen pro Routine (in Minuten). Wenn das jüngste Pipeline-File
# älter ist, wird gewarnt. Werte basieren auf den geplanten Routine-Zeiten:
# - morning_check (08:45 CEST) — letzter Pipeline-Lauf max ~30 Min davor
# - scan_afternoon (15:45 CEST) — letzter Pipeline-Lauf max ~30 Min davor
# - scan_evening (20:30 CEST) — etwas mehr Toleranz nach Xetra-Close
FRESHNESS_THRESHOLDS_MIN: dict[str, int] = {
    "morning_check": 30,
    "scan_afternoon": 30,
    "scan_evening": 60,
}

# Ab dieser Schwelle gilt die Pipeline als ausgefallen — Routine fällt
# komplett auf Web-Fallback zurück und meldet das im Briefing-Header.
AUSFALL_THRESHOLD_HOURS: int = 24

# Drive-Folder-ID des Pipeline-Briefing-Ordners (Workspace Shared Drive
# Trading-Pipeline/Briefing/). Nicht hart benötigt — search_files kann auch
# ohne Parent-Filter laufen — aber spart Treffer in fremden Ordnern.
PIPELINE_DRIVE_PARENT_ID: str = "1_oQBr6KH7u6FDCAUIs1liTnEFjn-b_Ht"

# Sentinel-Ticker, die im "Standard-Universum"-MARKETDATA garantiert vorkommen
# (Indizes + Major Krypto + FX). Werden von classify_universe() benutzt, um
# Standard- von Gamechanger-Hunting-Universum zu unterscheiden, wenn die
# Pipeline parallel beide Läufe in den Briefing-Ordner schreibt.
#
# Hintergrund (Befund 2026-04-26): Pipeline schreibt Sa-Nacht zwei separate
# MARKETDATA-Files mit unterschiedlichen Tickerlisten — der jüngste ist nicht
# automatisch der für Routine 7 (Watchlist-Briefing) relevante. Ohne diese
# Klassifikation würde der Watchlist-Block leer ablaufen, weil ^GDAXI/BTC-EUR
# fehlen.
STANDARD_UNIVERSE_SENTINELS: frozenset[str] = frozenset({
    # Index-Sentinels (mind. eines davon im Standard-Lauf garantiert)
    "^GDAXI", "^MDAXI", "^SDAXI", "^TECDAX", "^STOXX50E",
    "^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX",
    "^N225", "^HSI", "^FTSE",
    # Major-Krypto-Sentinels
    "BTC-EUR", "ETH-EUR", "SOL-EUR", "BNB-EUR",
    # FX-Sentinels
    "EURUSD=X", "EURGBP=X", "USDJPY=X",
    # Rohstoff-Sentinels
    "GC=F", "SI=F", "CL=F", "BZ=F", "NG=F", "HG=F",
})

# Schwelle: ab wie vielen Sentinels im Content gilt der Lauf als Standard?
# Konservativ niedrig (3) — selbst bei Pipeline-Partial-Failures (manche
# Yahoo-Ticker schlagen fehl) sind 3+ aus dem Pool praktisch immer dabei.
STANDARD_UNIVERSE_MIN_HITS: int = 3


# ---------------------------------------------------------------------------
# Datenklassen
# ---------------------------------------------------------------------------


@dataclass
class TickerData:
    """Indikator-Set für einen Ticker aus MARKETDATA-FULL.md."""

    ticker: str
    kurs: float
    change_pct: float
    ema20: float
    ema50: float
    ema200: float
    ema_stack: str  # "bullish" | "bearish" | "neutral"
    rsi: float
    atr: float
    move_30d: float
    low_52w: float
    high_52w: float
    hi_52w_dist: float  # negative Zahl = X% unter Hoch
    lo_52w_dist: float  # positive Zahl = X% über Tief
    low_20d: float
    high_20d: float
    vol_avg_stk: int = 0
    vol_avg_eur: int = 0
    vol_today_ratio: float = 0.0

    # === EMA200-MeanRev-Felder (Note #49, seit 2026-05-08) ===
    # Pipeline-Output-Zeile: `- **EMA200-MeanRev:** Dist=±X.XX% · LastTouch=Nd ·
    # TrendQual=✓/✗ · WeeklyHHHL=✓/✗`. Felder sind Optional, weil
    # Indizes/FX/Krypto die Vorprüfungen oft nicht erfüllen.
    ema200_distance_pct: Optional[float] = None
    days_since_last_ema200_touch: Optional[int] = None
    ema200_trend_qualified: Optional[bool] = None
    weekly_higher_highs_lows: Optional[bool] = None

    # === Earnings-Felder (optional, seit 2026-05-08) ===
    # Pipeline-Output-Zeile: `- **Earnings:** Next=YYYY-MM-DD · Last=YYYY-MM-DD (Nd ago)`
    next_earnings_date: Optional[str] = None
    last_earnings_date: Optional[str] = None
    days_since_last_earnings: Optional[int] = None


@dataclass
class CandidateEntry:
    """Ein Watchlist-Trigger-Eintrag aus CANDIDATES.md."""

    ticker: str
    direction: Optional[str]  # "LONG" | "SHORT" | None
    raw_direction: str
    details: str
    bucket: str  # "bereit" | "very_close" | "close" | "watching" | ...
    expiry: Optional[str] = None  # Verfallsdatum ISO YYYY-MM-DD (Patch 5, #42)


@dataclass
class GamechangerCandidate:
    """Ein Stufe-2-Setup-Kandidat aus GAMECHANGER-HUNT.md.

    Im Gegensatz zu CandidateEntry stammt dieser Eintrag NICHT aus der
    Watchlist, sondern aus einem systematischen Universe-Scan der Pipeline
    nach technischen Setup-Mustern (z.B. Long-Trend-Pullback). Direction
    wird aus dem Setup-Namen abgeleitet.
    """

    ticker: str
    setup: str  # Originalname, z.B. "Long-Trend-Pullback"
    direction: str  # "LONG" | "SHORT" | "NEUTRAL"
    kurs: float
    ema20: float
    distance_pct: float  # Distanz vom EMA20 in % (kann negativ sein)
    rsi: float
    move_30d: float


@dataclass
class GamechangerSnapshot:
    """Ergebnis des GAMECHANGER-HUNT-Parses.

    Note: Filter-Overrides aus dem File werden hier nicht ausgewertet — die
    sind redundant zu CANDIDATES.md, dort kommen sie an.
    """

    timestamp: Optional[str] = None
    candidates_by_setup: dict[str, list[GamechangerCandidate]] = field(
        default_factory=dict
    )

    def all_candidates(self) -> list[GamechangerCandidate]:
        """Flache Liste aller Setup-Kandidaten."""
        return [c for items in self.candidates_by_setup.values() for c in items]

    def find(self, ticker: str) -> Optional[GamechangerCandidate]:
        """Sucht einen Ticker quer durch alle Setup-Buckets."""
        base = ticker.upper().split(".")[0].split("-")[0]
        for items in self.candidates_by_setup.values():
            for c in items:
                c_base = c.ticker.upper().split(".")[0].split("-")[0]
                if c_base == base or c.ticker.upper() == ticker.upper():
                    return c
        return None


@dataclass
class PipelineSnapshot:
    """Ergebnis des Pipeline-Loads — vollständige Sicht für eine Routine."""

    marketdata: dict[str, TickerData] = field(default_factory=dict)
    candidates: dict[str, list[CandidateEntry]] = field(default_factory=dict)
    overrides: list[dict] = field(default_factory=list)
    filter_overrides: list[dict] = field(default_factory=list)
    candidates_timestamp: Optional[str] = None  # Aus File-Header

    # Frische-Status (gefüllt durch load_pipeline)
    marketdata_freshness: Optional[dict] = None
    candidates_freshness: Optional[dict] = None
    fallback_active: bool = False
    fallback_reason: str = ""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _unescape_drive_markdown(text: str) -> str:
    """Entfernt das Backslash-Escaping, das `read_file_content` einbaut.

    Drive's natural-language reader escapt Markdown-Sonderzeichen einmal
    (oder bei einigen Files mehrfach). Wir laufen iterativ bis stabil —
    max. 5 Runden, was in der Praxis nach 2 Iterationen fertig ist.
    Idempotent für saubere Eingaben (z.B. aus `download_file_content`).
    """
    pattern = re.compile(r"\\([#*\-\[\]\(\)>_])")
    for _ in range(5):
        new_text = pattern.sub(r"\1", text)
        if new_text == text:
            break
        text = new_text
    return text


def decode_drive_b64(source: str, out_path: Optional[str] = None) -> str:
    """Dekodiert eine via Drive `download_file_content` geholte Datei.

    `download_file_content` liefert byte-exakte Base64 — der korrekte Weg für
    Pipeline-Files (CANDIDATES/MARKETDATA/GAMECHANGER), weil `read_file_content`
    die Emoji-Bucket-Marker (🎯 📍 🔴 📅) zu Mojibake zerlegt und damit den
    Parser bricht.

    `source` ist ein **Dateipfad** — entweder:
      - eine tool_results-JSON-Datei (große Ergebnisse landen unter
        /mnt/user-data/tool_results/*.json), Form {'content': '<b64>'} ODER
        [{'text': '<json-string mit content>'}], oder
      - eine reine Base64-Textdatei (kleine Ergebnisse, per create_file
        zwischengespeichert).

    NIE mit /dev/stdin oder interaktivem Heredoc arbeiten — das hängt. Immer
    erst in eine echte Datei schreiben, dann diese Funktion mit dem Pfad rufen.

    Returns: dekodierter UTF-8-Text. Schreibt ihn zusätzlich nach `out_path`,
    falls gesetzt.
    """
    import json
    import base64

    raw = open(source, "r", encoding="utf-8").read()
    b64: Optional[str] = None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            b64 = obj.get("content")
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict) and "text" in item:
                    inner = json.loads(item["text"])
                    b64 = inner.get("content") if isinstance(inner, dict) else None
                    if b64:
                        break
    except (json.JSONDecodeError, ValueError):
        b64 = raw  # reine Base64-Datei

    if not b64:
        raise ValueError(f"Kein Base64-'content'-Feld gefunden in {source}")

    text = base64.b64decode(b64).decode("utf-8")
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return text


def parse_marketdata(content: str) -> dict[str, TickerData]:
    """Parst MARKETDATA-FULL.md zu Dict[ticker -> TickerData].

    Erwartet Format:
        ## TICKER

        - **Kurs:** 129.6 (-0.25%)
        - **EMAs:** EMA20=130.7 · EMA50=131.5 · EMA200=119.7 (bullish-Stack ↑)
        - **RSI-14:** 46.0
        - **ATR-14:** 2.472
        - **30d-Move:** +5.90%
        - **52W-Range:** 89.29 – 149.1 (High-Distanz -13.05%, Low-Distanz +45.21%)
        - **20d-Range:** 122.2 – 132.8
        - **Volumen:** Avg-20d 189,832 Stk · 24,611,718 EUR (heute 0.31× avg)

    Tickers ohne **Kurs:**-Zeile werden übersprungen (Pipeline-Lauf evtl. partial).
    """
    content = _unescape_drive_markdown(content)
    result: dict[str, TickerData] = {}

    # Erste Section ist Header — wird durch [1:] verworfen
    sections = re.split(r"\n##\s+", content)

    for section in sections[1:]:
        lines = section.split("\n")
        ticker = lines[0].strip()
        if not ticker or " " in ticker:  # Header-Zeilen ausschließen
            continue

        partial: dict = {"ticker": ticker}

        for line in lines[1:]:
            line = line.strip()
            if not line.startswith("- **"):
                continue

            if m := re.match(r"- \*\*Kurs:\*\* ([\d.]+) \(([+\-][\d.]+)%\)", line):
                partial["kurs"] = float(m.group(1))
                partial["change_pct"] = float(m.group(2))
                continue

            if m := re.match(
                r"- \*\*EMAs:\*\* EMA20=([\d.]+) · EMA50=([\d.]+) · EMA200=([\d.]+)"
                r"(?:\s+\((bullish|bearish)-Stack\s+[↑↓]\))?",
                line,
            ):
                partial["ema20"] = float(m.group(1))
                partial["ema50"] = float(m.group(2))
                partial["ema200"] = float(m.group(3))
                partial["ema_stack"] = m.group(4) or "neutral"
                continue

            if m := re.match(r"- \*\*RSI-14:\*\* ([\d.]+)", line):
                partial["rsi"] = float(m.group(1))
                continue

            if m := re.match(r"- \*\*ATR-14:\*\* ([\d.]+)", line):
                partial["atr"] = float(m.group(1))
                continue

            if m := re.match(r"- \*\*30d-Move:\*\* ([+\-][\d.]+)%", line):
                partial["move_30d"] = float(m.group(1))
                continue

            if m := re.match(
                r"- \*\*52W-Range:\*\* ([\d.]+) – ([\d.]+) "
                r"\(High-Distanz ([+\-][\d.]+)%, Low-Distanz ([+\-][\d.]+)%\)",
                line,
            ):
                partial["low_52w"] = float(m.group(1))
                partial["high_52w"] = float(m.group(2))
                partial["hi_52w_dist"] = float(m.group(3))
                partial["lo_52w_dist"] = float(m.group(4))
                continue

            if m := re.match(r"- \*\*20d-Range:\*\* ([\d.]+) – ([\d.]+)", line):
                partial["low_20d"] = float(m.group(1))
                partial["high_20d"] = float(m.group(2))
                continue

            if m := re.match(
                r"- \*\*Volumen:\*\* Avg-20d ([\d,]+) Stk · ([\d,]+) EUR"
                r"(?: \(heute ([\d.]+)× avg\))?",
                line,
            ):
                partial["vol_avg_stk"] = int(m.group(1).replace(",", ""))
                partial["vol_avg_eur"] = int(m.group(2).replace(",", ""))
                if m.group(3):
                    partial["vol_today_ratio"] = float(m.group(3))
                continue

            # === EMA200-MeanRev-Zeile (Note #49, seit 2026-05-08) ===
            # Format: `- **EMA200-MeanRev:** Dist=+1.25% · LastTouch=180d · TrendQual=✓ · WeeklyHHHL=✓`
            # Einzelne Tokens sind frei kombinierbar (manche fehlen je nach
            # History-Länge). Wir parsen jede Komponente getrennt mit Regex.
            if line.startswith("- **EMA200-MeanRev:**"):
                if mm := re.search(r"Dist=([+\-][\d.]+)%", line):
                    partial["ema200_distance_pct"] = float(mm.group(1))
                if mm := re.search(r"LastTouch=(\d+)d", line):
                    partial["days_since_last_ema200_touch"] = int(mm.group(1))
                if mm := re.search(r"TrendQual=([✓✗])", line):
                    partial["ema200_trend_qualified"] = (mm.group(1) == "✓")
                if mm := re.search(r"WeeklyHHHL=([✓✗])", line):
                    partial["weekly_higher_highs_lows"] = (mm.group(1) == "✓")
                continue

            # === Earnings-Zeile (optional, seit 2026-05-08) ===
            # Format: `- **Earnings:** Next=2026-08-01 · Last=2026-05-06 (2d ago)`
            if line.startswith("- **Earnings:**"):
                if mm := re.search(r"Next=(\d{4}-\d{2}-\d{2})", line):
                    partial["next_earnings_date"] = mm.group(1)
                if mm := re.search(r"Last=(\d{4}-\d{2}-\d{2})", line):
                    partial["last_earnings_date"] = mm.group(1)
                if mm := re.search(r"\((\d+)d ago\)", line):
                    partial["days_since_last_earnings"] = int(mm.group(1))
                continue

        # Mindest-Anforderung: Kurs muss da sein
        if "kurs" not in partial:
            continue

        # Defaults für fehlende Felder
        partial.setdefault("ema_stack", "neutral")
        for k in ("vol_avg_stk", "vol_avg_eur"):
            partial.setdefault(k, 0)
        partial.setdefault("vol_today_ratio", 0.0)

        try:
            result[ticker] = TickerData(**partial)
        except TypeError:
            # Eintrag unvollständig (Pipeline-Lauf hat einen Indikator nicht
            # geliefert) — überspringen, Routine kann Web-Fallback machen.
            continue

    return result


def parse_candidates(content: str) -> PipelineSnapshot:
    """Parst CANDIDATES.md zu PipelineSnapshot (ohne marketdata).

    Sektionen werden anhand ihrer Header-Keywords erkannt — Emojis im Header
    sind ok, weil sie als Unicode kommen. Kandidaten-Zeilen folgen dem
    Pattern: `- **TICKER** (DIRECTION) — Details`.
    """
    content = _unescape_drive_markdown(content)
    snap = PipelineSnapshot()

    # Timestamp aus dem Datei-Header
    if m := re.search(r"#\s+CANDIDATES\s+—\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", content):
        snap.candidates_timestamp = m.group(1)

    # Bucket-Mapping per Header-Keyword
    bucket_keywords: list[tuple[str, list[str]]] = [
        ("bereit", ["BEREIT"]),
        ("very_close", ["Sehr nah am Trigger", "≤2%"]),
        ("close", ["Nah am Trigger", "≤5%"]),
        ("watching", ["Auf Radar", "≤10%"]),
        ("pending", ["Pending", "Datum-Constraint"]),
        ("paused", ["Paused", "temporär nicht"]),
        ("passive", ["Passive"]),
        ("stufe2_neu", ["Stufe 2", "Neue Kandidaten"]),
    ]
    for key, _ in bucket_keywords:
        snap.candidates[key] = []

    # Sections per "## " oder "### " trennen
    sections = re.split(r"\n#{2,4}\s+", content)

    for section in sections:
        if "\n" not in section:
            continue
        first_line, body = section.split("\n", 1)

        # Override-Werte (priority_long/priority_short)
        if "Override-Werte" in first_line:
            snap.overrides.extend(_parse_override_block(body))
            continue

        # Aktive Filter-Overrides
        if "Aktive Filter-Overrides" in first_line:
            snap.filter_overrides.extend(_parse_filter_override_block(body))
            continue

        # Standard-Bucket
        target_key: Optional[str] = None
        for key, keywords in bucket_keywords:
            if any(kw in first_line for kw in keywords):
                target_key = key
                break
        if not target_key:
            continue

        for entry in _parse_candidate_bullets(body, target_key):
            snap.candidates[target_key].append(entry)

    return snap


def _parse_candidate_bullets(body: str, bucket: str) -> list[CandidateEntry]:
    """Extrahiert Kandidaten-Bullets der Form `- **TICKER** (DIR) — Details`."""
    out: list[CandidateEntry] = []

    # Wir suchen Top-Level-Bullets (nicht eingerückt). Jeder Eintrag bis zum
    # nächsten Top-Level-Bullet, Section-Ende oder `---`.
    pattern = (
        r"^-\s+\*\*([A-Z0-9.\-=^]+)\*\*\s*"
        r"(?:\(([^)]+)\))?\s*"
        r"(?:—\s+(.*?))?"
        r"(?=\n-\s+\*\*|\n#{2,4}\s|\n---|\Z)"
    )
    for m in re.finditer(pattern, body, re.MULTILINE | re.DOTALL):
        ticker = m.group(1)
        direction_raw = (m.group(2) or "").strip()
        details = (m.group(3) or "").strip()

        direction: Optional[str] = None
        upper = direction_raw.upper()
        if "LONG" in upper:
            direction = "LONG"
        elif "SHORT" in upper:
            direction = "SHORT"

        # Verfallsdatum aus der Verfall-Unterzeile ziehen (Patch 5, #42).
        # Renderer-Formate: '⏰ Verfall in N HT (YYYY-MM-DD)',
        # '⛔ verfallen (Verfall YYYY-MM-DD)', 'Verfall: YYYY-MM-DD (N HT)'.
        expiry: Optional[str] = None
        if em := re.search(
            r"[Vv]erfall(?:en)?[:\s][^\n]*?(\d{4}-\d{2}-\d{2})", details
        ):
            expiry = em.group(1)

        out.append(
            CandidateEntry(
                ticker=ticker,
                direction=direction,
                raw_direction=direction_raw,
                details=details,
                bucket=bucket,
                expiry=expiry,
            )
        )
    return out


def _parse_override_block(body: str) -> list[dict]:
    """Parst Override-Werte (priority_long/priority_short)."""
    out: list[dict] = []
    pattern = (
        r"^-\s+\*\*([A-Z0-9.\-=^]+)\*\*\s*\(([↑↓])\)"
        r"\s*—\s*(.*?)"
        r"(?=\n-\s+\*\*|\n#{2,4}\s|\n---|\Z)"
    )
    for m in re.finditer(pattern, body, re.MULTILINE | re.DOTALL):
        ticker = m.group(1)
        arrow = m.group(2)
        rest = (m.group(3) or "").strip()
        direction = "LONG" if arrow == "↑" else "SHORT"
        out.append({
            "ticker": ticker,
            "direction": direction,
            "raw": rest,
        })
    return out


def _parse_filter_override_block(body: str) -> list[dict]:
    """Parst Filter-Overrides der Form `- **TICKER** [tag] — Begründung`."""
    out: list[dict] = []
    pattern = (
        r"^-\s+\*\*([A-Z0-9.\-=^]+)\*\*\s*\[(\w+)\]"
        r"\s*—\s*(.*?)"
        r"(?=\n-\s+\*\*|\n#{2,4}\s|\n---|\Z)"
    )
    for m in re.finditer(pattern, body, re.MULTILINE | re.DOTALL):
        out.append({
            "ticker": m.group(1),
            "tag": m.group(2),
            "raw": (m.group(3) or "").strip(),
        })
    return out


def parse_gamechanger(content: str) -> GamechangerSnapshot:
    """Parst GAMECHANGER-HUNT.md zu GamechangerSnapshot.

    Format-Beispiel (Setup-Bullets sind kompakter als CANDIDATES — kein
    `**TICKER** (DIR) —`-Wrapper, stattdessen direkt Indikator-Werte):

        ## Stufe 2 — Neue Kandidaten aus Universe

        ### Long-Trend-Pullback

        - NDX1.DE: 44.94 EMA20=44.94 Dist=-0.00% RSI=53 30d=+4.0%

        ### Short-Trend-Pullback

        - PLTR: 143.09 EMA20=144.04 Dist=-0.66% RSI=49 30d=-7.7%

    Direction wird aus dem Setup-Namen abgeleitet (Long/Short im Setup
    triggert die Richtung). Setup-Namen, die weder Long noch Short enthalten,
    werden mit direction='NEUTRAL' geliefert.

    Hinweis zum File-Header: Aktuell schreibt die Pipeline `# CANDIDATES — ...`
    auch in GAMECHANGER-HUNT-Files (Cosmetic-Bug); der Parser ist robust
    dagegen — er liest den Timestamp unabhängig vom Header-Wort.
    """
    content = _unescape_drive_markdown(content)
    snap = GamechangerSnapshot()

    # Timestamp: akzeptiert sowohl `# GAMECHANGER-HUNT — ...` als auch
    # `# CANDIDATES — ...` als Header (s.o.).
    if m := re.search(
        r"#\s+(?:GAMECHANGER-HUNT|CANDIDATES)\s+—\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2})",
        content,
    ):
        snap.timestamp = m.group(1)

    # Wir brauchen nur den Stufe-2-Block. Die Filter-Overrides ignorieren
    # wir hier — die kommen über CANDIDATES.md.
    stufe2_match = re.search(
        r"##\s+Stufe\s+2\s*—\s*Neue\s+Kandidaten\s+aus\s+Universe(.*?)"
        r"(?=\n##\s+\S|\Z)",
        content,
        re.DOTALL,
    )
    if not stufe2_match:
        return snap

    stufe2_block = stufe2_match.group(1)

    # Sub-Sektionen via "### Setup-Name"
    sub_sections = re.split(r"\n###\s+", stufe2_block)
    for sub in sub_sections[1:]:  # Erste ist Pre-### (leer/Whitespace)
        first_line, *rest = sub.split("\n", 1)
        body = rest[0] if rest else ""

        setup_name = first_line.strip()
        # Direction aus Setup-Namen ableiten
        upper_setup = setup_name.upper()
        if "LONG" in upper_setup:
            direction = "LONG"
        elif "SHORT" in upper_setup:
            direction = "SHORT"
        else:
            direction = "NEUTRAL"

        # Bullet-Format: - TICKER: KURS EMA20=X Dist=±X% RSI=X 30d=±X%
        # Ticker erlaubt . - = ^ Ziffern Buchstaben
        bullet_pattern = (
            r"^-\s+([A-Z0-9.\-=^]+):\s+"
            r"([\d.]+)\s+"
            r"EMA20=([\d.]+)\s+"
            r"Dist=([+\-][\d.]+)%\s+"
            r"RSI=([\d.]+)\s+"
            r"30d=([+\-][\d.]+)%"
        )

        bucket: list[GamechangerCandidate] = []
        for m in re.finditer(bullet_pattern, body, re.MULTILINE):
            try:
                bucket.append(
                    GamechangerCandidate(
                        ticker=m.group(1),
                        setup=setup_name,
                        direction=direction,
                        kurs=float(m.group(2)),
                        ema20=float(m.group(3)),
                        distance_pct=float(m.group(4)),
                        rsi=float(m.group(5)),
                        move_30d=float(m.group(6)),
                    )
                )
            except (ValueError, TypeError):
                continue

        if bucket:
            snap.candidates_by_setup[setup_name] = bucket

    return snap


# ---------------------------------------------------------------------------
# Frische / Lookups
# ---------------------------------------------------------------------------


def freshness_status(
    file_modified_time_iso: Optional[str],
    routine: str,
    now: Optional[datetime] = None,
) -> dict:
    """Bewertet, ob ein Pipeline-File frisch genug für eine Routine ist.

    Args:
        file_modified_time_iso: ISO-Timestamp aus Drive-Metadata (modifiedTime),
            z.B. "2026-04-25T21:36:03.847Z". None bei Datei nicht gefunden.
        routine: 'morning_check' | 'scan_afternoon' | 'scan_evening'
        now: Optional, für Tests einsetzbar.

    Returns:
        dict mit Keys:
          status: 'ok' | 'stale' | 'ausfall' | 'missing'
          age_minutes: Alter in Minuten oder None
          threshold_minutes: Schwelle für diese Routine
          warning_text: Bereit zum Einkleben in Briefing-Header
          file_timestamp_utc: Lesbarer UTC-Timestamp
    """
    if now is None:
        now = datetime.now(timezone.utc)

    threshold = FRESHNESS_THRESHOLDS_MIN.get(routine, 30)
    ausfall_threshold_min = AUSFALL_THRESHOLD_HOURS * 60

    if not file_modified_time_iso:
        return {
            "status": "missing",
            "age_minutes": None,
            "threshold_minutes": threshold,
            "warning_text": "⚠️ Pipeline-File nicht gefunden — Web-Fallback aktiv.",
            "file_timestamp_utc": None,
        }

    ts = datetime.fromisoformat(file_modified_time_iso.replace("Z", "+00:00"))
    age_min = int((now - ts).total_seconds() / 60)
    ts_str = ts.strftime("%Y-%m-%d %H:%M UTC")

    if age_min > ausfall_threshold_min:
        return {
            "status": "ausfall",
            "age_minutes": age_min,
            "threshold_minutes": threshold,
            "warning_text": (
                f"⚠️ Pipeline-File {age_min // 60}h alt (letzter Lauf {ts_str}). "
                "Möglicher Pipeline-Ausfall — Web-Fallback aktiv."
            ),
            "file_timestamp_utc": ts_str,
        }
    if age_min > threshold:
        return {
            "status": "stale",
            "age_minutes": age_min,
            "threshold_minutes": threshold,
            "warning_text": (
                f"⚠️ Pipeline-File {age_min} Min alt "
                f"(Threshold {threshold} Min für {routine}). "
                "Daten möglicherweise nicht aktuell."
            ),
            "file_timestamp_utc": ts_str,
        }
    return {
        "status": "ok",
        "age_minutes": age_min,
        "threshold_minutes": threshold,
        "warning_text": "",
        "file_timestamp_utc": ts_str,
    }


def get_ticker_data(
    marketdata: dict[str, TickerData], ticker: str
) -> Optional[TickerData]:
    """Lookup mit Toleranz für Suffix-Varianten.

    Beispiele:
      - 'PG' findet 'PG'
      - 'CBK' findet 'CBK.DE' (eindeutig)
      - 'BTC' findet 'BTC-EUR' (eindeutig)
      - 'AB' findet nichts, wenn 'AB.DE' UND 'ABC' beide existieren

    Returns:
        TickerData oder None — None heißt: nicht im Pipeline-Universe,
        Routine soll Web-Fallback nur für diesen Ticker machen.
    """
    if ticker in marketdata:
        return marketdata[ticker]

    base = ticker.upper()
    matches = [
        k for k in marketdata
        if k.split(".")[0] == base or k.split("-")[0] == base or k == base
    ]
    if len(matches) == 1:
        return marketdata[matches[0]]
    return None


def find_candidate_in_buckets(
    snap: PipelineSnapshot, ticker: str
) -> Optional[CandidateEntry]:
    """Sucht einen Ticker quer durch alle CANDIDATES-Buckets.

    Genutzt für News-/Hidden-/Insider-Scan: Bevor ein neuer Kandidat ausgegeben
    wird, prüfen, ob er bereits in der Watchlist-Pipeline geführt wird.
    """
    base = ticker.upper().split(".")[0].split("-")[0]
    for bucket_items in snap.candidates.values():
        for entry in bucket_items:
            entry_base = entry.ticker.upper().split(".")[0].split("-")[0]
            if entry_base == base or entry.ticker.upper() == ticker.upper():
                return entry
    return None


# ---------------------------------------------------------------------------
# Setup-Klassen-Helfer (Note #49, seit 2026-05-08)
# ---------------------------------------------------------------------------


def ema200_meanrev_qualifies(td: TickerData) -> bool:
    """True, wenn alle 4 EMA200-MeanRev-Vorprüfungen erfüllt sind.

    Kriterien (Übergabe-Spec 2026-05-08):
    - abs(ema200_distance_pct) ≤ 2.0
    - days_since_last_ema200_touch ≥ 120
    - ema200_trend_qualified == True
    - weekly_higher_highs_lows == True

    Genutzt von Routinen 7/8b: nach `parse_marketdata` durchlaufen, um die
    Tier-A-Kandidaten zu finden — auch wenn die Pipeline-Flag-Zeile selbst
    noch nicht ins CANDIDATES.md gerendert wurde (frische Werte aus
    MARKETDATA-FULL-STD).
    """
    if td.ema200_distance_pct is None or abs(td.ema200_distance_pct) > 2.0:
        return False
    if td.days_since_last_ema200_touch is None or td.days_since_last_ema200_touch < 120:
        return False
    if not td.ema200_trend_qualified:
        return False
    if not td.weekly_higher_highs_lows:
        return False
    return True


def list_ema200_meanrev_candidates(
    marketdata: dict[str, TickerData],
) -> list[TickerData]:
    """Filtert MARKETDATA-FULL nach EMA200-MeanRev-Kandidaten und sortiert nach
    absoluter EMA200-Distanz aufsteigend (näher = relevanter)."""
    cands = [td for td in marketdata.values() if ema200_meanrev_qualifies(td)]
    cands.sort(key=lambda t: abs(t.ema200_distance_pct or 999))
    return cands


def list_pead_window_candidates(
    marketdata: dict[str, TickerData],
    max_days: int = 5,
) -> list[TickerData]:
    """Filtert nach Tickern mit Earnings ≤ max_days HT in der Vergangenheit.

    Standard 5 HT — kompatibel mit Übergabe-Spec. Sortiert nach Tagen
    aufsteigend (frischer = relevanter).
    """
    cands: list[TickerData] = []
    for td in marketdata.values():
        if td.last_earnings_date is None:
            continue
        if td.days_since_last_earnings is None:
            continue
        if 0 <= td.days_since_last_earnings <= max_days:
            cands.append(td)
    cands.sort(key=lambda t: t.days_since_last_earnings or 999)
    return cands


# ---------------------------------------------------------------------------
# High-Level: Briefing-Header
# ---------------------------------------------------------------------------


def render_freshness_header(
    md_status: dict,
    cand_status: dict,
    routine: str,
    gc_status: Optional[dict] = None,
) -> str:
    """Erzeugt einen kompakten Status-Header für den Briefing-Output.

    Rückgabe ist 0–4 Zeilen — eine Zeile pro Pipeline-File mit Auffälligkeit
    plus optional eine Zusammenfassungszeile bei Fallback. Bei status='ok'
    auf allen drei Files ist der Header leer (keine Geräusche im Normalfall).

    Gamechanger-Status ist optional — fehlt er, läuft die Funktion wie vor
    der Erweiterung. Gamechanger gilt als additiv: Sein Ausfall löst KEINEN
    globalen Fallback aus (im Gegensatz zu Marketdata/Candidates).
    """
    lines: list[str] = []

    core_fallback = md_status["status"] in {"ausfall", "missing"} or cand_status[
        "status"
    ] in {"ausfall", "missing"}

    if md_status["status"] != "ok":
        lines.append(f"MARKETDATA: {md_status['warning_text']}")
    if cand_status["status"] != "ok":
        lines.append(f"CANDIDATES: {cand_status['warning_text']}")
    if gc_status is not None and gc_status["status"] != "ok":
        # Gamechanger ist additiv — Default-Warntext aus freshness_status
        # spricht aber von "Web-Fallback aktiv". Für Gamechanger umformulieren.
        if gc_status["status"] in {"ausfall", "missing"}:
            gc_text = (
                "⚠️ GAMECHANGER-Pipeline nicht erreichbar — "
                "Block wird im Briefing weggelassen, Routine läuft normal weiter."
            )
        else:
            gc_text = gc_status["warning_text"]
        lines.append(f"GAMECHANGER: {gc_text}")

    if core_fallback:
        lines.insert(
            0,
            f"🔴 PIPELINE-FALLBACK aktiv für {routine} — "
            "Briefing nutzt Web-Suchen statt Pipeline-Files.",
        )
    elif lines:
        # Stale, aber nicht ausgefallen — Kopf etwas leiser
        lines.insert(0, f"🟡 PIPELINE-WARNUNG für {routine}:")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Universum-Erkennung (seit 2026-04-26)
# ---------------------------------------------------------------------------


def classify_universe(content: str, filename: Optional[str] = None) -> str:
    """Klassifiziert ein MARKETDATA-FULL.md anhand seiner Tickerliste oder seines Filenames.

    Pipeline kann mehrere MARKETDATA-Läufe mit unterschiedlichen Universen
    in den Briefing-Ordner schreiben (Befund 2026-04-26):

    - "standard": enthält Indizes (^GDAXI, ^GSPC, …), Krypto (BTC-EUR, …),
      FX, Rohstoffe + Watchlist-Aktien. Basis für Routine 7 (Watchlist) und
      8/8b/8c (Insider/News-Scan-Indikator-Lookup).
    - "gamechanger": enthält ein breiteres Aktien-Universum für den
      Setup-Scan (Universe-Pull, kein Index/Krypto/FX). Basis für
      GAMECHANGER-HUNT.md, dort schon vorausgewertet.
    - "unknown": weder ausreichend Sentinels noch klar leer — sollte im
      Briefing als Warnung erscheinen.

    Erkennungsreihenfolge (seit Action-Edit 2026-04-26):
    1. **Filename-Tag** (`-STD-` oder `-GC-` im Filename) — preferred,
       weil eindeutig und schnell. Funktioniert nur bei neuen Files
       seit Action-Umstellung.
    2. **Sentinel-Heuristik** auf Content — Fallback für alte Files
       und falls die Action mal ohne Tag schreibt.

    Heuristik: Zähle Vorkommen aus STANDARD_UNIVERSE_SENTINELS. Ab
    STANDARD_UNIVERSE_MIN_HITS (=3) gilt der Lauf als Standard.

    Args:
        content: MARKETDATA-FULL.md-Inhalt (escaped oder clean — wird intern
                 unescaped).
        filename: Optionaler Filename. Wenn er ein eindeutiges Tag
                  (`-STD-` / `-GC-`) enthält, wird dies bevorzugt vor
                  der Content-Heuristik genutzt.

    Returns:
        "standard" | "gamechanger" | "unknown"
    """
    # 1. Filename-Tag (preferred, seit Action-Edit 2026-04-26)
    if filename:
        if "-STD-" in filename or "-FULL-STD-" in filename:
            return "standard"
        if "-GC-" in filename or "-FULL-GC-" in filename:
            return "gamechanger"

    # 2. Content-Heuristik (Fallback, auch für Pre-Action-Edit-Files)
    content = _unescape_drive_markdown(content)
    # Tickers stehen jeweils als "## TICKER" am Zeilenanfang
    found_sentinels = sum(
        1 for s in STANDARD_UNIVERSE_SENTINELS
        if re.search(rf"^##\s+{re.escape(s)}\s*$", content, re.MULTILINE)
    )

    if found_sentinels >= STANDARD_UNIVERSE_MIN_HITS:
        return "standard"

    # Gegenprobe: Wie viele "## TICKER"-Sektionen gibt es überhaupt?
    total_sections = len(re.findall(r"^##\s+\S+\s*$", content, re.MULTILINE))
    if total_sections >= 5 and found_sentinels == 0:
        # Substanzielle Tickerliste, aber kein einziges Index/Krypto/FX
        # → klar Gamechanger-Universum
        return "gamechanger"

    return "unknown"


def select_latest_marketdata(
    files_with_content: list[dict],
    universe: str = "standard",
) -> Optional[dict]:
    """Wählt aus einer Liste von MARKETDATA-Files das jüngste des gewünschten Universums.

    Erwartet Liste mit Dicts der Form:
        {"id": "...", "title": "...", "modifiedTime": "ISO-8601", "content": "..."}

    Reihenfolge der Liste ist egal — sortiert intern nach modifiedTime DESC.

    Args:
        files_with_content: Liste mit Drive-Metadata + bereits geladenem
                            Content für jedes MARKETDATA-File. Routinen
                            müssen die Contents vorher per
                            read_file_content laden, weil classify_universe
                            den Content braucht.
        universe: "standard" oder "gamechanger".

    Returns:
        Das jüngste passende File-Dict (mit zusätzlichem Schlüssel "universe"),
        oder None wenn keines passt.
    """
    if not files_with_content:
        return None

    # Sortiert DESC nach modifiedTime
    sorted_files = sorted(
        files_with_content,
        key=lambda f: f.get("modifiedTime", ""),
        reverse=True,
    )

    for f in sorted_files:
        content = f.get("content", "") or ""
        # Filename aus 'title' (Drive-Standard) oder 'name' (alternative Konvention)
        filename = f.get("title") or f.get("name") or ""
        u = classify_universe(content, filename=filename)
        if u == universe:
            # Defensiv kopieren statt mutieren, falls der Aufrufer das Dict
            # anderweitig wiederverwendet.
            result = dict(f)
            result["universe"] = u
            return result

    return None


# ---------------------------------------------------------------------------
# Quick-Test (manuell ausführen)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Smoke-Test: parse_marketdata + parse_candidates auf hartkodierten
    # Beispielen, die der echten Pipeline-Output-Form entsprechen.
    sample_md = (
        "# MARKETDATA-FULL — 2026-04-25 23:36 CEST\n\n"
        "## PG\n\n"
        "- **Kurs:** 148.2 (+1.70%)\n"
        "- **EMAs:** EMA20=145.3 · EMA50=147.7 · EMA200=151.3 (bearish-Stack ↓)\n"
        "- **RSI-14:** 55.1\n"
        "- **ATR-14:** 2.924\n"
        "- **30d-Move:** +2.96%\n"
        "- **52W-Range:** 137.6 – 171.0 (High-Distanz -13.34%, Low-Distanz +7.67%)\n"
        "- **20d-Range:** 140.7 – 152.4\n"
        "- **Volumen:** Avg-20d 8,995,820 Stk · 1,333,000,542 EUR (heute 1.53× avg)\n"
    )
    md = parse_marketdata(sample_md)
    assert "PG" in md, f"Kein PG im Parse-Ergebnis: {md}"
    assert md["PG"].kurs == 148.2
    assert md["PG"].ema_stack == "bearish"
    assert md["PG"].vol_today_ratio == 1.53
    print("✅ parse_marketdata smoke-test OK")
    print(f"   PG: kurs={md['PG'].kurs}, RSI={md['PG'].rsi}, "
          f"30d={md['PG'].move_30d}%, stack={md['PG'].ema_stack}")

    sample_cand = (
        "# CANDIDATES — 2026-04-25 23:36 CEST\n\n"
        "## Stufe 1 — Watchlist-Trigger-Status\n\n"
        "### 🎯 BEREIT — Trigger erfüllt\n\n"
        "- **PG** (LONG ↑) — Kurs 148.2\n"
        "  - [A] 🎯 BEREIT — alle Bedingungen erfüllt\n"
        "  - _Note: warten Mo/Di_\n"
        "\n"
        "### Nah am Trigger (≤5%)\n\n"
        "- **CRM** (SHORT ↓) — Kurs 178.2\n"
        "\n"
        "## Override-Werte (priority_long / priority_short)\n\n"
        "- **BTC-EUR** (↓) — Kurs 66152 (+0.12%)\n"
        "  - _Grund: Position #24 Zeitstopp 27.04 vor FOMC_\n"
        "\n"
        "## Aktive Filter-Overrides\n\n"
        "- **CBK.DE** [priority_long] — Trigger A 33,40-33,60 sehr nah, Note #9 (gültig bis 2026-05-02)\n"
    )
    snap = parse_candidates(sample_cand)
    assert snap.candidates_timestamp == "2026-04-25 23:36"
    assert len(snap.candidates["bereit"]) == 1
    assert snap.candidates["bereit"][0].ticker == "PG"
    assert snap.candidates["bereit"][0].direction == "LONG"
    assert len(snap.candidates["close"]) == 1
    assert len(snap.overrides) == 1
    assert snap.overrides[0]["ticker"] == "BTC-EUR"
    assert len(snap.filter_overrides) == 1
    assert snap.filter_overrides[0]["tag"] == "priority_long"
    print("✅ parse_candidates smoke-test OK")

    # Frische-Check
    fresh = freshness_status(
        "2026-04-25T21:36:00Z",
        "morning_check",
        now=datetime(2026, 4, 25, 21, 50, tzinfo=timezone.utc),
    )
    assert fresh["status"] == "ok", f"Erwartet ok, bekam {fresh}"
    stale = freshness_status(
        "2026-04-25T21:36:00Z",
        "morning_check",
        now=datetime(2026, 4, 25, 22, 30, tzinfo=timezone.utc),
    )
    assert stale["status"] == "stale", f"Erwartet stale, bekam {stale}"
    ausfall = freshness_status(
        "2026-04-23T21:36:00Z",
        "morning_check",
        now=datetime(2026, 4, 25, 22, 30, tzinfo=timezone.utc),
    )
    assert ausfall["status"] == "ausfall", f"Erwartet ausfall, bekam {ausfall}"
    missing = freshness_status(None, "morning_check")
    assert missing["status"] == "missing"
    print("✅ freshness_status smoke-test OK")

    # Lookup
    assert get_ticker_data(md, "PG").kurs == 148.2
    assert get_ticker_data(md, "ZZZ") is None
    assert find_candidate_in_buckets(snap, "PG").bucket == "bereit"
    print("✅ Lookup smoke-test OK")

    # Gamechanger-Parser
    sample_gc = (
        "# CANDIDATES — 2026-04-26 00:31 CEST\n\n"
        "## Stufe 1 — Watchlist-Trigger-Status\n\n"
        "---\n\n"
        "## Stufe 2 — Neue Kandidaten aus Universe\n\n"
        "### Long-Trend-Pullback\n\n"
        "- NDX1.DE: 44.94 EMA20=44.94 Dist=-0.00% RSI=53 30d=+4.0%\n\n"
        "### Short-Trend-Pullback\n\n"
        "- PLTR: 143.09 EMA20=144.04 Dist=-0.66% RSI=49 30d=-7.7%\n"
        "- ZS: 135.50 EMA20=136.62 Dist=-0.82% RSI=46 30d=-2.8%\n"
        "- NEM.DE: 63.55 EMA20=64.62 Dist=-1.65% RSI=47 30d=-3.3%\n\n"
        "---\n\n"
        "## Aktive Filter-Overrides\n\n"
        "- **CBK.DE** [priority_long] — soll ignoriert werden\n"
    )
    gc = parse_gamechanger(sample_gc)
    assert gc.timestamp == "2026-04-26 00:31"
    assert "Long-Trend-Pullback" in gc.candidates_by_setup
    assert "Short-Trend-Pullback" in gc.candidates_by_setup
    assert len(gc.candidates_by_setup["Long-Trend-Pullback"]) == 1
    assert len(gc.candidates_by_setup["Short-Trend-Pullback"]) == 3

    ndx = gc.candidates_by_setup["Long-Trend-Pullback"][0]
    assert ndx.ticker == "NDX1.DE"
    assert ndx.direction == "LONG"
    assert ndx.kurs == 44.94
    assert ndx.rsi == 53.0
    assert ndx.move_30d == 4.0

    pltr = gc.candidates_by_setup["Short-Trend-Pullback"][0]
    assert pltr.ticker == "PLTR"
    assert pltr.direction == "SHORT"
    assert pltr.distance_pct == -0.66
    assert pltr.move_30d == -7.7

    # all_candidates / find
    assert len(gc.all_candidates()) == 4
    assert gc.find("PLTR").setup == "Short-Trend-Pullback"
    assert gc.find("PG") is None  # Im Watchlist-File, nicht im Gamechanger
    assert gc.find("NEM").ticker == "NEM.DE"  # Fuzzy
    print("✅ parse_gamechanger smoke-test OK")
    print(f"   Setup-Buckets: {list(gc.candidates_by_setup.keys())}")
    print(f"   Long: {[c.ticker for c in gc.candidates_by_setup['Long-Trend-Pullback']]}")
    print(f"   Short: {[c.ticker for c in gc.candidates_by_setup['Short-Trend-Pullback']]}")

    # classify_universe
    standard_md = (
        "# MARKETDATA-FULL — 2026-04-25 23:36 CEST\n\n"
        "## ^GDAXI\n\n- **Kurs:** 24129 (-0.11%)\n\n"
        "## BTC-EUR\n\n- **Kurs:** 66152 (+0.12%)\n\n"
        "## EURUSD=X\n\n- **Kurs:** 1.17 (+0.17%)\n\n"
        "## PG\n\n- **Kurs:** 148.2 (+1.70%)\n\n"
    )
    gamechanger_md = (
        "# MARKETDATA-FULL — 2026-04-26 00:31 CEST\n\n"
        "## ABNB\n\n- **Kurs:** 142.8 (+0.67%)\n\n"
        "## ADBE\n\n- **Kurs:** 245.4 (+2.70%)\n\n"
        "## AMD\n\n- **Kurs:** 347.8 (+13.91%)\n\n"
        "## PLTR\n\n- **Kurs:** 143.1 (+1.07%)\n\n"
        "## ZS\n\n- **Kurs:** 135.5 (+1.90%)\n\n"
    )
    sparse_md = "# MARKETDATA-FULL — leer\n\n## XYZ\n\n- **Kurs:** 1.0 (+0.00%)\n\n"

    assert classify_universe(standard_md) == "standard"
    assert classify_universe(gamechanger_md) == "gamechanger"
    assert classify_universe(sparse_md) == "unknown"
    # Auch escaped Markdown funktioniert
    assert classify_universe(standard_md.replace("##", "\\#\\#")) == "standard"

    # Filename-Tag hat Priorität vor Content-Heuristik
    # (Action-Edit ab 2026-04-26 setzt -STD-/-GC- in den Dateinamen)
    assert classify_universe(sparse_md, filename="MARKETDATA-FULL-STD-2026-04-28-0900.md") == "standard"
    assert classify_universe(sparse_md, filename="MARKETDATA-FULL-GC-2026-04-28-0900.md") == "gamechanger"
    # Filename ohne Tag → Heuristik greift
    assert classify_universe(standard_md, filename="MARKETDATA-FULL-2026-04-25-2336.md") == "standard"
    assert classify_universe(gamechanger_md, filename="MARKETDATA-FULL-2026-04-26-0031.md") == "gamechanger"
    # Filename-Tag schlägt Content (auch wenn Content widerspricht — Action ist Wahrheit)
    assert classify_universe(gamechanger_md, filename="MARKETDATA-FULL-STD-test.md") == "standard"
    print("✅ classify_universe smoke-test OK")

    # select_latest_marketdata — Pipeline-Realität: 23:36 Standard + 00:31 Gamechanger
    files = [
        {
            "id": "gc-id",
            "title": "MARKETDATA-FULL-2026-04-26-0031.md",
            "modifiedTime": "2026-04-25T22:31:27Z",
            "content": gamechanger_md,
        },
        {
            "id": "std-id",
            "title": "MARKETDATA-FULL-2026-04-25-2336.md",
            "modifiedTime": "2026-04-25T21:36:03Z",
            "content": standard_md,
        },
        {
            "id": "old-std-id",
            "title": "MARKETDATA-FULL-2026-04-25-2255.md",
            "modifiedTime": "2026-04-25T20:55:50Z",
            "content": standard_md,
        },
    ]
    pick_std = select_latest_marketdata(files, universe="standard")
    pick_gc = select_latest_marketdata(files, universe="gamechanger")
    assert pick_std is not None and pick_std["id"] == "std-id", pick_std
    assert pick_std["universe"] == "standard"
    assert pick_gc is not None and pick_gc["id"] == "gc-id", pick_gc
    assert pick_gc["universe"] == "gamechanger"
    # Kein passendes Universum → None
    assert select_latest_marketdata(
        [{"id": "x", "modifiedTime": "2026-04-25T20:55:50Z", "content": sparse_md}],
        universe="standard",
    ) is None
    # Leere Liste → None
    assert select_latest_marketdata([], universe="standard") is None
    print("✅ select_latest_marketdata smoke-test OK")
    print(f"   Standard pick: {pick_std['title']} (mtime {pick_std['modifiedTime']})")
    print(f"   Gamechanger pick: {pick_gc['title']} (mtime {pick_gc['modifiedTime']})")

    # Neues Filename-Schema (seit Action-Edit 2026-04-26):
    # Sentinel-Heuristik nicht mehr nötig — Filename-Tag entscheidet.
    new_schema_files = [
        {
            "id": "new-gc-id",
            "title": "MARKETDATA-FULL-GC-2026-04-28-0931.md",
            "modifiedTime": "2026-04-28T07:31:00Z",
            "content": "# MARKETDATA-FULL-GC\n## XYZ\n- **Kurs:** 1.0\n",  # spärlicher Content reicht
        },
        {
            "id": "new-std-id",
            "title": "MARKETDATA-FULL-STD-2026-04-28-0930.md",
            "modifiedTime": "2026-04-28T07:30:00Z",
            "content": "# MARKETDATA-FULL-STD\n## XYZ\n- **Kurs:** 1.0\n",  # spärlicher Content reicht
        },
    ]
    pick_std_new = select_latest_marketdata(new_schema_files, universe="standard")
    pick_gc_new  = select_latest_marketdata(new_schema_files, universe="gamechanger")
    assert pick_std_new is not None and pick_std_new["id"] == "new-std-id"
    assert pick_gc_new  is not None and pick_gc_new["id"]  == "new-gc-id"
    print("✅ Filename-Schema (post-Action-Edit) smoke-test OK")

    # === EMA200-MeanRev + Earnings — Parser + Helper (seit 2026-05-08) ===
    sample_md_v2 = (
        "# MARKETDATA-FULL — 2026-05-08 17:00 CEST\n\n"
        "## SAP.DE\n\n"
        "- **Kurs:** 242.5 (-1.54%)\n"
        "- **EMAs:** EMA20=255.4 · EMA50=250.2 · EMA200=243.8 (bullish-Stack ↑)\n"
        "- **RSI-14:** 42.0\n"
        "- **ATR-14:** 4.850\n"
        "- **30d-Move:** -2.80%\n"
        "- **52W-Range:** 180.00 – 275.00 (High-Distanz -11.82%, Low-Distanz +34.72%)\n"
        "- **20d-Range:** 240.00 – 260.00\n"
        "- **Volumen:** Avg-20d 2,400,000 Stk · 580,000,000 EUR (heute 1.04× avg)\n"
        "- **EMA200-MeanRev:** Dist=-0.53% · LastTouch=215d · TrendQual=✓ · WeeklyHHHL=✓\n"
        "- **Earnings:** Next=2026-08-01 · Last=2026-05-06 (2d ago)\n\n"
        "## CRASH.DE\n\n"
        "- **Kurs:** 50.0 (-3.00%)\n"
        "- **EMAs:** EMA20=55.0 · EMA50=60.0 · EMA200=80.0 (bearish-Stack ↓)\n"
        "- **RSI-14:** 28.0\n"
        "- **ATR-14:** 1.500\n"
        "- **30d-Move:** -15.00%\n"
        "- **52W-Range:** 45.00 – 100.00 (High-Distanz -50.00%, Low-Distanz +11.11%)\n"
        "- **20d-Range:** 48.00 – 60.00\n"
        "- **Volumen:** Avg-20d 500,000 Stk · 25,000,000 EUR\n"
        "- **EMA200-MeanRev:** Dist=-37.50% · LastTouch=10d · TrendQual=✗ · WeeklyHHHL=✗\n"
    )
    md2 = parse_marketdata(sample_md_v2)
    assert "SAP.DE" in md2, f"SAP.DE fehlt: {list(md2.keys())}"
    assert "CRASH.DE" in md2

    sap = md2["SAP.DE"]
    # Neue Felder geparst
    assert sap.ema200_distance_pct == -0.53, f"Erwartet -0.53, bekam {sap.ema200_distance_pct}"
    assert sap.days_since_last_ema200_touch == 215
    assert sap.ema200_trend_qualified is True
    assert sap.weekly_higher_highs_lows is True
    assert sap.next_earnings_date == "2026-08-01"
    assert sap.last_earnings_date == "2026-05-06"
    assert sap.days_since_last_earnings == 2

    crash = md2["CRASH.DE"]
    assert crash.ema200_distance_pct == -37.50
    assert crash.ema200_trend_qualified is False
    assert crash.weekly_higher_highs_lows is False
    print("✅ EMA200-MeanRev + Earnings parser smoke-test OK")

    # Helper-Tests
    assert ema200_meanrev_qualifies(sap) is True, "SAP sollte qualifizieren"
    assert ema200_meanrev_qualifies(crash) is False, "CRASH darf nicht qualifizieren"

    cands = list_ema200_meanrev_candidates(md2)
    assert len(cands) == 1
    assert cands[0].ticker == "SAP.DE"
    print("✅ list_ema200_meanrev_candidates smoke-test OK")

    pead = list_pead_window_candidates(md2)
    assert len(pead) == 1
    assert pead[0].ticker == "SAP.DE"
    print("✅ list_pead_window_candidates smoke-test OK")

    print("\nAlle smoke-tests bestanden.")
