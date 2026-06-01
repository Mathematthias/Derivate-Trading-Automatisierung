"""Tests für den Verdeckt-BEREIT-Blindfleck-Fix (2026-06-01).

Hintergrund: Der Parser kannte nur den Daily-Hammer (require_hammer als
Boolean). Trigger, die eine 4h-Reverse-/Bounce-Kerze verlangen, wurden vom
filter_engine gegen die DAILY-Kerze geprüft und bei Fehlschlag als harter
Block ("keine Reverse-Kerze" → conditions_missing) gewertet. Folge: Der
Eintrag erschien als NAHE ("in Zone, aber Bedingungen offen"), obwohl der
4h-Reverse evtl. schon gefeuert hatte = verdeckt BEREIT.

Fix:
- state_parser: Feld `reverse_tf` — "4h" wenn die Reverse-/Bounce-Bedingung
  im Entry-Teil (vor 'SL') auf 4h spezifiziert ist; sonst None.
- filter_engine: bei reverse_tf == "4h" wandert der fehlende Daily-Reverse
  von conditions_missing (hart → NAHE) nach conditions_pending (weich →
  BEREIT* mit 4h-Handcheck-Hinweis).
"""

from dataclasses import dataclass
from typing import Optional

import pytest
import yaml

from filter_engine import _evaluate_trigger
from state_parser import ParsedTrigger, _parse_single_trigger


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
    """Minimaler Snapshot-Stub (gespiegelt aus test_filter_pending.py)."""
    symbol: str = "TEST"
    price: float = 100.0
    rsi14: Optional[float] = 50.0
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
# PARSER: reverse_tf-Erkennung
# ============================================================

class TestReverseTfParsing:
    def test_4h_reverse_close_setzt_reverse_tf(self):
        """UNH-[B]-Form: '4h-Reverse-Close' → require_hammer + reverse_tf='4h'."""
        txt = ("Touch 374-385$ [pullback] + 4h-Reverse-Close "
               "(Hammer/Bullish-Engulfing) MIT 4h-EMA20-Reclaim. "
               "SL entry-relativ: Entry -1,5xATR. TP1 ~408$.")
        pt = _parse_single_trigger("B", txt)
        assert pt.require_hammer is True
        assert pt.reverse_tf == "4h"

    def test_4h_bearish_engulfing_setzt_reverse_tf(self):
        """Short-Form: '4h-Bearish-Engulfing' → Engulfing greift + reverse_tf='4h'."""
        txt = "Touch 1680-1710$ + 4h-Bearish-Engulfing in Zone. SL Entry +1,5xATR."
        pt = _parse_single_trigger("A", txt)
        assert pt.require_hammer is True
        assert pt.reverse_tf == "4h"

    def test_daily_reverse_ohne_4h_bleibt_none(self):
        """Reiner Daily-Reverse ohne 4h-Nennung → reverse_tf=None (harter Block bleibt)."""
        txt = "Daily-Close 130-136$ [breakout] + Reverse-Close + Vol >=1,2x Avg-20d."
        pt = _parse_single_trigger("A", txt)
        assert pt.require_hammer is True
        assert pt.reverse_tf is None

    def test_daily_hammer_ohne_4h_bleibt_none(self):
        txt = "Reverse-Kerze (Hammer) ~240€ + RSI 1D <35 + Volumen >= 0,9x Avg."
        pt = _parse_single_trigger("A", txt)
        assert pt.require_hammer is True
        assert pt.reverse_tf is None

    def test_atr_4h_im_sl_erzeugt_kein_falsch_positiv(self):
        """Daily-Reverse mit ATR-4h NUR in der SL-Definition → reverse_tf=None.

        Schützt vor der Falsch-Positiv-Falle: das '4h' der SL-Konvention
        darf den Entry nicht als 4h-Reverse markieren.
        """
        txt = ("Reverse-Close >=240€ + RSI 1D <40. "
               "SL = Reverse-Kerzen-Hoch + 1,0xATR-4h. TP1 260€.")
        pt = _parse_single_trigger("A", txt)
        assert pt.require_hammer is True
        assert pt.reverse_tf is None


# ============================================================
# FILTER: 4h-Reverse → pending/BEREIT* statt missing/NAHE
# ============================================================

def _zone_trigger(reverse_tf):
    """Pullback-Zonen-Trigger 374-385 mit require_hammer, reverse_tf variabel."""
    return ParsedTrigger(
        label="B",
        raw="Touch 374-385$ [pullback] + Reverse-Close",
        price_low=374.0,
        price_high=385.0,
        price_op="in_range",
        zone_kind="pullback",
        require_hammer=True,
        reverse_tf=reverse_tf,
    )


def _no_hammer_snap():
    """Preis in Zone, Daily-Kerze schließt schwach im unteren Drittel
    (UNH-Stand 2026-06-01: Close-Pos ~53%, hier bewusst unter 60% → kein
    Daily-Hammer/Engulfing)."""
    return FakeSnap(
        symbol="UNH",
        price=378.0,
        rsi14=55.0,
        today_open=380.0,
        today_high=383.0,
        today_low=375.0,
        today_close=377.0,          # Close-Pos = (377-375)/(383-375) = 25% → kein Hammer
        today_lower_wick_pct=20.0,  # < 50 → kein Hammer
        prev_open=379.0,
        prev_close=381.0,           # prev bullish → kein Bullish-Engulfing
    )


class TestVerdecktBereitFilter:
    def test_4h_reverse_wird_pending_und_bereit_stern(self, config):
        """reverse_tf='4h' + Preis in Zone + kein Daily-Hammer
        → Reverse landet in conditions_pending (NICHT missing), Summary = BEREIT*."""
        ts = _evaluate_trigger(_zone_trigger("4h"), _no_hammer_snap(), "LONG",
                               config, now_utc_hour=14)
        assert ts.proximity == "in_zone"
        # Reverse darf NICHT als harter Block auftauchen
        assert not any("Reverse-Kerze" in c for c in ts.conditions_missing)
        # … sondern als manueller 4h-Handcheck im pending-Kanal
        assert any("4h manuell" in c for c in ts.conditions_pending)
        # … und damit als BEREIT* (nicht NAHE)
        assert "BEREIT*" in ts.summary

    def test_daily_reverse_bleibt_harter_block_nahe(self, config):
        """reverse_tf=None (Daily) + Preis in Zone + kein Daily-Hammer
        → Reverse bleibt harter Block (conditions_missing), Summary = NAHE."""
        ts = _evaluate_trigger(_zone_trigger(None), _no_hammer_snap(), "LONG",
                               config, now_utc_hour=14)
        assert ts.proximity == "in_zone"
        assert any("Reverse-Kerze" in c for c in ts.conditions_missing)
        assert "BEREIT*" not in ts.summary
        assert "Bedingungen offen" in ts.summary

    def test_4h_reverse_mit_echtem_daily_hammer_ist_voll_bereit(self, config):
        """Feuert der Reverse sogar auf Daily, ist er erfüllt (conditions_met)
        — der 4h-Marker schadet nicht, sondern liefert Bonus-Bestätigung."""
        snap = _no_hammer_snap()
        snap.today_close = 382.5          # Close-Pos = (382,5-375)/(383-375) ≈ 94%
        snap.today_lower_wick_pct = 60.0  # ≥50 → Hammer
        ts = _evaluate_trigger(_zone_trigger("4h"), snap, "LONG",
                               config, now_utc_hour=14)
        assert ts.proximity == "in_zone"
        assert any("Hammer" in c for c in ts.conditions_met)
        assert not any("4h manuell" in c for c in ts.conditions_pending)
        assert "BEREIT" in ts.summary  # voll BEREIT (ohne pending-Stern)
