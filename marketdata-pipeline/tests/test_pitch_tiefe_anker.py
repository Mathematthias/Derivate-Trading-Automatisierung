"""Pitch-Scan je Anker (2026-10-12, User „C bitte" / „Und für Shorts auch").

Bis dahin prueften long/short_trend_pullback nur die EMA20 (−1/+2,5 % bzw.
−2,5/+1 %) mit 30d-Move-Filter. `trigger_ema_priority: [EMA20, EMA50]` stand in
der Config, kein Code las den zweiten Eintrag. Anlass: INTC stand am 2026-10-12
an der EMA100 (101,26 / 101,13) und kam nie als Pitch.
"""
import os
import sys

import pandas as pd
import pytest
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "src"))

import market_data as md  # noqa: E402
from filter_engine import (  # noqa: E402
    _check_bucket, _pitch_lane, build_pitches_payload, CandidateMatch,
)


@pytest.fixture
def config():
    with open(os.path.join(_HERE, "..", "config", "filter_config.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def _snap(**kw):
    s = md.TickerSnapshot(symbol=kw.pop("symbol", "T"), timestamp=pd.Timestamp("2026-10-12"),
                          price=kw.pop("price"), prev_close=None)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def _intc():
    # Werte aus dem Digest 2026-10-12 19:33
    return _snap(symbol="INTC", price=101.26, ema20=110.70, ema50=106.88, ema100=101.13, ema200=86.69,
                 atr14=5.76, rsi14=40.2, move_30d_pct=-1.63, distance_from_52w_high_pct=-28.9,
                 distance_from_52w_low_pct=60.0, high_20d=128.0, low_20d=100.9)


def test_intc_kommt_als_ema100_pullback(config):
    m = _check_bucket(_intc(), "long_trend_pullback", config)
    assert m is not None and m.anchor == "EMA100" and "@EMA100" in m.summary


def test_intc_lane_trendkonform_mit_anker(config):
    s = _intc()
    assert _pitch_lane("long_trend_pullback", "long", s, "EMA100")[0] == "trend"   # 2 EMAs ueber dem Kurs
    assert _pitch_lane("long_trend_pullback", "long", s, None)[0] == "counter"     # alte Logik: max 1


def test_ema50_long_mit_touch_unter_dem_anker(config):
    s = _snap(price=99.0, ema20=104.0, ema50=99.8, ema100=95.0, ema200=90.0, atr14=4.0, rsi14=45.0,
              move_30d_pct=-2.0, distance_from_52w_high_pct=-12.0, distance_from_52w_low_pct=30.0)
    m = _check_bucket(s, "long_trend_pullback", config)
    assert m is not None and m.anchor == "EMA50"                       # 0,2 ATR unter EMA50
    assert _pitch_lane("long_trend_pullback", "long", s, "EMA50")[0] == "trend"


def test_ema20_bleibt_wie_bisher_vorrangig(config):
    s = _snap(price=101.0, ema20=100.5, ema50=97.0, ema100=94.0, ema200=90.0, atr14=2.0, rsi14=55.0,
              move_30d_pct=3.0, distance_from_52w_high_pct=-6.0, distance_from_52w_low_pct=30.0)
    m = _check_bucket(s, "long_trend_pullback", config)
    assert m is not None and m.anchor == "EMA20" and "@" not in m.summary


def test_unter_ema200_kein_tiefer_anker(config):
    s = _snap(price=89.0, ema20=104.0, ema50=99.0, ema100=95.0, ema200=90.0, atr14=4.0, rsi14=40.0,
              move_30d_pct=-8.0, distance_from_52w_high_pct=-20.0, distance_from_52w_low_pct=10.0)
    assert _check_bucket(s, "long_trend_pullback", config) is None


def test_ausserhalb_band_kein_treffer(config):
    s = _snap(price=103.0, ema20=110.0, ema50=106.9, ema100=101.1, ema200=86.7, atr14=5.76, rsi14=42.0,
              move_30d_pct=-1.0, distance_from_52w_high_pct=-25.0, distance_from_52w_low_pct=50.0)
    # 103 liegt 0,33 ATR ueber EMA100 (Band bis +0,50) -> Treffer; 104,5 nicht mehr (0,59)
    assert _check_bucket(s, "long_trend_pullback", config).anchor == "EMA100"
    s.price = 104.5
    assert _check_bucket(s, "long_trend_pullback", config) is None


# --- Short gespiegelt -------------------------------------------------------

def _short_ema50():
    return _snap(symbol="S", price=50.6, ema20=48.0, ema50=50.5, ema100=52.0, ema200=55.0, atr14=1.2,
                 rsi14=52.0, move_30d_pct=2.5, distance_from_52w_high_pct=-25.0,
                 distance_from_52w_low_pct=12.0, high_20d=51.0, low_20d=46.0)


def test_short_ema50_bounce(config):
    m = _check_bucket(_short_ema50(), "short_trend_pullback", config)
    assert m is not None and m.anchor == "EMA50"                     # 0,08 ATR ueber EMA50, 30d positiv
    assert _pitch_lane("short_trend_pullback", "short", _short_ema50(), "EMA50")[0] == "trend"


def test_short_ema100_bounce(config):
    s = _snap(price=51.8, ema20=48.0, ema50=50.0, ema100=52.0, ema200=55.0, atr14=1.2, rsi14=55.0,
              move_30d_pct=4.0, distance_from_52w_high_pct=-25.0, distance_from_52w_low_pct=15.0)
    m = _check_bucket(s, "short_trend_pullback", config)
    assert m is not None and m.anchor == "EMA100"
    assert _pitch_lane("short_trend_pullback", "short", s, "EMA100")[0] == "trend"


def test_short_ueber_ema200_kein_tiefer_anker(config):
    s = _snap(price=55.5, ema20=48.0, ema50=50.0, ema100=52.0, ema200=55.0, atr14=1.2, rsi14=60.0,
              move_30d_pct=8.0, distance_from_52w_high_pct=-10.0, distance_from_52w_low_pct=20.0)
    assert _check_bucket(s, "short_trend_pullback", config) is None


def test_payload_traegt_anker(config):
    m = _check_bucket(_intc(), "long_trend_pullback", config)
    out = build_pitches_payload([m], config, source_tag="US")
    assert out and out[0]["anchor"] == "EMA100" and out[0]["lane"] == "trend"


def test_quote_tiefe_anker_hoechstens_zwei(config):
    rows = ([{"symbol": f"F{i}", "setup": "long_trend_pullback", "lane": "trend", "anchor": "EMA20",
              "rrprox": 1.0 + i / 10} for i in range(4)]
            + [{"symbol": f"T{i}", "setup": "long_trend_pullback", "lane": "trend", "anchor": "EMA100",
                "rrprox": 3.0 + i / 10} for i in range(4)])
    from filter_engine import apply_pitch_quota
    out = apply_pitch_quota(rows, config)
    tief = [r for r in out if r["anchor"] == "EMA100"]
    flach = [r for r in out if r["anchor"] == "EMA20"]
    assert len(tief) == 2 and len(flach) == 3
    assert {r["symbol"] for r in tief} == {"T3", "T2"}       # beste tiefe nach rrprox


def test_alte_pitches_ohne_anker_zaehlen_als_ema20(config):
    from filter_engine import apply_pitch_quota
    rows = [{"symbol": f"A{i}", "setup": "short_trend_pullback", "lane": "trend", "rrprox": 1.0 + i}
            for i in range(5)]
    assert len(apply_pitch_quota(rows, config)) == 5          # ohne tiefe Treffer unveraendert
