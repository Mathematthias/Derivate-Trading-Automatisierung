"""2026-10-09: Zwei-Läufe-Regel im Digest (streak je Grinder)."""
from datetime import date
from src import grinder_streak as gs


def test_bootstrap_und_folge():
    g1 = [{"symbol": "NVDA", "dir": "long"}, {"symbol": "HD", "dir": "short"}]
    h = gs.aktualisieren(None, date(2026, 10, 9), g1)
    assert [g["streak"] for g in g1] == [1, 1]
    g2 = [{"symbol": "NVDA", "dir": "long"}, {"symbol": "PEP", "dir": "short"}]
    h = gs.aktualisieren(h, date(2026, 10, 12), g2)          # Montag: Wochenende unterbricht nicht
    assert g2[0]["streak"] == 2 and g2[0]["streak_seit"] == "2026-10-09" and g2[1]["streak"] == 1


def test_letzter_lauf_des_tages_gewinnt_und_richtungswechsel():
    h = gs.aktualisieren(None, date(2026, 10, 8), [{"symbol": "HD", "dir": "long"}])
    g = [{"symbol": "HD", "dir": "short"}]
    h = gs.aktualisieren(h, date(2026, 10, 9), g)
    assert g[0]["streak"] == 1                                # Richtungswechsel bricht
    h = gs.aktualisieren(h, date(2026, 10, 9), [])            # spaeterer Lauf am selben Tag
    assert h["tage"]["2026-10-09"] == []


def test_luecke_bricht_folge():
    h = gs.aktualisieren(None, date(2026, 10, 7), [{"symbol": "X", "dir": "long"}])
    h = gs.aktualisieren(h, date(2026, 10, 8), [])
    g = [{"symbol": "X", "dir": "long"}]
    gs.aktualisieren(h, date(2026, 10, 9), g)
    assert g[0]["streak"] == 1


def test_als_json_ist_string_und_rund():
    """Fix 2026-10-22: der Sync uebergab das dict an write_json_file (erwartet str)."""
    import json
    h = gs.aktualisieren(None, date(2026, 10, 21), [{"symbol": "BNZL.L", "dir": "long"}])
    txt = gs.als_json(h)
    assert isinstance(txt, str) and json.loads(txt) == h
    g = [{"symbol": "BNZL.L", "dir": "long"}]
    gs.aktualisieren(json.loads(txt), date(2026, 10, 22), g)
    assert g[0]["streak"] == 2


def test_sync_ruft_als_json():
    import pathlib
    src = pathlib.Path(__file__).resolve().parents[1].joinpath("src", "marketdata_sync.py").read_text(encoding="utf-8")
    assert "gs.als_json(neu)" in src
