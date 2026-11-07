"""Kern-Rotation (Neuaufstellung A+, User-Entscheid 2026-11-07).

Regel (Backtest research/backtest-2026-11-07):
  - Score je ETF = Mittel der Renditen ueber 63/126/252 Handelstage (3/6/12 Monate).
  - Am letzten Handelstag des Monats die Top N nach Score; mit Absolutfilter nur Score > 0,
    ein leerer Platz bleibt Cash. Gleichgewichtet, Kapital / N je Platz.
  - Ausfuehrung am naechsten Handelstag im UCITS-Pendant (config/rotation_kern.yaml).

Der Job laeuft taeglich nach US-Schluss:
  - jeden Tag eine Vorschau (Rangliste, was am Monatsende passieren wuerde),
  - am letzten Handelstag des Monats (oder mit --force) das Signal: neuer Sollbestand,
    Kauf-/Verkaufsliste gegen den bisherigen Sollbestand.
Zustand: state/rotation_kern.json. Der Sollbestand gilt als umgesetzt; ob der User wirklich
gekauft hat, fragt der Morning Check ab.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yaml


# ------------------------------------------------------------------ Kernlogik
def scores(closes: pd.DataFrame, lookbacks: list[int]) -> pd.Series:
    """Score je Spalte am letzten Tag von `closes`; NaN, wenn die Historie nicht reicht."""
    out = {}
    for s in closes.columns:
        c = closes[s].dropna()
        if len(c) <= max(lookbacks):
            out[s] = np.nan
            continue
        out[s] = float(np.mean([c.iloc[-1] / c.iloc[-1 - lb] - 1 for lb in lookbacks]))
    return pd.Series(out, dtype=float)


def auswahl(sc: pd.Series, top_n: int, absolut: bool) -> list[str]:
    s = sc.dropna()
    if absolut:
        s = s[s > 0]
    return list(s.sort_values(ascending=False).index[:top_n])


def ist_monatsletzter(tag: date) -> bool:
    """Letzter Wochentag des Monats (US-Feiertage ignoriert; der Job laeuft nur an Handelstagen mit Daten)."""
    naechster = (pd.Timestamp(tag) + pd.offsets.BDay(1)).date()
    return naechster.month != tag.month


def plan(alt: list[str], neu: list[str], kapital: float, top_n: int, meta: dict) -> list[dict]:
    je = kapital / top_n
    akt = []
    for s in alt:
        if s not in neu:
            akt.append({"aktion": "verkaufen", "signal": s, **meta.get(s, {})})
    for s in neu:
        akt.append({"aktion": "halten" if s in alt else "kaufen", "signal": s,
                    "ziel_eur": round(je, 2), **meta.get(s, {})})
    frei = top_n - len(neu)
    if frei:
        akt.append({"aktion": "cash", "signal": "-", "ziel_eur": round(je * frei, 2),
                    "name": f"{frei} Platz/Plaetze Cash (Absolutfilter)"})
    return akt


def backtest(closes: pd.DataFrame, top_n: int, absolut: bool, lookbacks: list[int],
             kosten: float, start: str = "2008-06-01") -> pd.Series:
    """Tagesrenditen der Regel, Umschichtung am Monatsende (gleiche Logik wie das Live-Signal)."""
    closes = closes.ffill(limit=5)
    rets = closes.pct_change(fill_method=None)
    me = closes.index.to_series().groupby(closes.index.to_period("M")).last()
    me = me[me >= start]
    port = pd.Series(0.0, index=closes.index)
    alt: list[str] = []
    for i, t in enumerate(me.iloc[:-1]):
        neu = auswahl(scores(closes.loc[:t], lookbacks), top_n, absolut)
        umschlag = len(set(neu) ^ set(alt)) / top_n
        seg = rets.loc[t:me.iloc[i + 1]].iloc[1:]
        pr = seg[neu].fillna(0).sum(axis=1) / top_n if neu else pd.Series(0.0, index=seg.index)
        if len(pr):
            pr.iloc[0] -= kosten * umschlag
        port.loc[pr.index] = pr
        alt = neu
    return port.loc[me.iloc[0]:]


def kennzahlen(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 20:
        return {}
    eq = (1 + r).cumprod()
    cagr = eq.iloc[-1] ** (252 / len(r)) - 1
    vol = r.std() * math.sqrt(252)
    return {"CAGR": cagr, "Vol": vol, "MaxDD": float((eq / eq.cummax() - 1).min()),
            "Letzte12M": float((1 + r.iloc[-252:]).prod() - 1)}


# ------------------------------------------------------------------ Ausgabe
def _pct(x: Optional[float]) -> str:
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:+.1f} %".replace(".", ",")


def render(stichtag: date, sc: pd.Series, neu: list[str], aktionen: Optional[list[dict]],
           cfg: dict, meta: dict, signal: bool) -> str:
    L = [f"# Kern-Rotation {stichtag.isoformat()}", ""]
    if signal:
        L += ["**Signal zum Monatsende.** Umsetzung am nächsten Handelstag im UCITS-Pendant.", ""]
        L += ["| Aktion | ETF | ISIN | Ziel € |", "|---|---|---|---|"]
        for a in aktionen or []:
            ziel = f"{a['ziel_eur']:,.0f}".replace(",", ".") if a.get("ziel_eur") else "–"
            L.append(f"| {a['aktion']} | {a.get('name', a['signal'])} ({a['signal']}) | {a.get('isin', '–')} | {ziel} |")
        L.append("")
    else:
        L += [f"Vorschau (kein Monatsende). Stünde heute das Signal an, wären das: "
              f"{', '.join(neu) if neu else 'nur Cash'}.", ""]
    L += ["Rangliste (Score = Mittel der 3/6/12-Monats-Renditen):", "",
          "| # | Signal | ETF | Score |", "|---|---|---|---|"]
    for i, (s, v) in enumerate(sc.sort_values(ascending=False).items(), 1):
        mark = " ◀" if s in neu else ""
        L.append(f"| {i} | {s}{mark} | {meta.get(s, {}).get('name', s)} | {_pct(v)} |")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ Daten / main
def _lade(symbole: list[str], period: str = "2y") -> pd.DataFrame:
    import yfinance as yf
    df = yf.download(symbole, period=period, auto_adjust=True, group_by="ticker", progress=False, threads=True)
    out = {}
    for s in symbole:
        try:
            out[s] = (df[s] if len(symbole) > 1 else df)["Close"].dropna()
        except Exception:
            pass
    return pd.DataFrame(out)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="config/rotation_kern.yaml")
    ap.add_argument("--state-dir", default="state")
    ap.add_argument("--md", default=None)
    ap.add_argument("--force", action="store_true", help="Signal auch ausserhalb des Monatsendes schreiben")
    ap.add_argument("--backtest", action="store_true", help="Historie ab 2008 rechnen und berichten")
    a = ap.parse_args(argv)

    cfg = yaml.safe_load(Path(a.cfg).read_text(encoding="utf-8"))
    meta = {u["signal"]: {k: v for k, v in u.items() if k != "signal"} for u in cfg["universum"]}
    syms = list(meta)
    lb, n, ab = cfg["lookbacks_ht"], cfg["top_n"], cfg["absolutfilter"]

    if a.backtest:
        closes = _lade(syms + [cfg.get("benchmark", "URTH")], period="max")
        r = backtest(closes[syms], n, ab, lb, cfg["kosten_je_seite"])
        k = kennzahlen(r)
        b = kennzahlen(closes[cfg.get("benchmark", "URTH")].pct_change().loc[r.index[0]:])
        print("Regel:", {x: round(y, 4) for x, y in k.items()})
        print("Benchmark:", {x: round(y, 4) for x, y in b.items()})
        return 0

    closes = _lade(syms)
    stichtag = closes.dropna(how="all").index[-1].date()
    sc = scores(closes, lb)
    neu = auswahl(sc, n, ab)
    sp = Path(a.state_dir) / "rotation_kern.json"
    st = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {"bestand": [], "historie": []}
    signal = a.force or ist_monatsletzter(stichtag)
    aktionen = None
    if signal:
        aktionen = plan(st.get("bestand", []), neu, cfg["kapital_eur"], n, meta)
        st["historie"] = (st.get("historie", []) + [{"datum": stichtag.isoformat(), "bestand": neu,
                                                      "erzwungen": bool(a.force and not ist_monatsletzter(stichtag))}])[-36:]
        st["bestand"] = neu
        st["signal"] = {"datum": stichtag.isoformat(), "aktionen": aktionen, "umgesetzt": False}
    st["vorschau"] = {"datum": stichtag.isoformat(), "auswahl": neu,
                      "scores": {s: (None if math.isnan(v) else round(v, 4)) for s, v in sc.items()}}
    st["aktualisiert"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
    sp.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = render(stichtag, sc, neu, aktionen, cfg, meta, signal)
    if a.md:
        Path(a.md).write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
