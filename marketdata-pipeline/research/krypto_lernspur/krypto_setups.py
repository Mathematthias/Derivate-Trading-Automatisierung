"""Neue Krypto-Setups (User-Frage 2026-11-12), vorab festgelegt, mit FIFO-Steuermodell. Reine Messung.

Alle Setups handeln zum Tagesschluss (UTC) auf Basis der Daten bis zu diesem Schluss, Kosten 0,50 % je
Seite auf jede Umschichtung, Startkapital 10.000, Cash ohne Zins. Kurse in USD.
Steuer: FIFO je Coin, Gewinne aus Lots unter 365 Tagen steuerpflichtig (35 %, Annahme), Verlustausgleich
im Jahr, Freigrenze 600 (bis 2023) / 1.000 (ab 2024) vor Verlustvortrag, Vortrag unbegrenzt.

  S1  Donchian BTC/ETH je 50 %: rein bei Schluss > 50-Tage-Hoch, raus bei Schluss < 20-Tage-Tief
  S2  Zeitreihen-Momentum BTC/ETH je 50 %, woechentlich: Anteil = Anzahl positiver Renditen ueber
      30/90/180 Tage geteilt durch 3
  S3  Rotation: woechentlich die 3 Coins mit der hoechsten 60-Tage-Rendite (> 0), nur wenn BTC > SMA200;
      Vergleich: zufaellige 3 aus denselben zulaessigen Coins
  S4  ETH/BTC-Schalter, woechentlich: BTC > SMA200 -> ETH, wenn ETH/BTC ueber seiner SMA50, sonst BTC;
      BTC < SMA200 -> Cash
  S5  Dip im Aufwaertstrend BTC/ETH je 50 %: Schluss > SMA200 und RSI(2) < 10 -> kaufen;
      raus bei Schluss > SMA5 oder nach 10 Tagen
  S6  Sparplaene (nie verkaufen): monatlich gleicher Betrag in BTC (a) immer, (b) nur ueber SMA200
      (sonst Cash sammeln und beim Ueberschreiten investieren), (c) unter SMA200 doppelt, ueber 2,4x SMA200 aussetzen
  S7  Trendregel-Feinschliff BTC: T200 taeglich (Referenz), woechentlich, mit 3-%-Band, EMA200
  S8  Halving-Zyklus (User-Nachfrage): BTC von 500 Tagen vor bis 540 Tage nach dem Halving, sonst Cash;
      zusaetzlich mit T200. Dazu Renditen je Zyklusphase fuer BTC, ETH und Altkorb und die Korrelation mit BTC.
      Nur 3 Zyklen im Datensatz und die Regel ist an genau diesen Zyklen abgelesen: keine echte Pruefung.
Fenster: Start 2018 (Entwicklung bis 2021) und Start 2022 / 2024 (Pruefung).
"""
from __future__ import annotations

import argparse
import math
import pickle
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

KOST = 0.005
STEUER = 0.35
SEED = 20261112


# ------------------------------------------------------------------ Steuer + Depot
class Depot:
    def __init__(self, kapital: float):
        self.cash = kapital
        self.lots: dict[str, deque] = {}
        self.jahr: dict[int, float] = {}
        self.jahr_gesamt: dict[int, float] = {}
        self.vortrag = 0.0
        self.steuer = 0.0
        self.trades = 0
        self.gew_kurz = 0.0
        self.gew_lang = 0.0

    def menge(self, c: str) -> float:
        return sum(l[0] for l in self.lots.get(c, ()))

    def kaufen(self, c: str, eur: float, px: float, d: pd.Timestamp):
        if eur <= 1:
            return
        q = eur * (1 - KOST) / px
        self.lots.setdefault(c, deque()).append([q, eur / q, d])
        self.cash -= eur
        self.trades += 1

    def verkaufen(self, c: str, q: float, px: float, d: pd.Timestamp):
        lots = self.lots.get(c)
        rest = q
        while lots and rest > 1e-12:
            lot = lots[0]
            nimm = min(lot[0], rest)
            erloes = nimm * px * (1 - KOST)
            g = erloes - nimm * lot[1]
            if (d - lot[2]).days < 365:
                self.jahr[d.year] = self.jahr.get(d.year, 0.0) + g
                if g > 0:
                    self.gew_kurz += g
            elif g > 0:
                self.gew_lang += g
            self.cash += erloes
            lot[0] -= nimm
            rest -= nimm
            if lot[0] <= 1e-12:
                lots.popleft()
        self.trades += 1

    def jahresende(self, jahr: int):
        net = self.jahr.get(jahr, 0.0)
        fg = 600.0 if jahr <= 2023 else 1000.0
        if net < 0:
            self.vortrag += -net
            return
        if net < fg:
            return
        nutz = min(self.vortrag, net)
        self.vortrag -= nutz
        st = (net - nutz) * STEUER
        self.steuer += st
        self.cash -= st


def simulation(P: pd.DataFrame, W: pd.DataFrame, start: str, kapital=10000.0, toleranz=0.02) -> tuple[pd.Series, Depot]:
    """P: Schlusskurse, W: Zielgewichte je Tag (Summe <= 1). Umschichtung zum Schluss, wenn sich das
    Gewicht eines Coins um mehr als `toleranz` aendert oder auf 0 faellt / von 0 steigt."""
    P = P.loc[start:]
    W = W.reindex(P.index).fillna(0.0)
    dep = Depot(kapital)
    eq = []
    vorher = pd.Series(0.0, index=W.columns)
    for d in P.index:
        px = P.loc[d]
        wert = dep.cash + sum(dep.menge(c) * px[c] for c in dep.lots if np.isfinite(px.get(c, np.nan)))
        ziel = W.loc[d]
        # Nur handeln, wenn sich das Zielgewicht eines Coins aendert (keine laufende Rebalancierung,
        # Positionen duerfen driften wie bei einer echten Ein-/Aus-Regel).
        geaendert = [c for c in W.columns if abs(ziel[c] - vorher[c]) > 1e-9 and np.isfinite(px.get(c, np.nan))]
        for c in geaendert:  # Verkaeufe zuerst
            q = dep.menge(c)
            if q <= 0:
                continue
            soll = float(ziel[c])
            ist = q * px[c] / wert if wert > 0 else 0
            if soll == 0:
                dep.verkaufen(c, q, px[c], d)
            elif ist - soll > toleranz:
                dep.verkaufen(c, (ist - soll) * wert / px[c], px[c], d)
        for c in geaendert:
            soll = float(ziel[c])
            if soll <= 0:
                continue
            ist = dep.menge(c) * px[c] / wert if wert > 0 else 0
            if soll - ist > toleranz or ist == 0:
                dep.kaufen(c, min((soll - ist) * wert, dep.cash), px[c], d)
        vorher = ziel.copy()
        for c in W.columns:  # Coin ohne Kurs an dem Tag: Ziel spaeter erneut pruefen
            if not np.isfinite(px.get(c, np.nan)):
                vorher[c] = 0.0 if dep.menge(c) == 0 else vorher[c]
        if d.month == 12 and d.day == 31:
            dep.jahresende(d.year)
        eq.append(dep.cash + sum(dep.menge(c) * px[c] for c in dep.lots if np.isfinite(px.get(c, np.nan))))
    return pd.Series(eq, index=P.index), dep


def kennz(eq: pd.Series) -> dict:
    j = (eq.index[-1] - eq.index[0]).days / 365.25
    return {"end": float(eq.iloc[-1]), "cagr": (eq.iloc[-1] / eq.iloc[0]) ** (1 / j) - 1,
            "dd": float((eq / eq.cummax() - 1).min())}


# ------------------------------------------------------------------ Indikatoren
def rsi(c: pd.Series, n: int) -> pd.Series:
    dlt = c.diff()
    up = dlt.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-dlt.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def woechentlich(sig: pd.DataFrame | pd.Series):
    """Nur sonntags neu entscheiden, dazwischen halten."""
    x = sig.copy().astype(float)
    x[x.index.dayofweek != 6] = np.nan
    return x.ffill().fillna(0.0)


# ------------------------------------------------------------------ Setups -> Zielgewichte
def s1_donchian(P):
    W = pd.DataFrame(0.0, index=P.index, columns=["BTC", "ETH"])
    for c in W.columns:
        x = P[c]
        hoch, tief = x.rolling(50).max().shift(1), x.rolling(20).min().shift(1)
        drin = False
        w = []
        for d in x.index:
            if not drin and x[d] > hoch[d]:
                drin = True
            elif drin and x[d] < tief[d]:
                drin = False
            w.append(0.5 if drin else 0.0)
        W[c] = w
    return W


def s2_tsmom(P):
    W = pd.DataFrame(0.0, index=P.index, columns=["BTC", "ETH"])
    for c in W.columns:
        x = P[c]
        s = sum((x / x.shift(n) - 1 > 0).astype(float) for n in (30, 90, 180)) / 3
        s[x.shift(180).isna()] = 0
        W[c] = woechentlich(s) * 0.5
    return W


def s3_rotation(P, btc_ok, zufall_rng=None, top=3):
    mom = P / P.shift(60) - 1
    alt = P.notna().cumsum() >= 365
    W = pd.DataFrame(0.0, index=P.index, columns=P.columns)
    so = P.index[P.index.dayofweek == 6]
    letzte = None
    for d in P.index:
        if d in so:
            if not btc_ok.get(d, False):
                letzte = []
            else:
                m = mom.loc[d][alt.loc[d] & (mom.loc[d] > 0)].dropna()
                if zufall_rng is not None:
                    k = list(m.index)
                    letzte = list(zufall_rng.choice(k, size=min(top, len(k)), replace=False)) if k else []
                else:
                    letzte = list(m.sort_values(ascending=False).index[:top])
        if letzte:
            W.loc[d, letzte] = 1 / top
    return W


def s4_ethbtc(P, btc_ok):
    r = P.ETH / P.BTC
    eth_vorn = r > r.rolling(50).mean()
    W = pd.DataFrame(0.0, index=P.index, columns=["BTC", "ETH"])
    W["ETH"] = (btc_ok & eth_vorn).astype(float)
    W["BTC"] = (btc_ok & ~eth_vorn).astype(float)
    return woechentlich(W)


def s5_dip(P):
    W = pd.DataFrame(0.0, index=P.index, columns=["BTC", "ETH"])
    tr = []
    for c in W.columns:
        x = P[c]
        sma200, sma5, r2 = x.rolling(200).mean(), x.rolling(5).mean(), rsi(x, 2)
        drin, seit, ein = False, 0, 0.0
        w = []
        for d in x.index:
            if drin:
                seit += 1
                if x[d] > sma5[d] or seit >= 10:
                    tr.append(x[d] / ein * (1 - KOST) ** 2 - 1)
                    drin = False
            elif x[d] > sma200[d] and r2[d] < 10:
                drin, seit, ein = True, 0, x[d]
            w.append(0.5 if drin else 0.0)
        W[c] = w
    return W, tr


def s7_trend(P, art: str):
    x = P.BTC
    if art == "EMA200":
        lin = x.ewm(span=200, adjust=False).mean()
    else:
        lin = x.rolling(200).mean()
    if art == "Band3":
        drin, w = False, []
        for d in x.index:
            if not drin and x[d] > lin[d] * 1.03:
                drin = True
            elif drin and x[d] < lin[d] * 0.97:
                drin = False
            w.append(1.0 if drin else 0.0)
        s = pd.Series(w, index=x.index)
    else:
        s = (x > lin).astype(float)
    if art == "woechentlich":
        s = woechentlich(s)
    return pd.DataFrame({"BTC": s})


HALVINGS = [pd.Timestamp(x) for x in ("2012-11-28", "2016-07-09", "2020-05-11", "2024-04-20", "2028-04-15")]


def zyklus_phase(idx: pd.DatetimeIndex) -> pd.Series:
    """Tage seit dem letzten Halving (Halving-Termine folgen aus der Blockhoehe, kein Blick in die Zukunft;
    2028 ist eine Schaetzung und betrifft nur kuenftige Tage)."""
    out = []
    for d in idx:
        letzte = max(h for h in HALVINGS if h <= d)
        out.append((d - letzte).days)
    return pd.Series(out, index=idx)


def s8_zyklus(P, mit_trend: bool):
    """Investiert in BTC von 500 Tagen vor bis 540 Tage nach einem Halving, sonst Cash.
    Festgelegt nach dem bekannten Muster (Hochs 2017-12, 2021-11, 2025-10 je 17-18 Monate nach dem Halving)."""
    tage_seit = zyklus_phase(P.index)
    naechstes = pd.Series([min(h for h in HALVINGS if h > d) for d in P.index], index=P.index)
    tage_bis = (naechstes - P.index.to_series()).dt.days
    drin = (tage_seit <= 540) | (tage_bis <= 500)
    if mit_trend:
        drin &= P.BTC > P.BTC.rolling(200).mean()
    return pd.DataFrame({"BTC": drin.astype(float)}, index=P.index)


def zyklus_tabelle(P) -> list[str]:
    """Rendite nach Zyklusphase: BTC, ETH gegen BTC, Altcoin-Korb gegen BTC; dazu Korrelation."""
    r = P.pct_change(fill_method=None)
    alts = [c for c in P.columns if c not in ("BTC", "ETH")]
    korb = r[alts].mean(axis=1, skipna=True)
    ph = zyklus_phase(P.index) / 30.44
    bins = [0, 6, 12, 18, 24, 30, 36, 49]
    lab = ["0–6 M", "6–12 M", "12–18 M", "18–24 M", "24–30 M", "30–36 M", "36–48 M"]
    kl = pd.cut(ph, bins=bins, labels=lab, right=False)
    L = ["## Zyklusphasen (Monate nach dem Halving; Halvings 2016, 2020, 2024 im Datensatz)\n",
         "Ø Rendite je Monat in der Phase, ueber alle Zyklen gemittelt. Altkorb = gleichgewichtet alle anderen Coins "
         "mit Daten an dem Tag.\n",
         "| Phase | Zyklen mit Daten | BTC je Monat | ETH minus BTC je Monat | Altkorb minus BTC je Monat | Anteil Monate BTC positiv |",
         "|---|---|---|---|---|---|"]
    mon = pd.DataFrame({"btc": r.BTC, "eth": r.ETH, "korb": korb, "kl": kl}).dropna(subset=["btc"])
    mon["m"] = mon.index.to_period("M")
    g = mon.groupby(["m"]).agg(btc=("btc", lambda x: (1 + x).prod() - 1), eth=("eth", lambda x: (1 + x.fillna(0)).prod() - 1),
                               korb=("korb", lambda x: (1 + x.fillna(0)).prod() - 1), kl=("kl", "first"))
    g["jahr"] = [p.start_time.year for p in g.index]
    for k in lab:
        sub = g[g.kl == k]
        if sub.empty:
            continue
        zyklen = len({max(h for h in HALVINGS if h <= p.start_time).year for p in sub.index})
        L.append(f"| {k} | {zyklen} | {sub.btc.mean() * 100:+.1f} % | {(sub.eth - sub.btc).mean() * 100:+.1f} % | "
                 f"{(sub.korb - sub.btc).mean() * 100:+.1f} % | {(sub.btc > 0).mean() * 100:.0f} % |")
    # Korrelationen
    c90 = {c: r[c].rolling(90).corr(r.BTC) for c in P.columns if c != "BTC"}
    jetzt = pd.Series({c: v.iloc[-1] for c, v in c90.items()}).dropna()
    med = pd.concat(c90, axis=1).median(axis=1)
    L.append(f"\nKorrelation der Tagesrenditen mit BTC (90 Tage): heute Median {jetzt.median():.2f} "
             f"(Spanne {jetzt.min():.2f} bis {jetzt.max():.2f}); Median ueber die Zeit: 2018 {med.loc['2018'].mean():.2f}, "
             f"2021 {med.loc['2021'].mean():.2f}, 2022 {med.loc['2022'].mean():.2f}, 2025 {med.loc['2025'].mean():.2f}.\n")
    # Hochs und Tiefs
    hl = []
    for i, h in enumerate(HALVINGS[1:4]):
        nxt = HALVINGS[i + 2]
        seg = P.BTC.loc[h:nxt].dropna()
        if len(seg) < 30:
            continue
        hoch_d = seg.idxmax()
        nach = seg.loc[hoch_d:]
        tief_d = nach.idxmin()
        hl.append(f"Halving {h.date()}: Hoch {hoch_d.date()} ({(hoch_d - h).days / 30.44:.0f} M danach), "
                  f"danach Tief {tief_d.date()} ({(tief_d - h).days / 30.44:.0f} M nach Halving, {(nach.min() / seg.max() - 1) * 100:.0f} %)")
    L.append("Zyklusmarken BTC: " + "; ".join(hl) + f". Heute: {zyklus_phase(P.index).iloc[-1] / 30.44:.0f} Monate nach dem Halving 2024.\n")
    return L


def sparplan_sim(x_voll: pd.Series, start: str, art: str, betrag=200.0) -> dict:
    sma = x_voll.rolling(200).mean()
    x = x_voll.loc[start:]
    sma = sma.loc[start:]
    menge, eingezahlt, wartend = 0.0, 0.0, 0.0
    werte = []
    monat = None
    for d, px in x.items():
        neu = (d.year, d.month) != monat
        if neu:
            monat = (d.year, d.month)
            eingezahlt += betrag
            if art == "immer":
                menge += betrag * (1 - KOST) / px
            elif art == "ueber200":
                wartend += betrag
            elif art == "unter200x2":
                # unter der SMA200 doppelte Rate (frisches Geld), ueber 2,4x SMA200 aussetzen
                f = 2.0 if px < sma[d] else (0.0 if px > 2.4 * sma[d] else 1.0)
                eingezahlt += betrag * (f - 1)
                menge += betrag * f * (1 - KOST) / px
        if art == "ueber200" and wartend > 0 and px > sma[d]:
            menge += wartend * (1 - KOST) / px
            wartend = 0.0
        werte.append((menge * px + wartend) / eingezahlt)
    return {"monate": len(set((d.year, d.month) for d in x.index)), "eingezahlt": eingezahlt,
            "endwert": menge * x.iloc[-1] + wartend, "faktor": (menge * x.iloc[-1] + wartend) / eingezahlt,
            "tief": float(min(werte)), "reserve": wartend}


# ------------------------------------------------------------------ Bericht
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="work/krypto_lernspur.pkl")
    ap.add_argument("--out", default="research/krypto_lernspur/out")
    args = ap.parse_args()
    D = pickle.loads(Path(args.cache).read_bytes())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    P = pd.DataFrame({s.split("-")[0]: d.Close for s, d in D.items()}).sort_index()
    P = P.loc["2014-09-17":]
    btc_ok = (P.BTC > P.BTC.rolling(200).mean())
    rng = np.random.default_rng(SEED)
    setups = {
        "S1 Donchian 50/20 BTC/ETH": s1_donchian(P),
        "S2 Zeitreihen-Momentum BTC/ETH": s2_tsmom(P),
        "S3 Rotation Top 3 (60 T, BTC-Filter)": s3_rotation(P, btc_ok),
        "S4 ETH/BTC-Schalter": s4_ethbtc(P, btc_ok),
    }
    W5, dip_trades = s5_dip(P)
    setups["S5 Dip im Aufwaertstrend BTC/ETH"] = W5
    for art in ("taeglich", "woechentlich", "Band3", "EMA200"):
        setups[f"S7 BTC-Trend SMA200 {art}" if art != "EMA200" else "S7 BTC-Trend EMA200 taeglich"] = s7_trend(P, art)
    setups["S8 Halving-Zyklus BTC"] = s8_zyklus(P, False)
    setups["S8 Halving-Zyklus BTC + T200"] = s8_zyklus(P, True)
    setups["Referenz BTC halten"] = pd.DataFrame({"BTC": 1.0}, index=P.index)
    setups["Referenz ETH halten"] = pd.DataFrame({"ETH": 1.0}, index=P.index)
    setups["Referenz BTC/ETH-T200 je 50 %"] = pd.DataFrame({
        "BTC": (P.BTC > P.BTC.rolling(200).mean()).astype(float) * 0.5,
        "ETH": (P.ETH > P.ETH.rolling(200).mean()).astype(float) * 0.5}, index=P.index)
    starts = ("2018-01-01", "2022-01-01", "2024-01-01")
    L = ["# Neue Krypto-Setups mit Steuermodell (2026-11-12)\n",
         f"Daten: Yahoo, USD, {P.shape[1]} Coins, bis {P.index[-1].date()}. Handel zum Tagesschluss, Kosten 0,50 % je Seite, "
         "Startkapital 10.000, Cash ohne Zins. Steuer FIFO, 35 % auf Gewinne aus Lots unter 1 Jahr, Freigrenze, "
         "Verlustvortrag; Steuer des laufenden Jahres noch offen. Alle Werte nach gezahlter Steuer.\n"]
    for start in starts:
        L.append(f"## Start {start}\n")
        L.append("| Setup | Endkapital | CAGR | MaxDD | Trades | Steuer gezahlt | Gewinnanteil steuerfrei (> 1 J) |")
        L.append("|---|---|---|---|---|---|---|")
        for name, W in setups.items():
            cols = [c for c in W.columns if c in P.columns]
            eq, dep = simulation(P[cols], W[cols], start)
            m = kennz(eq)
            ant = dep.gew_lang / (dep.gew_lang + dep.gew_kurz) if (dep.gew_lang + dep.gew_kurz) > 0 else float("nan")
            L.append(f"| {name} | {m['end']:,.0f} | {m['cagr'] * 100:+.1f} % | {m['dd'] * 100:.0f} % | {dep.trades} | "
                     f"{dep.steuer:,.0f} | {ant * 100:.0f} % |".replace(",", "."))
            print(start, name, f"{m['cagr']:.3f}", flush=True)
        # Zufallsrotation
        res = []
        for k in range(20):
            Wz = s3_rotation(P, btc_ok, zufall_rng=np.random.default_rng(SEED + k))
            eq, _ = simulation(P, Wz, start)
            res.append(kennz(eq)["cagr"])
        L.append(f"\nS3 gegen Zufall (20 Laeufe, zufaellige 3 aus denselben zulaessigen Coins): "
                 f"Median CAGR {np.median(res) * 100:+.1f} %, Spanne {min(res) * 100:+.1f} bis {max(res) * 100:+.1f} %.\n")
    L += zyklus_tabelle(P)
    # S5 je Trade
    t = np.array(dip_trades)
    if len(t):
        L.append(f"## S5 je Trade (2015–heute, BTC und ETH)\n\n{len(t)} Trades, Treffer {(t > 0).mean() * 100:.0f} %, "
                 f"Ø {t.mean() * 100:+.2f} %, Median {np.median(t) * 100:+.2f} % (nach Kosten). Alle Gewinne steuerpflichtig (< 10 Tage).\n")
    # Sparplaene
    L.append("## S6 Sparplaene (200 je Monat, nie verkaufen, also nach 1 Jahr steuerfrei)\n")
    L.append("| Coin | Start | Variante | eingezahlt | Endwert | je eingezahltem € | schlechtester Zwischenstand | Reserve am Ende |")
    L.append("|---|---|---|---|---|---|---|---|")
    for coin in ("BTC", "ETH"):
        for start in ("2018-01-01", "2021-11-01", "2022-06-01", "2024-01-01", "2025-01-01"):
            for art in ("immer", "ueber200", "unter200x2"):
                r = sparplan_sim(P[coin].dropna(), start, art)
                L.append(f"| {coin} | {start[:7]} | {art} | {r['eingezahlt']:,.0f} | {r['endwert']:,.0f} | {r['faktor']:.2f} | "
                         f"{r['tief']:.2f} | {r['reserve']:,.0f} |".replace(",", "."))
    L.append("\nVarianten: immer = jeden Monat kaufen; ueber200 = nur kaufen, wenn der Kurs ueber der SMA200 liegt, sonst "
             "sammeln und beim Ueberschreiten alles investieren; unter200x2 = unter der SMA200 doppelte Rate (zusaetzliches "
             "Geld), ueber 2,4x SMA200 aussetzen.\n")
    # Stand heute
    x = P.BTC
    L.append("## Stand heute\n")
    L.append(f"BTC {x.iloc[-1]:,.0f} USD, SMA200 {x.rolling(200).mean().iloc[-1]:,.0f}, EMA200 {x.ewm(span=200, adjust=False).mean().iloc[-1]:,.0f}, "
             f"50-T-Hoch {x.rolling(50).max().iloc[-2]:,.0f}, 20-T-Tief {x.rolling(20).min().iloc[-2]:,.0f}. "
             f"ETH/BTC ueber SMA50: {'ja' if (P.ETH / P.BTC).iloc[-1] > (P.ETH / P.BTC).rolling(50).mean().iloc[-1] else 'nein'}. "
             f"Zielgewichte heute: " + "; ".join(
                 f"{n.split(' ')[0]}: " + (", ".join(f"{c} {v * 100:.0f} %" for c, v in W.iloc[-1].items() if v > 0) or "Cash")
                 for n, W in setups.items() if not n.startswith("Referenz")) + "\n")
    L.append("Grenzen: Survivorship-Bias (S3 waehlt aus heute noch existierenden Coins), nur 2–3 Krypto-Zyklen, "
             "Kurse in USD, Steuermodell vereinfacht, Handel zum Signal-Schluss.\n")
    (out / "SETUPS.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
