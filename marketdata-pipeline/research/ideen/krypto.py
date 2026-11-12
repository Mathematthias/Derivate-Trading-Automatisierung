"""Idee 4: Krypto-Strategien gegen Kaufen und Halten. Reine Messung.

Kosten 0,50 % je Seite (Kraken Pro Taker 0,40 % + 0,10 % Spread/Slippage). 365 Tage je Jahr.
Strategien je Coin (BTC, ETH, SOL in EUR):
  B      Kaufen und Halten
  T50/T100/T200  investiert, solange der Vortagesschluss ueber der SMA50/100/200 liegt
  M90    woechentlich: investiert, wenn die 90-Tage-Rendite > 0 ist
  ROT    woechentlich BTC oder ETH mit der hoeheren 90-Tage-Rendite, sonst Cash
  DCA    monatlich gleicher Betrag, verschiedene Startpunkte
Dazu: Was kam nach Rueckgaengen von 30/50/70 % unter das 365-Tage-Hoch (BTC und ETH in USD,
laengere Historie)? Und: Wie viel vom Gewinn der Trendstrategien faellt auf Trades unter
einem Jahr (steuerpflichtig nach § 23 EStG), im Gegensatz zum Halten ueber ein Jahr?
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from daten import laden

KOST = 0.005
TJ = 365


def serie(D, s):
    c = D["krypto"][s].Close.dropna()
    c = c[~c.index.duplicated()]
    return c.asfreq("D").ffill()


def positionen(c: pd.Series, var: str) -> pd.Series:
    if var == "B":
        return pd.Series(True, index=c.index)
    if var.startswith("T"):
        n = int(var[1:])
        return (c > c.rolling(n).mean()).shift(1).fillna(False).astype(bool)
    if var == "M90":
        mom = c / c.shift(90) - 1
        p = pd.Series(np.nan, index=c.index)
        sonntage = c.index[c.index.dayofweek == 6]
        p.loc[sonntage] = (mom.loc[sonntage] > 0).astype(float)
        return p.ffill().shift(1).fillna(0).astype(bool)
    raise ValueError(var)


def strat(c: pd.Series, p: pd.Series) -> pd.Series:
    r = c.pct_change(fill_method=None).fillna(0.0)
    out = r.where(p, 0.0)
    wechsel = p.astype(int).diff().abs().fillna(0) > 0
    return out - wechsel * KOST


def kennz(r: pd.Series, p: pd.Series) -> dict:
    eq = (1 + r).cumprod()
    j = len(r) / TJ
    wechsel = (p.astype(int).diff().abs() > 0).sum()
    return {"cagr": eq.iloc[-1] ** (1 / j) - 1, "dd": float((eq / eq.cummax() - 1).min()),
            "mult": float(eq.iloc[-1]), "quote": float(p.mean()), "trades_j": wechsel / 2 / j}


def trades(c: pd.Series, p: pd.Series) -> pd.DataFrame:
    rows = []
    pi = p.astype(int).to_numpy()
    cv = c.to_numpy()
    idx = c.index
    i = 1
    while i < len(pi):
        if pi[i] == 1 and pi[i - 1] == 0:
            ein = cv[i - 1]  # gekauft zum Vortagesschluss
            j = i
            while j < len(pi) and pi[j] == 1:
                j += 1
            aus = cv[j - 1]
            rows.append({"ein": idx[i - 1], "tage": (idx[j - 1] - idx[i - 1]).days,
                         "ret": aus / ein * (1 - KOST) ** 2 - 1})
            i = j
        else:
            i += 1
    return pd.DataFrame(rows)


def dca(c: pd.Series, ab: str, betrag=100.0) -> dict:
    sub = c.loc[ab:]
    monate = sub.groupby(sub.index.to_period("M")).head(1)
    stueck = (betrag * (1 - KOST) / monate).sum()
    eingezahlt = betrag * len(monate)
    wert = stueck * sub.iloc[-1]
    # schlechtester Zwischenstand Wert/Einzahlung
    st = (betrag * (1 - KOST) / monate).reindex(sub.index).fillna(0).cumsum()
    ein = pd.Series(betrag, index=monate.index).reindex(sub.index).fillna(0).cumsum()
    verh = (st * sub / ein).replace([np.inf, -np.inf], np.nan).dropna()
    return {"monate": len(monate), "eingezahlt": eingezahlt, "wert": wert,
            "faktor": wert / eingezahlt, "tief": float(verh.min())}


def dips(c: pd.Series, schwellen=(0.3, 0.5, 0.7)) -> tuple[list[str], pd.Series]:
    hoch = c.rolling(365, min_periods=200).max()
    dd = c / hoch - 1
    rows = []
    for x in schwellen:
        scharf = True
        ev = []
        for t, v in dd.items():
            if not np.isfinite(v):
                continue
            if v >= -0.0001:
                scharf = True
            elif scharf and v <= -x:
                ev.append(t)
                scharf = False
        fw = {h: [] for h in (90, 180, 365, 730)}
        tiefer = []
        for t in ev:
            i = c.index.get_loc(t)
            for h in fw:
                if i + h < len(c):
                    fw[h].append(c.iloc[i + h] / c.iloc[i] - 1)
            nxt = c.iloc[i:i + 366]
            tiefer.append(nxt.min() / c.iloc[i] - 1)
        def z(v):
            if not v:
                return "–"
            a = np.array(v)
            return f"{np.median(a) * 100:+.0f} % ({(a > 0).mean() * 100:.0f} % pos., n={len(a)})"
        rows.append(f"| -{int(x * 100)} % | {len(ev)} | {', '.join(t.strftime('%Y-%m') for t in ev)} | "
                    f"{z(fw[90])} | {z(fw[180])} | {z(fw[365])} | {z(fw[730])} | "
                    f"{(np.median(tiefer) * 100 if tiefer else float('nan')):+.0f} % / {(min(tiefer) * 100 if tiefer else float('nan')):+.0f} % |")
    return rows, dd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="config")
    ap.add_argument("--cache", default="work/ideen_cache.pkl")
    ap.add_argument("--out", default="research/ideen/out")
    args = ap.parse_args()
    D = laden(Path(args.cfg), Path(args.cache))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    L = ["# Idee 4: Krypto-Strategien gegen Kaufen und Halten, 2026-11-12\n",
         "Yahoo-Tagesdaten in EUR, Kosten 0,50 % je Seite (Kraken Pro Taker plus Spread), Cash ohne Zins. "
         "Kauf/Verkauf zum Schlusskurs (UTC) des Signaltags. Keine Steuern in den Renditen, Steueranteil separat.\n"]
    coins = [s for s in ("BTC-EUR", "ETH-EUR", "SOL-EUR") if s in D["krypto"]]
    C = {s: serie(D, s) for s in coins}
    varianten = ["B", "T50", "T100", "T200", "M90"]
    for s in coins:
        c = C[s]
        start = c.index[0] + pd.Timedelta(days=210)
        ende = c.index[-1]
        fenster = [("gesamt", start, ende), ("2015–2020", max(start, pd.Timestamp("2015-01-01")), pd.Timestamp("2020-12-31")),
                   ("2021–heute", max(start, pd.Timestamp("2021-01-01")), ende),
                   ("letzte 2 J", ende - pd.DateOffset(years=2), ende)]
        L.append(f"## {s} ({c.index[0].date()} bis {ende.date()})\n")
        L.append("| Fenster | Variante | CAGR | MaxDD | Endfaktor | investiert | Trades/Jahr |")
        L.append("|---|---|---|---|---|---|---|")
        P = {v: positionen(c, v) for v in varianten}
        Rr = {v: strat(c, P[v]) for v in varianten}
        for fname, ab, bis in fenster:
            if ab >= bis or (bis - ab).days < 365:
                continue
            for v in varianten:
                m = kennz(Rr[v].loc[ab:bis], P[v].loc[ab:bis])
                L.append(f"| {fname} | {v} | {m['cagr'] * 100:+.0f} % | {m['dd'] * 100:.0f} % | "
                         f"{m['mult']:.2f} | {m['quote'] * 100:.0f} % | {m['trades_j']:.1f} |")
        # Steueranteil
        L.append("\n| Variante | Trades | Treffer | Ø Haltedauer (Tage) | Anteil Gewinne aus Trades < 1 Jahr |")
        L.append("|---|---|---|---|---|")
        for v in varianten[1:]:
            tr = trades(c.loc[start:], P[v].loc[start:])
            if tr.empty:
                continue
            gew = tr[tr.ret > 0]
            kurz = gew[gew.tage < 365].ret.sum() / gew.ret.sum() if len(gew) else float("nan")
            L.append(f"| {v} | {len(tr)} | {(tr.ret > 0).mean() * 100:.0f} % | {tr.tage.mean():.0f} | {kurz * 100:.0f} % |")
        L.append("")
    # Rotation BTC/ETH
    if "BTC-EUR" in C and "ETH-EUR" in C:
        df = pd.DataFrame({"BTC": C["BTC-EUR"], "ETH": C["ETH-EUR"]}).dropna()
        mom = df / df.shift(90) - 1
        r = df.pct_change(fill_method=None).fillna(0.0)
        wahl = pd.Series(np.nan, index=df.index, dtype=object)
        so = df.index[df.index.dayofweek == 6]
        for t in so:
            m = mom.loc[t]
            if m.isna().any():
                continue
            k = m.idxmax()
            wahl.loc[t] = k if m[k] > 0 else "CASH"
        wahl = wahl.ffill().shift(1).fillna("CASH")
        rr = pd.Series(0.0, index=df.index)
        for k in ("BTC", "ETH"):
            rr = rr + r[k].where(wahl == k, 0.0)
        wechsel = (wahl != wahl.shift(1)) & (wahl.shift(1).notna())
        rr = rr - wechsel.astype(float) * KOST * np.where((wahl != "CASH") & (wahl.shift(1) != "CASH"), 2, 1)
        start = df.index[0] + pd.Timedelta(days=100)
        L.append("## Rotation BTC/ETH/Cash (woechentlich, 90-Tage-Momentum)\n")
        L.append("| Fenster | ROT CAGR / MaxDD | BTC halten | ETH halten | investiert |")
        L.append("|---|---|---|---|---|")
        for fname, ab in (("gesamt", start), ("2021–heute", pd.Timestamp("2021-01-01")),
                          ("letzte 2 J", df.index[-1] - pd.DateOffset(years=2))):
            sub = rr.loc[ab:]
            eq = (1 + sub).cumprod()
            j = len(sub) / TJ
            def bh(k):
                cc = df[k].loc[ab:]
                e = cc / cc.iloc[0]
                return f"{(e.iloc[-1] ** (1 / j) - 1) * 100:+.0f} % / {(e / e.cummax() - 1).min() * 100:.0f} %"
            L.append(f"| {fname} ({ab.year}) | {(eq.iloc[-1] ** (1 / j) - 1) * 100:+.0f} % / {(eq / eq.cummax() - 1).min() * 100:.0f} % | "
                     f"{bh('BTC')} | {bh('ETH')} | {(wahl.loc[ab:] != 'CASH').mean() * 100:.0f} % |")
        L.append(f"\nAktuelle Wahl: {wahl.iloc[-1]} (90-Tage-Rendite BTC {mom.BTC.iloc[-1] * 100:+.0f} %, ETH {mom.ETH.iloc[-1] * 100:+.0f} %)\n")
    # DCA
    L.append("## Sparplan (monatlich gleicher Betrag)\n")
    L.append("| Coin | Start | Monate | Endwert je eingezahltem € | schlechtester Zwischenstand |")
    L.append("|---|---|---|---|---|")
    for s in ("BTC-EUR", "ETH-EUR"):
        if s not in C:
            continue
        for ab in ("2017-12-01", "2018-06-01", "2021-11-01", "2022-06-01", "2024-01-01", "2025-01-01"):
            if pd.Timestamp(ab) < C[s].index[0]:
                continue
            d = dca(C[s], ab)
            L.append(f"| {s} | {ab[:7]} | {d['monate']} | {d['faktor']:.2f} | {d['tief']:.2f} |")
    L.append("")
    # Rueckgaenge
    for s in ("BTC-USD", "ETH-USD"):
        if s not in D["krypto"]:
            continue
        c = serie(D, s)
        rows, dd = dips(c)
        L.append(f"## Nach Rueckgaengen: {s} ({c.index[0].year}–{c.index[-1].year})\n")
        L.append("Median der Folgerendite ab dem ersten Schluss unter der Schwelle (Episode endet erst mit neuem 365-Tage-Hoch).\n")
        L.append("| Rueckgang vom 365-T-Hoch | Episoden | Ausloesung | +90 T | +180 T | +365 T | +730 T | weiterer Rueckgang im Jahr danach (Median / schlimmster) |")
        L.append("|---|---|---|---|---|---|---|---|")
        L += rows
        f365 = (c.shift(-365) / c - 1).dropna()
        L.append(f"\nUnbedingt (jeder Tag): +365 T Median {f365.median() * 100:+.0f} %, positiv {(f365 > 0).mean() * 100:.0f} %; "
                 f"seit 2021: Median {f365.loc['2021':].median() * 100:+.0f} %, positiv {(f365.loc['2021':] > 0).mean() * 100:.0f} %.")
        L.append(f"Stand {c.index[-1].date()}: {c.iloc[-1]:,.0f} USD, {dd.iloc[-1] * 100:+.0f} % zum 365-Tage-Hoch, "
                 f"{(c.iloc[-1] / c.max() - 1) * 100:+.0f} % zum Allzeithoch ({c.max():,.0f} am {c.idxmax().date()}).\n")
    for s in ("SOL-EUR", "ETH-EUR", "BTC-EUR"):
        if s in C:
            c = C[s]
            h = c.rolling(365, min_periods=200).max()
            L.append(f"Stand {s}: {c.iloc[-1]:,.2f} EUR, {(c.iloc[-1] / h.iloc[-1] - 1) * 100:+.0f} % zum 365-Tage-Hoch, "
                     f"{(c.iloc[-1] / c.max() - 1) * 100:+.0f} % zum Allzeithoch.")
    L.append("\n## Signal heute\n")
    L.append("| Coin | Schluss | SMA50 | SMA200 | T50 | T200 | 90-T-Rendite (M90) |")
    L.append("|---|---|---|---|---|---|---|")
    for s, c in C.items():
        s50, s200 = c.rolling(50).mean().iloc[-1], c.rolling(200).mean().iloc[-1]
        m90 = c.iloc[-1] / c.iloc[-91] - 1
        L.append(f"| {s} | {c.iloc[-1]:,.2f} | {s50:,.2f} | {s200:,.2f} | {'drin' if c.iloc[-1] > s50 else 'Cash'} | "
                 f"{'drin' if c.iloc[-1] > s200 else 'Cash'} | {m90 * 100:+.0f} % |")
    L.append("\nGrenzen: wenige Zyklen (BTC etwa 3 grosse Baerenmaerkte), Coins mit heutigem Erfolg "
             "(Survivorship), keine Zinsen auf Cash, Steuer nur als Anteil ausgewiesen.\n")
    (out / "4_Krypto.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
