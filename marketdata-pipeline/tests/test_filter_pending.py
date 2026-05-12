"""Tests für die filter_engine-Patches vom 13.05.2026:
- Vol-Status mit 4 Stati (met / failed / pending / unknown)
- BEREIT*-Summary wenn nur Vol pending ist
- conditions_pending-Liste statt conditions_missing für offene Tagesvolumen
- Touch-Operator wird wie approx ausgewertet (Toleranz)
- End-to-End: SL-Strip führt zu richtigem Trigger-Preis
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pytest
import yaml

from filter_engine import (
    _classify_proximity,
    _get_vol_status,
    _evaluate_trigger,
    evaluate_watchlist,
)
from state_parser import ParsedTrigger, WatchlistEntry, _parse_triggers


@pytest.fixture
def config():
    """Lädt die filter_config.yaml."""
    import os
    cfg_path = os.path.join(
        os.path.dirname(__file__), "..", "config", "filter_config.yaml"
    )
    with open(cfg_path) as f:
        return yaml.safe_load(f)


@dataclass
class FakeSnap:
    """Minimaler Snapshot-Stub für Tests."""
    symbol: str = "TEST"
    price: float = 100.0
    rsi14: Optional[float] = 50.0
    volume_multiplier_today: Optional[float] = None
    today_lower_wick_pct: Optional[float] = None
    today_close: Optional[float] = None
    today_open: Optional[float] = None
    today_high: Optional[float] = None
    today_low: Optional[float] = None


# ============================================================
# VOL-STATUS: 4 STATI
# ============================================================

class TestGetVolStatus:
    def test_met_default_threshold(self, config):
        snap = FakeSnap(volume_multiplier_today=1.3)
        assert _get_vol_status(snap, config, None, now_utc_hour=14) == "met"

    def test_met_explicit_threshold(self, config):
        snap = FakeSnap(volume_multiplier_today=1.3)
        # Trigger fordert 1,2× — 1,3 ≥ 1,2 → met
        assert _get_vol_status(snap, config, vol_multiplier=1.2, now_utc_hour=14) == "met"

    def test_failed_explicit_threshold_after_hard_hour(self, config):
        snap = FakeSnap(volume_multiplier_today=0.8)
        # Trigger fordert 1,2× — 0,8 < 1,2 nach 20 UTC → failed
        assert _get_vol_status(snap, config, vol_multiplier=1.2, now_utc_hour=21) == "failed"

    def test_pending_before_hard_hour(self, config):
        snap = FakeSnap(volume_multiplier_today=0.8)
        # 0,8 < 1,0 vor 20 UTC → pending (Tagesvolumen noch offen)
        assert _get_vol_status(snap, config, vol_multiplier=None, now_utc_hour=14) == "pending"

    def test_failed_exactly_at_hard_hour(self, config):
        snap = FakeSnap(volume_multiplier_today=0.5)
        # Genau 20 UTC → failed (>= hard_hour)
        assert _get_vol_status(snap, config, vol_multiplier=None, now_utc_hour=20) == "failed"

    def test_unknown_no_volume_data(self, config):
        snap = FakeSnap(volume_multiplier_today=None)
        assert _get_vol_status(snap, config, vol_multiplier=None, now_utc_hour=14) == "unknown"
        assert _get_vol_status(snap, config, vol_multiplier=None, now_utc_hour=21) == "unknown"

    def test_no_utc_hour_falls_back_to_failed_conservative(self, config):
        """Wenn now_utc_hour=None → konservativ failed (alter Default)."""
        snap = FakeSnap(volume_multiplier_today=0.5)
        assert _get_vol_status(snap, config, vol_multiplier=None, now_utc_hour=None) == "failed"


# ============================================================
# BEREIT* — Summary-Differenzierung
# ============================================================

class TestBereitStarSummary:
    def test_bereit_clean_when_vol_met(self, config):
        """In_zone + Vol erfüllt → BEREIT (ohne Stern)."""
        triggers = _parse_triggers("Daily-Close >35,10€ + Vol ≥30D-Ø")
        snap = FakeSnap(price=36.0, volume_multiplier_today=1.5)
        ts = _evaluate_trigger(triggers[0], snap, "LONG", config, now_utc_hour=14)
        assert ts.proximity == "in_zone"
        assert ts.conditions_pending == []
        assert "BEREIT" in ts.summary
        assert "*" not in ts.summary

    def test_bereit_star_when_vol_pending(self, config):
        """In_zone + Vol unter Schwelle aber vor 20 UTC → BEREIT*."""
        triggers = _parse_triggers("Daily-Close >35,10€ + Vol ≥30D-Ø")
        snap = FakeSnap(price=36.0, volume_multiplier_today=0.7)
        ts = _evaluate_trigger(triggers[0], snap, "LONG", config, now_utc_hour=14)
        assert ts.proximity == "in_zone"
        assert ts.conditions_pending  # nicht leer
        assert ts.conditions_missing == []  # Vol nicht in missing
        assert "BEREIT*" in ts.summary

    def test_in_zone_partial_when_vol_failed(self, config):
        """In_zone + Vol unter Schwelle NACH 20 UTC → in_zone_partial mit failed."""
        triggers = _parse_triggers("Daily-Close >35,10€ + Vol ≥30D-Ø")
        snap = FakeSnap(price=36.0, volume_multiplier_today=0.7)
        ts = _evaluate_trigger(triggers[0], snap, "LONG", config, now_utc_hour=21)
        assert ts.proximity == "in_zone"
        assert ts.conditions_missing  # Vol jetzt in missing
        assert ts.conditions_pending == []
        assert "in Zone" in ts.summary

    def test_pending_uses_trigger_multiplier(self, config):
        """Trigger fordert 1,2× — Snap hat 1,1× → pending mit threshold 1,2."""
        triggers = _parse_triggers("Daily-Close >100€ + Volumen ≥ 1,2× Avg-20d")
        snap = FakeSnap(price=105.0, volume_multiplier_today=1.1)
        ts = _evaluate_trigger(triggers[0], snap, "LONG", config, now_utc_hour=14)
        assert ts.conditions_pending
        # Schwelle 1,20× im Pending-Hinweis enthalten
        assert "1.20×" in ts.conditions_pending[0]


# ============================================================
# Touch-Operator (Verhalten wie approx)
# ============================================================

class TestTouchOperatorEvaluation:
    def test_touch_in_zone_within_2pct(self, config):
        """Touch 52,33$ + Kurs 52,40$ → in_zone (Distanz 0,13%)."""
        triggers = _parse_triggers("Daily-Touch 52,33$ + Hammer")
        snap = FakeSnap(
            price=52.40,
            today_lower_wick_pct=55, today_close=52.40, today_open=52.20,
            today_high=52.50, today_low=51.80,
        )
        ts = _evaluate_trigger(triggers[0], snap, "LONG", config, now_utc_hour=14)
        assert ts.proximity == "in_zone"

    def test_touch_out_of_zone_above_2pct(self, config):
        """Touch 52,33$ + Kurs 54,00$ → not in_zone (Distanz +3,19%)."""
        triggers = _parse_triggers("Daily-Touch 52,33$ + Hammer")
        snap = FakeSnap(
            price=54.00,
            today_lower_wick_pct=55, today_close=54.00, today_open=53.50,
            today_high=54.20, today_low=53.30,
        )
        ts = _evaluate_trigger(triggers[0], snap, "LONG", config, now_utc_hour=14)
        # approx mit 2% Toleranz: 54.00 ist 3.19% drüber → nicht in_zone
        assert ts.proximity != "in_zone"


# ============================================================
# END-TO-END: SL-Strip wirkt sich auf Trigger-Auswertung aus
# ============================================================

class TestEndToEndSlStrip:
    def test_fdx_style_trigger_correct_price(self, config):
        """Klassiker FDX: '1D-Schluss >380$ ... SL <370$' →
        Trigger-Preis muss 380$ sein, nicht 370$.

        Snap bei 381$: BEREIT (über 380), nicht "fast bei 370".
        """
        triggers = _parse_triggers(
            "1D-Schluss >380$ + Volumen ≥ 1,2× Avg-20d + RSI 1D >55. SL <370$ (-1,2ATR). TP1 392$"
        )
        # Snap leicht über Trigger
        snap = FakeSnap(
            price=381.0,
            rsi14=58.0,
            volume_multiplier_today=1.3,  # über 1.2 → met
        )
        ts = _evaluate_trigger(triggers[0], snap, "LONG", config, now_utc_hour=14)
        assert ts.proximity == "in_zone"
        assert "BEREIT" in ts.summary


# ============================================================
# evaluate_watchlist Signatur — backward-compat
# ============================================================

class TestEvaluateWatchlistSignature:
    def test_old_call_without_now_utc_hour(self, config):
        """Alte Aufrufe ohne now_utc_hour müssen weiter funktionieren."""
        entry = WatchlistEntry(
            name="Test", symbol="TEST", direction="LONG",
            trigger_raw="Daily-Close >35€ + Vol ≥30D-Ø",
            status="aktiv", status_note="",
            triggers=_parse_triggers("Daily-Close >35€ + Vol ≥30D-Ø"),
        )
        snap = FakeSnap(price=36.0, volume_multiplier_today=0.5)
        # Kein now_utc_hour → konservativ wie alt: Vol-fail
        results = evaluate_watchlist([entry], {"TEST": snap}, config, date(2026, 5, 13))
        assert len(results) == 1
        assert results[0].overall_status == "active"
        # Ohne UTC-Hour ist Vol failed (konservativ) → conditions_missing nicht leer
        assert results[0].trigger_results[0].conditions_missing

    def test_new_call_with_now_utc_hour(self, config):
        """Neuer Aufruf mit now_utc_hour=14 → Vol pending."""
        entry = WatchlistEntry(
            name="Test", symbol="TEST", direction="LONG",
            trigger_raw="Daily-Close >35€ + Vol ≥30D-Ø",
            status="aktiv", status_note="",
            triggers=_parse_triggers("Daily-Close >35€ + Vol ≥30D-Ø"),
        )
        snap = FakeSnap(price=36.0, volume_multiplier_today=0.5)
        results = evaluate_watchlist(
            [entry], {"TEST": snap}, config, date(2026, 5, 13), now_utc_hour=14
        )
        assert results[0].trigger_results[0].conditions_pending
