"""Tests für den Carry-Forward-Fix bestätigter Tagesschluss-Breakouts
(Note #110, 2026-05-29 — entdeckt via SAN.PA).

Bug: Ein Daily-Close-Breakout, der im Abendlauf nach Markt-Schluss als
"BEREIT — alle Bedingungen erfüllt" (volles Tagesvolumen) bestätigt wurde,
fiel am Folgetag-Morgen gegen die werdende (partielle) Tageskerze zurück auf
BEREIT*/very_close und war im Morning-Check unsichtbar.

Fix: Für reine Close-Breakout-Trigger werden Preis UND Volumen gegen die
zuletzt ABGESCHLOSSENE Tageskerze (prev_*) evaluiert, solange die Sitzung
noch läuft. Selbst-invalidierend über prev_close.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

import os
import pytest
import yaml

from filter_engine import (
    _evaluate_trigger,
    _is_close_breakout_trigger,
    _last_bar_is_forming,
)
from state_parser import ParsedTrigger


@pytest.fixture
def config():
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "filter_config.yaml")
    with open(cfg_path) as f:
        return yaml.safe_load(f)


@dataclass
class FakeSnap:
    """Snapshot-Stub inkl. der Carry-Forward-Felder."""
    symbol: str = "SAN.PA"
    price: float = 76.27                       # Live/Teilbalken (Fr intraday)
    rsi14: Optional[float] = 49.4
    volume_multiplier_today: Optional[float] = 0.10   # partiell
    prev_volume_multiplier: Optional[float] = 1.03    # Do-Schluss final
    prev_close: Optional[float] = 76.36               # Do-Schluss (bestätigt)
    last_bar_date: Optional[str] = "2026-05-29"       # heute (werdende Kerze)
    prev_open: Optional[float] = None
    today_lower_wick_pct: Optional[float] = None
    today_close: Optional[float] = None
    today_open: Optional[float] = None
    today_high: Optional[float] = None
    today_low: Optional[float] = None


TODAY = date(2026, 5, 29)
FORMING_HOUR = 9    # 09 UTC = 11 CEST, Sitzung läuft (vor hard_hour 20)
FINAL_HOUR = 21     # nach hard_hour → Sitzung final


def _gt_trigger(single=76.30, vol_mult=1.0):
    return ParsedTrigger(
        label="A", raw="Daily-Close >76,30€ + Vol >Avg-20d",
        price_op=">", price_single=single,
        require_volume=True, vol_multiplier=vol_mult,
    )


# ------------------------------------------------------------------
# Helper-Units
# ------------------------------------------------------------------

class TestHelpers:
    def test_is_close_breakout_gt(self):
        assert _is_close_breakout_trigger(_gt_trigger()) is True

    def test_is_close_breakout_range_breakout(self):
        t = ParsedTrigger(label="A", raw="", price_op="in_range",
                           price_low=29.65, price_high=30.30, zone_kind="breakout")
        assert _is_close_breakout_trigger(t) is True

    def test_pullback_zone_not_close_breakout(self):
        t = ParsedTrigger(label="A", raw="", price_op="in_range",
                           price_low=72.0, price_high=72.5, zone_kind="pullback")
        assert _is_close_breakout_trigger(t) is False

    def test_reverse_close_trigger_excluded(self):
        t = _gt_trigger()
        t.require_hammer = True
        assert _is_close_breakout_trigger(t) is False

    def test_touch_trigger_excluded(self):
        t = ParsedTrigger(label="A", raw="", price_op="approx",
                          price_single=240.0, is_touch=True)
        assert _is_close_breakout_trigger(t) is False

    def test_forming_true_intraday(self, config):
        snap = FakeSnap()
        assert _last_bar_is_forming(snap, TODAY, FORMING_HOUR, 20) is True

    def test_forming_false_after_hard_hour(self, config):
        snap = FakeSnap()
        assert _last_bar_is_forming(snap, TODAY, FINAL_HOUR, 20) is False

    def test_forming_false_prior_session_bar(self, config):
        snap = FakeSnap(last_bar_date="2026-05-28")   # Balken aus Vorsitzung
        assert _last_bar_is_forming(snap, TODAY, FORMING_HOUR, 20) is False

    def test_forming_false_without_timecontext(self, config):
        snap = FakeSnap()
        assert _last_bar_is_forming(snap, None, None, 20) is False


# ------------------------------------------------------------------
# Carry-Forward Verhalten (SAN.PA-Fall)
# ------------------------------------------------------------------

class TestCarryForward:
    def test_confirmed_prior_close_survives_morning(self, config):
        """Kern-Fall: Live 76,27 < Trigger, aber Do-Schluss 76,36 bestätigt →
        BEREIT (Carry-Forward), nicht very_close/BEREIT*."""
        snap = FakeSnap()
        ts = _evaluate_trigger(_gt_trigger(), snap, "LONG", config,
                               now_utc_hour=FORMING_HOUR, today=TODAY)
        assert ts.proximity == "in_zone"
        assert not ts.conditions_missing
        assert "BEREIT" in ts.summary
        assert "Carry-Forward" in ts.summary

    def test_failing_breakout_watch_when_live_below(self, config):
        """Live-Kurs intraday zurück unter Trigger → Failing-Breakout-Watch."""
        snap = FakeSnap(price=76.27)
        ts = _evaluate_trigger(_gt_trigger(), snap, "LONG", config,
                               now_utc_hour=FORMING_HOUR, today=TODAY)
        assert "Failing-Breakout-Watch" in ts.summary

    def test_no_watch_when_live_still_above(self, config):
        """Live hält über Trigger → bestätigt, kein Watch."""
        snap = FakeSnap(price=76.55)
        ts = _evaluate_trigger(_gt_trigger(), snap, "LONG", config,
                               now_utc_hour=FORMING_HOUR, today=TODAY)
        assert ts.proximity == "in_zone"
        assert "Carry-Forward" in ts.summary
        assert "Failing-Breakout-Watch" not in ts.summary

    def test_self_invalidates_when_prior_close_back_inside(self, config):
        """Vortags-Schluss zurück UNTER Trigger (76,20) → NICHT bestätigt."""
        snap = FakeSnap(prev_close=76.20)
        ts = _evaluate_trigger(_gt_trigger(), snap, "LONG", config,
                               now_utc_hour=FORMING_HOUR, today=TODAY)
        assert ts.proximity != "in_zone"
        assert any("≤ 76.30" in m or "76.30" in m for m in ts.conditions_missing)

    def test_volume_fail_on_completed_candle_blocks_bereit(self, config):
        """Do-Schluss preislich ok, aber Vol der Schluss-Kerze < Schwelle
        (KBX-Fall, 0,62×) → kein BEREIT."""
        snap = FakeSnap(prev_volume_multiplier=0.62)
        ts = _evaluate_trigger(_gt_trigger(vol_mult=1.2), snap, "LONG", config,
                               now_utc_hour=FORMING_HOUR, today=TODAY)
        assert any("Vol" in m for m in ts.conditions_missing)
        assert "alle Bedingungen erfüllt" not in ts.summary

    def test_session_final_uses_live_bar(self, config):
        """Nach Hard-Hour ist der letzte Balken final → Live-Auswertung,
        kein Carry-Forward-Vermerk."""
        snap = FakeSnap(price=76.55, volume_multiplier_today=1.10)
        ts = _evaluate_trigger(_gt_trigger(), snap, "LONG", config,
                               now_utc_hour=FINAL_HOUR, today=TODAY)
        assert ts.proximity == "in_zone"
        assert "alle Bedingungen erfüllt" in ts.summary
        assert "Carry-Forward" not in ts.summary

    def test_backward_compat_without_timecontext(self, config):
        """Ohne today/now_utc_hour → alte Logik (Live-Preis), prev_close ignoriert."""
        snap = FakeSnap(price=76.27)   # live unter Trigger
        ts = _evaluate_trigger(_gt_trigger(), snap, "LONG", config)
        assert ts.proximity != "in_zone"   # 76,27 ≤ 76,30 → nicht erfüllt

    def test_range_breakout_carry_forward(self, config):
        """in_range [breakout]: Do-Schluss in Zone → BEREIT trotz Live unter Zone."""
        t = ParsedTrigger(label="A", raw="", price_op="in_range",
                          price_low=29.65, price_high=30.30, zone_kind="breakout",
                          require_volume=True, vol_multiplier=1.0)
        snap = FakeSnap(symbol="DTE.DE", price=29.05, prev_close=29.80,
                        prev_volume_multiplier=1.10)
        ts = _evaluate_trigger(t, snap, "LONG", config,
                               now_utc_hour=FORMING_HOUR, today=TODAY)
        assert ts.proximity == "in_zone"
        assert "Carry-Forward" in ts.summary
        assert "Failing-Breakout-Watch" in ts.summary   # live 29,05 < 29,65

    def test_range_breakout_completed_close_chased_blown_through(self, config):
        """Vortags-Schluss ÜBER Chase-Cap (Zonen-Obergrenze) → DURCHGELAUFEN."""
        t = ParsedTrigger(label="A", raw="", price_op="in_range",
                          price_low=29.65, price_high=30.30, zone_kind="breakout",
                          require_volume=True, vol_multiplier=1.0)
        snap = FakeSnap(symbol="DTE.DE", price=30.60, prev_close=30.55,
                        prev_volume_multiplier=1.10)
        ts = _evaluate_trigger(t, snap, "LONG", config,
                               now_utc_hour=FORMING_HOUR, today=TODAY)
        assert ts.blown_through is True
        assert ts.proximity == "far"
