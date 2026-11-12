"""Idee 2: Kern-Rotation mit Crash-Schutz. Reine Messung, aendert die Regel nicht.

Basis wie src/rotation_kern.py: 16 ETFs, Score = Mittel der 3/6/12-Monats-Renditen, Top 4,
Absolutfilter (Score <= 0 -> Platz Cash), Umschichtung am Monatsende, 0,10 % je Seite.
Varianten (vorher festgelegt):
  R0   Basis, Cash ohne Zins (Abgleich mit dem Backtest 2026-11-07)
  R0z  Basis, Cash verzinst (BIL, US-Geldmarkt; Naeherung fuer Tagesgeld)
  R1   R0z + Crash-Filter monatlich: SPY-Schluss am Monatsende < SMA200 -> alles Cash
  R2   R0z + Crash-Filter taeglich mit 2-%-Band: raus bei SPY < SMA200 x 0,98,
       wieder rein bei SPY > SMA200 x 1,02 (Auswahl vom letzten Monatsende)
  R3   R0z + Vol-Ziel 12 % p. a.: Anteil = min(1, 12 % / Vola der Auswahl der letzten 63 Tage)
Fenster: Entwicklung 2008-06 bis 2018, Pruefung 2019 bis heute, gesamt.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from daten import KERN, laden

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from rotation_kern import auswahl, scores  # noqa: E402

KOSTEN = 0.0010
LB = [63, 126, 252]
TOP = 4


def simulation(closes: pd.DataFrame, var: str, start="2008-06-01") -> tuple[pd.Series, dict]:
    closes = closes.ffill(limit=5)
    rets = closes.pct_change(fill_method=None).fillna(0.0)
    spy = closes["SPY"]
    sma = spy.rolling(200).mean()
    me = closes.index.to_series().groupby(closes.index.to_period("M")).last()
    me = me[me >= start]
    idx = closes.index
    W = pd.DataFrame(0.0, index=idx, columns=KERN + ["BIL"])
    zustand_an = True
    tage_cash = 0
    tage = 0
    for i, t in enumerate(me.iloc[:-1]):
        neu = auswahl(scores(closes[KERN].loc[:t], LB), TOP, True)
        w = pd.Series(0.0, index=W.columns)
        for s in neu:
            w[s] = 1 / TOP
        if var == "R3" and neu:
            sel = rets[neu].loc[:t].iloc[-63:].mean(axis=1)
            vol = sel.std() * math.sqrt(252)
            f = min(1.0, 0.12 / vol) if vol > 0 else 1.0
            w[neu] *= f
        if var == "R1" and spy.loc[t] < sma.loc[t]:
            w[:] = 0.0
        w["BIL"] = 0.0 if var == "R0" else max(0.0, 1 - w[KERN].sum())
        seg = idx[(idx > t) & (idx <= me.iloc[i + 1])]
        if var == "R2":
            for d in seg:
                # Position fuer Tag d folgt dem Zustand am Vortagesschluss
                prev = idx[idx.get_loc(d) - 1]
                p, m = spy.loc[prev], sma.loc[prev]
                if np.isfinite(m):
                    if zustand_an and p < m * 0.98:
                        zustand_an = False
                    elif not zustand_an and p > m * 1.02:
                        zustand_an = True
                if zustand_an:
                    W.loc[d] = w.values
                else:
                    W.loc[d, :] = 0.0
                    W.loc[d, "BIL"] = 1.0
                    tage_cash += 1
                tage += 1
        else:
            W.loc[seg] = w.values
            tage += len(seg)
            if w[KERN].sum() == 0:
                tage_cash += len(seg)
    W = W.loc[me.iloc[0]:]
    r = (W * rets[W.columns].loc[W.index]).sum(axis=1)
    dw = W[KERN].diff().abs().sum(axis=1).fillna(0.0)
    r = r - dw * KOSTEN
    r = r.iloc[1:]
    info = {"cash": tage_cash / max(tage, 1), "umschlag_jahr": dw.sum() / (len(r) / 252)}
    return r, info


def kennzahlen(r: pd.Series) -> dict:
    r = r.dropna()
    eq = (1 + r).cumprod()
    cagr = eq.iloc[-1] ** (252 / len(r)) - 1
    vol = r.std() * math.sqrt(252)
    dd = float((eq / eq.cummax() - 1).min())
    return {"cagr": cagr, "vol": vol, "dd": dd, "calmar": cagr / abs(dd) if dd < 0 else float("nan")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="config")
    ap.add_argument("--cache", default="work/ideen_cache.pkl")
    ap.add_argument("--out", default="research/ideen/out")
    args = ap.parse_args()
    D = laden(Path(args.cfg), Path(args.cache))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    E = D["etfs"]
    closes = pd.DataFrame({s: E[s].Close for s in KERN + ["SPY", "BIL", "URTH"] if s in E})
    fehl = [s for s in KERN + ["SPY", "BIL"] if s not in closes]
    if fehl:
        raise SystemExit(f"fehlende ETFs: {fehl}")
    closes = closes.loc["2005-01-01":]
    R, INFO = {}, {}
    for v in ("R0", "R0z", "R1", "R2", "R3"):
        R[v], INFO[v] = simulation(closes, v)
        print(v, kennzahlen(R[v]), INFO[v], flush=True)
    for b in ("SPY", "URTH"):
        if b in closes:
            R[b] = closes[b].pct_change(fill_method=None).loc[R["R0"].index].dropna()
    namen = {"R0": "Basis, Cash ohne Zins", "R0z": "Basis, Cash verzinst", "R1": "+ Crash-Filter monatlich",
             "R2": "+ Crash-Filter taeglich (Band 2 %)", "R3": "+ Vol-Ziel 12 %", "SPY": "S&P 500 halten (SPY)",
             "URTH": "MSCI World halten (URTH, ab 2012)"}
    ende = R["R0"].index[-1]
    fenster = [("Entwicklung 2008-06 bis 2018", "2008-06-01", "2018-12-31"),
               ("Pruefung 2019 bis heute", "2019-01-01", str(ende.date())),
               ("gesamt", "2008-06-01", str(ende.date()))]
    L = ["# Idee 2: Kern-Rotation mit Crash-Schutz, 2026-11-12\n",
         f"Daten: Yahoo, Tagesbasis, bis {ende.date()}. Renditen in USD (Signal-ETFs), Kosten 0,10 % je Seite, "
         "Cash-Zins ueber BIL (US-T-Bills, Naeherung fuer Tagesgeld). Keine Steuern.\n"]
    for fname, ab, bis in fenster:
        L.append(f"## {fname}\n")
        L.append("| Variante | CAGR | Vola | MaxDD | CAGR / MaxDD |")
        L.append("|---|---|---|---|---|")
        for k, r in R.items():
            rr = r.loc[ab:bis]
            if len(rr) < 200:
                continue
            m = kennzahlen(rr)
            L.append(f"| {namen[k]} | {m['cagr'] * 100:+.1f} % | {m['vol'] * 100:.1f} % | {m['dd'] * 100:.1f} % | {m['calmar']:.2f} |")
        L.append("")
    L.append("Zeit ganz in Cash (nur Crash-Filter): " + ", ".join(
        f"{k} {INFO[k]['cash'] * 100:.0f} %" for k in ("R1", "R2")) + ". Umschlag je Jahr (Summe der Gewichtsaenderungen): "
        + ", ".join(f"{k} {INFO[k]['umschlag_jahr']:.1f}" for k in INFO) + "\n")
    L.append("## Jahresrenditen\n")
    keys = [k for k in ("R0z", "R1", "R2", "R3", "SPY", "URTH") if k in R]
    L.append("| Jahr | " + " | ".join(keys) + " |")
    L.append("|---" * (len(keys) + 1) + "|")
    jahre = sorted(set(R["R0z"].index.year))
    for j in jahre:
        zeile = []
        for k in keys:
            rr = R[k][R[k].index.year == j]
            zeile.append(f"{((1 + rr).prod() - 1) * 100:+.1f} %" if len(rr) > 20 else "–")
        L.append(f"| {j} | " + " | ".join(zeile) + " |")
    L.append("\nGrenzen: kein Waehrungseffekt (Vehikel in EUR bei Trade Republic), BIL statt Tagesgeld, "
             "Crash-Filter misst nur SPY. Steuer: Crash-Filter realisiert Gewinne frueher.\n")
    (out / "2_Kern_Crashschutz.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
