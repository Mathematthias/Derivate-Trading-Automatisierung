"""Tests für die state_parser-Patches vom 13.05.2026:
- A)/B)/C)-Splitter + "Trigger A:"-Form + alter ·-Separator
- Vol-Regex breit (≥30D-Ø, >Avg-Nd, ≥ N,M× Avg, ≥ N,M× Avg-Nd)
- Touch-Operator (Punkt-Touch ohne Range)
- SL/TP/R:R/ATR-Strip vor Preis-Heuristik
"""

import pytest
from state_parser import _parse_triggers, _split_into_triggers, _strip_sl_tp


# ============================================================
# SPLITTER
# ============================================================

class TestSplitter:
    def test_klammer_splitter_2_trigger(self):
        """A) ... B) ... → 2 Trigger mit Labels A und B."""
        text = "A) Daily-Close <60€ + Volumen >Avg-20d → Re-Short. B) Daily-Close <58€"
        chunks = _split_into_triggers(text)
        assert len(chunks) == 2
        assert chunks[0][0] == "A"
        assert chunks[1][0] == "B"
        assert "Daily-Close <60€" in chunks[0][1]
        assert "Daily-Close <58€" in chunks[1][1]

    def test_doppelpunkt_splitter_2_trigger(self):
        """A: ... · B: ... → 2 Trigger mit Labels A und B."""
        text = "A: Touch EMA50 33,40–33,60€ + Bounce · B: Daily-Close >35,10€ auf Vol ≥30D-Ø"
        chunks = _split_into_triggers(text)
        assert len(chunks) == 2
        assert chunks[0][0] == "A"
        assert chunks[1][0] == "B"

    def test_trigger_label_form(self):
        """Trigger A: ... → Label A erkannt."""
        text = "Bounce-Short an Re-Resistance. Trigger A: 4h-Bearish-Engulfing"
        chunks = _split_into_triggers(text)
        assert len(chunks) == 1
        assert chunks[0][0] == "A"
        assert "4h-Bearish-Engulfing" in chunks[0][1]

    def test_no_false_match_on_trigger_a_phrase(self):
        """"Alter Trigger A (Pullback 258€) verfallen" darf NICHT als Label-Marker
        gewertet werden (kein ) oder : direkt hinter dem A)."""
        text = "A) Reverse-Kerze ~240€. Alter Trigger A (Pullback 258€) verfallen."
        chunks = _split_into_triggers(text)
        assert len(chunks) == 1, f"Erwartet 1 Trigger, bekam {len(chunks)}: {chunks}"
        assert chunks[0][0] == "A"

    def test_no_label_falls_back_to_dot_separator(self):
        """Trigger ohne Labels → ·-Separator."""
        text = "Pullback ~59$ + 4h-Reversal · Daily-Close >62$"
        chunks = _split_into_triggers(text)
        assert len(chunks) == 2
        assert chunks[0][0] == ""
        assert chunks[1][0] == ""

    def test_single_trigger_no_label(self):
        """Einzelner Trigger ohne Label und ohne ·."""
        text = "Pullback ~59$ + 4h-Reversal (nach Gap +28.9%)"
        chunks = _split_into_triggers(text)
        assert len(chunks) == 1
        assert chunks[0][0] == ""

    def test_rr_not_misread_as_label(self):
        """"R:R 1,2" enthält 'R:' aber kein Trigger-Label."""
        text = "Daily-Close >380$ + RSI 1D >55. R:R 1,2 / 2,4"
        chunks = _split_into_triggers(text)
        assert len(chunks) == 1, f"R:R darf nicht splitten, bekam {len(chunks)}: {chunks}"
        assert chunks[0][0] == ""


# ============================================================
# SL/TP-STRIP
# ============================================================

class TestStripSlTp:
    def test_strip_sl(self):
        assert "SL" not in _strip_sl_tp("Daily-Close >380$. SL <370$.")

    def test_strip_tp(self):
        assert "TP1" not in _strip_sl_tp("Entry. TP1 392$, TP2 404$")
        assert "TP2" not in _strip_sl_tp("Entry. TP1 392$, TP2 404$")

    def test_strip_rr(self):
        assert "R:R" not in _strip_sl_tp("Entry an Bestätigungskerze. R:R 1,2 / 2,4")
        assert "R:R" not in _strip_sl_tp("R:R ~2,5")
        assert "R:R" not in _strip_sl_tp("R:R primär 1,8")

    def test_strip_atr(self):
        assert "ATR" not in _strip_sl_tp("SL <370$ (-1,2ATR)")

    def test_preserve_main_trigger(self):
        """Der eigentliche Preis bleibt erhalten."""
        result = _strip_sl_tp("Daily-Close >380$. SL <370$. TP1 392$")
        assert ">380$" in result
        assert "<370" not in result


# ============================================================
# VOL-REGEX BREIT
# ============================================================

class TestVolRegex:
    def test_old_form_30d_omega(self):
        triggers = _parse_triggers("Daily-Close >35,10€ auf Vol ≥30D-Ø")
        assert len(triggers) == 1
        assert triggers[0].require_volume is True

    def test_avg_nd(self):
        triggers = _parse_triggers("Daily-Close <60€ + Volumen >Avg-20d")
        assert len(triggers) == 1
        assert triggers[0].require_volume is True

    def test_multiplier_with_nd(self):
        triggers = _parse_triggers("Daily-Close >380$ + Volumen ≥ 1,2× Avg-20d")
        assert len(triggers) == 1
        assert triggers[0].require_volume is True
        assert triggers[0].vol_multiplier == pytest.approx(1.2)

    def test_multiplier_no_nd(self):
        triggers = _parse_triggers("Reverse-Kerze ~240€ + Volumen ≥ 0,9× Avg")
        assert len(triggers) == 1
        assert triggers[0].require_volume is True
        assert triggers[0].vol_multiplier == pytest.approx(0.9)


# ============================================================
# TOUCH-OPERATOR
# ============================================================

class TestTouchOperator:
    def test_daily_touch_with_currency(self):
        """Daily-Touch 52,33$ → is_touch=True, price_single=52.33, op=approx."""
        triggers = _parse_triggers("A) Daily-Touch 52,33$ + Hammer + Vol >Avg-30d")
        assert len(triggers) == 1
        t = triggers[0]
        assert t.is_touch is True
        assert t.price_op == "approx"
        assert t.price_single == pytest.approx(52.33)

    def test_touch_with_approx(self):
        """Touch ... ~240€ → is_touch=True via Touch-Wort, op=approx via ~."""
        triggers = _parse_triggers("Touch EMA100 1D ~240€ + RSI 1D <35")
        assert len(triggers) == 1
        assert triggers[0].is_touch is True
        assert triggers[0].price_op == "approx"
        assert triggers[0].price_single == pytest.approx(240.0)

    def test_no_touch_word_no_touch_flag(self):
        """Wenn kein "Touch" im Text → is_touch=False, normale approx-Logik."""
        triggers = _parse_triggers("Pullback ~59$")
        assert len(triggers) == 1
        assert triggers[0].is_touch is False
        assert triggers[0].price_op == "approx"


# ============================================================
# SL/TP-STRIP — Effekt auf Preis-Heuristik
# ============================================================

class TestSlTpStrippingInTriggers:
    def test_sl_not_picked_as_price_op(self):
        """SL <370$ darf NICHT als price_op="<", price_single=370 enden,
        weil der echte Trigger ">380$" ist."""
        triggers = _parse_triggers(
            "A) 1D-Schluss >380$ + Volumen ≥ 1,2× Avg-20d + RSI 1D >55. SL <370$ (-1,2ATR). TP1 392$, TP2 404$"
        )
        assert len(triggers) == 1
        t = triggers[0]
        assert t.price_op == ">"
        assert t.price_single == pytest.approx(380.0)
        # Modifikatoren weiter erkannt:
        assert t.require_volume is True
        assert t.vol_multiplier == pytest.approx(1.2)
        assert t.rsi_min == pytest.approx(55.0)


# ============================================================
# REGRESSION — alter Splitter darf weiter funktionieren
# ============================================================

class TestRegression:
    def test_old_a_colon_b_colon_still_works(self):
        triggers = _parse_triggers(
            "A: Touch EMA50 Daily 33,40–33,60€ + Bounce · B: Daily-Close >35,10€ auf Vol ≥30D-Ø"
        )
        assert len(triggers) == 2
        assert triggers[0].label == "A"
        assert triggers[0].price_op == "in_range"
        assert triggers[0].require_bounce is True
        assert triggers[1].label == "B"
        assert triggers[1].price_op == ">"
        assert triggers[1].require_volume is True

    def test_empty_trigger_text(self):
        """ONBERG-Story (Defense/Drohnenabwehr) — Setup ergänzen wenn relevant"""
        triggers = _parse_triggers("ONBERG-Story (Defense/Drohnenabwehr) — Setup ergänzen wenn relevant")
        assert len(triggers) == 1
        # Kein Preis-Op, keine Modifikatoren → leerer Trigger
        assert triggers[0].price_op is None
        assert triggers[0].require_volume is False
        assert triggers[0].require_bounce is False
