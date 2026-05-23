"""Tests für watchlist_sync — laufen ohne Netz und ohne Drive.

Schema-Stand 2026-05-23 v2: 3-Trigger-Schema mit 🚦-Ampel. Das Watchlist-Sheet
hat 12 Spalten (Aktie | Symbol | Richtung | 🚦 A | Trigger A | 🚦 B | Trigger B
| 🚦 C | Trigger C | Bemerkungen | Datum hinzugefügt | Verfallsdatum).
"""

import datetime as dt
import io
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
sys.path.insert(0, _SRC)

from openpyxl import Workbook

from watchlist_sync import (
    _count_watchlist_entries,
    _format_trigger_for_state,
    _normalize_gate,
    _shorten_richtung,
    read_journal_watchlist,
    render_watchlist_block,
    replace_watchlist_block,
)

# 12-Spalten-Header des neuen Watchlist-Schemas
HEADER = [
    "Aktie", "Symbol", "Richtung", "🚦 A", "Trigger A", "🚦 B", "Trigger B",
    "🚦 C", "Trigger C", "Bemerkungen", "Datum hinzugefügt", "Verfallsdatum",
]


# ---------------------------------------------------------------------------
# Richtung
# ---------------------------------------------------------------------------

def test_richtung_simple():
    assert _shorten_richtung("LONG") == "LONG"
    assert _shorten_richtung("SHORT") == "SHORT"


def test_richtung_with_modifier():
    assert _shorten_richtung("LONG (Post-Earnings-Pullback)") == "LONG"
    assert _shorten_richtung("SHORT (Bounce)") == "SHORT"
    assert _shorten_richtung("LONG (Momentum-Continuation v0.1)") == "LONG"


def test_richtung_konditional():
    # KONDITIONAL bleibt erhalten — Pipeline kann's interpretieren oder skippen
    result = _shorten_richtung("KONDITIONAL (Long oder Short)")
    assert "KONDITIONAL" in result or "LONG" in result.upper()


# ---------------------------------------------------------------------------
# Gate-Normalisierung
# ---------------------------------------------------------------------------

def test_normalize_gate_known_emojis():
    assert _normalize_gate("🟢") == "🟢"
    assert _normalize_gate("🟡") == "🟡"
    assert _normalize_gate("⏳") == "⏳"
    assert _normalize_gate("🔴") == "🔴"


def test_normalize_gate_with_extra_text():
    # Zelle darf Zusatztext tragen — Emoji wird trotzdem extrahiert
    assert _normalize_gate("🔴 tot seit 22.05.") == "🔴"


def test_normalize_gate_empty_defaults_green():
    # Leere oder unbekannte Zelle → 🟢 (sicherer "wird ausgewertet"-Default)
    assert _normalize_gate("") == "🟢"
    assert _normalize_gate(None) == "🟢"
    assert _normalize_gate("xyz") == "🟢"


# ---------------------------------------------------------------------------
# Trigger-Formatierung fürs STATE-Doc
# ---------------------------------------------------------------------------

def test_format_trigger_basic():
    out = _format_trigger_for_state("A", "🟢", "Daily-Close >50€")
    assert out == "🟢 A) Daily-Close >50€"


def test_format_trigger_strips_existing_marker():
    # Migrations-Artefakt: Zelltext beginnt schon mit 'A)' — nicht doppeln
    out = _format_trigger_for_state("A", "🟢", "A) Daily-Close >50€")
    assert out == "🟢 A) Daily-Close >50€"
    assert out.count("A)") == 1


def test_format_trigger_marker_after_preamble():
    # 'A)' steht hinter einer Präambel (FDX/HNR1-Stil) — Marker raus, Präambel bleibt
    out = _format_trigger_for_state("A", "🔴", "LONG Breakout-Setup: A) 1D-Schluss 380$")
    assert out == "🔴 A) LONG Breakout-Setup: 1D-Schluss 380$"


def test_format_trigger_newlines_collapsed():
    out = _format_trigger_for_state("B", "🟡", "Touch 45€\n\nReverse-Kerze")
    assert "\n" not in out
    assert out == "🟡 B) Touch 45€ Reverse-Kerze"


def test_format_trigger_empty():
    assert _format_trigger_for_state("A", "🟢", "") == ""
    assert _format_trigger_for_state("A", "🟢", None) == ""


# ---------------------------------------------------------------------------
# Excel-Read (12-Spalten-Schema)
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
        HEADER,
        ["United Rentals", "URI", "LONG (Momentum)", "🟢", "A) Daily-Close 1019-1049$",
         "🟢", "B) Touch 925-952$", None, None, "These-Text", "2026-05-22",
         "11.06.2026 (Momentum +14 HT)"],
        ["Nemetschek", "NEM.DE", "SHORT", "🔴", "A) Daily-Close <58€",
         None, None, None, None, "These", "2026-05-12", "27.05.2026"],
    ])
    entries = read_journal_watchlist(xlsx)
    assert len(entries) == 2
    assert entries[0]["symbol"] == "URI"
    assert entries[0]["richtung"] == "LONG"
    # URI hat zwei Trigger-Slots
    assert len(entries[0]["triggers"]) == 2
    assert entries[0]["triggers"][0]["label"] == "A"
    assert entries[0]["triggers"][0]["gate"] == "🟢"
    assert entries[0]["triggers"][1]["label"] == "B"
    # NEM hat nur Trigger A, Gate 🔴
    assert len(entries[1]["triggers"]) == 1
    assert entries[1]["triggers"][0]["gate"] == "🔴"
    # Verfall ISO-normiert
    assert entries[0]["verfall"] == "2026-06-11"


def test_excel_three_triggers():
    xlsx = _make_test_xlsx([
        HEADER,
        ["Check Point", "CHKP", "LONG", "🟢", "A) Trigger eins", "🟡", "B) Trigger zwei",
         "⏳", "C) nach 2026-06-01 Trigger drei", "Bem", "2026-05-20", "01.06.2026"],
    ])
    entries = read_journal_watchlist(xlsx)
    assert len(entries) == 1
    triggers = entries[0]["triggers"]
    assert len(triggers) == 3
    assert [t["label"] for t in triggers] == ["A", "B", "C"]
    assert [t["gate"] for t in triggers] == ["🟢", "🟡", "⏳"]


def test_excel_gate_missing_defaults_green():
    # Trigger gesetzt, Gate-Zelle leer → 🟢 (Trigger soll ausgewertet werden)
    xlsx = _make_test_xlsx([
        HEADER,
        ["Test", "T.DE", "LONG", None, "A) Daily-Close >50€",
         None, None, None, None, "", "2026-05-23", ""],
    ])
    entries = read_journal_watchlist(xlsx)
    assert entries[0]["triggers"][0]["gate"] == "🟢"


def test_excel_missing_symbol_raises():
    xlsx = _make_test_xlsx([
        ["Aktie", "Richtung", "🚦 A", "Trigger A", "Bemerkungen"],
        ["Commerzbank", "LONG", "🟢", "A) Pullback", "T"],
    ])
    try:
        read_journal_watchlist(xlsx)
        assert False, "Sollte Fehler werfen, weil Symbol-Spalte fehlt"
    except RuntimeError as e:
        assert "Symbol" in str(e)


def test_excel_old_schema_raises():
    # Altes 7-Spalten-Schema (Entry-Trigger statt Trigger A) → klare Fehlermeldung
    xlsx = _make_test_xlsx([
        ["Aktie", "Symbol", "Richtung", "Entry-Trigger", "These", "Status", "Datum"],
        ["Commerzbank", "CBK.DE", "LONG", "Pullback 33€", "T", "⚠️ aktiv", "2026-04-23"],
    ])
    try:
        read_journal_watchlist(xlsx)
        assert False, "Sollte Fehler werfen — altes Schema ohne 'Trigger A'"
    except RuntimeError as e:
        assert "Trigger A" in str(e)


def test_excel_skip_empty_rows():
    xlsx = _make_test_xlsx([
        HEADER,
        ["Commerzbank", "CBK.DE", "LONG", "🟢", "A) T", None, None, None, None, "", "", ""],
        [None] * 12,
        ["AIXTRON", "AIXA.DE", "SHORT", "🟡", "A) T", None, None, None, None, "", "", ""],
    ])
    entries = read_journal_watchlist(xlsx)
    assert len(entries) == 2


def test_excel_skip_row_without_trigger():
    # Symbol da, aber kein einziger Trigger → übersprungen
    xlsx = _make_test_xlsx([
        HEADER,
        ["Commerzbank", "CBK.DE", "LONG", "🟢", "A) T", None, None, None, None, "", "", ""],
        ["LeerWert", "LEER.DE", "LONG", None, None, None, None, None, None, "Bem", "", ""],
    ])
    entries = read_journal_watchlist(xlsx)
    assert len(entries) == 1
    assert entries[0]["symbol"] == "CBK.DE"


def test_excel_skip_row_with_only_aktie_no_symbol():
    xlsx = _make_test_xlsx([
        HEADER,
        ["Commerzbank", "CBK.DE", "LONG", "🟢", "A) T", None, None, None, None, "", "", ""],
        ["NeuerWert", "", "LONG", "🟢", "A) T", None, None, None, None, "", "", ""],
    ])
    entries = read_journal_watchlist(xlsx)
    assert len(entries) == 1
    assert entries[0]["symbol"] == "CBK.DE"


# ---------------------------------------------------------------------------
# Markdown-Rendering
# ---------------------------------------------------------------------------

def _entry(aktie="Commerzbank", symbol="CBK.DE", richtung="LONG",
           triggers=None, verfall=""):
    if triggers is None:
        triggers = [{"label": "A", "gate": "🟢", "text": "A) Daily-Close >50€"}]
    return {"aktie": aktie, "symbol": symbol, "richtung": richtung,
            "triggers": triggers, "verfall": verfall}


def test_render_block_structure():
    block = render_watchlist_block([_entry()], dt.datetime(2026, 5, 23, 18, 30))
    assert "## Watchlist-Trigger (aktive Einträge)" in block
    assert "| Kandidat | Symbol | Richtung | Trigger" in block
    assert "| Commerzbank | CBK.DE | LONG |" in block
    # Status-Spalte ist eintragsweit fix
    assert "⚠️ aktiv" in block
    assert "Auto-Sync zuletzt: 2026-05-23 18:30 UTC (1 Einträge)" in block


def test_render_trigger_block_joined():
    """Mehrere Trigger werden als '🟢 A) … · 🔴 B) …' in EINE Zelle gerendert."""
    e = _entry(triggers=[
        {"label": "A", "gate": "🟢", "text": "A) Daily-Close >50€"},
        {"label": "B", "gate": "🔴", "text": "B) Touch ~45€"},
    ])
    block = render_watchlist_block([e], dt.datetime(2026, 5, 23))
    data_line = [l for l in block.splitlines()
                 if l.startswith("|") and "CBK.DE" in l][0]
    assert "🟢 A) Daily-Close >50€" in data_line
    assert "🔴 B) Touch ~45€" in data_line
    assert " · " in data_line


def test_render_gate_survives_roundtrip():
    """Gerendertes Gate muss vom state_parser wieder als ParsedTrigger.gate
    erkannt werden — End-to-End-Absicherung der Sync-Kette."""
    from state_parser import _parse_triggers
    e = _entry(triggers=[
        {"label": "A", "gate": "🟢", "text": "A) Daily-Close >50,46€"},
        {"label": "B", "gate": "🔴", "text": "B) Touch ~45€"},
    ])
    block = render_watchlist_block([e], dt.datetime(2026, 5, 23))
    data_line = [l for l in block.splitlines()
                 if l.startswith("|") and "CBK.DE" in l][0]
    # Trigger-Zelle ist die 4. echte Spalte
    cols = [c.strip() for c in data_line.split("|")][1:-1]
    trigger_cell = cols[3]
    triggers = _parse_triggers(trigger_cell)
    assert len(triggers) == 2
    assert triggers[0].gate == "🟢"
    assert triggers[1].gate == "🔴"


def test_render_with_pipe_in_content():
    """Pipe-Zeichen in Trigger-Texten dürfen die Tabelle nicht zerschießen."""
    e = _entry(aktie="Test|Wert", symbol="X.DE",
               triggers=[{"label": "A", "gate": "🟢", "text": "A) X | Y alternative"}])
    block = render_watchlist_block([e], dt.datetime(2026, 5, 23))
    data_lines = [l for l in block.splitlines()
                  if l.startswith("|") and "Test" in l]
    assert len(data_lines) == 1
    assert "\\|" in data_lines[0]


def test_render_marker_not_doubled():
    """Zelltext mit vorhandenem 'A)'-Marker → im Output nur ein 'A)'."""
    e = _entry(triggers=[{"label": "A", "gate": "🟢", "text": "A) Daily-Close >50€"}])
    block = render_watchlist_block([e], dt.datetime(2026, 5, 23))
    data_line = [l for l in block.splitlines()
                 if l.startswith("|") and "CBK.DE" in l][0]
    assert data_line.count("A)") == 1


# ---------------------------------------------------------------------------
# Block-Replace (unverändert — Funktion nicht angefasst)
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
    assert "## Offene Positionen" in result
    assert "## Offene Notes" in result
    assert "#1 alt" in result


def test_replace_no_block_existing_inserts_after_state_start():
    state_text = "# STATE START\n\n## Offene Notes\n- foo\n"
    new_block = "## Watchlist-Trigger (aktive Einträge)\n\nNEU\n"
    result = replace_watchlist_block(state_text, new_block)
    assert "NEU" in result
    assert "## Offene Notes" in result
    assert result.index("NEU") < result.index("## Offene Notes")


def test_replace_block_at_end_of_file():
    state_text = """\
# STATE START

## Watchlist-Trigger (aktive Einträge)
| alt |
"""
    new_block = "## Watchlist-Trigger (aktive Einträge)\n\nNEU\n"
    result = replace_watchlist_block(state_text, new_block)
    assert "NEU" in result
    assert "alt" not in result


# ---------------------------------------------------------------------------
# Sanity-Check Count (unverändert — Funktion nicht angefasst)
# ---------------------------------------------------------------------------

def test_count_entries_basic():
    state = """\
# STATE START

## Watchlist-Trigger (aktive Einträge)

| Kandidat | Symbol | Richtung | Trigger (🚦 A/B/C) | Status | Verfall |
|----------|--------|----------|--------------------|--------|---------|
| Commerzbank | CBK.DE | LONG | 🟢 A) T | ⚠️ aktiv | |
| TUI | TUI1.DE | LONG | 🔴 A) T | ⚠️ aktiv | |
| AIXTRON | AIXA.DE | SHORT | ⏳ A) T | ⚠️ aktiv | |

## Offene Notes
"""
    assert _count_watchlist_entries(state) == 3


def test_count_entries_empty_block():
    state = """\
## Watchlist-Trigger (aktive Einträge)

| Kandidat | Symbol | Richtung | Trigger (🚦 A/B/C) | Status | Verfall |
|----------|--------|----------|--------------------|--------|---------|

## Offene Notes
"""
    assert _count_watchlist_entries(state) == 0


def test_count_entries_no_block():
    state = "# STATE START\n\n## Offene Positionen\n| 1 | foo |\n"
    assert _count_watchlist_entries(state) == 0


def test_count_entries_robust_against_plain_text_export():
    state = """\
STATE START


## Watchlist-Trigger (aktive Einträge)



| Kandidat | Symbol | Richtung | Trigger (🚦 A/B/C) | Status | Verfall |
|----------|--------|----------|--------------------|--------|---------|
| TestA    | A.DE   | LONG     | 🟢 A) T            | ⚠️ aktiv | |
| TestB    | B.DE   | SHORT    | 🔴 A) T            | ⚠️ aktiv | |


## Offene Notes
"""
    assert _count_watchlist_entries(state) == 2


# Mini-Runner
if __name__ == "__main__":
    fns = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    passed = failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  OK {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  FAIL {name}: UNEXPECTED — {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
