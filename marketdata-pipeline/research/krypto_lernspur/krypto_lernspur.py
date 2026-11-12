"""Lern-Spur-Regeln (Frueh-Stack) auf Krypto, mit Steuermodell § 23 EStG. Reine Messung.

User-Frage 2026-11-12: Altbestaende laufen weiter; kann fuer frisches Krypto-Kapital die Lern-Spur
oder eine Verfeinerung helfen? Die Steuer spielt eine grosse Rolle.

Signal (wie LS-2): EMA20 kreuzt EMA50 nach oben, Schluss > EMA200, EMA50 > EMA200.
Varianten (vorher festgelegt):
  K0  LS-2 1:1: ATR% 0,5-6 %, Stop 1,5 ATR, Chandelier 3 ATR, Zeitausstieg nach 60 Tagen
  K1  K0 ohne ATR%-Obergrenze (Krypto schwankt mehr)
  K2  K1 + Marktfilter: BTC-Schluss > BTC-SMA200
  K3  K2 ohne Zeitausstieg (nur Chandelier) -> Gewinner duerfen ueber 1 Jahr laufen (steuerfrei)
  K4  K3 mit weiteren Stops: Anfang 2,5 ATR, Chandelier 4 ATR
Kosten 0,50 % je Seite. Kurse in USD (EUR-Effekt nicht modelliert). Einstieg zum Schluss des
Signaltags (Krypto handelt durch; naechste Eroeffnung = dieser Schluss).

Teil A: je Trade gegen Zufall (A: beliebiger Tag; B: beliebiger Tag im gleichen Trendregime),
gleicher Ausstieg.
Teil B: Portfolio mit frischem Kapital 10.000, R = 1 % des Kapitals, Risikobudget 3 R wie LS-2,
hoechstens 30 % je Position, Auswahl niedrigste ATR%. Vergleich: BTC halten, BTC-T200 (ganz rein ueber
SMA200, ganz raus darunter), BTC/ETH-T200 je zur Haelfte. Steuermodell vereinfacht:
Gewinne aus Verkaeufen < 365 Tage nach Kauf steuerpflichtig, Verlustausgleich im Jahr, Freigrenze
600 (bis 2023) / 1.000 (ab 2024) auf den Jahresgewinn vor Verlustvortrag, Verlustvortrag unbegrenzt,
Steuersatz 35 % (Annahme), Zahlung zum Jahresende aus dem Konto. Keine Steuerberatung.
"""
from __future__ import annotations

import argparse
import math
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

KOST = 0.005
SEED = 20261112
STEUER = 0.35
COINS = ["BTC-USD", "ETH-USD", "XRP-USD", "LTC-USD", "BCH-USD", "ADA-USD", "XLM-USD", "LINK-USD",
         "DOT-USD", "SOL-USD", "DOGE-USD", "TRX-USD", "ETC-USD", "ATOM-USD", "AVAX-USD", "UNI7083-USD",
         "AAVE-USD", "ALGO-USD", "XTZ-USD", "NEAR-USD", "FIL-USD", "BAT-USD", "DASH-USD", "ZEC-USD",
         "EOS-USD", "MANA-USD", "SAND-USD", "GRT6719-USD", "CRV-USD", "SNX-USD", "ICP-USD", "INJ-USD",
         "HBAR-USD", "VET-USD", "QNT-USD", "KSM-USD"]
VARIANTEN = {
    "K0": dict(atr_max=0.06, a0=1.5, ac=3.0, max_ht=60, regime=False),
    "K1": dict(atr_max=None, a0=1.5, ac=3.0, max_ht=60, regime=False),
    "K2": dict(atr_max=None, a0=1.5, ac=3.0, max_ht=60, regime=True),
    "K3": dict(atr_max=None, a0=1.5, ac=3.0, max_ht=None, regime=True),
    "K4": dict(atr_max=None, a0=2.5, ac=4.0, max_ht=None, regime=True),
}


# ------------------------------------------------------------------ Daten
def laden(cache: Path) -> dict[str, pd.DataFrame]:
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    import yfinance as yf
    data = {}
    for s in COINS:
        for versuch in range(3):
            try:
                d = yf.download(s, start="2014-01-01", auto_adjust=True, progress=False)
                if isinstance(d.columns, pd.MultiIndex):
                    d.columns = d.columns.get_level_values(0)
                d = d[["Open", "High", "Low", "Close"]].dropna()
                d = d[(d > 0).all(axis=1)]
                d.index = pd.DatetimeIndex(d.index).tz_localize(None)
                d = d[~d.index.duplicated()].asfreq("D").ffill()
                if len(d) > 400:
                    data[s] = d
                break
            except Exception as e:  # noqa: BLE001
                print("Fehler", s, e, flush=True)
                time.sleep(3)
        time.sleep(1)
    print("Coins geladen:", len(data), sorted(data), flush=True)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(pickle.dumps(data))
    return data


def ind(d: pd.DataFrame, btc_ok: pd.Series) -> dict:
    c = d.Close
    pc = c.shift()
    tr = pd.concat([d.High - d.Low, (d.High - pc).abs(), (d.Low - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    e20, e50, e200 = (c.ewm(span=n, adjust=False).mean() for n in (20, 50, 200))
    kreuz = (e20 > e50) & ~(e20.shift() > e50.shift())
    regime = (c > e200) & (e50 > e200)
    reg_btc = btc_ok.reindex(d.index).fillna(False).astype(bool)
    alter = np.arange(len(d)) >= 250
    return {"o": d.Open.to_numpy(float), "l": d.Low.to_numpy(float), "c": c.to_numpy(float),
            "atr": atr.to_numpy(float), "atrp": (atr / c).to_numpy(float),
            "kreuz": (kreuz & regime).to_numpy() & alter, "regime": regime.to_numpy() & alter,
            "btc": reg_btc.to_numpy(), "dates": d.index}


def signale(a: dict, v: dict) -> np.ndarray:
    s = a["kreuz"].copy()
    s &= a["atrp"] >= 0.005
    if v["atr_max"]:
        s &= a["atrp"] <= v["atr_max"]
    if v["regime"]:
        s &= a["btc"]
    return s


def regime_tage(a: dict, v: dict) -> np.ndarray:
    s = a["regime"] & (a["atrp"] >= 0.005)
    if v["atr_max"]:
        s &= a["atrp"] <= v["atr_max"]
    if v["regime"]:
        s &= a["btc"]
    return s


# ------------------------------------------------------------------ Teil A
def trade(a: dict, t: int, v: dict):
    o, l, c, atr = a["o"], a["l"], a["c"], a["atr"]
    n = len(c)
    ein = c[t]
    stop = ein - v["a0"] * atr[t]
    risk = ein - stop
    if not (risk > 0 and np.isfinite(risk)):
        return None
    hoch = ein
    j = t
    aus = None
    while True:
        j += 1
        if j >= n:
            return None  # offen am Datenende
        if l[j] <= stop:
            aus = min(o[j], stop)
            break
        hoch = max(hoch, c[j])
        stop = max(stop, hoch - v["ac"] * atr[j])
        if v["max_ht"] and j - t >= v["max_ht"]:
            aus = c[j]
            break
    ret = aus / ein * (1 - KOST) ** 2 - 1
    return ret, ret * ein / risk, j - t, j


def teil_a(A: dict, rng) -> list[str]:
    ende = max(a["dates"][-1] for a in A.values())
    fenster = [("gesamt", "2015-01-01"), ("2018–2021", "2018-01-01", "2021-12-31"),
               ("2022–heute", "2022-01-01"), ("letzte 2 J", str((ende - pd.DateOffset(years=2)).date()))]
    L = ["## Teil A: je Trade gegen Zufall\n",
         "Zufall A = beliebiger Tag im selben Coin und Fenster, Zufall B = beliebiger Tag, an dem Trendregime "
         "(und ggf. BTC-Filter) ohnehin passen; beide mit gleichem Stop und Ausstieg.\n",
         "| Variante | Fenster | Trades | Coins | Treffer | Ø Trade | Ø R | Zufall A Ø R | Zufall B Ø R | Vorsprung A / B | Median Tage | Trades >= 1 J | R-Anteil aus Trades >= 1 J |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, v in VARIANTEN.items():
        T = []
        for s, a in A.items():
            frei = -1
            for t in np.flatnonzero(signale(a, v)):
                if t <= frei:
                    continue
                r = trade(a, int(t), v)
                if r is None:
                    continue
                T.append((s, a["dates"][t], r[0], r[1], r[2]))
                frei = r[3]
        df = pd.DataFrame(T, columns=["sym", "datum", "ret", "R", "tage"])
        for f in fenster:
            ab = pd.Timestamp(f[1])
            bis = pd.Timestamp(f[2]) if len(f) > 2 else ende
            sub = df[(df.datum >= ab) & (df.datum <= bis)]
            if len(sub) < 10:
                continue
            ZA, ZB = [], []
            for s, g in sub.groupby("sym"):
                a = A[s]
                lo = max(250, int(a["dates"].searchsorted(ab)))
                hi = int(a["dates"].searchsorted(bis))
                hi = min(hi, len(a["c"]) - 2)
                if hi <= lo:
                    continue
                kand = np.flatnonzero(regime_tage(a, v))
                kand = kand[(kand >= lo) & (kand < hi)]
                for _ in range(5 * len(g)):
                    r = trade(a, int(rng.integers(lo, hi)), v)
                    if r:
                        ZA.append(r[1])
                    if len(kand):
                        r = trade(a, int(kand[rng.integers(0, len(kand))]), v)
                        if r:
                            ZB.append(r[1])
            za, zb = (float(np.mean(x)) if x else float("nan") for x in (ZA, ZB))
            lang = sub[sub.tage >= 365]
            anteil = lang.R.sum() / sub.R[sub.R > 0].sum() if (sub.R > 0).any() else float("nan")
            L.append(f"| {name} | {f[0]} | {len(sub)} | {sub.sym.nunique()} | {(sub.ret > 0).mean() * 100:.0f} % | "
                     f"{sub.ret.mean() * 100:+.1f} % | {sub.R.mean():+.2f} | {za:+.2f} | {zb:+.2f} | "
                     f"{sub.R.mean() - za:+.2f} / {sub.R.mean() - zb:+.2f} | {sub.tage.median():.0f} | "
                     f"{len(lang)} | {anteil * 100:.0f} % |")
        print(name, len(df), flush=True)
    return L


# ------------------------------------------------------------------ Steuer
class Steuer:
    def __init__(self, satz=STEUER, vortrag=0.0):
        self.satz, self.vortrag = satz, vortrag
        self.jahr: dict[int, float] = {}
        self.gezahlt = 0.0

    def verkauf(self, datum: pd.Timestamp, gewinn: float, halte_tage: int):
        if halte_tage < 365:
            self.jahr[datum.year] = self.jahr.get(datum.year, 0.0) + gewinn

    def jahresende(self, jahr: int) -> float:
        net = self.jahr.get(jahr, 0.0)
        fg = 600.0 if jahr <= 2023 else 1000.0
        if net < 0:
            self.vortrag += -net
            return 0.0
        if net < fg:
            return 0.0
        nutz = min(self.vortrag, net)
        self.vortrag -= nutz
        st = (net - nutz) * self.satz
        self.gezahlt += st
        return st


def kennz(eq: pd.Series) -> dict:
    j = (eq.index[-1] - eq.index[0]).days / 365.25
    return {"end": float(eq.iloc[-1]), "cagr": (eq.iloc[-1] / eq.iloc[0]) ** (1 / j) - 1 if j > 0 else float("nan"),
            "dd": float((eq / eq.cummax() - 1).min())}


# ------------------------------------------------------------------ Teil B
def portfolio(A: dict, v: dict, start: str, kapital=10000.0, r_pct=0.01, budget_r=3.0, max_pos=0.30):
    tage = pd.date_range(start, max(a["dates"][-1] for a in A.values()), freq="D")
    pos: dict[str, dict] = {}
    cash = kapital
    st = Steuer()
    eq, invest = [], []
    trades = 0
    idx = {s: {d: i for i, d in enumerate(a["dates"])} for s, a in A.items()}
    sig = {s: signale(a, v) for s, a in A.items()}
    for d in tage:
        # 1. offene Positionen
        for s in list(pos):
            i = idx[s].get(d)
            if i is None:
                continue
            a, p = A[s], pos[s]
            if i <= p["i0"]:
                continue
            aus = None
            if a["l"][i] <= p["stop"]:
                aus = min(a["o"][i], p["stop"])
            else:
                p["hoch"] = max(p["hoch"], a["c"][i])
                p["stop"] = max(p["stop"], p["hoch"] - v["ac"] * a["atr"][i])
                if v["max_ht"] and i - p["i0"] >= v["max_ht"]:
                    aus = a["c"][i]
            if aus is not None:
                erloes = p["stk"] * aus * (1 - KOST)
                cash += erloes
                st.verkauf(d, erloes - p["kosten"], (d - p["datum"]).days)
                del pos[s]
        # 2. Wert
        wert = cash
        for s, p in pos.items():
            i = idx[s].get(d)
            px = A[s]["c"][i] if i is not None else p["ein"]
            wert += p["stk"] * px
        # 3. neue Signale (Schluss heute)
        kand = []
        for s, a in A.items():
            i = idx[s].get(d)
            if i is not None and s not in pos and sig[s][i]:
                kand.append((a["atrp"][i], s, i))
        kand.sort()
        for _, s, i in kand:
            offen = sum(min(1.0, max(0.0, (p["ein"] - p["stop"]) / p["risk"])) for p in pos.values())
            if budget_r - offen < 1.0 - 1e-9:
                break
            a = A[s]
            ein = a["c"][i]
            stop = ein - v["a0"] * a["atr"][i]
            risk = ein - stop
            if risk <= 0:
                continue
            stk = r_pct * wert / risk
            stk = min(stk, max_pos * wert / ein, cash / (ein * (1 + KOST)))
            if stk * ein < 50:
                continue
            kosten = stk * ein * (1 + KOST)
            cash -= kosten
            pos[s] = {"stk": stk, "ein": ein, "stop": stop, "risk": risk, "hoch": ein, "i0": i,
                      "datum": d, "kosten": kosten}
            trades += 1
        # 4. Jahresende Steuer
        if d.month == 12 and d.day == 31:
            cash -= st.jahresende(d.year)
        wert = cash + sum(p["stk"] * (A[s]["c"][idx[s][d]] if d in idx[s] else p["ein"]) for s, p in pos.items())
        eq.append(wert)
        invest.append(1 - cash / wert if wert > 0 else 0)
    # Steuer fuer das laufende Jahr nicht faellig gestellt; offene Positionen zum Marktwert
    s_eq = pd.Series(eq, index=tage)
    return s_eq, {"trades": trades, "steuer": st.gezahlt, "invest": float(np.mean(invest)),
                  "vortrag": st.vortrag, "offen_jahr": st.jahr.get(tage[-1].year, 0.0)}


def trend(c: pd.Series, start: str, kapital: float, n=200):
    """Ganz rein, wenn Schluss > SMA200, ganz raus darunter; Handel zum Schluss, mit Steuer."""
    sma = c.rolling(n).mean()
    c = c.loc[start:]
    sma = sma.loc[start:]
    cash, stk, kosten, datum = kapital, 0.0, 0.0, None
    st = Steuer()
    eq = []
    for d, px in c.items():
        drin = px > sma.loc[d]
        if drin and stk == 0:
            stk = cash * (1 - KOST) / px
            kosten, datum, cash = cash, d, 0.0
        elif not drin and stk > 0:
            erloes = stk * px * (1 - KOST)
            st.verkauf(d, erloes - kosten, (d - datum).days)
            cash, stk = erloes, 0.0
        if d.month == 12 and d.day == 31:
            cash -= st.jahresende(d.year)
        eq.append(cash + stk * px)
    return pd.Series(eq, index=c.index), st.gezahlt


def teil_b(A: dict, D: dict) -> list[str]:
    L = ["\n## Teil B: Portfolio mit frischem Kapital 10.000 (nach Steuer, Annahme 35 %)\n",
         "R = 1 % des aktuellen Kapitals, Risikobudget 3 R, hoechstens 30 % je Position. Steuer auf Gewinne "
         "aus Verkaeufen unter 1 Jahr, Freigrenze, Verlustvortrag; Steuer des laufenden Jahres noch nicht abgezogen. "
         "Halten: keine Steuer, solange nicht verkauft (nach 1 Jahr steuerfrei).\n"]
    btc = D["BTC-USD"].Close
    eth = D["ETH-USD"].Close
    for start in ("2018-01-01", "2020-01-01", "2022-01-01", "2024-01-01"):
        L.append(f"### Start {start}\n")
        L.append("| Strategie | Endkapital | CAGR | MaxDD | Trades | Ø investiert | Steuer gezahlt |")
        L.append("|---|---|---|---|---|---|---|")
        for name, v in VARIANTEN.items():
            for rp in ((0.01, 0.02) if name in ("K3", "K4") else (0.01,)):
                eq, info = portfolio(A, v, start, r_pct=rp)
                m = kennz(eq)
                L.append(f"| {name} (R {rp * 100:.0f} %) | {m['end']:,.0f} | {m['cagr'] * 100:+.1f} % | {m['dd'] * 100:.0f} % | "
                         f"{info['trades']} | {info['invest'] * 100:.0f} % | {info['steuer']:,.0f} |".replace(",", "."))
        b = btc.loc[start:]
        bh = 10000 * (1 - KOST) * b / b.iloc[0]
        m = kennz(bh)
        L.append(f"| BTC halten | {m['end']:,.0f} | {m['cagr'] * 100:+.1f} % | {m['dd'] * 100:.0f} % | 1 | 100 % | 0 |".replace(",", "."))
        e = eth.loc[start:]
        eh = 10000 * (1 - KOST) * e / e.iloc[0]
        m = kennz(eh)
        L.append(f"| ETH halten | {m['end']:,.0f} | {m['cagr'] * 100:+.1f} % | {m['dd'] * 100:.0f} % | 1 | 100 % | 0 |".replace(",", "."))
        t1, s1 = trend(btc, start, 10000)
        m = kennz(t1)
        L.append(f"| BTC-T200 | {m['end']:,.0f} | {m['cagr'] * 100:+.1f} % | {m['dd'] * 100:.0f} % | – | – | {s1:,.0f} |".replace(",", "."))
        ta, sa = trend(btc, start, 5000)
        tb, sb = trend(eth, start, 5000)
        tt = (ta + tb.reindex(ta.index).ffill())
        m = kennz(tt)
        L.append(f"| BTC/ETH-T200 je 50 % | {m['end']:,.0f} | {m['cagr'] * 100:+.1f} % | {m['dd'] * 100:.0f} % | – | – | {sa + sb:,.0f} |".replace(",", "."))
        L.append("")
        print("Start", start, flush=True)
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default="work/krypto_lernspur.pkl")
    ap.add_argument("--out", default="research/krypto_lernspur/out")
    args = ap.parse_args()
    D = laden(Path(args.cache))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    btc = D["BTC-USD"].Close
    btc_ok = btc > btc.rolling(200).mean()
    A = {s: ind(d, btc_ok) for s, d in D.items()}
    rng = np.random.default_rng(SEED)
    ende = max(a["dates"][-1] for a in A.values())
    L = ["# Lern-Spur-Regeln auf Krypto, mit Steuermodell (2026-11-12)\n",
         f"Daten: Yahoo, Tagesbasis in USD, {len(A)} Coins, die es heute noch gibt und die bei Kraken handelbar sind "
         f"(Survivorship-Bias), bis {ende.date()}. Kosten 0,50 % je Seite.\n",
         "Coins: " + ", ".join(f"{s.split('-')[0]} (ab {A[s]['dates'][0].year})" for s in sorted(A)) + "\n",
         "| Variante | Regeln |", "|---|---|",
         "| K0 | LS-2 1:1: EMA20 kreuzt EMA50, Schluss > EMA200, EMA50 > EMA200, ATR% 0,5–6 %, Stop 1,5 ATR, Chandelier 3 ATR, Zeitausstieg 60 Tage |",
         "| K1 | K0 ohne ATR%-Obergrenze |", "| K2 | K1 + BTC ueber SMA200 |",
         "| K3 | K2 ohne Zeitausstieg (nur Chandelier) |", "| K4 | K3 mit Stop 2,5 ATR und Chandelier 4 ATR |", ""]
    L += teil_a(A, rng)
    L += teil_b(A, D)
    # aktuelle Signale
    L.append("## Stand heute\n")
    L.append(f"BTC ueber SMA200: {'ja' if btc_ok.iloc[-1] else 'nein'}. Coins im Trendregime (Schluss > EMA200, EMA50 > EMA200): "
             + (", ".join(s.split('-')[0] for s, a in A.items() if a["regime"][-1]) or "keiner")
             + ". Signale heute (K2): " + (", ".join(s.split('-')[0] for s, a in A.items() if signale(a, VARIANTEN['K2'])[-1]) or "keine")
             + ". Signale der letzten 30 Tage (K2): " + (", ".join(
                 f"{s.split('-')[0]} {a['dates'][i].date()}" for s, a in A.items()
                 for i in np.flatnonzero(signale(a, VARIANTEN['K2'])) if i >= len(a['c']) - 30) or "keine") + ".\n")
    L.append("Grenzen: Survivorship-Bias (tote Coins fehlen), Kurse in USD, Steuermodell vereinfacht "
             "(FIFO je Position, Steuersatz angenommen, Soli/Kirchensteuer nicht), keine Zinsen auf Cash.\n")
    (out / "REPORT.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
