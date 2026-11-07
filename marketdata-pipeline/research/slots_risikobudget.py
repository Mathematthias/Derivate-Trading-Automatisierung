"""Lern-Spur: Plaetze gegen Risikobudget (User-Frage 2026-11-07 21:00).

Varianten (alle mit Filter EMA50 > EMA200, Auswahl niedrigste ATR%):
  Plaetze      n Positionen mit Stop unter Einstieg, Gesamtzahl unbegrenzt
  Budget       Summe des offenen Risikos bis zum AKTUELLEN Stop <= B R. Eine Position, deren
               Chandelier-Stop von -1 R auf -0,4 R gestiegen ist, belegt nur noch 0,4 R.
Gemessen: Trades/Jahr, Wochen fuer 20 Trades, Ø R, R/Jahr, max. gleichzeitige Positionen,
max. Drawdown in R (kumuliert nach Ausstiegsdatum), groesstes Risiko an einem Tag.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from backtest_wochenende import _a, ind, laden, tab, universum  # noqa: E402


def pfad(d, i, mult=3.0, max_ht=60):
    """R, Exit-Index, offenes Restrisiko in R je Tag (Index -> R), gueltig ab dem Folgetag."""
    O, H, Lo, C, A = _a(d)
    e = C[i]
    stop = e - 1.5 * A[i]
    risk = e - stop
    hoch = e
    rest = {i + 1: 1.0}
    n = len(C)
    for k in range(1, max_ht + 1):
        j = i + k
        if j >= n:
            return (C[-1] - e) / risk, n - 1, rest
        if Lo[j] <= stop:
            return (min(O[j], stop) - e) / risk, j, rest
        hoch = max(hoch, C[j])
        stop = max(stop, hoch - mult * A[j])
        rest[j + 1] = max(0.0, (e - stop) / risk)
    return (C[i + max_ht] - e) / risk, i + max_ht, rest


def signale(dd):
    rows = []
    for s, d in dd.items():
        ueber = d.ema20 > d.ema50
        m = (ueber & ~ueber.shift(fill_value=True) & (d.Close > d.ema200) & (d.ema50 > d.ema200)
             & (d.atrp <= 0.06) & (d.atrp >= 0.005))
        idx = d.index
        for j in np.flatnonzero(m.values):
            if j < 260 or j >= len(d) - 2:
                continue
            r, x, rest = pfad(d, j)
            # Restrisiko je Kalenderdatum, vorwaerts gefuellt
            rr = pd.Series({idx[k]: v for k, v in rest.items() if k < len(idx)})
            rows.append({"Symbol": s, "Datum": idx[j], "ATRp": d.atrp.iloc[j], "R": r,
                         "Exit": idx[min(x, len(idx) - 1)], "rest": rr})
    return pd.DataFrame(rows)


def rest_am(p, tg):
    s = p["rest"]
    s = s[s.index <= tg]
    return float(s.iloc[-1]) if len(s) else 1.0


def portfolio(t, plaetze=None, budget=None, r_eur=75.0, kapital=None, deckel=2000.0):
    tage = np.sort(t.Datum.unique())
    nach_tag = {k: g.sort_values("ATRp") for k, g in t.groupby("Datum")}
    offen, genommen, bel, risk_max, kap_max = [], [], [], 0.0, 0.0
    for tg in tage:
        offen = [p for p in offen if p["Exit"] > tg]
        held = {p["Symbol"] for p in offen}
        if plaetze is not None:
            belegt = sum(1 for p in offen if rest_am(p, tg) > 0)
        else:
            belegt = sum(rest_am(p, tg) for p in offen)
        for _, c in nach_tag.get(tg, pd.DataFrame()).iterrows():
            grenze = plaetze if plaetze is not None else budget
            if belegt + 1 > grenze + 1e-9:
                break
            if c.Symbol in held:
                continue
            einsatz = min(deckel, r_eur / (1.5 * c.ATRp))
            if kapital is not None and sum(q["einsatz"] for q in offen) + einsatz > kapital:
                continue
            p = c.to_dict()
            p["einsatz"] = einsatz
            offen.append(p); genommen.append(p); held.add(c.Symbol); belegt += 1
        bel.append(len(offen))
        kap_max = max(kap_max, sum(q["einsatz"] for q in offen))
        risk_max = max(risk_max, sum(rest_am(p, tg) for p in offen))
    g = pd.DataFrame(genommen)
    kum = g.sort_values("Exit").R.cumsum()
    dd = float((kum - kum.cummax()).min())
    g.attrs["kap_max"] = kap_max
    g.attrs["kap_mittel"] = float(np.mean([0]))
    return g, max(bel), float(np.mean(bel)), dd, risk_max


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
    t = t[t.Datum >= "2009-01-01"]
    ende = t.Datum.max()
    jahre = (ende - pd.Timestamp("2009-01-01")).days / 365.25
    rows = {}
    varianten = [("Budget 2 R a 75, ohne Kapitalgrenze", {"budget": 2, "r_eur": 75})]
    for b_r, r_eur in ((3, 50), (4, 75)):
        for kap in (None, 8000, 10000, 12000, 15000):
            varianten.append((f"Budget {b_r} R a {r_eur}, Kapital {'offen' if kap is None else f'{kap:,}'.replace(',', '.')}",
                              {"budget": b_r, "r_eur": r_eur, "kapital": kap}))
    varianten.append(("4 Risiko-Plaetze a 75, ohne Kapitalgrenze", {"plaetze": 4, "r_eur": 75}))
    for name, kw in varianten:
        g, bmax, bmit, ddr, rmax = portfolio(t, **kw)
        g5 = g[g.Datum >= ende - pd.DateOffset(years=5)]
        reur = kw["r_eur"]
        rows[name] = {"Wochen fuer 20": 20 / (len(g) / jahre) * 52, "Ø R": g.R.mean(), "Ø R 5J": g5.R.mean(),
                      "EUR/Jahr": g.R.sum() / jahre * reur, "max DD EUR": ddr * reur, "max DD R": ddr,
                      "Pos Ø": bmit, "Pos max": bmax, "Kapital max": g.attrs["kap_max"]}
    df = pd.DataFrame(rows).T
    L = [f"# Lern-Spur: Plaetze gegen Risikobudget ({pd.Timestamp.utcnow():%Y-%m-%d})\n",
         f"Signale mit Filter EMA50 > EMA200: {len(t)}, ab 2009, {len(dd)} Direktaktien EUR/USD. "
         "Absolute R mit rund +0,07 R Simulationsbias; Drawdown kumuliert nach Ausstiegsdatum.\n",
         tab(df, {"Trades/Jahr": "{:.1f}", "Trades/Jahr 5J": "{:.1f}", "Wochen fuer 20": "{:.0f}",
                  "EUR/Jahr": "{:,.0f}", "max DD EUR": "{:,.0f}", "max DD R": "{:.1f}", "Pos max": "{:.0f}",
                  "Pos Ø": "{:.1f}", "Kapital max": "{:,.0f}"}), "\n"]
    (out / "LERNSPUR_BUDGET.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
