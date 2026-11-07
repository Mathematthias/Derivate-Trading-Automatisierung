"""LS-2 nach Waehrungsraum (User-Frage 2026-11-07 23:35: Ist EUR/USD-only sinnvoll?).

Alle Signale LS-2 (EMA20 x EMA50, Schluss > EMA200, EMA50 > EMA200, ATR% 0,5-6) im ganzen Universum,
Ausstieg Chandelier 3 ATR / 60 HT. Gruppiert nach Boersen-Suffix. Dazu Portfolio LS-2 (Budget 3 R a 50 EUR,
Kapital 12.000 EUR) einmal nur EUR/USD und einmal alle Waehrungen.
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
from backtest_wochenende import ind, laden, tab, universum  # noqa: E402
from slots_risikobudget import portfolio, signale  # noqa: E402

RAUM = {"": "USD", ".DE": "EUR", ".PA": "EUR", ".AS": "EUR", ".MI": "EUR", ".MC": "EUR", ".BR": "EUR",
        ".HE": "EUR", ".VI": "EUR", ".SW": "CHF", ".L": "GBP", ".ST": "SEK", ".CO": "DKK", ".OL": "NOK"}

def raum(s):
    suf = "." + s.split(".")[-1] if "." in s else ""
    return RAUM.get(suf, "andere " + suf)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cfg", default="config"); ap.add_argument("--out", default="research/out")
    ap.add_argument("--cache", default="work/bt_cache.pkl"); a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True); Path(a.cache).parent.mkdir(parents=True, exist_ok=True)
    uni = universum(Path(a.cfg))
    raw = laden(uni, Path(a.cache))
    dd = {s: ind(d) for s, d in raw.items() if s in uni}
    t = signale(dd); t = t[t.Datum >= "2009-01-01"].copy()
    t["Raum"] = t.Symbol.map(raum)
    ende = t.Datum.max()
    g = t.groupby("Raum").agg(Symbole=("Symbol", "nunique"), n=("R", "size"), Treffer=("R", lambda r: (r > 0).mean()),
                              ØR=("R", "mean"), ATRp=("ATRp", "median"))
    g5 = t[t.Datum >= ende - pd.DateOffset(years=5)].groupby("Raum").R.agg(["size", "mean"]).rename(columns={"size": "n 5J", "mean": "Ø R 5J"})
    g = g.join(g5)
    L = [f"# LS-2 nach Waehrungsraum ({pd.Timestamp.utcnow():%Y-%m-%d})\n",
         f"Alle Signale ab 2009: n = {len(t)}, {t.Symbol.nunique()} Symbole. Absolute R mit ~+0,07 R Simulationsbias, Survivorship-Bias.\n",
         tab(g.sort_values("n", ascending=False), {"Symbole": "{:.0f}", "n": "{:.0f}", "Treffer": "{:.0%}", "ATRp": "{:.2%}", "n 5J": "{:.0f}"}), "\n"]
    rows = {}
    for name, sub in (("nur EUR/USD", t[t.Raum.isin(["EUR", "USD"])]), ("alle Waehrungen", t)):
        p, bmax, bmit, ddr, _ = portfolio(sub, budget=3, r_eur=50, kapital=12000)
        p5 = p[p.Datum >= ende - pd.DateOffset(years=5)]
        anteil = p.Symbol.map(raum).value_counts(normalize=True)
        rows[name] = {"Trades/Jahr": len(p) / ((ende - pd.Timestamp('2009-01-01')).days / 365.25), "Ø R": p.R.mean(),
                      "Ø R 5J": p5.R.mean(), "max DD R": ddr, "Anteil CHF/GBP/Nordics": 1 - anteil.get("EUR", 0) - anteil.get("USD", 0)}
    L += ["## Portfolio LS-2 (Budget 3 R a 50 EUR, Kapital 12.000 EUR)\n",
          tab(pd.DataFrame(rows).T, {"Trades/Jahr": "{:.1f}", "max DD R": "{:.1f}", "Anteil CHF/GBP/Nordics": "{:.0%}"}), "\n"]
    (out / "LERNSPUR_REGIONEN.md").write_text("\n".join(L), encoding="utf-8"); print("\n".join(L))

if __name__ == "__main__":
    main()
