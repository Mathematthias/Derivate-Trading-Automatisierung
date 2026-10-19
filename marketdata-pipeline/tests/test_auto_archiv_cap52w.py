"""Tests 2026-10-19: INBOX-Op watchlist.archive_reeval (Dauerregel TIW/Halbzeit)
und 52W-Kappe des Measured-Move-RRprox nur fuer aeltere Hochs."""
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from filter_engine import _cap_52w_aktiv, _rr_proxy  # noqa: E402
from state_yaml import _leg_reeval, apply_actions  # noqa: E402

CFG = {"rr_proxy": {"enabled": True, "atr_mult": 1.5, "min_rr": 1.4,
                    "measured_move_buckets": ["breakout_long", "breakdown_short"]}}


@dataclass
class Snap:
    price: float
    atr14: float
    high_20d: Optional[float] = None
    low_20d: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None


# --- 52W-Kappe -------------------------------------------------------------

def test_aelteres_52w_hoch_kappt():
    # TRV-artig: Ausbruch 20d-Hoch 386, Range 20 -> MM-Ziel 406; aelteres 52W-Hoch 398,71
    s = Snap(price=386.59, atr14=7.686, high_20d=386.0, low_20d=366.0, high_52w=398.71)
    rr, eng = _rr_proxy(s, "long", CFG, bucket="breakout_long")
    assert rr == pytest.approx((398.71 - 386.59) / (1.5 * 7.686))
    assert eng is False                      # ENG am ungekappten Wert (406 - 386,59)
    assert _cap_52w_aktiv(s, "long", "breakout_long", CFG) is True


def test_frisches_52w_hoch_bleibt_ungekappt():
    # Blue Sky: das 52W-Hoch IST das 20d-Hoch (Ausbruch auf neues Hoch)
    s = Snap(price=100.0, atr14=2.0, high_20d=101.0, low_20d=90.0, high_52w=101.0)
    rr, _ = _rr_proxy(s, "long", CFG, bucket="breakout_long")
    assert rr == pytest.approx((101.0 + 11.0 - 100.0) / 3.0)
    assert _cap_52w_aktiv(s, "long", "breakout_long", CFG) is False


def test_52w_hoch_hinter_dem_ziel_kappt_nicht():
    s = Snap(price=100.0, atr14=2.0, high_20d=101.0, low_20d=90.0, high_52w=130.0)
    rr, _ = _rr_proxy(s, "long", CFG, bucket="breakout_long")
    assert rr == pytest.approx(12.0 / 3.0)


def test_short_spiegelbildlich():
    s = Snap(price=34.06, atr14=0.905, high_20d=36.0, low_20d=34.2, low_52w=32.6)
    rr, _ = _rr_proxy(s, "short", CFG, bucket="breakdown_short")
    assert rr == pytest.approx((34.06 - 32.6) / (1.5 * 0.905))
    assert _cap_52w_aktiv(s, "short", "breakdown_short", CFG) is True


def test_pullback_unberuehrt():
    s = Snap(price=100.0, atr14=2.0, high_20d=110.0, low_20d=90.0, high_52w=105.0)
    rr, _ = _rr_proxy(s, "long", CFG, bucket="long_trend_pullback")
    assert rr == pytest.approx(10.0 / 3.0)


def test_kappe_abschaltbar():
    cfg = {"rr_proxy": dict(CFG["rr_proxy"], cap_52w_aelter=False)}
    s = Snap(price=386.59, atr14=7.686, high_20d=386.0, low_20d=366.0, high_52w=398.71)
    rr, _ = _rr_proxy(s, "long", cfg, bucket="breakout_long")
    assert rr == pytest.approx((406.0 - 386.59) / (1.5 * 7.686))


# --- INBOX-Op watchlist.archive_reeval --------------------------------------

def _state():
    return {"watchlist": {"entries": [
        {"symbol": "XYZ", "status": "archiviert", "legs": [{"label": "A", "gate": "🔴", "text": "alt"}]},
        {"symbol": "XYZ", "status": "aktiv", "legs": [
            {"label": "A", "gate": "🟡", "text": "TIW = 1D-Schluss unter 100,00$."},
            {"label": "B", "gate": "🟡", "text": "TIW = 1D-Schluss unter 90,00$."}]},
    ]}, "radar": {"rows": []}, "thesen": {"thesen": []}}


def test_archive_reeval_ganze_zeile():
    st = _state()
    log = apply_actions(st, [{"op": "watchlist.archive_reeval", "symbol": "XYZ", "reason": "TIW gebrochen",
                              "reeval_op": ">", "reeval_level": 100.0}], today=date(2026, 10, 20))
    e = st["watchlist"]["entries"][1]
    assert e["status"] == "archiviert" and e["archived"]["date"] == "2026-10-20"
    assert all(l["gate"] == "🔴" for l in e["legs"])
    assert _leg_reeval(e["legs"][0]["text"]) == {"op": ">", "level": 100.0}
    assert st["watchlist"]["entries"][0]["legs"][0]["text"] == "alt"     # Archiv-Zwilling unberuehrt
    assert "archiviert" in log[0]


def test_archive_reeval_nur_ein_leg():
    st = _state()
    apply_actions(st, [{"op": "watchlist.archive_reeval", "symbol": "XYZ", "leg": "B", "reason": "TIW B",
                        "reeval_op": ">", "reeval_level": 90.0}], today=date(2026, 10, 20))
    e = st["watchlist"]["entries"][1]
    assert e["status"] == "aktiv"
    assert e["legs"][0]["gate"] == "🟡" and e["legs"][1]["gate"] == "🔴"


def test_archive_reeval_idempotent():
    st = _state()
    a = {"op": "watchlist.archive_reeval", "symbol": "XYZ", "reason": "x", "reeval_op": "<", "reeval_level": 9.5}
    apply_actions(st, [a], today=date(2026, 10, 20))
    log = apply_actions(st, [a], today=date(2026, 10, 20))
    assert "uebersprungen" in log[0] and "verworfen" not in log[0]
    assert _leg_reeval(st["watchlist"]["entries"][1]["legs"][0]["text"]) == {"op": "<", "level": 9.5}


def test_archive_reeval_falscher_op_wird_verworfen():
    st = _state()
    log = apply_actions(st, [{"op": "watchlist.archive_reeval", "symbol": "XYZ", "reeval_op": "=",
                              "reeval_level": 1}], today=date(2026, 10, 20))
    assert "verworfen" in log[0]
    assert st["watchlist"]["entries"][1]["status"] == "aktiv"
