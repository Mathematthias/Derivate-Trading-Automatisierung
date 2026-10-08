#!/usr/bin/env python3
"""
mfe_mae.py — Maximum Favorable / Adverse Excursion in R je geschlossenem Trade.

Warum (System-Review 2026-10-04): Das Journal kennt nur das Ergebnis eines
Trades, nicht seinen Weg. Ob ein Verlust ein Einstiegsfehler war (Kurs lief
nie fuer uns: MFE < 0,5 R) oder ein Ausstiegsfehler (Kurs stand bei +1,5 R
und wir sind bei -1 R raus: MFE hoch, Ergebnis negativ), entscheidet, WELCHE
Regel man anfasst. Ohne MFE/MAE wird jede Regelaenderung geraten.

Eingang: Blatt "Trade-Audit" im Journal mit den Spalten
    Nr, Symbol, Richtung, Kauf, Verkauf, EntryU, SL_U
(EntryU/SL_U = Einstieg und Stop im BASISWERT, nicht im Zertifikat — das
Hebelprodukt ist nur die Huelle; MFE/MAE gehoeren zum Basiswert.)

Ausgang: Spalten MFE_R, MAE_R, Bars im selben Blatt (werden angelegt, falls
sie fehlen) + CSV + Markdown-Zusammenfassung (Vier-Felder-Matrix).

Rechenweg (Long; Short gespiegelt):
    risk  = EntryU - SL_U                       (> 0, sonst Zeile uebersprungen)
    MFE_R = (max(High[Kauf..Verkauf]) - EntryU) / risk
    MAE_R = (EntryU - min(Low[Kauf..Verkauf]))  / risk
Beide auf Tagesbalken des Basiswerts, Kauf- und Verkaufstag eingeschlossen.
Das ist eine Untergrenze fuer MAE und eine Obergrenze fuer MFE auf Tagesbasis
— intraday kann beides groesser gewesen sein, aber die Klassifikation
(Einstiegs- vs. Ausstiegsfehler) haengt an der Groessenordnung, nicht an der
zweiten Nachkommastelle.

Aufruf:
    python src/mfe_mae.py --journal Trading_Journal_20261004b.xlsx --out mfe.xlsx --csv mfe.csv
    python src/mfe_mae.py --journal in.xlsx --dry-run            # nur rechnen, nicht schreiben
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
from openpyxl import load_workbook

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("mfe_mae")

AUDIT_SHEET = "Trade-Audit"
REQUIRED = ("Nr", "Symbol", "Richtung", "Kauf", "Verkauf", "EntryU", "SL_U")
OUT_COLS = ("MFE_R", "MAE_R", "Bars")

# Vier-Felder-Matrix: Schwellen fuer die Klassifikation
MFE_GOOD_R = 1.0        # Kurs lief mindestens 1 R fuer uns
MAE_DEEP_R = 0.8        # Kurs lief mindestens 0,8 R gegen uns (Stop im Rauschen?)


# ---------------------------------------------------------------------------
# Reine Rechenfunktion (offline testbar)
# ---------------------------------------------------------------------------

@dataclass
class Excursion:
    mfe_r: float
    mae_r: float
    bars: int
    mfe_date: Optional[date] = None   # Tag des guenstigsten Extrems (Long: Hoch, Short: Tief)
    mae_date: Optional[date] = None   # Tag des unguenstigsten Extrems


def compute_mfe_mae(
    df: pd.DataFrame,
    direction: str,
    entry: float,
    sl: float,
    start: date,
    end: date,
) -> Optional[Excursion]:
    """df: Tagesbalken mit Spalten High/Low (DatetimeIndex). None, wenn
    kein Balken im Fenster liegt oder das Risiko <= 0 ist."""
    direction = direction.strip().upper()
    if direction.startswith("S"):
        risk = sl - entry
    else:
        risk = entry - sl
    if risk <= 0:
        return None
    win = df.loc[(df.index.date >= start) & (df.index.date <= end)]
    if win.empty:
        return None
    hi, lo = float(win["High"].max()), float(win["Low"].min())
    d_hi, d_lo = win["High"].idxmax().date(), win["Low"].idxmin().date()
    if direction.startswith("S"):
        mfe = (entry - lo) / risk
        mae = (hi - entry) / risk
        return Excursion(round(mfe, 2), round(mae, 2), int(len(win)), d_lo, d_hi)
    mfe = (hi - entry) / risk
    mae = (entry - lo) / risk
    return Excursion(round(mfe, 2), round(mae, 2), int(len(win)), d_hi, d_lo)


def classify(mfe_r: float, mae_r: float, result_r: Optional[float]) -> str:
    """Vier-Felder-Matrix fuer die Lesehilfe."""
    if result_r is not None and result_r > 0:
        return "Gewinner (lief)" if mfe_r >= MFE_GOOD_R else "Gewinner (knapp)"
    if mfe_r < 0.5 and mae_r >= MAE_DEEP_R:
        return "Einstiegsfehler (lief nie)"
    if mfe_r >= MFE_GOOD_R:
        return "Ausstiegsfehler (lief, dann weg)"
    if mae_r >= MAE_DEEP_R:
        return "Stop im Rauschen?"
    return "unklar"


# ---------------------------------------------------------------------------
# Journal lesen / schreiben
# ---------------------------------------------------------------------------

_DATE_RX = re.compile(r"(\d{4})-(\d{2})-(\d{2})|(\d{1,2})\.(\d{1,2})\.(\d{4})|(\d{1,2})\.(\d{1,2})\.(?=/)")


def parse_date(value) -> Optional[date]:
    """ISO, dd.mm.yyyy oder 'dd.mm./dd.mm.yyyy' (dann ERSTES Datum, Jahr vom Ende)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    m = _DATE_RX.search(s)
    if not m:
        return None
    if m.group(1):
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if m.group(4):
        return date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
    # 'dd.mm./...yyyy' — Jahr aus dem letzten 4-stelligen Token
    y = re.findall(r"(\d{4})", s)
    if not y:
        return None
    return date(int(y[-1]), int(m.group(8)), int(m.group(7)))


def _num(value) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace("€", "").replace("$", "").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def read_audit_rows(xlsx: Path, sheet: str = AUDIT_SHEET) -> tuple[list[dict], dict]:
    """Gibt (zeilen, spaltenindex) zurueck. Zeilen ohne vollstaendige Eingaben
    bekommen 'skip' mit Grund."""
    wb = load_workbook(xlsx, data_only=True)
    if sheet not in wb.sheetnames:
        raise ValueError(f"Blatt {sheet!r} fehlt in {xlsx.name}")
    ws = wb[sheet]
    hdr = {str(c.value).strip(): c.column for c in ws[1] if c.value is not None}
    missing = [c for c in REQUIRED if c not in hdr]
    if missing:
        raise ValueError(f"Blatt {sheet!r}: Spalten fehlen: {missing}")
    rows = []
    for r in range(2, ws.max_row + 1):
        def g(name):
            return ws.cell(row=r, column=hdr[name]).value
        nr = g("Nr")
        if nr in (None, ""):
            continue
        row = {
            "row": r, "nr": str(nr), "symbol": str(g("Symbol") or "").strip(),
            "direction": str(g("Richtung") or "").strip(), "start": parse_date(g("Kauf")),
            "end": parse_date(g("Verkauf")), "entry": _num(g("EntryU")), "sl": _num(g("SL_U")),
            "result_r": _num(g("R")) if "R" in hdr else None,
        }
        why = []
        if not row["symbol"]:
            why.append("Symbol")
        if row["start"] is None or row["end"] is None:
            why.append("Datum")
        if row["entry"] is None or row["sl"] is None:
            why.append("EntryU/SL_U")
        row["skip"] = ", ".join(why) if why else None
        rows.append(row)
    return rows, hdr


def write_results(xlsx_in: Path, xlsx_out: Path, results: dict[int, Excursion], sheet: str = AUDIT_SHEET) -> None:
    """Schreibt MFE_R/MAE_R/Bars in das Blatt (Spalten werden bei Bedarf angelegt).
    Laedt OHNE data_only, damit Formeln anderer Blaetter erhalten bleiben."""
    wb = load_workbook(xlsx_in)
    ws = wb[sheet]
    hdr = {str(c.value).strip(): c.column for c in ws[1] if c.value is not None}
    for col in OUT_COLS:
        if col not in hdr:
            ws.cell(row=1, column=ws.max_column + 1, value=col)
            hdr[col] = ws.max_column
    for r, ex in results.items():
        ws.cell(row=r, column=hdr["MFE_R"], value=ex.mfe_r)
        ws.cell(row=r, column=hdr["MAE_R"], value=ex.mae_r)
        ws.cell(row=r, column=hdr["Bars"], value=ex.bars)
    xlsx_out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(xlsx_out)


# ---------------------------------------------------------------------------
# Kursdaten
# ---------------------------------------------------------------------------

def fetch_daily(symbol: str, start: date, end: date) -> Optional[pd.DataFrame]:
    import yfinance as yf
    try:
        df = yf.download(
            symbol, start=(start - timedelta(days=40)).isoformat(),
            end=(end + timedelta(days=2)).isoformat(),
            interval="1d", auto_adjust=False, progress=False, threads=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"{symbol}: Download fehlgeschlagen: {exc}")
        return None
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    cols = [c for c in ("Open", "High", "Low", "Close") if c in df.columns]
    return df[cols].dropna()



# ---------------------------------------------------------------------------
# Gegenfakten (A) und Einstiegs-Kontext (C) — User-Auftrag 2026-10-08
# ---------------------------------------------------------------------------
# Review 2026-10-08: 7 von 11 Verlierern liefen erst 0,5-2,1 R fuer uns und
# fielen dann bis zum SL. Ob eine Zwischenstufe zwischen Einstieg und TP1
# geholfen haette, wird hier GEMESSEN, nicht eingefuehrt (Exit-Test laeuft,
# Anti-Ratsche L23). Tagesbalken, deshalb konservativ:
#   - Ein Stop, der durch ein Ereignis in Balken t aktiviert wird, gilt erst
#     ab Balken t+1 (Reihenfolge Hoch/Tief innerhalb eines Tages unbekannt).
#   - Oeffnet ein Balken jenseits des Stops (Gap), zaehlt der Eroeffnungskurs.
#   - Tranchen/Teilverkaeufe der Realitaet sind nicht bekannt: Wird die
#     Gegenfakt-Regel nie ausgeloest, gilt das tatsaechliche R.
CF_LEVELS = (("CF_BE07", 0.7), ("CF_BE10", 1.0))
CF_PARTIAL = ("CF_P10", 1.0, 1 / 3)
CTX_COLS = ["Einstieg_Lage_Pct", "Gap_Einstieg_ATR", "Max_Gap_gegen_ATR"]
CF_COLS = [c for c, _ in CF_LEVELS] + [CF_PARTIAL[0], "CF_Hinweis"]


def _atr14(df: pd.DataFrame) -> pd.Series:
    prev = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - prev).abs(), (df["Low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / 14, adjust=False).mean()


def counterfactuals(df: pd.DataFrame, direction: str, entry: float, sl: float,
                    start: date, end: date, result_r: Optional[float]) -> Optional[dict]:
    """Gegenfakten in R: SL auf Einstand ab +0,7 R / +1,0 R; 1/3 raus bei +1,0 R."""
    if result_r is None or not {"Open", "High", "Low"} <= set(df.columns):
        return None
    short = direction.strip().upper().startswith("S")
    risk = (sl - entry) if short else (entry - sl)
    if risk <= 0:
        return None
    win = df.loc[(df.index.date >= start) & (df.index.date <= end)]
    if win.empty:
        return None
    fav = (lambda b: (entry - b["Low"]) / risk) if short else (lambda b: (b["High"] - entry) / risk)
    out, hinweis = {}, []
    for col, lvl in CF_LEVELS:
        armed, res = False, result_r
        for i, (_, b) in enumerate(win.iterrows()):
            if armed:
                op = b["Open"]
                hit = (b["High"] >= entry) if short else (b["Low"] <= entry)
                if hit:
                    gap = (op > entry) if short else (op < entry)
                    res = round(((entry - op) / risk) if (short and gap) else ((op - entry) / risk) if gap else 0.0, 2)
                    if gap:
                        hinweis.append(f"{col}: Gap ueber Einstand")
                    break
            if fav(b) >= lvl:
                armed = True
        out[col] = res
    col, lvl, part = CF_PARTIAL
    touched = any(fav(b) >= lvl for _, b in win.iterrows())
    out[col] = round(part * lvl + (1 - part) * result_r, 2) if touched else result_r
    out["CF_Hinweis"] = "; ".join(dict.fromkeys(hinweis)) or "Naeherung: Tranchen ignoriert"
    return out


def entry_context(df: pd.DataFrame, direction: str, entry: float, start: date, end: date) -> Optional[dict]:
    """(C) Lage des Einstiegs in der Tagesspanne und Gaps.
    Einstieg_Lage_Pct: 100 = am Tagesextrem in Handelsrichtung (Long: Hoch, Short: Tief), 0 = am Gegenextrem.
    Gap_Einstieg_ATR: Eroeffnung Einstiegstag gegen Vortagesschluss, in ATR-14, positiv = in Handelsrichtung.
    Max_Gap_gegen_ATR: groesstes Eroeffnungs-Gap GEGEN die Position waehrend des Trades (ATR-14, positiv)."""
    if not {"Open", "High", "Low", "Close"} <= set(df.columns):
        return None
    short = direction.strip().upper().startswith("S")
    atr = _atr14(df)
    prev_close = df["Close"].shift(1)
    day = df.loc[df.index.date == start]
    if day.empty:
        return None
    d = day.iloc[0]; i0 = day.index[0]
    rng = d["High"] - d["Low"]
    lage = None
    if rng > 0:
        lage = ((d["High"] - entry) if short else (entry - d["Low"])) / rng * 100
        lage = round(min(max(lage, 0.0), 100.0), 0)
    a0 = atr.shift(1).loc[i0]
    gap0 = None
    if pd.notna(prev_close.loc[i0]) and pd.notna(a0) and a0 > 0:
        g = (d["Open"] - prev_close.loc[i0]) / a0
        gap0 = round(-g if short else g, 2)
    win = df.loc[(df.index.date > start) & (df.index.date <= end)]
    gmax = 0.0
    for idx, b in win.iterrows():
        a = atr.shift(1).loc[idx]
        if pd.isna(a) or a <= 0 or pd.isna(prev_close.loc[idx]):
            continue
        g = (b["Open"] - prev_close.loc[idx]) / a
        against = g if short else -g
        gmax = max(gmax, against)
    return {"Einstieg_Lage_Pct": lage, "Gap_Einstieg_ATR": gap0, "Max_Gap_gegen_ATR": round(gmax, 2)}


# ---------------------------------------------------------------------------
# CSV-Modus (Workflow B, Fix 2026-10-08): Eingaben im Repo statt im Journal
# ---------------------------------------------------------------------------
# Befund 2026-10-08: MFE_R/MAE_R waren in allen Audit-Zeilen leer. Ursachen:
#   (1) der Job lief nie (nur workflow_dispatch, niemand hat ihn angestossen),
#   (2) Symbol/EntryU/SL_U fehlten in 103 von 105 Audit-Zeilen -> jede Zeile
#       waere uebersprungen worden,
#   (3) das Ergebnis landete als separates *_mfe.xlsx im Drive und kam nie
#       ins Arbeits-Journal zurueck,
#   (4) Direktaktien-Trades (A-xxx) standen gar nicht im Audit.
# Neu: Eingaben als state/trade_audit.csv (Schluessel TradeID D-0NN/A-0NN),
# Ergebnis als state/mfe_mae.csv im Repo; merge_into_journal() schreibt es
# beim Journal-Export ins Blatt Trade-Audit. Offene Trades (Verkauf leer)
# werden bis heute gerechnet und als offen markiert.

CSV_OUT_COLS = ["TradeID", "Symbol", "Richtung", "Kauf", "Verkauf", "EntryU", "SL_U", "R",
                "MFE_R", "MAE_R", "Bars", "MFE_Datum", "MAE_Datum", "Klasse",
                "CF_BE07", "CF_BE10", "CF_P10", "CF_Hinweis",
                "Einstieg_Lage_Pct", "Gap_Einstieg_ATR", "Max_Gap_gegen_ATR", "Status"]


def read_csv_rows(path: Path, today: Optional[date] = None) -> list[dict]:
    today = today or date.today()
    df = pd.read_csv(path, dtype=str).fillna("")
    rows = []
    for _, r in df.iterrows():
        tid = r.get("TradeID", "").strip()
        if not tid:
            continue
        end = parse_date(r.get("Verkauf", ""))
        row = {"row": tid, "nr": tid, "symbol": r.get("Symbol", "").strip(),
               "direction": r.get("Richtung", "").strip(), "start": parse_date(r.get("Kauf", "")),
               "end": end or today, "offen": end is None,
               "entry": _num(r.get("EntryU", "")), "sl": _num(r.get("SL_U", "")),
               "result_r": _num(r.get("R", ""))}
        why = []
        if not row["symbol"]:
            why.append("Symbol")
        if row["start"] is None:
            why.append("Datum")
        if row["entry"] is None or row["sl"] is None:
            why.append("EntryU/SL_U")
        row["skip"] = ", ".join(why) if why else None
        rows.append(row)
    return rows


def run_csv(inputs: Path, results_csv: Optional[Path],
            fetch: Callable[[str, date, date], Optional[pd.DataFrame]] = fetch_daily,
            today: Optional[date] = None) -> tuple[list[dict], str]:
    table = []
    for row in read_csv_rows(inputs, today):
        out = {"TradeID": row["nr"], "Symbol": row["symbol"], "Richtung": row["direction"],
               "Kauf": row["start"].isoformat() if row["start"] else "",
               "Verkauf": "" if row["offen"] else row["end"].isoformat(),
               "EntryU": row["entry"], "SL_U": row["sl"], "R": row["result_r"]}
        if row["skip"]:
            table.append({**out, "Status": f"uebersprungen ({row['skip']})"})
            continue
        df = fetch(row["symbol"], row["start"], row["end"])
        ex = compute_mfe_mae(df, row["direction"], row["entry"], row["sl"], row["start"], row["end"]) if df is not None else None
        if ex is None:
            table.append({**out, "Status": "keine Kursdaten" if df is None else "Risiko <= 0 oder Fenster leer"})
            continue
        klasse = "offen" if row["offen"] else classify(ex.mfe_r, ex.mae_r, row["result_r"])
        extra = {}
        cf = None if row["offen"] else counterfactuals(df, row["direction"], row["entry"], row["sl"],
                                                        row["start"], row["end"], row["result_r"])
        if cf:
            extra.update(cf)
        ctx = entry_context(df, row["direction"], row["entry"], row["start"], row["end"])
        if ctx:
            extra.update(ctx)
        table.append({**out, **extra, "MFE_R": ex.mfe_r, "MAE_R": ex.mae_r, "Bars": ex.bars,
                      "MFE_Datum": ex.mfe_date.isoformat() if ex.mfe_date else "",
                      "MAE_Datum": ex.mae_date.isoformat() if ex.mae_date else "",
                      "Klasse": klasse, "Status": "ok (offen)" if row["offen"] else "ok"})
    if results_csv:
        results_csv.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(table, columns=CSV_OUT_COLS).to_csv(results_csv, index=False)
    summ = [{"nr": t["TradeID"], "symbol": t["Symbol"], "direction": t["Richtung"], "mfe_r": t.get("MFE_R"),
             "mae_r": t.get("MAE_R"), "bars": t.get("Bars"), "klasse": t.get("Klasse"),
             "status": "ok" if str(t["Status"]).startswith("ok") else t["Status"]} for t in table]
    return table, render_summary(summ) + "\n\n" + render_counterfactuals(table)


def _f(x) -> Optional[float]:
    try:
        v = float(x)
        return None if v != v else v
    except (TypeError, ValueError):
        return None


def render_counterfactuals(table: list[dict]) -> str:
    """Summen der Gegenfakten ueber alle geschlossenen Trades mit Daten, plus
    Einstiegslage je Verlaufsklasse. Messung, keine Empfehlung."""
    rows = [t for t in table if t.get("Status") == "ok" and _f(t.get("R")) is not None and _f(t.get("CF_BE07")) is not None]
    if not rows:
        return "Gegenfakten: keine Daten."
    n = len(rows)
    real = sum(_f(t["R"]) for t in rows)
    lines = ["## Gegenfakten (Tagesbalken, Naeherung)", "",
             f"{n} geschlossene Trades. Ein durch Balken t ausgeloester Stop gilt ab t+1; Gaps zum Eroeffnungskurs.", "",
             "| Regel | Σ R | Δ zu real | Trades veraendert | davon besser | davon schlechter |", "|---|---|---|---|---|---|",
             f"| real | {real:+.2f} | – | – | – | – |"]
    for col, label in (("CF_BE07", "SL auf Einstand ab +0,7 R"), ("CF_BE10", "SL auf Einstand ab +1,0 R"),
                       ("CF_P10", "1/3 raus bei +1,0 R")):
        tot = sum(_f(t[col]) for t in rows)
        diff = [(_f(t[col]) - _f(t["R"])) for t in rows]
        ch = [d for d in diff if abs(d) > 0.005]
        lines.append(f"| {label} | {tot:+.2f} | {tot - real:+.2f} | {len(ch)} | {sum(1 for d in ch if d > 0)} | {sum(1 for d in ch if d < 0)} |")
    lines += ["", "## Einstiegslage je Verlaufsklasse", "",
              "| Klasse | n | Ø Lage in Tagesspanne (%) | Ø Gap Einstieg (ATR) | Trades mit Gap gegen ≥ 0,5 ATR |", "|---|---|---|---|---|"]
    from collections import defaultdict
    grp = defaultdict(list)
    for t in table:
        if str(t.get("Status", "")).startswith("ok") and t.get("Klasse") not in (None, "offen"):
            grp[t["Klasse"]].append(t)
    for k, ts in sorted(grp.items()):
        la = [_f(t.get("Einstieg_Lage_Pct")) for t in ts if _f(t.get("Einstieg_Lage_Pct")) is not None]
        ga = [_f(t.get("Gap_Einstieg_ATR")) for t in ts if _f(t.get("Gap_Einstieg_ATR")) is not None]
        gg = sum(1 for t in ts if (_f(t.get("Max_Gap_gegen_ATR")) or 0) >= 0.5)
        lines.append(f"| {k} | {len(ts)} | {sum(la)/len(la):.0f} | {sum(ga)/len(ga):+.2f} | {gg} |" if la and ga else f"| {k} | {len(ts)} | – | – | {gg} |")
    return "\n".join(lines)


def _tid(nr) -> Optional[str]:
    if isinstance(nr, (int, float)):
        return f"D-{int(nr):03d}"
    s = str(nr or "").strip()
    if re.fullmatch(r"[AD]-\d{3}", s):
        return s
    if s.isdigit():
        return f"D-{int(s):03d}"
    return None


def merge_into_journal(xlsx_in: Path, results_csv: Path, xlsx_out: Path,
                       inputs_csv: Optional[Path] = None, sheet: str = AUDIT_SHEET) -> dict:
    """Schreibt MFE_R/MAE_R/Bars (und fehlende Symbol/EntryU/SL_U) je TradeID ins
    Blatt Trade-Audit. Direktaktien-Trades (A-xxx), die im Blatt fehlen, werden
    als Zeile angehaengt. Nur Wertzellen, keine Formeln anderer Blaetter."""
    res = pd.read_csv(results_csv, dtype=str).fillna("")
    inp = pd.read_csv(inputs_csv, dtype=str).fillna("") if inputs_csv and Path(inputs_csv).exists() else None
    wb = load_workbook(xlsx_in)
    ws = wb[sheet]
    hdr = {str(c.value).strip(): c.column for c in ws[1] if c.value is not None}
    for col in OUT_COLS:
        if col not in hdr:
            ws.cell(row=1, column=ws.max_column + 1, value=col)
            hdr[col] = ws.max_column
    index = {}
    for r in range(2, ws.max_row + 1):
        t = _tid(ws.cell(row=r, column=hdr["Nr"]).value)
        if t:
            index[t] = r
    stats = {"gefuellt": 0, "angehaengt": 0}

    def put(r, col, val, only_empty=False):
        if col not in hdr or val in ("", None):
            return
        c = ws.cell(row=r, column=hdr[col])
        if only_empty and c.value not in (None, ""):
            return
        num = _num(val)
        c.value = num if num is not None and col not in ("Symbol", "Kauf", "Verkauf", "Richtung") else val

    for _, t in res.iterrows():
        tid = t["TradeID"]
        r = index.get(tid)
        if r is None and tid.startswith("A-"):
            r = ws.max_row + 1
            ws.cell(row=r, column=hdr["Nr"], value=tid)
            put(r, "Instrument", t["Symbol"] + " (Direktaktie)")
            put(r, "Richtung", t["Richtung"]); put(r, "Kauf", t["Kauf"]); put(r, "Verkauf", t["Verkauf"])
            put(r, "R", t.get("R", ""))
            if "Status" in hdr:
                ws.cell(row=r, column=hdr["Status"], value="OFFEN" if not t["Verkauf"] else "CLOSED")
            index[tid] = r
            stats["angehaengt"] += 1
        if r is None:
            continue
        put(r, "Symbol", t["Symbol"], only_empty=True)
        put(r, "EntryU", t["EntryU"], only_empty=True)
        put(r, "SL_U", t["SL_U"], only_empty=True)
        if str(t["Status"]).startswith("ok"):
            put(r, "MFE_R", t["MFE_R"]); put(r, "MAE_R", t["MAE_R"]); put(r, "Bars", t["Bars"])
            for extra in CF_COLS + CTX_COLS:
                if extra in t.index and t[extra] != "":
                    if extra not in hdr:
                        ws.cell(row=1, column=ws.max_column + 1, value=extra)
                        hdr[extra] = ws.max_column
                    put(r, extra, t[extra])
            stats["gefuellt"] += 1
    xlsx_out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(xlsx_out)
    return stats


# ---------------------------------------------------------------------------
# Lauf
# ---------------------------------------------------------------------------

def run(
    xlsx_in: Path,
    xlsx_out: Optional[Path],
    csv_out: Optional[Path],
    fetch: Callable[[str, date, date], Optional[pd.DataFrame]] = fetch_daily,
    sheet: str = AUDIT_SHEET,
) -> tuple[list[dict], str]:
    rows, _ = read_audit_rows(xlsx_in, sheet)
    results: dict[int, Excursion] = {}
    table = []
    for row in rows:
        if row["skip"]:
            table.append({**row, "status": f"uebersprungen ({row['skip']})"})
            continue
        df = fetch(row["symbol"], row["start"], row["end"])
        if df is None:
            table.append({**row, "status": "keine Kursdaten"})
            continue
        ex = compute_mfe_mae(df, row["direction"], row["entry"], row["sl"], row["start"], row["end"])
        if ex is None:
            table.append({**row, "status": "Risiko <= 0 oder Fenster leer"})
            continue
        results[row["row"]] = ex
        table.append({**row, "mfe_r": ex.mfe_r, "mae_r": ex.mae_r, "bars": ex.bars,
                      "klasse": classify(ex.mfe_r, ex.mae_r, row.get("result_r")), "status": "ok"})

    if xlsx_out and results:
        write_results(xlsx_in, xlsx_out, results, sheet)
    if csv_out:
        pd.DataFrame(table).drop(columns=["row"], errors="ignore").to_csv(csv_out, index=False)
    return table, render_summary(table)


def render_summary(table: list[dict]) -> str:
    ok = [t for t in table if t.get("status") == "ok"]
    lines = [f"# MFE/MAE {datetime.now().astimezone().isoformat(timespec='minutes')}", "",
             f"{len(ok)} von {len(table)} Zeilen gerechnet.", ""]
    if ok:
        from collections import Counter
        cnt = Counter(t["klasse"] for t in ok)
        lines.append("| Klassifikation | n |")
        lines.append("|---|---|")
        for k, v in cnt.most_common():
            lines.append(f"| {k} | {v} |")
        lines.append("")
        lines.append("| Nr | Symbol | Ri | MFE_R | MAE_R | Bars | Klassifikation |")
        lines.append("|---|---|---|---|---|---|---|")
        for t in ok:
            lines.append(f"| {t['nr']} | {t['symbol']} | {t['direction'][:1]} | {t['mfe_r']:.2f} | "
                         f"{t['mae_r']:.2f} | {t['bars']} | {t['klasse']} |")
    skipped = [t for t in table if t.get("status") != "ok"]
    if skipped:
        lines += ["", f"Nicht gerechnet ({len(skipped)}):"]
        lines += [f"- Nr {t['nr']} {t.get('symbol') or ''}: {t['status']}" for t in skipped]
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--journal", default=None, help="Journal mit Blatt Trade-Audit (Altmodus)")
    ap.add_argument("--audit-csv", default=None, help="Eingaben als CSV (state/trade_audit.csv) statt Journal")
    ap.add_argument("--results-csv", default=None, help="Ergebnis-CSV (state/mfe_mae.csv)")
    ap.add_argument("--merge-journal", default=None, help="Journal, in das --results-csv eingetragen wird")
    ap.add_argument("--merge-out", default=None, help="Ausgabe-Journal fuer --merge-journal")
    ap.add_argument("--out", default=None, help="Journal-Kopie mit MFE_R/MAE_R (Default: kein Schreiben)")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--md", default=None, help="Markdown-Zusammenfassung in Datei schreiben")
    ap.add_argument("--sheet", default=AUDIT_SHEET)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.merge_journal:
        st = merge_into_journal(Path(args.merge_journal), Path(args.results_csv), Path(args.merge_out),
                                Path(args.audit_csv) if args.audit_csv else None, args.sheet)
        print(f"Trade-Audit: {st['gefuellt']} Zeilen gefuellt, {st['angehaengt']} angehaengt")
        return 0
    if args.audit_csv:
        table, summary = run_csv(Path(args.audit_csv), None if args.dry_run else (Path(args.results_csv) if args.results_csv else None))
    else:
        if not args.journal:
            ap.error("--journal oder --audit-csv angeben")
        out = None if args.dry_run else (Path(args.out) if args.out else None)
        table, summary = run(Path(args.journal), out, Path(args.csv) if args.csv else None, sheet=args.sheet)
    print(summary)
    if args.md:
        Path(args.md).write_text(summary, encoding="utf-8")
    step = os.environ.get("GITHUB_STEP_SUMMARY")
    if step:
        with open(step, "a", encoding="utf-8") as f:
            f.write(summary + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
