"""A — Schema-Assertion: der Digest deklariert seine Top-Level-Felder.

HINTERGRUND
===========
Zwischen dem 2026-09-04 und dem 2026-09-14 sind drei Top-Level-Felder in den
Digest gekommen — ``data_freshness``, ``grinders``, ``grinders_meta`` —,
waehrend ``SCHEMA_VERSION`` unveraendert auf ``briefing-digest/v1`` stand.
Die Leseseite (``pipeline_utils.BriefingDigest`` im Skill) kannte sie nicht
und hat sie stillschweigend verschluckt. Aufgefallen ist es erst, als im
Morning-Check vom 2026-09-14 ``dg.data_freshness`` ins Leere lief — obwohl
die SKILL.md das Feld als Pflichtpruefung fuehrt.

Eine stille Divergenz ist teurer als ein lauter Abbruch. Deshalb:
``_assert_schema`` bricht den Lauf ab, sobald Digest und ``SCHEMA_FIELDS``
auseinanderlaufen — in BEIDE Richtungen.
"""
from __future__ import annotations

import pytest

from digest_renderer import SCHEMA_FIELDS, SCHEMA_VERSION, _assert_schema


def _valide() -> dict:
    return {k: {} for k in SCHEMA_FIELDS}


def test_version_ist_hochgezogen():
    """v1 hat drei Feld-Erweiterungen ueberlebt — das soll nicht wieder passieren."""
    assert SCHEMA_VERSION == "briefing-digest/v2"


def test_die_drei_nachgezogenen_felder_sind_deklariert():
    """Genau die Felder, die unter v1 durchgerutscht sind."""
    for feld in ("data_freshness", "grinders", "grinders_meta"):
        assert feld in SCHEMA_FIELDS, f"{feld} fehlt in SCHEMA_FIELDS"


def test_keine_doppelten_felder():
    assert len(SCHEMA_FIELDS) == len(set(SCHEMA_FIELDS))


def test_valider_digest_passiert():
    _assert_schema(_valide())  # darf nicht werfen


def test_undeklariertes_feld_bricht_ab():
    """Die Richtung, die den Anlassfall abgedeckt haette."""
    d = _valide()
    d["voellig_neues_feld"] = [1, 2, 3]
    with pytest.raises(ValueError) as exc:
        _assert_schema(d)
    msg = str(exc.value)
    assert "voellig_neues_feld" in msg
    assert "nicht deklariert" in msg
    # Die Meldung muss sagen, was zu tun ist — nicht nur, dass etwas falsch ist.
    assert "SCHEMA_FIELDS" in msg and "pipeline_utils" in msg


def test_fehlendes_feld_bricht_ab():
    """Die Gegenrichtung: Leseseiten rechnen mit einem Feld, das nicht kommt."""
    d = _valide()
    del d["data_freshness"]
    with pytest.raises(ValueError) as exc:
        _assert_schema(d)
    assert "data_freshness" in str(exc.value)
    assert "nicht gebaut" in str(exc.value)


def test_beide_richtungen_gleichzeitig():
    d = _valide()
    d.pop("grinders")
    d["anderes"] = 1
    with pytest.raises(ValueError) as exc:
        _assert_schema(d)
    msg = str(exc.value)
    assert "grinders" in msg and "anderes" in msg


def test_echter_digest_haelt_das_schema_ein():
    """Integration: ein real gebauter Digest muss durch den Guard gehen.

    Ohne diesen Test koennte SCHEMA_FIELDS beliebig von der Wirklichkeit
    abweichen, solange nur niemand _assert_schema direkt aufruft.
    """
    import json
    from datetime import datetime, timezone

    from digest_renderer import build_briefing_digest

    raw = build_briefing_digest(
        {}, [], [], [],
        datetime(2026, 9, 14, 19, 31, tzinfo=timezone.utc),
    )
    d = json.loads(raw)
    assert set(d) == set(SCHEMA_FIELDS), (
        f"zuviel: {sorted(set(d) - set(SCHEMA_FIELDS))} | "
        f"fehlt: {sorted(set(SCHEMA_FIELDS) - set(d))}"
    )
    assert d["schema"] == SCHEMA_VERSION
