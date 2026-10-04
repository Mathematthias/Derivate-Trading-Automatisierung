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
    if direction.startswith("S"):
        mfe = (entry - lo) / risk
        mae = (hi - entry) / risk
    else:
        mfe = (hi - entry) / risk
        mae = (entry - lo) / risk
    return Excursion(round(mfe, 2), round(mae, 2), int(len(win)))


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
            symbol, start=(start - timedelta(days=3)).isoformat(),
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
    return df[["High", "Low"]].dropna()


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
    ap.add_argument("--journal", required=True)
    ap.add_argument("--out", default=None, help="Journal-Kopie mit MFE_R/MAE_R (Default: kein Schreiben)")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--md", default=None, help="Markdown-Zusammenfassung in Datei schreiben")
    ap.add_argument("--sheet", default=AUDIT_SHEET)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

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
