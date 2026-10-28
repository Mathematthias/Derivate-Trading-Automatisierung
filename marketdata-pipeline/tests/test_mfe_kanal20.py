"""2026-10-28 (User "B + C"): 20-HT-Regressionskanal als Ex-ante-Messung im MFE/MAE-Job."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import mfe_mae as mm  # noqa: E402


def _df(closes, start="2026-07-01"):
    idx = pd.bdate_range(start, periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c})


def _trend(n=60):
    return [100 + i + (0.6 if i % 2 else -0.6) for i in range(n)]


def test_long_an_der_unterkante_negativ_steigung_positiv():
    closes = _trend()
    df = _df(closes)
    i = 50
    # Fill deutlich unter der fortgeschriebenen Mitte (~150) -> negative sigma
    ctx = mm.entry_context(df, "Long", 148.0, df.index[i].date(), df.index[-1].date())
    assert ctx["Kanal20_Pos"] is not None and ctx["Kanal20_Pos"] < -1.0
    assert ctx["Kanal20_Steig_ATR"] > 0
    assert ctx["Kanal20_R2"] > 0.95


def test_short_spiegelt_vorzeichen():
    closes = _trend()
    df = _df(closes)
    i = 50
    lo = mm.entry_context(df, "Long", 152.0, df.index[i].date(), df.index[-1].date())
    sh = mm.entry_context(df, "Short", 152.0, df.index[i].date(), df.index[-1].date())
    assert lo["Kanal20_Pos"] == -sh["Kanal20_Pos"]
    assert sh["Kanal20_Steig_ATR"] < 0              # Aufwaertstrend gegen den Short


def test_zu_wenig_vorlauf_none():
    closes = _trend(30)
    df = _df(closes)
    ctx = mm.entry_context(df, "Long", closes[10], df.index[10].date(), df.index[-1].date())
    assert ctx["Kanal20_Pos"] is None and ctx["Kanal20_R2"] is None


def test_spalten_in_ctx_und_csv():
    for c in ("Kanal20_Pos", "Kanal20_Steig_ATR", "Kanal20_R2"):
        assert c in mm.CTX_COLS and c in mm.CSV_OUT_COLS
