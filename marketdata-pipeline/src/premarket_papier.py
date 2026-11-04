#!/usr/bin/env python3
"""
premarket_papier.py — Papier-Spur „Premarket-Limit nach Earnings“ (User-Idee 2026-11-04, Anlass ANET).

These des Users: Steigt ein Kurs nach guten Zahlen vorboerslich stark und faellt zwischendurch
zurueck, fuellt eine Limit-Order am unteren Rand der vorboerslichen Spanne im Eroeffnungsrauschen;
danach laeuft der Kurs oft bis an die obere Kante der vorboerslichen Spanne.

Gegenthese (L27, adverse Selektion): Das Limit fuellt bevorzugt an Tagen mit schwacher Eroeffnung
und verpasst die staerksten Tage. Deshalb misst der Job auch die Vergleichsspur „Markt zur
Eroeffnung“ und implizit „nichts“ (= 0 R). Reine Messung nach L24, kein Geld, Urteil ab n >= 20.

Regeln (fest, VOR dem ersten Fall festgelegt; Zeiten in New York, entspricht 13:00-15:25 MEZ):
  Kandidaten   US-Werte des Universums mit Earnings gestern nach Schluss (AMC) oder heute vor
               Eroeffnung (BMO), Quelle earn_last aus dem BRIEFING-DIGEST.
  Zahlen gut   EPS-Ueberraschung > 0 (yfinance earnings_dates) — Ersatz fuer „Umsatz und Ausblick
               ueber Konsens“, das yfinance nicht liefert (User-Entscheid 2026-11-04).
  Luecke       (PM-Last − Vortagesschluss) >= 1,0 x ATR-14-1D — Ersatz fuer „>= halbe implizite
               Bewegung“. Nur Long.
  Limit        PM-Tief 07:00-09:25 ET, gueltig 09:30-10:00 ET. Fill = min(Limit, Open der Kerze).
  Stop (L25)   SL = MIN(Entry − 1,5 x ATR ; TIW − 0,30 x ATR), TIW = Vortagesschluss (Lueckenschluss).
  Ziel A       PM-Hoch. Ziel B Tagesschluss. Treffen Stop und Ziel in derselben 5m-Kerze: Stop zuerst.
  Vergleich    „Markt“: Kauf zum ersten Open 09:30 ET, gleicher Stop-Rechenweg, Halten bis Schluss.

Ausgang: state/premarket_papier.csv (Upsert je Datum+Symbol) + Markdown-Zusammenfassung.
Daten: yfinance 5m mit prepost=True (bis 60 Tage zurueck) und 1d-Historie fuer Vortagesschluss/ATR.

Aufruf:
    python src/premarket_papier.py --digest digest.json --state-dir state --md out.md
    python src/premarket_papier.py --digest digest.json --backfill-days 45 --state-dir state
    python src/premarket_papier.py --digest digest.json --date 2026-11-04 --symbols ANET
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable, Iterable, Optional

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("premarket_papier")

NY = "America/New_York"
PM_START, PM_END = time(7, 0), time(9, 25)
RTH_OPEN, LIMIT_BIS, RTH_CLOSE = time(9, 30), time(10, 0), time(16, 0)
GAP_MIN_ATR = 1.0
SL_ATR, TIW_PUFFER_ATR = 1.5, 0.30
CSV_NAME = "premarket_papier.csv"

COLUMNS = [
    "Datum", "Symbol", "Termin", "EPS_Surprise_Pct", "PrevClose", "ATR", "PM_Low", "PM_High",
    "PM_Last", "Gap_ATR", "Open", "Fill", "Entry", "SL", "R_Einheit", "Ziel_A", "Ergebnis_A",
    "R_A", "R_Schluss", "Markt_Entry", "Markt_SL", "R_Markt_Schluss", "MFE_R", "MAE_R",
    "Schluss", "Hinweis",
]


# ---------------------------------------------------------------------------
# Reine Rechenfunktionen (offline testbar)
# ---------------------------------------------------------------------------

def atr_wilder(daily: pd.DataFrame, n: int = 14) -> Optional[float]:
    """ATR-14 nach Wilder (RMA) aus Tagesbalken mit High/Low/Close. Letzter Wert."""
    if daily is None or len(daily) < n + 1:
        return None
    h, l, c = daily["High"].astype(float), daily["Low"].astype(float), daily["Close"].astype(float)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    v = float(atr.iloc[-1])
    return v if math.isfinite(v) else None


def l25_sl_long(entry: float, tiw: float, atr: float) -> float:
    return min(entry - SL_ATR * atr, tiw - TIW_PUFFER_ATR * atr)


def _ny_index(df: pd.DataFrame) -> pd.DataFrame:
    idx = pd.DatetimeIndex(df.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx
    out = df.copy()
    out.index = idx.tz_convert(NY)
    return out


def split_session(intra: pd.DataFrame, tag: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Liefert (Premarket 07:00-09:25, regulaere Sitzung 09:30-16:00) fuer einen Tag (NY-Zeit)."""
    d = _ny_index(intra)
    d = d[d.index.date == tag]
    t = d.index.time
    pm = d[(t >= PM_START) & (t < PM_END)]
    rth = d[(t >= RTH_OPEN) & (t < RTH_CLOSE)]
    return pm, rth


@dataclass
class Fall:
    Datum: str
    Symbol: str
    Termin: str = ""
    EPS_Surprise_Pct: Optional[float] = None
    PrevClose: Optional[float] = None
    ATR: Optional[float] = None
    PM_Low: Optional[float] = None
    PM_High: Optional[float] = None
    PM_Last: Optional[float] = None
    Gap_ATR: Optional[float] = None
    Open: Optional[float] = None
    Fill: str = "nein"
    Entry: Optional[float] = None
    SL: Optional[float] = None
    R_Einheit: Optional[float] = None
    Ziel_A: Optional[float] = None
    Ergebnis_A: str = ""
    R_A: Optional[float] = None
    R_Schluss: Optional[float] = None
    Markt_Entry: Optional[float] = None
    Markt_SL: Optional[float] = None
    R_Markt_Schluss: Optional[float] = None
    MFE_R: Optional[float] = None
    MAE_R: Optional[float] = None
    Schluss: Optional[float] = None
    Hinweis: str = ""


def _pfad(rth_ab: pd.DataFrame, entry: float, sl: float, ziel: Optional[float]):
    """Laeuft die 5m-Kerzen ab dem Fill ab. Rueckgabe (exit_preis, ergebnis, mfe, mae) in Kurs.

    Stop vor Ziel in derselben Kerze (konservativ). ziel=None → nur Stop oder Schluss.
    """
    hi, lo = entry, entry
    for _, b in rth_ab.iterrows():
        bl, bh = float(b["Low"]), float(b["High"])
        lo, hi = min(lo, bl), max(hi, bh)
        if bl <= sl:
            return sl, "Stop", hi, lo
        if ziel is not None and bh >= ziel:
            return ziel, "Ziel", hi, lo
    return float(rth_ab["Close"].iloc[-1]), "Schluss", hi, lo


def bewerte(datum: date, symbol: str, prev_close: float, atr: float, intra: pd.DataFrame,
            termin: str = "", eps_surprise: Optional[float] = None) -> Optional[Fall]:
    """Wertet einen Kandidaten-Tag aus. None, wenn die Luecke das Kriterium verfehlt
    oder Daten fehlen (Grund steht dann im Log)."""
    pm, rth = split_session(intra, datum)
    f = Fall(Datum=datum.isoformat(), Symbol=symbol, Termin=termin,
             EPS_Surprise_Pct=None if eps_surprise is None else round(eps_surprise, 2),
             PrevClose=round(prev_close, 4), ATR=round(atr, 4))
    if pm.empty or rth.empty:
        logger.info(f"{symbol} {datum}: keine PM- oder RTH-Kerzen")
        return None
    f.PM_Low, f.PM_High = round(float(pm["Low"].min()), 4), round(float(pm["High"].max()), 4)
    f.PM_Last = round(float(pm["Close"].iloc[-1]), 4)
    f.Gap_ATR = round((f.PM_Last - prev_close) / atr, 2)
    if f.Gap_ATR < GAP_MIN_ATR:
        logger.info(f"{symbol} {datum}: Luecke {f.Gap_ATR} ATR < {GAP_MIN_ATR}")
        return None
    f.Open = round(float(rth["Open"].iloc[0]), 4)
    f.Schluss = round(float(rth["Close"].iloc[-1]), 4)
    f.Ziel_A = f.PM_High

    # Vergleichsspur Markt zur Eroeffnung, Halten bis Schluss (Stop gilt)
    m_sl = l25_sl_long(f.Open, prev_close, atr)
    m_exit, _, _, _ = _pfad(rth, f.Open, m_sl, None)
    f.Markt_Entry, f.Markt_SL = f.Open, round(m_sl, 4)
    f.R_Markt_Schluss = round((m_exit - f.Open) / (f.Open - m_sl), 2)

    # Limit am PM-Tief, gueltig bis 10:00 ET
    fenster = rth[rth.index.time < LIMIT_BIS]
    hit = fenster[fenster["Low"].astype(float) <= f.PM_Low]
    if hit.empty:
        f.Hinweis = "Limit nicht erreicht"
        return f
    t_fill = hit.index[0]
    entry = min(f.PM_Low, float(hit["Open"].iloc[0]))
    sl = l25_sl_long(entry, prev_close, atr)
    r = entry - sl
    f.Fill, f.Entry, f.SL, f.R_Einheit = "ja", round(entry, 4), round(sl, 4), round(r, 4)
    ab = rth[rth.index >= t_fill]
    exit_a, erg_a, hi, lo = _pfad(ab, entry, sl, f.Ziel_A if f.Ziel_A > entry else None)
    exit_b, erg_b, hi_b, lo_b = _pfad(ab, entry, sl, None)
    f.Ergebnis_A = erg_a if f.Ziel_A > entry else "Ziel <= Entry"
    f.R_A = round((exit_a - entry) / r, 2)
    f.R_Schluss = round((exit_b - entry) / r, 2)
    f.MFE_R = round((hi_b - entry) / r, 2)
    f.MAE_R = round((entry - lo_b) / r, 2)
    if erg_b == "Stop":
        f.Hinweis = "Stop vor Schluss"
    return f


def us_symbol(sym: str) -> bool:
    return "." not in sym and not sym.startswith("^") and "=" not in sym and "-" not in sym


def kandidaten(digest: dict, tag: date, vortag: date, symbols: Optional[Iterable[str]] = None) -> list[tuple[str, str]]:
    """(Symbol, 'AMC'|'BMO') fuer US-Werte mit earn_last == vortag (AMC) bzw. == tag (BMO).
    Die genaue Uhrzeit prueft spaeter earnings_zeit(); hier nur die Vorauswahl."""
    uni = digest.get("universe") or {}
    erlaubt = {s.upper() for s in symbols} if symbols else None
    out = []
    for sym, v in uni.items():
        if not us_symbol(sym) or (erlaubt and sym.upper() not in erlaubt):
            continue
        el = (v or {}).get("earn_last")
        if el == vortag.isoformat():
            out.append((sym, "AMC"))
        elif el == tag.isoformat():
            out.append((sym, "BMO"))
    return sorted(out)


def vortag_von(tag: date, handelstage: Iterable[date]) -> Optional[date]:
    frueher = [d for d in handelstage if d < tag]
    return max(frueher) if frueher else None


def upsert_csv(path: Path, faelle: list[Fall]) -> int:
    alt: dict[tuple[str, str], dict] = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                alt[(row["Datum"], row["Symbol"])] = row
    for f in faelle:
        alt[(f.Datum, f.Symbol)] = {k: ("" if v is None else v) for k, v in asdict(f).items()}
    rows = sorted(alt.values(), key=lambda r: (r["Datum"], r["Symbol"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in COLUMNS})
    return len(rows)


def _f(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def zusammenfassung(path: Path) -> str:
    rows = list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []
    n = len(rows)
    fills = [r for r in rows if r["Fill"] == "ja"]

    def mittel(vals):
        vals = [v for v in vals if v is not None]
        return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)

    ra, na = mittel([_f(r["R_A"]) for r in fills])
    rb, nb = mittel([_f(r["R_Schluss"]) for r in fills])
    rm, nm = mittel([_f(r["R_Markt_Schluss"]) for r in rows])
    rm_f, _ = mittel([_f(r["R_Markt_Schluss"]) for r in fills])
    rm_nf, _ = mittel([_f(r["R_Markt_Schluss"]) for r in rows if r["Fill"] != "ja"])
    ziel = sum(1 for r in fills if r["Ergebnis_A"] == "Ziel")
    stop = sum(1 for r in fills if r["Ergebnis_A"] == "Stop")

    def z(v):
        return "—" if v is None else f"{v:+.2f} R"

    zeilen = [
        "# Papier-Spur Premarket-Limit nach Earnings",
        "",
        f"Stand {date.today().isoformat()} · Faelle mit Luecke >= {GAP_MIN_ATR} ATR: **n = {n}** · "
        f"Limit gefuellt: {len(fills)} ({(len(fills) / n * 100):.0f} %)" if n else "Noch keine Faelle.",
        "",
        "| Spur | n | Ø R |",
        "|---|---|---|",
        f"| Limit, Ziel A (PM-Hoch) | {na} | {z(ra)} |",
        f"| Limit, Halten bis Schluss | {nb} | {z(rb)} |",
        f"| Markt zur Eroeffnung, bis Schluss | {nm} | {z(rm)} |",
        "| Nichts | — | ±0,00 R |",
        "",
        f"Ziel A erreicht: {ziel} · Stop: {stop} · Rest zum Schluss: {len(fills) - ziel - stop}.",
        "",
        "**Adverse Selektion (L27):** Markt-Spur an Tagen MIT Fill "
        f"{z(rm_f)} gegen Tage OHNE Fill {z(rm_nf)}. Liegt der erste Wert deutlich darunter, "
        "fuellt das Limit bevorzugt die schwachen Tage.",
        "",
        "_Reine Messung (L24), kein Gate. Urteil ab n >= 20 gefuellten Faellen._",
    ]
    return "\n".join(zeilen) + "\n"


# ---------------------------------------------------------------------------
# Datenabruf (yfinance) — im Test durch Fakes ersetzt
# ---------------------------------------------------------------------------

def yf_daily(sym: str, ende: date) -> pd.DataFrame:
    import yfinance as yf
    df = yf.Ticker(sym).history(start=(ende - timedelta(days=90)).isoformat(),
                                end=(ende + timedelta(days=1)).isoformat(), interval="1d", auto_adjust=False)
    return df


def yf_intraday(sym: str) -> pd.DataFrame:
    import yfinance as yf
    return yf.Ticker(sym).history(period="60d", interval="5m", prepost=True, auto_adjust=False)


def earnings_zeit(sym: str, um: date) -> tuple[Optional[str], Optional[float]]:
    """('AMC'|'BMO'|'?', EPS-Surprise %) fuer den Bericht am Tag `um` laut yfinance."""
    import yfinance as yf
    try:
        ed = yf.Ticker(sym).earnings_dates
    except Exception as e:  # noqa: BLE001
        logger.warning(f"{sym}: earnings_dates fehlgeschlagen: {e}")
        return None, None
    if ed is None or ed.empty:
        return None, None
    ed = ed.copy()
    idx = pd.DatetimeIndex(ed.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx
    ed.index = idx.tz_convert(NY)
    sel = ed[ed.index.date == um]
    if sel.empty:
        return None, None
    ts = sel.index[0]
    zeit = "AMC" if ts.time() >= time(16, 0) else ("BMO" if ts.time() < time(9, 30) else "?")
    s = sel.iloc[0].get("Surprise(%)")
    return zeit, (None if s is None or pd.isna(s) else float(s))


def lauf(digest: dict, tage: list[date], symbols: Optional[list[str]] = None,
         daily_fn: Callable = yf_daily, intra_fn: Callable = yf_intraday,
         earn_fn: Callable = earnings_zeit) -> tuple[list[Fall], list[str]]:
    faelle, protokoll = [], []
    intra_cache: dict[str, pd.DataFrame] = {}
    # Handelstage aus einer Referenzreihe (SPY) bestimmen, einmal fuer den ganzen Lauf
    ref = daily_fn("SPY", max(tage)) if tage else None
    htage = sorted({pd.Timestamp(i).date() for i in ref.index}) if ref is not None and len(ref) else []
    for tag in tage:
        if tag not in htage:
            protokoll.append(f"{tag}: kein Handelstag")
            continue
        vortag = vortag_von(tag, htage)
        for sym, termin_vorab in kandidaten(digest, tag, vortag, symbols):
            earn_tag = vortag if termin_vorab == "AMC" else tag
            termin, surprise = earn_fn(sym, earn_tag)
            if termin is not None and termin != termin_vorab and termin != "?":
                protokoll.append(f"{tag} {sym}: Termin {termin} passt nicht zu {termin_vorab}")
                continue
            if surprise is None or surprise <= 0:
                protokoll.append(f"{tag} {sym}: EPS-Ueberraschung {surprise} -> keine guten Zahlen")
                continue
            d = daily_fn(sym, tag)
            if d is None or d.empty:
                protokoll.append(f"{tag} {sym}: keine Tagesdaten")
                continue
            d = d[[pd.Timestamp(i).date() < tag for i in d.index]]
            atr = atr_wilder(d)
            if atr is None or d.empty:
                protokoll.append(f"{tag} {sym}: zu wenig Historie fuer ATR")
                continue
            prev_close = float(d["Close"].iloc[-1])
            if sym not in intra_cache:
                intra_cache[sym] = intra_fn(sym)
            f = bewerte(tag, sym, prev_close, atr, intra_cache[sym], termin or termin_vorab, surprise)
            if f is None:
                protokoll.append(f"{tag} {sym}: Luecke < {GAP_MIN_ATR} ATR oder keine Intraday-Daten")
                continue
            faelle.append(f)
            protokoll.append(f"{tag} {sym}: Fall erfasst (Fill {f.Fill}, R_A {f.R_A}, Markt {f.R_Markt_Schluss})")
    return faelle, protokoll


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--digest", required=True, help="BRIEFING-DIGEST-JSON (Quelle earn_last)")
    ap.add_argument("--state-dir", default="state")
    ap.add_argument("--date", help="Auswertungstag JJJJ-MM-TT (Default heute, NY)")
    ap.add_argument("--backfill-days", type=int, default=0, help="zusaetzlich so viele Kalendertage zurueck (max ~55)")
    ap.add_argument("--symbols", help="Komma-Liste, beschraenkt die Kandidaten")
    ap.add_argument("--md", help="Markdown-Zusammenfassung schreiben")
    a = ap.parse_args(argv)

    digest = json.loads(Path(a.digest).read_text(encoding="utf-8"))
    heute = date.fromisoformat(a.date) if a.date else pd.Timestamp.now(tz=NY).date()
    tage = [heute - timedelta(days=i) for i in range(min(a.backfill_days, 55), -1, -1)]
    tage = [t for t in tage if t.weekday() < 5]
    syms = [s.strip() for s in a.symbols.split(",")] if a.symbols else None
    faelle, protokoll = lauf(digest, tage, syms)
    for p in protokoll:
        logger.info(p)
    path = Path(a.state_dir) / CSV_NAME
    n = upsert_csv(path, faelle)
    logger.info(f"{len(faelle)} Faelle neu/aktualisiert, {n} gesamt in {path}")
    if a.md:
        Path(a.md).write_text(zusammenfassung(path) + "\n<details><summary>Protokoll</summary>\n\n"
                              + "\n".join(f"- {p}" for p in protokoll) + "\n</details>\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
