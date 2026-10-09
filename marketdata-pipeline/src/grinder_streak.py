"""grinder_streak.py — Zwei-Läufe-Regel im Digest (2026-10-09).

ANLASS (User, Morning Check 2026-10-09 17:08): „Bei den Grindern fehlt mir als Info, ob
sie zum ersten oder zweiten Mal drin stehen." Die Klasse verlangt zwei aufeinander-
folgende Handelstage im Grinder-Block (references/klassen/grinder.md). Der Skill hatte
dafür `wh.grinder_streak(runs)`, braucht dazu aber die Digests der Vortage — und die
löscht die Pipeline nach zehn Läufen (cleanup keep_count=10), also nach ~5 Stunden.

LÖSUNG: Ein kleines Historien-File `GRINDER-STREAK-<stamp>.json` im Briefing-Ordner.
Jeder Tier-A-Lauf liest das jüngste, setzt den Stand des HEUTIGEN Tages auf die aktuelle
Grinder-Liste (der letzte Lauf des Tages gewinnt), schreibt es neu und hängt an jeden
Grinder `streak` (Handelstage in Folge, heute eingeschlossen) und `streak_seit`.
Tage ohne Lauf (Wochenende, Feiertag, Ausfall) fehlen im File und unterbrechen die Folge
NICHT — gezählt werden aufeinanderfolgende EINTRÄGE. Richtungswechsel bricht die Folge.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

PREFIX = "GRINDER-STREAK-"
MAX_TAGE = 15


def _key(g: dict) -> str:
    return f"{str(g.get('symbol', '')).upper()}|{str(g.get('dir', 'long')).lower()[:1]}"


def aktualisieren(historie: Optional[dict], heute: date, grinders: list[dict]) -> dict:
    """Setzt den heutigen Stand, rechnet streak/streak_seit in die Grinder-Dicts (in place)
    und liefert die neue Historie {"schema": 1, "tage": {"JJJJ-MM-TT": [keys]}}."""
    tage = dict((historie or {}).get("tage") or {})
    h = heute.isoformat()
    tage[h] = sorted({_key(g) for g in grinders if g.get("symbol")})
    frueher = sorted((d for d in tage if d < h), reverse=True)
    for g in grinders:
        k = _key(g)
        n, seit = 1, h
        for d in frueher:
            if k in tage[d]:
                n += 1
                seit = d
            else:
                break
        g["streak"] = n
        g["streak_seit"] = seit
    behalten = sorted(tage)[-MAX_TAGE:]
    return {"schema": 1, "tage": {d: tage[d] for d in behalten}}
