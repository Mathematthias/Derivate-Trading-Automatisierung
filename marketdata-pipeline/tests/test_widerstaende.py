"""2026-10-28 (User „A und C jetzt“): Widerstandszonen mit Klasse fuer TP1 am ersten starken Widerstand."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import widerstaende as wd  # noqa: E402


def _df(closes, spanne=0.6):
    idx = pd.bdate_range("2025-11-03", periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"Open": c, "High": c + spanne, "Low": c - spanne, "Close": c})


def _welle(basis, amp, n, phase=0.0):
    return [basis + amp * np.sin(2 * np.pi * (i / 20.0) + phase) for i in range(n)]


def test_doppeltop_mit_reaktion_ist_mindestens_mittel():
    # Seitwaerts 100-110 mit mehreren Hochs bei ~110, dann Ruecksetzer auf 102
    closes = _welle(105, 5, 120) + [104 - i * 0.2 for i in range(10)]
    z = wd.zonen(_df(closes), preis=closes[-1], atr=1.5)
    oben = [x for x in z["ueber"] if 109 <= x["level"] <= 112]
    assert oben, z["ueber"]
    assert oben[0]["klasse"] in ("stark", "mittel")
    assert any(g.endswith("x") for g in oben[0]["gruende"])


def test_rollentausch_alte_unterstuetzung_ueber_dem_kurs():
    # Boden bei ~100 mehrfach getestet, dann Bruch nach unten auf 92
    closes = _welle(104, 4, 100) + [99 - i * 0.7 for i in range(12)]
    z = wd.zonen(_df(closes), preis=closes[-1], atr=1.5)
    alt = [x for x in z["ueber"] if 99 <= x["level"] <= 101.5]
    assert alt and "Rollentausch" in alt[0]["gruende"]


def test_52w_hoch_und_runde_zahl_zaehlen():
    closes = _welle(240, 8, 120) + [236 - i * 0.3 for i in range(8)]
    hoch = max(c + 0.6 for c in closes)
    z = wd.zonen(_df(closes), preis=closes[-1], atr=4.0, hoch_52w=hoch)
    top = max(z["ueber"], key=lambda x: x["level"])
    assert "52W-Hoch" in top["gruende"]
    assert top["klasse"] == "stark"


def test_einzelnes_hoch_ohne_merkmale_schwach():
    closes = [100 + i * 0.05 for i in range(60)] + [104, 106, 104] + [103 - i * 0.05 for i in range(10)]
    z = wd.zonen(_df(closes, spanne=0.2), preis=closes[-1], atr=2.0)
    spitze = [x for x in z["ueber"] if 105.5 <= x["level"] <= 106.5]
    assert spitze and spitze[0]["klasse"] in ("schwach", "mittel")


def test_ohne_atr_oder_daten_none():
    assert wd.zonen(_df([1.0] * 10), 1.0, 0.1) is None
    assert wd.zonen(_df([1.0] * 40), 1.0, None) is None


def test_sortierung_und_abstand():
    closes = _welle(105, 5, 120) + [104 - i * 0.2 for i in range(10)]
    z = wd.zonen(_df(closes), preis=closes[-1], atr=1.5)
    lv = [x["level"] for x in z["ueber"]]
    assert lv == sorted(lv)
    assert all(x["dist_atr"] <= wd.MAX_DIST_ATR for x in z["ueber"])
