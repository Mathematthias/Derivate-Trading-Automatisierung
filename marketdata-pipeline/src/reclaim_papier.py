#!/usr/bin/env python3
"""
reclaim_papier.py — Papierspur „Reclaim am EMA200“ (Long), ohne Geld.

User-Entscheid 2026-11-03 (Anlass MRK.DE: Tief 18.09. am EMA200, erste 4h-Umkehr 22.09.,
Stack erst am 14.10. bullish): Das Stack-Gate sperrt genau diese Einstiege. Ob sie etwas
taugen, wird hier gemessen, bevor eine Regel faellt. Grobe Vormessung 2026-11-03 ueber neun
Digest-Staende: Reclaim n = 23, Median +0,8 ATR; Trend-Pullback n = 59, Median +2,1 ATR.

Signal (Tagesbalken D):
  - Touch: |Schluss - EMA200| <= 1 ATR (Definition aus market_data) an einem der letzten
    TOUCH_MAX_HT Handelstage
  - Schluss D ueber der EMA200
  - 4h-Umkehr bullisch auf einem geschlossenen Block von D, mindestens BLOCK_MIN_BARS 1h-Balken
    (das XETRA-Reststueck 17:00-17:35 ist kein Block, Fund MRK.DE 2026-11-03)
  - ATR % <= ATR_MAX_PCT, je Symbol hoechstens ein Signal in SPERRE_HT Handelstagen
Der Stack wird NICHT gefiltert, sondern als Spalte gefuehrt, damit die Auswertung neutral gegen
bullisch trennen kann.

Plan je Signal (wie eine Auto-Zeile mit Anker EMA200):
  Entry = Schluss des Umkehr-Blocks · TIW = EMA200 - 0,50 ATR
  SL    = MIN(Entry - 1,5 ATR ; TIW - 0,30 ATR)            (L25)
  TP1   = erster starker Widerstand ueber dem Entry, wenn es einen gibt; TP1_ok = mindestens 1,3 R
Das Signal wird auch ohne TP1_ok gefuehrt: Genau diese Sperre soll die Messung pruefen.

Ausgang auf Tagesbalken ab D+1, hoechstens ZEIT_HT Handelstage:
  Oeffnung unter SL = Eroeffnungskurs · Tief unter SL = SL · sonst Schluss am letzten Tag.
  Reihenfolge innerhalb eines Tages ist unbekannt, deshalb gewinnt der Stop.

Urteil erst ab n >= MIN_N_URTEIL geschlossenen Signalen (L28).

Aufruf (Samstag im MFE/MAE-Job):
    python src/reclaim_papier.py --state-dir state --scan --fill --md out.md
"""
from __future__ import annotations

import argparse
import csv
import logging
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

import intraday_4h as i4
import widerstaende as wd
from market_data import EMA200_TOUCH_TOL_ATR

logger = logging.getLogger("reclaim_papier")

DATEI = "reclaim_papier.csv"
COLS = [
    "Datum", "Symbol", "Entry", "ATR", "EMA200", "TIW", "SL", "R", "TP1", "TP1_R", "TP1_ok",
    "Touch_HT", "Stack", "RSI", "Umkehr", "Earnings_7d", "Status", "Exit_Datum", "Exit_Grund",
    "Exit", "Ergebnis_R", "MFE_R", "MAE_R", "TP1_Hit",
]
TOUCH_MAX_HT = 6
BLOCK_MIN_BARS = 2
ATR_MAX_PCT = 8.0
SPERRE_HT = 20
ZEIT_HT = 20
RR_BODEN = 1.3
TIW_OFF_ATR = 0.50
SCAN_HT = 8                 # Rueckblick je Lauf: Wochenlauf plus Ueberlappung
MIN_N_URTEIL = 20
SPERRE_KALENDER = int(SPERRE_HT * 1.4)


def _f(x) -> Optional[float]:
    try:
        return None if x in (None, "") else float(x)
    except (TypeError, ValueError):
        return None


def lesen(pfad: Path) -> list[dict]:
    if not pfad.exists():
        return []
    with open(pfad, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def schreiben(pfad: Path, rows: list[dict]) -> None:
    with open(pfad, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})


# ---------------------------------------------------------------------------
# Rechnen (ohne Netz, testbar)
# ---------------------------------------------------------------------------

def _serien(d1: pd.DataFrame) -> pd.DataFrame:
    df = d1.copy()
    c = df["Close"]
    df["ema20"] = c.ewm(span=20, adjust=False).mean()
    df["ema50"] = c.ewm(span=50, adjust=False).mean()
    df["ema200"] = c.ewm(span=200, adjust=False).mean()
    prev = c.shift(1)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - prev).abs(), (df["Low"] - prev).abs()], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    delta = c.diff()
    auf = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    ab = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + auf / ab.replace(0, float("nan")))
    df["touch"] = (c - df["ema200"]).abs() <= df["atr"] * EMA200_TOUCH_TOL_ATR
    return df


def _stack(z) -> str:
    if z["ema20"] > z["ema50"] > z["ema200"]:
        return "bullish"
    if z["ema20"] < z["ema50"] < z["ema200"]:
        return "bearish"
    return "neutral"


def kandidaten_tage(d1: pd.DataFrame, scan_ht: int = SCAN_HT) -> list[pd.Timestamp]:
    """Tage im Rueckblick mit Touch in den letzten TOUCH_MAX_HT Tagen und Schluss ueber der EMA200."""
    df = _serien(d1)
    if len(df) < 200:
        return []
    out = []
    for pos in range(max(0, len(df) - scan_ht), len(df)):
        z = df.iloc[pos]
        if z["Close"] <= z["ema200"] or not z["atr"] > 0 or z["atr"] / z["Close"] * 100 > ATR_MAX_PCT:
            continue
        if df["touch"].iloc[max(0, pos - TOUCH_MAX_HT):pos + 1].any():
            out.append(df.index[pos])
    return out


def umkehr_block(h1: pd.DataFrame, tag: date) -> Optional[tuple[float, str]]:
    """(Schluss, Grund) des ersten echten bullischen 4h-Blocks an diesem Tag, sonst None."""
    b4 = i4.resample_1h_to_4h(h1)
    if b4 is None or b4.empty:
        return None
    for pos in range(1, len(b4)):
        ts = b4.index[pos]
        if ts.date() != tag:
            continue
        if "_bars" in b4.columns and int(b4["_bars"].iloc[pos]) < BLOCK_MIN_BARS:
            continue
        bull, _bear, grund = i4.detect_reverse(b4.iloc[: pos + 1])
        if bull:
            return float(b4["Close"].iloc[pos]), str(grund or "Umkehr")
    return None


def plan(d1: pd.DataFrame, tag: pd.Timestamp, entry: float) -> Optional[dict]:
    """Plan nach den Regeln einer Auto-Zeile mit Anker EMA200."""
    df = _serien(d1.loc[:tag])
    z = df.iloc[-1]
    a = float(z["atr"])
    tiw = float(z["ema200"]) - TIW_OFF_ATR * a
    sl = min(entry - 1.5 * a, tiw - 0.30 * a)
    r = entry - sl
    if r <= 0:
        return None
    tp1, tp1_r = None, None
    fenster = df.tail(260)
    zonen = wd.zonen(df, entry, a, ema200=float(z["ema200"]),
                     hoch_52w=float(fenster["High"].max()), tief_52w=float(fenster["Low"].min())) or {}
    for zone in zonen.get("ueber") or []:
        if zone.get("klasse") == "stark" and zone["lo"] > entry:
            tp1, tp1_r = round(float(zone["lo"]), 4), round((zone["lo"] - entry) / r, 2)
            break
    pos = len(df) - 1
    touch = df["touch"].iloc[max(0, pos - TOUCH_MAX_HT):pos + 1]
    return {
        "Entry": round(entry, 4), "ATR": round(a, 4), "EMA200": round(float(z["ema200"]), 4),
        "TIW": round(tiw, 4), "SL": round(sl, 4), "R": round(r, 4), "TP1": tp1, "TP1_R": tp1_r,
        "TP1_ok": "" if tp1_r is None else ("ja" if tp1_r >= RR_BODEN else "nein"),
        "Touch_HT": int(pos - touch[touch].index.map(df.index.get_loc).max()) if touch.any() else "",
        "Stack": _stack(z), "RSI": round(float(z["rsi"]), 1),
    }


def ausgang(row: dict, d1: pd.DataFrame) -> dict:
    """Weg ab dem Tag nach dem Signal: Felder Status bis TP1_Hit."""
    d0 = pd.Timestamp(str(row["Datum"])[:10])
    entry, sl, r = float(row["Entry"]), float(row["SL"]), float(row["R"])
    tp1 = _f(row.get("TP1"))
    idx = d1.index.tz_localize(None) if getattr(d1.index, "tz", None) is not None else d1.index
    nach = d1[idx > d0].head(ZEIT_HT)
    hoch, tief, tp_hit = entry, entry, False
    for ts, z in nach.iterrows():
        o, h, l = float(z["Open"]), float(z["High"]), float(z["Low"])
        tief = min(tief, l)
        if o <= sl or l <= sl:
            ex = o if o <= sl else sl
            return {"Status": "geschlossen", "Exit_Datum": ts.date().isoformat(), "Exit_Grund": "Stop",
                    "Exit": round(ex, 4), "Ergebnis_R": round((ex - entry) / r, 2),
                    "MFE_R": round((hoch - entry) / r, 2), "MAE_R": round((entry - tief) / r, 2),
                    "TP1_Hit": "ja" if tp_hit else "nein"}
        hoch = max(hoch, h)
        tp_hit = tp_hit or (tp1 is not None and h >= tp1)
    st = {"MFE_R": round((hoch - entry) / r, 2), "MAE_R": round((entry - tief) / r, 2),
          "TP1_Hit": "ja" if tp_hit else "nein", "Status": "offen"}
    if len(nach) >= ZEIT_HT:
        ex = float(nach["Close"].iloc[-1])
        st.update({"Status": "geschlossen", "Exit_Datum": nach.index[-1].date().isoformat(),
                   "Exit_Grund": "Zeit", "Exit": round(ex, 4), "Ergebnis_R": round((ex - entry) / r, 2)})
    return st


def scan(rows: list[dict], symbole: list[str], tages: Callable[[str], Optional[pd.DataFrame]],
         stunden: Callable[[str], Optional[pd.DataFrame]],
         earnings: Optional[Callable[[str, date], bool]] = None) -> int:
    """Haengt neue Signale an `rows` an (idempotent ueber Symbol + Sperrfrist)."""
    neu = 0
    for sym in symbole:
        d1 = tages(sym)
        if d1 is None or d1.empty:
            continue
        tage = kandidaten_tage(d1)
        if not tage:
            continue
        h1 = stunden(sym)
        if h1 is None or h1.empty:
            continue
        for ts in tage:
            tag = ts.date()
            alt = [date.fromisoformat(str(r["Datum"])[:10]) for r in rows if r.get("Symbol") == sym]
            if any(abs((tag - a).days) < SPERRE_KALENDER for a in alt):
                continue
            u = umkehr_block(h1, tag)
            if u is None:
                continue
            p = plan(d1, ts, u[0])
            if p is None:
                continue
            rows.append({"Datum": tag.isoformat(), "Symbol": sym, **p, "Umkehr": u[1],
                         "Earnings_7d": ("ja" if earnings(sym, tag) else "nein") if earnings else "",
                         "Status": "offen"})
            neu += 1
    rows.sort(key=lambda r: (str(r.get("Datum")), str(r.get("Symbol"))))
    return neu


def fill(rows: list[dict], tages: Callable[[str], Optional[pd.DataFrame]]) -> int:
    n = 0
    for r in rows:
        if r.get("Status") == "geschlossen":
            continue
        d1 = tages(str(r.get("Symbol")))
        if d1 is None or d1.empty:
            continue
        r.update(ausgang(r, d1))
        n += 1
    return n


def _block(rows: list[dict]) -> Optional[str]:
    werte = [_f(r.get("Ergebnis_R")) for r in rows]
    werte = [w for w in werte if w is not None]
    if not werte:
        return None
    tr = sum(w > 0 for w in werte)
    tp = sum(r.get("TP1_Hit") == "ja" for r in rows)
    return (f"n {len(werte)} · Treffer {tr / len(werte):.0%} · Ø {statistics.mean(werte):+.2f} R · "
            f"Median {statistics.median(werte):+.2f} R · TP1 erreicht {tp}")


def render(rows: list[dict], heute: Optional[date] = None) -> str:
    heute = heute or date.today()
    zu = [r for r in rows if r.get("Status") == "geschlossen" and r.get("Earnings_7d") != "ja"]
    offen = [r for r in rows if r.get("Status") != "geschlossen"]
    out = [f"# Papierspur Reclaim EMA200 — Stand {heute.isoformat()}", "",
           f"Signale {len(rows)}, offen {len(offen)}, ohne Earnings-Sperre geschlossen {len(zu)}. "
           f"Urteil erst ab n = {MIN_N_URTEIL}. Kein Geld, keine Kosten eingerechnet.", ""]
    for titel, teil in (("Alle", zu),
                        ("Stack neutral", [r for r in zu if r.get("Stack") == "neutral"]),
                        ("Stack bullish", [r for r in zu if r.get("Stack") == "bullish"]),
                        ("TP1 mindestens 1,3 R", [r for r in zu if r.get("TP1_ok") == "ja"]),
                        ("TP1 unter 1,3 R", [r for r in zu if r.get("TP1_ok") == "nein"]),
                        ("Kein TP1 gefunden", [r for r in zu if r.get("TP1_ok") == ""])):
        b = _block(teil)
        if b:
            out.append(f"- **{titel}:** {b}")
    if len(zu) >= MIN_N_URTEIL:
        out += ["", f"**n >= {MIN_N_URTEIL} erreicht: Entscheid über das Stack-Gate für die Anker EMA100/200 fällig.**"]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Netz (nur im Job)
# ---------------------------------------------------------------------------

def _yf_tages(sym: str) -> Optional[pd.DataFrame]:
    import yfinance as yf
    try:
        df = yf.download(sym, period="2y", interval="1d", auto_adjust=False, progress=False, threads=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"{sym}: Tagesbalken fehlen: {exc}")
        return None
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[["Open", "High", "Low", "Close"]].dropna()


def _yf_stunden(sym: str) -> Optional[pd.DataFrame]:
    import yfinance as yf
    try:
        df = yf.download(sym, period="60d", interval="1h", auto_adjust=False, progress=False, threads=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"{sym}: Stundenbalken fehlen: {exc}")
        return None
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def _yf_earnings(sym: str, tag: date) -> bool:
    import yfinance as yf
    try:
        df = yf.Ticker(sym).get_earnings_dates(limit=12)
    except Exception:  # noqa: BLE001 — Flag ist Komfort, kein Abbruchgrund
        return False
    if df is None or df.empty:
        return False
    return any(tag <= ts.date() <= tag + timedelta(days=7) for ts in df.index)


def symbole() -> list[str]:
    from dividend_scan import load_universe
    return sorted(s for s in load_universe() if not (s.startswith("^") or "=" in s or s.endswith(("-EUR", "-USD"))))


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state-dir", default="./state")
    ap.add_argument("--scan", action="store_true", help="neue Signale suchen")
    ap.add_argument("--fill", action="store_true", help="Ausgaenge nachtragen")
    ap.add_argument("--md", default=None, help="Auswertung als Markdown")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    pfad = Path(a.state_dir) / DATEI
    rows = lesen(pfad)
    cache: dict[str, Optional[pd.DataFrame]] = {}

    def tages(s: str) -> Optional[pd.DataFrame]:
        if s not in cache:
            cache[s] = _yf_tages(s)
        return cache[s]

    if a.scan:
        logger.info(f"Neue Signale: {scan(rows, symbole(), tages, _yf_stunden, _yf_earnings)}")
    if a.fill:
        logger.info(f"Aktualisiert: {fill(rows, tages)}")
    if a.scan or a.fill:
        schreiben(pfad, rows)
    if a.md:
        Path(a.md).write_text(render(rows), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
