"""Tests fuer die Stufe-2-Ausnahme nach Gate-Status (Fix 2026-09-09).

Hintergrund: `watchlist_sync` schreibt JEDE Journal-Zeile mit Symbol und
Trigger-Text nach STATE — ohne Gate-Filter, also auch archivierte 🔴-Zeilen.
`marketdata_sync` bildete daraus `excluded_symbols` und uebergab sie an
`evaluate_universe`, das jedes darin enthaltene Symbol in Stufe 2 ueberspringt.
Zusammen mit dem 🔴-Skip in `evaluate_trigger` (Stufe 1) und
`gamechanger_include_watchlist: false` fiel ein archiviertes Symbol damit
VOLLSTAENDIG aus der Pipeline: weder ausgewertet noch neu entdeckt, dauerhaft.
Am Journal-Stand 2026-09-09 betraf das 28 von 71 Symbolen.

Was der Fix NICHT aendert: den Pull. `build_pull_universe` zieht weiter aus
`watchlist_entries`, damit die Kurse archivierter Zeilen im Universum bleiben —
ohne sie koennte der Re-Eval-Check archivierte Zeilen nicht pruefen.
"""
import pytest

from state_parser import (
    ParsedTrigger,
    WatchlistEntry,
    active_watchlist_symbols,
    has_live_trigger,
)


def entry(symbol, *gates):
    return WatchlistEntry(
        name=f"Test ({symbol})", symbol=symbol, direction="LONG",
        trigger_raw="x", status="aktiv", status_note="",
        triggers=[ParsedTrigger(label=chr(65 + i), raw="x", gate=g)
                  for i, g in enumerate(gates)],
    )


# --- has_live_trigger ----------------------------------------------------

def test_alle_trigger_tot_ist_tot():
    assert has_live_trigger(entry("TOT.DE", "🔴", "🔴")) is False


def test_ein_lebender_trigger_reicht():
    """Gemischte Zeile: A archiviert, B noch scharf -> die Zeile lebt."""
    assert has_live_trigger(entry("MIX.DE", "🔴", "🟢")) is True


@pytest.mark.parametrize("gate", ["🟢", "🟡", "⏳"])
def test_nur_rot_gilt_als_tot(gate):
    """⏳ wartet und 🟡 beobachtet — beide werden weiterverfolgt."""
    assert has_live_trigger(entry("X.DE", gate)) is True


def test_ohne_gate_gilt_als_lebendig():
    """Alt-STATE-Dokumente ohne Ampel-Emoji duerfen nicht still wegkippen."""
    assert has_live_trigger(entry("ALT.DE", None)) is True


def test_ohne_trigger_gilt_als_lebendig():
    e = WatchlistEntry(name="Leer", symbol="LEER.DE", direction="LONG",
                       trigger_raw="", status="aktiv", status_note="")
    assert has_live_trigger(e) is True


# --- active_watchlist_symbols -------------------------------------------

def test_archivierte_symbole_blockieren_stufe2_nicht_mehr():
    entries = [
        entry("LEBT.DE", "🟢"),
        entry("WARTET.DE", "⏳"),
        entry("TOT.DE", "🔴"),
        entry("AUCHTOT.DE", "🔴", "🔴"),
        entry("MIX.DE", "🔴", "🟡"),
    ]
    assert active_watchlist_symbols(entries) == {
        "LEBT.DE", "WARTET.DE", "MIX.DE",
    }


def test_symbolloser_eintrag_faellt_raus():
    entries = [entry("", "🟢"), entry("OK.DE", "🟢")]
    assert active_watchlist_symbols(entries) == {"OK.DE"}


def test_regression_vorher_alle_jetzt_nur_lebende():
    """Die Zahl, um die es ging: 5 Zeilen, vorher 5 Blocker, jetzt 3."""
    entries = [
        entry("A.DE", "🟢"), entry("B.DE", "🟡"), entry("C.DE", "⏳"),
        entry("D.DE", "🔴"), entry("E.DE", "🔴"),
    ]
    alt = {e.symbol for e in entries if e.symbol}          # altes Verhalten
    neu = active_watchlist_symbols(entries)
    assert len(alt) == 5
    assert len(neu) == 3
    assert alt - neu == {"D.DE", "E.DE"}


def test_pull_liste_bleibt_unberuehrt():
    """Der Fix darf den Pull NICHT verkleinern — sonst verliert der
    Re-Eval-Check die Kurse archivierter Zeilen."""
    entries = [entry("LEBT.DE", "🟢"), entry("TOT.DE", "🔴")]
    pull = {e.symbol for e in entries if e.symbol}   # so baut marketdata_sync Z145
    assert pull == {"LEBT.DE", "TOT.DE"}
    assert active_watchlist_symbols(entries) == {"LEBT.DE"}
