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

from filter_engine import (
    build_grinders_payload,
    build_grinders_report,
    dedupe_grinders,
)


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
        """Isoliert das move_atr-Gate — Tempo-Gate dafuer ausgeschaltet.

        Seit dem 2026-09-08 gibt es ZWEI Gates (move_atr und tempo). Dieser Test
        gehoert dem ersten; ohne die Abschaltung wuerde er am zweiten scheitern
        und damit etwas anderes messen, als sein Name sagt.
        """
        cfg = dict(config)
        cfg["grinders"] = dict(config["grinders"], min_tempo=0.0)
        # 2,5 % Move bei ATR% 1,0 = 2,5 ATR → durch
        assert len(run(cfg, atr14=1.0, move_30d_pct=2.5)) == 1
        # derselbe Move bei ATR% 2,5 = 1,0 ATR → gerade noch durch
        assert len(run(cfg, atr14=2.5, price=100.0, ema20=99.5,
                       move_30d_pct=2.5)) == 1
        # und bei ATR% 2,5 mit nur 2,0 % Move = 0,8 ATR → raus
        assert run(cfg, atr14=2.5, move_30d_pct=2.0) == []


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


class TestTempoGate:
    """Tempo ist seit dem 2026-09-08 GATE, nicht nur Rangfolge.

    Grinder-Continuation v0.1 verspricht "R:R >= 2 in rund 30 HT". Genau das
    misst tempo = |30d-Move| / ziel_pct. Vorher lief nur min_move_atr, und
    damit standen Werte mit Tempo 0,54 im Block (JNJ, Lauf 2026-09-08 18:05) —
    das entspraeche einem Horizont von rund 55 HT.
    """

    def test_unter_der_schwelle_faellt_raus(self, config):
        # ATR% 1,0 → ziel_pct 3,0 → Move 2,5 % = Tempo 0,83 < 0,9
        assert run(config, atr14=1.0, move_30d_pct=2.5) == []

    def test_auf_der_schwelle_kommt_durch(self, config):
        # ATR% 1,0 → ziel_pct 3,0 → Move 2,7 % = Tempo 0,90
        out = run(config, atr14=1.0, move_30d_pct=2.7)
        assert len(out) == 1 and out[0]["tempo"] == pytest.approx(0.90)

    def test_gilt_auch_short(self, config):
        kw = dict(ema20=99.5, ema50=105.0, ema200=115.0, price=100.0,
                  atr14=1.0, weekly_higher_highs_lows=False)
        assert run(config, move_30d_pct=-2.5, **kw) == []
        assert len(run(config, move_30d_pct=-2.7, **kw)) == 1

    def test_schwelle_abschaltbar(self, config):
        cfg = dict(config)
        cfg["grinders"] = dict(config["grinders"], min_tempo=0.0)
        assert len(run(cfg, atr14=1.0, move_30d_pct=2.5)) == 1

    def test_default_ist_konfiguriert(self, config):
        assert config["grinders"]["min_tempo"] == pytest.approx(0.9)


class TestReport:
    """Die ungedeckelte Trefferzahl muss sichtbar sein.

    Befund 2026-09-08: Beide Produktionslaeufe lieferten exakt fuenf Grinder —
    weil top_n=5 der Deckel ist, nicht weil der Markt fuenf hergab. Wer gegen
    eine abgeschnittene Liste kalibriert, haelt den Deckel fuer den Marktzustand.
    """

    def _many(self, n):
        snaps = {}
        for i in range(n):
            # Tempo absteigend, alle klar ueber der Schwelle
            snaps[f"S{i}"] = Snap(symbol=f"S{i}", atr14=2.0, price=100.0,
                                  ema20=99.5, move_30d_pct=12.0 - i * 0.3)
        return snaps

    def test_total_zaehlt_ungedeckelt(self, config):
        rep = build_grinders_report(self._many(12), config)
        assert rep["total"] == 12
        assert len(rep["items"]) == config["grinders"]["top_n"]
        assert rep["top_n"] == config["grinders"]["top_n"]

    def test_items_sind_die_besten(self, config):
        rep = build_grinders_report(self._many(12), config)
        tempi = [g["tempo"] for g in rep["items"]]
        assert tempi == sorted(tempi, reverse=True)
        assert rep["items"][0]["symbol"] == "S0"

    def test_dropped_by_tempo_wird_gezaehlt(self, config):
        snaps = {
            "GUT": Snap(symbol="GUT", atr14=2.0, price=100.0, ema20=99.5,
                        move_30d_pct=6.0),                      # Tempo 1,00
            "LAHM": Snap(symbol="LAHM", atr14=2.0, price=100.0, ema20=99.5,
                         move_30d_pct=4.0),                     # Tempo 0,67
        }
        rep = build_grinders_report(snaps, config)
        assert rep["total"] == 1 and rep["dropped_by_tempo"] == 1

    def test_payload_bleibt_rueckwaertskompatibel(self, config):
        snaps = self._many(3)
        assert build_grinders_payload(snaps, config) == \
            build_grinders_report(snaps, config)["items"]

    def test_report_bei_abgeschaltetem_screen(self, config):
        cfg = dict(config)
        cfg["grinders"] = dict(config["grinders"], enabled=False)
        rep = build_grinders_report({"TEST": Snap()}, cfg)
        assert rep["items"] == [] and rep["total"] == 0


class TestDedupe:
    """EU- und US-Lauf ueberlappen — Duplikate fressen Plaetze im Block."""

    def test_haelt_das_erste_vorkommen(self):
        lst = [
            {"symbol": "KNIN.SW", "tempo": 1.05, "tier": "US"},
            {"symbol": "AD.AS", "tempo": 1.00, "tier": "US"},
            {"symbol": "KNIN.SW", "tempo": 0.94, "tier": "EU"},
        ]
        out = dedupe_grinders(lst)
        assert [g["symbol"] for g in out] == ["KNIN.SW", "AD.AS"]
        assert out[0]["tempo"] == 1.05 and out[0]["tier"] == "US"

    def test_ohne_duplikate_unveraendert(self):
        lst = [{"symbol": "A", "tempo": 1.2}, {"symbol": "B", "tempo": 1.0}]
        assert dedupe_grinders(lst) == lst

    def test_leer_und_none(self):
        assert dedupe_grinders([]) == [] and dedupe_grinders(None) == []

    def test_realfall_2026_09_08(self):
        """Beide Produktionslaeufe des 2026-09-08, zusammengelegt."""
        eu = ["KNIN.SW", "NOEJ.DE", "MUX.DE", "ALV.DE", "JNJ"]
        us = ["KNIN.SW", "AD.AS", "EOG", "ABBV", "WMT"]
        lst = [{"symbol": s, "tempo": 1.0 - i * 0.01}
               for i, s in enumerate(us + eu)]
        out = dedupe_grinders(lst)
        assert len(lst) == 10 and len(out) == 9
