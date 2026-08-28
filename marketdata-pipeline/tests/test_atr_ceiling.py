"""
Tests fuer den ATR-Deckel im universal_disqualifier (neu 2026-08-28).

Ausfuehren vom marketdata-pipeline/ Verzeichnis:
    PYTHONPATH=./src python tests/test_atr_ceiling.py
oder mit pytest:
    PYTHONPATH=./src pytest tests/test_atr_ceiling.py -v
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "src"))

import datetime as dt
from filter_engine import _passes_universal_disqualifier
from market_data import TickerSnapshot

CFG = {"universal_disqualifier": {
    "min_avg_volume_eur": 1_000_000,
    "earnings_blackout_days": 7,
    "thirty_day_move_max_pct": 15.0,
    "max_atr_pct": 8.0,
}}

def snap(price=100.0, atr14=5.0, vol=50_000_000, move=2.0):
    return TickerSnapshot(
        symbol="TEST", timestamp=dt.datetime(2026, 8, 28), price=price,
        prev_close=price if price else 100.0, atr14=atr14,
        volume_eur_avg_20d=vol, move_30d_pct=move,
    )

def run():
    # 5 % ATR -> durch
    assert _passes_universal_disqualifier(snap(atr14=5.0), CFG) is True
    # 8,0 % exakt -> durch (Deckel ist ">", nicht ">=")
    assert _passes_universal_disqualifier(snap(atr14=8.0), CFG) is True
    # 8,1 % -> raus
    assert _passes_universal_disqualifier(snap(atr14=8.1), CFG) is False
    # 12 % (High-Beta-Fall) -> raus
    assert _passes_universal_disqualifier(snap(atr14=12.0), CFG) is False

    # Fehlende ATR darf NICHT disqualifizieren (Datenluecke != Ausschluss)
    assert _passes_universal_disqualifier(snap(atr14=None), CFG) is True
    assert _passes_universal_disqualifier(snap(price=None, atr14=9.0), CFG) is True
    assert _passes_universal_disqualifier(snap(price=0.0, atr14=9.0), CFG) is True

    # Alte Config ohne max_atr_pct -> Filter inaktiv, Rueckwaertskompatibilitaet
    old = {"universal_disqualifier": {k: v for k, v in
           CFG["universal_disqualifier"].items() if k != "max_atr_pct"}}
    assert _passes_universal_disqualifier(snap(atr14=20.0), old) is True

    # Die anderen Disqualifier wirken unveraendert weiter
    assert _passes_universal_disqualifier(snap(vol=500_000), CFG) is False
    assert _passes_universal_disqualifier(snap(move=20.0), CFG) is False

    print("test_atr_ceiling: 10/10 OK")

if __name__ == "__main__":
    run()
