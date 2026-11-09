"""LS-2: Einstieg am Signalschluss (Backtest) gegen Eroeffnung T+1 (live). Reine Messung (User 2026-11-09).

Protokoll (vor dem Lauf festgelegt, 2026-11-09):
  * Signale wie filter_ls2.py: EMA20 x EMA50, Schluss > EMA200, EMA50 > EMA200, ATR% 0,5-6, EUR/USD/CHF, ab 2009.
  * A  Backtest: Einstieg Schluss T, Stop Schluss T - 1,5 ATR(T), R = 1,5 ATR(T).
  * B  Live: Einstieg Eroeffnung T+1, Stop bleibt Schluss T - 1,5 ATR(T), Stueckzahl vom Signal, also
       R_plan = (Ausstieg - Einstieg) / 1,5 ATR(T). Chandelier wie stop_nachziehen (hoechster Schluss seit
       Einstieg, mindestens Einstieg, minus 3 ATR, wirksam ab Folgetag). Stop gilt ab T+1 intraday.
       Zeitausstieg am Schluss T+61 (handelstage >= 60).
  * Eroeffnung <= Stop: kein Trade (gezaehlt). Fehlende oder ausserhalb High/Low liegende Eroeffnung: Signal raus.
  * C1/C2: B, aber kein Trade bei Gap nach oben > 1,0 / > 0,5 ATR(T).
  * Zufall: je Symbol 3 % der zulaessigen Tage (Seed 17), ATR% 0,5-6, einmal alle Tage, einmal nur Trendtage
    (Schluss > EMA200 und EMA50 > EMA200); gleiche Simulation A und B.
  * Portfolio wie filter_ls2.py: Budget 3 R a 50 EUR, Kapital 12.000 EUR, CHF-Deckel 1.
  Standardfehler unterstellen unabhaengige Trades, Signale ballen sich aber: eher zu klein.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from backtest_wochenende import _a, ind, laden, tab, universum  # noqa: E402
from filter_ls2 import _chf_deckel, waehrung, EUR  # noqa: E402
from slots_risikobudget import pfad, portfolio  # noqa: E402

START = "2009-01-01"


def oeffnung_ok(d, j) -> bool:
    O, H, Lo, _, _ = _a(d)
    o = O[j]
    return bool(np.isfinite(o) and o > 0 and Lo[j] * 0.999 <= o <= H[j] * 1.001)


def pfad_t1(d, i, mult=3.0, max_ht=60):
    """Live: R_plan, Exit-Index, Restrisiko je Tag in Plan-R. None, wenn die Eroeffnung schon unter dem Stop liegt."""
    O, H, Lo, C, A = _a(d)
    j0 = i + 1
    e, stop = O[j0], C[i] - 1.5 * A[i]
    plan = C[i] - stop
    if e <= stop:
        return None
    hoch = e
    rest = {j0: (e - stop) / plan}
    n = len(C)
    for k in range(0, max_ht + 1):
        j = j0 + k
        if j >= n:
            return (C[-1] - e) / plan, n - 1, rest
        if Lo[j] <= stop:
            return (min(O[j], stop) - e) / plan, j, rest
        hoch = max(hoch, C[j])
        stop = max(stop, hoch - mult * A[j])
        rest[j + 1] = max(0.0, (e - stop) / plan)
    return (C[j0 + max_ht] - e) / plan, j0 + max_ht, rest


def fall(s, d, j, idx) -> dict | None:
    """Ein Signal oder Zufallstag in beiden Einstiegsvarianten."""
    if not oeffnung_ok(d, j + 1):
        return None
    _, _, _, C, A = _a(d)
    O = _a(d)[0]
    r_a, x_a, rest_a = pfad(d, j)
    plan = 1.5 * A[j]
    gap = (O[j + 1] - C[j]) / A[j]
    b = pfad_t1(d, j)
    rec = {"Symbol": s, "Datum": idx[j], "Waehrung": waehrung(s), "ATRp": d.atrp.iloc[j], "gap_atr": gap,
           "ist_risiko": (O[j + 1] - (C[j] - plan)) / plan, "R_A": r_a,
           "Exit_A": idx[min(x_a, len(idx) - 1)], "rest_A": rest_a, "R_B": np.nan, "Exit_B": pd.NaT, "rest_B": None}
    if b is not None:
        rec.update(R_B=b[0], Exit_B=idx[min(b[1], len(idx) - 1)], rest_B=b[2])
    return rec


def signale(dd) -> tuple[pd.DataFrame, int]:
    rows, raus = [], 0
    for s, d in dd.items():
        ueber = d.ema20 > d.ema50
        m = (ueber & ~ueber.shift(fill_value=True) & (d.Close > d.ema200) & (d.ema50 > d.ema200)
             & (d.atrp <= 0.06) & (d.atrp >= 0.005))
        for j in np.flatnonzero(m.values):
            if j < 260 or j >= len(d) - 2:
                continue
            r = fall(s, d, j, d.index)
            if r is None:
                raus += 1
            else:
                rows.append(r)
    return pd.DataFrame(rows), raus


def zufall(dd, trend: bool, anteil=0.03, seed=17) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for s, d in dd.items():
        m = (d.atrp <= 0.06) & (d.atrp >= 0.005)
        if trend:
            m &= (d.Close > d.ema200) & (d.ema50 > d.ema200)
        k = np.flatnonzero(m.values)
        k = k[(k >= 260) & (k < len(d) - 2)]
        if len(k) == 0:
            continue
        for j in rng.choice(k, size=max(1, int(len(k) * anteil)), replace=False):
            r = fall(s, d, int(j), d.index)
            if r is not None:
                rows.append(r)
    return pd.DataFrame(rows)


def fenster(t) -> dict:
    ende = t.Datum.max()
    return {"gesamt": pd.Series(True, index=t.index), "09-17": t.Datum < "2018-01-01", "18-26": t.Datum >= "2018-01-01",
            "5J": t.Datum >= ende - pd.DateOffset(years=5), "2J": t.Datum >= ende - pd.DateOffset(years=2)}


def se(x) -> float:
    x = pd.Series(x).dropna()
    return float(x.std() / np.sqrt(len(x))) if len(x) > 1 else np.nan


def ein_varianten(t) -> dict:
    """Maske der ausgefuehrten Trades und R-Spalte je Variante."""
    b = t.R_B.notna()
    return {"A Schluss T (Backtest)": ("R_A", pd.Series(True, index=t.index)),
            "B Eroeffnung T+1 (live)": ("R_B", b),
            "C1 B, kein Gap > +1,0 ATR": ("R_B", b & (t.gap_atr <= 1.0)),
            "C2 B, kein Gap > +0,5 ATR": ("R_B", b & (t.gap_atr <= 0.5))}


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
    t, raus = signale(dd)
    t = t[t.Datum >= START].reset_index(drop=True)
    z_alle = zufall(dd, False); z_alle = z_alle[z_alle.Datum >= START].reset_index(drop=True)
    z_tr = zufall(dd, True); z_tr = z_tr[z_tr.Datum >= START].reset_index(drop=True)
    F = fenster(t)
    ende = t.Datum.max()
    jahre = (ende - pd.Timestamp(START)).days / 365.25

    # 1 Varianten
    rows = {}
    for name, (col, m) in ein_varianten(t).items():
        r = {"n": int(m.sum()), "Ø R": t.loc[m, col].mean(), "SE": se(t.loc[m, col])}
        for fn, f in F.items():
            if fn != "gesamt":
                r[f"Ø R {fn}"] = t.loc[m & f, col].mean()
        d = t.loc[m, col] - t.loc[m, "R_A"]
        r["Δ zu A"] = d.mean(); r["SE Δ"] = se(d)
        r["Δ 5J"] = (t.loc[m & F["5J"], col] - t.loc[m & F["5J"], "R_A"]).mean()
        rows[name] = r
    T1 = pd.DataFrame(rows).T

    # 2 Zufall und Vorsprung
    rows = {}
    for lab, z in (("Zufall alle Tage", z_alle), ("Zufall Trendtage", z_tr)):
        Fz = fenster(z)
        for v, col in (("A", "R_A"), ("B", "R_B")):
            r = {"n": int(z[col].notna().sum())}
            r.update({f"Ø R {fn}": z.loc[f, col].mean() for fn, f in Fz.items()})
            rows[f"{lab}, {v}"] = r
    T2 = pd.DataFrame(rows).T
    rows = {}
    for lab, z in (("gegen Zufall alle Tage", z_alle), ("gegen Zufall Trendtage", z_tr)):
        Fz = fenster(z)
        for v, col in (("A", "R_A"), ("B", "R_B")):
            rows[f"LS-2 {v} {lab}"] = {f"Vorsprung {fn}": t.loc[f, col].mean() - z.loc[Fz[fn], col].mean()
                                       for fn, f in F.items()}
    T2b = pd.DataFrame(rows).T

    # 3 Gaps
    def gapz(x):
        g = x.gap_atr
        return {"n": len(x), "Ø Gap ATR": g.mean(), "Median": g.median(), "Ø Gap in R": g.mean() / 1.5,
                "> +0,5 ATR": (g > 0.5).mean(), "> +1 ATR": (g > 1).mean(), "< -0,5 ATR": (g < -0.5).mean(),
                "Eroeffnung <= Stop": (g <= -1.5).mean(), "Ø Ist-Risiko R": x.ist_risiko.mean(),
                "P95 Ist-Risiko R": x.ist_risiko.quantile(0.95), "|Gap| > 5 ATR (n)": int((g.abs() > 5).sum())}
    rows = {"LS-2 Signale": gapz(t), "LS-2 Signale 5J": gapz(t[F["5J"]]), "Zufall alle Tage": gapz(z_alle),
            "Zufall Trendtage": gapz(z_tr)}
    for w in ("EUR", "USD", "CHF"):
        if (t.Waehrung == w).any():
            rows[f"LS-2 {w}"] = gapz(t[t.Waehrung == w])
    T3 = pd.DataFrame(rows).T

    # 4 Region
    rows = {}
    for w in ("EUR", "USD", "CHF"):
        m = (t.Waehrung == w) & t.R_B.notna()
        if m.any():
            d = t.R_B[m] - t.R_A[m]
            rows[w] = {"n": int(m.sum()), "Ø R A": t.R_A[m].mean(), "Ø R B": t.R_B[m].mean(), "Δ": d.mean(), "SE Δ": se(d)}
    T4 = pd.DataFrame(rows).T

    # 5 Gap-Eimer
    kanten = [-np.inf, -0.5, 0.0, 0.5, 1.0, np.inf]
    namen = ["< -0,5", "-0,5 bis 0", "0 bis +0,5", "+0,5 bis +1", "> +1"]
    e = pd.cut(t.gap_atr, kanten, labels=namen)
    rows = {}
    for nm in namen:
        m = (e == nm) & t.R_B.notna()
        rows[nm] = {"n": int(m.sum()), "Ø R A": t.R_A[m].mean(), "Ø R B": t.R_B[m].mean(), "SE B": se(t.R_B[m]),
                    "Ø R B 5J": t.R_B[m & F["5J"]].mean(), "n 5J": int((m & F["5J"]).sum())}
    T5 = pd.DataFrame(rows).T

    # 6 Portfolio
    rows = {}
    for name, (col, m) in ein_varianten(t).items():
        rc, xc, oc = (col, "Exit_A", "rest_A") if col == "R_A" else (col, "Exit_B", "rest_B")
        sub = t.loc[m].copy()
        sub["R"] = sub[rc]; sub["Exit"] = sub[xc]
        idx_map = dd
        sub["rest"] = [pd.Series({idx_map[s].index[k]: v for k, v in r.items() if k < len(idx_map[s].index)})
                       for s, r in zip(sub.Symbol, sub[oc])]
        p, bmax, bmit, ddr, _ = portfolio(_chf_deckel(sub), budget=3, r_eur=50, kapital=12000)
        p5 = p[p.Datum >= ende - pd.DateOffset(years=5)]
        rows[name] = {"Trades/J": len(p) / jahre, "Ø R": p.R.mean(), "Ø R 5J": p5.R.mean(),
                      "EUR/J": p.R.sum() / jahre * 50, "EUR/J 5J": p5.R.sum() / 5 * 50, "DD R": ddr, "Pos max": bmax}
    T6 = pd.DataFrame(rows).T

    fm = {"n": "{:.0f}", "n 5J": "{:.0f}", "EUR/J": "{:,.0f}", "EUR/J 5J": "{:,.0f}", "Trades/J": "{:.1f}", "DD R": "{:.1f}",
          "Pos max": "{:.0f}", "> +0,5 ATR": "{:.1%}", "> +1 ATR": "{:.1%}", "< -0,5 ATR": "{:.1%}",
          "Eroeffnung <= Stop": "{:.2%}", "|Gap| > 5 ATR (n)": "{:.0f}"}
    L = [f"# LS-2: Einstieg Schluss T gegen Eroeffnung T+1 ({pd.Timestamp.now('UTC'):%Y-%m-%d})\n",
         f"Signale ab 2009: n = {len(t)}, Daten bis {ende:%Y-%m-%d}, {len(dd)} Werte EUR/USD/CHF. Raus wegen unbrauchbarer "
         f"Eroeffnung: {raus}. Eroeffnung schon unter Stop: {int(t.R_B.isna().sum())}. Absolute R mit Survivorship- und "
         "Simulationsbias, ohne Kosten und Steuern. Protokoll im Kopf von `research/einstieg_t1.py`.\n",
         "Kontrolle: Basis LS-2 im Bericht vom 2026-11-08 n 8.525, Ø R 0,35 / 0,32 / 0,25 (09-17 / 18-26 / 5J).\n",
         "## 1 Varianten\n", tab(T1, fm), "\n## 2 Zufall\n", tab(T2, fm), "\n", tab(T2b, fm),
         "\n## 3 Gap nach dem Signal\n", tab(T3, fm), "\n## 4 Regionen\n", tab(T4, fm),
         "\n## 5 Gap-Eimer (ATR)\n", tab(T5, fm),
         "\n## 6 Portfolio (3 R a 50 EUR, 12.000 EUR, CHF-Deckel)\n", tab(T6, fm), "\n"]
    (out / "LS2_EINSTIEG_T1.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
