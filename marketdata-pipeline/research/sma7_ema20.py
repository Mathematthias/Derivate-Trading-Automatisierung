"""Backtest SMA7/EMA20-Kreuzung (User-Frage 2026-11-12, reine Messung, keine Regel).

Frage: "Einstieg, wenn EMA20 die SMA7 von unten kreuzt, Ausstieg beim Kreuz in die
andere Richtung." Woertlich heisst das: die langsame EMA20 steigt UEBER die schnelle SMA7
(= SMA7 faellt unter EMA20, ein Schwaeche-Signal). Ueblich gemeint ist meist das
Gegenteil: SMA7 kreuzt EMA20 von unten. Beide werden gemessen.

  K  klassisch: Einstieg, wenn SMA7 ueber EMA20 kreuzt; Ausstieg, wenn sie wieder darunter faellt
  W  woertlich: Einstieg, wenn EMA20 ueber SMA7 kreuzt; Ausstieg, wenn sie wieder darunter faellt

Varianten: ohne / mit Trendfilter (Schluss > EMA200 am Signaltag), ohne / mit
Anfangsstop 1,5 ATR (wie LS-2). Signal am Schluss, Ausfuehrung naechste Eroeffnung.
Kosten 0,10 % je Seite. R = Ergebnis / (1,5 x ATR14 am Signaltag), damit vergleichbar mit
den Backtests vom 2026-11-07 (Frueh-Stack +0,26 R, Zufall +0,21 R).

Zufallsvergleich: je echtem Trade 5 Zufallseinstiege im selben Wert mit gleicher Haltedauer
(und gleichem Stop, wenn die Variante einen hat). Vorsprung = echt minus Zufall.

Grenzen: Universum = heutige Pipeline-Werte (Survivorship-Bias nach oben), Yahoo-Tagesdaten,
Waehrungen nicht umgerechnet, keine Steuern.
"""
from __future__ import annotations

import argparse
import math
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

START = "2007-01-01"
COST = 0.0010
STOP_ATR = 1.5
INDIZES = ["^GSPC", "^NDX", "^GDAXI", "^MDAXI", "^STOXX50E"]
ETFS = ["SPY", "QQQ", "IWM", "EXS1.DE", "URTH", "XLK", "XLF", "XLE", "XLV", "XLI", "XLY",
        "XLP", "XLU", "XLB", "SMH", "GLD", "TLT"]
SEED = 20261112


# ---------------------------------------------------------------- Daten
def universum(cfg: Path) -> list[str]:
    a = yaml.safe_load((cfg / "tickers_tier_a.yaml").read_text())
    ex = set(a.get("ethik_excluded") or [])
    out: list[str] = []
    for k in ("thesen_koerbe", "tech_linse", "nebenwerte_de", "positionen"):
        out += list((a.get(k) or {}).values())
    for t in "bc":
        d = yaml.safe_load((cfg / f"tickers_tier_{t}.yaml").read_text())
        for v in (d.get("categories") or {}).values():
            if isinstance(v, dict):
                out += list(v.values())
            elif isinstance(v, list):
                out += [x if isinstance(x, str) else x.get("ticker") for x in v]
    out = [s for s in dict.fromkeys(out) if s and isinstance(s, str) and s not in ex
           and not s.startswith("^") and "=" not in s and "-EUR" not in s
           and s not in ("4GLD.DE", "XAD5.DE") and s not in ETFS]
    return out


def laden(symbole: list[str], cache: Path) -> dict[str, pd.DataFrame]:
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    import yfinance as yf
    data: dict[str, pd.DataFrame] = {}

    def hole(chunk):
        try:
            df = yf.download(chunk, start=START, auto_adjust=True, group_by="ticker",
                             threads=True, progress=False)
        except Exception as e:  # noqa: BLE001
            print("Download-Fehler", e)
            return
        for s in chunk:
            try:
                d = df[s] if len(chunk) > 1 else df
                if isinstance(d.columns, pd.MultiIndex):
                    d.columns = d.columns.get_level_values(-1)
                d = d[["Open", "High", "Low", "Close"]].dropna()
                d = d[(d.Open > 0) & (d.Close > 0)]
                if len(d) > 400:
                    data[s] = d
            except Exception:  # noqa: BLE001
                pass

    for i in range(0, len(symbole), 40):
        hole(symbole[i:i + 40])
        time.sleep(2)
    fehlend = [s for s in symbole if s not in data]
    for i in range(0, len(fehlend), 15):
        hole(fehlend[i:i + 15])
        time.sleep(3)
    cache.write_bytes(pickle.dumps(data))
    return data


def ind(d: pd.DataFrame) -> dict[str, np.ndarray]:
    c = d.Close
    pc = c.shift()
    tr = pd.concat([d.High - d.Low, (d.High - pc).abs(), (d.Low - pc).abs()], axis=1).max(axis=1)
    return {
        "o": d.Open.to_numpy(float), "h": d.High.to_numpy(float), "l": d.Low.to_numpy(float),
        "c": c.to_numpy(float),
        "sma7": c.rolling(7).mean().to_numpy(float),
        "ema20": c.ewm(span=20, adjust=False).mean().to_numpy(float),
        "ema200": c.ewm(span=200, adjust=False).mean().to_numpy(float),
        "atr": tr.ewm(alpha=1 / 14, adjust=False).mean().to_numpy(float),
        "dates": d.index.to_numpy(),
    }


# ---------------------------------------------------------------- Trades
def zustand(a: dict, richtung: str) -> np.ndarray:
    """True, solange die Variante 'drin' sein will (Zustand am Schluss)."""
    if richtung == "K":
        return a["sma7"] > a["ema20"]
    return a["ema20"] > a["sma7"]


def simuliere(o, l, start: int, ende_signal: int, stop: float | None) -> tuple[int, float]:
    """Einstieg Eroeffnung start; regulaerer Ausstieg Eroeffnung ende_signal+1.
    Stop: greift ab dem Einstiegstag am Tief, Fill min(Eroeffnung, Stop)."""
    n = len(o)
    ausstieg_idx = min(ende_signal + 1, n - 1)
    if stop is not None:
        for j in range(start, ausstieg_idx):
            if o[j] <= stop:
                return j, o[j]
            if l[j] <= stop:
                return j, stop
    return ausstieg_idx, o[ausstieg_idx]


def trades_fuer(sym: str, a: dict, richtung: str, filt: bool, mit_stop: bool,
                warmup: int = 220) -> list[dict]:
    z = zustand(a, richtung)
    o, l, c, atr, ema200 = a["o"], a["l"], a["c"], a["atr"], a["ema200"]
    n = len(c)
    out = []
    t = warmup
    while t < n - 2:
        if z[t] and not z[t - 1] and np.isfinite(atr[t]) and atr[t] > 0:
            if filt and not c[t] > ema200[t]:
                t += 1
                continue
            # Ende des Zustands suchen
            e = t + 1
            while e < n - 1 and z[e]:
                e += 1
            # e = erster Schluss ausserhalb; offenes Ende -> letzter Tag
            ein_idx = t + 1
            ein = o[ein_idx]
            stop = c[t] - STOP_ATR * atr[t] if mit_stop else None  # vom Signalschluss wie LS-2
            aus_idx, aus = simuliere(o, l, ein_idx, e, stop)
            ret = aus / ein - 1 - 2 * COST
            risiko = STOP_ATR * atr[t] / ein
            out.append({
                "sym": sym, "datum": pd.Timestamp(a["dates"][t]), "tage": aus_idx - ein_idx,
                "ret": ret, "R": ret / risiko,
                "ein_idx": ein_idx, "dauer": max(e - t, 1),
                "risiko": risiko,
            })
            t = max(aus_idx, t + 1) if mit_stop else e
            continue
        t += 1
    return out


def zufall(trades: list[dict], A: dict[str, dict], mit_stop: bool, ab: str,
           reps: int = 3) -> np.ndarray:
    """Zufallseinstieg im selben Wert und Fenster, geplante Haltedauer wie der echte Trade
    (bis zum Gegenkreuz), mit Stop, wenn die Variante einen hat."""
    rng = np.random.default_rng(SEED)
    res = []
    for tr in trades:
        a = A[tr["sym"]]
        o, l, c, atr = a["o"], a["l"], a["c"], a["atr"]
        n = len(o)
        dauer = tr["dauer"]
        lo = max(221, int(np.searchsorted(a["dates"], np.datetime64(pd.Timestamp(ab)))))
        hi = n - dauer - 2
        if hi <= lo:
            continue
        for _ in range(reps):
            s = int(rng.integers(lo, hi))  # Signaltag
            ein_idx = s + 1
            ein = o[ein_idx]
            stop = c[s] - STOP_ATR * atr[s] if mit_stop else None
            aus_idx, aus = simuliere(o, l, ein_idx, ein_idx + dauer - 1, stop)
            ret = aus / ein - 1 - 2 * COST
            res.append((ret, ret / (STOP_ATR * atr[s] / ein)))
    return np.array(res) if res else np.zeros((0, 2))


_DRIN: dict = {}


def zufall_ausstieg(trades: list[dict], A: dict[str, dict], richtung: str, filt: bool,
                    mit_stop: bool, ab: str, reps: int = 3) -> np.ndarray:
    """Zufallseinstieg an einem beliebigen Tag, an dem die Variante 'drin' waere (Zustand wahr,
    ggf. Schluss > EMA200), danach GLEICHER Ausstieg (Gegenkreuz, ggf. Stop). Misst, ob das
    Kreuz als Einstiegszeitpunkt etwas bringt."""
    rng = np.random.default_rng(SEED + 1)
    res = []
    for tr in trades:
        s_ = tr["sym"]
        a = A[s_]
        o, l, c, atr = a["o"], a["l"], a["c"], a["atr"]
        n = len(o)
        key = (s_, richtung, filt)
        if key not in _DRIN:
            z = zustand(a, richtung)
            ok = z.copy()
            if filt:
                ok &= c > a["ema200"]
            ok[:221] = False
            ok[n - 3:] = False
            _DRIN[key] = (z, np.flatnonzero(ok))
        z, kand = _DRIN[key]
        lo = int(np.searchsorted(a["dates"], np.datetime64(pd.Timestamp(ab))))
        kand = kand[kand >= lo]
        if len(kand) == 0:
            continue
        for _ in range(reps):
            s = int(kand[rng.integers(0, len(kand))])
            e = s + 1
            while e < n - 1 and z[e]:
                e += 1
            ein_idx = s + 1
            ein = o[ein_idx]
            stop = c[s] - STOP_ATR * atr[s] if mit_stop else None
            aus_idx, aus = simuliere(o, l, ein_idx, e, stop)
            ret = aus / ein - 1 - 2 * COST
            res.append((ret, ret / (STOP_ATR * atr[s] / ein)))
    return np.array(res) if res else np.zeros((0, 2))


# ---------------------------------------------------------------- Kurven (Indizes/ETFs)
def kurve(a: dict, richtung: str | None, filt: bool) -> dict:
    """Taeglich investiert / Cash. richtung None = Kaufen und Halten."""
    o, c = a["o"], a["c"]
    n = len(c)
    w0 = 220
    if richtung is None:
        r = c[w0 + 1:] / c[w0:-1] - 1
        pos = np.ones(len(r), bool)
        wechsel = 0
    else:
        z = zustand(a, richtung)
        if filt:
            # Filter nur beim Einstieg: Zustand beginnt nur, wenn Schluss > EMA200
            drin = np.zeros(n, bool)
            for t in range(1, n):
                if z[t] and not z[t - 1]:
                    drin[t] = c[t] > a["ema200"][t]
                elif z[t]:
                    drin[t] = drin[t - 1]
            z = drin
        # Position am Tag t+1 (Eroeffnung bis Eroeffnung) folgt Zustand am Schluss t.
        # Naeherung in Schlusskursen: Rendite Tag t+1 = c[t+1]/c[t]-1, gehalten, wenn z[t-?]
        # Exakter: Eroeffnung-zu-Eroeffnung.
        oo = o[w0:]
        r_oo = np.r_[oo[1:] / oo[:-1] - 1]
        zz = z[w0 - 1:n - 2]  # Zustand am Vortags-Schluss bestimmt Position ab Eroeffnung
        pos = zz[:len(r_oo)]
        r = np.where(pos, r_oo, 0.0)
        wechsel = int(np.sum(pos[1:] != pos[:-1]))
        # Kosten je Wechsel
        kost = np.zeros(len(r))
        idx = np.where(pos[1:] != pos[:-1])[0] + 1
        kost[idx] = COST
        r = r - kost
    eq = np.cumprod(1 + r)
    jahre = len(r) / 252
    cagr = eq[-1] ** (1 / jahre) - 1 if jahre > 0 else np.nan
    dd = (eq / np.maximum.accumulate(eq) - 1).min()
    return {"cagr": cagr, "maxdd": dd, "quote": float(np.mean(pos)), "wechsel_jahr": wechsel / 2 / jahre,
            "jahre": jahre}


def kurve_fenster(a: dict, ab: str, richtung, filt) -> dict:
    d = pd.DatetimeIndex(a["dates"])
    i0 = max(int(np.searchsorted(d, pd.Timestamp(ab))) - 221, 0)
    b = {k: (v[i0:] if isinstance(v, np.ndarray) else v) for k, v in a.items()}
    return kurve(b, richtung, filt)


# ---------------------------------------------------------------- Bericht
def fmt(x, p=2, pct=False):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "–"
    return f"{x * 100:+.1f} %" if pct else f"{x:+.{p}f}"


def region(s: str) -> str:
    return "US" if "." not in s else "EU"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="config")
    ap.add_argument("--cache", default="work/sma7_cache.pkl")
    ap.add_argument("--out", default="research/out_sma7")
    args = ap.parse_args()
    Path(args.cache).parent.mkdir(parents=True, exist_ok=True)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    aktien = universum(Path(args.cfg))
    data = laden(aktien + INDIZES + ETFS, Path(args.cache))
    A = {s: ind(d) for s, d in data.items()}
    stocks = [s for s in aktien if s in A]
    print(f"Aktien geladen: {len(stocks)} von {len(aktien)}; Indizes/ETFs: "
          f"{sum(s in A for s in INDIZES + ETFS)}")
    letzter = max(pd.Timestamp(a["dates"][-1]) for a in A.values())
    fenster = [("gesamt", "1900-01-01"), ("2018–26", "2018-01-01"),
               ("letzte 5 J", str((letzter - pd.DateOffset(years=5)).date())),
               ("letzte 2 J", str((letzter - pd.DateOffset(years=2)).date()))]

    L = []
    L.append("# Backtest SMA7/EMA20-Kreuzung (2026-11-12)\n")
    L.append(f"Daten: Yahoo, Tagesbasis, {START[:4]} bis {letzter.date()}, {len(stocks)} Aktien aus dem "
             "Pipeline-Universum (heutige Werte, Survivorship-Bias), dazu Indizes und ETFs. "
             "Signal am Schluss, Ausfuehrung naechste Eroeffnung, Kosten 0,10 % je Seite. "
             "R = Ergebnis / (1,5 ATR am Signaltag). Zufall = gleiche geplante Haltedauer (und gleicher Stop) "
             "ab zufaelligem Tag im selben Wert und Fenster, 3 je Trade.\n")
    L.append("- **K klassisch**: SMA7 kreuzt EMA20 von unten (rein), wieder darunter (raus).")
    L.append("- **W woertlich**: EMA20 kreuzt SMA7 von unten (rein), wieder darunter (raus).\n")

    # ---- Aktien: Trades
    L.append("## 1. Aktien, je Trade\n")
    L.append("Zufall A = gleiche geplante Haltedauer ab beliebigem Tag. Zufall B = beliebiger Tag, an dem "
             "die Variante ohnehin 'drin' waere, danach gleicher Ausstieg (Gegenkreuz, ggf. Stop): "
             "misst, ob gerade der Kreuzungstag als Einstieg etwas bringt.\n")
    L.append("| Variante | Fenster | Trades | Ø Tage | Treffer | Ø Trade | Median | Ø R | Zufall A Ø R | Zufall B Ø R | Vorsprung A / B | Gewinnfaktor |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    zusammen = {}
    for richtung in ("K", "W"):
        for filt in (False, True):
            for mit_stop in (False, True):
                name = f"{richtung}{' +EMA200' if filt else ''}{' +Stop 1,5 ATR' if mit_stop else ''}"
                T = []
                for s in stocks:
                    T += trades_fuer(s, A[s], richtung, filt, mit_stop)
                df = pd.DataFrame(T)
                zusammen[name] = df
                for fname, ab in fenster:
                    sub = df[df.datum >= pd.Timestamp(ab)]
                    if sub.empty:
                        continue
                    rec = sub.to_dict("records")
                    zf = zufall(rec, A, mit_stop, ab)
                    zb = zufall_ausstieg(rec, A, richtung, filt, mit_stop, ab)
                    gew = sub.ret[sub.ret > 0].sum()
                    verl = -sub.ret[sub.ret < 0].sum()
                    L.append(
                        f"| {name} | {fname} | {len(sub):,} | {sub.tage.mean():.0f} | "
                        f"{(sub.ret > 0).mean() * 100:.0f} % | {fmt(sub.ret.mean(), pct=True)} | "
                        f"{fmt(sub.ret.median(), pct=True)} | {sub.R.mean():+.2f} | "
                        f"{zf[:, 1].mean():+.2f} | {zb[:, 1].mean():+.2f} | "
                        f"{sub.R.mean() - zf[:, 1].mean():+.2f} / {sub.R.mean() - zb[:, 1].mean():+.2f} | "
                        f"{gew / verl if verl > 0 else float('nan'):.2f} |".replace(",", "."))
                    print(name, fname, len(sub), flush=True)
    L.append("")

    # ---- Region
    L.append("## 2. Aktien nach Region (Variante K, ohne Stop, gesamt)\n")
    L.append("| Region | Trades | Treffer | Ø Trade | Ø R |")
    L.append("|---|---|---|---|---|")
    df = zusammen["K"]
    df["region"] = df.sym.map(region)
    for rg, sub in df.groupby("region"):
        L.append(f"| {rg} | {len(sub)} | {(sub.ret > 0).mean() * 100:.0f} % | {fmt(sub.ret.mean(), pct=True)} | {sub.R.mean():+.2f} |")
    L.append("")

    # ---- Haltedauer-Verteilung K
    L.append("## 3. Wie sehen die Trades aus? (Variante K, ohne Stop, gesamt)\n")
    df = zusammen["K"]
    bins = [0, 3, 7, 15, 30, 60, 10000]
    labels = ["1–3 T", "4–7 T", "8–15 T", "16–30 T", "31–60 T", "> 60 T"]
    df["klasse"] = pd.cut(df.tage.clip(lower=1), bins=bins, labels=labels)
    L.append("| Haltedauer | Anteil Trades | Treffer | Ø Trade | Summe je 100 Trades (Prozentpunkte) |")
    L.append("|---|---|---|---|---|")
    for k, sub in df.groupby("klasse", observed=True):
        L.append(f"| {k} | {len(sub) / len(df) * 100:.0f} % | {(sub.ret > 0).mean() * 100:.0f} % | "
                 f"{fmt(sub.ret.mean(), pct=True)} | {sub.ret.sum() / len(df) * 100 * 100:+.0f} |")
    L.append(f"\nTrades je Aktie und Jahr: {len(df) / len(stocks) / ((letzter - pd.Timestamp('2008-01-01')).days / 365.25):.1f}\n")

    # ---- Aktien: Strategie gegen Halten
    L.append("## 4. Aktien: Strategie gegen Kaufen und Halten (je Aktie, gleichgewichtet)\n")
    L.append("| Fenster | Variante | Ø CAGR Strategie | Ø CAGR Halten | Anteil Aktien, in denen die Strategie vorn liegt | Ø MaxDD Strategie | Ø MaxDD Halten | Ø investiert |")
    L.append("|---|---|---|---|---|---|---|---|")
    for fname, ab in fenster:
        for richtung, filt in (("K", False), ("K", True), ("W", False)):
            rs, rh = [], []
            for s in stocks:
                d = pd.DatetimeIndex(A[s]["dates"])
                if d[0] > pd.Timestamp(ab) - pd.Timedelta(days=400) and fname != "gesamt":
                    continue
                try:
                    rs.append(kurve_fenster(A[s], ab, richtung, filt))
                    rh.append(kurve_fenster(A[s], ab, None, False))
                except Exception:  # noqa: BLE001
                    pass
            if not rs:
                continue
            cs = np.array([x["cagr"] for x in rs]); ch = np.array([x["cagr"] for x in rh])
            ok = np.isfinite(cs) & np.isfinite(ch)
            L.append(f"| {fname} | {richtung}{' +EMA200' if filt else ''} | {fmt(np.mean(cs[ok]), pct=True)} | "
                     f"{fmt(np.mean(ch[ok]), pct=True)} | {np.mean(cs[ok] > ch[ok]) * 100:.0f} % | "
                     f"{fmt(np.mean([x['maxdd'] for x in rs]), pct=True)} | {fmt(np.mean([x['maxdd'] for x in rh]), pct=True)} | "
                     f"{np.mean([x['quote'] for x in rs]) * 100:.0f} % |")
    L.append("")

    # ---- Indizes / ETFs
    L.append("## 5. Indizes und ETFs (ohne Survivorship-Bias)\n")
    L.append("| Wert | Fenster | Halten CAGR / MaxDD | K CAGR / MaxDD | K +EMA200 | W CAGR / MaxDD | K investiert | K Wechsel/Jahr |")
    L.append("|---|---|---|---|---|---|---|---|")
    for s in INDIZES + ETFS:
        if s not in A:
            continue
        for fname, ab in (fenster[0], fenster[2]):
            h = kurve_fenster(A[s], ab, None, False)
            k = kurve_fenster(A[s], ab, "K", False)
            kf = kurve_fenster(A[s], ab, "K", True)
            w = kurve_fenster(A[s], ab, "W", False)
            L.append(f"| {s} | {fname} | {fmt(h['cagr'], pct=True)} / {fmt(h['maxdd'], pct=True)} | "
                     f"{fmt(k['cagr'], pct=True)} / {fmt(k['maxdd'], pct=True)} | "
                     f"{fmt(kf['cagr'], pct=True)} / {fmt(kf['maxdd'], pct=True)} | "
                     f"{fmt(w['cagr'], pct=True)} / {fmt(w['maxdd'], pct=True)} | {k['quote'] * 100:.0f} % | {k['wechsel_jahr']:.1f} |")
    L.append("")
    L.append("## Grenzen\n")
    L.append("Survivorship-Bias bei Aktien (heutige Pipeline-Werte), Abschnitt 5 ist frei davon. "
             "Keine Steuern, Waehrungen nicht umgerechnet, Spreads pauschal. Signal und Ausfuehrung "
             "auf Tagesbasis; Ausfuehrung zur Eroeffnung des Folgetags.\n")
    (out / "REPORT.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
