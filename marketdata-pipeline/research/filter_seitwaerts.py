"""Seitwaerts-Filter fuer die Lern-Spur LS-1 (User-Frage 2026-11-07).

Frage: Ein EMA20/50-Kreuz im Seitwaertsmarkt ist haeufig und oft ein Fehlsignal. Hilft ein Filter?
Basis ist Signal A aus S6 (EMA20 kreuzt EMA50, Schluss > EMA200, ATR% 0,5-6), Einstieg am
Signalschluss, Stop 1,5 ATR, Chandelier 3 ATR, max 60 HT. Gemessen wird je Filter:
alle Signale und die Live-Auswahl (je Tag das Signal mit niedrigster ATR%), jeweils gegen den
Zufallseinstieg mit gleichem Ausstieg, gesamt, 2009-17, 2018-26 und letzte 5 Jahre.

Merkmale am Signaltag:
  kreuz60    Zahl der EMA20/50-Kreuzungen (beide Richtungen) in den 60 HT davor (Whipsaw-Zaehler)
  er40       Kaufman-Effizienz: |C - C[-40]| / Summe |Tagesaenderung| ueber 40 HT (0 = Rauschen, 1 = Linie)
  adx14      ADX nach Wilder
  ema200_auf EMA200 hoeher als vor 20 HT
  ema50_200  EMA50 ueber EMA200 (die strengere Lesart des Users)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from backtest_wochenende import ind, laden, rstat, sim_trail, tab, universum, zufall  # noqa: E402


def adx(d: pd.DataFrame, n: int = 14) -> pd.Series:
    up = d.High.diff()
    dn = -d.Low.diff()
    pdm = up.where((up > dn) & (up > 0), 0.0)
    ndm = dn.where((dn > up) & (dn > 0), 0.0)
    pc = d.Close.shift()
    tr = pd.concat([d.High - d.Low, (d.High - pc).abs(), (d.Low - pc).abs()], axis=1).max(axis=1)
    a = 1 / n
    atr = tr.ewm(alpha=a, adjust=False).mean()
    pdi = 100 * pdm.ewm(alpha=a, adjust=False).mean() / atr
    ndi = 100 * ndm.ewm(alpha=a, adjust=False).mean() / atr
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(alpha=a, adjust=False).mean()


def signale(dd: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for s, d in dd.items():
        ueber = d.ema20 > d.ema50
        x = ueber & ~ueber.shift(fill_value=True)
        wechsel = (ueber != ueber.shift()).astype(int)
        kreuz60 = wechsel.shift().rolling(60).sum()
        er = (d.Close - d.Close.shift(40)).abs() / d.Close.diff().abs().rolling(40).sum()
        ax = adx(d)
        m = x & (d.Close > d.ema200) & (d.atrp <= 0.06) & (d.atrp >= 0.005)
        frei = 0
        for j in np.flatnonzero(m.values):
            if j < frei or j < 260 or j >= len(d) - 2:
                continue
            e, a = d.Close.iloc[j], d.atr.iloc[j]
            r, _ = sim_trail(d, j, e, e - 1.5 * a, 3.0, 60)
            rows.append({"Symbol": s, "Datum": d.index[j], "R": r, "ATRp": d.atrp.iloc[j],
                         "kreuz60": kreuz60.iloc[j], "er40": er.iloc[j], "adx14": ax.iloc[j],
                         "ema200_auf": bool(d.ema200.iloc[j] > d.ema200.iloc[j - 20]),
                         "ema50_200": bool(d.ema50.iloc[j] > d.ema200.iloc[j])})
            frei = j + 10
    return pd.DataFrame(rows)


FILTER = {
    "ohne Filter (LS-1 heute)": lambda t: pd.Series(True, index=t.index),
    "kreuz60 = 0 (kein Kreuz in 60 HT davor)": lambda t: t.kreuz60 == 0,
    "kreuz60 <= 1": lambda t: t.kreuz60 <= 1,
    "kreuz60 >= 3 (Gegenprobe: Seitwaerts)": lambda t: t.kreuz60 >= 3,
    "er40 >= 0,20": lambda t: t.er40 >= 0.20,
    "er40 >= 0,30": lambda t: t.er40 >= 0.30,
    "er40 < 0,15 (Gegenprobe: Rauschen)": lambda t: t.er40 < 0.15,
    "adx14 >= 20": lambda t: t.adx14 >= 20,
    "adx14 >= 25": lambda t: t.adx14 >= 25,
    "adx14 < 15 (Gegenprobe)": lambda t: t.adx14 < 15,
    "EMA200 steigt (20 HT)": lambda t: t.ema200_auf,
    "EMA50 > EMA200 (strengere Lesart)": lambda t: t.ema50_200,
    "kreuz60 <= 1 und EMA200 steigt": lambda t: (t.kreuz60 <= 1) & t.ema200_auf,
}


def auswahl(t: pd.DataFrame) -> pd.DataFrame:
    """Live-Regel: je Tag das Signal mit der niedrigsten ATR%."""
    return t.sort_values("ATRp").groupby("Datum", as_index=False).head(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="config")
    ap.add_argument("--out", default="research/out")
    ap.add_argument("--cache", default="work/bt_cache.pkl")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    Path(a.cache).parent.mkdir(parents=True, exist_ok=True)
    uni = universum(Path(a.cfg))
    raw = laden(uni, Path(a.cache))
    dd = {s: ind(d) for s, d in raw.items() if s in uni}
    t = signale(dd)
    null = zufall(dd, None, 60, trail=True)
    n0 = null.mean()
    ende = t.Datum.max()
    fenster = {"gesamt": t.Datum >= "2009-01-01", "2009-17": (t.Datum >= "2009-01-01") & (t.Datum < "2018-01-01"),
               "2018-26": t.Datum >= "2018-01-01", "letzte 5 J": t.Datum >= ende - pd.DateOffset(years=5)}

    def zeile(sub: pd.DataFrame) -> dict:
        r = {"n": len(sub), "Treffer": (sub.R > 0).mean() if len(sub) else np.nan,
             "Ø R": sub.R.mean(), "Vorsprung": sub.R.mean() - n0}
        for fn, fm in fenster.items():
            if fn != "gesamt":
                r[f"Ø {fn}"] = sub.R[fm.reindex(sub.index, fill_value=False)].mean()
        return r

    L = [f"# Seitwaerts-Filter fuer LS-1 ({pd.Timestamp.utcnow():%Y-%m-%d})\n",
         f"Signale A: n = {len(t)}, Zeitraum {t.Datum.min().date()} bis {ende.date()}. "
         f"Zufallsnull (gleicher Chandelier-Ausstieg): Ø {n0:+.3f} R, n = {len(null)}. "
         "Absolute R-Werte enthalten rund +0,07 R Simulationsbias, massgeblich ist der Vorsprung. "
         "Survivorship-Bias wie im Hauptbericht.\n"]
    for titel, basis in (("Alle Signale", t[fenster['gesamt']]), ("Live-Auswahl (je Tag niedrigste ATR%)", None)):
        rows = {}
        for fname, f in FILTER.items():
            src = t[fenster["gesamt"]]
            sub = src[f(src)]
            if basis is None:
                sub = auswahl(sub)
            rows[fname] = zeile(sub)
        df = pd.DataFrame(rows).T
        L += [f"## {titel}\n", tab(df, {"n": "{:.0f}", "Treffer": "{:.0%}"}), "\n"]
    t.describe().to_csv(out / "FILTER_SEITWAERTS_merkmale.csv")
    (out / "FILTER_SEITWAERTS.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
