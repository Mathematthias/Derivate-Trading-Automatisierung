"""Tests fuer den Regressionskanal 20/50 HT (2026-10-28, reine Messung, Anlass CAP.PA)."""
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import market_data as md  # noqa: E402


def _closes(vals):
    return pd.Series(vals, dtype=float)


def test_linearer_trend_mit_wechselndem_rauschen():
    # Gerade 100 + 1/HT, Rauschen +/-0,5 abwechselnd
    n = 20
    vals = [100 + i + (0.5 if i % 2 else -0.5) for i in range(n)]
    k = md._compute_reg_channel(_closes(vals), 20, atr=4.0)
    assert k is not None
    assert abs(k["steig_atr"] - 0.25) < 0.02          # 1 je HT bei ATR 4
    assert k["ug"] < k["mitte"] < k["og"]
    assert abs((k["og"] - k["mitte"]) - (k["mitte"] - k["ug"])) < 1e-3
    assert k["r2"] > 0.98


def test_pos_an_der_unterkante_negativ():
    n = 50
    rng = np.random.default_rng(7)
    vals = list(100 + 0.5 * np.arange(n) + rng.normal(0, 1, n))
    vals[-1] = vals[-2] - 4.0                          # letzter Schluss faellt deutlich
    k = md._compute_reg_channel(_closes(vals), 50, atr=2.0)
    assert k["pos"] < -1.5


def test_zu_wenig_daten_und_flatline():
    assert md._compute_reg_channel(_closes([10.0] * 10), 20) is None
    assert md._compute_reg_channel(_closes([10.0] * 20), 20) is None   # sigma 0
    assert md._compute_reg_channel(_closes([10.0] * 19 + [float("nan")]), 20) is None


def test_ohne_atr_keine_steigung_in_atr():
    vals = [50 + 0.3 * i + (0.2 if i % 3 else -0.1) for i in range(20)]
    k = md._compute_reg_channel(_closes(vals), 20, atr=None)
    assert k is not None and k["steig_atr"] is None


def test_digest_traegt_rc():
    import digest_renderer as dr
    src = open(dr.__file__, encoding="utf-8").read()
    assert '"rc": getattr(snap, "reg_channel", None)' in src
    assert md.REG_CHANNEL_WINDOWS == (20, 50)
