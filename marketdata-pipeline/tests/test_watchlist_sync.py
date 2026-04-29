"""Tests für watchlist_sync — laufen ohne Netz und ohne Drive."""

import datetime as dt
import io
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
sys.path.insert(0, _SRC)

from openpyxl import Workbook

from watchlist_sync import (
    _parse_status, _shorten_richtung, _shorten_trigger,
    read_journal_watchlist, render_watchlist_block, replace_watchlist_block,
)


# ---------------------------------------------------------------------------
# Status-Parsing
# ---------------------------------------------------------------------------

def test_status_paused():
    status, note = _parse_status("⏸ warten auf Pullback — aktuell 265,80€")
    assert status == "paused"
    assert "warten auf Pullback" in note


def test_status_pending_with_date():
    status, note = _parse_status("📅 28.04.2026 (Di): Short-Pre-Trade-Plan erstellen")
    assert status == "pending"
    assert "2026-04-28" in note


def test_status_aktiv_default():
    status, note = _parse_status("Trigger A in Reichweite, Note #9")
    # Kein Emoji → default aktiv
    assert status == "aktiv"


def test_status_beobachten_eye():
    status, note = _parse_status("👀 beobachten — Pullback-Only, kein Chase")
    assert status == "beobachten"


def test_status_long_note_truncated():
    long_text = "⏸ warten — " + "x" * 200
    _, note = _parse_status(long_text)
    assert len(note) <= 80


# ---------------------------------------------------------------------------
# Richtung
# ---------------------------------------------------------------------------

def test_richtung_simple():
    assert _shorten_richtung("LONG") == "LONG"
    assert _shorten_richtung("SHORT") == "SHORT"


def test_richtung_with_modifier():
    assert _shorten_richtung("LONG (Post-Earnings-Pullback)") == "LONG"
    assert _shorten_richtung("SHORT (Bounce)") == "SHORT"


def test_richtung_konditional():
    # KONDITIONAL bleibt erhalten — Pipeline kann's interpretieren oder skippen
    result = _shorten_richtung("KONDITIONAL (Long oder Short)")
    assert "KONDITIONAL" in result or "LONG" in result.upper()


# ---------------------------------------------------------------------------
# Trigger-Kürzung
# ---------------------------------------------------------------------------

def test_trigger_short_unchanged():
    s = "Pullback 258€ + RSI<60"
    assert _shorten_trigger(s) == s


def test_trigger_long_truncated():
    s = "A) " + "Lorem ipsum " * 50
    result = _shorten_trigger(s)
    assert len(result) <= 201
    assert result.endswith("…")


def test_trigger_empty():
    assert _shorten_trigger("") == ""
    assert _shorten_trigger(None) == ""


# ---------------------------------------------------------------------------
# Excel-Read
# ---------------------------------------------------------------------------

def _make_test_xlsx(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Watchlist"
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_excel_basic_parsing():
    xlsx = _make_test_xlsx([
        ["Aktie", "Symbol", "Richtung", "Entry-Trigger", "These", "Status", "Datum"],
        ["Commerzbank", "CBK.DE", "LONG", "Pullback 33,40€", "These", "⚠️ aktiv", "2026-04-23"],
        ["AIXTRON", "AIXA.DE", "SHORT (Sell-the-news)", "Rejection 44€", "These", "📅 30.04.2026 abwarten", ""],
    ])
    entries = read_journal_watchlist(xlsx)
    assert len(entries) == 2
    assert entries[0]["symbol"] == "CBK.DE"
    assert entries[0]["status"] == "aktiv"
    assert entries[1]["richtung"] == "SHORT"
    assert entries[1]["status"] == "pending"


def test_excel_missing_symbol_raises():
    xlsx = _make_test_xlsx([
        ["Aktie", "Richtung", "Entry-Trigger", "These", "Status", "Datum"],
        ["Commerzbank", "LONG", "Pullback", "T", "⚠️ aktiv", ""],
    ])
    try:
        read_journal_watchlist(xlsx)
        assert False, "Sollte Fehler werfen, weil Symbol-Spalte fehlt"
    except RuntimeError as e:
        assert "Symbol" in str(e)


def test_excel_skip_empty_rows():
    xlsx = _make_test_xlsx([
        ["Aktie", "Symbol", "Richtung", "Entry-Trigger", "These", "Status", "Datum"],
        ["Commerzbank", "CBK.DE", "LONG", "T", "T", "⚠️", ""],
        [None, None, None, None, None, None, None],
        ["AIXTRON", "AIXA.DE", "SHORT", "T", "T", "⏸", ""],
    ])
    entries = read_journal_watchlist(xlsx)
    assert len(entries) == 2


def test_excel_skip_row_with_only_aktie_no_symbol():
    """Eintrag mit Aktie aber ohne Symbol → übersprungen mit Warnung."""
    xlsx = _make_test_xlsx([
        ["Aktie", "Symbol", "Richtung", "Entry-Trigger", "These", "Status", "Datum"],
        ["Commerzbank", "CBK.DE", "LONG", "T", "T", "⚠️", ""],
        ["NeuerWert", "", "LONG", "T", "T", "⚠️", ""],
    ])
    entries = read_journal_watchlist(xlsx)
    assert len(entries) == 1
    assert entries[0]["symbol"] == "CBK.DE"


# ---------------------------------------------------------------------------
# Markdown-Rendering
# ---------------------------------------------------------------------------

def test_render_block_structure():
    entries = [
        {"aktie": "Commerzbank", "symbol": "CBK.DE", "richtung": "LONG",
         "trigger": "Pullback 33,40€", "status": "aktiv", "note": "Note #9"},
    ]
    block = render_watchlist_block(entries, dt.datetime(2026, 4, 29, 18, 30))
    assert "## Watchlist-Trigger (aktive Einträge)" in block
    assert "| Kandidat | Symbol | Richtung | Trigger" in block
    assert "| Commerzbank | CBK.DE | LONG |" in block
    assert "⚠️ aktiv — Note #9" in block
    assert "Auto-Sync zuletzt: 2026-04-29 18:30 UTC (1 Einträge)" in block


def test_render_with_pipe_in_content():
    """Pipe-Zeichen in Trigger-Texten dürfen die Tabelle nicht zerschießen."""
    entries = [
        {"aktie": "Test|Wert", "symbol": "X.DE", "richtung": "LONG",
         "trigger": "A | B alternative", "status": "aktiv", "note": "x|y"},
    ]
    block = render_watchlist_block(entries, dt.datetime(2026, 4, 29))
    # In der Datenzeile muss jeder Pipe innerhalb von Zellen escaped sein
    data_lines = [
        l for l in block.splitlines()
        if l.startswith("|") and "Test" in l
    ]
    assert len(data_lines) == 1
    # Sollte 5 echte Zellen haben + 2 äußere Pipes = 6 Pipes — die in
    # Inhalten escapeten (\|) zählen für split nicht mit
    line = data_lines[0]
    # Echter Pipe-Test: raw line muss escapte Pipes enthalten
    assert "\\|" in line


# ---------------------------------------------------------------------------
# Block-Replace
# ---------------------------------------------------------------------------

def test_replace_existing_block():
    state_text = """\
# STATE START

## Offene Positionen
| # | Trade |
| 39 | Gold |

## Watchlist-Trigger (aktive Einträge)
> alte Pflege-Notiz
| alte | tabelle |

## Offene Notes
- #1 alt
"""
    new_block = "## Watchlist-Trigger (aktive Einträge)\n\nNEUER INHALT\n"
    result = replace_watchlist_block(state_text, new_block)
    assert "alte tabelle" not in result
    assert "NEUER INHALT" in result
    # Nachbar-Sektionen erhalten
    assert "## Offene Positionen" in result
    assert "## Offene Notes" in result
    assert "#1 alt" in result


def test_replace_no_block_existing_inserts_after_state_start():
    state_text = "# STATE START\n\n## Offene Notes\n- foo\n"
    new_block = "## Watchlist-Trigger (aktive Einträge)\n\nNEU\n"
    result = replace_watchlist_block(state_text, new_block)
    assert "NEU" in result
    assert "## Offene Notes" in result
    # NEU sollte vor Offene Notes stehen
    assert result.index("NEU") < result.index("## Offene Notes")


def test_replace_block_at_end_of_file():
    """Watchlist-Block ist die letzte Sektion — Replace darf nicht crashen."""
    state_text = """\
# STATE START

## Watchlist-Trigger (aktive Einträge)
| alt |
"""
    new_block = "## Watchlist-Trigger (aktive Einträge)\n\nNEU\n"
    result = replace_watchlist_block(state_text, new_block)
    assert "NEU" in result
    assert "alt" not in result


# Mini-Runner
if __name__ == "__main__":
    fns = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    passed = failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  ✅ {name}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ {name}: UNEXPECTED — {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
