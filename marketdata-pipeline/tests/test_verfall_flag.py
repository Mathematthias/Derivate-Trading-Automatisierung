"""
Tests für Patch 5 — CANDIDATES Verfall-Flag (#42).

Deckt die End-to-End-Kette ab:
- watchlist_sync: Verfallsdatum (Spalte H) aus dem Journal lesen + ISO-normieren,
  6. Spalte im STATE-Watchlist-Block rendern
- state_parser: 6. Spalte parsen, robust gegen leere Verfall-Zellen
- output_renderer: _expiry_flag (Handelstage-Countdown)
- pipeline_utils: parse_candidates reicht das Verfallsdatum durch

Ausführen vom marketdata-pipeline/ Verzeichnis:
    PYTHONPATH=./src pytest tests/test_verfall_flag.py -v
"""

import datetime as dt
import io
import os
import sys

import pytest
from openpyxl import Workbook

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
_SKILL = os.path.join(os.path.dirname(_HERE), "..", "skills", "derivate-trading")
sys.path.insert(0, _SRC)
sys.path.insert(0, _SKILL)

from watchlist_sync import (
    _parse_verfall_date,
    read_journal_watchlist,
    render_watchlist_block,
)
from state_parser import parse_watchlist
from output_renderer import _expiry_flag
from pipeline_utils import parse_candidates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_journal_xlsx(verfall_value) -> bytes:
    """Minimales Journal mit 8-Spalten-Watchlist-Sheet (Stand 2026-05-23)."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Watchlist"
    ws.append(["Aktie", "Symbol", "Richtung", "Entry-Trigger", "These",
               "Status", "Datum hinzugefügt", "Verfallsdatum"])
    ws.append(["Testfirma AG", "TST.DE", "LONG", "A) Daily-Close > 100",
               "These-Text", "aktiv", "aktualisiert 20.05.2026", verfall_value])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def state_doc(table_rows: str) -> str:
    """STATE-Markdown mit Watchlist-Sektion aus den übergebenen Tabellenzeilen."""
    return (
        "## Watchlist-Trigger (aktive Einträge)\n\n"
        + table_rows
        + "\n## Nächste Sektion\n\nirgendwas\n"
    )


# ---------------------------------------------------------------------------
# 1) watchlist_sync — _parse_verfall_date
# ---------------------------------------------------------------------------

def test_parse_verfall_date_with_freetext():
    """Journal-Feld 'TT.MM.JJJJ (Freitext)' -> ISO-Datum."""
    assert _parse_verfall_date("11.06.2026 (Momentum-Setup +14 HT)") == "2026-06-11"


def test_parse_verfall_date_plain():
    assert _parse_verfall_date("27.05.2026") == "2026-05-27"


def test_parse_verfall_date_empty():
    assert _parse_verfall_date("") == ""


def test_parse_verfall_date_no_date():
    assert _parse_verfall_date("kein Datum hinterlegt") == ""


def test_parse_verfall_date_invalid():
    """Unplausibles Datum -> leer statt Exception."""
    assert _parse_verfall_date("32.13.2026 (Tippfehler)") == ""


# ---------------------------------------------------------------------------
# 2) watchlist_sync — Sheet-Read + Block-Render
# ---------------------------------------------------------------------------

def test_read_journal_watchlist_reads_verfall():
    """Spalte H wird gelesen und ISO-normiert in das entry-Dict übernommen."""
    entries = read_journal_watchlist(make_journal_xlsx("11.06.2026 (Default +14 HT)"))
    assert len(entries) == 1
    assert entries[0]["verfall"] == "2026-06-11"


def test_read_journal_watchlist_empty_verfall():
    """Leere Verfall-Zelle -> leerer String, kein Fehler."""
    entries = read_journal_watchlist(make_journal_xlsx(None))
    assert entries[0]["verfall"] == ""


def test_render_watchlist_block_has_verfall_column():
    """Der STATE-Block bekommt eine 6. Spalte 'Verfall'."""
    entries = [{
        "aktie": "Testfirma", "symbol": "TST.DE", "richtung": "LONG",
        "trigger": "A) Trigger", "status": "aktiv", "note": "",
        "verfall": "2026-06-11",
    }]
    block = render_watchlist_block(entries, dt.datetime(2026, 5, 23, 12, 0))
    assert "| Verfall |" in block
    assert "2026-06-11" in block


def test_render_watchlist_block_missing_verfall_key():
    """Fehlender verfall-Key (Alt-Aufrufer) -> leere Zelle statt KeyError."""
    entries = [{
        "aktie": "Testfirma", "symbol": "TST.DE", "richtung": "LONG",
        "trigger": "A) Trigger", "status": "aktiv", "note": "",
    }]
    block = render_watchlist_block(entries, dt.datetime(2026, 5, 23, 12, 0))
    assert "| Verfall |" in block  # Header trotzdem da


# ---------------------------------------------------------------------------
# 3) state_parser — 6. Spalte parsen
# ---------------------------------------------------------------------------

def test_parse_watchlist_reads_expiry():
    """6-Spalten-STATE-Tabelle -> expiry_date wird gesetzt."""
    rows = (
        "| Kandidat | Symbol | Richtung | Trigger (Kurzform) | Status | Verfall |\n"
        "|----------|--------|----------|--------------------|--------|---------|\n"
        "| Testfirma | TST.DE | LONG | A) Daily-Close > 100 | ⚠️ aktiv | 2026-06-11 |\n"
    )
    entries = parse_watchlist(state_doc(rows))
    assert len(entries) == 1
    assert entries[0].expiry_date == dt.date(2026, 6, 11)


def test_parse_watchlist_backward_compat_5col():
    """Alte 5-Spalten-Tabelle (vor dem nächsten Sync) -> expiry_date bleibt None."""
    rows = (
        "| Kandidat | Symbol | Richtung | Trigger (Kurzform) | Status |\n"
        "|----------|--------|----------|--------------------|--------|\n"
        "| Testfirma | TST.DE | LONG | A) Daily-Close > 100 | ⚠️ aktiv |\n"
    )
    entries = parse_watchlist(state_doc(rows))
    assert len(entries) == 1
    assert entries[0].expiry_date is None


def test_parse_watchlist_empty_verfall_cell():
    """Leere Verfall-Zelle in 6-Spalten-Tabelle: die inneren Leerzellen dürfen
    die Spaltenzuordnung nicht verschieben — die 5 Kernfelder bleiben korrekt."""
    rows = (
        "| Kandidat | Symbol | Richtung | Trigger (Kurzform) | Status | Verfall |\n"
        "|----------|--------|----------|--------------------|--------|---------|\n"
        "| Testfirma | TST.DE | SHORT | B) Daily-Close < 80 | ⚠️ aktiv |  |\n"
    )
    entries = parse_watchlist(state_doc(rows))
    assert len(entries) == 1
    e = entries[0]
    assert e.expiry_date is None
    assert e.symbol == "TST.DE"
    assert e.direction == "SHORT"
    assert e.status == "aktiv"


# ---------------------------------------------------------------------------
# 4) output_renderer — _expiry_flag (Handelstage-Countdown)
# ---------------------------------------------------------------------------

# 2026-05-25 ist ein Montag -> deterministische Handelstage-Abstände.
_MONDAY = dt.date(2026, 5, 25)


def test_expiry_flag_none():
    assert _expiry_flag(None, _MONDAY) is None


def test_expiry_flag_far():
    """5 HT entfernt -> Info-Zeile, keine ⏰-Markierung."""
    flag = _expiry_flag(dt.date(2026, 6, 1), _MONDAY)  # Mo+5 HT
    assert flag is not None
    assert "5 HT" in flag
    assert "⏰" not in flag and "⛔" not in flag


def test_expiry_flag_near():
    """2 HT entfernt -> ⏰-Markierung."""
    flag = _expiry_flag(dt.date(2026, 5, 27), _MONDAY)  # Mo+2 HT (Mi)
    assert flag.startswith("⏰")
    assert "2 HT" in flag


def test_expiry_flag_today():
    """Verfall heute -> verfallen (0 HT)."""
    assert _expiry_flag(_MONDAY, _MONDAY).startswith("⛔")


def test_expiry_flag_past():
    """Verfall in der Vergangenheit -> verfallen."""
    assert _expiry_flag(dt.date(2026, 5, 22), _MONDAY).startswith("⛔")


# ---------------------------------------------------------------------------
# 5) pipeline_utils — parse_candidates reicht das Verfallsdatum durch
# ---------------------------------------------------------------------------

def test_parse_candidates_surfaces_expiry():
    """Die Verfall-Unterzeile in CANDIDATES.md landet in CandidateEntry.expiry."""
    content = (
        "# CANDIDATES — 2026-05-23 14:30\n\n"
        "## Stufe 1 — Watchlist-Trigger-Status\n\n"
        "### 🎯 BEREIT — Trigger erfüllt\n\n"
        "- **TST.DE** (LONG ↑) — Kurs 100,00€\n"
        "  - ⏰ Verfall in 3 HT (2026-06-11)\n"
        "  - [A] Trigger-Zusammenfassung\n\n"
        "- **NOX.DE** (SHORT ↓) — Kurs 50,00€\n"
        "  - [B] anderer Trigger\n"
    )
    snap = parse_candidates(content)
    bereit = {e.ticker: e for e in snap.candidates["bereit"]}
    assert bereit["TST.DE"].expiry == "2026-06-11"
    assert bereit["NOX.DE"].expiry is None


def test_parse_candidates_expiry_from_expired_format():
    """Auch das '⛔ verfallen (Verfall ...)'-Format wird erkannt."""
    content = (
        "# CANDIDATES — 2026-05-23 14:30\n\n"
        "### 🎯 BEREIT — Trigger erfüllt\n\n"
        "- **OLD.DE** (LONG ↑) — Kurs 12,00€\n"
        "  - ⛔ verfallen (Verfall 2026-05-20)\n"
    )
    snap = parse_candidates(content)
    assert snap.candidates["bereit"][0].expiry == "2026-05-20"
