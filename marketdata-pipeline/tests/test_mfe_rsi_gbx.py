"""2026-10-27 (User „A mit Reparatur"): RSI_1D_Vortag als Ex-ante-Messung, GBp->GBP fuer .L-Werte."""
from datetime import date
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import mfe_mae as mm  # noqa: E402


def _df(closes, start="2026-07-01"):
    idx = pd.bdate_range(start, periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c})


def test_rsi14_steigend_hoch_fallend_tief():
    up = mm._rsi14(pd.Series(range(1, 60), dtype=float))
    dn = mm._rsi14(pd.Series(range(60, 1, -1), dtype=float))
    assert up.iloc[-1] > 90 and dn.iloc[-1] < 10


def test_entry_context_liefert_rsi_vortag():
    closes = [100 + i * 0.5 for i in range(60)]
    df = _df(closes)
    start = df.index[50].date()
    ctx = mm.entry_context(df, "Long", closes[50], start, df.index[-1].date())
    assert ctx["RSI_1D_Vortag"] is not None and ctx["RSI_1D_Vortag"] > 70


def test_einheit_gbp_pence():
    df = _df([117.0, 118.0, 119.5, 120.0])
    out, hinweis = mm.einheit_angleichen(df, "VOD.L", 1.1976)
    assert hinweis == "GBp->GBP" and abs(out["Close"].iloc[-1] - 1.20) < 1e-9
    same, h2 = mm.einheit_angleichen(df, "VOD.L", 117.5)          # Entry schon in Pence
    assert h2 == "" and same["Close"].iloc[-1] == 120.0
    other, h3 = mm.einheit_angleichen(df, "MSFT", 1.1976)          # nur .L
    assert h3 == ""


def test_run_csv_vod_plausibel(tmp_path):
    inp = tmp_path / "audit.csv"
    inp.write_text("TradeID,Symbol,Richtung,Kauf,Verkauf,EntryU,SL_U,R,Einstiegsart\n"
                   "A-016,VOD.L,Long,2026-08-20,,1.1976,1.1516,,unklar\n", encoding="utf-8")
    closes = [115.0 + (i % 5) for i in range(60)]
    fake = lambda sym, s, e: _df(closes)
    table, _ = mm.run_csv(inp, None, fetch=fake, today=date(2026, 9, 22))
    t = table[0]
    assert "GBp->GBP" in t["Status"]
    assert abs(t["MFE_R"]) < 10 and abs(t["MAE_R"]) < 10
