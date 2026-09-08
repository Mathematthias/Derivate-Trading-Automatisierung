"""Tests für den 4h-Layer (2026-09-08).

Der Kern ist die Resample-Semantik: TradingView verankert Intraday-Balken an
der SESSION-Eröffnung, nicht an Mitternacht. Ein Kalender-Resample("4h") würde
Balken erzeugen, die nicht zu den Charts passen, gegen die der User seine
Trigger schreibt. Diese Tests pinnen das Verhalten für NYSE, XETRA und 24h.
"""
from datetime import datetime, timedelta

import pandas as pd
import pytest

from intraday_4h import (
    Indicators4h,
    compute_4h,
    detect_reverse,
    pull_4h,
    resample_1h_to_4h,
)


def bars(start: str, n: int, step_min: int = 60, base: float = 100.0,
         drift: float = 0.0):
    """n 1h-Balken ab `start`, jeder um `drift` höher als der vorige."""
    idx, rows = [], []
    t = pd.Timestamp(start)
    for i in range(n):
        o = base + i * drift
        rows.append({"Open": o, "High": o + 1, "Low": o - 1,
                     "Close": o + 0.5, "Volume": 1000})
        idx.append(t)
        t = t + timedelta(minutes=step_min)
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx))


class TestResample:
    def test_nyse_tag_gibt_zwei_bloecke(self):
        """09:30-16:00 = 7 1h-Balken -> 4 + 3."""
        df = bars("2026-09-07 09:30", 7)
        out = resample_1h_to_4h(df, closed_only=False)
        assert len(out) == 2
        assert out.index[0] == pd.Timestamp("2026-09-07 09:30")
        assert out.index[1] == pd.Timestamp("2026-09-07 13:30")

    def test_xetra_tag_gibt_drei_bloecke(self):
        """09:00-17:30 = 9 1h-Balken -> 4 + 4 + 1."""
        df = bars("2026-09-07 09:00", 9)
        out = resample_1h_to_4h(df, closed_only=False)
        assert len(out) == 3
        assert [t.hour for t in out.index] == [9, 13, 17]

    def test_24h_tag_gibt_sechs_bloecke(self):
        df = bars("2026-09-07 00:00", 24)
        out = resample_1h_to_4h(df, closed_only=False)
        assert len(out) == 6
        assert [t.hour for t in out.index] == [0, 4, 8, 12, 16, 20]

    def test_ohlc_wird_korrekt_aggregiert(self):
        df = bars("2026-09-07 09:00", 4)
        out = resample_1h_to_4h(df, closed_only=False)
        assert out["Open"].iloc[0] == df["Open"].iloc[0]
        assert out["Close"].iloc[0] == df["Close"].iloc[-1]
        assert out["High"].iloc[0] == df["High"].max()
        assert out["Low"].iloc[0] == df["Low"].min()
        assert out["Volume"].iloc[0] == df["Volume"].sum()

    def test_bloecke_laufen_nicht_ueber_tagesgrenzen(self):
        """Der entscheidende Unterschied zum Kalender-Resample."""
        df = pd.concat([bars("2026-09-07 09:30", 7),
                        bars("2026-09-08 09:30", 7)])
        out = resample_1h_to_4h(df, closed_only=False)
        assert len(out) == 4
        assert [t.date().isoformat() for t in out.index] == [
            "2026-09-07", "2026-09-07", "2026-09-08", "2026-09-08"]

    def test_closed_only_verwirft_laufenden_block(self):
        """Tag 1 voll (8 Balken = 2 Bloecke), Tag 2 angefangen (6 = 1 + Rest)."""
        df = pd.concat([bars("2026-09-07 09:00", 8), bars("2026-09-08 09:00", 6)])
        offen = resample_1h_to_4h(df, closed_only=False)
        zu = resample_1h_to_4h(df, closed_only=True)
        assert len(offen) == 4 and len(zu) == 3
        assert zu.index[-1] == pd.Timestamp("2026-09-08 09:00")

    def test_closed_only_behaelt_vollen_letzten_block(self):
        df = pd.concat([bars("2026-09-07 09:00", 8), bars("2026-09-08 09:00", 8)])
        assert len(resample_1h_to_4h(df, closed_only=True)) == 4

    def test_leer_und_unvollstaendig(self):
        assert resample_1h_to_4h(pd.DataFrame()).empty
        assert resample_1h_to_4h(None).empty
        assert resample_1h_to_4h(pd.DataFrame({"Close": [1, 2]})).empty

    def test_nan_zeilen_fliegen_raus(self):
        df = bars("2026-09-07 09:00", 4)
        df.loc[df.index[1], ["Open", "High", "Low", "Close"]] = None
        out = resample_1h_to_4h(df, closed_only=False)
        assert len(out) == 1


class TestReverse:
    def _c(self, rows):
        return pd.DataFrame(rows, index=pd.DatetimeIndex(
            [pd.Timestamp("2026-09-07 09:00") + timedelta(hours=4 * i)
             for i in range(len(rows))]))

    def test_hammer(self):
        df = self._c([
            {"Open": 100, "High": 101, "Low": 99, "Close": 99.5},
            {"Open": 100, "High": 100.2, "Low": 95, "Close": 100.0},
        ])
        bull, bear, why = detect_reverse(df)
        assert bull is True and bear is False and "Hammer" in why

    def test_bullish_engulfing(self):
        df = self._c([
            {"Open": 100, "High": 100.5, "Low": 97, "Close": 97.5},   # rot
            {"Open": 98, "High": 101.5, "Low": 97.8, "Close": 101.0},  # > prev Open
        ])
        bull, bear, why = detect_reverse(df)
        assert bull is True and "Engulfing" in why

    def test_shooting_star(self):
        df = self._c([
            {"Open": 100, "High": 101, "Low": 99, "Close": 100.5},
            {"Open": 100, "High": 105, "Low": 99.8, "Close": 100.0},
        ])
        bull, bear, why = detect_reverse(df)
        assert bear is True and "Shooting-Star" in why

    def test_bearish_engulfing(self):
        df = self._c([
            {"Open": 98, "High": 101, "Low": 97.5, "Close": 100.5},   # gruen
            {"Open": 100, "High": 100.5, "Low": 96, "Close": 97.0},   # < prev Open
        ])
        bull, bear, why = detect_reverse(df)
        assert bear is True and "Engulfing" in why

    def test_neutrale_kerze(self):
        df = self._c([
            {"Open": 100, "High": 101, "Low": 99, "Close": 100.2},
            {"Open": 100.2, "High": 101.2, "Low": 99.2, "Close": 100.4},
        ])
        bull, bear, _ = detect_reverse(df)
        assert bull is False and bear is False

    def test_zu_wenig_balken(self):
        assert detect_reverse(pd.DataFrame()) == (None, None, None)


class TestComputeUndPull:
    def _lange_reihe(self, n_tage=40, drift=0.2):
        parts, base = [], 100.0
        for d in range(n_tage):
            day = (datetime(2026, 7, 1) + timedelta(days=d)).strftime("%Y-%m-%d")
            parts.append(bars(f"{day} 09:00", 8, base=base, drift=drift))
            base += 8 * drift
        return pd.concat(parts)

    def test_indikatoren_werden_berechnet(self):
        ind = compute_4h(self._lange_reihe())
        assert ind.bars_available >= 50
        assert ind.ema20 is not None and ind.ema50 is not None
        assert ind.rsi14 is not None and ind.rsi14_signal is not None
        assert ind.atr14 is not None and ind.close is not None

    def test_stack_bei_aufwaertsdrift_bullisch(self):
        ind = compute_4h(self._lange_reihe(drift=0.3))
        assert ind.stack == "bullish"

    def test_stack_bei_abwaertsdrift_bearisch(self):
        ind = compute_4h(self._lange_reihe(drift=-0.3))
        assert ind.stack == "bearish"

    def test_zu_kurze_reihe_liefert_leere_indikatoren(self):
        ind = compute_4h(bars("2026-09-07 09:00", 8))
        assert ind.bars_available == 2 and ind.ema20 is None

    def test_as_dict_laesst_none_weg(self):
        assert Indicators4h().as_dict() == {"bars_available": 0}

    def test_pull_mit_injiziertem_downloader(self):
        df = self._lange_reihe()
        cols = pd.MultiIndex.from_product([["AAA", "BBB"], df.columns])
        wide = pd.concat([df, df], axis=1)
        wide.columns = cols
        out = pull_4h(["AAA", "BBB"], downloader=lambda s, **k: wide)
        assert set(out) == {"AAA", "BBB"}
        assert out["AAA"].ema20 is not None

    def test_pull_faengt_download_fehler(self):
        def boom(s, **k):
            raise RuntimeError("Yahoo 403")
        assert pull_4h(["AAA"], downloader=boom) == {}

    def test_pull_leere_symbolliste(self):
        assert pull_4h([]) == {}


# ============================================================
# VERDRAHTUNG IN DEN FILTER_ENGINE
# ============================================================
# Der heikle Teil: `evaluate_reverse` schaltet Bucket-Verhalten um. Diese
# Tests pinnen die drei Zustaende, die dabei auseinandergehalten werden
# muessen — aus (Handcheck), an mit Daten (Entscheidung), an ohne Daten
# (Rueckfall auf Handcheck, NICHT auf "verletzt").

from dataclasses import dataclass, field  # noqa: E402
from typing import Optional  # noqa: E402

import yaml  # noqa: E402

from filter_engine import _evaluate_trigger, _tf4h_can_decide  # noqa: E402
from state_parser import ParsedTrigger  # noqa: E402


@pytest.fixture
def config():
    import os
    with open(os.path.join(os.path.dirname(__file__), "..",
                           "config", "filter_config.yaml")) as f:
        return yaml.safe_load(f)


@dataclass
class Snap4h:
    symbol: str = "TEST"
    price: float = 378.0
    rsi14: Optional[float] = 55.0
    volume_multiplier_today: Optional[float] = None
    last_bar_date: Optional[str] = None
    today_open: Optional[float] = 380.0
    today_high: Optional[float] = 383.0
    today_low: Optional[float] = 375.0
    today_close: Optional[float] = 377.0
    today_lower_wick_pct: Optional[float] = 20.0
    prev_open: Optional[float] = 379.0
    prev_close: Optional[float] = 381.0
    tf4h: Optional[dict] = None


def _trg():
    return ParsedTrigger(
        label="A", raw="Touch 374-385$ [pullback] + 4h-Reverse-Close",
        price_low=374.0, price_high=385.0, price_op="in_range",
        zone_kind="pullback", require_hammer=True, reverse_tf="4h",
    )


def _cfg(config, evaluate: bool):
    c = dict(config)
    c["intraday_4h"] = dict(config.get("intraday_4h", {}), evaluate_reverse=evaluate)
    return c


class TestFilterVerdrahtung:
    def test_default_ist_aus(self, config):
        assert config["intraday_4h"]["evaluate_reverse"] is False
        assert config["intraday_4h"]["enabled"] is True

    def test_aus_bleibt_beim_handcheck(self, config):
        snap = Snap4h(tf4h={"reverse_bullish": False, "reverse_bearish": False,
                            "bar_time": "2026-09-08T13:00:00"})
        ts = _evaluate_trigger(_trg(), snap, "LONG", _cfg(config, False), now_utc_hour=14)
        assert any("4h manuell" in c for c in ts.conditions_pending)
        assert "BEREIT*" in ts.summary

    def test_an_mit_bestaetigung_ist_voll_bereit(self, config):
        snap = Snap4h(tf4h={"reverse_bullish": True, "reverse_bearish": False,
                            "reverse_reason": "Hammer (Wick 72%, Close-Pos 94%)",
                            "bar_time": "2026-09-08T13:00:00"})
        ts = _evaluate_trigger(_trg(), snap, "LONG", _cfg(config, True), now_utc_hour=14)
        assert any("4h-Reverse ✓" in c for c in ts.conditions_met)
        assert not ts.conditions_pending
        assert "BEREIT" in ts.summary and "BEREIT*" not in ts.summary

    def test_an_ohne_bestaetigung_ist_harter_block(self, config):
        snap = Snap4h(tf4h={"reverse_bullish": False, "reverse_bearish": False,
                            "bar_time": "2026-09-08T13:00:00"})
        ts = _evaluate_trigger(_trg(), snap, "LONG", _cfg(config, True), now_utc_hour=14)
        assert any("4h-Reverse fehlt" in c for c in ts.conditions_missing)
        assert "BEREIT*" not in ts.summary

    def test_an_aber_KEINE_daten_faellt_auf_handcheck_zurueck(self, config):
        """Der wichtigste Test: fehlende Daten sind kein verletztes Kriterium."""
        ts = _evaluate_trigger(_trg(), Snap4h(tf4h=None), "LONG",
                               _cfg(config, True), now_utc_hour=14)
        assert any("4h manuell" in c for c in ts.conditions_pending)
        assert not any("4h-Reverse fehlt" in c for c in ts.conditions_missing)
        assert "BEREIT*" in ts.summary

    def test_short_liest_die_baerische_seite(self, config):
        snap = Snap4h(tf4h={"reverse_bullish": True, "reverse_bearish": False,
                            "bar_time": "2026-09-08T13:00:00"})
        ts = _evaluate_trigger(_trg(), snap, "SHORT", _cfg(config, True), now_utc_hour=14)
        assert any("4h-Reverse fehlt" in c for c in ts.conditions_missing)

    def test_can_decide_helfer(self, config):
        assert _tf4h_can_decide(Snap4h(tf4h=None), _cfg(config, True)) is False
        assert _tf4h_can_decide(Snap4h(tf4h={}), _cfg(config, True)) is False
        assert _tf4h_can_decide(
            Snap4h(tf4h={"reverse_bullish": False}), _cfg(config, True)) is True
        assert _tf4h_can_decide(
            Snap4h(tf4h={"reverse_bullish": True}), _cfg(config, False)) is False


# ============================================================
# RSI-ZEITEBENE UND RSI-CROSS (2026-09-08)
# ============================================================
# Zwei Befunde desselben Tages: (1) "RSI-4h >40" wurde still gegen den
# DAILY-RSI geprueft — die Regex "RSI[^<>]*>" frisst das "-4h" mit.
# (2) "RSI-4h Cross ueber die Signallinie" wurde vom Parser UEBERHAUPT
# NICHT erkannt: weder geprueft noch als pending gemeldet. Die Bedingung
# stand in 21 von 38 aktiven Triggern und existierte fuer die Pipeline nicht.

from state_parser import _parse_triggers  # noqa: E402


class TestRsiParsing:
    def _p(self, txt):
        return _parse_triggers("Touch 100-110€ [pullback] + " + txt)[0]

    def test_zeitebene_der_schwelle_wird_erkannt(self):
        assert self._p("RSI-4h >40.").rsi_min_tf == "4h"
        assert self._p("RSI-1D >50.").rsi_min_tf == "1D"
        assert self._p("RSI-1D <60.").rsi_max_tf == "1D"

    def test_schwellenwert_unveraendert(self):
        """Regression: die Werte selbst duerfen sich NICHT geaendert haben."""
        assert self._p("RSI-4h >40.").rsi_min == 40.0
        assert self._p("RSI-1D <60.").rsi_max == 60.0

    def test_schwelle_ohne_zeitebene_bleibt_daily(self):
        p = self._p("RSI >50.")
        assert p.rsi_min == 50.0 and p.rsi_min_tf is None

    @pytest.mark.parametrize("txt,d", [
        ("RSI-4h Cross ueber die Signallinie.", "above"),
        ("RSI-4h ueber Signallinie.", "above"),
        ("RSI-4h ueber die Signallinie.", "above"),
        ("RSI-4h Cross unter die Signallinie.", "below"),
        ("RSI-4h unter die Signallinie.", "below"),
    ])
    def test_alle_belegten_schreibweisen(self, txt, d):
        """Die fuenf Varianten aus der echten Watchlist, Stand 2026-09-08."""
        p = self._p(txt)
        assert p.rsi_cross_tf == "4h" and p.rsi_cross_dir == d

    def test_1d_cross_wird_auch_erkannt(self):
        p = self._p("RSI-1D Cross ueber die Signallinie.")
        assert p.rsi_cross_tf == "1D" and p.rsi_cross_dir == "above"

    def test_kein_cross_kein_feld(self):
        assert self._p("RSI-1D >50.").rsi_cross_dir is None


class TestRsiAuswertung:
    def _trg(self, **kw):
        t = ParsedTrigger(label="A", raw="x", price_low=374.0, price_high=385.0,
                          price_op="in_range", zone_kind="pullback")
        for k, v in kw.items():
            setattr(t, k, v)
        return t

    def test_4h_schwelle_liest_4h_rsi_nicht_daily(self, config):
        """Der Kern des Fixes: Daily 55 wuerde >40 erfuellen, 4h 30 nicht."""
        snap = Snap4h(rsi14=55.0, tf4h={"rsi14": 30.0, "rsi14_signal": 35.0})
        ts = _evaluate_trigger(self._trg(rsi_min=40.0, rsi_min_tf="4h"), snap,
                               "LONG", config, now_utc_hour=14)
        assert any("RSI-4h 30.0 ≤ 40" in c for c in ts.conditions_missing)
        assert not any("RSI 55" in c for c in ts.conditions_met)

    def test_daily_schwelle_unveraendert(self, config):
        snap = Snap4h(rsi14=55.0, tf4h=None)
        ts = _evaluate_trigger(self._trg(rsi_min=50.0, rsi_min_tf="1D"), snap,
                               "LONG", config, now_utc_hour=14)
        assert any("RSI 55.0 > 50" in c for c in ts.conditions_met)

    def test_4h_schwelle_ohne_daten_ist_pending_nicht_missing(self, config):
        snap = Snap4h(rsi14=55.0, tf4h=None)
        ts = _evaluate_trigger(self._trg(rsi_min=40.0, rsi_min_tf="4h"), snap,
                               "LONG", config, now_utc_hour=14)
        assert any("RSI-4h manuell" in c for c in ts.conditions_pending)
        assert not ts.conditions_missing

    def test_cross_default_ist_handcheck(self, config):
        snap = Snap4h(tf4h={"rsi14": 55.0, "rsi14_signal": 50.0})
        ts = _evaluate_trigger(self._trg(rsi_cross_tf="4h", rsi_cross_dir="above"),
                               snap, "LONG", config, now_utc_hour=14)
        assert any("RSI-4h-Cross über Signallinie — manuell" in c
                   for c in ts.conditions_pending)

    def test_cross_an_und_erfuellt(self, config):
        snap = Snap4h(tf4h={"rsi14": 55.0, "rsi14_signal": 50.0})
        cfg = dict(config)
        cfg["intraday_4h"] = dict(config["intraday_4h"], evaluate_rsi_cross=True)
        ts = _evaluate_trigger(self._trg(rsi_cross_tf="4h", rsi_cross_dir="above"),
                               snap, "LONG", cfg, now_utc_hour=14)
        assert any("RSI-4h 55.0 > Signal 50.0" in c for c in ts.conditions_met)

    def test_cross_an_und_verletzt(self, config):
        snap = Snap4h(tf4h={"rsi14": 44.1, "rsi14_signal": 48.0})   # NET, 08.09.
        cfg = dict(config)
        cfg["intraday_4h"] = dict(config["intraday_4h"], evaluate_rsi_cross=True)
        ts = _evaluate_trigger(self._trg(rsi_cross_tf="4h", rsi_cross_dir="above"),
                               snap, "LONG", cfg, now_utc_hour=14)
        assert any("verlangt über" in c for c in ts.conditions_missing)

    def test_cross_an_ohne_daten_faellt_auf_handcheck_zurueck(self, config):
        cfg = dict(config)
        cfg["intraday_4h"] = dict(config["intraday_4h"], evaluate_rsi_cross=True)
        ts = _evaluate_trigger(self._trg(rsi_cross_tf="4h", rsi_cross_dir="above"),
                               Snap4h(tf4h=None), "LONG", cfg, now_utc_hour=14)
        assert any("manuell prüfen" in c for c in ts.conditions_pending)
        assert not ts.conditions_missing

    def test_beide_schalter_default_aus(self, config):
        assert config["intraday_4h"]["evaluate_reverse"] is False
        assert config["intraday_4h"]["evaluate_rsi_cross"] is False


class TestEma9:
    def test_ema9_wird_berechnet(self):
        parts, base = [], 100.0
        for d in range(40):
            day = (datetime(2026, 7, 1) + timedelta(days=d)).strftime("%Y-%m-%d")
            parts.append(bars(f"{day} 09:00", 8, base=base, drift=0.2))
            base += 1.6
        ind = compute_4h(pd.concat(parts))
        assert ind.ema9 is not None and ind.ema20 is not None
        assert ind.ema9 > ind.ema20          # Aufwaertsdrift
