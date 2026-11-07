"""Kursmarken der Thesen-Spur taeglich pruefen (Neuaufstellung A+, 2026-11-07).

Der Morning Check hat fuer ETFs wie XLK keine Kurse (nicht im Pipeline-Universum). Dieser Job
liest state/thesen.yaml, nimmt jede These mit spur=thesen und Verdikt spielen/beobachten, und
prueft am Tagesschluss die Marken der Karte:
  karte.preis_falsifikat {symbol, op, level}  -> gebrochen ja/nein
  karte.einstieg         {symbol, op, level}  -> ausgeloest ja/nein (optional)
Dazu Schluss, 52W-Hoch (252 HT, Schlusskurse) und Abstand. Ergebnis: state/thesen_preise.json.

Marken sind KLEBRIG (2026-11-07): Einmal erreicht, bleibt `erstmals` mit Datum stehen, auch wenn
der Kurs zurueckspringt. Einstieg loescht sich erst, wenn karte.position eingetragen ist; das
Preis-Falsifikat bleibt, bis die These verworfen ist. So geht nichts verloren, wenn der User
einen Morning Check nicht liest. Verdikt `freigabe` (Kartenvorschlag des Thesen-Laufs) wird
mitgeprueft, damit die Freigabe-Entscheidung die aktuellen Abstaende sieht.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
import yaml


def marke(m: Optional[dict], schluss: float) -> Optional[dict]:
    if not isinstance(m, dict) or m.get("op") not in ("<", ">") or m.get("level") in (None, ""):
        return None
    lvl = float(m["level"])
    erreicht = schluss < lvl if m["op"] == "<" else schluss > lvl
    return {"op": m["op"], "level": lvl, "erreicht": bool(erreicht),
            "abstand_pct": round((schluss / lvl - 1) * 100, 2)}


AKTIV = ("spielen", "beobachten", "freigabe")


def pruefe(thesen: dict, kurse: Callable[[str], Optional[pd.Series]], vorher: Optional[dict] = None) -> dict:
    vorher = vorher or {}
    out = {}
    for t in thesen.get("thesen", []):
        if t.get("spur") != "thesen" or t.get("verdikt") not in AKTIV:
            continue
        k = t.get("karte") or {}
        syms = {m.get("symbol") for m in (k.get("preis_falsifikat"), k.get("einstieg")) if isinstance(m, dict)}
        for sym in filter(None, syms):
            c = kurse(sym)
            if c is None or len(c) < 2:
                out.setdefault(t["id"], {})[sym] = {"fehler": "keine Kurse"}
                continue
            schluss = float(c.iloc[-1])
            hoch = float(c.iloc[-252:].max())
            eintrag = {"datum": c.index[-1].date().isoformat(), "schluss": round(schluss, 4),
                       "hoch_52w": round(hoch, 4), "abstand_hoch_pct": round((schluss / hoch - 1) * 100, 2)}
            for name in ("preis_falsifikat", "einstieg"):
                m = k.get(name)
                if isinstance(m, dict) and m.get("symbol") == sym:
                    r = marke(m, schluss)
                    if r is None:
                        continue
                    alt = (((vorher.get(t["id"]) or {}).get(sym) or {}).get(name) or {})
                    erstmals = alt.get("erstmals") if alt.get("level") == r["level"] else None
                    if name == "einstieg" and k.get("position"):
                        erstmals = None
                    elif r["erreicht"] and not erstmals:
                        erstmals = eintrag["datum"]
                    r["erstmals"] = erstmals
                    eintrag[name] = r
            out.setdefault(t["id"], {})[sym] = eintrag
    return out


def _yf(sym: str) -> Optional[pd.Series]:
    import yfinance as yf
    try:
        df = yf.download(sym, period="15mo", auto_adjust=False, progress=False)
        c = df["Close"]
        if isinstance(c, pd.DataFrame):
            c = c.iloc[:, 0]
        return c.dropna()
    except Exception:
        return None


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", default="state")
    a = ap.parse_args(argv)
    sd = Path(a.state_dir)
    thesen = yaml.safe_load((sd / "thesen.yaml").read_text(encoding="utf-8"))
    alt_pfad = sd / "thesen_preise.json"
    vorher = {}
    if alt_pfad.exists():
        try:
            vorher = json.loads(alt_pfad.read_text(encoding="utf-8")).get("thesen", {})
        except Exception:
            vorher = {}
    res = pruefe(thesen, _yf, vorher)
    res = {"aktualisiert": datetime.now(timezone.utc).isoformat(timespec="minutes"), "thesen": res}
    (sd / "thesen_preise.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
