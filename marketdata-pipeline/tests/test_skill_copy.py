"""C — Diff-Test: die Skill-Kopie von state_parser.py gegen das Original.

HINTERGRUND
===========
Die SKILL.md sagt zu, dass ``trigger_lint`` gegen dieselbe Parse-Logik lintet,
die die GitHub-Action ausfuehrt — *"der Lint sieht, was die Action sieht"*.
Diese Zusage stand bis 2026-09-14 nur als Prosa in der SKILL.md, zusammen mit
dem Hinweis, man moege den Diff "beim naechsten Repo-Sync gegenpruefen".

Eine Zusage, deren Einhaltung von einer Erinnerung abhaengt, ist keine Zusage.
Dieser Test macht sie pruefbar.

WAS GEPRUEFT WIRD
=================
1. Die eingecheckte Kopie ist exakt das, was ``scripts/build_skill_copy.py``
   aus ``src/state_parser.py`` erzeugt.
2. Die einzige Abweichung ist der Import-Guard fuer ``googleapiclient``.
3. Die Kopie ist ohne Drive-Stack importierbar (der Zweck des Guards).
4. Beide Dateien parsen denselben Trigger feldgleich.

Punkt 4 ist der eigentliche Test: Zeilengleichheit ist ein Mittel,
Verhaltensgleichheit ist der Zweck.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "state_parser.py"
DST = ROOT / "skill" / "state_parser.py"
BUILDER = ROOT / "scripts" / "build_skill_copy.py"


def test_builder_existiert():
    assert BUILDER.exists(), "scripts/build_skill_copy.py fehlt"


def test_skill_kopie_existiert():
    assert DST.exists(), (
        "skill/state_parser.py fehlt — erzeugen mit "
        "'python3 scripts/build_skill_copy.py'"
    )


def test_kopie_ist_auf_dem_stand_der_quelle():
    """Der Kern: --check muss gruen sein, sonst ist die Kopie gedriftet."""
    res = subprocess.run(
        [sys.executable, str(BUILDER), "--check"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, (
        "Die Skill-Kopie ist nicht auf dem Stand von src/state_parser.py.\n"
        f"{res.stdout}{res.stderr}\n"
        "Fix: python3 scripts/build_skill_copy.py"
    )


def test_diff_ist_ausschliesslich_der_import_guard():
    """Zeilenweise Gegenprobe — unabhaengig vom Builder gerechnet."""
    src_lines = SRC.read_text(encoding="utf-8").splitlines()
    dst_lines = DST.read_text(encoding="utf-8").splitlines()

    # Genau eine Zeile wird durch vier ersetzt.
    assert len(dst_lines) - len(src_lines) == 3, (
        f"Zeilendifferenz {len(dst_lines) - len(src_lines)}, erwartet 3 "
        "(eine Import-Zeile wird zu vier Guard-Zeilen)."
    )

    import difflib
    diff = list(difflib.unified_diff(src_lines, dst_lines, lineterm="", n=0))
    # Geaenderte Inhaltszeilen (ohne die ---/+++/@@-Koepfe)
    changed = [l for l in diff if l[:1] in "+-" and l[:3] not in ("---", "+++")]

    assert len(changed) == 5, (
        "Der Diff besteht nicht mehr aus genau einer entfernten und vier "
        f"hinzugefuegten Zeilen, sondern aus {len(changed)}:\n"
        + "\n".join(changed)
    )
    entfernt = [l for l in changed if l.startswith("-")]
    assert len(entfernt) == 1 and "googleapiclient" in entfernt[0], (
        f"Die entfernte Zeile ist nicht der googleapiclient-Import: {entfernt}"
    )
    for l in changed:
        if l.startswith("+"):
            assert any(tok in l for tok in
                       ("try:", "googleapiclient", "except", "Resource = object")), (
                f"Unerwartete hinzugefuegte Zeile im Guard-Block: {l!r}"
            )


def test_kopie_ist_ohne_drive_stack_importierbar():
    """Der Zweck des Guards: Import ohne googleapiclient darf nicht knallen."""
    # sys.modules[name] = None laesst 'import name' mit ImportError scheitern —
    # genau die Lage einer Skill-Session ohne Drive-Stack.
    # WICHTIG: das Modul VOR exec_module in sys.modules registrieren, sonst
    # findet die dataclass-Maschinerie ihr eigenes Modul nicht
    # (dataclasses.py: ns = sys.modules.get(cls.__module__).__dict__).
    code = (
        "import sys;"
        "sys.modules['googleapiclient'] = None;"
        "sys.modules['googleapiclient.discovery'] = None;"
        "import importlib.util as u;"
        f"spec = u.spec_from_file_location('sp_skill', {str(DST)!r});"
        "m = u.module_from_spec(spec);"
        "sys.modules['sp_skill'] = m;"
        "spec.loader.exec_module(m);"
        "print('IMPORT_OK', hasattr(m, '_parse_triggers'))"
    )
    res = subprocess.run([sys.executable, "-c", code],
                         capture_output=True, text=True)
    assert "IMPORT_OK True" in res.stdout, (
        "Die Skill-Kopie laesst sich ohne Drive-Stack nicht importieren:\n"
        f"stdout={res.stdout}\nstderr={res.stderr}"
    )


def test_beide_parsen_denselben_trigger_feldgleich():
    """Verhaltensgleichheit — der eigentliche Zweck des Diff-Tests.

    Zeilengleichheit ist nur das Mittel. Wenn beide Dateien denselben Trigger
    unterschiedlich lesen, ist die Zusage gebrochen, egal wie der Diff aussieht.
    """
    import importlib.util as u

    def load(path: Path, name: str):
        spec = u.spec_from_file_location(name, str(path))
        mod = u.module_from_spec(spec)
        # Vor exec_module registrieren — sonst scheitert @dataclass beim
        # Aufloesen von cls.__module__ (dataclasses.py:712).
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    sys.path.insert(0, str(ROOT / "src"))
    repo = load(SRC, "sp_repo")
    skill = load(DST, "sp_skill_cmp")

    trigger = (
        "A) nach 2026-09-14 MOMENTUM-CONTINUATION-LONG: Touch EMA20-1D "
        "+0,00/+0,40 ATR [pullback] + 4h-Bullish-Reverse-Close (MANUELL) + "
        "RSI-4h Cross ueber die Signallinie. Stopweite entry-relativ "
        "-1,5xATR-1D. TIW = 1D-Schluss unter 58,20EUR. TP1 63,50EUR. "
        "TP2 67,00EUR. R:R Runner 1,63-2,25. 1% Sizing."
    )
    a = repo._parse_triggers(trigger)
    b = skill._parse_triggers(trigger)
    assert len(a) == len(b) == 1

    import dataclasses
    felder = [f.name for f in dataclasses.fields(a[0]) if f.name != "raw"]
    assert len(felder) >= 5, (
        f"ParsedTrigger hat nur {len(felder)} vergleichbare Felder — "
        "der Test wuerde kaum etwas pruefen."
    )
    for f in felder:
        assert getattr(a[0], f) == getattr(b[0], f), (
            f"Feld {f!r} weicht ab: Repo={getattr(a[0], f)!r} "
            f"Skill={getattr(b[0], f)!r}"
        )

    # Und die Felder, an denen der Skill konkret haengt, sind gesetzt:
    assert a[0].reverse_tf == "4h", "reverse_tf ging verloren"
