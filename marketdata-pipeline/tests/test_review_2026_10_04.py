"""System-Review 2026-10-04 — Filter-Fixes, die der Review im Code gefunden hat.

1. Earnings-Blackout (`earnings_blackout_days`) wird ERSTMALS geprueft — der
   Schluessel stand seit 2026-04-25 in der Config, der Code las ihn nicht.
2. 30d-Move ist KEIN Ausschluss mehr (L8 v3), sondern Flag `late_entry`
   -> sizing_hint "floor_1pct" im Pitch-Payload.
3. Ex-Div-Disqualifier fuer Shorts (`disqualifier_dividend_within_days`)
   wird gelesen.
4. market_data: Breakout-Retest-Felder bo_*/bd_* aus einer OHLCV-Reihe.
"""

import os
import sys
from dataclasses import dataclass
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
import pytest
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
sys.path.insert(0, _SRC)

from filter_engine import (  # noqa: E402
    _check_bucket,
    _is_late_entry,
    _passes_universal_disqualifier,
    build_pitches_payload,
    evaluate_universe,
)
import market_data as md  # noqa: E402


@pytest.fixture
def config():
    with open(os.path.join(_HERE, "..", "config", "filter_config.yaml"),
              encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class Snap:
    symbol: str = "XYZ"
    price: float = 100.0
    ema20: float = 99.0
    ema50: float = 98.0
    ema100: float = 97.0
    ema200: float = 96.0
    atr14: float = 2.0
    rsi14: float = 50.0
    move_30d_pct: float = 5.0
    high_20d: Optional[float] = 112.0
    low_20d: Optional[float] = 90.0
    volume_eur_avg_20d: Optional[float] = 5_000_000.0
    volume_multiplier_today: Optional[float] = 1.0
    distance_from_52w_high_pct: Optional[float] = -10.0
    distance_from_52w_low_pct: Optional[float] = 40.0
    has_bullish_stack: bool = True
    has_bearish_stack: bool = False
    next_earnings_date: Optional[str] = None
    next_ex_div_date: Optional[str] = None
    last_ex_div_days_ago: Optional[int] = None
    bo_level: Optional[float] = None
    bo_bars_ago: Optional[int] = None
    bo_vol_mult: Optional[float] = None
    bo_failed: Optional[bool] = None
    bd_level: Optional[float] = None
    bd_bars_ago: Optional[int] = None
    bd_vol_mult: Optional[float] = None
    bd_failed: Optional[bool] = None


class TestEarningsBlackout:
    T = date(2026, 10, 5)

    def test_earnings_in_fenster_disqualifiziert(self, config):
        s = Snap(next_earnings_date="2026-10-09")       # in 4 Tagen (<= 7)
        assert _passes_universal_disqualifier(s, config, today=self.T) is False

    def test_earnings_heute_disqualifiziert(self, config):
        s = Snap(next_earnings_date="2026-10-05")
        assert _passes_universal_disqualifier(s, config, today=self.T) is False

    def test_earnings_ausserhalb_ok(self, config):
        s = Snap(next_earnings_date="2026-10-20")       # in 15 Tagen
        assert _passes_universal_disqualifier(s, config, today=self.T) is True

    def test_vergangene_earnings_blocken_nicht(self, config):
        s = Snap(next_earnings_date="2026-09-30")
        assert _passes_universal_disqualifier(s, config, today=self.T) is True

    def test_ohne_datum_neutral(self, config):
        """Fehlender Datenpunkt ist kein Veto (EARNINGS_PULL=0)."""
        assert _passes_universal_disqualifier(Snap(), config, today=self.T) is True

    def test_ohne_today_neutral(self, config):
        assert _passes_universal_disqualifier(
            Snap(next_earnings_date="2026-10-06"), config) is True


class TestLateEntryIstFlagNichtVeto:

    def test_30d_move_schliesst_nicht_mehr_aus(self, config):
        s = Snap(move_30d_pct=+28.0)
        assert _passes_universal_disqualifier(s, config, today=date(2026, 10, 5)) is True
        assert _is_late_entry(s, config) is True
        assert _is_late_entry(Snap(move_30d_pct=9.0), config) is False

    def test_flag_landet_am_match_und_im_payload(self, config):
        # Long-Trend-Pullback-Geometrie mit reifem Trend (+22 % in 30 Tagen)
        s = Snap(symbol="RUN", price=100.0, ema20=99.5, rsi14=55.0, move_30d_pct=22.0,
                 high_20d=112.0, distance_from_52w_high_pct=-8.0)
        matches = evaluate_universe({"RUN": s}, excluded_symbols=set(), config=config,
                                    overrides=[], today=date(2026, 10, 5))
        pull = [m for m in matches if m.bucket == "long_trend_pullback"]
        assert pull and pull[0].late_entry is True
        assert "REIFE" in pull[0].summary
        p = build_pitches_payload(pull, config)[0]
        assert p["late_entry"] is True
        assert p["sizing_hint"] == "floor_1pct"

    def test_ohne_reife_kein_flag(self, config):
        s = Snap(symbol="CALM", price=100.0, ema20=99.5, rsi14=55.0, move_30d_pct=6.0,
                 high_20d=112.0, distance_from_52w_high_pct=-8.0)
        matches = evaluate_universe({"CALM": s}, excluded_symbols=set(), config=config,
                                    overrides=[], today=date(2026, 10, 5))
        pull = [m for m in matches if m.bucket == "long_trend_pullback"]
        assert pull and pull[0].late_entry is False


class TestExDivShortDisqualifier:

    def _short_pullback(self, **kw):
        return Snap(price=100.0, ema20=100.5, rsi14=45.0, move_30d_pct=-6.0,
                    has_bullish_stack=False, has_bearish_stack=True,
                    distance_from_52w_low_pct=12.0, low_20d=90.0, **kw)

    def test_ex_tag_in_14_tagen_blockt_short_pullback(self, config):
        s = self._short_pullback(next_ex_div_date="2026-10-15")
        assert _check_bucket(s, "short_trend_pullback", config, today=date(2026, 10, 5)) is None

    def test_ex_tag_spaeter_blockt_nicht(self, config):
        s = self._short_pullback(next_ex_div_date="2026-11-15")
        assert _check_bucket(s, "short_trend_pullback", config, today=date(2026, 10, 5)) is not None

    def test_ohne_today_neutral(self, config):
        s = self._short_pullback(next_ex_div_date="2026-10-06")
        assert _check_bucket(s, "short_trend_pullback", config) is not None


def _ohlcv(closes, vols=None):
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    idx = pd.bdate_range("2026-01-05", periods=n)
    highs = closes + 0.5
    lows = closes - 0.5
    opens = closes.copy()
    vols = np.asarray(vols if vols is not None else [1_000_000] * n, dtype=float)
    return pd.DataFrame({"Open": opens, "High": highs, "Low": lows,
                         "Close": closes, "Volume": vols}, index=idx)


class TestBreakoutRetestFelder:

    def _snap(self):
        return md.TickerSnapshot(symbol="T", timestamp=pd.Timestamp("2026-10-05"),
                                 price=0.0, prev_close=None)

    def test_ausbruch_vor_drei_balken_wird_erkannt(self):
        # 30 Balken flach bei 100 (High 100,5), dann Ausbruchsschluss 104 vor 3 HT
        # (Vol 3x), danach zwei Balken 103/102,5 (Retest), heute 102 (laufend).
        closes = [100.0] * 30 + [104.0, 103.0, 102.5, 102.0]
        vols = [1_000_000] * 30 + [3_000_000, 900_000, 800_000, 700_000]
        df = _ohlcv(closes, vols)
        s = self._snap()
        md._compute_breakout_retest_fields(s, df)
        assert s.bo_level == pytest.approx(100.5)
        assert s.bo_bars_ago == 3
        assert s.bo_vol_mult == pytest.approx(3.0)
        assert s.bo_failed is False
        assert s.bd_level is None

    def test_schluss_zurueck_unter_niveau_ist_fehlausbruch(self):
        closes = [100.0] * 30 + [104.0, 100.2, 99.8, 100.1]   # 99,8 < 100,5
        df = _ohlcv(closes)
        s = self._snap()
        md._compute_breakout_retest_fields(s, df)
        assert s.bo_level == pytest.approx(100.5)
        assert s.bo_failed is True

    def test_laufender_balken_ist_kein_ausbruch(self):
        """Nur abgeschlossene Balken zaehlen — iloc[-1] kann kein Tagesschluss sein."""
        closes = [100.0] * 30 + [104.0]        # Ausbruch waere HEUTE
        df = _ohlcv(closes)
        s = self._snap()
        md._compute_breakout_retest_fields(s, df)
        assert s.bo_level is None

    def test_breakdown_spiegel(self):
        closes = [100.0] * 30 + [96.0, 97.0, 97.5, 98.0]
        vols = [1_000_000] * 30 + [2_000_000, 900_000, 800_000, 700_000]
        s = self._snap()
        md._compute_breakout_retest_fields(s, _ohlcv(closes, vols))
        assert s.bd_level == pytest.approx(99.5)
        assert s.bd_bars_ago == 3
        assert s.bd_vol_mult == pytest.approx(2.0)
        assert s.bo_level is None

    def test_zu_kurze_historie_bleibt_none(self):
        s = self._snap()
        md._compute_breakout_retest_fields(s, _ohlcv([100.0] * 20))
        assert s.bo_level is None and s.bd_level is None

    def test_alter_ausbruch_ausserhalb_des_fensters(self):
        closes = [100.0] * 30 + [104.0] + [103.0] * 12   # Ausbruch vor 12 HT
        s = self._snap()
        md._compute_breakout_retest_fields(s, _ohlcv(closes))
        assert s.bo_level is None


class TestDigestStateBlock:
    """Workflow B: der Digest traegt den Repo-Zustand (Watchlist-Meta, Radar-
    Fenster, Thesen) als Block `state`, damit der Morning Check ihn nicht mehr
    aus dem Journal abschreiben muss."""

    def test_ohne_state_leeres_objekt(self):
        import datetime as dt
        import json
        from digest_renderer import build_briefing_digest
        raw = build_briefing_digest({}, [], [], [], dt.datetime(2026, 10, 5, 6, tzinfo=dt.timezone.utc))
        d = json.loads(raw)
        assert d["schema"] == "briefing-digest/v4"
        assert d["state"] == {}

    def test_state_wird_durchgereicht(self):
        import datetime as dt
        import json
        import state_yaml as sy
        from digest_renderer import build_briefing_digest
        st = {
            "watchlist": {"updated": "x", "entries": [{"symbol": "SIE.DE", "klasse": "trend_pullback", "status": "aktiv",
                                                        "legs": [{"label": "A", "gate": "🟡", "text": "t"}]}]},
            "radar": {"rows": [{"id": "Z1", "date": "2026-10-10", "kat": 1, "ereignis": "E", "status": "offen"}]},
            "thesen": {"thesen": [{"id": "A", "titel": "AI", "verdikt": "spielen", "re_check": "2026-10-09"}]},
        }
        block = sy.state_for_digest(st, date(2026, 10, 5))
        raw = build_briefing_digest({}, [], [], [], dt.datetime(2026, 10, 5, 6, tzinfo=dt.timezone.utc), state=block)
        d = json.loads(raw)
        assert d["state"]["watchlist"][0]["symbol"] == "SIE.DE"
        assert d["state"]["radar"]["einrueckend"][0]["id"] == "Z1"
        assert d["state"]["thesen"][0]["id"] == "A"
        assert d["state"]["updated"]["watchlist"] == "x"
