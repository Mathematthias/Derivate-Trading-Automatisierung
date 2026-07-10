"""Tests für den BRIEFING-DIGEST v1 (2026-07-10).

Prüft:
  - classify_watchlist_results ordnet korrekt (ready / in_zone_partial /
    very_close / pending).
  - build_briefing_digest → gültiges JSON → parse_briefing_digest Roundtrip.
  - Note-#118-Fix: in-Zone-mit-fehlender-Bedingung landet in in_zone_partial,
    NICHT in ready; die fehlende Bedingung steht strukturiert unter "missing".
  - render_briefing_from_digest läuft und enthält die erwarteten Abschnitte.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from digest_renderer import build_briefing_digest
from output_renderer import classify_watchlist_results

# pipeline_utils liegt im Skill-Verzeichnis des Repos, nicht in src/.
import os
import sys
_SKILL = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "skills", "derivate-trading"))
if _SKILL not in sys.path:
    sys.path.insert(0, _SKILL)
from pipeline_utils import parse_briefing_digest, render_briefing_from_digest  # noqa: E402


# --- Minimal-Stubs (gespiegelt aus den echten Datenklassen) ----------------

@dataclass
class StubParsedTrigger:
    label: str = "A"
    raw: str = "Pullback 100-102 + Bounce SL 98"
    gate: Optional[str] = None
    price_low: Optional[float] = 100.0
    price_high: Optional[float] = 102.0
    price_single: Optional[float] = None
    price_op: Optional[str] = "in_range"
    ema_ref: Optional[str] = "EMA20"
    require_bounce: bool = True
    require_volume: bool = False
    vol_multiplier: Optional[float] = None
    require_hammer: bool = False
    reverse_tf: Optional[str] = None
    is_touch: bool = False
    rsi_max: Optional[float] = None
    rsi_min: Optional[float] = None
    zone_kind: Optional[str] = None
    sl_kind: Optional[str] = "hard"
    sl_value: Optional[float] = 98.0


@dataclass
class StubEntry:
    name: str = "Teststock (TST)"
    symbol: str = "TST"
    direction: str = "LONG"
    trigger_raw: str = "..."
    status: str = "ACTIVE"
    status_note: str = ""
    triggers: list = field(default_factory=lambda: [StubParsedTrigger()])
    earliest_date: Optional[date] = None
    expiry_date: Optional[date] = None


@dataclass
class StubTrigger:
    label: str = "A"
    proximity: str = "in_zone"
    distance_pct: float = 0.0
    conditions_met: list = field(default_factory=list)
    conditions_missing: list = field(default_factory=list)
    conditions_pending: list = field(default_factory=list)
    summary: str = ""
    blown_through: bool = False
    sl_check: Optional[tuple] = None


@dataclass
class StubSnap:
    symbol: str = "TST"
    price: float = 101.0
    change_pct: Optional[float] = 1.5
    ema20: Optional[float] = 100.0
    ema50: Optional[float] = 98.0
    ema200: Optional[float] = 90.0
    rsi14: Optional[float] = 55.0
    atr14: Optional[float] = 2.0
    move_30d_pct: Optional[float] = 5.0
    distance_from_52w_high_pct: Optional[float] = -10.0
    distance_from_52w_low_pct: Optional[float] = 40.0
    ema200_distance_pct: Optional[float] = 12.0
    days_since_last_ema200_touch: Optional[int] = 30
    weekly_higher_highs_lows: Optional[bool] = True
    next_earnings_date: Optional[str] = "2026-08-01"
    last_earnings_date: Optional[str] = None
    days_since_last_earnings: Optional[int] = None
    last_ex_div_days_ago: Optional[int] = None
    last_ex_div_amount: Optional[float] = None
    today_open: Optional[float] = 100.5
    today_high: Optional[float] = 101.5
    today_low: Optional[float] = 100.0
    today_close: Optional[float] = 101.0
    gap_pct: Optional[float] = None
    atr_zscore_60d: Optional[float] = None
    # Properties, die _setup_class_flags liest
    ema200_meanrev_qualifies: bool = False
    has_any_anomaly: bool = False

    def anomaly_flag_labels(self):
        return []


@dataclass
class StubResult:
    entry: StubEntry
    snapshot: Optional[StubSnap]
    overall_status: str = "active"
    trigger_results: list = field(default_factory=list)
    note: str = ""


def _wr(symbol, proximity, missing=None, status="active", direction="LONG",
        expiry=None):
    ts = StubTrigger(proximity=proximity, conditions_missing=missing or [])
    entry = StubEntry(symbol=symbol, name=f"{symbol} AG", direction=direction,
                      triggers=[StubParsedTrigger()], expiry_date=expiry)
    return StubResult(entry=entry, snapshot=StubSnap(symbol=symbol),
                      overall_status=status, trigger_results=[ts])


def _monitor(symbol):
    """Passiver Position-Monitor: Richtung POSITION-MONITOR, kein Entry-Trigger."""
    entry = StubEntry(symbol=symbol, name=f"{symbol} [MONITOR #4]",
                      direction="POSITION-MONITOR (TIW 24,70)", triggers=[])
    return StubResult(entry=entry, snapshot=StubSnap(symbol=symbol),
                      overall_status="active", trigger_results=[])


# --- Tests -----------------------------------------------------------------

class TestClassification:
    def test_in_zone_ohne_missing_ist_ready(self):
        wr = _wr("AAA", "in_zone", missing=[])
        b = classify_watchlist_results([wr])
        assert wr in b["ready"]
        assert wr not in b["in_zone_partial"]

    def test_in_zone_mit_missing_ist_partial_nicht_ready(self):
        """Note-#118-Kern: in Zone, aber Bedingung offen → in_zone_partial."""
        wr = _wr("BBB", "in_zone", missing=["4h-Reverse fehlt"])
        b = classify_watchlist_results([wr])
        assert wr in b["in_zone_partial"]
        assert wr not in b["ready"]

    def test_very_close_und_pending(self):
        near = _wr("CCC", "very_close")
        pend = _wr("DDD", "watching", status="pending")
        b = classify_watchlist_results([near, pend])
        assert near in b["very_close"]
        assert pend in b["pending"]


class TestDigestRoundtrip:
    def _build(self):
        results = [
            _wr("AAA", "in_zone", missing=[]),                       # ready
            _wr("BBB", "in_zone", missing=["4h-Reverse fehlt"]),     # partial
            _wr("CCC", "very_close"),                                 # very_close
            _wr("EXP", "watching", expiry=date(2026, 7, 11)),        # watching + expiry
        ]
        snaps = {r.entry.symbol: r.snapshot for r in results}
        snaps["^GDAXI"] = StubSnap(symbol="^GDAXI", price=24942.0, change_pct=0.18)
        ts = datetime(2026, 7, 10, 14, 2, 0)
        raw = build_briefing_digest(snaps, results, [], [], ts)
        return raw, results

    def test_ist_gueltiges_json(self):
        raw, _ = self._build()
        data = json.loads(raw)  # darf nicht werfen
        assert data["schema"] == "briefing-digest/v1"
        assert data["tier"] == "A"

    def test_parse_roundtrip_und_counts(self):
        raw, results = self._build()
        dg = parse_briefing_digest(raw)
        assert dg.counts["ready"] == 1
        assert dg.counts["in_zone_partial"] == 1
        assert dg.counts["very_close"] == 1
        assert dg.counts["universe"] == len(results) + 1  # + ^GDAXI
        # universe-Lookup liefert Kurs + abgeleitete Felder
        s = dg.snap("AAA")
        assert s is not None and s["kurs"] == 101.0
        assert s["stack"] == "bullish"           # 100>98>90
        assert s["ext_gate"] == 0.5              # (101-100)/2

    def test_118_missing_bleibt_strukturiert(self):
        raw, _ = self._build()
        dg = parse_briefing_digest(raw)
        partial = dg.bucket("in_zone_partial")
        assert len(partial) == 1
        assert partial[0]["symbol"] == "BBB"
        assert "4h-Reverse fehlt" in partial[0]["missing"]
        # darf NICHT im ready-Bucket auftauchen
        assert all(e["symbol"] != "BBB" for e in dg.bucket("ready"))

    def test_macro_und_expiry(self):
        raw, _ = self._build()
        dg = parse_briefing_digest(raw)
        assert "^GDAXI" in dg.macro
        assert any(w["symbol"] == "EXP" for w in dg.watchlist_expiry)

    def test_trigger_levels_im_ready(self):
        raw, _ = self._build()
        dg = parse_briefing_digest(raw)
        ready = dg.bucket("ready")[0]
        assert ready["trigger"]["zone_low"] == 100.0
        assert ready["trigger"]["sl_value"] == 98.0
        assert "bounce" in ready["trigger"]["conds"]

    def test_position_monitor_wird_erkannt(self):
        results = [_wr("AAA", "in_zone", missing=[]), _monitor("COK.DE")]
        snaps = {"AAA": results[0].snapshot,
                 "COK.DE": StubSnap(symbol="COK.DE", price=23.27)}
        raw = build_briefing_digest(snaps, results, [], [],
                                    datetime(2026, 7, 10, 14, 2))
        dg = parse_briefing_digest(raw)
        assert len(dg.position_monitors) == 1
        assert dg.position_monitors[0]["symbol"] == "COK.DE"
        # Monitor darf NICHT als handelbarer Kandidat auftauchen
        assert all(e["symbol"] != "COK.DE" for e in dg.bucket("ready"))


class TestRenderer:
    def test_render_enthaelt_abschnitte(self):
        results = [_wr("AAA", "in_zone", missing=[])]
        snaps = {"AAA": results[0].snapshot,
                 "^GDAXI": StubSnap(symbol="^GDAXI", price=24942.0, change_pct=0.18)}
        raw = build_briefing_digest(snaps, results, [], [],
                                    datetime(2026, 7, 10, 14, 2))
        dg = parse_briefing_digest(raw)
        out = render_briefing_from_digest(dg)
        assert "BEREIT" in out
        assert "AAA" in out
        assert "Makro-Lage" in out
