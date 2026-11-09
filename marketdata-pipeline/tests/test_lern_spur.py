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
    n = int(-CFG["notbremse_r"])
    st = {"abgeschlossen": [{"r": -1.0}] * (n - 1), "reviews": {"5": "x"}}
    assert ls.sperre(st, CFG) is None or not ls.sperre(st, CFG).startswith("Notbremse")
    st = {"abgeschlossen": [{"r": -1.0}] * n, "reviews": {"5": "x", "10": "x"}}
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


def test_ls2_risikobudget_und_kapital():
    cfg = dict(CFG)
    assert cfg["r_eur"] == 50 and cfg["risiko_budget_r"] == 3 and cfg["kapital_eur"] == 12000
    voll = {"symbol": "X.DE", "einstieg_kurs": 100, "stop_initial": 95, "stop": 95, "stueck": 10, "einsatz_eur": 1000}
    halb = dict(voll, stop=97.5)
    sicher = dict(voll, stop=100)
    b = ls.budget([voll, halb, sicher], cfg, 1.1)
    assert b["risiko_offen_eur"] == 75.0 and b["risiko_frei_eur"] == 75.0
    assert b["kapital_gebunden_eur"] == 3000.0
    kand = [{"stueck": 5, "r_eur_effektiv": 50, "einsatz_eur": 1800},
            {"stueck": 5, "r_eur_effektiv": 50, "einsatz_eur": 1800},
            {"stueck": 5, "r_eur_effektiv": 20, "einsatz_eur": 900}]
    assert ls.zuege_markieren(kand, b) == 2 and [c["zug"] for c in kand] == [True, False, True]
    eng = dict(b, kapital_frei_eur=1000.0)
    assert ls.zuege_markieren(kand, eng) == 1 and [c["zug"] for c in kand] == [False, False, True]
    # USD-Position: Risiko in EUR umgerechnet
    usd = {"symbol": "ALGN", "einstieg_kurs": 110, "stop_initial": 100, "stop": 100, "stueck": 5}
    assert round(ls.rest_risiko_eur(usd, cfg, 1.25), 2) == 40.0


def test_ls2_stop_abgesichert():
    d = _df(list(np.linspace(100, 160, 260)))
    pos = {"symbol": "X", "einstieg_datum": str(d.index[200].date()), "einstieg_kurs": float(d.Close.iloc[200]),
           "stop_initial": float(d.Close.iloc[200]) - 3, "stop": float(d.Close.iloc[200]) - 3}
    assert ls.stop_nachziehen(pos, d, CFG)["abgesichert"]


def test_veto_papiertrade_wie_backtest():
    # Anstieg, dann Einbruch: Papier-Trade laeuft mit, zieht Stop nach und wird am Stop geschlossen
    d = _df(list(np.linspace(100, 110, 200)) + list(np.linspace(110, 150, 15)) + list(np.linspace(150, 100, 45)))
    i = 199
    e, a = float(d.Close.iloc[i]), float(d.atr.iloc[i])
    p = {"symbol": "X", "einstieg_datum": str(d.index[i].date()), "einstieg_kurs": e,
         "stop_initial": e - 1.5 * a, "stop": e - 1.5 * a, "grund": "Story gefaellt mir nicht"}
    halb = ls.papier_update(p, d.iloc[:215], CFG)
    assert not halb.get("ausstieg_datum") and halb["stop"] > p["stop"]
    assert ls.papier_update(dict(p), d.iloc[:201], CFG)["stop"] >= p["stop"]          # Rundung lockert nie
    fertig = ls.papier_update(halb, d, CFG)
    assert fertig["grund_ausstieg"] == "stop" and fertig["r"] > 0
    assert ls.papier_update(fertig, d, CFG) == fertig


def test_chf_waehrung_fx_und_deckel():
    assert ls.waehrung("NESN.SW") == "CHF" and ls.waehrung("SAP.DE") == "EUR" and ls.waehrung("AMZN") == "USD"
    fx = {"USD": 1.12, "CHF": 0.94}
    assert ls.fx_kurs("CHF", fx) == 0.94 and ls.fx_kurs("EUR", fx) == 1.0 and ls.fx_kurs("USD", 1.12) == 1.12
    # CHF-Position: Restrisiko in EUR
    p = {"symbol": "NOVN.SW", "einstieg_kurs": 94.0, "stop_initial": 90.24, "stop": 90.24, "stueck": 10}
    assert round(ls.rest_risiko_eur(p, CFG, fx), 2) == 40.0
    bud = {"risiko_frei_eur": 150.0, "kapital_frei_eur": 12000.0}
    kand = [{"symbol": "NESN.SW", "waehrung": "CHF", "stueck": 5, "r_eur_effektiv": 40, "einsatz_eur": 900},
            {"symbol": "ROG.SW", "waehrung": "CHF", "stueck": 5, "r_eur_effektiv": 40, "einsatz_eur": 900},
            {"symbol": "SAP.DE", "waehrung": "EUR", "stueck": 5, "r_eur_effektiv": 40, "einsatz_eur": 900}]
    assert ls.zuege_markieren(kand, bud, [], CFG["max_je_waehrung"]) == 2
    assert [c["zug"] for c in kand] == [True, False, True]
    # schon eine CHF-Position offen: kein weiterer CHF-Zug
    assert ls.zuege_markieren(kand, bud, [p], CFG["max_je_waehrung"]) == 1
    assert [c["zug"] for c in kand] == [False, False, True]


# ------------------------------------------------------------------ Papier-Start T+1 (2026-11-09)
def _papier_df():
    idx = pd.to_datetime(["2026-11-06", "2026-11-09", "2026-11-10"])
    return pd.DataFrame({"Open": [100.0, 110.0, 112.0], "High": [101.0, 112.0, 113.0], "Low": [99.0, 108.0, 110.0],
                         "Close": [100.0, 111.0, 112.0], "Volume": [1, 1, 1], "atr": [4.0, 4.0, 4.0]}, index=idx)


def _papier_veto(**kw):
    p = {"symbol": "X", "signal_datum": "2026-11-06", "signal_kurs": 100.0, "stop_initial": 94.0, "stop": 94.0}
    p.update(kw)
    return p


def test_papier_start_traegt_eroeffnung_t1_ein():
    cfg = {"chandelier_atr": 3.0, "max_ht": 60}
    q = ls.papier_update(_papier_veto(), _papier_df(), cfg)
    assert q["einstieg_datum"] == "2026-11-09"
    assert q["einstieg_kurs"] == 110.0
    assert q["handelstage"] == 1              # Einstiegstag = Tag 0
    assert "ausstieg_datum" not in q


def test_papier_start_r_auf_geplantes_risiko():
    cfg = {"chandelier_atr": 3.0, "max_ht": 60}
    d = _papier_df()
    d.loc["2026-11-10", "Low"] = 90.0         # Stop 94 gerissen (Chandelier von Tag 0: 111 - 12 = 99)
    q = ls.papier_update(_papier_veto(), d, cfg)
    assert q["ausstieg_kurs"] == 99.0
    assert q["r"] == round((99.0 - 110.0) / 6.0, 2)


def test_papier_start_eroeffnung_unter_stop_kein_trade():
    cfg = {"chandelier_atr": 3.0, "max_ht": 60}
    d = _papier_df()
    d.loc["2026-11-09", ["Open", "Low"]] = [93.0, 92.0]
    q = ls.papier_update(_papier_veto(), d, cfg)
    assert q["grund_ausstieg"] == "kein_trade_eroeffnung_unter_stop"
    assert q["r"] == 0.0


def test_papier_chat_format_wird_auf_t1_umgesetzt():
    cfg = {"chandelier_atr": 3.0, "max_ht": 60}
    p = {"symbol": "X", "einstieg_datum": "2026-11-06", "einstieg_kurs": 100.0, "stop_initial": 94.0, "stop": 94.0}
    q = ls.papier_update(p, _papier_df(), cfg)
    assert (q["signal_datum"], q["signal_kurs"]) == ("2026-11-06", 100.0)
    assert (q["einstieg_datum"], q["einstieg_kurs"]) == ("2026-11-09", 110.0)
    assert q["handelstage"] == 1


def test_papier_ohne_folgetag_bleibt_unveraendert():
    cfg = {"chandelier_atr": 3.0, "max_ht": 60}
    p = {"symbol": "X", "einstieg_datum": "2026-11-06", "einstieg_kurs": 100.0, "stop_initial": 94.0, "stop": 94.0}
    assert ls.papier_update(p, _papier_df().iloc[:1], cfg) == p


def test_papier_laufender_alteintrag_unveraendert():
    cfg = {"chandelier_atr": 3.0, "max_ht": 60}
    p = {"symbol": "X", "einstieg_datum": "2026-11-06", "einstieg_kurs": 100.0, "stop_initial": 94.0, "stop": 94.0,
         "geprueft_bis": "2026-11-06", "handelstage": 0}
    q = ls.papier_update(p, _papier_df(), cfg)
    assert q["einstieg_kurs"] == 100.0 and q["handelstage"] == 2 and "signal_datum" not in q
