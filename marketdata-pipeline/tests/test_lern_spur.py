"""Lern-Spur LS-1 (Neuaufstellung A+, 2026-11-07)."""
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src import lern_spur as ls

CFG = yaml.safe_load((Path(__file__).parent.parent / "config" / "lern_spur.yaml").read_text())


def _df(close):
    idx = pd.bdate_range("2025-01-01", periods=len(close))
    c = np.asarray(close, dtype=float)
    return ls.ind(pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": 1e6}, index=idx))


def test_signal_kreuzung_ueber_ema200():
    # lange Seitwaerts-/Aufwaertsphase, dann kurzer Ruecksetzer und Wiederanstieg -> EMA20 kreuzt EMA50 hoch
    base = list(np.linspace(50, 100, 220)) + list(np.linspace(100, 92, 25)) + list(np.linspace(92, 104, 30))
    d = _df(base)
    tage = [k for k in range(215, len(d)) if ls.signal_heute(d.iloc[:k + 1], CFG)]
    assert tage, "Kreuzung muss erkannt werden"
    k = tage[0]
    x = d.iloc[k]
    assert x.ema20 > x.ema50 and x.Close > x.ema200


def test_kein_signal_unter_ema200():
    base = list(np.linspace(150, 100, 220)) + list(np.linspace(100, 92, 25)) + list(np.linspace(92, 99, 30))
    d = _df(base)
    assert not any(ls.signal_heute(d.iloc[:k + 1], CFG) for k in range(215, len(d)))


def test_stop_nie_lockern_und_beruehrung():
    d = _df(list(np.linspace(100, 120, 260)))
    pos = {"symbol": "X", "einstieg_datum": str(d.index[230].date()), "einstieg_kurs": float(d.Close.iloc[230]),
           "stop_initial": float(d.Close.iloc[230]) - 3, "stop": float(d.Close.iloc[230]) - 3}
    p1 = ls.stop_nachziehen(pos, d, CFG)
    assert p1["stop"] >= pos["stop"] and not p1["stop_beruehrt"]
    p2 = ls.stop_nachziehen({**p1, "stop": 10_000.0}, d, CFG)       # absurder Stop: nie lockern
    assert p2["stop"] == 10_000.0


def test_sperre_review_und_notbremse():
    st = {"abgeschlossen": [{"r": 0.5}] * 5, "reviews": {}}
    assert "Trade 5" in ls.sperre(st, CFG)
    st["reviews"] = {"5": "2026-12-01"}
    assert ls.sperre(st, CFG) is None
    st = {"abgeschlossen": [{"r": -1.0}] * 6, "reviews": {"5": "x"}}
    assert ls.sperre(st, CFG).startswith("Notbremse")


def test_kandidat_stueck_in_eur():
    d = _df(list(np.linspace(50, 100, 260)))
    c = ls.kandidat("AAPL", d, CFG, fx_usd=1.10)
    risiko = c["stueck"] * CFG["stop_atr"] * c["atr"] / 1.10
    assert c["waehrung"] == "USD" and 0 < risiko <= CFG["r_eur"] + 1e-6


def test_universum_nur_eur_usd():
    u = ls.universum(Path(__file__).parent.parent / "config", CFG["suffixe_eur"])
    assert u and all("." not in s or any(s.endswith(x) for x in CFG["suffixe_eur"]) for s in u)
    assert "RHM.DE" not in u


def test_einsatzdeckel_und_rangfolge():
    d = _df(list(np.linspace(50, 100, 260)))
    c = ls.kandidat("SAP.DE", d, CFG, fx_usd=1.10)
    assert c["einsatz_eur"] <= CFG["max_einsatz_eur"] + 1e-6
    assert c["r_eur_effektiv"] <= CFG["r_eur"] + 1e-6
    assert CFG["auswahl"] == {"feld": "atrp", "absteigend": False}


def test_ls2_filter_ema50_ueber_ema200():
    # Kreuzung EMA20/50 mit Schluss ueber EMA200, aber EMA50 noch darunter (ALGN-Fall 2026-11-06)
    base = list(np.linspace(150, 100, 220)) + list(np.linspace(100, 90, 15)) + list(np.linspace(90, 160, 25))
    d = _df(base)
    lose = dict(CFG, signal=dict(CFG["signal"], ema50_ueber_ema200=False))
    tage = [k for k in range(215, len(d)) if ls.signal_heute(d.iloc[:k + 1], lose)]
    assert tage, "ohne Filter muss das Signal kommen"
    assert any(d.ema50.iloc[k] < d.ema200.iloc[k] for k in tage)
    assert not any(ls.signal_heute(d.iloc[:k + 1], CFG) and d.ema50.iloc[k] < d.ema200.iloc[k]
                   for k in range(215, len(d)))


def test_ls2_abgesicherte_position_gibt_platz_frei():
    cfg = dict(CFG)
    risiko = {"einstieg_kurs": 100, "stop": 95}
    sicher = {"einstieg_kurs": 100, "stop": 100}
    assert ls.freie_plaetze([], cfg) == 2
    assert ls.freie_plaetze([risiko], cfg) == 1
    assert ls.freie_plaetze([risiko, risiko], cfg) == 0
    assert ls.freie_plaetze([risiko, sicher], cfg) == 1
    assert ls.freie_plaetze([sicher, sicher], cfg) == 1          # Gesamtgrenze 3
    assert ls.freie_plaetze([sicher, sicher, sicher], cfg) == 0
    d = _df(list(np.linspace(100, 160, 260)))
    pos = {"symbol": "X", "einstieg_datum": str(d.index[200].date()), "einstieg_kurs": float(d.Close.iloc[200]),
           "stop_initial": float(d.Close.iloc[200]) - 3, "stop": float(d.Close.iloc[200]) - 3}
    assert ls.stop_nachziehen(pos, d, cfg)["abgesichert"]
