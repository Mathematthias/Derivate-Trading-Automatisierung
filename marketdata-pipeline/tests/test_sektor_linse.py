"""Tests Sektor-Linse (2026-10-19) und EMA200-Fix der relativen TIW."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sektor_linse import CLUSTER, sektor_linse  # noqa: E402
from state_yaml import _leg_tiw  # noqa: E402


def _snap(kurs, atr=1.0, e20=None, e50=None, e100=None, e200=None, stack="bullish", **kw):
    d = {"kurs": kurs, "atr": atr, "ema20": e20, "ema50": e50, "ema100": e100,
         "ema200": e200, "stack": stack}
    d.update(kw)
    return d


def _uni(index_stack="bullish", index_ueber=True):
    u = {"^IXIC": _snap(110 if index_ueber else 90, e20=105, e50=104, e100=102, e200=100,
                        stack=index_stack, dist52wH=-5.7)}
    # Halbleiter: 4 Werte, 3 davon > 2 ATR unter der EMA20, einer an der EMA100
    for s, k in (("NVDA", 97.0), ("MU", 96.0), ("AVGO", 95.0)):
        u[s] = _snap(k, e20=100, e50=99, e100=97.2, e200=90, dist52wH=-20, move30d=-8, chg=-4)
    u["QCOM"] = _snap(99.5, e20=100, e50=99, e100=98, e200=95, dist52wH=-10, move30d=-2, chg=-1)
    return u


def test_signal_bei_tiefem_cluster_und_intaktem_index():
    out = sektor_linse(_uni())
    h = out["cluster"]["halbleiter"]
    assert out["modus"] == "messung"
    assert out["index_intakt"] is True
    assert h["n"] == 4 and h["n_tief"] == 3 and h["anteil_tief"] == 0.75
    assert h["signal"] is True
    assert "NVDA@EMA100" in h["tiefe_anker"]


def test_kein_signal_wenn_index_unter_ema200():
    out = sektor_linse(_uni(index_ueber=False))
    assert out["index_intakt"] is False
    assert out["cluster"]["halbleiter"]["signal"] is False


def test_kein_signal_unter_min_n():
    u = _uni()
    del u["QCOM"], u["AVGO"]
    h = sektor_linse(u)["cluster"]["halbleiter"]
    assert h["n"] == 2 and h["signal"] is False


def test_leere_cluster_und_fehlende_daten():
    u = {"^IXIC": _snap(110, e20=105, e50=104, e100=102, e200=100),
         "NVDA": {"kurs": 100, "atr": None}}
    out = sektor_linse(u)
    assert all(c["n"] == 0 and c["signal"] is False for c in out["cluster"].values())
    assert set(out["cluster"]) == set(CLUSTER)


def test_tiw_relativ_ema200_wird_nicht_als_ema20_gelesen():
    t = _leg_tiw("Touch EMA200-1D … TIW = 1D-Schluss unter EMA200-1D -0,30 ATR. TP1 218,68$")
    assert t["anker"] == "EMA200" and t["off"] == -0.3
    t = _leg_tiw("TIW = 1D-Schluss unter EMA20-1D -0,30 ATR.")
    assert t["anker"] == "EMA20" and t["off"] == -0.3
    t = _leg_tiw("TIW = 1D-Schluss unter EMA100-1D -0,30 ATR.")
    assert t["anker"] == "EMA100"
