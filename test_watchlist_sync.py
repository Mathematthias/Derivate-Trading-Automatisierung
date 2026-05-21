"""Tests für build_pull_universe — Universe-Aufbau ohne Drive/Netz.

Regression-Schutz für watchlist_sync Bug 1 (Note #68): Watchlist-Symbole
müssen in JEDEM Tier Teil des Pull-Universums sein, nicht nur in tier_a.
Vor dem Fix (2026-05-21) bekamen US-Watchlist-Werte (NET, CHKP, ...) nie
eine Auswertung zur US-Session — Folge CHKP-Trigger-B-Miss 18.05.2026.
"""

import os
import sys
from types import SimpleNamespace

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
sys.path.insert(0, _SRC)

from marketdata_sync import build_pull_universe


def _wl(*symbols):
    """Minimal-Stub für Watchlist-Einträge — build_pull_universe nutzt nur .symbol."""
    return [SimpleNamespace(symbol=s) for s in symbols]


TIER_A_CFG = {
    "indizes": {"DAX": "^GDAXI", "SP500": "^GSPC"},
    "rohstoffe_forex": {"Brent": "BZ=F", "EURUSD": "EURUSD=X"},
    "krypto": {"Bitcoin": "BTC-EUR"},
    "positionen": {"Gold_ETC": "4GLD.DE"},
    "ethik_excluded": ["RHM.DE"],
}

TIER_C_CFG = {
    "categories": {
        "nasdaq_100": {"Apple": "AAPL", "Nvidia": "NVDA", "Cognizant": "CTSH"},
    },
}


def test_tier_a_enthaelt_watchlist_symbole():
    all_s, excl, excl_cat = build_pull_universe(
        "tier_a", TIER_A_CFG, _wl("CHKP", "NET", "SAN.PA"),
    )
    assert {"CHKP", "NET", "SAN.PA"} <= all_s
    assert {"^GDAXI", "BZ=F", "BTC-EUR"} <= all_s
    # Kategorie-Symbole sind vom Universe-Setup-Filter ausgenommen
    assert {"^GDAXI", "BZ=F", "BTC-EUR", "4GLD.DE"} <= excl_cat


def test_tier_c_enthaelt_watchlist_symbole():
    # Kern der Bug-1-Regression: NET/CHKP müssen NICHT mehr im yaml hardcodiert
    # sein — sie kommen über die Watchlist in den tier_c-Pull.
    all_s, excl, excl_cat = build_pull_universe(
        "tier_c", TIER_C_CFG, _wl("CHKP", "NET"),
    )
    assert "CHKP" in all_s, "CHKP fehlt im tier_c-Pull — Bug 1 nicht gefixt"
    assert "NET" in all_s, "NET fehlt im tier_c-Pull — Bug 1 nicht gefixt"
    # yaml-Universum bleibt zusätzlich enthalten
    assert {"AAPL", "NVDA", "CTSH"} <= all_s
    # tier_c hat keine Kategorie-Ausschlüsse (nur tier_a)
    assert excl_cat == set()


def test_tier_b_enthaelt_watchlist_symbole():
    all_s, _, _ = build_pull_universe(
        "tier_b", {"categories": {"dax": {"SAP": "SAP.DE"}}}, _wl("MUV2.DE", "CHKP"),
    )
    assert {"MUV2.DE", "CHKP", "SAP.DE"} <= all_s


def test_ethik_excluded_schlaegt_watchlist():
    # Ein ethik-ausgeschlossenes Symbol darf auch dann nicht in den Pull,
    # wenn es (versehentlich) auf der Watchlist steht.
    all_s, excl, _ = build_pull_universe(
        "tier_a", TIER_A_CFG, _wl("RHM.DE", "CHKP"),
    )
    assert "RHM.DE" not in all_s
    assert "RHM.DE" in excl
    assert "CHKP" in all_s


def test_watchlist_eintrag_ohne_symbol_wird_ignoriert():
    all_s, _, _ = build_pull_universe(
        "tier_c", TIER_C_CFG, _wl("CHKP", "", None),
    )
    assert "CHKP" in all_s
    assert "" not in all_s and None not in all_s


def test_leere_watchlist_bricht_nicht():
    all_s, _, _ = build_pull_universe("tier_c", TIER_C_CFG, [])
    assert all_s == {"AAPL", "NVDA", "CTSH"}
