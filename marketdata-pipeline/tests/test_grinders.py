"""Tests für den zweiten Pitch-Block: Grinder (2026-09-04, Journal-Note #527).

Hintergrund: Die RRprox-Rangliste vergräbt Werte, die stetig nach oben laufen.
RRprox misst den Abstand Kurs ↔ Zielzone; ein Wert, der an seiner EMA20
entlanggrindet, hat per Definition einen kleinen Abstand und landet hinten.
Messung der Pitch-Liste vom 2026-09-04: Plätze 1–4 counter-trend mit 4,1–7,8 %
Abstand zur EMA20, Plätze 5–7 trendkonform mit +0,36 / +0,81 / −0,73 %.

build_grinders_payload rankt deshalb nach "Tempo" (wie oft der Trend in 30 Tagen
die für R:R 2,0 nötige Strecke geliefert hat) und screent das GESAMTE Universum
statt nur der Bucket-Treffer — ein Grinder erzeugt gerade kein Setup-Signal.
"""

from dataclasses import dataclass
from typing import Optional

import pytest
import yaml

from filter_engine import build_grinders_payload


@pytest.fixture
def config():
    import os
    cfg_path = os.path.join(
        os.path.dirname(__file__), "..", "config", "filter_config.yaml"
    )
    with open(cfg_path) as f:
        return yaml.safe_load(f)


@dataclass
class Snap:
    """Snapshot-Stub mit den Feldern, die der Grinder-Screen liest."""
    symbol: str = "TEST"
    price: float = 100.0
    ema20: Optional[float] = 99.5
    ema50: Optional[float] = 95.0
    ema200: Optional[float] = 85.0
    atr14: Optional[float] = 2.0
    rsi14: Optional[float] = 55.0
    move_30d_pct: Optional[float] = 6.0
    weekly_higher_highs_lows: Optional[bool] = True

    @property
    def has_bullish_stack(self) -> bool:
        if None in (self.ema20, self.ema50, self.ema200):
            return False
        return self.ema20 > self.ema50 > self.ema200

    @property
    def has_bearish_stack(self) -> bool:
        if None in (self.ema20, self.ema50, self.ema200):
            return False
        return self.ema20 < self.ema50 < self.ema200


def run(config, **kw):
    return build_grinders_payload({"TEST": Snap(**kw)}, config)


class TestAufnahme:
    def test_sauberer_grinder_kommt_durch(self, config):
        out = run(config)
        assert len(out) == 1
        g = out[0]
        assert g["symbol"] == "TEST" and g["dir"] == "long" and g["setup"] == "grinder"

    def test_neutraler_stack_faellt_raus(self, config):
        assert run(config, ema20=90.0, ema50=95.0, ema200=85.0) == []

    def test_zu_hohe_atr_faellt_raus(self, config):
        """ATR% 6 > max_atr_pct 2,5 — der Stop wäre zu teuer."""
        assert run(config, atr14=6.0) == []

    def test_zu_weit_von_der_ema20_faellt_raus(self, config):
        """Ein Wert 2 ATR über der EMA20 klebt nicht, er ist extended."""
        assert run(config, price=103.5) == []

    def test_konsolidierung_im_bullstack_faellt_raus(self, config):
        """MRK.DE-Fall 2026-09-04: bullischer Stack, aber −4,3 % in 30 Tagen.
        Das ist eine Konsolidierung, kein Grinder."""
        assert run(config, move_30d_pct=-4.3) == []

    def test_fehlende_weekly_hhll_faellt_raus(self, config):
        assert run(config, weekly_higher_highs_lows=False) == []

    def test_fehlende_daten_werfen_nicht(self, config):
        for kw in ({"atr14": None}, {"ema20": None}, {"move_30d_pct": None},
                   {"price": None}, {"atr14": 0.0}):
            assert run(config, **kw) == []


class TestSchwelleInAtrEinheiten:
    """Die Trend-Schwelle ist in ATR-Einheiten, nicht in Prozent.

    Kalibrierungsbefund 2026-09-04: 3 % sind bei ^GDAXI (ATR 0,96 %) gut drei
    ATR und bei RACE.MI (2,25 %) nur 1,3 — eine Prozentschwelle vergleicht
    Unvergleichbares und liess von 14 Kandidaten genau einen übrig.
    """

    def test_gleicher_prozent_move_unterschiedliche_atr(self, config):
        # 2,5 % Move bei ATR% 1,0 = 2,5 ATR → durch
        assert len(run(config, atr14=1.0, move_30d_pct=2.5)) == 1
        # derselbe Move bei ATR% 2,5 = 1,0 ATR → gerade noch durch
        assert len(run(config, atr14=2.5, price=100.0, ema20=99.5,
                       move_30d_pct=2.5)) == 1
        # und bei ATR% 2,5 mit nur 2,0 % Move = 0,8 ATR → raus
        assert run(config, atr14=2.5, move_30d_pct=2.0) == []


class TestRanking:
    def test_tempo_formel(self, config):
        """tempo = |30d| / (2,0 x 1,5 x ATR%). Bei ATR% 2 und 30d 6 % → 1,0."""
        g = run(config, atr14=2.0, price=100.0, move_30d_pct=6.0)[0]
        assert g["atr_pct"] == pytest.approx(2.0)
        assert g["ziel_pct"] == pytest.approx(6.0)
        assert g["tempo"] == pytest.approx(1.0)

    def test_sortiert_nach_tempo_nicht_nach_move(self, config):
        """Der langsamere Prozent-Move gewinnt, wenn er billiger zu halten ist."""
        snaps = {
            "TEUER": Snap(symbol="TEUER", atr14=2.4, move_30d_pct=8.0),   # 3,33 ATR
            "BILLIG": Snap(symbol="BILLIG", atr14=1.0, ema20=99.7,
                           move_30d_pct=5.0),                            # 5,0 ATR
        }
        out = build_grinders_payload(snaps, config)
        assert [g["symbol"] for g in out] == ["BILLIG", "TEUER"]
        assert out[0]["move30d"] < out[1]["move30d"]   # weniger Prozent, mehr Tempo

    def test_top_n_wird_eingehalten(self, config):
        snaps = {f"S{i}": Snap(symbol=f"S{i}", move_30d_pct=5.0 + i) for i in range(9)}
        assert len(build_grinders_payload(snaps, config)) == config["grinders"]["top_n"]


class TestShortSeite:
    def test_bearischer_grinder(self, config):
        out = run(config, ema20=99.5, ema50=105.0, ema200=115.0,
                  price=100.0, move_30d_pct=-6.0, weekly_higher_highs_lows=False)
        assert len(out) == 1 and out[0]["dir"] == "short"

    def test_bearischer_stack_mit_positivem_move_faellt_raus(self, config):
        assert run(config, ema20=99.5, ema50=105.0, ema200=115.0,
                   move_30d_pct=+6.0, weekly_higher_highs_lows=False) == []


class TestKonfiguration:
    def test_abschaltbar(self, config):
        cfg = dict(config)
        cfg["grinders"] = dict(config["grinders"], enabled=False)
        assert build_grinders_payload({"TEST": Snap()}, cfg) == []

    def test_ethik_ausschluss_greift(self, config):
        sym = config["pitches"]["ethics_exclude"][0]
        assert build_grinders_payload({sym: Snap(symbol=sym)}, config) == []
