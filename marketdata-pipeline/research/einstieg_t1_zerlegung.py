"""Warum liegt das LS-2-Portfolio ueber dem Schnitt aller Signale? Reine Messung (User 2026-11-09).

Basis: Live-Einstieg Eroeffnung T+1 wie einstieg_t1.py. Portfolio 3 R a 50 EUR, 12.000 EUR, CHF-Deckel, 2.000 EUR je Position.
Zerlegung: Auswahl (niedrigste ATR% / Zufall 50 Seeds / hoechste ATR%), Stoertest (1 % der Signale entfernt, 50 Seeds),
Einsatzdeckel in EUR, Verteilung und Jahre der genommenen Trades, Bootstrap ueber Kalenderjahre.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from backtest_wochenende import ind, laden, tab, universum  # noqa: E402
from einstieg_t1 import START, signale, se  # noqa: E402
from filter_ls2 import _chf_deckel, EUR  # noqa: E402
from slots_risikobudget import rest_am  # noqa: E402


def pf(t, key="ATRp", budget=3.0, r_eur=50.0, kapital=12000.0, deckel=2000.0) -> pd.DataFrame:
    tage = np.sort(t.Datum.unique())
    nach_tag = {k: g.sort_values(key) for k, g in t.groupby("Datum")}
    offen, genommen = [], []
    for tg in tage:
        offen = [p for p in offen if p["Exit"] > tg]
        held = {p["Symbol"] for p in offen}
        belegt = sum(rest_am(p, tg) for p in offen)
        for _, c in nach_tag[tg].iterrows():
            if belegt + 1 > budget + 1e-9:
                break
            if c.Symbol in held:
                continue
            einsatz = min(deckel, r_eur / (1.5 * c.ATRp))
            if sum(q["einsatz"] for q in offen) + einsatz > kapital:
                continue
            p = c.to_dict()
            p["einsatz"] = einsatz
            offen.append(p); genommen.append(p); held.add(c.Symbol); belegt += 1
    return pd.DataFrame(genommen)


def kennz(r: pd.Series) -> dict:
    g, v = r[r > 0], r[r <= 0]
    return {"n": len(r), "Ø R": r.mean(), "SE": se(r), "Median": r.median(), "Treffer": (r > 0).mean(),
            "Ø Gewinn": g.mean(), "Ø Verlust": v.mean()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="config")
    ap.add_argument("--out", default="research/out")
    ap.add_argument("--cache", default="work/bt_cache.pkl")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    Path(a.cache).parent.mkdir(parents=True, exist_ok=True)
    uni = [s for s in universum(Path(a.cfg)) if "." not in s or s.endswith(EUR) or s.endswith(".SW")]
    raw = laden(uni, Path(a.cache))
    dd = {s: ind(d) for s, d in raw.items() if s in uni}
    t, _ = signale(dd)
    t = t[(t.Datum >= START) & t.R_B.notna()].reset_index(drop=True)
    t["R"] = t.R_B; t["Exit"] = t.Exit_B
    t["rest"] = [pd.Series({dd[s].index[k]: v for k, v in r.items() if k < len(dd[s].index)})
                 for s, r in zip(t.Symbol, t.rest_B)]
    ende = t.Datum.max()
    ab5 = ende - pd.DateOffset(years=5)
    jahre = (ende - pd.Timestamp(START)).days / 365.25
    t = _chf_deckel(t).reset_index(drop=True)

    # 1 Alle Signale nach ATR%
    t["q"] = pd.qcut(t.ATRp, 5, labels=["Q1 ruhigste", "Q2", "Q3", "Q4", "Q5 unruhigste"])
    rows = {}
    for q, g in t.groupby("q", observed=True):
        r = kennz(g.R); r["Ø ATR%"] = g.ATRp.mean(); r["Ø R 5J"] = g.R[g.Datum >= ab5].mean(); rows[q] = r
    rows["alle"] = {**kennz(t.R), "Ø ATR%": t.ATRp.mean(), "Ø R 5J": t.R[t.Datum >= ab5].mean()}
    T1 = pd.DataFrame(rows).T
    t["rang"] = t.groupby("Datum").ATRp.rank(method="first")
    t["n_tag"] = t.groupby("Datum").Symbol.transform("size")
    rows = {}
    for lab, m in (("Rang 1 (ruhigster des Tages)", t.rang == 1), ("Rang 2", t.rang == 2), ("Rang 3 und mehr", t.rang >= 3),
                   ("einziges Signal des Tages", t.n_tag == 1), ("Tage mit >= 3 Signalen", t.n_tag >= 3)):
        rows[lab] = kennz(t.R[m])
    T1b = pd.DataFrame(rows).T

    # 2 Zerlegung
    basis = pf(t)
    rng = np.random.default_rng(23)
    rnd, stoer = [], []
    for i in range(50):
        x = t.copy(); x["zk"] = rng.random(len(x))
        p = pf(x, key="zk")
        rnd.append((p.R.mean(), len(p) / jahre, p[p.Datum >= ab5].R.mean()))
    for i in range(50):
        x = t.sample(frac=0.99, random_state=int(rng.integers(1e9))).reset_index(drop=True)
        p = pf(x)
        stoer.append((p.R.mean(), len(p) / jahre, p[p.Datum >= ab5].R.mean()))
    x = t.copy(); x["zk"] = -x.ATRp
    hoch = pf(x, key="zk")
    rnd, stoer = np.array(rnd), np.array(stoer)
    def z(a):
        return {"Ø R (Mittel)": a[:, 0].mean(), "Streuung SD": a[:, 0].std(), "min": a[:, 0].min(), "max": a[:, 0].max(),
                "Trades/J": a[:, 1].mean(), "Ø R 5J": np.nanmean(a[:, 2])}
    T2 = pd.DataFrame({
        "Alle Signale, ungewichtet": {"Ø R (Mittel)": t.R.mean(), "Trades/J": len(t) / jahre, "Ø R 5J": t.R[t.Datum >= ab5].mean()},
        "Portfolio, niedrigste ATR% (Regel)": {"Ø R (Mittel)": basis.R.mean(), "Trades/J": len(basis) / jahre,
                                                "Ø R 5J": basis.R[basis.Datum >= ab5].mean()},
        "Portfolio, zufaellige Auswahl (50x)": z(rnd),
        "Portfolio, hoechste ATR%": {"Ø R (Mittel)": hoch.R.mean(), "Trades/J": len(hoch) / jahre,
                                      "Ø R 5J": hoch.R[hoch.Datum >= ab5].mean()},
        "Regel, 1 % Signale entfernt (50x)": z(stoer)}).T

    # 3 Genommene Trades
    r = basis.R
    k = kennz(r)
    k.update({"P10": r.quantile(.1), "P90": r.quantile(.9), "Anteil Summe R aus besten 5 %": r.nlargest(int(len(r) * .05)).sum() / r.sum(),
              "Ø ATR%": basis.ATRp.mean(), "Ø Haltetage (Kalender)": (basis.Exit - basis.Datum).dt.days.mean()})
    T3 = pd.DataFrame({"Regel-Portfolio": k}).T
    j = basis.groupby(basis.Datum.dt.year).R.agg(["size", "mean", "sum"])
    j.columns = ["n", "Ø R", "Summe R"]; j["Ø R"] = j["Ø R"].round(2)
    # Bootstrap Kalenderjahre
    bs_r = np.random.default_rng(5)
    jr = {y: g.R.to_numpy() for y, g in basis.groupby(basis.Datum.dt.year)}
    ys = list(jr)
    bs = [np.concatenate([jr[y] for y in bs_r.choice(ys, len(ys))]).mean() for _ in range(5000)]
    q = np.percentile(bs, [2.5, 97.5])

    # 4 Euro
    basis["r_eff"] = basis.einsatz * 1.5 * basis.ATRp
    basis["eur"] = basis.R * basis.r_eff
    T4 = pd.DataFrame({"Regel-Portfolio": {
        "Ø Einsatz EUR": basis.einsatz.mean(), "Anteil gedeckelt 2.000 EUR": (basis.einsatz >= 2000).mean(),
        "Ø effektives R EUR": basis.r_eff.mean(), "Ø EUR je Trade": basis.eur.mean(), "EUR/J nominal (R x 50)": r.sum() / jahre * 50,
        "EUR/J mit Deckel": basis.eur.sum() / jahre, "Anteil Einsatz < 1.000 EUR": (basis.einsatz < 1000).mean(),
        "Anteil Einsatz < 500 EUR": (basis.einsatz < 500).mean()}}).T

    fm = {"n": "{:.0f}", "Trades/J": "{:.1f}", "Treffer": "{:.1%}", "Ø ATR%": "{:.2%}", "Anteil Summe R aus besten 5 %": "{:.0%}",
          "Ø Haltetage (Kalender)": "{:.0f}", "Anteil gedeckelt 2.000 EUR": "{:.0%}", "Anteil Einsatz < 1.000 EUR": "{:.0%}",
          "Anteil Einsatz < 500 EUR": "{:.0%}", "Ø Einsatz EUR": "{:,.0f}", "EUR/J nominal (R x 50)": "{:,.0f}", "EUR/J mit Deckel": "{:,.0f}"}
    L = [f"# LS-2: Zerlegung Portfolio gegen alle Signale ({pd.Timestamp.now('UTC'):%Y-%m-%d})\n",
         f"Live-Einstieg Eroeffnung T+1, n = {len(t)} Signale nach CHF-Deckel, ohne Kosten, Survivorship- und Simulationsbias.\n",
         "## 1 Alle Signale\n", tab(T1, fm), "\n", tab(T1b, fm), "\n## 2 Zerlegung\n", tab(T2, fm),
         "\n## 3 Genommene Trades\n", tab(T3, fm), f"\n\nBootstrap ueber Kalenderjahre, 95 %: {q[0]:.2f} bis {q[1]:.2f} R\n",
         "\n" + tab(j.reset_index().rename(columns={"Datum": "Jahr"}).set_index("Jahr"), {"n": "{:.0f}", "Summe R": "{:.1f}"}),
         "\n## 4 Euro\n", tab(T4, fm), "\n"]
    (out / "LS2_ZERLEGUNG.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
