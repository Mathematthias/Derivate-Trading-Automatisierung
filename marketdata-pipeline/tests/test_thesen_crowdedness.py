"""Crowdedness der Thesen-Spur (Erweiterung 2026-11-14).

Der wichtigste Test hier ist test_reproduziert_lauf_2026_11_07: er haelt fest, dass die
Laeufe bis zum 2026-11-07 unter dem Etikett "Sektor minus Index" den reinen Mittelwert
berichtet haben, und dass die neue Gate-Zahl eine andere ist. Wer die Rechnung aendert,
bricht diesen Test und muss den Sprung im Thesen-Lauf nennen.
"""
import pandas as pd
import pytest

from src import thesen_crowdedness as tc


def _reihe(move_pct, n=90, start="2026-08-16"):
    """Schlusskursreihe, deren 30-Tage-Bewegung genau `move_pct` ist.

    Konstant 100, nur der letzte Balken traegt die Bewegung — Basis ist nach der Regel von
    bewegung() der letzte Schluss am oder vor (letzter Tag minus 30 Tage), also 100.
    """
    idx = pd.bdate_range(start, periods=n)
    werte = [100.0] * (n - 1) + [100.0 * (1 + move_pct / 100.0)]
    return pd.Series(werte, index=idx)


def _kurse(mapping):
    return lambda sym: mapping.get(sym)


CFG = tc.lade_config(None) | {
    "suffix_index": {".DE": "^GDAXI", ".AS": "^STOXX50E", ".VI": "^STOXX50E", ".L": "^FTSE"},
    "default_index": "^GSPC",
    "symbol_index": {},
}


# --- Benchmark-Zuordnung ---------------------------------------------------

def test_benchmark_suffix_default_und_ausnahme():
    assert tc.benchmark("SZG.DE", CFG) == "^GDAXI"
    assert tc.benchmark("MT.AS", CFG) == "^STOXX50E"
    assert tc.benchmark("PSN.L", CFG) == "^FTSE"
    assert tc.benchmark("XOM", CFG) == "^GSPC"          # kein Suffix -> Default
    cfg = CFG | {"symbol_index": {"SZG.DE": "^STOXX50E"}}
    assert tc.benchmark("SZG.DE", cfg) == "^STOXX50E"   # Ausnahme schlaegt Suffix


def test_benchmark_laengstes_suffix_gewinnt():
    cfg = CFG | {"suffix_index": {".L": "^FTSE", "B.L": "^FTSE250"}}
    assert tc.benchmark("AAAB.L", cfg) == "^FTSE250"


# --- Fenster --------------------------------------------------------------

def test_bewegung_greift_nicht_vorwaerts():
    b = tc.bewegung(_reihe(-10.0), 30)
    assert b["move_pct"] == -10.0
    assert b["von"] <= (pd.Timestamp(b["bis"]) - pd.Timedelta(days=30)).date().isoformat()


def test_bewegung_ohne_abdeckung_ist_none():
    assert tc.bewegung(_reihe(5.0, n=3), 30) is None
    assert tc.bewegung(pd.Series(dtype=float), 30) is None


# --- Die Regressionsprobe an zwei echten Laeufen --------------------------

@pytest.mark.parametrize("tid, moves, idx_moves, erwartet_mittel, erwartet_rel", [
    # Thesen-Lauf 2026-11-07, These OEL: berichtet wurden -8,95 PP.
    ("OEL",
     {"VLO": -16.94, "MPC": -14.55, "XOM": 3.44, "PSX": -7.74},
     {"^GSPC": -5.00},
     -8.95, -3.95),
    # Thesen-Lauf 2026-11-07, These STAHL: berichtet wurden -0,02 PP.
    ("STAHL",
     {"SZG.DE": 6.90, "MT.AS": 0.40, "VOE.VI": -7.36},
     {"^GDAXI": 4.09, "^STOXX50E": 0.71},
     -0.02, -1.86),
])
def test_reproduziert_lauf_2026_11_07(tid, moves, idx_moves, erwartet_mittel, erwartet_rel):
    reihen = {s: _reihe(m) for s, m in {**moves, **idx_moves}.items()}
    thesen = {"thesen": [{"id": tid, "verdikt": "beobachten", "ausdruecke": list(moves)}]}
    r = tc.rechne(thesen, _kurse(reihen), CFG)[tid]
    assert r["mittelwert_pp"] == erwartet_mittel, "alte Rechnung muss die Reihe reproduzieren"
    assert r["rel_index_pp"] == erwartet_rel, "neue Gate-Zahl zieht den Index ab"
    assert r["gate_pp"] == erwartet_rel, "gate_feld zeigt per Default auf rel_index_pp"
    assert r["n"] == len(moves) and not r["fehler"]


def test_gate_feld_schaltet_die_zahl_um():
    reihen = {s: _reihe(m) for s, m in {"VLO": -16.94, "MPC": -14.55, "XOM": 3.44,
                                        "PSX": -7.74, "^GSPC": -5.00}.items()}
    thesen = {"thesen": [{"id": "OEL", "verdikt": "spielen",
                          "ausdruecke": ["VLO", "MPC", "XOM", "PSX"]}]}
    r = tc.rechne(thesen, _kurse(reihen), CFG | {"gate_feld": "mittelwert_pp"})["OEL"]
    assert r["gate_pp"] == -8.95


# --- Umfang und Fehlerfaelle ----------------------------------------------

def test_nur_aktive_verdikte_und_spur_ist_egal():
    reihen = {"A": _reihe(1.0), "^GSPC": _reihe(0.0)}
    thesen = {"thesen": [
        {"id": "SP", "verdikt": "spielen", "ausdruecke": ["A"], "spur": "thesen"},
        {"id": "BE", "verdikt": "beobachten", "ausdruecke": ["A"]},          # ohne spur
        {"id": "FR", "verdikt": "freigabe", "ausdruecke": ["A"]},
        {"id": "WE", "verdikt": "verworfen", "ausdruecke": ["A"]},
    ]}
    r = tc.rechne(thesen, _kurse(reihen), CFG)
    assert set(r) == {"SP", "BE", "FR"}, "verworfen raus, These ohne spur drin"


def test_these_ohne_ausdruecke_bekommt_keine_zahl():
    thesen = {"thesen": [{"id": "N4", "verdikt": "beobachten", "ausdruecke": None}]}
    r = tc.rechne(thesen, _kurse({}), CFG)["N4"]
    assert r["gate_pp"] is None and r["rel_index_pp"] is None and r["n"] == 0
    assert r["fehler"] == ["keine Ausdruecke"]


def test_fehlender_kurs_wird_gemeldet_und_der_rest_gerechnet():
    reihen = {"A": _reihe(10.0), "^GSPC": _reihe(0.0)}          # B fehlt
    thesen = {"thesen": [{"id": "X", "verdikt": "spielen", "ausdruecke": ["A", "B"]}]}
    r = tc.rechne(thesen, _kurse(reihen), CFG)["X"]
    assert r["n"] == 1 and r["rel_index_pp"] == 10.0
    assert r["fehler"] == ["B: keine Kurse"]


def test_fehlender_index_laesst_den_mittelwert_stehen():
    reihen = {"A": _reihe(10.0)}                                 # ^GSPC fehlt
    thesen = {"thesen": [{"id": "X", "verdikt": "spielen", "ausdruecke": ["A"]}]}
    r = tc.rechne(thesen, _kurse(reihen), CFG)["X"]
    assert r["mittelwert_pp"] == 10.0
    assert r["rel_index_pp"] is None and r["n_rel"] == 0
    assert r["gate_pp"] is None, "ohne Index keine Gate-Zahl - nicht schaetzen"
    assert "^GSPC: keine Kurse (Index zu A)" in r["fehler"]


# --- Katalysator-Fenster --------------------------------------------------

def test_seit_katalysator_nimmt_den_letzten_vergangenen():
    reihen = {"A": _reihe(10.0), "^GSPC": _reihe(4.0)}
    bis = reihen["A"].index[-1].date().isoformat()
    karte = {"katalysator": [
        {"date": "2026-08-20", "ereignis": "alt"},
        {"date": reihen["A"].index[-20].date().isoformat(), "ereignis": "zuletzt"},
        {"date": "2099-01-01", "ereignis": "Zukunft"},
    ]}
    thesen = {"thesen": [{"id": "X", "verdikt": "spielen", "ausdruecke": ["A"], "karte": karte}]}
    sk = tc.rechne(thesen, _kurse(reihen), CFG)["X"]["seit_katalysator"]
    assert sk["ereignis"] == "zuletzt" and sk["datum"] <= bis
    assert sk["rel_index_pp"] == 6.0 and sk["mittelwert_pp"] == 10.0


def test_nur_zukuenftige_katalysatoren_ergeben_keinen_wert():
    reihen = {"A": _reihe(10.0), "^GSPC": _reihe(0.0)}
    karte = {"katalysator": [{"date": "2099-01-01", "ereignis": "NVDA"}]}
    thesen = {"thesen": [{"id": "X", "verdikt": "spielen", "ausdruecke": ["A"], "karte": karte}]}
    assert tc.rechne(thesen, _kurse(reihen), CFG)["X"]["seit_katalysator"] is None


def test_these_ohne_karte_hat_kein_katalysator_fenster():
    reihen = {"A": _reihe(10.0), "^GSPC": _reihe(0.0)}
    thesen = {"thesen": [{"id": "N6", "verdikt": "beobachten", "ausdruecke": ["A"]}]}
    assert tc.rechne(thesen, _kurse(reihen), CFG)["N6"]["seit_katalysator"] is None


# --- Config ---------------------------------------------------------------

def test_config_aus_dem_repo_ist_lesbar_und_vollstaendig():
    import pathlib
    p = pathlib.Path(__file__).resolve().parents[1] / "config" / "thesen_crowdedness.yaml"
    cfg = tc.lade_config(p)
    assert cfg["fenster_tage"] == 30
    assert cfg["gate_feld"] == "rel_index_pp"
    assert cfg["default_index"] == "^GSPC"
    assert cfg["suffix_index"][".DE"] == "^GDAXI"
