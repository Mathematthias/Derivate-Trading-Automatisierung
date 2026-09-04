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
    _distance_in_atr,
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
    atr14: Optional[float] = None  # None → %-Fallback (Alt-Tests unverändert)
    volume_multiplier_today: Optional[float] = None
    last_bar_date: Optional[str] = None
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
# VOL-STATUS: HANDELSTAGS-CHECK (Wochenend-/Feiertags-Lauf, 2026-05-24)
# ============================================================

class TestVolStatusTradingDayCheck:
    """Der Vol-Guard darf an Nicht-Handelstagen das finale Volumen des letzten
    abgeschlossenen Handelstags nicht als 'pending' werten.

    Auslöser: Wochenend-Läufe liegen uhrzeitlich immer vor 20 UTC und ließen
    Freitags finales Volumen als 'noch offen' durchgehen → BEREIT-Bucket blähte
    auf. Fix: liegt der letzte Balken vor `today`, ist die Sitzung abgeschlossen.
    """

    FRIDAY = date(2026, 5, 22)
    SATURDAY = date(2026, 5, 23)
    MONDAY = date(2026, 5, 25)

    def test_weekend_run_below_threshold_is_failed(self, config):
        """Sa-Lauf 10 UTC, letzter Balken Fr, Vol unter Schwelle → failed
        (nicht pending) — das ist der eigentliche Bug-Fix."""
        snap = FakeSnap(volume_multiplier_today=0.8,
                        last_bar_date=self.FRIDAY.isoformat())
        assert _get_vol_status(snap, config, None, now_utc_hour=10,
                               today=self.SATURDAY) == "failed"

    def test_monday_early_run_friday_bar_is_failed(self, config):
        """Mo 07 UTC, letzter Balken noch Fr → Freitags-Volumen ist final."""
        snap = FakeSnap(volume_multiplier_today=0.8,
                        last_bar_date=self.FRIDAY.isoformat())
        assert _get_vol_status(snap, config, None, now_utc_hour=7,
                               today=self.MONDAY) == "failed"

    def test_genuine_intraday_today_bar_still_pending(self, config):
        """Letzter Balken == heute, vor 20 UTC → weiter pending (echtes
        Intraday, Volumen kann noch wachsen)."""
        snap = FakeSnap(volume_multiplier_today=0.8,
                        last_bar_date=self.FRIDAY.isoformat())
        assert _get_vol_status(snap, config, None, now_utc_hour=14,
                               today=self.FRIDAY) == "pending"

    def test_today_bar_after_hard_hour_is_failed(self, config):
        """Letzter Balken == heute, nach 20 UTC → failed wie gehabt."""
        snap = FakeSnap(volume_multiplier_today=0.8,
                        last_bar_date=self.FRIDAY.isoformat())
        assert _get_vol_status(snap, config, None, now_utc_hour=21,
                               today=self.FRIDAY) == "failed"

    def test_met_unaffected_by_dates(self, config):
        """Volumen über Schwelle → met, unabhängig von Datum/Uhrzeit."""
        snap = FakeSnap(volume_multiplier_today=1.5,
                        last_bar_date=self.FRIDAY.isoformat())
        assert _get_vol_status(snap, config, None, now_utc_hour=10,
                               today=self.SATURDAY) == "met"

    def test_no_bar_date_falls_back_to_time_logic(self, config):
        """last_bar_date=None → reine Uhrzeit-Logik (pending vor 20 UTC)."""
        snap = FakeSnap(volume_multiplier_today=0.8, last_bar_date=None)
        assert _get_vol_status(snap, config, None, now_utc_hour=14,
                               today=self.SATURDAY) == "pending"

    def test_no_today_falls_back_to_time_logic(self, config):
        """today=None (Alt-Aufruf) → reine Uhrzeit-Logik, Backward-Compat."""
        snap = FakeSnap(volume_multiplier_today=0.8,
                        last_bar_date=self.FRIDAY.isoformat())
        assert _get_vol_status(snap, config, None, now_utc_hour=14,
                               today=None) == "pending"

    def test_threading_through_evaluate_trigger(self, config):
        """today erreicht _get_vol_status auch über _evaluate_trigger: Sa-Lauf
        → Vol landet in conditions_missing (failed), nicht conditions_pending."""
        triggers = _parse_triggers("Daily-Close >35,10€ + Vol ≥30D-Ø")
        snap = FakeSnap(price=36.0, volume_multiplier_today=0.7,
                        last_bar_date=self.FRIDAY.isoformat())
        ts = _evaluate_trigger(triggers[0], snap, "LONG", config,
                               now_utc_hour=10, today=self.SATURDAY)
        assert ts.conditions_missing
        assert ts.conditions_pending == []
        assert "BEREIT*" not in ts.summary


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


# ============================================================
# SHORT-BREAKDOWN DURCHGELAUFEN (Task 5 Etappe-1-Nachtrag, 2026-05-22)
# ============================================================

class TestBreakdownShortDurchgelaufen:
    """Short-Breakdown-Zone: Kurs UNTER Untergrenze = durchgelaufen.
    Spiegelbild zum Long-Breakout — Durchgelaufen-Logik richtungsabhaengig."""

    def _zone(self):
        return ParsedTrigger(
            label="A", raw="Zone 58,94-60,00", price_low=58.94, price_high=60.00,
            price_op="in_range", zone_kind="breakout",
        )

    def test_short_breakdown_unter_untergrenze_durchgelaufen(self, config):
        """SHORT, Kurs unter Breakdown-Zone → blown_through, far."""
        snap = FakeSnap(price=58.0)
        ts = _evaluate_trigger(self._zone(), snap, "SHORT", config, now_utc_hour=14)
        assert ts.blown_through is True
        assert ts.proximity == "far"
        assert "DURCHGELAUFEN" in ts.summary

    def test_short_breakdown_in_zone_normal(self, config):
        """SHORT, Kurs in der Zone → in_zone, nicht durchgelaufen."""
        snap = FakeSnap(price=59.5)
        ts = _evaluate_trigger(self._zone(), snap, "SHORT", config, now_utc_hour=14)
        assert ts.blown_through is False
        assert ts.proximity == "in_zone"

    def test_short_breakdown_ueber_obergrenze_wartet(self, config):
        """SHORT, Kurs ueber Zone = Breakdown noch nicht erfolgt → warten."""
        snap = FakeSnap(price=61.0)
        ts = _evaluate_trigger(self._zone(), snap, "SHORT", config, now_utc_hour=14)
        assert ts.blown_through is False

    def test_long_breakout_unter_untergrenze_kein_durchgelaufen(self, config):
        """Gegenprobe: LONG-breakout, Kurs unter Zone = Ausbruch noch nicht
        erfolgt → warten, NICHT durchgelaufen (Short-Logik darf nicht greifen)."""
        zone = ParsedTrigger(
            label="A", raw="Zone 411-415", price_low=411.0, price_high=415.0,
            price_op="in_range", zone_kind="breakout",
        )
        snap = FakeSnap(price=405.0)
        ts = _evaluate_trigger(zone, snap, "LONG", config, now_utc_hour=14)
        assert ts.blown_through is False


# ============================================================
# JOURNAL-GATE-SKIP (3-Trigger-Schema, 2026-05-23)
# ============================================================

class TestGateSkip:
    """Trigger mit 🚦-Gate 🔴 (tot) oder ⏳ (wartet) werden von
    _evaluate_trigger nicht inhaltlich ausgewertet, sondern hart auf
    proximity='far' gesetzt. 🟢/🟡/None → normale Auswertung.
    """

    def _price_trigger(self, gate):
        # In-Zone-Trigger: ohne Gate-Skip wäre das proximity='in_zone'.
        return ParsedTrigger(
            label="A", raw="Zone 95-105", price_low=95.0, price_high=105.0,
            price_op="in_range", gate=gate,
        )

    def test_gate_rot_skipped(self, config):
        snap = FakeSnap(price=100.0)  # mitten in der Zone
        ts = _evaluate_trigger(self._price_trigger("🔴"), snap, "LONG",
                               config, now_utc_hour=14)
        assert ts.proximity == "far"
        assert "🔴" in ts.summary
        assert ts.conditions_missing  # Skip-Grund vermerkt

    def test_gate_sanduhr_MIT_preis_wird_normal_ausgewertet(self, config):
        """⏳-Blindfleck-Fix (2026-06-01): Ein ⏳-Trigger MIT auswertbarem Preis
        wird NICHT mehr übersprungen.

        Der Test prüfte bis 2026-09-04 das Verhalten VOR diesem Fix und war
        seither rot — unbemerkt, weil kein CI-Workflow pytest aufgerufen hat
        (Repo-Audit 2026-09-01). Anlassfall des Fixes war MRK: 0,2 ATR am
        Trigger, aber durch ⏳ nie gebucketet. Übersprungen werden seither nur
        noch PREISLOSE ⏳-Trigger (echte Datums-/Event-Warteschleifen).
        """
        snap = FakeSnap(price=100.0)  # mitten in der Zone 95–105
        ts = _evaluate_trigger(self._price_trigger("⏳"), snap, "LONG",
                               config, now_utc_hour=14)
        assert ts.proximity == "in_zone"

    def test_gate_sanduhr_OHNE_preis_wird_uebersprungen(self, config):
        """Die Gegenprobe: preislose ⏳-Trigger bleiben 'far'."""
        from state_parser import ParsedTrigger
        pt = ParsedTrigger(label="A", raw="wartet auf FDA-Entscheid", gate="⏳")
        ts = _evaluate_trigger(pt, FakeSnap(price=100.0), "LONG",
                               config, now_utc_hour=14)
        assert ts.proximity == "far"
        assert "⏳" in ts.summary

    def test_gate_gruen_evaluated_normally(self, config):
        """🟢 → Trigger wird ausgewertet, In-Zone bleibt In-Zone."""
        snap = FakeSnap(price=100.0)
        ts = _evaluate_trigger(self._price_trigger("🟢"), snap, "LONG",
                               config, now_utc_hour=14)
        assert ts.proximity == "in_zone"

    def test_gate_gelb_evaluated_normally(self, config):
        """🟡 (beobachten) → ebenfalls normale Auswertung, kein Skip."""
        snap = FakeSnap(price=100.0)
        ts = _evaluate_trigger(self._price_trigger("🟡"), snap, "LONG",
                               config, now_utc_hour=14)
        assert ts.proximity == "in_zone"

    def test_gate_none_evaluated_normally(self, config):
        """Kein Gate (Alt-STATE-Doc) → normale Auswertung wie bisher."""
        snap = FakeSnap(price=100.0)
        ts = _evaluate_trigger(self._price_trigger(None), snap, "LONG",
                               config, now_utc_hour=14)
        assert ts.proximity == "in_zone"

    def test_gate_label_preserved_on_skip(self, config):
        """Auch ein übersprungener Trigger behält sein Label im Output."""
        snap = FakeSnap(price=100.0)
        ts = _evaluate_trigger(self._price_trigger("🔴"), snap, "LONG",
                               config, now_utc_hour=14)
        assert ts.label == "A"


# ============================================================
# ATR-NORMALISIERTE PROXIMITY-BUCKETS (2026-07-12)
# ============================================================

class TestProximityATR:
    """Proximity-Buckets ATR-normalisiert: very_close/close/watching über
    Vielfache von ATR14 statt roher %-Schwellen. Fallback auf % wenn ATR
    fehlt. distance_pct bleibt als Anzeige-% erhalten."""

    # --- _distance_in_atr: exakte Umrechnung ---

    def test_distance_in_atr_exact(self):
        # ref = 108, price = 104 → distance_pct = -3.7037%, gap = -4.0, ATR 6
        d = (104.0 - 108.0) / 108.0 * 100.0
        val = _distance_in_atr(d, price=104.0, atr14=6.0)
        assert val is not None
        assert abs(val - (-4.0 / 6.0)) < 1e-6  # -0.6667

    def test_distance_in_atr_none_when_atr_missing(self):
        assert _distance_in_atr(2.0, price=100.0, atr14=None) is None
        assert _distance_in_atr(2.0, price=100.0, atr14=0.0) is None
        assert _distance_in_atr(2.0, price=None, atr14=5.0) is None

    # --- Klassifizierung: ATR enger als % bei Hoch-Vola ---

    def test_high_vola_atr_tighter_than_pct(self, config):
        # -3.7% wäre unter %-Logik "close" (>2, <=5); bei ATR 6 sind das
        # 0.67 ATR → very_close.
        d = (104.0 - 108.0) / 108.0 * 100.0  # -3.7037%
        prox = _classify_proximity(d, config, price=104.0, atr14=6.0)
        assert prox == "very_close"
        # Gegencheck: reiner %-Fallback (kein ATR) → close
        assert _classify_proximity(d, config, price=104.0, atr14=None) == "close"

    # --- Klassifizierung: ATR weiter als % bei Niedrig-Vola ---

    def test_low_vola_atr_wider_than_pct(self, config):
        # -1.96% wäre unter %-Logik "very_close" (<=2); bei ATR 1 sind das
        # ~1.96 ATR → watching (>1.5, <=3.0).
        d = (100.0 - 102.0) / 102.0 * 100.0  # -1.9608%
        prox = _classify_proximity(d, config, price=100.0, atr14=1.0)
        assert prox == "watching"
        # Gegencheck: %-Fallback → very_close
        assert _classify_proximity(d, config, price=100.0, atr14=None) == "very_close"

    def test_fallback_to_pct_when_no_atr(self, config):
        d = (100.0 - 102.0) / 102.0 * 100.0  # -1.96%
        assert _classify_proximity(d, config, price=100.0, atr14=None) == "very_close"

    def test_in_zone_regardless_of_atr(self, config):
        assert _classify_proximity(0.0, config, price=100.0, atr14=6.0) == "in_zone"
        assert _classify_proximity(0.0, config, price=100.0, atr14=None) == "in_zone"

    # --- End-to-End: ATR wird durch _evaluate_trigger durchgereicht ---

    def test_evaluate_trigger_threads_atr_high_vola(self, config):
        trigger = _parse_triggers("Daily-Close >108€")[0]
        snap = FakeSnap(price=104.0, atr14=6.0)  # -3.7% / 0.67 ATR
        ts = _evaluate_trigger(trigger, snap, "LONG", config, now_utc_hour=14)
        assert ts.proximity == "very_close"
        assert ts.distance_atr is not None
        assert abs(ts.distance_pct - (-3.7037)) < 0.01
        assert "×ATR" in ts.summary

    def test_evaluate_trigger_threads_atr_low_vola(self, config):
        trigger = _parse_triggers("Daily-Close >102€")[0]
        snap = FakeSnap(price=100.0, atr14=1.0)  # -1.96% / ~1.96 ATR
        ts = _evaluate_trigger(trigger, snap, "LONG", config, now_utc_hour=14)
        assert ts.proximity == "watching"

    def test_evaluate_trigger_no_atr_uses_pct(self, config):
        trigger = _parse_triggers("Daily-Close >102€")[0]
        snap = FakeSnap(price=100.0)  # kein atr14 → %-Fallback → very_close
        ts = _evaluate_trigger(trigger, snap, "LONG", config, now_utc_hour=14)
        assert ts.proximity == "very_close"
        assert ts.distance_atr is None
