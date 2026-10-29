#!/usr/bin/env python3
"""
tiw_events.py — Log und Auswertung der TIW-Ereignisse der Chart-Spur.

User-Entscheid 2026-10-29 (Auto-Archiv „A + B + C“):

  A  Jedes TIW-Ereignis wird geloggt: Schluss jenseits der TIW in ATR, Aktion
     (angekratzt / archiviert / zurueck) und spaeter der Kurs nach 5 und 10
     Handelstagen. Urteil ueber die Toleranz bei n >= 20.
  B  Schluss weniger als 0,25 ATR jenseits einer TIW ohne eigenen Puffer =
     „angekratzt“: Zeile bleibt, Gate rot, kein Entry. Archiviert wird ab
     0,25 ATR oder beim zweiten Schluss jenseits. (Entscheidung faellt im
     Morning Check, hier nur Messung.)
  C  Re-Eval-Filter (nur im Morning Check).

Anlass: Von 12 als TIW-Archiv erkennbaren Zeilen (2026-10-19 bis 2026-10-28)
standen am 2026-10-29 zehn weiter auf der falschen Seite der TIW. Ob das fuer
knappe Brueche genauso gilt, misst erst dieses Log.

Vorzeichen: ``abstand_atr`` ist in Handelsrichtung der Zeile gerechnet —
positiv heisst „auf der richtigen Seite der TIW“, negativ „jenseits“.

Aufrufe:
    python src/tiw_events.py --state-dir state --fill          # Kurse nach 5/10 HT nachtragen
    python src/tiw_events.py --state-dir state --md out.md     # Auswertung
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable, Optional

logger = logging.getLogger("tiw_events")

EVENTS_FILE = "tiw_events.csv"
COLS = [
    "Datum", "Symbol", "Leg", "Klasse", "Richtung", "TIW", "Schluss", "ATR",
    "Abstand_ATR", "Aktion", "Quelle",
    "Kurs_5HT", "Abstand_5HT_ATR", "Zurueck_5HT",
    "Kurs_10HT", "Abstand_10HT_ATR", "Zurueck_10HT",
]
TOLERANZ_ATR = 0.25
MIN_N_URTEIL = 20


def _f(x) -> Optional[float]:
    try:
        if x in (None, ""):
            return None
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return None


def abstand_atr(richtung: str, tiw: float, kurs: float, atr: float) -> Optional[float]:
    """Abstand Kurs ↔ TIW in ATR, positiv = richtige Seite (Long ueber, Short unter)."""
    if not atr or atr <= 0:
        return None
    d = (kurs - tiw) / atr
    return round(d if str(richtung).upper().startswith("L") else -d, 3)


def read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_events(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})


def _key(r: dict) -> tuple:
    return (str(r.get("Datum")), str(r.get("Symbol")).upper(), str(r.get("Leg") or ""), str(r.get("Aktion")))


def event_to_row(ev: dict) -> dict:
    """INBOX-Event (tiw.log) -> CSV-Zeile. Abstand wird hier gerechnet, nicht geglaubt."""
    tiw, schluss, atr = _f(ev.get("tiw")), _f(ev.get("schluss")), _f(ev.get("atr"))
    ab = abstand_atr(ev.get("richtung", ""), tiw, schluss, atr) if None not in (tiw, schluss, atr) else None
    return {
        "Datum": str(ev.get("date"))[:10], "Symbol": ev.get("symbol"), "Leg": ev.get("leg") or "",
        "Klasse": ev.get("klasse") or "", "Richtung": ev.get("richtung"),
        "TIW": tiw, "Schluss": schluss, "ATR": atr, "Abstand_ATR": ab,
        "Aktion": ev.get("aktion"), "Quelle": ev.get("source") or "",
    }


def append_events(state_dir: str | Path, events: Iterable[dict]) -> int:
    """Haengt Events an (idempotent ueber Datum/Symbol/Leg/Aktion). Gibt die Zahl neuer Zeilen zurueck."""
    path = Path(state_dir) / EVENTS_FILE
    rows = read_events(path)
    have = {_key(r) for r in rows}
    neu = 0
    for ev in events or []:
        r = event_to_row(ev)
        if _key(r) in have:
            continue
        rows.append(r)
        have.add(_key(r))
        neu += 1
    if neu or not path.exists():
        rows.sort(key=lambda r: (str(r.get("Datum")), str(r.get("Symbol"))))
        write_events(path, rows)
    return neu


def fill_outcomes(rows: list[dict], closes: Callable[[str, date, date], Optional[list[tuple[date, float]]]],
                  today: Optional[date] = None) -> int:
    """Traegt Kurs/Abstand nach 5 und 10 Handelstagen nach. ``closes(symbol, start, end)``
    liefert sortierte (Datum, Schluss)-Paare. Gibt die Zahl geaenderter Zeilen zurueck."""
    today = today or date.today()
    n = 0
    for r in rows:
        d0 = None
        try:
            d0 = date.fromisoformat(str(r.get("Datum"))[:10])
        except ValueError:
            continue
        if r.get("Kurs_10HT") not in (None, ""):
            continue
        tiw, atr = _f(r.get("TIW")), _f(r.get("ATR"))
        if tiw is None or not atr:
            continue
        ser = closes(str(r.get("Symbol")), d0, min(today, d0 + timedelta(days=21)))
        if not ser:
            continue
        nach = [(d, c) for d, c in ser if d > d0]
        changed = False
        for k in (5, 10):
            if len(nach) >= k and r.get(f"Kurs_{k}HT") in (None, ""):
                c = nach[k - 1][1]
                ab = abstand_atr(r.get("Richtung", ""), tiw, c, atr)
                r[f"Kurs_{k}HT"] = round(c, 4)
                r[f"Abstand_{k}HT_ATR"] = ab
                r[f"Zurueck_{k}HT"] = "ja" if (ab is not None and ab > 0) else "nein"
                changed = True
        n += int(changed)
    return n


def summary(rows: list[dict]) -> dict:
    """Je Bucket (knapp < 0,25 ATR jenseits / weit >= 0,25): n und Quote „zurueck nach 10 HT“."""
    out = {"knapp": {"n": 0, "zurueck": 0}, "weit": {"n": 0, "zurueck": 0}}
    for r in rows:
        if r.get("Aktion") not in ("angekratzt", "archiviert"):
            continue
        ab = _f(r.get("Abstand_ATR"))
        if ab is None or r.get("Zurueck_10HT") in (None, ""):
            continue
        b = "knapp" if ab > -TOLERANZ_ATR else "weit"
        out[b]["n"] += 1
        out[b]["zurueck"] += int(r.get("Zurueck_10HT") == "ja")
    for b in out.values():
        b["quote"] = round(b["zurueck"] / b["n"], 3) if b["n"] else None
    out["urteil_moeglich"] = (out["knapp"]["n"] + out["weit"]["n"]) >= MIN_N_URTEIL
    return out


def render_md(rows: list[dict], stichtag: Optional[date] = None) -> str:
    s = summary(rows)
    st = (stichtag or date.today()).isoformat()
    lines = [f"# TIW-Ereignisse — Stand {st}", "",
             "Reine Messung (Auto-Archiv A, User-Entscheid 2026-10-29). Urteil ueber die",
             f"Toleranz {TOLERANZ_ATR} ATR erst bei n >= {MIN_N_URTEIL} ausgewerteten Ereignissen.", "",
             "| Bucket | n | zurueck nach 10 HT | Quote |", "|---|---|---|---|"]
    for b, lab in (("knapp", f"< {TOLERANZ_ATR} ATR jenseits"), ("weit", f">= {TOLERANZ_ATR} ATR jenseits")):
        q = s[b]["quote"]
        lines.append(f"| {lab} | {s[b]['n']} | {s[b]['zurueck']} | {'—' if q is None else f'{q:.0%}'} |")
    lines += ["", "Urteil moeglich: " + ("ja" if s["urteil_moeglich"] else "nein (n zu klein)"),
              f"Ereignisse gesamt: {len(rows)}"]
    return "\n".join(lines) + "\n"


def _yf_closes(symbol: str, start: date, end: date):
    import mfe_mae
    df = mfe_mae.fetch_daily(symbol, start - timedelta(days=3), end + timedelta(days=2))
    if df is None or df.empty:
        return None
    col = "Close" if "Close" in df.columns else df.columns[-1]
    out = []
    for idx, v in df[col].items():
        try:
            out.append((idx.date() if hasattr(idx, "date") else idx, float(v)))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--state-dir", default="state")
    ap.add_argument("--fill", action="store_true", help="Kurse nach 5/10 HT nachtragen (yfinance)")
    ap.add_argument("--md", help="Auswertung als Markdown schreiben")
    args = ap.parse_args(argv)
    path = Path(args.state_dir) / EVENTS_FILE
    rows = read_events(path)
    if args.fill and rows:
        n = fill_outcomes(rows, _yf_closes)
        write_events(path, rows)
        logger.info("Outcomes nachgetragen: %d Zeilen", n)
    if args.md:
        Path(args.md).write_text(render_md(rows), encoding="utf-8")
    print(render_md(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
