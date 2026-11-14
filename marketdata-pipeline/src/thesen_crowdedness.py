"""Crowdedness der Thesen taeglich vorrechnen (Neuaufstellung A+, Erweiterung 2026-11-14).

Warum dieser Job existiert: Der Samstags-Thesen-Lauf laeuft in einer Umgebung ohne Kursquelle
(Agent-Proxy weist Yahoo und sechs weitere Endpunkte mit HTTP 403 ab, Befund 2026-11-14). Gate 4
der Thesen-Checkliste ist aber ein Pflichtpunkt, und ohne Zahl ist es nicht abhakbar — der Lauf
vom 2026-11-14 konnte deshalb fuer keine These einen Wert melden. Der Abendjob hat die Kurse,
also rechnet er den Wert vor und legt ihn nach state/thesen_crowdedness.json, genau wie
src/thesen_preise.py die Kursmarken der Karten vorrechnet.

Zwei Zahlen je These, weil die bisherige Reihe anders gerechnet war, als ihr Etikett sagte:
  mittelwert_pp  Mittelwert der Bewegungen der Ausdruecke. Das ist, was die Laeufe vom
                 2026-10-12 bis 2026-11-07 als "Sektor minus Index" berichtet haben, ohne den
                 Index tatsaechlich abzuziehen. Mitgeschrieben fuer die Vergleichbarkeit.
  rel_index_pp   Mittelwert von (Ausdruck minus eigene Benchmark). Das ist die Definition der
                 Thesen-Regel und seit dem User-Entscheid 2026-11-14 die GATE-ZAHL.
Welches Feld das Gate entscheidet, steht in config/thesen_crowdedness.yaml als gate_feld, damit
ein Wechsel eine Config-Zeile ist und keine Prompt-Aenderung.

Fenster: 30 Kalendertage als Gate-Zahl (vergleichbar von Woche zu Woche), zusaetzlich der Wert
seit dem letzten bereits VERGANGENEN Katalysator-Datum der Karte unter seit_katalysator — das
ist der Zeitraum, den die Regel nennt, und er steht damit belegt daneben statt als Behelf.

Umfang: jede These mit Verdikt spielen, beobachten oder freigabe und mindestens einem Ausdruck.
Anders als thesen_preise.py also NICHT nur spur=thesen — die Kandidaten-Thesen (N-Reihe) tragen
keine spur und keine Karte, brauchen die Zahl aber genauso, weil sie ueber eine Hochstufung
mitentscheidet. Thesen ohne Ausdruecke erscheinen mit fehler="keine Ausdruecke" und ohne Zahl;
eine fehlende Zahl ist ein Ergebnis und kein Grund, etwas zu schaetzen.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
import yaml

AKTIV = ("spielen", "beobachten", "freigabe")

STANDARD = {
    "fenster_tage": 30,
    "gate_feld": "rel_index_pp",
    "schwelle_pp": 20,
    "default_index": "^GSPC",
    "suffix_index": {},
    "symbol_index": {},
}


def lade_config(pfad: Optional[Path]) -> dict:
    cfg = dict(STANDARD)
    if pfad and Path(pfad).exists():
        roh = yaml.safe_load(Path(pfad).read_text(encoding="utf-8")) or {}
        if isinstance(roh, dict):
            cfg.update({k: v for k, v in roh.items() if v is not None})
    cfg["suffix_index"] = cfg.get("suffix_index") or {}
    cfg["symbol_index"] = cfg.get("symbol_index") or {}
    return cfg


def benchmark(symbol: str, cfg: dict) -> str:
    """Benchmark-Index eines Ausdrucks. Reihenfolge: Symbol-Ausnahme, laengstes Suffix, Default."""
    sym = str(symbol).strip()
    treffer = cfg["symbol_index"].get(sym)
    if treffer:
        return str(treffer)
    kandidaten = [s for s in cfg["suffix_index"] if sym.upper().endswith(str(s).upper())]
    if kandidaten:
        return str(cfg["suffix_index"][max(kandidaten, key=len)])
    return str(cfg["default_index"])


def bewegung(close: pd.Series, tage: int) -> Optional[dict]:
    """Prozentbewegung vom letzten Schluss zurueck um `tage` Kalendertage.

    Basis ist der letzte Schluss AM ODER VOR dem Zielzeitpunkt — an Wochenenden und Feiertagen
    gibt es keinen Balken, und ein Vorwaertsgriff wuerde das Fenster verkuerzen.
    """
    c = close.dropna()
    if len(c) < 2:
        return None
    ziel = c.index[-1] - pd.Timedelta(days=int(tage))
    vorher = c[c.index <= ziel]
    if vorher.empty:
        return None
    basis, letzt = float(vorher.iloc[-1]), float(c.iloc[-1])
    if basis == 0:
        return None
    return {"von": vorher.index[-1].date().isoformat(), "bis": c.index[-1].date().isoformat(),
            "basis": round(basis, 4), "schluss": round(letzt, 4),
            "move_pct": round((letzt / basis - 1) * 100, 2)}


def bewegung_ab(close: pd.Series, ab: str) -> Optional[dict]:
    """Prozentbewegung seit einem festen Datum (letzter Schluss am oder vor `ab`)."""
    c = close.dropna()
    if len(c) < 2:
        return None
    try:
        ziel = pd.Timestamp(str(ab)[:10])
    except Exception:
        return None
    vorher = c[c.index <= ziel]
    if vorher.empty or vorher.index[-1] == c.index[-1]:
        return None
    basis, letzt = float(vorher.iloc[-1]), float(c.iloc[-1])
    if basis == 0:
        return None
    return {"von": vorher.index[-1].date().isoformat(), "bis": c.index[-1].date().isoformat(),
            "basis": round(basis, 4), "schluss": round(letzt, 4),
            "move_pct": round((letzt / basis - 1) * 100, 2)}


def letzter_katalysator(karte: Optional[dict], bis: str) -> Optional[dict]:
    """Jüngstes Katalysator-Datum der Karte, das am Stichtag bereits vergangen ist.

    Ein Katalysator in der Zukunft hat noch nichts bewegt; dann gibt es keinen Wert und nicht
    etwa einen aus dem naechstbesten Datum.
    """
    eintraege = (karte or {}).get("katalysator") or []
    vergangen = []
    for e in eintraege:
        if not isinstance(e, dict) or not e.get("date"):
            continue
        d = str(e["date"])[:10]
        if d <= str(bis)[:10]:
            vergangen.append({"date": d, "ereignis": e.get("ereignis")})
    return max(vergangen, key=lambda e: e["date"]) if vergangen else None


def _mittel(werte: list[float]) -> Optional[float]:
    return round(sum(werte) / len(werte), 2) if werte else None


def rechne(thesen: dict, kurse: Callable[[str], Optional[pd.Series]], cfg: dict) -> dict:
    """Crowdedness je These. `kurse` liefert eine Schlusskursreihe oder None."""
    tage = int(cfg["fenster_tage"])
    cache: dict[str, Optional[pd.Series]] = {}

    def hol(sym: str) -> Optional[pd.Series]:
        if sym not in cache:
            cache[sym] = kurse(sym)
        return cache[sym]

    idx_cache: dict[str, Optional[dict]] = {}
    out: dict[str, dict] = {}

    for t in thesen.get("thesen", []) or []:
        if t.get("verdikt") not in AKTIV:
            continue
        tid = str(t.get("id"))
        ausdruecke = [str(s) for s in (t.get("ausdruecke") or []) if s]
        if not ausdruecke:
            # Gleiche Feldmenge wie im Normalfall: wer die Datei liest, soll nicht je These
            # ein anderes Schema vorfinden (Befund beim Smoke-Test 2026-11-14).
            out[tid] = {"gate_pp": None, "rel_index_pp": None, "mittelwert_pp": None,
                        "n": 0, "n_rel": 0, "ausdruecke": [], "seit_katalysator": None,
                        "fehler": ["keine Ausdruecke"]}
            continue

        zeilen, abs_moves, rel_moves, fehler = [], [], [], []
        bis = None
        for sym in ausdruecke:
            c = hol(sym)
            if c is None or len(c.dropna()) < 2:
                fehler.append(f"{sym}: keine Kurse")
                continue
            b = bewegung(c, tage)
            if b is None:
                fehler.append(f"{sym}: Fenster {tage}d nicht abgedeckt")
                continue
            bis = b["bis"]
            ix = benchmark(sym, cfg)
            if ix not in idx_cache:
                ic = hol(ix)
                idx_cache[ix] = bewegung(ic, tage) if ic is not None else None
            ib = idx_cache[ix]
            zeile = {"symbol": sym, "index": ix, "move_pct": b["move_pct"],
                     "von": b["von"], "bis": b["bis"]}
            abs_moves.append(b["move_pct"])
            if ib is None:
                zeile.update({"index_move_pct": None, "rel_pp": None})
                fehler.append(f"{ix}: keine Kurse (Index zu {sym})")
            else:
                zeile.update({"index_move_pct": ib["move_pct"],
                              "rel_pp": round(b["move_pct"] - ib["move_pct"], 2)})
                rel_moves.append(zeile["rel_pp"])
            zeilen.append(zeile)

        rel, mittel = _mittel(rel_moves), _mittel(abs_moves)
        eintrag = {
            "rel_index_pp": rel,
            "mittelwert_pp": mittel,
            "n": len(zeilen),
            "n_rel": len(rel_moves),
            "ausdruecke": zeilen,
            "fehler": fehler,
        }
        eintrag["gate_pp"] = eintrag.get(str(cfg["gate_feld"]))

        kat = letzter_katalysator(t.get("karte"), bis) if bis else None
        if kat:
            k_abs, k_rel, k_n = [], [], 0
            for z in zeilen:
                c = hol(z["symbol"])
                b = bewegung_ab(c, kat["date"]) if c is not None else None
                if b is None:
                    continue
                k_abs.append(b["move_pct"])
                k_n += 1
                ic = hol(z["index"])
                ib = bewegung_ab(ic, kat["date"]) if ic is not None else None
                if ib is not None:
                    k_rel.append(round(b["move_pct"] - ib["move_pct"], 2))
            eintrag["seit_katalysator"] = ({"datum": kat["date"], "ereignis": kat.get("ereignis"),
                                            "rel_index_pp": _mittel(k_rel),
                                            "mittelwert_pp": _mittel(k_abs), "n": k_n}
                                           if k_n else None)
        else:
            eintrag["seit_katalysator"] = None
        out[tid] = eintrag
    return out


def _yf(sym: str) -> Optional[pd.Series]:
    import yfinance as yf
    try:
        df = yf.download(sym, period="6mo", auto_adjust=False, progress=False)
        c = df["Close"]
        if isinstance(c, pd.DataFrame):
            c = c.iloc[:, 0]
        return c.dropna()
    except Exception:
        return None


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", default="state")
    ap.add_argument("--config", default="config/thesen_crowdedness.yaml")
    a = ap.parse_args(argv)
    sd = Path(a.state_dir)
    cfg = lade_config(Path(a.config))
    thesen = yaml.safe_load((sd / "thesen.yaml").read_text(encoding="utf-8"))
    res = rechne(thesen, _yf, cfg)
    doc = {
        "aktualisiert": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "basis": {"fenster_tage": int(cfg["fenster_tage"]), "gate_feld": str(cfg["gate_feld"]),
                  "schwelle_pp": cfg.get("schwelle_pp"),
                  "hinweis": "gate_pp ist das Feld, das gate_feld nennt. mittelwert_pp ist die "
                             "Rechnung der Laeufe bis 2026-11-07 (Index NICHT abgezogen), "
                             "rel_index_pp die Definition der Regel."},
        "thesen": res,
    }
    (sd / "thesen_crowdedness.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(doc, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
