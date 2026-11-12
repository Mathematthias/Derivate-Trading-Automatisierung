"""Idee 3: Saisonalitaet (Halloween-Effekt). Reine Messung.

  H   Halloween: investiert vom letzten Handelstag im Oktober (Schluss) bis zum letzten
      Handelstag im April (Schluss), sonst Cash (0 % Zins)
  HF  Halloween + Trendfilter: im Winterhalbjahr nur investiert, wenn der Vortagesschluss
      ueber der SMA200 liegt
  F   nur Trendfilter (ganzjaehrig, Schluss > SMA200), zur Einordnung von HF
  S   Sommer (Mai bis Oktober), nur als Gegenprobe
Kosten 0,10 % je Wechsel. Indizes: DAX und MDAX sind Performance-Indizes (mit Dividenden),
S&P 500 als Total-Return-Index, Euro Stoxx 50 nur als Kursindex.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

from daten import laden

KOSTEN = 0.0010
WINTER = {11, 12, 1, 2, 3, 4}
WERTE = [("^GDAXI", "DAX (Performance)"), ("^MDAXI", "MDAX (Performance)"), ("^SDAXI", "SDAX (Performance)"),
         ("EXS1.DE", "DAX-ETF EXS1"), ("^SP500TR", "S&P 500 TR"), ("^STOXX50E", "Euro Stoxx 50 (Kurs)")]


def pos_reihe(c: pd.Series, var: str) -> pd.Series:
    sma = c.rolling(200).mean()
    ueber = (c > sma).shift(1).fillna(False).astype(bool)
    w = pd.Series(c.index.month.isin(list(WINTER)), index=c.index)
    if var == "B":
        return pd.Series(True, index=c.index)
    if var == "H":
        return w
    if var == "HF":
        return w & ueber
    if var == "F":
        return ueber
    if var == "S":
        return ~w
    raise ValueError(var)


def strat(c: pd.Series, var: str) -> pd.Series:
    r = c.pct_change(fill_method=None).fillna(0.0)
    p = pos_reihe(c, var)
    out = r.where(p, 0.0)
    wechsel = p.astype(int).diff().abs().fillna(0) > 0
    return out - wechsel * KOSTEN, p


def kennz(r: pd.Series, p: pd.Series | None = None) -> dict:
    eq = (1 + r).cumprod()
    j = len(r) / 252
    return {"cagr": eq.iloc[-1] ** (1 / j) - 1, "dd": float((eq / eq.cummax() - 1).min()),
            "quote": float(p.mean()) if p is not None else 1.0}


def halbjahre(c: pd.Series) -> pd.DataFrame:
    """Rendite je Winterhalbjahr (Nov-Apr) und folgendem Sommer (Mai-Okt)."""
    r = c.pct_change(fill_method=None).fillna(0.0)
    rows = []
    for y in range(c.index[0].year, c.index[-1].year + 1):
        w = r[(r.index >= f"{y}-11-01") & (r.index < f"{y + 1}-05-01")]
        s = r[(r.index >= f"{y + 1}-05-01") & (r.index < f"{y + 1}-11-01")]
        if len(w) > 100 and len(s) > 100:
            rows.append({"winter_ab": y, "winter": (1 + w).prod() - 1, "sommer": (1 + s).prod() - 1})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="config")
    ap.add_argument("--cache", default="work/ideen_cache.pkl")
    ap.add_argument("--out", default="research/ideen/out")
    args = ap.parse_args()
    D = laden(Path(args.cfg), Path(args.cache))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    I = D["indizes"]
    L = ["# Idee 3: Saisonalitaet (Halloween-Effekt), 2026-11-12\n",
         "Investiert von Ende Oktober bis Ende April, Sommer in Cash (ohne Zins). Kosten 0,10 % je Wechsel, "
         "zwei Wechsel im Jahr. B = Kaufen und Halten, H = Halloween, HF = Halloween + SMA200, "
         "F = nur SMA200-Filter, S = nur Sommer (Gegenprobe).\n"]
    for sym, name in WERTE:
        if sym not in I:
            L.append(f"_{name}: keine Daten_\n")
            continue
        c = I[sym].Close.dropna()
        c = c[~c.index.duplicated()]
        start = c.index[0] + pd.Timedelta(days=300)
        ende = c.index[-1]
        fenster = [("gesamt", start, ende), ("bis 2007", start, pd.Timestamp("2007-12-31")),
                   ("2008–2018", pd.Timestamp("2008-01-01"), pd.Timestamp("2018-12-31")),
                   ("2019–heute", pd.Timestamp("2019-01-01"), ende)]
        L.append(f"## {name} ({c.index[0].year}–{ende.year})\n")
        L.append("| Fenster | B CAGR / MaxDD | H CAGR / MaxDD | HF CAGR / MaxDD | F CAGR / MaxDD | S CAGR | H investiert |")
        L.append("|---|---|---|---|---|---|---|")
        res = {v: strat(c, v) for v in ("B", "H", "HF", "F", "S")}
        for fname, ab, bis in fenster:
            if ab >= bis or (bis - ab).days < 900:
                continue
            m = {v: kennz(r.loc[ab:bis], p.loc[ab:bis]) for v, (r, p) in res.items()}
            f = lambda k: f"{m[k]['cagr'] * 100:+.1f} % / {m[k]['dd'] * 100:.0f} %"  # noqa: E731
            L.append(f"| {fname} ({ab.year}–{bis.year}) | {f('B')} | {f('H')} | {f('HF')} | {f('F')} | "
                     f"{m['S']['cagr'] * 100:+.1f} % | {m['H']['quote'] * 100:.0f} % |")
        hj = halbjahre(c)
        if len(hj):
            def zeile(sub, label):
                return (f"| {label} | {len(sub)} | {sub.winter.mean() * 100:+.1f} % | {sub.sommer.mean() * 100:+.1f} % | "
                        f"{(sub.winter > sub.sommer).mean() * 100:.0f} % | {(sub.winter < 0).mean() * 100:.0f} % | "
                        f"{sub.winter.min() * 100:+.1f} % |")
            L.append("\n| Halbjahre | Anzahl | Ø Winter | Ø Sommer | Winter besser | Winter negativ | schlechtester Winter |")
            L.append("|---|---|---|---|---|---|---|")
            L.append(zeile(hj, "alle"))
            L.append(zeile(hj[hj.winter_ab < 2008], "bis 2007"))
            L.append(zeile(hj[(hj.winter_ab >= 2008) & (hj.winter_ab <= 2018)], "2008–2018"))
            L.append(zeile(hj[hj.winter_ab >= 2019], "2019–heute"))
            letzte = hj.tail(8)
            L.append("\nLetzte Halbjahre (Winter ab Nov. des Jahres / folgender Sommer): " + "; ".join(
                f"{int(x.winter_ab)}: {x.winter * 100:+.1f} % / {x.sommer * 100:+.1f} %" for x in letzte.itertuples()))
        L.append("")
    L.append("Grenzen: Cash ohne Zins (2012–2022 lag der EUR-Zins nahe 0, seither hoeher, das hilft H). "
             "Steuer: H realisiert jedes Jahr, Halten schiebt die Steuer auf. Wenige unabhaengige Beobachtungen "
             "(ein Winter pro Jahr).\n")
    (out / "3_Saisonalitaet.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
