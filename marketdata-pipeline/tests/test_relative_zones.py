"""Tests für relative Trigger-Zonen (2026-09-04, Journal-Note #527).

Hintergrund: Eine Watchlist-Zone war bis dahin ein EINMAL geschriebener
absoluter Preisbereich. Bei einem Wert, dessen Anker-EMA weiterwandert,
veraltet sie — der Kurs kommt nie in die Zone zurück, weil die Zone stehen
bleibt und die Linie nicht. Messbar am Verfallslauf 2026-09-02: bei fünf von
zehn abgelaufenen Zeilen war nicht der Kurs weggelaufen, sondern die EMA
selbst (MAERSK 4,83 ATR, NXPI 2,32, TPE 2,18).

Fix in zwei Teilen:
  - state_parser: Syntax "Touch EMA20-1D ±0,30 ATR" bzw.
    "Touch EMA50-1D -0,50/+0,20 ATR" → rel_anchor / rel_lo_atr / rel_hi_atr.
    Beim Parsen wird NICHT gerechnet (Kurs/EMA/ATR liegen dort nicht vor).
  - filter_engine: löst die Zone zu Beginn von _evaluate_trigger mit den Daten
    DIESES Laufs in price_low/price_high auf. Damit läuft die gesamte
    bestehende Distanz-, Bucket- und Digest-Logik unverändert weiter.

Regressionsanspruch: absolute Zonen dürfen sich in keinem Punkt anders
verhalten als vorher.
"""

from dataclasses import dataclass
from typing import Optional

import pytest
import yaml

from filter_engine import _evaluate_trigger
from state_parser import _parse_single_trigger, resolve_relative_zone


@pytest.fixture
def config():
    import os
    cfg_path = os.path.join(
        os.path.dirname(__file__), "..", "config", "filter_config.yaml"
    )
    with open(cfg_path) as f:
        return yaml.safe_load(f)


@dataclass
class FakeSnap:
    symbol: str = "TEST"
    price: float = 100.0
    rsi14: Optional[float] = 50.0
    atr14: Optional[float] = 1.182
    ema20: Optional[float] = 24.17
    ema50: Optional[float] = None
    ema100: Optional[float] = None
    ema200: Optional[float] = None
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
# PARSER
# ============================================================

class TestRelativeZoneParsing:
    def test_symmetrisch(self):
        pt = _parse_single_trigger(
            "A", "MOMENTUM-CONTINUATION-LONG: Touch EMA20-1D ±0,30 ATR [pullback] "
                 "+ 4h-Bullish-Reverse-Close (MANUELL). Stopweite entry-relativ -1,5xATR-1D."
        )
        assert pt.rel_anchor == "EMA20"
        assert pt.rel_lo_atr == pytest.approx(-0.30)
        assert pt.rel_hi_atr == pytest.approx(0.30)
        assert pt.price_op == "in_range"
        assert pt.price_low is None and pt.price_high is None  # erst zur Laufzeit
        assert pt.zone_kind == "pullback"
        assert pt.reverse_tf == "4h"      # darf nicht verlorengehen

    def test_asymmetrisch(self):
        pt = _parse_single_trigger(
            "B", "TREND-PULLBACK-LONG: Touch EMA50-1D -0,50/+0,20 ATR [pullback] + RSI-1D >50."
        )
        assert pt.rel_anchor == "EMA50"
        assert pt.rel_lo_atr == pytest.approx(-0.50)
        assert pt.rel_hi_atr == pytest.approx(0.20)
        assert pt.rsi_min == 50

    def test_absolute_zone_unveraendert(self):
        """Regression: der bestehende Absolut-Fall bleibt bitgleich."""
        pt = _parse_single_trigger(
            "A", "Touch 23,90-25,09€ [pullback] (EMA20-1D 23,88) + 4h-Reverse-Close. "
                 "Stopweite entry-relativ -1,5xATR-1D (1,077 -> -1,62)."
        )
        assert pt.rel_anchor is None
        assert pt.price_low == pytest.approx(23.90)
        assert pt.price_high == pytest.approx(25.09)
        assert pt.price_op == "in_range"

    def test_atr_in_sl_definition_erzeugt_keine_zone(self):
        """'1,5xATR' in der Stopweite darf keine relative Zone erzeugen."""
        pt = _parse_single_trigger(
            "A", "Touch 100,00-102,00€ [pullback]. SL = EMA20-1D ±0,30 ATR."
        )
        assert pt.rel_anchor is None
        assert pt.price_low == pytest.approx(100.00)

    def test_ema_ref_wird_gesetzt(self):
        pt = _parse_single_trigger("A", "Touch EMA200-1D ±0,25 ATR [pullback].")
        assert pt.rel_anchor == "EMA200"
        assert pt.ema_ref == "EMA200"


# ============================================================
# RESOLVER
# ============================================================

class TestResolver:
    def test_rechnet_zone_aus_anker_und_atr(self):
        pt = _parse_single_trigger("A", "Touch EMA20-1D ±0,30 ATR [pullback].")
        assert resolve_relative_zone(pt, {"EMA20": 24.17}, 1.182) is True
        assert pt.price_low == pytest.approx(24.17 - 0.30 * 1.182)
        assert pt.price_high == pytest.approx(24.17 + 0.30 * 1.182)

    def test_wandert_mit_der_ema(self):
        """Derselbe Trigger, eine Woche später — die Zone folgt der Linie."""
        pt = _parse_single_trigger("A", "Touch EMA20-1D ±0,30 ATR [pullback].")
        resolve_relative_zone(pt, {"EMA20": 24.17}, 1.182)
        alt = (pt.price_low, pt.price_high)
        resolve_relative_zone(pt, {"EMA20": 25.90}, 1.100)
        assert pt.price_low == pytest.approx(25.90 - 0.33)
        assert pt.price_low > alt[0] and pt.price_high > alt[1]

    def test_idempotent(self):
        pt = _parse_single_trigger("A", "Touch EMA50-1D ±0,40 ATR.")
        resolve_relative_zone(pt, {"EMA50": 50.0}, 2.0)
        erst = (pt.price_low, pt.price_high)
        resolve_relative_zone(pt, {"EMA50": 50.0}, 2.0)
        assert (pt.price_low, pt.price_high) == erst

    @pytest.mark.parametrize("emas,atr", [({}, 1.18), ({"EMA20": None}, 1.18),
                                          ({"EMA20": 24.17}, None), ({"EMA20": 24.17}, 0)])
    def test_ohne_daten_keine_aufloesung(self, emas, atr):
        pt = _parse_single_trigger("A", "Touch EMA20-1D ±0,30 ATR.")
        assert resolve_relative_zone(pt, emas, atr) is False
        assert pt.price_low is None

    def test_absoluter_trigger_wird_nicht_angefasst(self):
        pt = _parse_single_trigger("A", "Touch 10,00-11,00€ [pullback].")
        assert resolve_relative_zone(pt, {"EMA20": 99.0}, 1.0) is False
        assert pt.price_low == pytest.approx(10.00)


# ============================================================
# FILTER-ENGINE: End-to-End
# ============================================================

class TestFilterEngineIntegration:
    def test_kurs_in_der_aufgeloesten_zone_ist_in_zone(self, config):
        pt = _parse_single_trigger("A", "Touch EMA20-1D ±0,30 ATR [pullback].")
        snap = FakeSnap(price=24.20, ema20=24.17, atr14=1.182)
        st = _evaluate_trigger(pt, snap, "LONG", config)
        assert st.distance_pct == pytest.approx(0.0)
        assert any("IN-ZONE" in c for c in st.conditions_met)

    def test_kurs_ausserhalb_wird_als_distanz_gemessen(self, config):
        pt = _parse_single_trigger("A", "Touch EMA20-1D ±0,30 ATR [pullback].")
        snap = FakeSnap(price=23.00, ema20=24.17, atr14=1.182)
        st = _evaluate_trigger(pt, snap, "LONG", config)
        assert st.distance_pct < 0

    def test_fehlender_anker_meldet_statt_zu_crashen(self, config):
        """EMA100 ist im Snapshot None → sauberer 'far'-Status, kein TypeError."""
        pt = _parse_single_trigger("A", "Touch EMA100-1D ±0,30 ATR [pullback].")
        snap = FakeSnap(price=24.20, ema100=None, atr14=1.182)
        st = _evaluate_trigger(pt, snap, "LONG", config)
        assert st.proximity == "far"
        assert any("nicht auflösbar" in c for c in st.conditions_missing)

    def test_fehlende_atr_meldet_statt_zu_crashen(self, config):
        pt = _parse_single_trigger("A", "Touch EMA20-1D ±0,30 ATR [pullback].")
        snap = FakeSnap(price=24.20, ema20=24.17, atr14=None)
        st = _evaluate_trigger(pt, snap, "LONG", config)
        assert st.proximity == "far"
        assert any("ATR-14" in c for c in st.conditions_missing)

    def test_gleiches_ergebnis_wie_aequivalente_absolute_zone(self, config):
        """Kernanspruch: relativ und absolut liefern bei gleichen Zahlen dasselbe."""
        rel = _parse_single_trigger("A", "Touch EMA20-1D ±0,30 ATR [pullback].")
        lo, hi = 24.17 - 0.3546, 24.17 + 0.3546
        ab = _parse_single_trigger("A", f"Touch {lo:.4f}-{hi:.4f}€ [pullback].".replace(".", ","))
        snap = FakeSnap(price=23.50, ema20=24.17, atr14=1.182)
        a = _evaluate_trigger(rel, snap, "LONG", config)
        b = _evaluate_trigger(ab, snap, "LONG", config)
        assert a.distance_pct == pytest.approx(b.distance_pct, abs=1e-6)
        assert a.proximity == b.proximity
