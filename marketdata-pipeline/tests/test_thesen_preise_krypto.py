"""Getrennte Krypto-Karte (spur=krypto, User 2026-11-20) wird vom Preis-Job geprueft wie eine These."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import thesen_preise as tp  # noqa: E402


def _kurse(sym):
    return pd.Series([60000.0, 55888.0], index=pd.to_datetime(["2026-11-19", "2026-11-20"]))


def _these(spur, verdikt="beobachten"):
    return {"id": "X", "spur": spur, "verdikt": verdikt, "karte": {
        "preis_falsifikat": {"symbol": "BTC-EUR", "op": "<", "level": 46000},
        "einstieg": {"symbol": "BTC-EUR", "op": "<", "level": 60000}}}


def test_krypto_spur_wird_geprueft():
    r = tp.pruefe({"thesen": [_these("krypto")]}, _kurse)
    e = r["X"]["BTC-EUR"]
    assert e["einstieg"]["erreicht"] is True and e["einstieg"]["erstmals"] == "2026-11-20"
    assert e["preis_falsifikat"]["erreicht"] is False


def test_andere_spur_bleibt_aussen():
    assert tp.pruefe({"thesen": [_these(None)]}, _kurse) == {}
    assert tp.pruefe({"thesen": [_these("krypto", "verworfen")]}, _kurse) == {}
