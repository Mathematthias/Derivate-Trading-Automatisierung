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
    prev_open: Optional[float] = None
    prev_close: Optional[float] = None


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
# REVERSE-CLOSE: Hammer ODER Bullish-Engulfing (Note #70, 2026-05-19)
# ============================================================

class TestReverseCloseEvaluation:
    """Hammer- und Bullish-Engulfing-Patterns als Reverse-Kerze.
    
    Auslöser: CTSH 19.05.2026 Bullish-Engulfing am 52W-Tief, fiel durch
    reinen Hammer-Filter."""

    def test_classic_hammer_still_matches(self, config):
        """Klassischer Hammer (Lower-Wick 55%, Close oben) — wie vor dem Patch."""
        triggers = _parse_triggers("Daily-Touch 52,33$ + Hammer + Vol >Avg-30d")
        snap = FakeSnap(
            price=52.40,
            today_lower_wick_pct=55, today_open=52.20, today_close=52.40,
            today_high=52.50, today_low=51.80,
            volume_multiplier_today=1.5,
        )
        ts = _evaluate_trigger(triggers[0], snap, "LONG", config, now_utc_hour=14)
        assert any("Hammer ✓" in c for c in ts.conditions_met), \
            f"Hammer sollte matchen, conditions_met={ts.conditions_met}"

    def test_bullish_engulfing_ctsh_style(self, config):
        """CTSH 19.05.2026 (Open 47,96 / Tief 47,31 / Close 51,40)
        + Vortag bearish (Open 49,50 / Close 47,80). Loose Bullish-Engulfing
        — heute schließt deutlich über prev_open.

        Lower-Wick nur ~16%, Hammer fällt durch — Engulfing muss matchen."""
        triggers = _parse_triggers("Daily-Touch 51,40$ + Reverse-Close + Vol >Avg-30d")
        snap = FakeSnap(
            price=51.40,
            today_lower_wick_pct=16,  # Hammer fällt durch
            today_open=47.96, today_close=51.40,
            today_high=51.40, today_low=47.31,
            prev_open=49.50, prev_close=47.80,  # gestern bearish
            volume_multiplier_today=1.98,
        )
        ts = _evaluate_trigger(triggers[0], snap, "LONG", config, now_utc_hour=14)
        assert any("Bullish-Engulfing ✓" in c for c in ts.conditions_met), \
            f"Bullish-Engulfing sollte matchen, conditions_met={ts.conditions_met}, " \
            f"conditions_missing={ts.conditions_missing}"

    def test_engulfing_fails_if_today_bearish(self, config):
        """Heutige Kerze bearish (Close < Open) → kein Bullish-Engulfing."""
        triggers = _parse_triggers("Daily-Touch 50$ + Reverse-Close")
        snap = FakeSnap(
            price=49.50,
            today_lower_wick_pct=20,
            today_open=51.00, today_close=49.50,  # heute bearish
            today_high=51.20, today_low=49.30,
            prev_open=52.00, prev_close=51.00,  # gestern bearish
        )
        ts = _evaluate_trigger(triggers[0], snap, "LONG", config, now_utc_hour=14)
        assert not any("Engulfing ✓" in c or "Hammer ✓" in c for c in ts.conditions_met)
        assert any("keine Reverse-Kerze" in c for c in ts.conditions_missing)

    def test_engulfing_fails_if_body_doesnt_engulf(self, config):
        """Heute bullish + gestern bearish, aber Body schluckt nicht
        (today_open > prev_close oder today_close < prev_open)."""
        triggers = _parse_triggers("Daily-Touch 50$ + Reverse-Close")
        snap = FakeSnap(
            price=51.00,
            today_lower_wick_pct=20,
            today_open=50.50, today_close=51.00,  # heute bullish, aber kleiner Body
            today_high=51.10, today_low=50.40,
            prev_open=53.00, prev_close=51.50,  # gestern bearish, ABER prev_open 53 > today_close 51
        )
        ts = _evaluate_trigger(triggers[0], snap, "LONG", config, now_utc_hour=14)
        assert not any("Engulfing ✓" in c for c in ts.conditions_met)

    def test_engulfing_word_in_trigger_text(self, config):
        """`Bullish-Engulfing` als Trigger-Wort soll require_hammer setzen."""
        triggers = _parse_triggers("Daily-Touch 50$ + Bullish-Engulfing")
        assert triggers[0].require_hammer is True

    def test_bounce_close_word_in_trigger_text(self, config):
        """`Bounce-Close` als breiterer Reverse-Begriff (siehe IFX-WL-Eintrag)."""
        triggers = _parse_triggers("Touch ≤60€ + 1D-Bounce-Close")
        assert triggers[0].require_hammer is True


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


# ============================================================
# BREAKOUT-ZONE DURCHGELAUFEN (Task 5, 2026-05-22)
# ============================================================

class TestBreakoutDurchgelaufen:
    """Breakout-Zone: Kurs ueber Obergrenze = durchgelaufen, Setup tot.
    Pullback-Zone / zone_kind=None: Alt-Verhalten (ueber Zone = warten)."""

    def _zone(self, zone_kind):
        return ParsedTrigger(
            label="A", raw="Zone 120-124", price_low=120.0, price_high=124.0,
            price_op="in_range", zone_kind=zone_kind,
        )

    def test_breakout_ueber_obergrenze_durchgelaufen(self, config):
        """Kurs 1,6% ueber Breakout-Zone → blown_through, proximity far."""
        snap = FakeSnap(price=126.0)  # 124 * 1.016
        ts = _evaluate_trigger(self._zone("breakout"), snap, "LONG", config, now_utc_hour=14)
        assert ts.blown_through is True
        assert ts.proximity == "far"
        assert "DURCHGELAUFEN" in ts.summary

    def test_breakout_durchgelaufen_nicht_very_close(self, config):
        """Regressions-Sicherung: durchgelaufener Breakout 1,6% drueber landet
        NICHT in very_close (≤2%) — genau der Bug, den Task 5 schliesst."""
        snap = FakeSnap(price=126.0)
        ts = _evaluate_trigger(self._zone("breakout"), snap, "LONG", config, now_utc_hour=14)
        assert ts.proximity != "very_close"

    def test_breakout_in_zone_normal(self, config):
        """Kurs IN der Breakout-Zone → in_zone, nicht durchgelaufen."""
        snap = FakeSnap(price=122.0)
        ts = _evaluate_trigger(self._zone("breakout"), snap, "LONG", config, now_utc_hour=14)
        assert ts.blown_through is False
        assert ts.proximity == "in_zone"

    def test_breakout_unter_untergrenze_normal(self, config):
        """Kurs unter der Breakout-Zone → wartend, nicht durchgelaufen."""
        snap = FakeSnap(price=118.0)
        ts = _evaluate_trigger(self._zone("breakout"), snap, "LONG", config, now_utc_hour=14)
        assert ts.blown_through is False

    def test_pullback_ueber_obergrenze_kein_durchgelaufen(self, config):
        """Pullback-Zone, Kurs drueber = Ruecksetzer noch nicht tief genug →
        Alt-Verhalten (very_close), NICHT durchgelaufen."""
        snap = FakeSnap(price=126.0)
        ts = _evaluate_trigger(self._zone("pullback"), snap, "LONG", config, now_utc_hour=14)
        assert ts.blown_through is False
        assert ts.proximity == "very_close"

    def test_zone_kind_none_abwaertskompatibel(self, config):
        """zone_kind=None → exakt Alt-Verhalten, kein Durchgelaufen-Check."""
        snap = FakeSnap(price=126.0)
        ts = _evaluate_trigger(self._zone(None), snap, "LONG", config, now_utc_hour=14)
        assert ts.blown_through is False
        assert ts.proximity == "very_close"
