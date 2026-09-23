"""Tests fuer die Grinder-Tempo-Basis trend20 (User-Entscheid 2026-09-24, Variante B).

Anlass: Abgleich Skill <-> Repo. move_30d_pct misst closes.iloc[-22], also 21
Balken = ~30 KALENDERtage; die Klasse versprach "R:R 2 in ~30 HT". Dazu der
Befund, dass der Endpunkt-Move von Tag zu Tag stark zittert (Basiseffekt) und
einen erlahmenden Trend langsam abwertet. Neu: log-lineare Regressionssteigung
ueber 20 Schlusskurse, hochgerechnet auf 20 HT. Fenster = Horizont = 20 HT.
"""
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
import pytest
import yaml

from filter_engine import build_grinders_payload, build_grinders_report
from market_data import TREND_WINDOW_HT, _compute_trend_regression


@pytest.fixture
def config():
    import os
    with open(os.path.join(os.path.dirname(__file__), "..", "config",
                           "filter_config.yaml")) as f:
        return yaml.safe_load(f)


@dataclass
class Snap:
    symbol: str = "TEST"
    price: float = 100.0
    ema20: Optional[float] = 99.5
    ema50: Optional[float] = 95.0
    ema200: Optional[float] = 85.0
    atr14: Optional[float] = 2.0
    rsi14: Optional[float] = 55.0
    move_30d_pct: Optional[float] = 6.0
    trend20_move_pct: Optional[float] = 6.0
    trend20_r2: Optional[float] = 0.9
    weekly_higher_highs_lows: Optional[bool] = True
    last_bar_date: Optional[str] = None

    @property
    def has_bullish_stack(self):
        return self.ema20 > self.ema50 > self.ema200

    @property
    def has_bearish_stack(self):
        return self.ema20 < self.ema50 < self.ema200


def run(config, **kw):
    return build_grinders_payload({"TEST": Snap(**kw)}, config)


# ---------------------------------------------------------------- Regression

class TestRegression:
    def test_fenster_ist_20(self):
        assert TREND_WINDOW_HT == 20

    def test_log_linearer_trend_liefert_seinen_20ht_zuwachs(self):
        # 0,3 % pro Tag, exakt log-linear -> 20 HT = (1,003^20 - 1) = 6,18 %
        closes = pd.Series(100 * 1.003 ** np.arange(60))
        move, r2 = _compute_trend_regression(closes)
        assert move == pytest.approx((1.003 ** 20 - 1) * 100, rel=1e-9)
        assert r2 == pytest.approx(1.0)

    def test_fallender_trend_negativ(self):
        closes = pd.Series(100 * 0.997 ** np.arange(40))
        move, _ = _compute_trend_regression(closes)
        assert move < 0

    def test_zu_wenig_daten(self):
        assert _compute_trend_regression(pd.Series([1.0] * 19)) == (None, None)

    def test_nicht_positive_kurse(self):
        s = pd.Series([1.0] * 19 + [0.0])
        assert _compute_trend_regression(s) == (None, None)

    def test_flacher_kurs_r2_none(self):
        move, r2 = _compute_trend_regression(pd.Series([50.0] * 25))
        assert move == pytest.approx(0.0) and r2 is None

    def test_skaleninvariant_gbx_gbp(self):
        base = pd.Series(11.4 * 1.002 ** np.arange(30))
        a, _ = _compute_trend_regression(base)
        b, _ = _compute_trend_regression(base * 100)
        assert a == pytest.approx(b)

    def test_erlahmter_trend_wird_schneller_abgewertet_als_endpunkt(self):
        # 30 Tage +0,25/Tag, dann 10 Tage flach (Modellfall aus dem Chat 2026-09-24)
        p = pd.Series([100 + min(0.25 * i, 7.5) for i in range(41)])
        move, _ = _compute_trend_regression(p)
        end21 = (p.iloc[-1] / p.iloc[-22] - 1) * 100
        voll = (107.5 / 102.5 - 1) * 100   # Referenz: 20 T ungebremster Anstieg
        assert move < end21 < voll

    def test_ruhiger_als_endpunkt_move(self):
        rng = np.random.default_rng(7)
        p = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.001, 0.01, 800))))
        reg = [_compute_trend_regression(p.iloc[: i + 1])[0] for i in range(60, 800)]
        end = [(p.iloc[i] / p.iloc[i - 21] - 1) * 100 for i in range(60, 800)]
        assert np.std(np.diff(reg)) < 0.7 * np.std(np.diff(end))


# ---------------------------------------------------------------- Filter

class TestTempoBasis:
    def test_default_basis_ist_trend20(self, config):
        assert config["grinders"]["tempo_basis"] == "trend20"

    def test_tempo_rechnet_auf_trend20(self, config):
        # ATR 2 % -> Ziel 6 %; trend20 4,8 -> 0,80, move30d 9,0 -> waere 1,50
        g = run(config, trend20_move_pct=4.8, move_30d_pct=9.0)[0]
        assert g["tempo"] == pytest.approx(0.80)
        assert g["tempo_basis"] == "trend20"
        assert g["trend20"] == 4.8 and g["move30d"] == 9.0 and g["r2"] == 0.9
        assert g["sizing_daempfer"] is True

    def test_rueckfall_auf_move30d_wenn_trend20_fehlt(self, config):
        g = run(config, trend20_move_pct=None, move_30d_pct=6.0)[0]
        assert g["tempo"] == pytest.approx(1.0)
        assert g["tempo_basis"] == "move30d_fallback"

    def test_rollback_schalter(self, config):
        cfg = dict(config)
        cfg["grinders"] = dict(config["grinders"], tempo_basis="move30d")
        g = run(cfg, trend20_move_pct=3.0, move_30d_pct=6.0)[0]
        assert g["tempo"] == pytest.approx(1.0) and g["tempo_basis"] == "move30d"
        assert build_grinders_report({"T": Snap()}, cfg)["tempo_basis"] == "move30d"

    def test_richtung_kommt_aus_trend20(self, config):
        # Bullstack, alter 30d-Move positiv, aber die Regression dreht schon: raus
        assert run(config, trend20_move_pct=-1.0, move_30d_pct=6.0) == []

    def test_erlahmter_grinder_faellt_unter_den_boden(self, config):
        # move30d haette 0,83 (drin), trend20 0,50 -> unter 0,6, abgeschlossener Balken
        assert run(config, trend20_move_pct=3.0, move_30d_pct=5.0) == []

    def test_report_meldet_basis(self, config):
        assert build_grinders_report({"T": Snap()}, config)["tempo_basis"] == "trend20"

    def test_ohne_beide_moves_kein_eintrag(self, config):
        assert run(config, trend20_move_pct=None, move_30d_pct=None) == []

    def test_short_mit_trend20(self, config):
        g = run(config, ema20=100.3, ema50=105.0, ema200=110.0, price=100.0,
                trend20_move_pct=-6.0, move_30d_pct=-2.0)[0]
        assert g["dir"] == "short" and g["tempo"] == pytest.approx(1.0)


# ---------------------------------------------------------------- Snapshot + Digest

class TestSnapshotUndDigest:
    def test_snapshot_rechnet_trend20(self):
        from market_data import _compute_snapshot
        idx = pd.bdate_range("2026-06-01", periods=80)
        c = 100 * 1.002 ** np.arange(80)
        df = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99,
                           "Close": c, "Volume": 1_000_000}, index=idx)
        snap = _compute_snapshot("TEST.DE", df)
        assert snap.trend20_move_pct == pytest.approx((1.002 ** 20 - 1) * 100, rel=1e-6)
        # move_30d = 21 Balken zurueck (iloc[-22]), NICHT 30 HT
        assert snap.move_30d_pct == pytest.approx((1.002 ** 21 - 1) * 100, rel=1e-6)
        assert snap.trend20_r2 == pytest.approx(1.0)

    def test_digest_traegt_trend20(self):
        from digest_renderer import _compact_snap
        from market_data import _compute_snapshot
        idx = pd.bdate_range("2026-06-01", periods=80)
        c = 100 * 1.002 ** np.arange(80)
        df = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99,
                           "Close": c, "Volume": 1_000_000}, index=idx)
        d = _compact_snap(_compute_snapshot("TEST.DE", df))
        assert d["trend20"] == pytest.approx(4.08, abs=0.01)
        assert d["r2"] == 1.0
