"""Lern-Spur LS-1 (Neuaufstellung A+, User-Entscheid 2026-11-07, Variante B).

Regel (eingefroren bis Trade 20, Backtest research/backtest-2026-11-07, S6 Variante A):
  Signal   EMA20 kreuzt EMA50 nach oben, Schluss ueber EMA200, 0,5 % <= ATR% <= 6 %.
  Einstieg naechste Eroeffnung (Direktaktie, EUR- oder USD-Notiz).
  Stop     Einstieg - 1,5 ATR; danach Chandelier: MAX(alter Stop ; hoechster Schluss seit Einstieg - 3 ATR).
  Ausstieg Stop oder nach 60 Handelstagen.
  Groesse  R = 75 EUR, Stueck = R / (1,5 ATR in EUR), hoechstens 2.000 EUR Einsatz, max. 2 Positionen.
  Auswahl  bei mehr Signalen als Plaetzen: niedrigste ATR% zuerst (Auswahl-Test 2026-11-07).

Der Job laeuft nach US-Schluss und schreibt state/lern_spur.json:
  - kandidaten: heutige Signale, gerankt nach config.auswahl, mit Stueckzahl und Stop,
  - positionen: offene Lern-Trades (traegt Claude im Chat ein, wenn der User den Fill meldet),
    mit neuem Chandelier-Stop und Flag, wenn der Stop seit Einstieg beruehrt wurde,
  - sperre: Review faellig (Trade 5/10/15/20) oder Notbremse (kumuliert <= -6 R).
Bei Sperre bleiben Kandidaten sichtbar, gelten aber nicht als Pitch.
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


# ------------------------------------------------------------------ Universum
def universum(cfg_dir: Path, suffixe_eur: list[str]) -> list[str]:
    a = yaml.safe_load((cfg_dir / "tickers_tier_a.yaml").read_text(encoding="utf-8"))
    ex = set(a.get("ethik_excluded") or [])
    out: list[str] = []
    for k in ("thesen_koerbe", "tech_linse", "nebenwerte_de"):
        out += list((a.get(k) or {}).values())
    for t in "bc":
        d = yaml.safe_load((cfg_dir / f"tickers_tier_{t}.yaml").read_text(encoding="utf-8"))
        for v in (d.get("categories") or {}).values():
            if isinstance(v, dict):
                out += list(v.values())
            elif isinstance(v, list):
                out += [x if isinstance(x, str) else x.get("ticker") for x in v]
    ok = []
    for s in dict.fromkeys(out):
        if not s or s in ex or s.startswith("^") or "=" in s or "-EUR" in s:
            continue
        if "." not in s or any(s.endswith(x) for x in suffixe_eur):
            ok.append(s)
    return ok


def waehrung(sym: str) -> str:
    return "USD" if "." not in sym else "EUR"


# ------------------------------------------------------------------ Indikatoren / Signal
def ind(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    for n in (20, 50, 200):
        d[f"ema{n}"] = d.Close.ewm(span=n, adjust=False).mean()
    pc = d.Close.shift()
    tr = pd.concat([d.High - d.Low, (d.High - pc).abs(), (d.Low - pc).abs()], axis=1).max(axis=1)
    d["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    d["atrp"] = d.atr / d.Close
    return d


def signal_heute(d: pd.DataFrame, cfg: dict) -> bool:
    if len(d) < 210:
        return False
    x, y = d.iloc[-1], d.iloc[-2]
    s = cfg["signal"]
    return bool(x.ema20 > x.ema50 and y.ema20 <= y.ema50 and x.Close > x.ema200
                and s["atr_pct_min"] <= x.atrp <= s["atr_pct_max"])


def rangwert(d: pd.DataFrame, feld: str) -> float:
    c = d.Close
    if feld == "mom252":
        return float(c.iloc[-1] / c.iloc[-253] - 1) if len(c) > 252 else float("nan")
    if feld == "mom63":
        return float(c.iloc[-1] / c.iloc[-64] - 1) if len(c) > 63 else float("nan")
    if feld == "atrp":
        return float(d.atrp.iloc[-1])
    if feld == "ext20":
        return float((c.iloc[-1] - d.ema20.iloc[-1]) / d.atr.iloc[-1])
    return float("nan")


def kandidat(sym: str, d: pd.DataFrame, cfg: dict, fx_usd: float) -> dict:
    x = d.iloc[-1]
    kurs_eur = x.Close / fx_usd if waehrung(sym) == "USD" else x.Close
    atr_eur = x.atr / fx_usd if waehrung(sym) == "USD" else x.atr
    risiko_je_stk = cfg["stop_atr"] * atr_eur
    stueck = int(cfg["r_eur"] // risiko_je_stk) if risiko_je_stk > 0 else 0
    deckel = int(cfg.get("max_einsatz_eur", 1e12) // kurs_eur) if kurs_eur > 0 else 0
    stueck = min(stueck, deckel)
    return {"symbol": sym, "waehrung": waehrung(sym), "schluss": round(float(x.Close), 4),
            "r_eur_effektiv": round(stueck * risiko_je_stk, 2),
            "atr": round(float(x.atr), 4), "atr_pct": round(float(x.atrp), 4),
            "stop_vorschlag": round(float(x.Close - cfg["stop_atr"] * x.atr), 4),
            "stueck": stueck, "einsatz_eur": round(stueck * kurs_eur, 2),
            "rang": rangwert(d, cfg["auswahl"]["feld"])}


# ------------------------------------------------------------------ Positionen
def stop_nachziehen(pos: dict, d: pd.DataFrame, cfg: dict) -> dict:
    """Erst pruefen, ob der bisherige Stop seit dem letzten Lauf beruehrt wurde, dann Chandelier
    nachziehen (nie lockern). Pflichtfelder: symbol, einstieg_datum, einstieg_kurs, stop_initial, stop."""
    p = dict(pos)
    seit = d.loc[d.index >= pd.Timestamp(p["einstieg_datum"])]
    if seit.empty:
        return p
    alt = float(p["stop"])
    zuletzt = pd.Timestamp(p.get("geprueft_bis") or p["einstieg_datum"])
    neu_bars = seit.loc[seit.index > zuletzt]
    p["stop_beruehrt"] = bool(p.get("stop_beruehrt")) or bool((neu_bars.Low <= alt).any())
    hoch = max(float(seit.Close.max()), float(p["einstieg_kurs"]))
    p["stop"] = max(alt, round(hoch - cfg["chandelier_atr"] * float(seit.atr.iloc[-1]), 4))   # nie lockern, auch nicht durch Rundung
    p["hoechster_schluss"] = round(hoch, 4)
    p["handelstage"] = int(len(seit) - 1)
    p["zeitausstieg_faellig"] = p["handelstage"] >= cfg["max_ht"]
    risk = float(p["einstieg_kurs"]) - float(p["stop_initial"])
    p["r_offen"] = round((float(seit.Close.iloc[-1]) - float(p["einstieg_kurs"])) / risk, 2) if risk > 0 else None
    p["geprueft_bis"] = seit.index[-1].date().isoformat()
    return p


def sperre(st: dict, cfg: dict) -> Optional[str]:
    zu = st.get("abgeschlossen", [])
    n = len(zu)
    summe = sum(float(t.get("r", 0)) for t in zu)
    if summe <= cfg["notbremse_r"]:
        return f"Notbremse: kumuliert {summe:+.2f} R nach {n} Trades"
    erledigt = {int(k) for k, v in (st.get("reviews") or {}).items() if v}
    for schwelle in cfg["reviews"]:
        if n >= schwelle and schwelle not in erledigt:
            art = "Vollreview" if schwelle == cfg["reviews"][-1] else "Zwischenreview"
            return f"{art} nach Trade {schwelle} faellig"
    return None


# ------------------------------------------------------------------ Ausgabe
def render(st: dict, cfg: dict) -> str:
    L = [f"# Lern-Spur {cfg['version']} — {st['stand']}", ""]
    if st.get("sperre"):
        L += [f"**GESPERRT: {st['sperre']}.** Keine neuen Lern-Trades bis zum Review.", ""]
    pos = st.get("positionen", [])
    if pos:
        L += ["Offene Lern-Trades:", "", "| Symbol | Einstieg | Stop neu | R offen | HT | Hinweis |", "|---|---|---|---|---|---|"]
        for p in pos:
            hinweis = "Stop berührt?" if p.get("stop_beruehrt") else ("Zeitausstieg fällig" if p.get("zeitausstieg_faellig") else "")
            L.append(f"| {p['symbol']} | {p['einstieg_kurs']} ({p['einstieg_datum']}) | {p['stop']} | {p.get('r_offen', '–')} | {p.get('handelstage', '–')} | {hinweis} |")
        L.append("")
    frei = max(0, cfg["max_parallel"] - len(pos))
    k = st.get("kandidaten", [])
    if k:
        L += [f"Signale heute: {len(k)}, freie Plätze: {frei}.", "",
              "| # | Symbol | Schluss | Stop | Stück | Einsatz € | R € | ATR % |", "|---|---|---|---|---|---|---|---|"]
        for i, c in enumerate(k[:max(frei + 2, 3)], 1):
            mark = " ⚡" if i <= frei and not st.get("sperre") else ""
            L.append(f"| {i}{mark} | {c['symbol']} | {c['schluss']} {c['waehrung']} | {c['stop_vorschlag']} | {c['stueck']} | "
                     f"{c['einsatz_eur']:.0f} | {c['r_eur_effektiv']:.0f} | {c['atr_pct'] * 100:.1f} |")
    else:
        L.append("Heute keine Signale.")
    zu = st.get("abgeschlossen", [])
    if zu:
        L += ["", f"Abgeschlossen: {len(zu)} Trades, Summe {sum(float(t.get('r', 0)) for t in zu):+.2f} R."]
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ main
def _lade(symbole: list[str]) -> dict[str, pd.DataFrame]:
    import time
    import yfinance as yf
    out = {}
    for i in range(0, len(symbole), 50):
        chunk = symbole[i:i + 50]
        df = yf.download(chunk, period="15mo", auto_adjust=True, group_by="ticker", progress=False, threads=True)
        for s in chunk:
            try:
                d = (df[s] if len(chunk) > 1 else df)[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
                if len(d) > 210:
                    out[s] = d
            except Exception:
                pass
        time.sleep(1)
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cfg", default="config/lern_spur.yaml")
    ap.add_argument("--cfg-dir", default="config")
    ap.add_argument("--state-dir", default="state")
    ap.add_argument("--md", default=None)
    a = ap.parse_args(argv)
    cfg = yaml.safe_load(Path(a.cfg).read_text(encoding="utf-8"))
    syms = universum(Path(a.cfg_dir), cfg["suffixe_eur"])
    sp = Path(a.state_dir) / "lern_spur.json"
    st = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {
        "version": cfg["version"], "positionen": [], "abgeschlossen": [], "reviews": {}}
    pos_syms = [p["symbol"] for p in st.get("positionen", [])]
    daten = _lade(sorted(set(syms) | set(pos_syms)))
    import yfinance as yf
    fx = yf.download("EURUSD=X", period="5d", progress=False)["Close"].dropna()
    fx_usd = float(np.asarray(fx).ravel()[-1]) if len(fx) else 1.10
    dd = {s: ind(d) for s, d in daten.items()}
    stand = max(d.index[-1] for d in dd.values()).date()
    kand = [kandidat(s, d, cfg, fx_usd) for s, d in dd.items()
            if s in syms and s not in pos_syms and d.index[-1].date() == stand and signal_heute(d, cfg)]
    kand.sort(key=lambda c: (math.isnan(c["rang"]), -c["rang"] if cfg["auswahl"]["absteigend"] else c["rang"]))
    st["positionen"] = [stop_nachziehen(p, dd[p["symbol"]], cfg) if p["symbol"] in dd else p
                        for p in st.get("positionen", [])]
    st["kandidaten"] = kand
    st["sperre"] = sperre(st, cfg)
    st["stand"] = stand.isoformat()
    st["eurusd"] = round(fx_usd, 4)
    st["aktualisiert"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
    sp.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = render(st, cfg)
    if a.md:
        Path(a.md).write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
