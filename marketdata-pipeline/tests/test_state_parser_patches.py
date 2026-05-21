"""Tests für die state_parser-Patches vom 13.05.2026:
- A)/B)/C)-Splitter + "Trigger A:"-Form + alter ·-Separator
- Vol-Regex breit (≥30D-Ø, >Avg-Nd, ≥ N,M× Avg, ≥ N,M× Avg-Nd)
- Touch-Operator (Punkt-Touch ohne Range)
- SL/TP/R:R/ATR-Strip vor Preis-Heuristik
"""

import pytest
from state_parser import _parse_triggers, _split_into_triggers, _strip_sl_tp, _detect_zone_kind


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


# ============================================================
# MARKDOWN-ESCAPE-STRIP (Note #68 Round 2, 2026-05-19)
# Anlass: STATE-Doc hatte 12 Backslashes vor `~`, weil bei jedem
# Read/Write-Cycle ein weiterer Backslash akkumulierte und der alte
# Strip nicht iterativ war. Pipeline failte mit HTTP 400 weil Doc
# auf 1,6 MB aufgebläht war.
# ============================================================

class TestStripMarkdownEscapesIterative:
    def test_single_escape(self):
        """Standard-Fall: ein Backslash vor ~ wird gestrippt."""
        from state_parser import _strip_markdown_escapes
        result = _strip_markdown_escapes(r"Trigger \~240€")
        assert result == "Trigger ~240€"

    def test_double_escape(self):
        """Zwei Backslashes: \\~ wird zu ~ (über \\\\ → \\ → ~)."""
        from state_parser import _strip_markdown_escapes
        result = _strip_markdown_escapes(r"Trigger \\~240€")
        assert "\\" not in result, f"Strip unvollständig: {result!r}"
        assert "~240€" in result

    def test_twelve_backslashes_real_state_doc_case(self):
        """Realer Fall vom STATE-Doc 19.05.2026: 12 Backslashes vor `~`.

        Vorher reduzierte der Single-Pass-Strip nur auf 10 — exponentielles
        Wachstum war die Folge. Iterativ muss vollständig abräumen."""
        from state_parser import _strip_markdown_escapes
        input_text = "EMA100 1D " + "\\" * 12 + "~240€ + RSI 1D " + "\\" * 8 + "<35"
        result = _strip_markdown_escapes(input_text)
        assert "~240€" in result, f"Tilde nicht freigelegt: {result!r}"
        assert "<35" in result, f"Less-than nicht freigelegt: {result!r}"
        assert "\\" not in result, f"Backslashes übrig: {result!r}"

    def test_mixed_specials_all_stripped(self):
        """Verschiedene escapte Sonderzeichen — alle iterativ frei."""
        from state_parser import _strip_markdown_escapes
        # Mehrfach-escaped: # > < * _ ` [ ] ( ) - . ~
        input_text = r"\\\#header \\\> quote \\\<price \\\* italic"
        result = _strip_markdown_escapes(input_text)
        assert "\\" not in result
        assert "#header" in result
        assert "> quote" in result
        assert "<price" in result
        assert "* italic" in result

    def test_idempotent_on_clean_text(self):
        """Bereits sauberer Text bleibt unverändert."""
        from state_parser import _strip_markdown_escapes
        clean = "Setup neu: ~240€ + RSI <35 + Vol >Avg-20d"
        assert _strip_markdown_escapes(clean) == clean

    def test_runaway_protection(self):
        """30-Iterationen-Safety-Belt: extreme Eskalation (1000 Backslashes)
        terminiert in endlicher Zeit, auch wenn das Ergebnis noch nicht voll
        konvergiert ist (sollte aber)."""
        from state_parser import _strip_markdown_escapes
        input_text = "X" + "\\" * 1000 + "~Y"
        result = _strip_markdown_escapes(input_text)
        # Bei 30 Iterationen ist auch 1000 BS voll abgebaut
        # (jede Iteration halbiert die Backslash-Zahl: 2^30 > 10^9)
        assert "~Y" in result

    def test_preserves_non_special_backslash_pairs(self):
        """`\\n`, `\\t` etc. werden NICHT gestrippt — die sind keine
        Markdown-Specials, das sind echte Escape-Sequenzen."""
        from state_parser import _strip_markdown_escapes
        # Hinweis: hier raw-string mit \n als Text, nicht als newline
        result = _strip_markdown_escapes(r"Zeile1\nZeile2")
        # `\n` als Token bleibt — Strip-Set deckt n nicht ab
        assert "\\n" in result or "\nZeile2" in result


# ============================================================
# ZONE-KIND (Task 5, 2026-05-22) — Hybrid-Erkennung Ansatz C
# ============================================================

class TestZoneKind:
    """_detect_zone_kind: expliziter Tag mit Vorrang, sonst Heuristik, sonst None."""

    # --- Expliziter Tag ---
    def test_tag_breakout(self):
        assert _detect_zone_kind("Daily-Close 120-124$ [breakout]") == "breakout"

    def test_tag_pullback(self):
        assert _detect_zone_kind("Touch 374-385$ [pullback]") == "pullback"

    def test_tag_with_zone_suffix(self):
        assert _detect_zone_kind("Zone 120-124$ [breakout-zone]") == "breakout"

    def test_tag_case_insensitive(self):
        assert _detect_zone_kind("Zone [PULLBACK]") == "pullback"

    def test_tag_takes_precedence_over_heuristic(self):
        """Tag [pullback] gewinnt, auch wenn das Wort 'Breakout' im Text steht."""
        assert _detect_zone_kind("Breakout-Logik, aber Zone [pullback]") == "pullback"

    # --- Heuristik-Fallback ---
    def test_heuristic_breakout_word(self):
        assert _detect_zone_kind("Daily-Close >124$ Breakout ueber Konsol-Hoch") == "breakout"

    def test_heuristic_ausbruch_word(self):
        assert _detect_zone_kind("Ausbruchs-Long ueber 124$") == "breakout"

    def test_heuristic_pullback_word(self):
        assert _detect_zone_kind("Pullback in EMA20-Zone 374-385$") == "pullback"

    def test_heuristic_touch_word(self):
        assert _detect_zone_kind("Touch EMA20 1D ~174$") == "pullback"

    # --- Sichere Rückfallebene None ---
    def test_ambiguous_both_words_returns_none(self):
        """Breakout UND Pullback im Text → None (lieber kein Check als falscher)."""
        assert _detect_zone_kind("Pullback nach Breakout, Zone 120-124$") is None

    def test_no_marker_returns_none(self):
        assert _detect_zone_kind("Daily-Close >124$ + Vol >Avg-20d") is None

    # --- Integration über _parse_triggers ---
    def test_parse_triggers_sets_zone_kind(self):
        text = ("A) Daily-Close 1019-1024$ [breakout] + Vol >Avg-20d. "
                "B) Touch 925-952$ [pullback]")
        triggers = _parse_triggers(text)
        assert len(triggers) == 2
        assert triggers[0].zone_kind == "breakout"
        assert triggers[1].zone_kind == "pullback"

    def test_parse_triggers_zone_kind_none_when_unmarked(self):
        triggers = _parse_triggers("Daily-Close >50,46€ + Volumen-Bestaetigung")
        assert len(triggers) == 1
        assert triggers[0].zone_kind is None
