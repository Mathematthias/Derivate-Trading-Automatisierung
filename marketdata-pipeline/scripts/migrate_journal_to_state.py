#!/usr/bin/env python3
"""
migrate_journal_to_state.py — Einmalige Migration Journal-xlsx -> state/*.yaml
(Workflow B, System-Review 2026-10-04).

Liest die Sheets "Watchlist" und "Termin-Radar" aus dem Trading-Journal und
schreibt `state/watchlist.yaml` und `state/radar.yaml`. Optional werden die
Klassen-Entscheide des Reviews gleich angewendet (--apply-review-2026-10-04).

Aufruf:
    PYTHONPATH=./src python scripts/migrate_journal_to_state.py \
        Trading_Journal_20261002c.xlsx --state-dir state --apply-review-2026-10-04

Das Skript ist idempotent (schreibt die Dateien vollstaendig neu) und
veraendert das Journal NICHT.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import state_yaml as sy  # noqa: E402

GATE_CHARS = "🟢🟡⏳🔴📍"


# ---------------------------------------------------------------------------
# Klassen-Erkennung (Zuordnungstest-Token hat Vorrang vor Freitext)
# ---------------------------------------------------------------------------

def _klasse_und_anker(richtung: str, trigger_a: str) -> tuple[str, str]:
    s = f"{richtung} {trigger_a}".upper()
    m = re.search(r"\[KLASSE:\s*([^|\]]+)\|\s*ANKER:\s*([^|\]]+)", s)
    anker = ""
    if m:
        anker = m.group(2).strip().split(" ")[0]
    if "POSITION-MONITOR" in s:
        return "position_monitor", anker
    if "EVENT-WATCH" in s:
        return "event_watch", anker
    if "GRINDER" in s:
        return "grinder", anker or "EMA20"
    if "BREAKOUT" in s and "RETEST" not in s and "[BREAKOUT]" in s:
        return "breakout_retest", anker or "Struktur"
    if "BREAKDOWN-RETEST" in s or "BREAKOUT-RETEST" in s:
        return "breakout_retest", anker or "Struktur"
    if "NEWS-CATALYST" in s:
        return "news_catalyst", anker or "Struktur"
    if "INSIDER" in s:
        return "insider", anker
    if "KORB" in s:
        return "thesen_korb", anker
    if "BOUNCE-REVERSAL" in s or "REVERSAL" in s or "MEANREV" in s or "MEAN-REV" in s:
        if "EMA200" in s:
            return "trend_pullback", "EMA200"
        return "reversal", anker
    if "MOMENTUM-CONTINUATION" in s:
        # Entscheid 2026-10-04: geht in Trend-Pullback auf, Anker EMA20
        return "trend_pullback", anker or "EMA20"
    if "TREND-PULLBACK" in s or "PULLBACK" in s:
        if not anker:
            mm = re.search(r"TOUCH\s+EMA(\d+)", s)
            anker = f"EMA{mm.group(1)}" if mm else "EMA20"
        return "trend_pullback", anker
    return "sonstige", anker


def _iso(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return ""


def _gate(cell) -> str:
    s = str(cell or "")
    for ch in GATE_CHARS:
        if ch in s:
            return "🟢" if ch == "📍" else ch
    return "🟡"


def read_watchlist(xlsx: Path) -> list[dict]:
    wb = load_workbook(xlsx, data_only=True)
    ws = wb["Watchlist"]
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(h or "").strip().lower() for h in rows[0]]

    def col(*cands):
        for c in cands:
            for j, h in enumerate(hdr):
                if c in h:
                    return j
        return None

    c_akt, c_sym, c_ri = col("aktie"), col("symbol"), col("richtung")
    c_ga, c_ta = col("🚦 a"), col("trigger a")
    c_gb, c_tb = col("🚦 b"), col("trigger b")
    c_gc, c_tc = col("🚦 c"), col("trigger c")
    c_bem, c_add, c_ver = col("bemerk"), col("hinzugef"), col("verfall")

    entries = []
    for i, r in enumerate(rows[1:], start=2):
        if r is None or all(c is None for c in r):
            continue

        def cell(j):
            return "" if j is None or j >= len(r) or r[j] is None else str(r[j]).strip()

        symbol, name, richtung = cell(c_sym), cell(c_akt), cell(c_ri)
        if not symbol:
            continue
        ta, tb, tc = cell(c_ta), cell(c_tb), cell(c_tc)
        legs = []
        for lab, g, t in (("A", c_ga, ta), ("B", c_gb, tb), ("C", c_gc, tc)):
            if t:
                legs.append({"label": lab, "gate": _gate(cell(g)), "text": t})
        if not legs:
            continue
        archived = ("ARCHIVIERT" in richtung.upper()) or ("ARCHIVIERT" in ta.upper()) or \
                   all(l["gate"] == "🔴" for l in legs)
        klasse, anker = _klasse_und_anker(richtung, ta)
        is_pos = klasse == "position_monitor" or "📍" in cell(c_ga)
        status = "archiviert" if archived else ("position" if is_pos else "aktiv")
        direction = "SHORT" if "SHORT" in richtung.upper()[:60] else "LONG"
        trade_nr = None
        m = re.search(r"#(\d{1,3})(?:\s*AV)?", ta) if is_pos else None
        if m:
            trade_nr = m.group(1) + (" AV" if "AV" in ta[m.end():m.end() + 4] else "")
        e = {
            "symbol": symbol, "name": name, "direction": direction,
            "klasse": klasse, "anker": anker, "treiber": "",
            "status": status, "added": _iso(cell(c_add)), "expiry": _iso(cell(c_ver)),
            "legs": legs, "notes": cell(c_bem)[:600], "journal_row": i,
        }
        if trade_nr:
            e["trade_nr"] = trade_nr
        if archived:
            reason = ""
            mm = re.search(r"ARCHIVIERT\s*(\d{4}-\d{2}-\d{2})?\s*[—\-\(]*\s*([^\)\]]{0,160})", richtung + " " + ta)
            if mm:
                reason = (mm.group(2) or "").strip()
            e["archived"] = {"date": (mm.group(1) if mm and mm.group(1) else ""), "reason": reason}
        entries.append(e)
    return entries


def read_radar(xlsx: Path) -> list[dict]:
    wb = load_workbook(xlsx, data_only=True)
    if "Termin-Radar" not in wb.sheetnames:
        return []
    ws = wb["Termin-Radar"]
    rows = list(ws.iter_rows(values_only=True))
    hdr_i = next(i for i, r in enumerate(rows) if r and str(r[0] or "").strip().lower() == "datum")
    out = []
    for i, r in enumerate(rows[hdr_i + 1:], start=hdr_i + 2):
        if r is None or all(c is None for c in r):
            continue
        d = _iso(r[0])
        ereignis = str(r[2] or "").strip()
        if not d or not ereignis:
            continue            # Datum ohne Ereignis = leere Journal-Zeile
        kat = r[1]
        try:
            kat = int(kat) if kat not in (None, "") else None
        except (TypeError, ValueError):
            kat = str(kat)
        # Status-Zelle: erstes Wort ist der Status, der Rest (nach " | " oder
        # Klammer) ist eine Pflege-Notiz in Originalschreibung.
        status_raw = str(r[5] or "offen").strip()
        m = re.match(r"\s*(offen|erledigt|verworfen|verschoben)\b(.*)$", status_raw, re.IGNORECASE)
        if m:
            status = m.group(1).lower()
            note = m.group(2).strip(" |—-")
        else:
            status, note = "offen", status_raw
        row = {
            "id": f"Z{i}", "date": d, "kat": kat,
            "ereignis": ereignis, "werte": str(r[3] or "").strip(),
            "wirkung": str(r[4] or "").strip(),
            "status": status,
            "quelle": str(r[6] or "").strip() if len(r) > 6 else "",
        }
        if note:
            row["note"] = note
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Review-Entscheide 2026-10-04 (User)
# ---------------------------------------------------------------------------

REVIEW_ARCHIVE = {
    "HLMA.L": "Reversal/Counter-Trend-Klasse gestrichen (Review 2026-10-04)",
    "LIN": "Short-Grinder ohne Katalysator (Entscheid 2026-10-04)",
    "HLN.L": "Short-Grinder ohne Katalysator (Entscheid 2026-10-04)",
    "ALC.SW": "Short-Grinder ohne Katalysator (Entscheid 2026-10-04)",
    "HOLN.SW": "Short-Grinder ohne Katalysator (Entscheid 2026-10-04)",
    "ZTS": "Short-Trend-Pullback auf Defensive ohne Katalysator (Entscheid 2026-10-04)",
}

# Breakout-Legs -> Breakout-Retest (Definition: bestaetigter Schluss ueber dem
# Niveau mit Vol >= 1,2x, danach Rueckkehr in Niveau -0,5/+0,75 ATR, Einstieg
# Stop-Buy ueber dem Hoch der Retest-Kerze, SL unter Retest-Tief - 0,3 ATR,
# L4-Floor 1,5 ATR).
REVIEW_RETEST = {
    "GIVN.SW": "nach 2026-10-05 BREAKOUT-RETEST-LONG: Niveau 3481,00€ (Range-Hoch). Bedingung: Daily-Close >3481,00€ + Vol >=1,2x Avg-20d bestaetigt, danach Touch 3481,00€ -0,50/+0,75 ATR [pullback] + 4h-Bullish-Reverse-Close (MANUELL). Einstieg Stop-Buy ueber Hoch der Retest-Kerze. SL = MIN(Entry-1,5xATR ; Retest-Tief-0,30xATR). TIW = 1D-Schluss unter 3481,00€. TP1 Measured Move (Range-Hoehe), TP2 Runner/Chandelier.",
    "TMO": "nach 2026-10-05 BREAKOUT-RETEST-LONG: Niveau 651,77$ (Range-Hoch). Bedingung: Daily-Close >651,77$ + Vol >=1,2x Avg-20d bestaetigt, danach Touch 651,77$ -0,50/+0,75 ATR [pullback] + 4h-Bullish-Reverse-Close (MANUELL). Einstieg Stop-Buy ueber Hoch der Retest-Kerze. SL = MIN(Entry-1,5xATR ; Retest-Tief-0,30xATR). TIW = 1D-Schluss unter 651,77$. TP1 Measured Move (Range-Hoehe), TP2 Runner/Chandelier.",
}


def apply_review(entries: list[dict], today: str) -> list[str]:
    log = []
    for e in entries:
        sym = e["symbol"]
        if sym in REVIEW_ARCHIVE and e["status"] != "archiviert":
            e["status"] = "archiviert"
            e["archived"] = {"date": today, "reason": REVIEW_ARCHIVE[sym]}
            log.append(f"{sym}: archiviert — {REVIEW_ARCHIVE[sym]}")
        if sym in REVIEW_RETEST and e["status"] == "aktiv":
            # Leg A (bzw. das Breakout-Leg) ersetzen, uebrige Legs behalten
            for leg in e["legs"]:
                if "[breakout]" in leg["text"] or "BREAKOUT" in leg["text"].upper():
                    leg["text"] = REVIEW_RETEST[sym]
                    leg["gate"] = "🟡"
                    log.append(f"{sym} Leg {leg['label']}: auf Breakout-Retest umgeschrieben")
            e["klasse"] = "breakout_retest"
            e["anker"] = "Struktur"
        if e.get("klasse") == "reversal" and e["status"] == "aktiv":
            e["status"] = "archiviert"
            e["archived"] = {"date": today, "reason": "Reversal-Klasse gestrichen (Review 2026-10-04)"}
            log.append(f"{sym}: Reversal-Zeile archiviert")
    return log


THESEN_SEED_2026_10_03 = [
    {"id": "A", "titel": "AI-Strom/Elektrifizierung", "verdikt": "spielen", "korb_budget_pct": 4,
     "crowdedness_pp": 4.52, "re_check": "2026-10-09",
     "falsifikat": "(a) Hyperscaler-Capex-Cut (Messtermin Q3-Calls Ende Oktober, Alphabet 2026-10-28); (b) book-to-bill < 1 (PRY 2026-10-29, ENR 2026-11-11)",
     "ausdruecke": ["PRY.MI", "NEX.PA", "ENR.DE"], "note": "Re-Check 2026-10-02 war ueberfaellig (Thesen-Lauf 2026-10-03); naechster Termin vorlaeufig +1 Woche"},
    {"id": "OEL", "titel": "Oel/Hormus", "verdikt": "spielen", "korb_budget_pct": 2,
     "crowdedness_pp": 6.81, "re_check": "2026-10-05",
     "falsifikat": "Brent-Schluss < 88 USD ODER Waffenruhe/Deeskalationsvereinbarung USA-Iran",
     "ausdruecke": ["ENI.MI"], "note": "Budget-Entscheid 1 % vs 2 % am 2026-10-05 (Crowdedness vs. Gap-Risiko)"},
    {"id": "STAHL", "titel": "EU-Stahl melt-and-pour", "verdikt": "beobachten", "korb_budget_pct": 0,
     "crowdedness_pp": -11.84, "re_check": "2026-10-10",
     "falsifikat": "HRC Nordeuropa unter 745 EUR/t am 2026-11-12", "ausdruecke": []},
    {"id": "N2", "titel": "UK-Ersterwerber (N-2)", "verdikt": "beobachten", "korb_budget_pct": 0,
     "crowdedness_pp": None, "re_check": "2026-10-29", "falsifikat": "", "ausdruecke": []},
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("journal")
    ap.add_argument("--state-dir", default="state")
    ap.add_argument("--apply-review-2026-10-04", action="store_true")
    ap.add_argument("--seed-thesen", action="store_true", help="thesen.yaml mit dem Stand 2026-10-03 vorbelegen")
    ap.add_argument("--today", default=date.today().isoformat())
    a = ap.parse_args()

    xlsx = Path(a.journal)
    entries = read_watchlist(xlsx)
    radar = read_radar(xlsx)
    print(f"Watchlist: {len(entries)} Zeilen ({sum(e['status']=='aktiv' for e in entries)} aktiv, "
          f"{sum(e['status']=='position' for e in entries)} Positionen, "
          f"{sum(e['status']=='archiviert' for e in entries)} archiviert); Radar: {len(radar)} Zeilen")
    if a.apply_review_2026_10_04:
        for line in apply_review(entries, a.today):
            print("  review:", line)
    state = sy.load_state(a.state_dir)
    state["watchlist"] = {"schema": sy.SCHEMA_VERSION, "source": f"migriert aus {xlsx.name} am {a.today}", "entries": entries}
    state["radar"] = {"schema": sy.SCHEMA_VERSION, "source": f"migriert aus {xlsx.name} am {a.today}", "rows": radar}
    if a.seed_thesen or not state["thesen"].get("thesen"):
        state["thesen"] = {"schema": sy.SCHEMA_VERSION, "source": "Thesen-Lauf 2026-10-03", "thesen": THESEN_SEED_2026_10_03}
    sy.save_state(a.state_dir, state)
    print("geschrieben:", Path(a.state_dir).resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
