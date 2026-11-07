"""Kern-Rotation (Neuaufstellung A+, 2026-11-07)."""
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src import rotation_kern as rk


def _closes(n=300, drifts=None):
    idx = pd.bdate_range("2025-01-01", periods=n)
    drifts = drifts or {"A": 0.002, "B": 0.001, "C": -0.001, "D": 0.0005, "E": -0.002}
    return pd.DataFrame({s: 100 * np.exp(np.cumsum(np.full(n, d))) for s, d in drifts.items()}, index=idx)


def test_scores_und_auswahl_mit_absolutfilter():
    sc = rk.scores(_closes(), [63, 126, 252])
    assert list(sc.sort_values(ascending=False).index[:2]) == ["A", "B"]
    assert rk.auswahl(sc, 4, True) == ["A", "B", "D"]          # C, E negativ -> Cash
    assert rk.auswahl(sc, 4, False) == ["A", "B", "D", "C"]


def test_zu_kurze_historie_ist_nan():
    sc = rk.scores(_closes(n=100), [63, 126, 252])
    assert sc.isna().all()


def test_monatsletzter():
    assert rk.ist_monatsletzter(date(2026, 11, 30))            # Montag, letzter Wochentag
    assert not rk.ist_monatsletzter(date(2026, 11, 27))
    assert rk.ist_monatsletzter(date(2026, 10, 30))            # Freitag, 31. ist Samstag


def test_plan_kauf_verkauf_cash():
    akt = rk.plan(["A", "C"], ["A", "B", "D"], 8000, 4, {"B": {"isin": "X"}})
    by = {(a["aktion"], a["signal"]) for a in akt}
    assert ("verkaufen", "C") in by and ("halten", "A") in by and ("kaufen", "B") in by
    cash = [a for a in akt if a["aktion"] == "cash"][0]
    assert cash["ziel_eur"] == 2000.0
    assert [a for a in akt if a["signal"] == "B"][0]["isin"] == "X"


def test_backtest_waehlt_den_starken_wert():
    r = rk.backtest(_closes(n=600), 1, True, [63, 126, 252], 0.0, start="2025-01-01")
    assert r.sum() > 0


def test_config_ethik_und_isins():
    cfg = yaml.safe_load((Path(__file__).parent.parent / "config" / "rotation_kern.yaml").read_text())
    sig = [u["signal"] for u in cfg["universum"]]
    assert not {"XLI", "EWG"} & set(sig)
    assert len(sig) == len(set(sig)) and all(len(u["isin"]) == 12 for u in cfg["universum"])


def test_thesen_preise_marken():
    from src import thesen_preise as tp
    idx = pd.bdate_range("2025-01-01", periods=300)
    c = pd.Series(np.r_[np.linspace(100, 200, 250), np.linspace(200, 158, 50)], index=idx)
    th = {"thesen": [{"id": "TDIP", "spur": "thesen", "verdikt": "spielen",
                      "karte": {"preis_falsifikat": {"symbol": "XLK", "op": "<", "level": 130},
                                "einstieg": {"symbol": "XLK", "op": "<", "level": 160}}},
                     {"id": "ALT", "spur": "thesen", "verdikt": "verworfen", "karte": {}}]}
    r = tp.pruefe(th, lambda s: c)
    x = r["TDIP"]["XLK"]
    assert x["einstieg"]["erreicht"] and not x["preis_falsifikat"]["erreicht"]
    assert x["hoch_52w"] == 200.0 and x["abstand_hoch_pct"] == -21.0
    assert "ALT" not in r
