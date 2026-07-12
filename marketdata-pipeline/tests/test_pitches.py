"""Tests für Bucket-4-Pitches im BRIEFING-DIGEST (2026-07-12).

- build_pitches_payload: Ranking nach rrprox, Ethik-Filter, Trend-Gate,
  ⚠️ENG-Filter, top_n-Cap.
- build_briefing_digest: pitches landen im JSON (rückwärtskompatibel leer).
"""

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pytest
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
sys.path.insert(0, _SRC)

from filter_engine import build_pitches_payload, CandidateMatch  # noqa: E402
from digest_renderer import build_briefing_digest  # noqa: E402


@pytest.fixture
def config():
    cfg_path = os.path.join(_HERE, "..", "config", "filter_config.yaml")
    with open(cfg_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class FakeSnap:
    symbol: str
    price: float
    ema20: float
    atr14: float
    move_30d_pct: float
    rsi14: float = 50.0
    high_20d: Optional[float] = None
    low_20d: Optional[float] = None


def _match(symbol, bucket, price, ema20, atr14, move30, high_20d=None, low_20d=None, rsi=50.0):
    snap = FakeSnap(symbol=symbol, price=price, ema20=ema20, atr14=atr14,
                    move_30d_pct=move30, rsi14=rsi, high_20d=high_20d, low_20d=low_20d)
    return CandidateMatch(symbol=symbol, bucket=bucket, snapshot=snap, score=0.0, summary="")


class TestBuildPitchesPayload:

    def _universe(self):
        return [
            # A long, rr = 15/7.5 = 2.0
            _match("AAA", "long_trend_pullback", 100, 99.5, 5.0, +8.0, high_20d=115),
            # B short, rr = 12/4.5 = 2.67 (bester)
            _match("BBB", "short_trend_pullback", 50, 50.2, 3.0, -6.0, low_20d=38),
            # C eng: rr = 5/7.5 = 0.67 < 1.4 → raus
            _match("CCC", "long_trend_pullback", 100, 100.0, 5.0, +4.0, high_20d=105),
            # D trendlos: move30 0.5 < 1.0 → raus
            _match("DDD", "long_trend_pullback", 100, 100.0, 5.0, +0.5, high_20d=112),
            # E Ethik-Ausschluss RHM.DE → raus (trotz gutem rr)
            _match("RHM.DE", "long_trend_pullback", 100, 99.0, 5.0, +7.0, high_20d=120),
            # F Grenzfall HAG.DE: rr = 10/6 = 1.67 → drin, ethics grenzfall
            _match("HAG.DE", "short_trend_pullback", 70, 70.3, 4.0, -5.0, low_20d=60),
        ]

    def test_ranking_and_filters(self, config):
        payload = build_pitches_payload(self._universe(), config, source_tag="EU")
        syms = [p["symbol"] for p in payload]
        # Nur A, B, F überleben
        assert syms == ["BBB", "AAA", "HAG.DE"]  # nach rrprox absteigend
        assert "CCC" not in syms  # eng
        assert "DDD" not in syms  # trendlos
        assert "RHM.DE" not in syms  # Ethik-Ausschluss

    def test_rrprox_descending(self, config):
        payload = build_pitches_payload(self._universe(), config, source_tag="EU")
        rrs = [p["rrprox"] for p in payload]
        assert rrs == sorted(rrs, reverse=True)
        assert payload[0]["rrprox"] == pytest.approx(2.67, abs=0.01)

    def test_grenzfall_marked(self, config):
        payload = build_pitches_payload(self._universe(), config, source_tag="EU")
        hag = next(p for p in payload if p["symbol"] == "HAG.DE")
        assert hag["ethics"] == "grenzfall"
        aaa = next(p for p in payload if p["symbol"] == "AAA")
        assert aaa["ethics"] == "ok"

    def test_fields_present(self, config):
        payload = build_pitches_payload(self._universe(), config, source_tag="US")
        p = payload[0]
        for k in ("symbol", "dir", "setup", "price", "ema20", "dist_pct",
                  "rsi", "move30d", "rrprox", "ethics", "tier"):
            assert k in p
        assert p["tier"] == "US"
        assert p["dir"] in ("long", "short")

    def test_top_n_cap(self, config):
        # 12 gültige Kandidaten → top_n (8) cappt
        uni = []
        for i in range(12):
            uni.append(_match(f"T{i}", "long_trend_pullback", 100, 99.5,
                              5.0, +5.0, high_20d=110 + i))  # steigendes rr
        payload = build_pitches_payload(uni, config, source_tag="EU")
        assert len(payload) == config["pitches"]["top_n"]

    def test_empty_universe(self, config):
        assert build_pitches_payload([], config) == []


class TestDigestPitches:

    def _ts(self):
        return datetime(2026, 7, 12, 8, 0, tzinfo=timezone.utc)

    def test_pitches_in_digest(self):
        pitches = [{"symbol": "BBB", "dir": "short", "rrprox": 2.67, "ethics": "ok"}]
        raw = build_briefing_digest({}, [], [], [], self._ts(), pitches=pitches)
        d = json.loads(raw)
        assert d["pitches"] == pitches

    def test_pitches_default_empty(self):
        # Rückwärtskompatibel: ohne pitches-Arg → leere Liste
        raw = build_briefing_digest({}, [], [], [], self._ts())
        d = json.loads(raw)
        assert d["pitches"] == []
