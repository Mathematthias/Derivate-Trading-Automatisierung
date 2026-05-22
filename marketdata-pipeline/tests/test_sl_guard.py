"""Tests für den Lektion-4-SL-Guard (Note #88/#89/#92, 2026-05-22).

Drei Ebenen:
1. _extract_sl (state_parser) — SL-Art + Fix-Level aus Trigger-Text.
2. _parse_single_trigger — sl_kind/sl_value landen auf ParsedTrigger.
3. check_sl_lektion4 (filter_engine) — SL-Abstand ÷ ATR an Zonenkante.

Regressionsfälle aus dem Audit 2026-05-22 (Patch §6) sind als Fixtures
hinterlegt.

Ausführen vom marketdata-pipeline/ Verzeichnis:
    PYTHONPATH=./src python tests/test_sl_guard.py
oder mit pytest:
    PYTHONPATH=./src pytest tests/test_sl_guard.py -v
"""

import os
import sys
from dataclasses import dataclass
from typing import Optional

# src/ in den Path, damit die Module gefunden werden
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
sys.path.insert(0, _SRC)

from state_parser import _extract_sl, _parse_single_trigger  # noqa: E402
from filter_engine import check_sl_lektion4  # noqa: E402


@dataclass
class FakeSnap:
    """Minimaler Snapshot-Stub — nur atr14 ist für den SL-Guard relevant."""
    symbol: str = "TEST"
    price: float = 100.0
    atr14: Optional[float] = None


# ============================================================
# EBENE 1 — _extract_sl
# ============================================================

def test_extract_sl_fix_euro():
    assert _extract_sl("SL <125€") == ("fix", 125.0)


def test_extract_sl_fix_dezimalkomma():
    """Deutsche Dezimalnotation: SL <3,55€ → 3.55."""
    assert _extract_sl("SL <3,55€") == ("fix", 3.55)


def test_extract_sl_fix_dollar_und_groesser():
    assert _extract_sl("SL >58$") == ("fix", 58.0)


def test_extract_sl_fix_ohne_operator_und_waehrung():
    """SL X (ohne Operator, ohne Währung) → trotzdem Fix-Level."""
    assert _extract_sl("Daily-Hammer ≥240€. SL 232. TP1 252€") == ("fix", 232.0)


def test_extract_sl_fix_mit_klammerkommentar():
    """Knackpunkt: 'unter 52W-Tief' ist Kommentar, NICHT Pattern-Marker.

    Das Fix-Muster wird am Anfang des SL-Ausdrucks verankert geprüft —
    der parenthetische Zusatz darf nicht als Pattern fehlklassifiziert werden.
    """
    assert _extract_sl("SL <125€ (unter 52W-Tief)") == ("fix", 125.0)


def test_extract_sl_entry_relativ_keyword():
    assert _extract_sl("SL entry-relativ -1,5×ATR") == ("entry_relativ", None)


def test_extract_sl_entry_relativ_ohne_bindestrich():
    assert _extract_sl("SL entry relativ") == ("entry_relativ", None)


def test_extract_sl_entry_relativ_formel_form():
    """'Entry -1,5×ATR' ohne das Wort 'relativ' → trotzdem entry_relativ."""
    assert _extract_sl("SL = Entry -1,5×ATR") == ("entry_relativ", None)


def test_extract_sl_pattern_kerzenfunktion():
    assert _extract_sl(
        "SL = Reverse-Kerzen-Hoch + 1,0×ATR-4h"
    ) == ("pattern", None)


def test_extract_sl_pattern_atr4h():
    """ATR-4h-Konvention (INTU-Typ) → pattern, kein 1D-ATR-Check."""
    assert _extract_sl("SL = Kerzen-Hoch + 1,0×ATR-4h") == ("pattern", None)


def test_extract_sl_pattern_prozent():
    """Prozentualer SL ist relativ, kein Fix-Level → pattern (skip)."""
    assert _extract_sl("SL 5%") == ("pattern", None)


def test_extract_sl_kein_sl():
    assert _extract_sl("Daily-Close >180€ + Vol >Avg-20d") == (None, None)


def test_extract_sl_stoppt_vor_tp():
    """SL-Ausdruck darf nicht in den TP-Teil hineinlaufen."""
    assert _extract_sl("SL <245€ TP1 272€ TP2 290€") == ("fix", 245.0)


# ============================================================
# EBENE 2 — _parse_single_trigger reicht sl_kind/sl_value durch
# ============================================================

def test_parse_single_trigger_fix():
    pt = _parse_single_trigger(
        "A", "Touch EMA50 1D 130,00–136,00€ + Bounce. SL <125€. TP1 142€"
    )
    assert pt.sl_kind == "fix"
    assert pt.sl_value == 125.0


def test_parse_single_trigger_entry_relativ():
    pt = _parse_single_trigger(
        "A", "Touch EMA20 1D ~167€ + Bounce. SL entry-relativ -1,5×ATR. TP1 178€"
    )
    assert pt.sl_kind == "entry_relativ"
    assert pt.sl_value is None


def test_parse_single_trigger_pattern():
    pt = _parse_single_trigger(
        "A", "Reverse-Kerze ~600€ + RSI<35. SL = Reverse-Kerzen-Hoch + 1,0×ATR-4h"
    )
    assert pt.sl_kind == "pattern"
    assert pt.sl_value is None


# ============================================================
# EBENE 3 — check_sl_lektion4, Regressionsfälle Audit 2026-05-22
# ============================================================

def _trigger(text: str):
    """Helper: rohen Trigger-Text durch den echten Parser jagen."""
    return _parse_single_trigger("A", text)


def test_regression_chkp_a_verstoss():
    """CHKP-A: Zone 130–136, Fix-SL 125, ATR 5,4 → verstoss, ratio ≈ 0,93."""
    trig = _trigger("Touch EMA50 1D 130,00–136,00€ + Bounce. SL <125€. TP1 142€")
    snap = FakeSnap(symbol="CHKP", atr14=5.4)
    level, msg = check_sl_lektion4(trig, snap, "LONG")
    assert level == "verstoss", msg
    assert "0.93" in msg, msg


def test_regression_sie_b_verstoss():
    """SIE-B: Zone 256–260, Fix-SL 245, ATR 8,39 → verstoss, ratio ≈ 1,31."""
    trig = _trigger("Daily-Close 256,00–260,00€ [breakout]. SL <245€. TP1 272€")
    snap = FakeSnap(symbol="SIE.DE", atr14=8.39)
    level, msg = check_sl_lektion4(trig, snap, "LONG")
    assert level == "verstoss", msg
    assert "1.31" in msg, msg


def test_regression_fang_b_grenz():
    """FANG-B: Zone 198–199,5, Fix-SL 189, ATR 6,53 → grenz, ratio ≈ 1,38."""
    trig = _trigger("Pullback 198,00–199,50€ [pullback]. SL <189€. TP1 210€")
    snap = FakeSnap(symbol="FANG", atr14=6.53)
    level, msg = check_sl_lektion4(trig, snap, "LONG")
    assert level == "grenz", msg
    assert "1.38" in msg, msg


def test_regression_hnr1_a_ok():
    """HNR1-A: Schwelle 240, Fix-SL 232, ATR 2,99 → ok, ratio ≈ 2,68.

    Pattern-Schwellen-Trigger ohne echte Zone — die Schwelle ist die Kante.
    """
    trig = _trigger("Daily-Hammer ≥240€ + RSI<35. SL <232€. TP1 252€")
    snap = FakeSnap(symbol="HNR1.DE", atr14=2.99)
    level, msg = check_sl_lektion4(trig, snap, "LONG")
    assert level == "ok", msg
    assert "2.68" in msg, msg


def test_regression_uri_a_entry_relativ_ok():
    """URI-A: SL entry-relativ → ok ohne Rechnung."""
    trig = _trigger("Touch EMA20 1D ~167€ + Bounce. SL entry-relativ -1,5×ATR")
    snap = FakeSnap(symbol="URI", atr14=4.0)
    level, msg = check_sl_lektion4(trig, snap, "LONG")
    assert level == "ok", msg
    assert "entry-relativ" in msg


def test_regression_intu_a_pattern_skip():
    """INTU-A: SL = Reverse-Kerzen-Hoch + 1,0×ATR-4h → skip (pattern)."""
    trig = _trigger("Reverse-Kerze ~600€. SL = Reverse-Kerzen-Hoch + 1,0×ATR-4h")
    snap = FakeSnap(symbol="INTU", atr14=12.0)
    level, msg = check_sl_lektion4(trig, snap, "LONG")
    assert level == "skip", msg


def test_regression_off_universe_atr_none_skip():
    """Off-universe-Ticker ohne ATR → skip, kein Verstoß."""
    trig = _trigger("Pullback 198,00–199,50€. SL <189€. TP1 210€")
    snap = FakeSnap(symbol="FANG", atr14=None)
    level, msg = check_sl_lektion4(trig, snap, "LONG")
    assert level == "skip", msg
    assert "ATR" in msg


def test_regression_snap_none_skip():
    """Kein Snapshot überhaupt → skip statt Crash."""
    trig = _trigger("Pullback 198,00–199,50€. SL <189€")
    level, msg = check_sl_lektion4(trig, None, "LONG")
    assert level == "skip", msg


# ============================================================
# EBENE 3 — Richtungsabhängigkeit der Zonenkante
# ============================================================

def test_short_zonenkante_ist_obergrenze():
    """SHORT zieht die Obergrenze als ungünstige Kante, LONG die Untergrenze.

    Zone 100–110, Fix-SL 118, ATR 14 — bewusst so gewählt, dass beide
    Richtungen in 'verstoss' fallen (nur dann steht die Kante in der Meldung).
    SHORT: Kante 110, Abstand 8. LONG: Kante 100, Abstand 18.
    """
    trig = _trigger("Re-Short 100,00–110,00€ [breakout]. SL <118€")
    snap = FakeSnap(symbol="TEST", atr14=14.0)
    level_short, msg_short = check_sl_lektion4(trig, snap, "SHORT")
    level_long, msg_long = check_sl_lektion4(trig, snap, "LONG")
    assert level_short == "verstoss" and "Zonenkante 110" in msg_short, msg_short
    assert level_long == "verstoss" and "Zonenkante 100" in msg_long, msg_long


def test_grenzwert_genau_135_ist_grenz():
    """ratio == 1,35 ist NICHT mehr verstoss (Grenze ist <1,35)."""
    # Zone-Untergrenze 100, SL 86,5 → Abstand 13,5; ATR 10 → ratio 1,35
    trig = _trigger("Pullback 100,00–104,00€. SL <86,5€")
    snap = FakeSnap(atr14=10.0)
    level, msg = check_sl_lektion4(trig, snap, "LONG")
    assert level == "grenz", msg


def test_grenzwert_genau_15_ist_ok():
    """ratio == 1,5 ist konform (Grenze ist <1,5)."""
    # Untergrenze 100, SL 85 → Abstand 15; ATR 10 → ratio 1,50
    trig = _trigger("Pullback 100,00–104,00€. SL <85€")
    snap = FakeSnap(atr14=10.0)
    level, msg = check_sl_lektion4(trig, snap, "LONG")
    assert level == "ok", msg


if __name__ == "__main__":
    fns = [
        (name, fn) for name, fn in sorted(globals().items())
        if name.startswith("test_") and callable(fn)
    ]
    passed = 0
    failed = 0
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
