"""Messung fuer die Thesenkarte "Krypto-Zyklustief" (User-Auftrag 2026-11-20). Reine Messung, kein State.

A  Stand je Coin (USD, BTC/ETH zusaetzlich EUR): Schluss, Allzeithoch, Abstand, 52W-Hoch, Renditen 30/90/180 T,
   relativ zu BTC, Abstand SMA200, ATR14 %, Korrelation der Tagesrenditen mit BTC (90 T), 30-T-Bewegung minus ^GSPC
   (Crowdedness-Vorschau, Definition wie src/thesen_crowdedness.py).
B  BTC-Zyklen: je Zyklus Hoch, erster Schluss >= 50 % unter Hoch, finales Tief, Tage bis dahin, und was ab dem
   ersten -50-%-Schluss bzw. ab dem Stand "13 Monate nach Hoch" noch kam (weiterer Rueckgang, Rendite 6/12 M).
C  Wiederholungstest: Wie oft lag BTC nach einem Zwischentief (tiefster Schluss der letzten 120 T) spaeter noch
   tiefer, wenn der Kurs auf <= 5 % ueber das Zwischentief zurueckkam (heutige Lage: Juni-Tief 2026).
D  Preis-Falsifikat-Kalibrierung: Wochenschluss-Marken X % unter dem Juni-Tief und ihre Trefferquote in alten Zyklen.
"""
from __future__ import annotations
import math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

OUT = Path(__file__).parent / "out"
COINS = ["BTC-USD", "ETH-USD", "HYPE32196-USD", "SOL-USD", "XRP-USD", "BNB-USD", "LINK-USD", "AAVE-USD",
         "UNI7083-USD", "ZEC-USD", "NEAR-USD", "TAO22974-USD", "SUI20947-USD", "ENA-USD", "ONDO-USD",
         "PENDLE-USD", "LTC-USD", "TRX-USD", "AVAX-USD", "ADA-USD", "DOT-USD", "INJ-USD", "QNT-USD", "BAT-USD",
         "RENDER-USD", "XLM-USD", "HBAR-USD", "BCH-USD", "DASH-USD", "ICP-USD"]
EXTRA = ["BTC-EUR", "ETH-EUR", "HYPE32196-EUR", "^GSPC", "^IXIC"]


def lade(sym):
    try:
        d = yf.download(sym, start="2014-01-01", auto_adjust=False, progress=False)
        if d is None or d.empty:
            return None
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        return d.dropna(subset=["Close"])
    except Exception as e:
        print("Fehler", sym, e)
        return None


def atr_pct(d, n=14):
    h, l, c = d["High"], d["Low"], d["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return float(tr.rolling(n).mean().iloc[-1] / c.iloc[-1] * 100)


def ret(c, tage):
    ziel = c.index[-1] - pd.Timedelta(days=tage)
    v = c[c.index <= ziel]
    return float((c.iloc[-1] / v.iloc[-1] - 1) * 100) if len(v) else float("nan")


def f(x, nd=1):
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:+.{nd}f}" if nd is not None else str(x)


def main():
    D = {s: lade(s) for s in COINS + EXTRA}
    D = {k: v for k, v in D.items() if v is not None and len(v) > 30}
    L = ["# Krypto-Zyklus: Messung fuer die Thesenkarte (2026-11-20)\n",
         "Yahoo-Tagesdaten (Schluss UTC). Coins: " + ", ".join(sorted(D)) + "\n"]
    btc = D["BTC-USD"]["Close"]
    spx = D["^GSPC"]["Close"]
    rb = btc.pct_change()
    # A
    L.append("\n## A Stand\n")
    L.append("| Coin | Schluss | Datum | ab Hoch % | Hoch (Datum) | ab 52W-Hoch % | 30 T % | 90 T % | 180 T % | 90 T rel BTC pp | 180 T rel BTC pp | ueber SMA200 % | ATR14 % | Korr BTC 90 T | 30 T minus GSPC pp | seit |\n|" + "---|" * 16)
    rows = []
    for s, d in D.items():
        if s.startswith("^"):
            continue
        c = d["Close"]
        hoch = float(c.max()); hd = c.idxmax().date()
        h52 = float(c.iloc[-365:].max())
        sma = float(c.rolling(200).mean().iloc[-1]) if len(c) > 200 else float("nan")
        r = c.pct_change()
        j = pd.concat([r, rb], axis=1).dropna().iloc[-90:]
        korr = float(j.iloc[:, 0].corr(j.iloc[:, 1])) if len(j) > 30 else float("nan")
        spx30 = ret(spx, 30)
        row = dict(s=s, schluss=float(c.iloc[-1]), datum=c.index[-1].date(), ab_hoch=(c.iloc[-1] / hoch - 1) * 100,
                   hoch=hoch, hd=hd, ab52=(c.iloc[-1] / h52 - 1) * 100, r30=ret(c, 30), r90=ret(c, 90), r180=ret(c, 180),
                   rel90=ret(c, 90) - ret(btc, 90), rel180=ret(c, 180) - ret(btc, 180),
                   sma=(c.iloc[-1] / sma - 1) * 100 if not math.isnan(sma) else float("nan"), atr=atr_pct(d), korr=korr,
                   crowd=ret(c, 30) - spx30, seit=c.index[0].date())
        rows.append(row)
    rows.sort(key=lambda x: -x["rel90"] if not math.isnan(x["rel90"]) else 999)
    for x in rows:
        L.append(f"| {x['s']} | {x['schluss']:.4g} | {x['datum']} | {f(x['ab_hoch'])} | {x['hoch']:.4g} ({x['hd']}) | {f(x['ab52'])} | {f(x['r30'])} | {f(x['r90'])} | {f(x['r180'])} | {f(x['rel90'])} | {f(x['rel180'])} | {f(x['sma'])} | {x['atr']:.1f} | {x['korr']:.2f} | {f(x['crowd'])} | {x['seit']} |")
    # B
    L.append("\n## B BTC-Zyklen (USD, Tagesschluss)\n")
    peaks = ["2013-11-30", "2017-12-17", "2021-11-08", "2025-10-06"]
    L.append("| Hoch | Hochkurs | erster Schluss >= -50 % | Kurs | Tage ab Hoch | finales Tief | Tiefkurs | Tief % ab Hoch | Tage Hoch->Tief | weiter ab -50 % | 6 M ab -50 % | 12 M ab -50 % | Kurs 13 M nach Hoch | weiter ab 13 M | 6 M ab 13 M | 12 M ab 13 M |\n|" + "---|" * 16)
    for i, p in enumerate(peaks):
        p0 = pd.Timestamp(p)
        seg = btc[(btc.index >= p0 - pd.Timedelta(days=10)) & (btc.index <= (pd.Timestamp(peaks[i + 1]) if i + 1 < len(peaks) else btc.index[-1]))]
        if seg.empty:
            continue
        hd = seg.iloc[:40].idxmax(); hk = float(seg.loc[hd])
        nach = seg[seg.index >= hd]
        # finales Tief: Minimum bis zum naechsten Hoch-Durchbruch bzw. Datenende
        tief_d = nach.idxmin(); tief = float(nach.min())
        fz = nach[nach <= hk * 0.5]
        def fwd(d0, k0, tage):
            z = btc[btc.index >= d0 + pd.Timedelta(days=tage)]
            return (float(z.iloc[0]) / k0 - 1) * 100 if len(z) else float("nan")
        def weiter(d0, k0):
            z = btc[(btc.index >= d0) & (btc.index <= tief_d)]
            return (float(z.min()) / k0 - 1) * 100 if len(z) else float("nan")
        if len(fz):
            d50 = fz.index[0]; k50 = float(fz.iloc[0])
            a = (d50.date(), f"{k50:.0f}", (d50 - hd).days, f(weiter(d50, k50)), f(fwd(d50, k50, 182)), f(fwd(d50, k50, 365)))
        else:
            a = ("–",) * 6
        d13 = hd + pd.Timedelta(days=395)
        z13 = btc[btc.index >= d13]
        if len(z13):
            k13 = float(z13.iloc[0]); b = (f"{k13:.0f}", f(weiter(z13.index[0], k13)), f(fwd(z13.index[0], k13, 182)), f(fwd(z13.index[0], k13, 365)))
        else:
            b = ("–",) * 4
        L.append(f"| {hd.date()} | {hk:.0f} | {a[0]} | {a[1]} | {a[2]} | {tief_d.date()} | {tief:.0f} | {f((tief / hk - 1) * 100)} | {(tief_d - hd).days} | {a[3]} | {a[4]} | {a[5]} | {b[0]} | {b[1]} | {b[2]} | {b[3]} |")
    # aktueller Zyklus Detail
    hd = btc[btc.index >= "2025-01-01"].idxmax(); hk = float(btc.loc[hd])
    nach = btc[btc.index >= hd]
    L.append(f"\nAktueller Zyklus: Hoch {hk:.0f} am {hd.date()}, tiefster Schluss seitdem {float(nach.min()):.0f} am {nach.idxmin().date()} "
             f"({(nach.min() / hk - 1) * 100:+.1f} %), heute {float(btc.iloc[-1]):.0f} ({(btc.iloc[-1] / hk - 1) * 100:+.1f} %), "
             f"{(btc.index[-1] - hd).days} Tage nach dem Hoch.\n")
    be = D.get("BTC-EUR")
    if be is not None:
        ce = be["Close"]; he = ce[ce.index >= "2025-01-01"]; hde = he.idxmax()
        ne = ce[ce.index >= hde]
        jun = ce[(ce.index >= "2026-05-01") & (ce.index <= "2026-08-31")]
        L.append(f"BTC-EUR: Hoch {float(he.max()):.0f} am {hde.date()}, tiefster Schluss seitdem {float(ne.min()):.0f} am {ne.idxmin().date()}, "
                 f"Tief Mai-Aug 2026 {float(jun.min()):.0f} am {jun.idxmin().date()}, heute {float(ce.iloc[-1]):.0f}, SMA200 {float(ce.rolling(200).mean().iloc[-1]):.0f}, "
                 f"Wochenschluss-Tief 2026 {float(ce.resample('W-SUN').last()[lambda s: s.index >= '2026-01-01'].min()):.0f}.\n")
        wk = ce.resample("W-SUN").last()
        L.append("Letzte 12 Wochenschluesse BTC-EUR: " + ", ".join(f"{d.date()} {v:.0f}" for d, v in wk.iloc[-12:].items()) + "\n")
    for s in ("ETH-EUR", "HYPE32196-EUR", "HYPE32196-USD", "ETH-USD"):
        if s in D:
            c = D[s]["Close"]
            j26 = c[(c.index >= "2026-01-01")]
            L.append(f"{s}: heute {float(c.iloc[-1]):.4g}, Tief 2026 {float(j26.min()):.4g} am {j26.idxmin().date()}, Hoch 52W {float(c.iloc[-365:].max()):.4g}, SMA200 {float(c.rolling(200).mean().iloc[-1]):.4g}\n")
            wk = c.resample("W-SUN").last()
            L.append(f"  Wochenschluesse: " + ", ".join(f"{d.date()} {v:.4g}" for d, v in wk.iloc[-8:].items()) + "\n")
    # C Wiederholungstest
    L.append("\n## C Retest eines Zwischentiefs (BTC-USD, ab 2014)\n")
    L.append("Ereignis: Schluss <= 5 % ueber dem tiefsten Schluss der letzten 120 T, dieser Tiefpunkt liegt 60-180 T zurueck, und BTC >= 40 % unter dem bisherigen Allzeithoch. Ein Ereignis je 60 T. Gemessen: Schloss BTC in den naechsten 180 T >10 % unter dem Zwischentief? Rendite 6/12 M.\n")
    c = btc; ath = c.cummax(); ev = []; last = None
    for i in range(200, len(c) - 1):
        d = c.index[i]
        fen = c.iloc[i - 180:i - 60] if i >= 180 else None
        if fen is None or fen.empty:
            continue
        zt = float(fen.min())
        if float(c.iloc[i - 60:i].min()) < zt:  # neues Tief dazwischen -> kein Retest
            continue
        if c.iloc[i] <= zt * 1.05 and c.iloc[i] >= zt * 0.97 and c.iloc[i] <= ath.iloc[i] * 0.6:
            if last is None or (d - last).days >= 60:
                last = d
                z = c.iloc[i:i + 181]
                bruch = bool((z < zt * 0.9).any())
                def fw(t):
                    q = c[c.index >= d + pd.Timedelta(days=t)]
                    return (float(q.iloc[0]) / float(c.iloc[i]) - 1) * 100 if len(q) else float("nan")
                ev.append((d.date(), float(c.iloc[i]), zt, bruch, (float(z.min()) / float(c.iloc[i]) - 1) * 100, fw(182), fw(365)))
    L.append("| Datum | Kurs | Zwischentief | spaeter >10 % darunter | tiefster Kurs 180 T % | 6 M % | 12 M % |\n|---|---|---|---|---|---|---|")
    for e in ev:
        L.append(f"| {e[0]} | {e[1]:.0f} | {e[2]:.0f} | {'ja' if e[3] else 'nein'} | {e[4]:+.1f} | {f(e[5])} | {f(e[6])} |")
    n = len([e for e in ev if e[0] < (btc.index[-1] - pd.Timedelta(days=180)).date()])
    nb = len([e for e in ev if e[3] and e[0] < (btc.index[-1] - pd.Timedelta(days=180)).date()])
    L.append(f"\nAbgeschlossene Ereignisse: {n}, davon mit Bruch >10 % unter Zwischentief: {nb}.\n")
    # D
    L.append("\n## D Wochenschluss-Marken unter dem Zyklus-Zwischentief (alte Zyklen)\n")
    L.append("Je alter Baerenmarkt: erstes Zwischentief nach -50 % (tiefster Schluss in den 120 T nach dem ersten -50-%-Schluss) und wie tief das finale Tief darunter lag.\n")
    L.append("| Zyklus | Zwischentief | finales Tief | finales Tief unter Zwischentief % |\n|---|---|---|---|")
    for p in peaks[:-1]:
        seg = btc[btc.index >= p]
        hk = float(seg.iloc[:40].max())
        fz = seg[seg <= hk * 0.5]
        if fz.empty:
            continue
        d50 = fz.index[0]
        zt = float(btc[(btc.index >= d50) & (btc.index <= d50 + pd.Timedelta(days=120))].min())
        nxt = seg[seg.index > d50]
        ft = float(nxt.iloc[:900].min())
        L.append(f"| {p[:4]} | {zt:.0f} | {ft:.0f} | {(ft / zt - 1) * 100:+.1f} |")
    OUT.mkdir(exist_ok=True)
    (OUT / "ZYKLUS.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
