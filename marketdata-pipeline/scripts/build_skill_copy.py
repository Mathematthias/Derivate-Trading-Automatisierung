#!/usr/bin/env python3
"""Erzeugt die Skill-Kopie von state_parser.py deterministisch aus src/.

WARUM ES DIESES SKRIPT GIBT
===========================
Der Skill-Ordner trägt eine Kopie von ``src/state_parser.py``, damit
``trigger_lint`` gegen dieselbe Parse-Logik lintet, die die GitHub-Action
später ausführt. Die SKILL.md sagt dazu zu: *"der Lint sieht, was die Action
sieht"*.

Eine Kopie, die von Hand gepflegt wird, hält diese Zusage irgendwann nicht
mehr — und zwar lautlos. Deshalb wird sie nicht kopiert, sondern **generiert**:
eine Quelle (``src/``), ein deterministischer Transformationsschritt, ein Test
(``tests/test_skill_copy.py``), der prüft, dass die eingecheckte Kopie exakt
das Ergebnis dieses Skripts ist.

DIE EINZIGE ERLAUBTE ABWEICHUNG
===============================
Der Skill läuft in einer Session ohne Google-Drive-Stack. Der harte Import
von ``googleapiclient`` würde das Modul dort nicht ladbar machen. Er wird
deshalb — und NUR er — durch einen try/except-Guard ersetzt.

Jede andere Abweichung ist ein Fehler, nicht eine Anpassung.

Aufruf:
    python3 scripts/build_skill_copy.py          # schreibt skill/state_parser.py
    python3 scripts/build_skill_copy.py --check  # prüft nur, Exit 1 bei Drift
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "state_parser.py"
DST = ROOT / "skill" / "state_parser.py"

# Die eine Zeile, die ersetzt wird, und ihr Ersatz.
GUARD_FROM = "from googleapiclient.discovery import Resource\n"
GUARD_TO = (
    "try:\n"
    "    from googleapiclient.discovery import Resource  # type: ignore\n"
    "except Exception:  # Skill-Session ohne Drive-Stack\n"
    "    Resource = object  # type: ignore\n"
)


def transform(source: str) -> str:
    """Wendet genau eine Ersetzung an. Fehlt die Zeile, ist das ein Fehler."""
    if GUARD_FROM not in source:
        raise SystemExit(
            "FEHLER: Die Import-Zeile fuer den Guard steht nicht mehr in "
            f"src/state_parser.py:\n  {GUARD_FROM.strip()!r}\n"
            "Entweder wurde der Import umbenannt/entfernt — dann ist dieses "
            "Skript anzupassen — oder die Datei ist kaputt."
        )
    if source.count(GUARD_FROM) != 1:
        raise SystemExit(
            f"FEHLER: Die Import-Zeile kommt {source.count(GUARD_FROM)}x vor, "
            "erwartet wird genau 1x."
        )
    return source.replace(GUARD_FROM, GUARD_TO)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="nur pruefen, nicht schreiben")
    args = ap.parse_args()

    expected = transform(SRC.read_text(encoding="utf-8"))

    if args.check:
        if not DST.exists():
            print(f"DRIFT: {DST.relative_to(ROOT)} fehlt.", file=sys.stderr)
            return 1
        actual = DST.read_text(encoding="utf-8")
        if actual != expected:
            print(
                f"DRIFT: {DST.relative_to(ROOT)} weicht vom generierten Stand ab.\n"
                "Fix:  python3 scripts/build_skill_copy.py",
                file=sys.stderr,
            )
            return 1
        print("OK — Skill-Kopie ist auf dem Stand von src/state_parser.py")
        return 0

    DST.parent.mkdir(parents=True, exist_ok=True)
    DST.write_text(expected, encoding="utf-8")
    print(f"geschrieben: {DST.relative_to(ROOT)} ({len(expected.splitlines())} Zeilen)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
