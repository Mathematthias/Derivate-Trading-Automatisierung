#!/usr/bin/env python3
"""
weggelaufen_papier.py — Papier-Spur „bestaetigt, aber weggelaufen“ (User-Entscheid B, 2026-11-05).

Frage: Wie viel kostet die Regel „Live-Entry nach 4h-Bestaetigung nur innerhalb der Zone“
(L26, v81.1)? Anlass DE 2026-11-04: Tagestief 656,99 in der Zone, bullische 4h-Umkehr bis 676,5 —
die Bestaetigungskerze selbst trug den Kurs 0,56 ATR aus der Zone, ein Entry war nicht mehr zulaessig.
Jede Umkehrkerze, die groesser ist als der Abstand Tief→Zonenkante, schliesst zwangslaeufig ausserhalb.

Messung (L24, kein Geld, Urteil ab n >= 20; Entscheid ueber Weg A beim 20er-Review):
  Signal    aktive Chart-Zeile (trend_pullback, grinder, breakout_retest), Tagestouch der Zone und eine
            geschlossene 4h-Umkehrkerze in Zeilenrichtung (intraday_4h.detect_reverse) am selben Tag,
            deren Schluss AUSSERHALB der Zone liegt (Long: ueber der Oberkante).
  Entry     Schluss dieser 4h-Kerze. Flag, ob er hinter der Entry-Grenze der Zeile liegt.
  Stop L25  SL = MIN(Entry − 1,5 ATR ; TIW − 0,30 ATR) (Short gespiegelt); TIW aus der Zeile (fest oder
            relativ zur EMA, aufgeloest mit Tages-EMAs des Vortags).
  Ziel      TP1 aus der Zeile. Ergebnis R bis TP1 oder Stop (1h-Kerzen, Stop zuerst bei Gleichstand),
            sonst nach 20 Handelstagen zum Schluss. Dazu: Kam der Kurs spaeter noch in die Zone (= die
            strenge Regel haette doch noch gefuellt)? Datum und R ab Zonenkante.
  Zusatz    „ohne Touch“: aktive Zeile, deren TP1 erreicht wurde, ohne dass die Zone je beruehrt wurde
            (Anlass RACE.MI 2026-11-05). Nur gezaehlt, kein R.

Ausgang: state/weggelaufen_papier.csv (Upsert je Symbol+Signaldatum) + Markdown.
Aufruf:
    python src/weggelaufen_papier.py --state-dir state --md out.md [--backfill-days 10] [--date JJJJ-MM-TT]
"""
from __future__ import annotations

import argparse
import csv
import logging
import math
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from intraday_4h import detect_reverse, resample_1h_to_4h
from state_parser import _parse_single_trigger, resolve_relative_zone
from state_yaml import _leg_tiw, load_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("weggelaufen_papier")

KLASSEN = {"trend_pullback", "grinder", "breakout_retest"}
SL_ATR, TIW_PUFFER = 1.5, 0.30
MAX_HT = 20
CSV_NAME = "weggelaufen_papier.csv"
NUM = r"(\d{1,3}(?:\.\d{3})*,\d+|\d+,\d+|\d+(?:\.\d+)?)"
TP1_RE = re.compile(r"\bTP1\s+" + NUM)
GRENZE_RE = re.compile(r"(ueber|über|unter)\s+" + NUM + r"\s*\S{0,4}\s+kein Entry", re.IGNORECASE)

COLUMNS = ["Symbol", "Richtung", "Klasse", "Signal_Datum", "Kerze", "Art", "Zone_UG", "Zone_OG",
           "Tagesextrem", "Entry", "Abstand_Zone_ATR", "Grenze", "Hinter_Grenze", "ATR", "TIW", "SL",
           "R_Einheit", "TP1", "RR_TP1", "Status", "Ergebnis", "R", "Exit_Datum", "MFE_R", "MAE_R",
           "Zone_spaeter", "R_ab_Zone", "Hinweis"]


def _zahl(s: str) -> float:
    s = s.strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return float(s)


def ema(s: pd.Series, n: int) -> float:
    return float(s.ewm(span=n, adjust=False).mean().iloc[-1])


def atr_wilder(d: pd.DataFrame, n: int = 14) -> Optional[float]:
    if d is None or len(d) < n + 1:
        return None
    h, l, c = d["High"].astype(float), d["Low"].astype(float), d["Close"].astype(float)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    v = float(tr.ewm(alpha=1 / n, adjust=False).mean().iloc[-1])
    return v if math.isfinite(v) else None


@dataclass
class Zeile:
    symbol: str
    long: bool
    klasse: str
    text: str
    added: Optional[date]

    @property
    def tp1(self) -> Optional[float]:
        m = TP1_RE.search(self.text)
        return _zahl(m.group(1)) if m else None

    @property
    def grenze(self) -> Optional[float]:
        m = GRENZE_RE.search(self.text)
        return _zahl(m.group(2)) if m else None


def zone_und_tiw(z: Zeile, daily_bis_vortag: pd.DataFrame) -> tuple[Optional[tuple[float, float]], Optional[float], Optional[float]]:
    """(Zone, TIW-Level, ATR) mit EMAs/ATR bis einschliesslich Vortag."""
    c = daily_bis_vortag["Close"].astype(float)
    if len(c) < 30:
        return None, None, None
    emas = {f"EMA{n}": ema(c, n) for n in (20, 50, 100, 200)}
    A = atr_wilder(daily_bis_vortag)
    pt = _parse_single_trigger("A", z.text)
    resolve_relative_zone(pt, emas, A)
    zone = (pt.price_low, pt.price_high) if pt.price_low is not None and pt.price_high is not None else None
    t = _leg_tiw(z.text)
    tiw = None
    if t:
        tiw = t["level"] if t.get("level") is not None else (
            emas.get(t["anker"]) + t.get("off", 0.0) * A if emas.get(t.get("anker")) is not None and A else None)
    return zone, tiw, A


@dataclass
class Fall:
    Symbol: str
    Richtung: str
    Klasse: str
    Signal_Datum: str
    Kerze: str = ""
    Art: str = "weggelaufen"
    Zone_UG: Optional[float] = None
    Zone_OG: Optional[float] = None
    Tagesextrem: Optional[float] = None
    Entry: Optional[float] = None
    Abstand_Zone_ATR: Optional[float] = None
    Grenze: Optional[float] = None
    Hinter_Grenze: str = ""
    ATR: Optional[float] = None
    TIW: Optional[float] = None
    SL: Optional[float] = None
    R_Einheit: Optional[float] = None
    TP1: Optional[float] = None
    RR_TP1: Optional[float] = None
    Status: str = "offen"
    Ergebnis: str = ""
    R: Optional[float] = None
    Exit_Datum: str = ""
    MFE_R: Optional[float] = None
    MAE_R: Optional[float] = None
    Zone_spaeter: str = ""
    R_ab_Zone: Optional[float] = None
    Hinweis: str = ""


def finde_signal(z: Zeile, tag: date, daily: pd.DataFrame, h1: pd.DataFrame) -> Optional[Fall]:
    """Prueft einen Tag auf das Muster Touch + Umkehr + Schluss ausserhalb der Zone."""
    dd = daily[[pd.Timestamp(i).date() < tag for i in daily.index]]
    heute = daily[[pd.Timestamp(i).date() == tag for i in daily.index]]
    if dd.empty or heute.empty:
        return None
    zone, tiw, A = zone_und_tiw(z, dd)
    if not zone or not A or tiw is None:
        return None
    ug, og = zone
    lo, hi = float(heute["Low"].iloc[0]), float(heute["High"].iloc[0])
    beruehrt = lo <= og if z.long else hi >= ug
    if not beruehrt:
        return None
    k4 = resample_1h_to_4h(h1, closed_only=False)
    tage = pd.Series([pd.Timestamp(i).date() for i in k4.index], index=k4.index)
    for i, ts in enumerate(k4.index):
        if tage.iloc[i] != tag:
            continue
        bull, bear, why = detect_reverse(k4.iloc[: i + 1])
        if not (bull if z.long else bear):
            continue
        close = float(k4["Close"].iloc[i])
        draussen = close > og if z.long else close < ug
        if not draussen:
            return None          # Normalfall: Bestaetigung in der Zone — nicht diese Spur
        f = Fall(Symbol=z.symbol, Richtung="LONG" if z.long else "SHORT", Klasse=z.klasse,
                 Signal_Datum=tag.isoformat(), Kerze=str(ts), Zone_UG=round(ug, 4), Zone_OG=round(og, 4),
                 Tagesextrem=round(lo if z.long else hi, 4), Entry=round(close, 4), ATR=round(A, 4),
                 TIW=round(tiw, 4), TP1=z.tp1, Grenze=z.grenze, Hinweis=why or "")
        f.Abstand_Zone_ATR = round(((close - og) if z.long else (ug - close)) / A, 2)
        if z.long:
            sl = min(close - SL_ATR * A, tiw - TIW_PUFFER * A)
        else:
            sl = max(close + SL_ATR * A, tiw + TIW_PUFFER * A)
        f.SL, f.R_Einheit = round(sl, 4), round(abs(close - sl), 4)
        if f.Grenze is not None:
            f.Hinter_Grenze = "ja" if (close > f.Grenze if z.long else close < f.Grenze) else "nein"
        if f.TP1 is not None and f.R_Einheit:
            f.RR_TP1 = round(((f.TP1 - close) if z.long else (close - f.TP1)) / f.R_Einheit, 2)
        return f
    return None


def verfolge(f: Fall, h1: pd.DataFrame, heute: date) -> Fall:
    """Ergebnis auf 1h-Kerzen nach der Signalkerze: Stop zuerst, dann TP1, sonst Zeitstopp."""
    if f.Entry is None or not f.R_Einheit:
        return f
    long = f.Richtung == "LONG"
    start = pd.Timestamp(f.Kerze)
    d = h1[h1.index > start + pd.Timedelta(hours=3, minutes=59)]
    if d.empty:
        return f
    e, r, sl, tp = f.Entry, f.R_Einheit, f.SL, f.TP1
    best = worst = e
    tage_gesehen: list[date] = []
    zone_kante = f.Zone_OG if long else f.Zone_UG
    for ts, b in d.iterrows():
        tg = pd.Timestamp(ts).date()
        if not tage_gesehen or tage_gesehen[-1] != tg:
            tage_gesehen.append(tg)
        bl, bh = float(b["Low"]), float(b["High"])
        best = max(best, bh) if long else min(best, bl)
        worst = min(worst, bl) if long else max(worst, bh)
        if not f.Zone_spaeter and (bl <= zone_kante if long else bh >= zone_kante):
            f.Zone_spaeter = tg.isoformat()
            if tp is not None:
                sl_z = min(zone_kante - SL_ATR * f.ATR, f.TIW - TIW_PUFFER * f.ATR) if long else \
                    max(zone_kante + SL_ATR * f.ATR, f.TIW + TIW_PUFFER * f.ATR)
                f.R_ab_Zone = round(((tp - zone_kante) if long else (zone_kante - tp)) / abs(zone_kante - sl_z), 2)
        if f.Status == "offen":
            if (bl <= sl) if long else (bh >= sl):
                f.Status, f.Ergebnis, f.R, f.Exit_Datum = "zu", "Stop", -1.0, tg.isoformat()
            elif tp is not None and ((bh >= tp) if long else (bl <= tp)):
                f.Status, f.Ergebnis, f.Exit_Datum = "zu", "TP1", tg.isoformat()
                f.R = round(((tp - e) if long else (e - tp)) / r, 2)
            elif len(tage_gesehen) > MAX_HT:
                c = float(b["Close"])
                f.Status, f.Ergebnis, f.Exit_Datum = "zu", "Zeitstopp", tg.isoformat()
                f.R = round(((c - e) if long else (e - c)) / r, 2)
    f.MFE_R = round(((best - e) if long else (e - best)) / r, 2)
    f.MAE_R = round(((e - worst) if long else (worst - e)) / r, 2)
    return f


def ohne_touch(z: Zeile, daily: pd.DataFrame) -> Optional[Fall]:
    """TP1 seit Anlage erreicht, Zone nie beruehrt (Anlass RACE.MI)."""
    if z.tp1 is None or z.added is None:
        return None
    seit = daily[[pd.Timestamp(i).date() >= z.added for i in daily.index]]
    vor = daily[[pd.Timestamp(i).date() < z.added for i in daily.index]]
    if seit.empty or vor.empty:
        return None
    zone, _, A = zone_und_tiw(z, vor)
    if not zone:
        return None
    ug, og = zone
    if z.long:
        touch, tp_hit = (seit["Low"].astype(float) <= og).any(), (seit["High"].astype(float) >= z.tp1).any()
    else:
        touch, tp_hit = (seit["High"].astype(float) >= ug).any(), (seit["Low"].astype(float) <= z.tp1).any()
    if touch or not tp_hit:
        return None
    return Fall(Symbol=z.symbol, Richtung="LONG" if z.long else "SHORT", Klasse=z.klasse,
                Signal_Datum=z.added.isoformat(), Art="ohne Touch", Zone_UG=round(ug, 4), Zone_OG=round(og, 4),
                TP1=z.tp1, Status="zu", Ergebnis="TP1 ohne Zone", Hinweis="Zone nie beruehrt, TP1 erreicht")


def _pence(sym: str, df: pd.DataFrame, ref: Optional[float]) -> pd.DataFrame:
    """LSE-Kurse kommen in Pence; Zeilen fuehren GBP (Pipeline-Konvention market_data .L/100)."""
    if df is None or df.empty or not sym.endswith(".L") or not ref:
        return df
    if float(df["Close"].iloc[-1]) > 20 * ref:
        df = df.copy()
        for k in ("Open", "High", "Low", "Close"):
            df[k] = df[k].astype(float) / 100.0
    return df


def yf_daily(sym: str) -> pd.DataFrame:
    import yfinance as yf
    return yf.Ticker(sym).history(period="2y", interval="1d", auto_adjust=False)


def yf_1h(sym: str) -> pd.DataFrame:
    import yfinance as yf
    return yf.Ticker(sym).history(period="60d", interval="1h", auto_adjust=False)


def zeilen_aus_state(state_dir: str) -> list[Zeile]:
    st = load_state(state_dir)
    out = []
    for w in (st.get("watchlist") or {}).get("entries", []) or []:
        if w.get("status") != "aktiv" or w.get("klasse") not in KLASSEN or not w.get("legs"):
            continue
        try:
            added = date.fromisoformat(str(w.get("added"))[:10])
        except ValueError:
            added = None
        out.append(Zeile(str(w["symbol"]), str(w.get("direction", "LONG")).upper().startswith("L"),
                         str(w.get("klasse")), str(w["legs"][0].get("text", "")), added))
    return out


def upsert(path: Path, faelle: list[Fall]) -> list[dict]:
    alt: dict[tuple[str, str, str], dict] = {}
    if path.exists():
        for r in csv.DictReader(path.open(encoding="utf-8")):
            alt[(r["Symbol"], r["Signal_Datum"], r["Art"])] = r
    for f in faelle:
        alt[(f.Symbol, f.Signal_Datum, f.Art)] = {k: ("" if v is None else v) for k, v in asdict(f).items()}
    rows = sorted(alt.values(), key=lambda r: (r["Signal_Datum"], r["Symbol"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLUMNS})
    return rows


def _fall_aus_row(r: dict) -> Fall:
    f = Fall(Symbol=r["Symbol"], Richtung=r["Richtung"], Klasse=r["Klasse"], Signal_Datum=r["Signal_Datum"])
    for k in COLUMNS:
        v = r.get(k, "")
        cur = getattr(f, k)
        if v == "":
            continue
        if isinstance(cur, str) or k in ("Kerze", "Art", "Hinter_Grenze", "Status", "Ergebnis", "Exit_Datum",
                                         "Zone_spaeter", "Hinweis", "Symbol", "Richtung", "Klasse", "Signal_Datum"):
            setattr(f, k, v)
        else:
            setattr(f, k, float(v))
    return f


def zusammenfassung(rows: list[dict]) -> str:
    w = [r for r in rows if r["Art"] == "weggelaufen"]
    zu = [r for r in w if r["Status"] == "zu" and r["R"] != ""]
    ot = [r for r in rows if r["Art"] == "ohne Touch"]
    rs = [float(r["R"]) for r in zu]
    zs = [float(r["R_ab_Zone"]) for r in w if r["R_ab_Zone"] != ""]

    def m(x):
        return f"{sum(x) / len(x):+.2f} R" if x else "—"

    return "\n".join([
        "# Papier-Spur „bestaetigt, aber weggelaufen“",
        "",
        f"Faelle: {len(w)} (offen {len(w) - len(zu)}, geschlossen {len(zu)}) · Ø R geschlossen {m(rs)} · "
        f"TP1 {sum(1 for r in zu if r['Ergebnis'] == 'TP1')} / Stop {sum(1 for r in zu if r['Ergebnis'] == 'Stop')} / "
        f"Zeitstopp {sum(1 for r in zu if r['Ergebnis'] == 'Zeitstopp')}",
        f"Hinter der Entry-Grenze der Zeile: {sum(1 for r in w if r['Hinter_Grenze'] == 'ja')}",
        f"Kurs kam spaeter doch in die Zone: {sum(1 for r in w if r['Zone_spaeter'])} (dort R:R bis TP1 Ø {m(zs)})",
        f"Zeilen mit TP1 ohne jeden Zonen-Touch: {len(ot)} ({', '.join(r['Symbol'] for r in ot) or '—'})",
        "",
        "_Reine Messung (L24). Entscheid ueber Live-Entry bis zur Entry-Grenze (Weg A) beim 20er-Review._",
    ]) + "\n"


def lauf(state_dir: str, tage: list[date], daily_fn: Callable = yf_daily, h1_fn: Callable = yf_1h,
         csv_path: Optional[Path] = None) -> tuple[list[Fall], list[str]]:
    zeilen = zeilen_aus_state(state_dir)
    path = csv_path or Path(state_dir) / CSV_NAME
    bestand = [_fall_aus_row(r) for r in csv.DictReader(path.open(encoding="utf-8"))] if path.exists() else []
    cache: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    prot, neu = [], []

    def daten(sym, ref):
        if sym not in cache:
            d, h = daily_fn(sym), h1_fn(sym)
            cache[sym] = (_pence(sym, d, ref), _pence(sym, h, ref))
        return cache[sym]

    for z in zeilen:
        try:
            d, h = daten(z.symbol, z.tp1)
        except Exception as e:  # noqa: BLE001
            prot.append(f"{z.symbol}: Datenabruf fehlgeschlagen ({e})")
            continue
        if d is None or d.empty or h is None or h.empty:
            prot.append(f"{z.symbol}: keine Daten")
            continue
        for t in tage:
            if any(b.Symbol == z.symbol and b.Signal_Datum == t.isoformat() and b.Art == "weggelaufen" for b in bestand + neu):
                continue
            f = finde_signal(z, t, d, h)
            if f:
                neu.append(f)
                prot.append(f"{t} {z.symbol}: weggelaufen erfasst (Entry {f.Entry}, {f.Abstand_Zone_ATR} ATR ueber Zone, RR {f.RR_TP1})")
        ot = ohne_touch(z, d)
        if ot and not any(b.Symbol == ot.Symbol and b.Art == "ohne Touch" for b in bestand + neu):
            neu.append(ot)
            prot.append(f"{z.symbol}: TP1 ohne Zonen-Touch erfasst")
    for f in bestand + neu:
        if f.Art == "weggelaufen" and f.Status == "offen":
            try:
                _, h = daten(f.Symbol, f.TP1)
                verfolge(f, h, max(tage))
            except Exception as e:  # noqa: BLE001
                prot.append(f"{f.Symbol}: Verfolgung fehlgeschlagen ({e})")
    return bestand + neu, prot


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", default="state")
    ap.add_argument("--date")
    ap.add_argument("--backfill-days", type=int, default=0)
    ap.add_argument("--md")
    a = ap.parse_args(argv)
    heute = date.fromisoformat(a.date) if a.date else date.today()
    tage = [heute - timedelta(days=i) for i in range(min(a.backfill_days, 55), -1, -1)]
    tage = [t for t in tage if t.weekday() < 5]
    faelle, prot = lauf(a.state_dir, tage)
    for p in prot:
        logger.info(p)
    rows = upsert(Path(a.state_dir) / CSV_NAME, faelle)
    if a.md:
        Path(a.md).write_text(zusammenfassung(rows) + "\n<details><summary>Protokoll</summary>\n\n"
                              + "\n".join(f"- {p}" for p in prot) + "\n</details>\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
