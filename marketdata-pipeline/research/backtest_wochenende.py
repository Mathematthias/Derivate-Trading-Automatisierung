"""Mehrjahres-Backtest Wochenende 2026-11-07 (reine Messung, keine Regel).

Fragen:
  S1  Momentum-Rotation Aktien (Top-N nach 12-1-Momentum, monatlich, Trendfilter)
  S2  Momentum-Rotation ETFs (Top-3 nach 3/6/12-Monats-Mittel, Absolutfilter)
  S3  Kapitulations-Rebound Long (Entwurf Wochenend-Agenda Punkt 3, Tagesnaeherung)
  S3b Weit unter EMA200 (-10/-20/-30 %): Vorwaertsrenditen 10/20/60 HT, schnell vs. langsam
  S4  RSI(2)-Baseline (Connors) als bekannte Referenz fuer Kurzfrist-Umkehr
  S5  Trend-Pullback-Naeherung (Stack, Ruecksetzer EMA20/50, 1,5-ATR-Stop) als Gegenprobe zur Live-Spur

Grenzen (stehen auch im Bericht):
  - Universum = heutige Indexmitglieder -> Survivorship-Bias nach oben. Darum wird S1 immer
    gegen das gleichgewichtete Universum gemessen; der Abstand ist die belastbarere Zahl.
  - Tagesdaten, keine 4h-Kerzen, keine Earnings-Termine historisch, keine Kosten ausser
    pauschal 0,10 % je Seite in S1/S2. Waehrungen nicht umgerechnet.
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

START = "2008-01-01"
ETFS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "SMH", "IGV",
        "QQQ", "IWM", "EFA", "EEM", "EWG", "EWJ", "GLD", "TLT", "IEF"]
BENCH = ["SPY", "URTH", "EXS1.DE"]
TECH = {"AMD", "TSM", "AMAT", "LRCX", "KLAC", "IFX.DE", "ORCL", "CRWD", "NOW", "ADBE", "SAP.DE",
        "DELL", "TSLA", "CRM", "ANET", "SNOW", "IBM", "ACN", "ASML", "ASML.AS", "NVDA", "MSFT",
        "GOOGL", "META", "AMZN", "AAPL", "AVGO", "QCOM", "INTC", "MU", "TXN", "ADI", "MRVL", "NXPI",
        "PANW", "FTNT", "ZS", "DDOG", "NET", "CDNS", "SNPS", "INTU", "WDAY", "TEAM", "PLTR", "ADSK",
        "ASM.AS", "BESI.AS", "STMPA.PA", "DSY.PA", "CAP.PA", "AIXA.DE", "WAF.DE", "NBIS", "MDB", "TTD"}
COST = 0.0010


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
    out = [s for s in dict.fromkeys(out) if s and s not in ex and not s.startswith("^")
           and "=" not in s and "-EUR" not in s and s not in ("4GLD.DE", "XAD5.DE")]
    return out


def laden(symbole: list[str], cache: Path) -> dict[str, pd.DataFrame]:
    if cache.exists():
        return pickle.loads(cache.read_bytes())
    import yfinance as yf
    data: dict[str, pd.DataFrame] = {}

    def hole(chunk):
        df = yf.download(chunk, start=START, auto_adjust=True, group_by="ticker",
                         threads=True, progress=False)
        for s in chunk:
            try:
                d = df[s] if len(chunk) > 1 else df
                if isinstance(d.columns, pd.MultiIndex):
                    d.columns = d.columns.get_level_values(-1)
                d = d[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
                if len(d) > 300:
                    data[s] = d
            except Exception:
                pass

    for i in range(0, len(symbole), 40):
        hole(symbole[i:i + 40])
        time.sleep(2)
    fehlend = [s for s in symbole if s not in data]
    for i in range(0, len(fehlend), 20):
        hole(fehlend[i:i + 20])
        time.sleep(3)
    cache.write_bytes(pickle.dumps(data))
    return data


# ---------------------------------------------------------------- Indikatoren
def ind(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    c = d.Close
    for n in (5, 20, 50, 100, 200):
        d[f"ema{n}"] = c.ewm(span=n, adjust=False).mean()
    d["sma5"] = c.rolling(5).mean()
    d["sma200"] = c.rolling(200).mean()
    pc = c.shift()
    tr = pd.concat([d.High - d.Low, (d.High - pc).abs(), (d.Low - pc).abs()], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    delta = c.diff()
    for n in (2, 14):
        up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
        dn = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
        d[f"rsi{n}"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    d["ext20"] = (c - d.ema20) / d.atr
    d["dist200"] = c / d.ema200 - 1
    d["ret30"] = c / c.shift(21) - 1
    d["atrp"] = d.atr / c
    return d


def kennz(r: pd.Series, per_jahr: int = 252) -> dict:
    r = r.dropna()
    if len(r) < 20:
        return {}
    eq = (1 + r).cumprod()
    jahre = len(r) / per_jahr
    cagr = eq.iloc[-1] ** (1 / jahre) - 1
    vol = r.std() * math.sqrt(per_jahr)
    dd = (eq / eq.cummax() - 1).min()
    m = (1 + r).groupby(r.index.to_period("M")).prod() - 1
    return {"CAGR": cagr, "Vol": vol, "Sharpe": cagr / vol if vol else np.nan, "MaxDD": dd,
            "SchlechtesterMonat": m.min(), "Monate_pos": (m > 0).mean(),
            "2022": (1 + r[r.index.year == 2022]).prod() - 1,
            "Letzte12M": (1 + r.iloc[-252:]).prod() - 1}


# ---------------------------------------------------------------- S1/S2 Rotation
def rotation(closes: pd.DataFrame, regime: pd.Series | None, n: int, score: str,
             trendfilter_einzel: bool, absolut: bool, start: str = "2010-01-01") -> tuple[pd.Series, float]:
    closes = closes.ffill(limit=5)
    rets = closes.pct_change(fill_method=None)
    me = closes.index.to_series().groupby(closes.index.to_period("M")).last()
    me = me[me >= start]
    sma200 = closes.rolling(200).mean()
    port = pd.Series(0.0, index=closes.index)
    alt: set[str] = set()
    turns = []
    for i, t in enumerate(me.iloc[:-1]):
        nxt = me.iloc[i + 1]
        row = closes.loc[:t]
        if len(row) < 260:
            continue
        if score == "12-1":
            s = row.iloc[-22] / row.iloc[-253] - 1
        elif score == "52w":
            s = row.iloc[-1] / row.iloc[-252:].max() - 1
        else:
            s = (row.iloc[-1] / row.iloc[-64] + row.iloc[-1] / row.iloc[-127]
                 + row.iloc[-1] / row.iloc[-253]) / 3 - 1
        s = s.dropna()
        if trendfilter_einzel:
            ok = row.iloc[-1] > sma200.loc[t]
            s = s[ok.reindex(s.index).fillna(False)]
        if absolut:
            s = s[s > 0]
        aus = regime is not None and not bool(regime.loc[:t].iloc[-1])
        neu = set() if aus else set(s.sort_values(ascending=False).index[:n])
        tu = len(neu ^ alt) / max(n, 1)
        turns.append(tu)
        seg = rets.loc[t:nxt].iloc[1:]
        if neu:
            pr = seg[list(neu)].fillna(0).mean(axis=1)
        else:
            pr = pd.Series(0.0, index=seg.index)
        if len(pr):
            pr.iloc[0] -= COST * tu
        port.loc[pr.index] = pr
        alt = neu
    port = port.loc[me.iloc[0]:]
    return port, float(np.mean(turns)) if turns else np.nan


# ---------------------------------------------------------------- Trade-Simulation
def sim(d: pd.DataFrame, i: int, entry: float, stop: float, ziel: float | None, max_ht: int) -> tuple[float, int, str]:
    risk = entry - stop
    for k in range(1, max_ht + 1):
        if i + k >= len(d):
            return (d.Close.iloc[-1] - entry) / risk, k, "offen"
        o, h, l = d.Open.iloc[i + k], d.High.iloc[i + k], d.Low.iloc[i + k]
        if l <= stop:
            return (min(o, stop) - entry) / risk, k, "stop"
        if ziel is not None and h >= ziel:
            return (max(o, ziel) - entry) / risk, k, "ziel"
    return (d.Close.iloc[i + max_ht] - entry) / risk, max_ht, "zeit"


def sim_trail(d: pd.DataFrame, i: int, entry: float, stop: float, mult: float = 3.0,
              max_ht: int = 60) -> tuple[float, int]:
    """Chandelier: Stop = max(Anfangsstop, hoechster Schluss seit Entry - mult*ATR)."""
    risk = entry - stop
    hoch = entry
    for k in range(1, max_ht + 1):
        if i + k >= len(d):
            return (d.Close.iloc[-1] - entry) / risk, k
        o, l, c = d.Open.iloc[i + k], d.Low.iloc[i + k], d.Close.iloc[i + k]
        if l <= stop:
            return (min(o, stop) - entry) / risk, k
        hoch = max(hoch, c)
        stop = max(stop, hoch - mult * d.atr.iloc[i + k])
    return (d.Close.iloc[i + max_ht] - entry) / risk, max_ht


def sim_dir(d, i, entry, stop, ziel, max_ht, rich=1):
    """rich=1 Long, -1 Short. Stop zuerst bei gleichem Tag."""
    risk = (entry - stop) * rich
    for k in range(1, max_ht + 1):
        if i + k >= len(d):
            return (d.Close.iloc[-1] - entry) * rich / risk, k
        o, h, l = d.Open.iloc[i + k], d.High.iloc[i + k], d.Low.iloc[i + k]
        if rich == 1:
            if l <= stop:
                return (min(o, stop) - entry) / risk, k
            if ziel is not None and h >= ziel:
                return (max(o, ziel) - entry) / risk, k
        else:
            if h >= stop:
                return (entry - max(o, stop)) / risk, k
            if ziel is not None and l <= ziel:
                return (entry - min(o, ziel)) / risk, k
    return (d.Close.iloc[i + max_ht] - entry) * rich / risk, max_ht


def trail_dir(d, i, entry, stop, mult=3.0, max_ht=60, rich=1):
    risk = (entry - stop) * rich
    ext = entry
    for k in range(1, max_ht + 1):
        if i + k >= len(d):
            return (d.Close.iloc[-1] - entry) * rich / risk, k
        o, h, l, c, a = d.Open.iloc[i + k], d.High.iloc[i + k], d.Low.iloc[i + k], d.Close.iloc[i + k], d.atr.iloc[i + k]
        if rich == 1:
            if l <= stop:
                return (min(o, stop) - entry) / risk, k
            ext = max(ext, c); stop = max(stop, ext - mult * a)
        else:
            if h >= stop:
                return (entry - max(o, stop)) / risk, k
            ext = min(ext, c); stop = min(stop, ext + mult * a)
    return (d.Close.iloc[i + max_ht] - entry) * rich / risk, max_ht


def zufall_dir(dd, rich, modus, anteil=0.03, seed=11):
    """Nullprobe je Richtung: modus 'z13' (Ziel 1,3 R/15 HT), 'tr3', 'tr2' (Chandelier), 'mix' (1/3 z13 + 2/3 tr2)."""
    rng = np.random.default_rng(seed)
    out = []
    for d in dd.values():
        n = len(d)
        for i in rng.choice(np.arange(210, n - 1), size=max(1, int((n - 211) * anteil)), replace=False):
            e, a = d.Close.iloc[i], d.atr.iloc[i]
            if pd.isna(a) or not (0.005 <= a / e <= 0.08):
                continue
            st = e - rich * 1.5 * a
            z13 = sim_dir(d, i, e, st, e + rich * 1.3 * 1.5 * a, 15, rich)[0]
            if modus == "z13":
                out.append(z13)
            elif modus == "tr3":
                out.append(trail_dir(d, i, e, st, 3.0, 60, rich)[0])
            elif modus == "tr2":
                out.append(trail_dir(d, i, e, st, 2.0, 60, rich)[0])
            else:
                out.append(z13 / 3 + 2 / 3 * trail_dir(d, i, e, st, 2.0, 60, rich)[0])
    return pd.Series(out)


def s7_retest(dd):
    """Breakout-Retest Long / Breakdown-Retest Short nach Skill v76 (Tagesnaeherung, ohne 4h)."""
    rows = []
    for s, d in dd.items():
        vol20 = d.Volume.rolling(20).mean().shift()
        hi20 = d.High.rolling(20).max().shift()
        lo20 = d.Low.rolling(20).min().shift()
        for rich in (1, -1):
            if rich == 1:
                bo = (d.Close > hi20) & (d.Volume >= vol20) & (d.ema20 > d.ema50) & (d.ema50 > d.ema200) & (d.rsi14 <= 70)
            else:
                bo = (d.Close < lo20) & (d.Volume >= vol20) & (d.ema20 < d.ema50) & (d.ema50 < d.ema200) & (d.rsi14 >= 30)
            bo = bo & (d.atrp >= 0.005) & (d.atrp <= 0.08)
            frei = 0
            for b in np.flatnonzero(bo.values):
                if b < frei or b < 210 or b >= len(d) - 15:
                    continue
                niveau = hi20.iloc[b] if rich == 1 else lo20.iloc[b]
                rng_h = (hi20.iloc[b] - lo20.iloc[b])
                ein = None
                for r in range(b + 1, min(b + 11, len(d) - 2)):
                    a = d.atr.iloc[r]
                    if (d.Close.iloc[r] - niveau) * rich < 0:      # Fehlausbruch
                        break
                    if rich == 1:
                        im_band = d.Low.iloc[r] <= niveau + 0.75 * a
                    else:
                        im_band = d.High.iloc[r] >= niveau - 0.75 * a
                    if not im_band:
                        continue
                    marke = d.High.iloc[r] if rich == 1 else d.Low.iloc[r]
                    for q in range(r + 1, min(r + 4, len(d) - 1)):  # Stop-Buy binnen 3 HT
                        if (rich == 1 and d.High.iloc[q] >= marke) or (rich == -1 and d.Low.iloc[q] <= marke):
                            o = d.Open.iloc[q]
                            ein = (q, max(o, marke) if rich == 1 else min(o, marke))
                            break
                    break
                if ein is None:
                    frei = b + 1
                    continue
                q, e = ein
                a = d.atr.iloc[q]
                stop = min(e - 1.5 * a, niveau - 0.3 * a) if rich == 1 else max(e + 1.5 * a, niveau + 0.3 * a)
                risk = (e - stop) * rich
                if risk <= 0:
                    frei = q + 1
                    continue
                # Simulation ab Entry-Tag: Entry intraday, daher ab Folgetag pruefen (Naeherung)
                z13 = sim_dir(d, q, e, stop, e + rich * 1.3 * risk, 15, rich)[0]
                mm = max(1.3 * risk, rng_h)
                zmm = sim_dir(d, q, e, stop, e + rich * mm, 25, rich)[0]
                tr2 = trail_dir(d, q, e, stop, 2.0, 60, rich)[0]
                tr3, ht = trail_dir(d, q, e, stop, 3.0, 60, rich)
                rows.append({"Richtung": "Long" if rich == 1 else "Short", "Symbol": s, "Datum": d.index[q],
                             "R_z13": z13, "R_tr3": tr3, "R_tr2": tr2, "R_skill": zmm / 3 + 2 / 3 * tr2,
                             "Regime_ueber200": None, "Tech": s in TECH})
                frei = q + ht + 1
    return pd.DataFrame(rows)


def s8_grinder(dd):
    """Grinder Long nach Skill (Stand 2026-10-22): Stack 20>50>100>200, ATR% <= 2,5, |Kurs-EMA20| <= 2 ATR,
    Tempo |20-HT-Move| / ATR% >= 1, zwei Tage in Folge; Entry Schluss Tag 2, SL 1,5 ATR,
    Trail MAX(SL; EMA20 - 1,25 ATR), Ausstieg bei Stackbruch (Schluss), Horizont 20/40 HT."""
    rows = []
    for s, d in dd.items():
        stack = (d.ema20 > d.ema50) & (d.ema50 > d.ema100) & (d.ema100 > d.ema200)
        tempo = (d.Close / d.Close.shift(20) - 1) / d.atrp
        ok = stack & (d.atrp <= 0.025) & (d.atrp >= 0.005) & ((d.Close - d.ema20).abs() <= 2 * d.atr) & (tempo >= 1.0)
        sig = ok & ok.shift().fillna(False).astype(bool)
        frei = 0
        for j in np.flatnonzero(sig.values):
            if j < frei or j < 210 or j >= len(d) - 2:
                continue
            e, a = d.Close.iloc[j], d.atr.iloc[j]
            res = {}
            for hor in (20, 40):
                stop = e - 1.5 * a
                r = None
                for k in range(1, hor + 1):
                    if j + k >= len(d):
                        r = (d.Close.iloc[-1] - e) / (1.5 * a); break
                    o, l, c = d.Open.iloc[j + k], d.Low.iloc[j + k], d.Close.iloc[j + k]
                    if l <= stop:
                        r = (min(o, stop) - e) / (1.5 * a); break
                    if not stack.iloc[j + k]:
                        r = (c - e) / (1.5 * a); break
                    stop = max(stop, d.ema20.iloc[j + k] - 1.25 * d.atr.iloc[j + k])
                if r is None:
                    r = (d.Close.iloc[j + hor] - e) / (1.5 * a)
                res[f"R_{hor}"] = r
            rows.append({"Symbol": s, "Datum": d.index[j], **res, "Tech": s in TECH})
            frei = j + 20
    return pd.DataFrame(rows)


def s9_momcont(dd):
    """Momentum-Continuation Trigger B: EMA20>50>100 alle steigend, Tief in Zone EMA20..EMA20+3 %, Schluss >= EMA20;
    Einstieg Schluss des naechsten bullischen Tages binnen 3 HT, Stop 1,5 ATR."""
    rows = []
    for s, d in dd.items():
        steig = (d.ema20 > d.ema20.shift(5)) & (d.ema50 > d.ema50.shift(5)) & (d.ema100 > d.ema100.shift(5))
        zone = (d.Low <= d.ema20 * 1.03) & (d.Close >= d.ema20)
        sig = (d.ema20 > d.ema50) & (d.ema50 > d.ema100) & steig & zone & (d.atrp >= 0.005) & (d.atrp <= 0.05)
        frei = 0
        for j in np.flatnonzero(sig.values):
            if j < frei or j < 210:
                continue
            ein = None
            for k in range(1, 4):
                m = j + k
                if m >= len(d) - 1:
                    break
                if d.Close.iloc[m] > d.Open.iloc[m] and d.Close.iloc[m] > d.Close.iloc[m - 1]:
                    ein = m; break
            if ein is None:
                frei = j + 4; continue
            e, a = d.Close.iloc[ein], d.atr.iloc[ein]
            st = e - 1.5 * a
            z13 = sim_dir(d, ein, e, st, e + 1.3 * 1.5 * a, 15, 1)[0]
            tr3, ht = trail_dir(d, ein, e, st, 3.0, 60, 1)
            tr2 = trail_dir(d, ein, e, st, 2.0, 60, 1)[0]
            rows.append({"Symbol": s, "Datum": d.index[ein], "R_z13": z13, "R_tr3": tr3, "R_skill": z13 / 3 + 2 / 3 * tr2})
            frei = ein + 10
    return pd.DataFrame(rows)


def s6_frueh(dd: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Fruehe Stack-Umordnung (User-Idee 2026-11-07, Anlass DB1): drei Ausloeser, Einstieg am Signalschluss."""
    rows = []
    for s, d in dd.items():
        x2050 = (d.ema20 > d.ema50) & (d.ema20.shift() <= d.ema50.shift())
        sig = {
            "A EMA20 kreuzt EMA50, Schluss > EMA200": x2050 & (d.Close > d.ema200),
            "B EMA20 kreuzt EMA50, EMA50 dreht hoch": x2050 & (d.ema50 > d.ema50.shift(5)),
            "C Rueckeroberung EMA50 nach >= 20 HT darunter, EMA20 steigt":
                (d.Close > d.ema50) & ((d.Close < d.ema50).shift().rolling(20).min() == 1)
                & (d.ema20 > d.ema20.shift(3)),
            "D EMA50 kreuzt EMA200 (Golden Cross)": (d.ema50 > d.ema200) & (d.ema50.shift() <= d.ema200.shift()),
            "Spaet: Stack komplett (20>50>100>200) erstmals seit 60 HT":
                (d.ema20 > d.ema50) & (d.ema50 > d.ema100) & (d.ema100 > d.ema200)
                & ~(((d.ema20 > d.ema50) & (d.ema50 > d.ema100) & (d.ema100 > d.ema200)).shift().rolling(60).max().fillna(1).astype(bool)),
        }
        for name, m in sig.items():
            m = m & (d.atrp <= 0.06) & (d.atrp >= 0.005)
            frei = 0
            for j in np.flatnonzero(m.values):
                if j < frei or j < 210 or j >= len(d) - 2:
                    continue
                e, a = d.Close.iloc[j], d.atr.iloc[j]
                stop = e - 1.5 * a
                r_tr, ht = sim_trail(d, j, e, stop, 3.0, 60)
                r13, _, _ = sim(d, j, e, stop, e + 1.3 * (e - stop), 15)
                r20z, _, _ = sim(d, j, e, stop, None, 20)
                vr = d.Volume.iloc[j] / d.Volume.iloc[max(0, j - 20):j].mean() if j >= 20 else np.nan
                rec = {"Signal": name, "Symbol": s, "Datum": d.index[j], "R_trail3": r_tr, "HT_trail": ht,
                       "ATRp": d.atrp.iloc[j], "Mom63": d.Close.iloc[j] / d.Close.iloc[j - 63] - 1,
                       "Mom252": d.Close.iloc[j] / d.Close.iloc[j - 252] - 1 if j >= 252 else np.nan,
                       "VolRatio": vr, "Dist200": d.dist200.iloc[j],
                       "R_1.3": r13, "R_zeit20": r20z, "Ext20": d.ext20.iloc[j], "Tech": s in TECH}
                for h in (20, 60):
                    rec[f"fwd{h}"] = d.Close.iloc[j + h] / e - 1 if j + h < len(d) else np.nan
                rows.append(rec)
                frei = j + 10
    return pd.DataFrame(rows)


def zufall_win(dd, rich, modus, start=None, anteil=0.03, seed=17):
    """Nullprobe im Zeitfenster ab `start` (Chandelier 3 ATR oder Ziel 1,3 R)."""
    rng = np.random.default_rng(seed)
    out = []
    for d in dd.values():
        n = len(d)
        lo = 210 if start is None else max(210, int(d.index.searchsorted(pd.Timestamp(start))))
        if lo >= n - 2:
            continue
        k = max(1, int((n - 1 - lo) * anteil))
        for i in rng.choice(np.arange(lo, n - 1), size=min(k, n - 1 - lo), replace=False):
            e, a = d.Close.iloc[i], d.atr.iloc[i]
            if pd.isna(a) or not (0.005 <= a / e <= 0.08):
                continue
            st = e - rich * 1.5 * a
            out.append(trail_dir(d, i, e, st, 3.0, 60, rich)[0] if modus == "tr3"
                       else sim_dir(d, i, e, st, e + rich * 1.3 * 1.5 * a, 15, rich)[0])
    return pd.Series(out)


def s10_frueh_short(dd):
    rows = []
    for s, d in dd.items():
        x = (d.ema20 < d.ema50) & (d.ema20.shift() >= d.ema50.shift()) & (d.Close < d.ema200) & (d.atrp <= 0.06) & (d.atrp >= 0.005)
        frei = 0
        for j in np.flatnonzero(x.values):
            if j < frei or j < 210 or j >= len(d) - 2:
                continue
            e, a = d.Close.iloc[j], d.atr.iloc[j]
            st = e + 1.5 * a
            rows.append({"Symbol": s, "Datum": d.index[j], "R_tr3": trail_dir(d, j, e, st, 3.0, 60, -1)[0],
                         "R_z13": sim_dir(d, j, e, st, e - 1.3 * 1.5 * a, 15, -1)[0]})
            frei = j + 10
    return pd.DataFrame(rows)


def zufall_regime(dd, rich, modus, regime, ueber, anteil=0.03, seed=13):
    """Nullprobe nur an Tagen mit gegebener Marktlage (SPY ueber/unter SMA200)."""
    rng = np.random.default_rng(seed)
    out = []
    for d in dd.values():
        n = len(d)
        reg = regime.reindex(d.index).ffill().fillna(True).values
        kand = np.array([i for i in range(210, n - 1) if bool(reg[i]) == ueber])
        if not len(kand):
            continue
        for i in rng.choice(kand, size=max(1, int(len(kand) * anteil)), replace=False):
            e, a = d.Close.iloc[i], d.atr.iloc[i]
            if pd.isna(a) or not (0.005 <= a / e <= 0.08):
                continue
            st = e - rich * 1.5 * a
            out.append(trail_dir(d, i, e, st, 3.0, 60, rich)[0] if modus == "tr3"
                       else sim_dir(d, i, e, st, e + rich * 1.3 * 1.5 * a, 15, rich)[0])
    return pd.Series(out)


def s3_rebound(dd: dict[str, pd.DataFrame], regime: pd.Series) -> pd.DataFrame:
    rows = []
    for s, d in dd.items():
        sig = (d.ext20 <= -3) & (d.rsi14 <= 30) & (d.atrp <= 0.08)
        idx = np.flatnonzero(sig.values)
        frei = 0
        for j in idx:
            if j < frei or j < 210:
                continue
            ein = None
            for k in range(0, 6):
                m = j + k
                if m >= len(d) - 1:
                    break
                if d.Close.iloc[m] > d.Open.iloc[m] and d.Close.iloc[m] > d.Close.iloc[m - 1]:
                    ein = m
                    break
            if ein is None:
                frei = j + 6
                continue
            e = d.Close.iloc[ein]
            a = d.atr.iloc[ein]
            tief = d.Low.iloc[max(0, j - 10):ein + 1].min()
            stop = min(e - 1.5 * a, tief - 0.3 * a)
            ziel20 = d.ema20.iloc[ein]
            if ziel20 <= e:
                frei = ein + 1
                continue
            r, ht, wie = sim(d, ein, e, stop, ziel20, 10)
            r200, ht2, wie2 = sim(d, ein, e, stop, max(d.ema200.iloc[ein], ziel20), 60)
            fwd = {f"fwd{h}": d.Close.iloc[ein + h] / e - 1 if ein + h < len(d) else np.nan for h in (5, 10, 20)}
            t = d.index[ein]
            rows.append({"Symbol": s, "Datum": t, "R": r, "HT": ht, "Ausgang": wie,
                         "R_ziel200_60": r200, "Ziel_R": (ziel20 - e) / (e - stop),
                         "Risiko_pct": (e - stop) / e, "Regime_ueber200": bool(regime.asof(t)),
                         "Dist200": d.dist200.iloc[ein], "Ret30": d.ret30.iloc[ein],
                         "Tech": s in TECH, **fwd})
            frei = ein + ht + 1
    return pd.DataFrame(rows)


def s3b_ema200(dd: dict[str, pd.DataFrame], regime: pd.Series) -> pd.DataFrame:
    rows = []
    for s, d in dd.items():
        for schwelle in (-0.10, -0.20, -0.30):
            unter = (d.dist200 <= schwelle).values
            letzte = -999
            for j in np.flatnonzero(unter):
                if j < 210 or j - letzte <= 20:
                    letzte = j
                    continue
                # Ereignis = erster Tag unter der Schwelle nach >= 20 HT darueber
                if unter[j - 20:j].any():
                    letzte = j
                    continue
                letzte = j
                c = d.Close.iloc[j]
                rec = {"Symbol": s, "Datum": d.index[j], "Schwelle": schwelle,
                       "Schnell": d.ret30.iloc[j] <= -0.15, "Regime_ueber200": bool(regime.asof(d.index[j])),
                       "Tech": s in TECH}
                for h in (10, 20, 60):
                    if j + h < len(d):
                        rec[f"fwd{h}"] = d.Close.iloc[j + h] / c - 1
                        w = d.iloc[j + 1:j + h + 1]
                        rec[f"ema20_erreicht{h}"] = bool((w.High >= w.ema20).any())
                        rec[f"ema200_erreicht{h}"] = bool((w.High >= w.ema200).any())
                        rec[f"mae{h}"] = w.Low.min() / c - 1
                rows.append(rec)
    return pd.DataFrame(rows)


def s4_rsi2(dd: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for s, d in dd.items():
        sig = (d.Close > d.sma200) & (d.rsi2 < 10)
        frei = 0
        for j in np.flatnonzero(sig.values):
            if j < frei or j < 210 or j >= len(d) - 1:
                continue
            e = d.Close.iloc[j]
            k = 1
            while j + k < len(d) - 1 and k < 10 and d.Close.iloc[j + k] <= d.sma5.iloc[j + k]:
                k += 1
            x = d.Close.iloc[min(j + k, len(d) - 1)]
            rows.append({"Symbol": s, "Datum": d.index[j], "Ret": x / e - 1, "HT": k, "Tech": s in TECH})
            frei = j + k + 1
    return pd.DataFrame(rows)


def s5_pullback(dd: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for s, d in dd.items():
        stack = (d.ema20 > d.ema50) & (d.ema50 > d.ema200) & (d.ema50 > d.ema50.shift(10))
        rueck = (d.Low <= d.ema20) & (d.Close >= d.ema50) & (d.atrp <= 0.05) & (d.atrp >= 0.005)
        sig = stack & rueck
        frei = 0
        for j in np.flatnonzero(sig.values):
            if j < frei or j < 210:
                continue
            ein = None
            for k in range(1, 4):
                m = j + k
                if m >= len(d) - 1:
                    break
                if d.Close.iloc[m] > d.Open.iloc[m] and d.Close.iloc[m] > d.High.iloc[m - 1]:
                    ein = m
                    break
            if ein is None:
                frei = j + 4
                continue
            e, a = d.Close.iloc[ein], d.atr.iloc[ein]
            stop = e - 1.5 * a
            r13, ht, _ = sim(d, ein, e, stop, e + 1.3 * (e - stop), 15)
            r20, _, _ = sim(d, ein, e, stop, e + 2.0 * (e - stop), 25)
            rz, _, _ = sim(d, ein, e, stop, None, 20)
            rtr, _ = sim_trail(d, ein, e, stop, 3.0, 60)
            rows.append({"Symbol": s, "Datum": d.index[ein], "R_1.3": r13, "R_2.0": r20, "R_zeit20": rz, "R_trail3": rtr,
                         "Ext20": d.ext20.iloc[ein], "Tech": s in TECH})
            frei = ein + ht + 1
    return pd.DataFrame(rows)


def zufall(dd: dict[str, pd.DataFrame], ziel_r: float | None, max_ht: int, anteil: float = 0.03,
           seed: int = 7, trail: bool = False) -> pd.Series:
    """Nullhypothese: Einstieg an zufaelligen Tagen, Stop 1,5 ATR, gleiches Ziel/Horizont."""
    rng = np.random.default_rng(seed)
    out = []
    for d in dd.values():
        n = len(d)
        for i in rng.choice(np.arange(210, n - 1), size=max(1, int((n - 211) * anteil)), replace=False):
            e, a = d.Close.iloc[i], d.atr.iloc[i]
            if pd.isna(a) or not (0.005 <= a / e <= 0.08):
                continue
            stop = e - 1.5 * a
            if trail:
                out.append(sim_trail(d, i, e, stop, 3.0, max_ht)[0])
            else:
                out.append(sim(d, i, e, stop, None if ziel_r is None else e + ziel_r * (e - stop), max_ht)[0])
    return pd.Series(out)


# ---------------------------------------------------------------- Bericht
def rstat(x: pd.Series) -> dict:
    x = x.dropna()
    if not len(x):
        return {"n": 0}
    g, v = x[x > 0].sum(), -x[x < 0].sum()
    return {"n": len(x), "Treffer": (x > 0).mean(), "Ø": x.mean(), "Median": x.median(),
            "Summe": x.sum(), "PF": g / v if v else np.nan}


def tab(df: pd.DataFrame, fmt: dict | None = None) -> str:
    fmt = fmt or {}
    cols = list(df.columns)
    out = ["| " + " | ".join([df.index.name or ""] + cols) + " |", "|" + "---|" * (len(cols) + 1)]
    for i, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            f = fmt.get(c)
            if c == "n" and isinstance(v, (int, float, np.integer, np.floating)) and not pd.isna(v):
                cells.append(f"{int(v)}")
            elif isinstance(v, (float, np.floating)):
                cells.append("" if pd.isna(v) else (f.format(v) if f else f"{v:.2f}"))
            else:
                cells.append(str(v))
        out.append("| " + " | ".join([str(i)] + cells) + " |")
    return "\n".join(out)


def gruppen(df: pd.DataFrame, by, col: str) -> pd.DataFrame:
    g = df.groupby(by)[col].apply(lambda s: pd.Series(rstat(s))).unstack()
    return g


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="config")
    ap.add_argument("--out", default="research/out")
    ap.add_argument("--cache", default="work/bt_cache.pkl")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    Path(a.cache).parent.mkdir(parents=True, exist_ok=True)

    uni = universum(Path(a.cfg))
    raw = laden(uni + ETFS + BENCH, Path(a.cache))
    dd = {s: ind(d) for s, d in raw.items() if s in uni}
    spy = ind(raw["SPY"])
    regime = (spy.Close > spy.sma200)
    L = [f"# Backtest Wochenende 2026-11-07\n",
         f"Daten: Yahoo, Tagesbasis ab {START}, Stand {spy.index[-1].date()}. "
         f"Universum: {len(dd)} von {len(uni)} Aktien geladen (heutige Mitglieder, Survivorship-Bias nach oben). "
         f"Kosten in S1/S2 pauschal {COST:.2%} je Seite, Waehrungen nicht umgerechnet.\n"]

    # S1
    closes = pd.DataFrame({s: d.Close for s, d in dd.items()}).ffill(limit=5)
    us = [s for s in closes if "." not in s]
    eu = [s for s in closes if "." in s]
    res = {}
    for name, cols in (("Alle", list(closes)), ("US", us), ("EU", eu)):
        c = closes[cols].dropna(how="all")
        c = c[c.notna().sum(axis=1) >= 0.5 * c.notna().sum(axis=1).max()]
        ew = c.pct_change().loc["2010-01-01":].mean(axis=1)
        res[f"{name}: gleichgewichtet (Universum)"] = (kennz(ew), np.nan)
        for n in (5, 10, 15):
            for rg in (True, False):
                p, tu = rotation(c, regime if rg else None, n, "12-1", True, False)
                res[f"{name}: Top{n} 12-1{' + SPY>SMA200' if rg else ''}"] = (kennz(p), tu)
    res["SPY Buy&Hold"] = (kennz(raw["SPY"].Close.pct_change().loc["2010-01-01":]), np.nan)
    if "URTH" in raw:
        res["MSCI World (URTH) B&H"] = (kennz(raw["URTH"].Close.pct_change().loc["2012-02-01":]), np.nan)
    t1 = pd.DataFrame({k: {**v[0], "Umschlag/Monat": v[1]} for k, v in res.items()}).T
    t1.index.name = "Variante"
    pct = {c: "{:.1%}" for c in ("CAGR", "Vol", "MaxDD", "SchlechtesterMonat", "Monate_pos", "2022", "Letzte12M", "Umschlag/Monat")}
    L += ["## S1 Momentum-Rotation Aktien (ab 2010)\n", tab(t1, pct), "\n"]
    t1.to_csv(out / "s1_rotation.csv")

    # S2
    res2 = {}
    for lab, liste in (("alle 20", ETFS), ("ohne XLI", [e for e in ETFS if e != "XLI"]),
                       ("ohne XLI+EWG", [e for e in ETFS if e not in ("XLI", "EWG")]),
                       ("ohne XLI+EWG+EWJ", [e for e in ETFS if e not in ("XLI", "EWG", "EWJ")])):
        et = pd.DataFrame({s: raw[s].Close for s in liste if s in raw})
        for n in (3, 4):
            for ab in (True, False):
                p, tu = rotation(et, None, n, "mix", False, ab, start="2008-06-01")
                res2[f"{lab}: Top{n} 3/6/12M{' + absolut>0' if ab else ''}"] = (kennz(p), tu)
    res2["SPY B&H ab 2008-06"] = (kennz(raw["SPY"].Close.pct_change().loc["2008-06-01":]), np.nan)
    t2 = pd.DataFrame({k: {**v[0], "Umschlag/Monat": v[1]} for k, v in res2.items()}).T
    t2.index.name = "Variante"
    L += ["## S2 Momentum-Rotation ETFs (20 US-ETFs, ab 2008)\n", tab(t2, pct), "\n"]
    t2.to_csv(out / "s2_etf.csv")

    # S3
    r3 = s3_rebound(dd, regime)
    r3.to_csv(out / "s3_rebound.csv", index=False)
    rf = {"Treffer": "{:.0%}"}
    if len(r3):
        r3["Jahr"] = r3.Datum.dt.year
        r3["Dist200_Bucket"] = pd.cut(r3.Dist200, [-9, -0.3, -0.2, -0.1, 0, 9],
                                      labels=["< -30%", "-30..-20%", "-20..-10%", "-10..0%", "ueber EMA200"])
        r3["Tempo"] = np.where(r3.Ret30 <= -0.20, "schnell (30T <= -20%)", "langsam")
        L += ["## S3 Kapitulations-Rebound Long (Ziel EMA20, max 10 HT, R brutto)\n",
              "Signal: Ext EMA20 <= -3 ATR, RSI14 <= 30, ATR% <= 8 %; Einstieg Schluss des ersten bullischen Tages "
              "(Schluss > Eroeffnung und > Vortag) binnen 5 HT; Stop MIN(Entry - 1,5 ATR; Serientief - 0,3 ATR). "
              "Gleicher Tag Stop und Ziel = Stop. Keine Earnings-Sperre (historisch nicht verfuegbar).\n",
              tab(pd.DataFrame({"Alle": rstat(r3.R)}).T, rf), "\n",
              "Nach Marktlage (SPY ueber SMA200):\n", tab(gruppen(r3, "Regime_ueber200", "R"), rf), "\n",
              "Nach Abstand zur EMA200:\n", tab(gruppen(r3, "Dist200_Bucket", "R"), rf), "\n",
              "Nach Tempo:\n", tab(gruppen(r3, "Tempo", "R"), rf), "\n",
              "Tech-Werte:\n", tab(gruppen(r3, "Tech", "R"), rf), "\n",
              "Nach Jahr:\n", tab(gruppen(r3, "Jahr", "R"), rf), "\n",
              "Variante Ziel EMA200 (mind. EMA20), max 60 HT:\n", tab(pd.DataFrame({"Alle": rstat(r3.R_ziel200_60)}).T, rf), "\n",
              f"Median Ziel-Abstand {r3.Ziel_R.median():.2f} R, Median Risiko {r3.Risiko_pct.median():.1%} vom Kurs.\n"]

    if len(r3):
        z = zufall(dd, round(float(r3.Ziel_R.median()), 2), 10)
        L += [f"Nullprobe: Zufallseinstieg, Stop 1,5 ATR, Ziel {r3.Ziel_R.median():.2f} R, max 10 HT:\n",
              tab(pd.DataFrame({"Zufall": rstat(z)}).T, rf), "\n"]

    # S3b
    r3b = s3b_ema200(dd, regime)
    r3b.to_csv(out / "s3b_ema200.csv", index=False)
    if len(r3b):
        g = r3b.groupby(["Schwelle", "Schnell"]).agg(
            n=("fwd20", "size"), fwd10=("fwd10", "mean"), fwd20=("fwd20", "mean"), fwd60=("fwd60", "mean"),
            fwd60_med=("fwd60", "median"), pos60=("fwd60", lambda s: (s > 0).mean()),
            ema20_in20=("ema20_erreicht20", "mean"), ema200_in60=("ema200_erreicht60", "mean"), mae60=("mae60", "median"))
        g.index = [f"{int(a*100)}% / {'schnell' if b else 'langsam'}" for a, b in g.index]
        g.index.name = "Schwelle / Tempo"
        # Basis: unbedingte 60-HT-Rendite im Universum
        base = pd.concat([d.Close.shift(-60) / d.Close - 1 for d in dd.values()]).dropna()
        base20 = pd.concat([d.Close.shift(-20) / d.Close - 1 for d in dd.values()]).dropna()
        L += ["## S3b Weit unter EMA200: Vorwaertsrenditen (Ereignis = erster Tag unter Schwelle nach >= 20 HT darueber)\n",
              tab(g, {c: "{:.1%}" for c in g.columns if c != "n"}), "\n",
              f"Vergleich unbedingt (alle Tage, alle Werte): 20 HT Ø {base20.mean():.1%}, 60 HT Ø {base.mean():.1%}, "
              f"60 HT positiv {(base > 0).mean():.0%}.\n"]
        g2 = r3b[r3b.Schwelle == -0.20].groupby("Regime_ueber200").agg(n=("fwd60", "size"), fwd60=("fwd60", "mean"),
                                                                         pos60=("fwd60", lambda s: (s > 0).mean()))
        L += ["-20 % nach Marktlage:\n", tab(g2, {"fwd60": "{:.1%}", "pos60": "{:.0%}"}), "\n"]

    # S4
    r4 = s4_rsi2(dd)
    r4.to_csv(out / "s4_rsi2.csv", index=False)
    if len(r4):
        r4["Periode"] = np.where(r4.Datum.dt.year < 2018, "2009-2017", "2018-2026")
        g = r4.groupby("Periode").Ret.agg(n="size", avg="mean", med="median", hit=lambda s: (s > 0).mean())
        L += ["## S4 RSI(2)-Baseline (Close > SMA200, RSI2 < 10, Ausstieg Close > SMA5, max 10 HT; Rendite je Trade brutto)\n",
              tab(g, {"avg": "{:.2%}", "med": "{:.2%}", "hit": "{:.0%}"}), "\n"]

    # S5
    r5 = s5_pullback(dd)
    r5.to_csv(out / "s5_pullback.csv", index=False)
    if len(r5):
        t5 = pd.DataFrame({"Ziel 1,3 R (15 HT)": rstat(r5["R_1.3"]), "Ziel 2,0 R (25 HT)": rstat(r5["R_2.0"]),
                           "kein Ziel, 20 HT": rstat(r5["R_zeit20"]),
                           "Chandelier 3 ATR, max 60 HT": rstat(r5["R_trail3"])}).T
        r5["Periode"] = np.where(r5.Datum.dt.year < 2018, "2009-2017", "2018-2026")
        L += ["## S5 Trend-Pullback-Naeherung (EMA20>50>200, EMA50 steigt, Tief an EMA20, Schluss >= EMA50, "
              "ATR% <= 5; Einstieg bullischer Tag ueber Vortageshoch binnen 3 HT; Stop 1,5 ATR; R brutto)\n",
              tab(t5, rf), "\n",
              "Nullprobe Zufallseinstieg, gleicher Stop/Ziel:\n",
              tab(pd.DataFrame({"Zufall 1,3 R / 15 HT": rstat(zufall(dd, 1.3, 15)),
                                "Zufall kein Ziel / 20 HT": rstat(zufall(dd, None, 20)),
                                "Zufall Chandelier / 60 HT": rstat(zufall(dd, None, 60, trail=True))}).T, rf), "\n",
              "Nach Periode (Ziel 1,3 R):\n", tab(gruppen(r5, "Periode", "R_1.3"), rf), "\n"]

    # S6
    r6 = s6_frueh(dd)
    r6.to_csv(out / "s6_frueh.csv", index=False)
    if len(r6):
        rows6 = {}
        for name, g in r6.groupby("Signal"):
            for col, lab in (("R_trail3", "Chandelier 3 ATR, max 60 HT"), ("R_1.3", "Ziel 1,3 R, 15 HT"), ("R_zeit20", "kein Ziel, 20 HT")):
                rows6[f"{name} / {lab}"] = {**rstat(g[col]), "fwd60 Ø": g.fwd60.mean()}
        t6 = pd.DataFrame(rows6).T
        t6.index.name = "Signal / Ausstieg"
        zt = zufall(dd, None, 60, trail=True)
        L += ["## S6 Fruehe Stack-Umordnung (User-Idee 2026-11-07, Anlass DB1): Einstieg am Signalschluss, Stop 1,5 ATR, R brutto\n",
              tab(t6, {"Treffer": "{:.0%}", "fwd60 Ø": "{:.1%}"}), "\n",
              "Nullprobe Zufallseinstieg mit gleichem Chandelier-Ausstieg (Vergleich fuer die Chandelier-Zeilen):\n",
              tab(pd.DataFrame({"Zufall Chandelier": rstat(zt)}).T, rf), "\n"]
        r6["Periode"] = np.where(r6.Datum.dt.year < 2018, "2009-2017", "2018-2026")
        g = r6.groupby(["Signal", "Periode"]).R_trail3.mean().unstack()
        g.index.name = "Signal (Chandelier Ø R)"
        L += ["Stabilitaet nach Periode:\n", tab(g), "\n"]

    # S7-S9 alle Skill-Klassen gegen Nullproben
    rf2 = {"Treffer": "{:.0%}"}
    nl = {m: zufall_dir(dd, 1, m) for m in ("z13", "tr3", "mix")}
    ns = {m: zufall_dir(dd, -1, m) for m in ("z13", "tr3", "mix")}
    zeilen = {}
    r7 = s7_retest(dd); r7.to_csv(out / "s7_retest.csv", index=False)
    for rich, nul in (("Long", nl), ("Short", ns)):
        g = r7[r7.Richtung == rich] if len(r7) else r7
        for col, lab, m in (("R_skill", "Skill-Exit (1/3 Measured Move, 2/3 Chandelier 2 ATR)", "mix"),
                            ("R_z13", "Ziel 1,3 R / 15 HT", "z13"), ("R_tr3", "Chandelier 3 ATR", "tr3")):
            if len(g):
                zeilen[f"Breakout-Retest {rich} / {lab}"] = {**rstat(g[col]), "Zufall Ø": nul[m].mean()}
    r9 = s9_momcont(dd); r9.to_csv(out / "s9_momcont.csv", index=False)
    for col, lab, m in (("R_skill", "Skill-Exit (1/3 Ziel 1,3 R, 2/3 Chandelier 2 ATR)", "mix"),
                        ("R_z13", "Ziel 1,3 R / 15 HT", "z13"), ("R_tr3", "Chandelier 3 ATR", "tr3")):
        if len(r9):
            zeilen[f"Momentum-Continuation Long / {lab}"] = {**rstat(r9[col]), "Zufall Ø": nl[m].mean()}
    r8 = s8_grinder(dd); r8.to_csv(out / "s8_grinder.csv", index=False)
    zg = zufall(dd, None, 20)
    for col, lab in (("R_20", "Skill-Trail, Horizont 20 HT"), ("R_40", "Skill-Trail, Horizont 40 HT")):
        if len(r8):
            zeilen[f"Grinder Long / {lab}"] = {**rstat(r8[col]), "Zufall Ø": zg.mean() if col == "R_20" else zufall(dd, None, 40).mean()}
    if len(r5):
        zeilen["Trend-Pullback Long / Ziel 1,3 R / 15 HT"] = {**rstat(r5["R_1.3"]), "Zufall Ø": nl["z13"].mean()}
        zeilen["Trend-Pullback Long / Chandelier 3 ATR"] = {**rstat(r5["R_trail3"]), "Zufall Ø": nl["tr3"].mean()}
    if len(r6):
        g6 = r6[r6.Signal.str.startswith("A ")]
        zeilen["Frueh-Stack A Long / Chandelier 3 ATR"] = {**rstat(g6.R_trail3), "Zufall Ø": nl["tr3"].mean()}
    # Shorts und Marktlage (User 2026-11-07: spaete Bullenphase, Shorts in der Lern-Spur?)
    r10 = s10_frueh_short(dd); r10.to_csv(out / "s10_frueh_short.csv", index=False)
    rz = {}
    for ueber in (True, False):
        lab = "SPY ueber SMA200" if ueber else "SPY unter SMA200"
        nul_s = zufall_regime(dd, -1, "tr3", regime, ueber)
        nul_l = zufall_regime(dd, 1, "tr3", regime, ueber)
        if len(r10):
            g = r10[r10.Datum.map(lambda t: bool(regime.asof(t))) == ueber]
            rz[f"Frueh-Stack Short / {lab}"] = {**rstat(g.R_tr3), "Zufall Ø": nul_s.mean()}
        if len(r7):
            g = r7[(r7.Richtung == "Short") & (r7.Datum.map(lambda t: bool(regime.asof(t))) == ueber)]
            rz[f"Breakdown-Retest Short / {lab}"] = {**rstat(g.R_tr3), "Zufall Ø": nul_s.mean()}
        if len(r6):
            g = r6[r6.Signal.str.startswith("A ") & (r6.Datum.map(lambda t: bool(regime.asof(t))) == ueber)]
            rz[f"Frueh-Stack Long / {lab}"] = {**rstat(g.R_trail3), "Zufall Ø": nul_l.mean()}
    tr = pd.DataFrame(rz).T
    tr["Vorsprung"] = tr["Ø"] - tr["Zufall Ø"]
    tr.index.name = "Klasse / Marktlage (Chandelier 3 ATR)"
    L += ["## Shorts und Marktlage (Chandelier 3 ATR, Nullprobe gleiche Richtung und Marktlage)\n", tab(tr, rf2), "\n"]

    # Auswahlregel fuer die Lern-Spur: an Tagen mit >= 2 Fruehsignalen (A)
    if len(r6):
        g6 = r6[r6.Signal.str.startswith("A ")].copy()
        tage = g6.groupby("Datum").filter(lambda x: len(x) >= 2)
        krit = {"alle Signale (Mittel)": None,
                "niedrigste ATR%": ("ATRp", True), "hoechste ATR%": ("ATRp", False),
                "staerkstes 3M-Momentum": ("Mom63", False), "schwaechstes 3M-Momentum": ("Mom63", True),
                "staerkstes 12M-Momentum": ("Mom252", False),
                "naechst an EMA20 (kleinste Ext20)": ("Ext20", True),
                "hoechstes Volumen-Verhaeltnis": ("VolRatio", False),
                "naechst an EMA200 (kleinster Abstand)": ("Dist200", True)}
        aw = {}
        for lab, k in krit.items():
            if k is None:
                sel = tage
            else:
                col, asc = k
                sel = tage.sort_values(col, ascending=asc).groupby("Datum").head(1)
            st = rstat(sel.R_trail3)
            p1 = sel[sel.Datum.dt.year < 2018].R_trail3.mean()
            p2 = sel[sel.Datum.dt.year >= 2018].R_trail3.mean()
            aw[lab] = {**st, "2009-2017": p1, "2018-2026": p2}
        ta = pd.DataFrame(aw).T
        ta.index.name = "Auswahl (je Tag 1 von >= 2 Signalen)"
        L += [f"## Auswahlregel Lern-Spur: Tage mit mindestens zwei Frueh-Stack-Long-Signalen (n Tage = {tage.Datum.nunique()})\n",
              tab(ta, rf2), "\n"]

    tz = pd.DataFrame(zeilen).T
    tz["Vorsprung"] = tz["Ø"] - tz["Zufall Ø"]
    tz.index.name = "Klasse / Ausstieg"
    L += ["## Uebersicht alle Skill-Klassen gegen Zufallseinstieg mit gleichem Ausstieg (R brutto)\n",
          "Tagesnaeherung: keine 4h-Bestaetigung, keine Earnings-Sperre, keine Kosten. Short-Nullprobe = zufaellige Shorts.\n",
          tab(tz, rf2), "\n"]

    # Zeitfenster (User 2026-11-07: hat sich der Markt in den letzten Jahren veraendert?)
    stand = max(d.index[-1] for d in dd.values())
    fenster = {"gesamt": None, "5 J": stand - pd.DateOffset(years=5), "2 J": stand - pd.DateOffset(years=2)}
    klassen = []
    if len(r6):
        klassen.append(("Frueh-Stack Long", r6[r6.Signal.str.startswith("A ")], "R_trail3", 1))
    if len(r5):
        klassen.append(("Trend-Pullback Long", r5, "R_trail3", 1))
    if len(r7):
        klassen.append(("Breakout-Retest Long", r7[r7.Richtung == "Long"], "R_tr3", 1))
        klassen.append(("Breakdown-Retest Short", r7[r7.Richtung == "Short"], "R_tr3", -1))
    if len(r9):
        klassen.append(("Momentum-Continuation Long", r9, "R_tr3", 1))
    if len(r10):
        klassen.append(("Frueh-Stack Short", r10, "R_tr3", -1))
    nulls = {(rich, f): zufall_win(dd, rich, "tr3", st).mean() for rich in (1, -1) for f, st in fenster.items()}
    fz = {}
    for name, df_, col, rich in klassen:
        row = {}
        for f, st in fenster.items():
            g = df_ if st is None else df_[df_.Datum >= st]
            row[f"n {f}"] = len(g)
            row[f"Ø {f}"] = g[col].mean() if len(g) else np.nan
            row[f"Vorsprung {f}"] = row[f"Ø {f}"] - nulls[(rich, f)]
        fz[name] = row
    fz["Zufall Long"] = {f"Ø {f}": nulls[(1, f)] for f in fenster}
    fz["Zufall Short"] = {f"Ø {f}": nulls[(-1, f)] for f in fenster}
    tf = pd.DataFrame(fz).T
    tf = tf[[c for c in tf.columns if not c.startswith("n ")] + [c for c in tf.columns if c.startswith("n ")]]
    tf.index.name = "Klasse (Chandelier 3 ATR)"
    L += [f"## Zeitfenster: gesamt, letzte 5 Jahre (ab {fenster['5 J'].date()}), letzte 2 Jahre (ab {fenster['2 J'].date()})\n",
          tab(tf), "\n"]

    # 52-Wochen-Hoch-Momentum (George/Hwang 2004) als Aktien-Rotation, mit Fenstern
    res52 = {}
    c_all = closes.dropna(how="all")
    for lab, sc_ in (("52W-Hoch-Naehe Top10", "52w"), ("12-1 Momentum Top10", "12-1")):
        p, tu = rotation(c_all, None, 10, sc_, True, False)
        for f, st in fenster.items():
            res52[f"{lab} / {f}"] = kennz(p if st is None else p.loc[st:])
    ew = c_all.pct_change(fill_method=None).loc["2010-01-01":].mean(axis=1)
    for f, st in fenster.items():
        res52[f"Universum gleichgewichtet / {f}"] = kennz(ew if st is None else ew.loc[st:])
    t52 = pd.DataFrame(res52).T
    t52.index.name = "Variante / Fenster"
    L += ["## 52-Wochen-Hoch-Momentum gegen 12-1-Momentum (Aktien, Survivorship-Bias, nur relativ lesen)\n",
          tab(t52, pct), "\n"]

    (out / "REPORT.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
