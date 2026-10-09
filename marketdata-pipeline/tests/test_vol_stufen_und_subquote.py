"""Zweistufiges Volumen-Gate und Trend-Sub-Quote (User-Entscheid 2026-09-18).

Angepasst 2026-10-04 (System-Review): breakout_long/breakdown_short sind jetzt
RETEST-Buckets. Das Volumen-Gate misst das Volumen AM AUSBRUCHSTAG
(bo_vol_mult/bd_vol_mult), Boden 1,2x, Daempfer 1,5x; die Zone ist
Niveau -0,5/+0,75 ATR. `_vol_stufe` bleibt als Helfer bestehen.

Anlass der beiden Aenderungen steht in config/filter_config.yaml:
- Volumen: Querschnittsmessung ueber 1.717 Ticker-Tage plus VOLGATE-Backtest.
  Der Boden bei 1,0x ist gestuetzt, das Band 1,0-1,5 ungemessen -> Daempfer
  statt Rauswurf.
- Sub-Quote: Range- und Pullback-Buckets rechnen ihr rrprox verschieden
  (Measured Move gegen Abstand zum 20d-Extrem, Median 2,93 gegen 1,74). In
  EINER Rangliste verdraengt die erste Sorte die zweite vollstaendig.
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Optional

import pytest
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
sys.path.insert(0, _SRC)

from filter_engine import (  # noqa: E402
    _check_bucket,
    _vol_stufe,
    _trend_sub,
    apply_pitch_quota,
    build_pitches_payload,
    CandidateMatch,
)
import volgate_backtest as vb  # noqa: E402


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
    high_20d: Optional[float] = None
    low_20d: Optional[float] = None
    volume_multiplier_today: Optional[float] = None
    last_ex_div_days_ago: Optional[int] = None
    # Breakout-Retest-Felder (2026-10-04)
    bo_level: Optional[float] = None
    bo_bars_ago: Optional[int] = None
    bo_vol_mult: Optional[float] = None
    bo_failed: Optional[bool] = None
    bd_level: Optional[float] = None
    bd_bars_ago: Optional[int] = None
    bd_vol_mult: Optional[float] = None
    bd_failed: Optional[bool] = None
    next_ex_div_date: Optional[str] = None
    next_earnings_date: Optional[str] = None
    has_bullish_stack: bool = True
    has_bearish_stack: bool = False
    distance_from_52w_high_pct: Optional[float] = -10.0
    distance_from_52w_low_pct: Optional[float] = 40.0


def _long(vol, **kw):
    """breakout_long (Retest): Ausbruch ueber 120 vor 3 HT mit Volumen `vol`,
    Kurs 119,5 = 0,25 ATR unter dem Niveau -> in der Retest-Zone."""
    s = Snap(high_20d=121.0, low_20d=100.0, price=119.5, rsi14=60.0,
             bo_level=120.0, bo_bars_ago=3, bo_vol_mult=vol, bo_failed=False,
             volume_multiplier_today=0.9, **kw)
    return s


def _short(vol, **kw):
    """breakdown_short (Retest): Breakdown unter 80 vor 2 HT, Kurs 80,4 =
    0,2 ATR ueber dem Niveau -> in der Zone."""
    s = Snap(low_20d=79.0, high_20d=100.0, price=80.4, rsi14=40.0,
             move_30d_pct=-5.0, has_bullish_stack=False, has_bearish_stack=True,
             bd_level=80.0, bd_bars_ago=2, bd_vol_mult=vol, bd_failed=False,
             volume_multiplier_today=0.9, **kw)
    return s


class TestVolStufe:
    """Die reine Schwellen-Logik."""

    def test_unter_dem_boden_kein_kandidat(self, config):
        assert _vol_stufe(Snap(volume_multiplier_today=0.99),
                          config["breakdown_short"]) is None  # Boden 1,0 seit 2026-10-09

    def test_auf_dem_boden_ist_drin(self, config):
        assert _vol_stufe(Snap(volume_multiplier_today=1.00),
                          config["breakdown_short"]) is not None

    def test_zwischen_boden_und_daempfer_gedaempft(self, config):
        gedaempft, hint = _vol_stufe(Snap(volume_multiplier_today=1.15),
                                     config["breakout_long"])
        assert gedaempft is True and hint == "eine_stufe"

    def test_ab_daempfer_volle_groesse(self, config):
        gedaempft, hint = _vol_stufe(Snap(volume_multiplier_today=1.3),
                                     config["breakout_long"])  # Daempfer 1,3 seit 2026-10-09
        assert gedaempft is False and hint == "voll"

    def test_short_daempfer_geht_auf_den_1prozent_floor(self, config):
        """Punkt 3 des Entscheids: bei Shorts greift der Daempfer haerter."""
        gedaempft, hint = _vol_stufe(Snap(volume_multiplier_today=1.15),
                                     config["breakdown_short"])
        assert gedaempft is True and hint == "floor_1pct"

    def test_ohne_daempfer_config_verhaelt_es_sich_wie_frueher(self):
        """Rueckwaertskompatibel: fehlt die Daempfer-Schwelle, ist der Boden alles."""
        cfg = {"volume_multiplier_min": 1.5}
        assert _vol_stufe(Snap(volume_multiplier_today=1.2), cfg) is None
        assert _vol_stufe(Snap(volume_multiplier_today=1.6), cfg) == (False, "voll")

    def test_fehlendes_volumen_ist_kein_kandidat(self, config):
        assert _vol_stufe(Snap(volume_multiplier_today=None),
                          config["breakout_long"]) is None


class TestCheckBucketMitStufen:
    """Die Gates im Bucket selbst — inklusive der Format-Falle im Summary."""

    def test_breakdown_short_unter_boden_raus(self, config):
        assert _check_bucket(_short(0.9), "breakdown_short", config) is None

    def test_breakdown_short_gedaempft_kommt_durch(self, config):
        m = _check_bucket(_short(1.15), "breakdown_short", config)
        assert m is not None
        assert m.vol_daempfer is True
        assert m.sizing_hint == "floor_1pct"

    def test_breakout_long_voll(self, config):
        m = _check_bucket(_long(1.8), "breakout_long", config)
        assert m is not None and m.vol_daempfer is False and m.sizing_hint == "voll"
        assert "DÄMPFER" not in m.summary

    def test_stack_gate_bleibt_hart(self, config):
        """Das Volumengate ist NICHT der einzige Filter — Befund 2026-09-18."""
        s = _short(2.0)
        s.has_bearish_stack = False        # neutraler Stack, wie NFLX
        assert _check_bucket(s, "breakdown_short", config) is None

    def test_rsi_gate_bleibt_hart(self, config):
        s = _long(2.0)
        s.rsi14 = 75.0                      # ueber rsi_max 70, wie UPM.HE
        assert _check_bucket(s, "breakout_long", config) is None

    def test_marker_steht_am_ENDE_und_bricht_den_vol_parser_nicht(self, config):
        """Note #556: Feldtrenner sind zwei Leerzeichen, das Mal-Zeichen U+00D7.

        Ein Einschub zwischen 'Vol=' und 'RSI=' wuerde den Skill-Parser
        brechen. Der Marker gehoert deshalb hinter alles andere.
        """
        import re
        m = _check_bucket(_short(1.15), "breakdown_short", config)
        assert m.summary.rstrip().endswith("⚠️VOL-DÄMPFER")
        assert re.search(r"Vol=1\.1×\s\sRSI=\d+", m.summary) or re.search(r"Vol=1\.15×\s\sRSI=\d+", m.summary) or re.search(r"Vol=1\.2×\s\sRSI=\d+", m.summary)
        # Retest-Marker steht hinter dem RRprox-Suffix, vor dem Daempfer
        assert re.search(r"RSI=\d+(\s\sRRprox=[\d.]+(\s*⚠️ENG)?)?\s\sRetest=2HT", m.summary)


class TestRetestGates:
    """Neudefinition 2026-10-04: Ausbruch = Ereignis, Kandidat = Retest."""

    def test_kein_ausbruch_im_fenster_kein_kandidat(self, config):
        s = _long(2.0); s.bo_level = None; s.bo_bars_ago = None
        assert _check_bucket(s, "breakout_long", config) is None

    def test_ausbruch_zu_alt(self, config):
        s = _long(2.0); s.bo_bars_ago = 11
        assert _check_bucket(s, "breakout_long", config) is None

    def test_fehlausbruch_raus(self, config):
        s = _long(2.0); s.bo_failed = True
        assert _check_bucket(s, "breakout_long", config) is None

    def test_kurs_zu_weit_ueber_dem_niveau_ist_kein_retest(self, config):
        s = _long(2.0); s.price = 122.0          # +1,0 ATR ueber 120
        assert _check_bucket(s, "breakout_long", config) is None

    def test_kurs_zu_weit_unter_dem_niveau_ist_kein_retest(self, config):
        s = _long(2.0); s.price = 118.5          # -0,75 ATR unter 120
        assert _check_bucket(s, "breakout_long", config) is None

    def test_in_zone_ist_kandidat_und_traegt_retest_marker(self, config):
        m = _check_bucket(_long(2.0), "breakout_long", config)
        assert m is not None
        assert "20d-High=120.00" in m.summary and "Retest=3HT" in m.summary

    def test_heutiges_volumen_zaehlt_nicht(self, config):
        """Das Gate misst den Ausbruchstag, nicht den Retest-Tag."""
        s = _long(2.0); s.volume_multiplier_today = 0.3
        assert _check_bucket(s, "breakout_long", config) is not None

    def test_short_exdiv_bald_blockt(self, config):
        from datetime import date
        s = _short(2.0); s.next_ex_div_date = "2026-10-10"
        assert _check_bucket(s, "breakdown_short", config, today=date(2026, 10, 4)) is None
        assert _check_bucket(s, "breakdown_short", config, today=date(2026, 9, 1)) is not None


class TestTrendSubQuote:

    def _rows(self, n_range, n_pull):
        rows = [{"lane": "trend", "setup": "breakdown_short",
                 "symbol": f"R{i}", "rrprox": 5.0 - i * 0.01} for i in range(n_range)]
        rows += [{"lane": "trend", "setup": "long_trend_pullback",
                  "symbol": f"P{i}", "rrprox": 2.0 - i * 0.01} for i in range(n_pull)]
        return rows

    def test_trend_sub_ordnet_die_buckets_zu(self):
        assert _trend_sub("breakout_long") == "range"
        assert _trend_sub("breakdown_short") == "range"
        assert _trend_sub("long_trend_pullback") == "pullback"
        assert _trend_sub("short_trend_pullback") == "pullback"

    def test_fuenf_und_fuenf(self, config):
        out = apply_pitch_quota(self._rows(8, 8), config)
        syms = [r["symbol"] for r in out]
        assert len([s for s in syms if s.startswith("R")]) == 5
        assert len([s for s in syms if s.startswith("P")]) == 5

    def test_kein_uebertrag_wenn_ein_topf_leer_ist(self, config):
        """Der Kern: 10 Range-Kandidaten bekommen trotzdem nur 5 Plaetze.

        Ohne diese Zusage haette der Range-Bucket die Lane wieder ganz belegt —
        genau der Befund, der die Sub-Quote ausgeloest hat.
        """
        out = apply_pitch_quota(self._rows(10, 0), config)
        assert len(out) == 5

    def test_pullbacks_ueberleben_starke_range_kandidaten(self, config):
        """Range-rrprox ist strukturell groesser; vorher hat das alles gekickt."""
        out = apply_pitch_quota(self._rows(10, 3), config)
        syms = [r["symbol"] for r in out]
        assert {"P0", "P1", "P2"} <= set(syms)

    def test_ohne_sub_quote_alte_logik(self, config):
        cfg = {"pitches": {"quota": {"trend": 6, "counter": 4}}}
        out = apply_pitch_quota(self._rows(10, 3), cfg)
        assert len(out) == 6

    def test_payload_traegt_die_neuen_felder(self, config):
        m = _check_bucket(_short(1.15), "breakdown_short", config)
        p = build_pitches_payload([m], config)[0]
        assert p["trend_sub"] == "range"
        # Fuer Retest-Buckets ist das relevante Volumen das des Ausbruchstags
        assert p["vol_mult"] == pytest.approx(1.15)
        assert p["vol_daempfer"] is True
        assert p["sizing_hint"] == "floor_1pct"


class TestBacktestBaender:
    """Patch 4: absolute Vol-Baender, damit 1,0-1,5 messbar wird."""

    @pytest.mark.parametrize("vol,erwartet", [
        (0.59, "<0.6"), (0.6, "0.6-0.8"), (0.79, "0.6-0.8"),
        (0.8, "0.8-1.0"), (0.999, "0.8-1.0"),
        (1.0, "1.0-1.2"), (1.19, "1.0-1.2"),
        (1.2, "1.2-1.5"), (1.49, "1.2-1.5"),
        (1.5, ">=1.5"), (7.7, ">=1.5"),
    ])
    def test_bandgrenzen(self, vol, erwartet):
        assert vb.band_of(vol) == erwartet

    def test_kein_volumen_kein_band(self):
        assert vb.band_of(None) is None

    def test_gamechanger_range_bullet_wird_geparst(self, tmp_path):
        """Die drei Format-Fallen aus Note #556 sind hier alle drin:
        zwei Leerzeichen als Trenner, U+00D7 als Mal-Zeichen, und beim
        Short-Bullet KEIN erzwungenes Vorzeichen in der Klammer."""
        f = tmp_path / "GAMECHANGER-HUNT-US-2026-09-17-2233.md"
        f.write_text(
            "## Stufe 2\n\n### Breakdown Short\n\n"
            "- TMUS: 166.45  20d-Low=166.35 (+0.06%)  Vol=1.7×  RSI=34  RRprox=2.94\n"
            "- NFLX: 75.31  20d-Low=75.03 (0.37%)  Vol=1.0×  RSI=43  RRprox=2.58\n\n"
            "### Breakout Long\n\n"
            "- AAPL: 337.00  20d-High=338.30 (-0.38%)  Vol=2.1×  RSI=65  RRprox=2.82\n",
            encoding="utf-8")
        day, prices, signals = vb.parse_gamechanger_file(str(f))
        assert day == "2026-09-17"
        by = {s["ticker"]: s for s in signals}
        assert set(by) == {"TMUS", "NFLX", "AAPL"}
        assert by["TMUS"]["direction"] == "SHORT"
        assert by["AAPL"]["direction"] == "LONG"
        assert by["NFLX"]["vol_final"] == pytest.approx(1.0)
        assert by["NFLX"]["source"] == "gamechanger"
        assert prices["TMUS"] == pytest.approx(166.45)

    def test_gc_dateiauswahl_nimmt_je_tier_das_spaeteste(self, tmp_path):
        for name in ("GAMECHANGER-HUNT-EU-2026-09-17-1134.md",
                     "GAMECHANGER-HUNT-EU-2026-09-17-1834.md",
                     "GAMECHANGER-HUNT-US-2026-09-17-2233.md"):
            (tmp_path / name).write_text("x", encoding="utf-8")
        picked = {os.path.basename(p) for p in vb.pick_gc_files(str(tmp_path))}
        assert picked == {"GAMECHANGER-HUNT-EU-2026-09-17-1834.md",
                          "GAMECHANGER-HUNT-US-2026-09-17-2233.md"}
