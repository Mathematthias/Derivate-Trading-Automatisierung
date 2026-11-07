"""Index-Strategien ohne Survivorship-Bias (Wochenende 2026-11-07, reine Messung).

T1  Trend-Hebel: Index ueber SMA200 (Vortagesschluss) -> L-fach investiert (taeglich rebalanciert,
    Finanzierungskosten (L-1) x 3 % p. a. + 0,5 % p. a. Produktkosten), sonst Cash (0 %) bzw. 7-10J-Treasuries.
    Gegen Buy & Hold 1x/2x/3x. Fenster gesamt / 5 J / 2 J.
T2  Index-Ruecksetzer kaufen: Drawdown vom 252-Tage-Hoch kreuzt -10/-20/-30 % (erstes Kreuzen nach Erholung
    ueber -5 %). Vorwaertsrendite 3/6/12 Monate gegen unbedingt. Plus aktueller Drawdown je Index.
T3  Monatswechsel: Tagesrendite im Fenster letzter Handelstag + erste 3 Handelstage gegen den Rest.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("research/out")
IDX = ["SPY", "QQQ", "SMH", "XLK", "IGV", "SKYY", "EFA", "IEF"]


def lade() -> pd.DataFrame:
    import yfinance as yf
    df = yf.download(IDX, period="max", auto_adjust=True, group_by="ticker", progress=False, threads=True)
    return pd.DataFrame({s: df[s]["Close"] for s in IDX}).dropna(how="all")


def kz(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 60:
        return {}
    eq = (1 + r).cumprod()
    cagr = eq.iloc[-1] ** (252 / len(r)) - 1
    vol = r.std() * math.sqrt(252)
    return {"CAGR": cagr, "Vol": vol, "MaxDD": float((eq / eq.cummax() - 1).min()),
            "Sharpe0": cagr / vol if vol else np.nan, "Zeit investiert": float((r != 0).mean())}


def hebel(r: pd.Series, L: float) -> pd.Series:
    kosten = ((L - 1) * 0.03 + (0.005 if L > 1 else 0)) / 252
    return L * r - kosten


def tab(df: pd.DataFrame, pct_cols=()) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join([df.index.name or ""] + cols) + " |", "|" + "---|" * (len(cols) + 1)]
    for i, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if isinstance(v, (float, np.floating)):
                cells.append("" if pd.isna(v) else (f"{v:.1%}" if c in pct_cols else f"{v:.2f}"))
            else:
                cells.append(str(v))
        out.append("| " + " | ".join([str(i)] + cells) + " |")
    return "\n".join(out)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    px = lade()
    rets = px.pct_change(fill_method=None)
    stand = px.index[-1]
    fenster = {"gesamt": None, "5 J": stand - pd.DateOffset(years=5), "2 J": stand - pd.DateOffset(years=2)}
    P = ("CAGR", "Vol", "MaxDD", "Zeit investiert")
    L = [f"# Index-Strategien, Stand {stand.date()}\n",
         "Daten Yahoo (bereinigt), keine Survivorship-Verzerrung, USD, Steuern nicht beruecksichtigt.\n"]

    # T1 Trend-Hebel
    zeilen = {}
    for idx in ("SPY", "QQQ"):
        r = rets[idx].dropna()
        c = px[idx].dropna()
        ueber = (c > c.rolling(200).mean()).shift(1).reindex(r.index).fillna(False).astype(bool)
        ief = rets["IEF"].reindex(r.index).fillna(0)
        start = c.index[200]
        varianten = {
            "B&H 1x": r, "B&H 2x": hebel(r, 2), "B&H 3x": hebel(r, 3),
            "Trend 1x / Cash": r.where(ueber, 0.0),
            "Trend 2x / Cash": hebel(r, 2).where(ueber, 0.0),
            "Trend 3x / Cash": hebel(r, 3).where(ueber, 0.0),
            "Trend 2x / Treasuries": hebel(r, 2).where(ueber, ief),
        }
        for v, ser in varianten.items():
            ser = ser.loc[start:]
            for f, st in fenster.items():
                k = kz(ser if st is None else ser.loc[st:])
                zeilen[f"{idx} {v} / {f}"] = k
        zeilen[f"{idx} Wechsel pro Jahr"] = {"Wechsel/Jahr": float(ueber.loc[start:].astype(int).diff().abs().sum()
                                                          / (len(ueber.loc[start:]) / 252))}
    t1 = pd.DataFrame(zeilen).T
    t1.index.name = "Variante / Fenster"
    L += ["## T1 Trend-Hebel (ueber SMA200 investiert, sonst Cash oder Treasuries)\n",
          "Hebel taeglich rebalanciert wie ein Faktor-Zertifikat/gehebelter ETF; Kosten (L-1)x3 % + 0,5 % p. a.\n",
          tab(t1, P), "\n"]

    # T2 Index-Ruecksetzer
    zeilen = {}
    aktuell = {}
    for idx in ("SPY", "QQQ", "SMH", "XLK", "IGV", "SKYY", "EFA"):
        c = px[idx].dropna()
        hoch = c.rolling(252, min_periods=60).max()
        dd = c / hoch - 1
        aktuell[idx] = {"Drawdown heute": float(dd.iloc[-1]), "Kurs ueber SMA200": bool(c.iloc[-1] > c.rolling(200).mean().iloc[-1])}
        for schw in (-0.10, -0.20, -0.30):
            ereignisse = []
            scharf = True
            for t, v in dd.items():
                if v > -0.05:
                    scharf = True
                elif scharf and v <= schw:
                    ereignisse.append(t)
                    scharf = False
            fwd = {}
            for m, h in (("3M", 63), ("6M", 126), ("12M", 252)):
                vals = []
                for t in ereignisse:
                    i = c.index.get_loc(t)
                    if i + h < len(c):
                        vals.append(c.iloc[i + h] / c.iloc[i] - 1)
                fwd[f"Ø {m}"] = np.mean(vals) if vals else np.nan
                fwd[f"schlechtester {m}"] = np.min(vals) if vals else np.nan
                if m == "12M":
                    fwd["positiv 12M"] = np.mean([v > 0 for v in vals]) if vals else np.nan
            unbed = (c.shift(-252) / c - 1).dropna().mean()
            zeilen[f"{idx} {int(schw * 100)} %"] = {"Episoden": len(ereignisse), **fwd, "unbedingt Ø 12M": unbed,
                                                    "letzte": ereignisse[-1].date().isoformat() if ereignisse else "-"}
    t2 = pd.DataFrame(zeilen).T
    t2.index.name = "Index / Schwelle"
    pc = [c for c in t2.columns if c.startswith(("Ø", "schlechtester", "positiv", "unbedingt"))]
    ta = pd.DataFrame(aktuell).T
    ta.index.name = "Index"
    L += ["## T2 Index-Ruecksetzer kaufen (Drawdown vom 252-Tage-Hoch)\n",
          "Episode = erstes Kreuzen der Schwelle nach Erholung ueber -5 %. Wenige Episoden = grosse Unsicherheit.\n",
          tab(t2, pc), "\n", "Stand heute:\n", tab(ta, ("Drawdown heute",)), "\n"]

    # T3 Monatswechsel
    zeilen = {}
    for idx in ("SPY", "QQQ"):
        r = rets[idx].dropna()
        m = r.index.to_period("M")
        pos = r.groupby(m).cumcount()
        rueck = r.groupby(m).cumcount(ascending=False)
        tom = (pos <= 2) | (rueck == 0)
        for f, st in fenster.items():
            rr, tt = (r, tom) if st is None else (r.loc[st:], tom.loc[st:])
            zeilen[f"{idx} / {f}"] = {"Ø Tag im Fenster (bp)": rr[tt].mean() * 1e4,
                                      "Ø Tag sonst (bp)": rr[~tt].mean() * 1e4,
                                      "Anteil Gesamtrendite im Fenster": rr[tt].sum() / rr.sum() if rr.sum() else np.nan,
                                      "Anteil Tage im Fenster": tt.mean()}
    t3 = pd.DataFrame(zeilen).T
    t3.index.name = "Index / Fenster"
    L += ["## T3 Monatswechsel (letzter + erste 3 Handelstage)\n",
          tab(t3, ("Anteil Gesamtrendite im Fenster", "Anteil Tage im Fenster")), "\n"]

    (OUT / "STRATEGIEN.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
