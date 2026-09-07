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

from filter_engine import (  # noqa: E402
    build_pitches_payload,
    apply_pitch_quota,
    CandidateMatch,
)
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
    ema50: Optional[float] = None
    ema100: Optional[float] = None
    ema200: Optional[float] = None


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
        # Seit 2026-09-07: DDD überlebt. Es ist ein long_trend_pullback und
        # liegt damit in der Trend-Lane, für die der 30d-Move-Filter NICHT gilt
        # (ein Pullback ist per Konstruktion ein Wert, der gerade nicht läuft).
        assert syms == ["BBB", "AAA", "HAG.DE", "DDD"]  # nach rrprox absteigend
        assert "CCC" not in syms  # eng — ⚠️ENG greift lane-unabhängig
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

    def test_trend_quota_cappt(self, config):
        # 12 gültige Trend-Kandidaten → Trend-Quote (6) cappt, nicht top_n
        uni = []
        for i in range(12):
            uni.append(_match(f"T{i}", "long_trend_pullback", 100, 99.5,
                              5.0, +5.0, high_20d=110 + i))  # steigendes rr
        payload = build_pitches_payload(uni, config, source_tag="EU")
        assert len(payload) == config["pitches"]["quota"]["trend"]
        assert all(p["lane"] == "trend" for p in payload)

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


class TestLanesUndQuote:
    """Bucket-4-Quote 6/4 und die Lane-Zuordnung (User-Entscheid 2026-09-07)."""

    def _trend(self, i):
        # high_20d ab 112, damit T0 nicht am ⚠️ENG-Filter (rr < 1,4) hängenbleibt
        return _match(f"T{i}", "long_trend_pullback", 100, 99.5, 5.0, +5.0,
                      high_20d=112 + i)

    def _counter(self, i):
        # reversal_long braucht Bewegung — die Counter-Lane behält den Filter
        return _match(f"C{i}", "reversal_long", 100, 106.0, 5.0, -12.0,
                      high_20d=118 + i)

    def test_move_filter_gilt_nur_counter(self, config):
        """Der 30d-Move-Filter darf einen Trend-Pullback nicht mehr killen."""
        trendlos_trend = _match("TP", "long_trend_pullback", 100, 100.0, 5.0,
                                +0.2, high_20d=112)
        trendlos_rev = _match("RV", "reversal_long", 100, 106.0, 5.0,
                              +0.2, high_20d=118)
        syms = [p["symbol"] for p in
                build_pitches_payload([trendlos_trend, trendlos_rev], config)]
        assert "TP" in syms      # Trend-Lane: kein Move-Gate
        assert "RV" not in syms  # Counter-Lane: Gate greift weiter

    def test_quote_trennt_die_toepfe(self, config):
        uni = [self._trend(i) for i in range(9)] + [self._counter(i) for i in range(9)]
        payload = build_pitches_payload(uni, config, source_tag="EU")
        q = config["pitches"]["quota"]
        lanes = [p["lane"] for p in payload]
        assert lanes.count("trend") == q["trend"]
        assert lanes.count("counter") == q["counter"]
        # Reihenfolge IST die Suchbudget-Zuteilung: Trend zuerst
        assert lanes == ["trend"] * q["trend"] + ["counter"] * q["counter"]

    def test_counter_verdraengt_trend_nicht(self, config):
        """Der Kern des Auftrags: hoher RRprox auf Counter darf Trend nicht kicken."""
        # Counter mit weit besserem rr als jeder Trend-Kandidat
        stark = _match("XX", "reversal_long", 100, 112.0, 5.0, -15.0, high_20d=160)
        uni = [stark] + [self._trend(i) for i in range(6)]
        syms = [p["symbol"] for p in build_pitches_payload(uni, config)]
        assert len([s for s in syms if s.startswith("T")]) == 6
        assert "XX" in syms

    def test_faecher_stuft_short_herab(self, config):
        """Note #542: bearischer Stack, aber Kurs über dem Fächer → counter."""
        snap = FakeSnap(symbol="AMV", price=37.5, ema20=36.64, atr14=1.4,
                        move_30d_pct=-5.0, rsi14=54.8, low_20d=30.0)
        snap.ema50, snap.ema100, snap.ema200 = 37.02, 37.35, 38.01
        m = CandidateMatch(symbol="AMV", bucket="short_trend_pullback",
                           snapshot=snap, score=0.0, summary="")
        p = build_pitches_payload([m], config)[0]
        assert p["lane"] == "counter"
        assert p["below_emas"] == 1
        assert "Stack-Reclaim" in p["fan_note"]

    def test_faecher_laesst_echten_short_trend_durch(self, config):
        snap = FakeSnap(symbol="DUE", price=17.84, ema20=17.84, atr14=0.48,
                        move_30d_pct=-0.8, rsi14=49.5, low_20d=15.0)
        snap.ema50, snap.ema100, snap.ema200 = 18.15, 18.89, 19.78
        m = CandidateMatch(symbol="DUE", bucket="short_trend_pullback",
                           snapshot=snap, score=0.0, summary="")
        p = build_pitches_payload([m], config)[0]
        assert p["lane"] == "trend"
        assert p["below_emas"] == 3
        assert p["fan_note"] is None
        assert p["fan_span_atr"] == pytest.approx(2.19, abs=0.05)

    def test_apply_pitch_quota_auf_fertiger_liste(self, config):
        """Der Tier-A-Merge-Pfad (EU+US zusammen)."""
        rows = ([{"lane": "counter", "rrprox": 5.0 - i} for i in range(6)]
                + [{"lane": "trend", "rrprox": 1.5 - i * 0.1} for i in range(8)])
        out = apply_pitch_quota(rows, config)
        assert [r["lane"] for r in out] == ["trend"] * 6 + ["counter"] * 4
        assert out[0]["rrprox"] == pytest.approx(1.5)   # bester Trend zuerst
