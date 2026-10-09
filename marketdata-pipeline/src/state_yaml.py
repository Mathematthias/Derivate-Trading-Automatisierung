"""
state_yaml.py — Repo-Zustand als YAML (Workflow B, System-Review 2026-10-04).

Bis zum Review lief der operative Zustand ueber drei Uebersetzungen:
Journal-xlsx (per Chat-Upload hin und her) -> watchlist_sync -> STATE-Doc ->
state_parser -> Digest. Jeder Automat konnte nur einen Brief (INBOX-Markdown)
an den Menschen schreiben, der Morning Check war der Postbote.

Neu: Die Pipeline liest `state/watchlist.yaml`, `state/radar.yaml` und
`state/thesen.yaml` direkt aus dem Repo. Auto-Laeufe liefern typisierte
Aktionen (INBOX-JSON), `inbox_apply.py` wendet sie an und committet. Das
Journal-xlsx bekommt die Watchlist- und Radar-Sheets per Export zurueck
(state_export.py) — es ist dann abgeleitet, nicht mehr Quelle.

Die Trigger-GRAMMATIK bleibt unveraendert: jedes Leg traegt den Text, den
`state_parser._parse_triggers` schon heute versteht. Nichts an filter_engine
muss sich aendern.
"""
from __future__ import annotations

import json
import re
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from state_parser import (
    WatchlistEntry,
    _parse_earliest_date,
    _parse_triggers,
)

logger = logging.getLogger("state_yaml")

SCHEMA_VERSION = 1
GATES = ("🟢", "🟡", "⏳", "🔴")
STATUS_WATCHLIST = ("aktiv", "position", "archiviert")
KLASSEN = (
    "trend_pullback",      # inkl. Momentum-Continuation (Anker EMA20) und EMA200-MeanRev (Anker EMA200)
    "grinder",
    "breakout_retest",
    "thesen_korb",
    "insider",
    "news_catalyst",
    "event_watch",
    "position_monitor",
    "sonstige",
    "reversal",            # GESTRICHEN 2026-10-04 (Review) — nur noch in archivierten Zeilen zulaessig
)
KLASSEN_GESTRICHEN = ("reversal",)

WATCHLIST_FILE = "watchlist.yaml"
RADAR_FILE = "radar.yaml"
THESEN_FILE = "thesen.yaml"
NOTES_FILE = "notes.jsonl"
PROCESSED_FILE = "inbox_processed.json"


# ===========================================================================
# Laden / Speichern
# ===========================================================================

def _read_yaml(path: Path, default: dict) -> dict:
    if not path.exists():
        return dict(default)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            data, f, allow_unicode=True, sort_keys=False, width=1000,
            default_flow_style=False,
        )


def load_state(state_dir: str | Path) -> dict:
    """Liest alle drei Dateien. Fehlende Dateien sind leer, kein Fehler."""
    d = Path(state_dir)
    return {
        "watchlist": _read_yaml(d / WATCHLIST_FILE, {"schema": SCHEMA_VERSION, "entries": []}),
        "radar": _read_yaml(d / RADAR_FILE, {"schema": SCHEMA_VERSION, "rows": []}),
        "thesen": _read_yaml(d / THESEN_FILE, {"schema": SCHEMA_VERSION, "thesen": []}),
    }


def save_state(state_dir: str | Path, state: dict, updated: Optional[datetime] = None) -> None:
    d = Path(state_dir)
    stamp = (updated or datetime.now().astimezone()).isoformat(timespec="seconds")
    for key, fname in (("watchlist", WATCHLIST_FILE), ("radar", RADAR_FILE), ("thesen", THESEN_FILE)):
        block = state[key]
        block["schema"] = SCHEMA_VERSION
        block["updated"] = stamp
        _write_yaml(d / fname, block)


# ===========================================================================
# Watchlist -> WatchlistEntry (fuer filter_engine)
# ===========================================================================

def _legs_to_trigger_raw(entry: dict) -> str:
    """Baut den Trigger-Text, den state_parser versteht: '🟢 A) … · 🔴 B) …'.

    Archivierte Zeilen bekommen alle Legs mit 🔴 — so verhaelt sich die
    Pipeline wie bisher (Stufe 1 ueberspringt, Stufe 2 nimmt das Symbol wieder
    auf, der Pull behaelt die Kurse fuer den Re-Eval-Check).
    """
    archived = entry.get("status") == "archiviert"
    parts = []
    for leg in entry.get("legs", []) or []:
        text = str(leg.get("text", "")).strip()
        if not text:
            continue
        gate = "🔴" if archived else (leg.get("gate") or "🟡")
        label = str(leg.get("label", "")).strip()
        parts.append(f"{gate} {label}) {text}" if label else f"{gate} {text}")
    return " · ".join(parts)


def _iso_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def entries_from_yaml(block: dict) -> list[WatchlistEntry]:
    """YAML-Eintraege -> WatchlistEntry-Objekte (dieselbe Klasse wie aus dem STATE-Doc)."""
    out: list[WatchlistEntry] = []
    for e in block.get("entries", []) or []:
        symbol = str(e.get("symbol", "")).strip()
        if not symbol:
            continue
        trigger_raw = _legs_to_trigger_raw(e)
        if not trigger_raw:
            continue
        name = str(e.get("name", symbol) or symbol)
        # Positions-Monitore erkennt digest_renderer am "[MONITOR"-Token im
        # Namen (oder an der Richtung). Der YAML-Status ist die Wahrheit —
        # fehlt das Token (DB1.DE #93 im Journal vom 2026-10-02), wird es
        # ergaenzt, damit die Zeile in Bucket 📍 landet und nicht als Kandidat.
        if e.get("status") == "position" and "[MONITOR" not in name.upper():
            nr = e.get("trade_nr")
            name = f"{name} [MONITOR{(' #' + str(nr)) if nr else ''}]"
        out.append(WatchlistEntry(
            name=name,
            symbol=symbol,
            direction=str(e.get("direction", "LONG")).upper(),
            trigger_raw=trigger_raw,
            status="aktiv",
            status_note=str(e.get("klasse", "")),
            triggers=_parse_triggers(trigger_raw),
            earliest_date=_parse_earliest_date(trigger_raw),
            expiry_date=_iso_date(e.get("expiry")),
            # Der YAML-Status muss bis in den Digest durch: watchlist_expiry
            # filtert archivierte Zeilen, Stufe 1 laesst Positionen aus.
            state_status=str(e.get("status") or "aktiv"),
        ))
    return out


def load_watchlist_yaml(path: str | Path) -> list[WatchlistEntry]:
    block = _read_yaml(Path(path), {"entries": []})
    entries = entries_from_yaml(block)
    logger.info(f"state_yaml: {len(entries)} Watchlist-Eintraege aus {path}")
    return entries


_TIW_META_RE = re.compile(
    r"TIW[^.]{0,40}?(?P<dir>unter|ueber|über)\s*(?P<val>\d{1,3}(?:\.\d{3})*,\d+|\d+,\d+|\d+)",
    re.IGNORECASE)
_REEVAL_META_RE = re.compile(
    r"RE[-\s]?EVAL\s*:\s*1D-Schluss\s*(?P<op>[<>])\s*(?P<val>\d{1,3}(?:\.\d{3})*,\d+|\d+,\d+|\d+)",
    re.IGNORECASE)


def _de_zahl(s: str) -> Optional[float]:
    try:
        return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)
    except (ValueError, AttributeError):
        return None


# Relative TIW (Skill v58, 2026-10-09): „TIW = 1D-Schluss unter EMA50-1D -0,30 ATR".
# Dieselbe Grammatik wie skill/tiw_rel.py. Das Level loest der Morning Check mit
# den Universe-Werten auf (EMA/ATR, am laufenden Balken zurueckgerechnet).
_TIW_REL_META_RE = re.compile(
    r"TIW[^.]{0,40}?(?P<dir>unter|ueber|über)\s*(?P<anker>EMA\s?(?:20|50|100|200))(?:-1D)?"
    r"(?:\s*(?P<sign>[+\-−–])\s*(?P<off>\d+(?:,\d+)?)\s*(?:x\s*)?ATR(?:-1D|-14)?)?",
    re.IGNORECASE)


def _leg_tiw(text: str) -> Optional[dict]:
    """TIW-Schlussbedingung aus einem Leg-Text.

    Fest:     {"seite": "unter"|"ueber", "level": x}
    Relativ:  {"seite": …, "level": None, "anker": "EMA50", "off": -0.3}
    """
    m = _TIW_META_RE.search(str(text or ""))
    if m:
        v = _de_zahl(m.group("val"))
        if v is not None:
            return {"seite": "ueber" if m.group("dir").lower().startswith(("ue", "üb")) else "unter",
                    "level": v}
    r = _TIW_REL_META_RE.search(str(text or ""))
    if not r:
        return None
    off = _de_zahl(r.group("off")) if r.group("off") else 0.0
    if off and r.group("sign") in ("-", "−", "–"):
        off = -off
    return {"seite": "ueber" if r.group("dir").lower().startswith(("ue", "üb")) else "unter",
            "level": None, "anker": r.group("anker").upper().replace(" ", ""), "off": off or 0.0}


def _leg_reeval(text: str) -> Optional[dict]:
    """RE-EVAL-Schlussbedingung (nur die maschinenlesbare Form
    „RE-EVAL: 1D-Schluss >X"): {"op": ">"|"<", "level": x}."""
    m = _REEVAL_META_RE.search(str(text or ""))
    if not m:
        return None
    v = _de_zahl(m.group("val"))
    return None if v is None else {"op": m.group("op"), "level": v}


def watchlist_meta(block: dict) -> list[dict]:
    """Schlanke Metadaten je Eintrag fuer den Digest (Klasse, Anker, Treiber,
    Verfall, Gates) — das, was der Morning Check braucht und bisher nirgends
    stand.

    Seit 2026-10-07 zusaetzlich je Eintrag `tiw` (aus dem ersten Leg mit
    TIW-Klausel) und `reeval` (aus dem ersten Leg mit „RE-EVAL: 1D-Schluss
    >/<X"). Damit sieht der Morning Check geparkte aktive Zeilen (alle Legs 🔴)
    samt TIW-Lage und archivierte Zeilen, deren Re-Eval naeherrueckt — beides
    stand vorher nur im Parked-Gate-Audit (Anlass VOS.DE)."""
    out = []
    for e in block.get("entries", []) or []:
        legs = e.get("legs") or []
        tiw = next((t for t in (_leg_tiw(l.get("text")) for l in legs) if t), None)
        reeval = next((r for r in (_leg_reeval(l.get("text")) for l in legs) if r), None)
        out.append({
            "symbol": e.get("symbol"),
            "name": e.get("name"),
            "direction": e.get("direction"),
            "klasse": e.get("klasse"),
            "anker": e.get("anker"),
            "treiber": e.get("treiber") or None,
            "status": e.get("status"),
            "expiry": e.get("expiry"),
            "gates": [l.get("gate") for l in (e.get("legs") or [])],
            "trade_nr": e.get("trade_nr"),
            "tiw": tiw,
            "reeval": reeval,
        })
    return out


# ===========================================================================
# INBOX-Vertrag: typisierte Aktionen
# ===========================================================================
#
# {"schema": 1, "source": "thesen-lauf", "generated": "2026-10-03T09:12:00+02:00",
#  "actions": [
#    {"op": "watchlist.set_status", "symbol": "SZG.DE", "status": "archiviert", "reason": "TIW gebrochen"},
#    {"op": "watchlist.set_gate",   "symbol": "ENR.DE", "leg": "B", "gate": "🔴"},
#    {"op": "watchlist.set_expiry", "symbol": "JNJ", "expiry": "2026-10-13"},
#    {"op": "watchlist.add",        "entry": {...wie in watchlist.yaml...}},
#    {"op": "watchlist.set_field",  "symbol": "PRY.MI", "field": "treiber", "value": "Q3 2026-10-29"},
#    {"op": "radar.add",            "row": {"date": "2026-10-28", "kat": 1, "ereignis": "...", "werte": "GOOGL", "wirkung": "...", "quelle": "..."}},
#    {"op": "radar.set_status",     "id": "Z16", "status": "erledigt", "note": "..."},
#    {"op": "radar.set_field",      "id": "Z19", "field": "date", "value": "2027-01-10"},
#    {"op": "thesen.update",        "id": "A", "verdikt": "spielen", "re_check": "2026-10-09", "crowdedness_pp": 4.52, "korb_budget_pct": 4, "note": "..."},
#    {"op": "note.add",             "kategorie": "INFO", "text": "..."}
#  ]}
#
# Jede Aktion ist idempotent (gleicher Zustand bei Wiederholung). Unbekannte
# Ops werden protokolliert und uebersprungen — ein Lauf mit einer neuen Op
# darf die anderen nicht blockieren.

class InboxError(ValueError):
    pass


def _find_entry(block: dict, symbol: str) -> Optional[dict]:
    for e in block.get("entries", []) or []:
        if str(e.get("symbol", "")).upper() == symbol.upper():
            return e
    return None


def _next_radar_id(block: dict) -> str:
    nums = []
    for r in block.get("rows", []) or []:
        rid = str(r.get("id", ""))
        if rid.startswith("Z") and rid[1:].isdigit():
            nums.append(int(rid[1:]))
    return f"Z{(max(nums) + 1) if nums else 1}"


def apply_actions(state: dict, actions: list[dict], today: Optional[date] = None) -> list[str]:
    """Wendet Aktionen auf den Zustand an (in-place) und gibt ein Log zurueck."""
    today = today or date.today()
    log: list[str] = []
    wl, radar, thesen = state["watchlist"], state["radar"], state["thesen"]
    wl.setdefault("entries", [])
    radar.setdefault("rows", [])
    thesen.setdefault("thesen", [])

    for i, a in enumerate(actions or []):
        op = str(a.get("op", ""))
        try:
            if op == "watchlist.set_status":
                e = _find_entry(wl, a["symbol"])
                if e is None:
                    raise InboxError(f"Symbol {a['symbol']} nicht in watchlist.yaml")
                status = a["status"]
                if status not in STATUS_WATCHLIST:
                    raise InboxError(f"unbekannter Status {status!r}")
                e["status"] = status
                if status == "archiviert":
                    e["archived"] = {"date": today.isoformat(), "reason": a.get("reason", "")}
                log.append(f"watchlist {a['symbol']}: status -> {status}")

            elif op == "watchlist.set_gate":
                e = _find_entry(wl, a["symbol"])
                if e is None:
                    raise InboxError(f"Symbol {a['symbol']} nicht in watchlist.yaml")
                if a["gate"] not in GATES:
                    raise InboxError(f"unbekanntes Gate {a['gate']!r}")
                hit = False
                for leg in e.get("legs", []) or []:
                    if str(leg.get("label", "")).upper() == str(a["leg"]).upper():
                        leg["gate"] = a["gate"]
                        hit = True
                if not hit:
                    raise InboxError(f"Leg {a['leg']} fehlt bei {a['symbol']}")
                log.append(f"watchlist {a['symbol']} Leg {a['leg']}: gate -> {a['gate']}")

            elif op == "watchlist.set_expiry":
                e = _find_entry(wl, a["symbol"])
                if e is None:
                    raise InboxError(f"Symbol {a['symbol']} nicht in watchlist.yaml")
                if _iso_date(a["expiry"]) is None:
                    raise InboxError(f"Verfall {a['expiry']!r} kein ISO-Datum")
                e["expiry"] = str(a["expiry"])[:10]
                log.append(f"watchlist {a['symbol']}: expiry -> {e['expiry']}")

            elif op == "watchlist.set_field":
                e = _find_entry(wl, a["symbol"])
                if e is None:
                    raise InboxError(f"Symbol {a['symbol']} nicht in watchlist.yaml")
                field = a["field"]
                if field in ("symbol", "legs", "status"):
                    raise InboxError(f"Feld {field!r} nicht per set_field aenderbar")
                e[field] = a.get("value")
                log.append(f"watchlist {a['symbol']}: {field} -> {a.get('value')!r}")

            elif op == "watchlist.add":
                entry = dict(a["entry"])
                sym = str(entry.get("symbol", "")).strip()
                if not sym:
                    raise InboxError("watchlist.add ohne symbol")
                if not entry.get("legs"):
                    raise InboxError(f"watchlist.add {sym} ohne legs")
                entry.setdefault("status", "aktiv")
                entry.setdefault("klasse", "sonstige")
                entry.setdefault("added", today.isoformat())
                if _find_entry(wl, sym) is not None:
                    # Idempotent: vorhandenen Eintrag ersetzen, nicht doppeln
                    wl["entries"] = [x for x in wl["entries"] if str(x.get("symbol", "")).upper() != sym.upper()]
                    log.append(f"watchlist {sym}: ersetzt")
                else:
                    log.append(f"watchlist {sym}: neu")
                wl["entries"].append(entry)

            elif op == "radar.add":
                row = dict(a["row"])
                if _iso_date(row.get("date")) is None:
                    raise InboxError("radar.add ohne gueltiges Datum")
                # Idempotent ueber (date, ereignis)
                dup = [r for r in radar["rows"] if r.get("date") == row.get("date")
                       and r.get("ereignis") == row.get("ereignis")]
                if dup:
                    log.append(f"radar: {row.get('ereignis')!r} bereits vorhanden")
                else:
                    row.setdefault("id", _next_radar_id(radar))
                    row.setdefault("status", "offen")
                    row.setdefault("added", today.isoformat())
                    radar["rows"].append(row)
                    log.append(f"radar {row['id']}: neu ({row['date']})")

            elif op == "radar.set_status":
                hit = [r for r in radar["rows"] if str(r.get("id")) == str(a["id"])]
                if not hit:
                    raise InboxError(f"Radar-Zeile {a['id']} fehlt")
                hit[0]["status"] = a["status"]
                if a.get("note"):
                    hit[0]["note"] = a["note"]
                log.append(f"radar {a['id']}: status -> {a['status']}")

            elif op == "radar.set_field":
                hit = [r for r in radar["rows"] if str(r.get("id")) == str(a["id"])]
                if not hit:
                    raise InboxError(f"Radar-Zeile {a['id']} fehlt")
                if a["field"] == "id":
                    raise InboxError("id nicht aenderbar")
                hit[0][a["field"]] = a.get("value")
                log.append(f"radar {a['id']}: {a['field']} -> {a.get('value')!r}")

            elif op == "thesen.update":
                tid = str(a["id"])
                hit = [t for t in thesen["thesen"] if str(t.get("id")) == tid]
                if not hit:
                    t = {"id": tid, "titel": a.get("titel", tid)}
                    thesen["thesen"].append(t)
                    hit = [t]
                    log.append(f"these {tid}: neu")
                t = hit[0]
                for k in ("verdikt", "re_check", "crowdedness_pp", "korb_budget_pct",
                          "falsifikat", "ausdruecke", "titel", "note"):
                    if k in a:
                        t[k] = a[k]
                hist = t.setdefault("historie", [])
                hist.append({"date": today.isoformat(), "verdikt": a.get("verdikt", t.get("verdikt")),
                             "crowdedness_pp": a.get("crowdedness_pp"), "source": a.get("source")})
                log.append(f"these {tid}: {t.get('verdikt')} / re_check {t.get('re_check')}")

            elif op == "note.add":
                # Notes landen in notes.jsonl (append-only), hier nur Log.
                state.setdefault("_notes", []).append({
                    "date": today.isoformat(), "kategorie": a.get("kategorie", "INFO"),
                    "text": a.get("text", ""), "source": a.get("source"),
                })
                log.append(f"note: {str(a.get('text', ''))[:60]}")

            else:
                log.append(f"⚠️ unbekannte Op {op!r} (Aktion {i}) uebersprungen")
        except (KeyError, InboxError) as exc:
            log.append(f"⚠️ Aktion {i} ({op}) verworfen: {exc}")
    return log


def append_notes(state_dir: str | Path, notes: list[dict]) -> None:
    if not notes:
        return
    p = Path(state_dir) / NOTES_FILE
    with open(p, "a", encoding="utf-8") as f:
        for n in notes:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")


def load_processed(state_dir: str | Path) -> dict:
    p = Path(state_dir) / PROCESSED_FILE
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_processed(state_dir: str | Path, processed: dict) -> None:
    p = Path(state_dir) / PROCESSED_FILE
    with open(p, "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=1, sort_keys=True)


# ===========================================================================
# Radar / Thesen fuer den Digest
# ===========================================================================

def radar_window(block: dict, today: date, days: int = 28) -> dict:
    """Einrueckende (<= days) und ueberfaellige offene Radar-Zeilen."""
    einr, ueber = [], []
    for r in block.get("rows", []) or []:
        if str(r.get("status", "offen")).lower() != "offen":
            continue
        d = _iso_date(r.get("date"))
        if d is None:
            continue
        delta = (d - today).days
        row = {"id": r.get("id"), "date": d.isoformat(), "tage": delta,
               "kat": r.get("kat"), "ereignis": r.get("ereignis"),
               "werte": r.get("werte"), "wirkung": r.get("wirkung")}
        if delta < 0:
            ueber.append(row)
        elif delta <= days:
            einr.append(row)
    einr.sort(key=lambda x: x["tage"])
    ueber.sort(key=lambda x: x["tage"])
    return {"einrueckend": einr, "ueberfaellig": ueber}


def thesen_aktiv(block: dict, today: date) -> list[dict]:
    out = []
    for t in block.get("thesen", []) or []:
        if str(t.get("verdikt", "")).lower() == "verworfen":
            continue
        rc = _iso_date(t.get("re_check"))
        out.append({
            "id": t.get("id"), "titel": t.get("titel"), "verdikt": t.get("verdikt"),
            "korb_budget_pct": t.get("korb_budget_pct"),
            "crowdedness_pp": t.get("crowdedness_pp"),
            "re_check": rc.isoformat() if rc else None,
            "re_check_faellig": (rc is not None and rc <= today),
            "ausdruecke": t.get("ausdruecke"),
        })
    out.sort(key=lambda x: x["re_check"] or "9999")
    return out


def state_for_digest(state: dict, today: date) -> dict:
    return {
        "watchlist": watchlist_meta(state["watchlist"]),
        "radar": radar_window(state["radar"], today),
        "thesen": thesen_aktiv(state["thesen"], today),
        "updated": {
            "watchlist": state["watchlist"].get("updated"),
            "radar": state["radar"].get("updated"),
            "thesen": state["thesen"].get("updated"),
        },
    }
