"""Notbremse und Ueberdehnung fuer LS-2 (2026-11-07 abends).

1. Wie oft faellt die kumulierte R-Summe innerhalb von 20 aufeinanderfolgenden Trades auf -6 R oder
   tiefer, obwohl das System positiv ist? (Portfolio LS-2: Budget 3 R a 50 EUR, Kapital 12.000 EUR.)
   Gemessen ueber alle Startpunkte (gleitende 20er-Fenster) und ueber feste Bloecke (Trade 1-20, 21-40 ...).
2. Ueberdehnung: Ø R nach Abstand Schluss-EMA20 in ATR am Signaltag (Checklisten-Punkt 6).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from backtest_wochenende import ind, laden, tab, universum  # noqa: E402
from slots_risikobudget import portfolio, signale  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="config")
    ap.add_argument("--out", default="research/out")
    ap.add_argument("--cache", default="work/bt_cache.pkl")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    Path(a.cache).parent.mkdir(parents=True, exist_ok=True)
    eur = (".DE", ".PA", ".AS", ".MI", ".MC", ".BR", ".HE", ".VI")
    uni = [s for s in universum(Path(a.cfg)) if "." not in s or s.endswith(eur)]
    raw = laden(uni, Path(a.cache))
    dd = {s: ind(d) for s, d in raw.items() if s in uni}
    t = signale(dd)
    t = t[t.Datum >= "2009-01-01"].copy()
    t["ext20"] = [float(dd[s].ext20.get(d, np.nan)) for s, d in zip(t.Symbol, t.Datum)]

    g, *_ = portfolio(t, budget=3, r_eur=50, kapital=12000)
    r = g.sort_values("Datum").R.to_numpy()
    L = [f"# Notbremse und Ueberdehnung LS-2 ({pd.Timestamp.utcnow():%Y-%m-%d})\n",
         f"Portfolio Budget 3 R a 50 EUR, Kapital 12.000 EUR: {len(r)} Trades ab 2009, Ø R {r.mean():+.2f}, "
         f"Trefferquote {(r > 0).mean():.0%}. Absolute R mit rund +0,07 R Simulationsbias.\n"]
    rows = {}
    for schwelle in (-4, -6, -8, -10):
        fenster = [np.cumsum(r[i:i + 20]).min() <= schwelle for i in range(len(r) - 19)]
        bloecke = [np.cumsum(r[i:i + 20]).min() <= schwelle for i in range(0, len(r) - 19, 20)]
        ende = [r[i:i + 20].sum() <= schwelle for i in range(0, len(r) - 19, 20)]
        rows[f"{schwelle} R"] = {"gleitende 20er": np.mean(fenster), "feste Bloecke": np.mean(bloecke),
                                 "Summe nach 20 <= Schwelle": np.mean(ende)}
    L += ["## Notbremse: Anteil der 20er-Fenster, in denen die kumulierte Summe die Schwelle erreicht\n",
          tab(pd.DataFrame(rows).T, {c: "{:.0%}" for c in ("gleitende 20er", "feste Bloecke", "Summe nach 20 <= Schwelle")}), "\n"]
    s20 = pd.Series([r[i:i + 20].sum() for i in range(0, len(r) - 19, 20)])
    L += [f"Summe je 20er-Block: Median {s20.median():+.1f} R, 10-%-Quantil {s20.quantile(0.1):+.1f} R, "
          f"schlechtester {s20.min():+.1f} R, Anteil negativ {(s20 < 0).mean():.0%} (n = {len(s20)} Bloecke).\n"]

    b = pd.cut(t.ext20, [-np.inf, 0, 1, 2, 3, np.inf], labels=["< 0", "0-1", "1-2", "2-3", "> 3"])
    ex = t.groupby(b, observed=True).R.agg(["count", "mean"]).rename(columns={"count": "n", "mean": "Ø R"})
    L += ["## Ueberdehnung: Ø R nach Abstand Schluss-EMA20 in ATR (alle Signale LS-2)\n", tab(ex), "\n"]
    (out / "LERNSPUR_NOTBREMSE.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
