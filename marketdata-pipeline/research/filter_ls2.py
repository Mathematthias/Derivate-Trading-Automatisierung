"""Zusatzfilter fuer die Lern-Spur LS-2 (User-Frage 2026-11-08: EV hoeher bei genug Setups?).

Protokoll (vorher festgelegt, 2026-11-08):
  * Basis: LS-2-Signale (EMA20 x EMA50, Schluss > EMA200, EMA50 > EMA200, ATR% 0,5-6), Universum EUR/USD/CHF.
  * Ausstieg wie live: Stop 1,5 ATR, Chandelier 3 ATR auf Schluss, max 60 HT.
  * Filterliste FEST (unten), keine Nachbesserung nach Ergebnis.
  * Entdeckung 2009-2017, Bestaetigung 2018-2026, dazu letzte 5 Jahre. Ein Filter "traegt" nur, wenn
    er in allen drei Fenstern ueber der Basis liegt UND in der Bestaetigung mindestens 1 Standardfehler.
  * Haeufigkeit: Signale je Woche (letzte 5 J): Anteil Wochen mit >= 1 und >= 2 Signalen.
  * Portfolio: Budget 3 R a 50 EUR, Kapital 12.000 EUR, hoechstens 1 CHF-Position, Auswahl niedrigste ATR%.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from backtest_wochenende import ind, laden, tab, universum  # noqa: E402
from slots_risikobudget import pfad  # noqa: E402

EUR = (".DE", ".PA", ".AS", ".MI", ".MC", ".BR", ".HE", ".VI")


def waehrung(s):
    if "." not in s:
        return "USD"
    return "CHF" if s.endswith(".SW") else "EUR"


def signale(dd, spy, breadth):
    rows = []
    spy_ok = (spy.Close > spy.Close.rolling(200).mean())
    for s, d in dd.items():
        ueber = d.ema20 > d.ema50
        m = (ueber & ~ueber.shift(fill_value=True) & (d.Close > d.ema200) & (d.ema50 > d.ema200)
             & (d.atrp <= 0.06) & (d.atrp >= 0.005))
        vol20 = d.Volume.rolling(20).mean()
        hoch252 = d.Close.rolling(252).max()
        idx = d.index
        for j in np.flatnonzero(m.values):
            if j < 260 or j >= len(d) - 2:
                continue
            tg = idx[j]
            r, x, rest = pfad(d, j)
            rr = pd.Series({idx[k]: v for k, v in rest.items() if k < len(idx)})
            rows.append({
                "Symbol": s, "Datum": tg, "Waehrung": waehrung(s), "ATRp": d.atrp.iloc[j], "R": r,
                "Exit": idx[min(x, len(idx) - 1)], "rest": rr,
                "ext20": d.ext20.iloc[j], "rsi14": d.rsi14.iloc[j],
                "vol_ratio": d.Volume.iloc[j] / vol20.iloc[j] if vol20.iloc[j] else np.nan,
                "dist_hoch": d.Close.iloc[j] / hoch252.iloc[j] - 1,
                "mom6": d.Close.iloc[j] / d.Close.iloc[j - 126] - 1,
                "mom12": d.Close.iloc[j] / d.Close.iloc[j - 252] - 1,
                "ema200_auf": d.ema200.iloc[j] > d.ema200.iloc[j - 20],
                "gap_atr": abs(d.Close.iloc[j] - d.Close.iloc[j - 1]) / d.atr.iloc[j - 1],
                "spy_ok": bool(spy_ok.asof(tg)) if len(spy_ok) else True,
                "breadth": float(breadth.asof(tg)),
            })
    t = pd.DataFrame(rows)
    # Querschnitt: 6M-Momentum-Rang am Signaltag gegen das ganze Universum
    return t


FILTER = {
    "Basis LS-2": lambda t: pd.Series(True, index=t.index),
    "Ueberdehnung <= 3 ATR": lambda t: t.ext20 <= 3,
    "Ueberdehnung <= 2 ATR": lambda t: t.ext20 <= 2,
    "RSI14 <= 70": lambda t: t.rsi14 <= 70,
    "Volumen >= 1,0x 20T": lambda t: t.vol_ratio >= 1.0,
    "Volumen >= 1,5x 20T": lambda t: t.vol_ratio >= 1.5,
    "Naehe 52W-Hoch <= 10 %": lambda t: t.dist_hoch >= -0.10,
    "Naehe 52W-Hoch <= 20 %": lambda t: t.dist_hoch >= -0.20,
    "Abstand 52W-Hoch > 10 % (Gegenprobe)": lambda t: t.dist_hoch < -0.10,
    "6M-Momentum > 0": lambda t: t.mom6 > 0,
    "12M-Momentum > 0": lambda t: t.mom12 > 0,
    "6M-Momentum obere Haelfte": lambda t: t.mom6_rang >= 0.5,
    "EMA200 steigt (20 HT)": lambda t: t.ema200_auf,
    "kein Gap-Tag (|Tagesbewegung| <= 2 ATR)": lambda t: t.gap_atr <= 2,
    "S&P 500 ueber SMA200": lambda t: t.spy_ok,
    "Marktbreite >= 50 % ueber EMA50": lambda t: t.breadth >= 0.5,
}


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
    spy = laden(["SPY"], Path(a.cache).with_name("spy_cache.pkl")).get("SPY")
    dd = {s: ind(d) for s, d in raw.items() if s in uni and s != "SPY"}
    # Marktbreite: Anteil der Werte ueber EMA50, je Tag
    ueber = pd.DataFrame({s: (d.Close > d.ema50).astype(float) for s, d in dd.items()})
    breadth = ueber.mean(axis=1, skipna=True).dropna()
    ret6 = pd.DataFrame({s: d.Close / d.Close.shift(126) - 1 for s, d in dd.items()})
    rang6 = ret6.rank(axis=1, pct=True)

    t = signale(dd, spy if spy is not None else pd.DataFrame({"Close": []}), breadth)
    t = t[t.Datum >= "2009-01-01"].copy()
    t["mom6_rang"] = [float(rang6.at[dt, s]) if s in rang6.columns and dt in rang6.index else np.nan
                      for s, dt in zip(t.Symbol, t.Datum)]
    ende = t.Datum.max()
    f5 = t.Datum >= ende - pd.DateOffset(years=5)
    fe = t.Datum < "2018-01-01"
    fb = t.Datum >= "2018-01-01"
    basis = {"ent": t.R[fe].mean(), "best": t.R[fb].mean(), "5J": t.R[f5].mean()}
    sd = t.R.std()
    wochen5 = pd.period_range((ende - pd.DateOffset(years=5)), ende, freq="W")

    from slots_risikobudget import portfolio as pf  # Budget-Portfolio ohne CHF-Deckel
    rows = {}
    for name, f in FILTER.items():
        m = f(t).fillna(False).astype(bool)
        sub = t[m]
        if len(sub) < 50:
            continue
        r_ent, r_best, r_5 = sub.R[fe[m]].mean(), sub.R[fb[m]].mean(), sub.R[f5[m]].mean()
        n_best = int(fb[m].sum())
        se_best = sd / np.sqrt(max(n_best, 1))
        wo = sub[f5[m]].groupby(sub.Datum[f5[m]].dt.to_period("W")).size().reindex(wochen5, fill_value=0)
        # Portfolio mit CHF-Deckel 1: CHF-Signale nur, wenn keine CHF-Position offen (Naeherung: nach Exit-Datum)
        p, bmax, bmit, ddr, _ = pf(_chf_deckel(sub), budget=3, r_eur=50, kapital=12000)
        p5 = p[p.Datum >= ende - pd.DateOffset(years=5)]
        jahre = (ende - pd.Timestamp("2009-01-01")).days / 365.25
        traegt = (name != "Basis LS-2" and r_ent > basis["ent"] and r_best > basis["best"] and r_5 > basis["5J"]
                  and (r_best - basis["best"]) >= se_best)
        rows[name] = {"n": len(sub), "Ø R 09-17": r_ent, "Ø R 18-26": r_best, "Ø R 5J": r_5,
                      "Wochen >=1 (5J)": (wo >= 1).mean(), "Wochen >=2 (5J)": (wo >= 2).mean(),
                      "PF Trades/J": len(p) / jahre, "PF Ø R": p.R.mean(), "PF Ø R 5J": p5.R.mean(),
                      "PF EUR/J": p.R.sum() / jahre * 50, "PF DD R": ddr, "traegt": "ja" if traegt else "–"}
    df = pd.DataFrame(rows).T
    L = [f"# Zusatzfilter LS-2 ({pd.Timestamp.utcnow():%Y-%m-%d})\n",
         f"Signale ab 2009: n = {len(t)} (EUR/USD/CHF). Standardabweichung je Trade {sd:.2f} R, also Standardfehler "
         f"der Bestaetigungshaelfte rund {sd / np.sqrt(fb.sum()):.2f} R fuer die Basis. Absolute R mit ~+0,07 R "
         "Simulationsbias und Survivorship-Bias; massgeblich ist der Abstand zur Basis.\n",
         "\"traegt\" = in Entdeckung, Bestaetigung und letzten 5 Jahren ueber der Basis und in der Bestaetigung "
         "mindestens 1 Standardfehler darueber. 16 Filter getestet: Einer davon besteht das rein zufaellig "
         "mit einer Wahrscheinlichkeit, die man nicht ignorieren sollte.\n",
         tab(df, {"n": "{:.0f}", "Wochen >=1 (5J)": "{:.0%}", "Wochen >=2 (5J)": "{:.0%}", "PF Trades/J": "{:.1f}",
                  "PF EUR/J": "{:,.0f}", "PF DD R": "{:.1f}"}), "\n"]
    (out / "LERNSPUR_FILTER.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


def _chf_deckel(sub: pd.DataFrame) -> pd.DataFrame:
    """Naeherung des CHF-Deckels: ein CHF-Signal faellt weg, solange ein frueheres CHF-Signal laeuft."""
    sub = sub.sort_values("Datum")
    frei_ab = pd.Timestamp.min
    keep = []
    for i, r in sub.iterrows():
        if r.Waehrung != "CHF":
            keep.append(i)
        elif r.Datum >= frei_ab:
            keep.append(i)
            frei_ab = r.Exit
    return sub.loc[keep]


if __name__ == "__main__":
    raise SystemExit(main())
