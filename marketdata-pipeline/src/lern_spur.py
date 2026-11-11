"""Lern-Spur LS-2 (Neuaufstellung A+, User-Entscheide 2026-11-07, vor dem ersten Lern-Trade).

Regel (eingefroren bis Trade 20, Backtest research/backtest-2026-11-07, S6 Variante A,
FILTER_SEITWAERTS.md und LERNSPUR_SLOTS.md):
  Signal   EMA20 kreuzt EMA50 nach oben, Schluss ueber EMA200, EMA50 ueber EMA200 (LS-2),
           0,5 % <= ATR% <= 6 %.
  Einstieg naechste Eroeffnung (Direktaktie, EUR- oder USD-Notiz).
  Stop     Einstieg - 1,5 ATR; danach Chandelier: MAX(alter Stop ; hoechster Schluss seit Einstieg - 3 ATR).
  Ausstieg Stop oder nach 60 Handelstagen.
  Groesse  R = 50 EUR, Stueck = R / (1,5 ATR in EUR), hoechstens 2.000 EUR Einsatz.
  Budget   offenes Risiko bis zum AKTUELLEN Stop <= 3 R (150 EUR), gebundenes Kapital <= 12.000 EUR.
           Eine Position, deren Chandelier-Stop steigt, belegt nur noch ihr Restrisiko; ab Stop >=
           Einstieg belegt sie nichts mehr (LS-2, Simulation LERNSPUR_BUDGET.md).
  Waehrung US-Werte handelt der User in EUR ueber gettex: Stops und Kurse zusaetzlich in EUR zum
           aktuellen EURUSD. Die Regel selbst rechnet in der Heimatwaehrung.
  Schweiz  CHF-Werte (.SW) seit LS-2 erlaubt, hoechstens 1 Position gleichzeitig (User 2026-11-07,
           LERNSPUR_REGIONEN.md: CHF +0,48 R bei n = 437; GBP und Nordics bleiben draussen).
  Veto     Der User darf ein Signal ablehnen. Abgelehnte Signale laufen als Papier-Trade mit
           denselben Regeln weiter (abgelehnt / abgelehnt_abgeschlossen), damit sich messen
           laesst, ob seine Vetos helfen. Sie zaehlen nicht zu den 20 Trades. Start wie ein realer
           Fill: Einstieg Eroeffnung T+1, Stop vom Signalschluss, R auf das geplante Risiko
           (User 2026-11-09, LS2_EINSTIEG_T1.md; Gap > 1 ATR: Papier +1,63 R gegen real +0,54 R).
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
def universum(cfg_dir: Path, suffixe_eur: list[str], weitere: dict | None = None) -> list[str]:
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
        if "." not in s or any(s.endswith(x) for x in suffixe_eur) or any(s.endswith(x) for x in (weitere or {})):
            ok.append(s)
    return ok


WEITERE_WAEHRUNGEN = {".SW": "CHF"}


def waehrung(sym: str) -> str:
    if "." not in sym:
        return "USD"
    for suf, w in WEITERE_WAEHRUNGEN.items():
        if sym.endswith(suf):
            return w
    return "EUR"


def fx_kurs(w: str, fx) -> float:
    """Einheiten Fremdwaehrung je EUR. fx: dict {"USD": .., "CHF": ..} oder (alt) float = EURUSD."""
    if w == "EUR":
        return 1.0
    if isinstance(fx, dict):
        return float(fx.get(w, 1.0))
    return float(fx) if w == "USD" else 1.0


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
    ok = (x.ema20 > x.ema50 and y.ema20 <= y.ema50 and x.Close > x.ema200
          and s["atr_pct_min"] <= x.atrp <= s["atr_pct_max"])
    if s.get("ema50_ueber_ema200"):
        ok = ok and x.ema50 > x.ema200
    return bool(ok)


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
    k = fx_kurs(waehrung(sym), fx_usd)
    kurs_eur = x.Close / k
    atr_eur = x.atr / k
    risiko_je_stk = cfg["stop_atr"] * atr_eur
    stueck = int(cfg["r_eur"] // risiko_je_stk) if risiko_je_stk > 0 else 0
    deckel = int(cfg.get("max_einsatz_eur", 1e12) // kurs_eur) if kurs_eur > 0 else 0
    stueck = min(stueck, deckel)
    return {"symbol": sym, "waehrung": waehrung(sym), "schluss": round(float(x.Close), 4),
            "r_eur_effektiv": round(stueck * risiko_je_stk, 2),
            "atr": round(float(x.atr), 4), "atr_pct": round(float(x.atrp), 4),
            "stop_vorschlag": round(float(x.Close - cfg["stop_atr"] * x.atr), 4),
            "stop_vorschlag_eur": round(float(x.Close - cfg["stop_atr"] * x.atr) / k, 2),
            "schluss_eur": round(float(kurs_eur), 2),
            "stueck": stueck, "einsatz_eur": round(stueck * kurs_eur, 2),
            "ext20_atr": round(rangwert(d, "ext20"), 2),
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
    p["abgesichert"] = float(p["stop"]) >= float(p["einstieg_kurs"])
    return p


def _fx(p: dict, fx_usd) -> float:
    return fx_kurs(p.get("waehrung", waehrung(p.get("symbol", ""))), fx_usd)


def rest_risiko_eur(p: dict, cfg: dict, fx_usd: float) -> float:
    """Offenes Risiko bis zum aktuellen Stop in EUR (0, sobald Stop >= Einstieg)."""
    e, stop = float(p["einstieg_kurs"]), float(p["stop"])
    if stop >= e:
        return 0.0
    if p.get("stueck"):
        return (e - stop) * float(p["stueck"]) / _fx(p, fx_usd)
    anfang = e - float(p.get("stop_initial", stop))
    return cfg["r_eur"] * ((e - stop) / anfang if anfang > 0 else 1.0)


def einsatz_eur(p: dict, cfg: dict, fx_usd: float) -> float:
    if p.get("einsatz_eur"):
        return float(p["einsatz_eur"])
    if p.get("stueck"):
        return float(p["stueck"]) * float(p["einstieg_kurs"]) / _fx(p, fx_usd)
    return float(cfg.get("max_einsatz_eur", 0))


def rest_risiko_r(p: dict) -> float:
    """Restrisiko in R wie im Backtest (slots_risikobudget.rest_am): Abstand Einstieg zu aktuellem
    Stop relativ zum Anfangsrisiko derselben Position, hoechstens 1 R, 0 sobald Stop >= Einstieg.
    Ein Fill ueber dem Signalschluss oder ein Waehrungseffekt macht eine Position in EUR teurer,
    in R zaehlt sie trotzdem 1 (Bugfix 2026-11-11, User: NEM fehlte 1,46 EUR, weil der Job in EUR zaehlte)."""
    e, stop = float(p["einstieg_kurs"]), float(p["stop"])
    if stop >= e:
        return 0.0
    anfang = e - float(p.get("stop_initial", stop))
    return min(1.0, (e - stop) / anfang) if anfang > 0 else 1.0


def budget(pos: list[dict], cfg: dict, fx_usd: float) -> dict:
    """Risikobudget in R (massgeblich, wie der Backtest) plus EUR-Werte zur Information.
    risiko_frei_eur = risiko_frei_r x r_eur, also die freie Kapazitaet in EUR-Gegenwert;
    risiko_offen_eur ist das tatsaechliche Restrisiko in EUR und kann ueber budget_eur liegen."""
    risiko = sum(rest_risiko_eur(p, cfg, fx_usd) for p in pos)
    offen_r = sum(rest_risiko_r(p) for p in pos)
    kapital = sum(einsatz_eur(p, cfg, fx_usd) for p in pos)
    b_r = float(cfg["risiko_budget_r"])
    frei_r = max(0.0, b_r - offen_r)
    return {"budget_r": b_r, "risiko_offen_r": round(offen_r, 2), "risiko_frei_r": round(frei_r, 2),
            "budget_eur": round(b_r * cfg["r_eur"], 2), "risiko_offen_eur": round(risiko, 2),
            "risiko_frei_eur": round(frei_r * cfg["r_eur"], 2),
            "kapital_eur": cfg["kapital_eur"], "kapital_gebunden_eur": round(kapital, 2),
            "kapital_frei_eur": round(max(0.0, cfg["kapital_eur"] - kapital), 2)}


def zuege_markieren(kand: list[dict], bud: dict, pos: list[dict] | None = None, deckel: dict | None = None) -> int:
    """Kandidaten in Rangfolge markieren, solange Risiko- und Kapitalbudget reichen und der
    Waehrungsdeckel (z. B. {"CHF": 1} = hoechstens eine Schweizer Position) nicht voll ist.
    Jeder neue Kandidat belegt 1 R, wie im Backtest (belegt + 1 <= Budget). Ohne Zug traegt der
    Kandidat den Grund in `grund` (Reihenfolge: 0 Stueck, CHF-Deckel, Budget, Kapital)."""
    r_frei, k_frei, n = bud["risiko_frei_r"] + 1e-6, bud["kapital_frei_eur"] + 0.01, 0
    belegt: dict[str, int] = {}
    for p in pos or []:
        w = p.get("waehrung", waehrung(p.get("symbol", "")))
        belegt[w] = belegt.get(w, 0) + 1
    for c in kand:
        w = c.get("waehrung", waehrung(c.get("symbol", "")))
        voll = deckel is not None and w in deckel and belegt.get(w, 0) >= deckel[w]
        grund = ("0 Stueck" if c["stueck"] <= 0 else f"{w}-Deckel" if voll else "Budget" if r_frei < 1.0
                 else "Kapital" if c["einsatz_eur"] > k_frei else None)
        c["zug"] = grund is None
        if grund:
            c["grund"] = grund
        else:
            c.pop("grund", None)
            r_frei -= 1.0; k_frei -= c["einsatz_eur"]; n += 1
            belegt[w] = belegt.get(w, 0) + 1
    return n


def papier_update(p: dict, d: pd.DataFrame, cfg: dict) -> dict:
    """Abgelehntes Signal mit denselben Regeln Tag fuer Tag weiterfuehren (wie der Backtest:
    Stop zuerst, dann Chandelier auf Schlusskurs, Zeitausstieg am Schluss von Tag max_ht).

    Mit signal_datum startet der Papier-Trade wie ein realer Fill: Einstieg zur Eroeffnung des
    Folgetags (fehlt einstieg_kurs, traegt der Job ihn ein), Stop bleibt vom Signalschluss, der
    Einstiegstag zaehlt als Handelstag 0 und sein Tief gilt schon gegen den Stop. R bezieht sich
    auf das geplante Risiko (signal_kurs - stop_initial), weil die Stueckzahl am Signal haengt.
    Eroeffnung schon unter dem Stop: kein Trade, r = 0. Neue Vetos legt der Chat mit Signaltag und
    Signalschluss in einstieg_datum/einstieg_kurs an; sie werden beim ersten Lauf umgesetzt. Bereits
    laufende Eintraege (geprueft_bis gesetzt) bleiben unveraendert."""
    roh = p
    p = dict(p)
    if p.get("ausstieg_datum"):
        return p
    s0 = float(p["stop_initial"])
    if not p.get("signal_datum") and not p.get("geprueft_bis") and not p.get("handelstage"):
        p.update(signal_datum=p["einstieg_datum"], signal_kurs=float(p["einstieg_kurs"]), einstieg_kurs=None)
    if p.get("signal_datum") and p.get("einstieg_kurs") is None:
        t1 = d.loc[d.index > pd.Timestamp(p["signal_datum"])]
        if t1.empty:
            return dict(roh)
        o = float(t1.Open.iloc[0])
        tag = t1.index[0].date().isoformat()
        p.update(einstieg_datum=tag, einstieg_kurs=round(o, 4))
        if o <= s0:
            p.update(ausstieg_datum=tag, ausstieg_kurs=round(o, 4), grund_ausstieg="kein_trade_eroeffnung_unter_stop", r=0.0)
            return p
    e = float(p["einstieg_kurs"])
    risk = float(p.get("signal_kurs", e)) - s0
    stop = float(p.get("stop", s0))
    hoch = float(p.get("hoechster_schluss", e))
    zuletzt = pd.Timestamp(p.get("geprueft_bis") or p.get("signal_datum") or p["einstieg_datum"])
    ht = int(p.get("handelstage", -1 if p.get("signal_datum") else 0))
    for ts, row in d.loc[d.index > zuletzt].iterrows():
        ht += 1
        if row.Low <= stop:
            px = min(float(row.Open), stop)
            p.update(ausstieg_datum=ts.date().isoformat(), ausstieg_kurs=round(px, 4), grund_ausstieg="stop",
                     r=round((px - e) / risk, 2))
            break
        hoch = max(hoch, float(row.Close))
        stop = max(stop, hoch - cfg["chandelier_atr"] * float(row.atr))
        if ht >= cfg["max_ht"]:
            p.update(ausstieg_datum=ts.date().isoformat(), ausstieg_kurs=round(float(row.Close), 4),
                     grund_ausstieg="zeit", r=round((float(row.Close) - e) / risk, 2))
            break
        p["geprueft_bis"] = ts.date().isoformat()
    p.update(stop=math.ceil(stop * 1e4) / 1e4, hoechster_schluss=round(hoch, 4), handelstage=ht)   # Rundung nie lockernd
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
            hinweis = "Stop berührt?" if p.get("stop_beruehrt") else ("Zeitausstieg fällig" if p.get("zeitausstieg_faellig")
                                                                     else ("abgesichert, Platz frei" if p.get("abgesichert") else ""))
            L.append(f"| {p['symbol']} | {p['einstieg_kurs']} ({p['einstieg_datum']}) | {p['stop']} | {p.get('r_offen', '–')} | {p.get('handelstage', '–')} | {hinweis} |")
        L.append("")
    b = st.get("budget") or {}
    k = st.get("kandidaten", [])
    if b:
        L.append(f"Risiko offen {b.get('risiko_offen_r', 0):.2f} von {b.get('budget_r', 0):.0f} R "
                 f"({b['risiko_offen_eur']:.0f} €), Kapital gebunden "
                 f"{b['kapital_gebunden_eur']:.0f} von {b['kapital_eur']:.0f} €.")
    if k:
        n = sum(1 for c in k if c.get("zug"))
        L += [f"Signale heute: {len(k)}, davon im Budget: {n}.", "",
              "| # | Symbol | Schluss | Stop | Stop € (gettex) | Stück | Einsatz € | R € | ATR % |", "|---|---|---|---|---|---|---|---|---|"]
        for i, c in enumerate(k[:max(n + 2, 3)], 1):
            mark = " ⚡" if c.get("zug") and not st.get("sperre") else ""
            L.append(f"| {i}{mark} | {c['symbol']} | {c['schluss']} {c['waehrung']} | {c['stop_vorschlag']} | "
                     f"{c.get('stop_vorschlag_eur', '–')} | {c['stueck']} | "
                     f"{c['einsatz_eur']:.0f} | {c['r_eur_effektiv']:.0f} | {c['atr_pct'] * 100:.1f} |")
    else:
        L.append("Heute keine Signale.")
    zu = st.get("abgeschlossen", [])
    if zu:
        L += ["", f"Abgeschlossen: {len(zu)} Trades, Summe {sum(float(t.get('r', 0)) for t in zu):+.2f} R."]
    ab = st.get("abgelehnt_abgeschlossen", [])
    if st.get("abgelehnt") or ab:
        L += [f"Vetos: {len(st.get('abgelehnt', []))} laufen als Papier-Trade, {len(ab)} abgeschlossen"
              + (f", Summe {sum(float(t.get('r', 0)) for t in ab):+.2f} R." if ab else ".")]
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
    syms = universum(Path(a.cfg_dir), cfg["suffixe_eur"], cfg.get("weitere_suffixe"))
    sp = Path(a.state_dir) / "lern_spur.json"
    st = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {
        "version": cfg["version"], "positionen": [], "abgeschlossen": [], "reviews": {}}
    pos_syms = [p["symbol"] for p in st.get("positionen", []) + st.get("abgelehnt", [])]
    daten = _lade(sorted(set(syms) | set(pos_syms)))
    import yfinance as yf
    fx_usd: dict[str, float] = {}
    for w, tick, ersatz in (("USD", "EURUSD=X", 1.10), ("CHF", "EURCHF=X", 0.94)):
        f = yf.download(tick, period="5d", progress=False)["Close"].dropna()
        fx_usd[w] = float(np.asarray(f).ravel()[-1]) if len(f) else ersatz
    dd = {s: ind(d) for s, d in daten.items()}
    stand = max(d.index[-1] for d in dd.values()).date()
    kand = [kandidat(s, d, cfg, fx_usd) for s, d in dd.items()
            if s in syms and s not in pos_syms and d.index[-1].date() == stand and signal_heute(d, cfg)]
    kand.sort(key=lambda c: (math.isnan(c["rang"]), -c["rang"] if cfg["auswahl"]["absteigend"] else c["rang"]))
    st["positionen"] = [stop_nachziehen(p, dd[p["symbol"]], cfg) if p["symbol"] in dd else p
                        for p in st.get("positionen", [])]
    for p in st["positionen"]:
        w = p.get("waehrung", waehrung(p["symbol"]))
        if w != "EUR":
            p["stop_eur"] = round(float(p["stop"]) / fx_kurs(w, fx_usd), 2)
    lauf, fertig = [], st.get("abgelehnt_abgeschlossen", [])
    for p in st.get("abgelehnt", []):
        q = papier_update(p, dd[p["symbol"]], cfg) if p["symbol"] in dd else p
        (fertig if q.get("ausstieg_datum") else lauf).append(q)
    st["abgelehnt"], st["abgelehnt_abgeschlossen"] = lauf, fertig
    st["budget"] = budget(st["positionen"], cfg, fx_usd)
    st["kandidaten"] = kand
    st["sperre"] = sperre(st, cfg)
    st["anzahl_zuege"] = (zuege_markieren(kand, st["budget"], st["positionen"], cfg.get("max_je_waehrung"))
                          if not st.get("sperre") else 0)
    st["version"] = cfg["version"]          # Regelwerk immer aus der Config, nicht aus dem alten Zustand
    st["stand"] = stand.isoformat()
    st["eurusd"] = round(fx_usd["USD"], 4)
    st["eurchf"] = round(fx_usd["CHF"], 4)
    st["aktualisiert"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
    sp.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = render(st, cfg)
    if a.md:
        Path(a.md).write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
