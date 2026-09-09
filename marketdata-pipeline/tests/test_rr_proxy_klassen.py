"""Tests fuer die klassenabhaengige Reward-Definition im R:R-Proxy (Fix 2026-09-09).

Befund, der den Fix ausgeloest hat: `build_pitches_payload` wandte den
Pullback-Proxy (Reward = Abstand zum 20d-Extrem) auf JEDEN Bucket an. Fuer
breakout_long und breakdown_short ist dieses Extrem aber der EINSTIEG, nicht das
Ziel — deren Bucket-Gate verlangt <= 1 % Abstand dazu. Zusammen mit
`rr >= min_rr` ergibt das die Schranke `ATR <= 0,476 %` vom Kurs; am 2026-09-09
erfuellten das 2 von 102 Universumswerten, keine Einzelaktie.

Messbarer Beleg: die Digests vom 07.-09.09. tragen zusammen 30 Pitches —
long_trend_pullback 17, reversal_long 6, reversal_short 6, short_trend_pullback 1
und breakout_long/breakdown_short exakt NULL, obwohl der GAMECHANGER-Lauf
22:47 CEST zwei Breakdown-Kandidaten erzeugt hatte (IMB.L, BATS.L).
"""
from dataclasses import dataclass
from typing import Optional

import pytest

from filter_engine import _rr_proxy, _rr_exempt


CFG = {"rr_proxy": {"enabled": True, "atr_mult": 1.5, "min_rr": 1.4,
                    "measured_move_buckets": ["breakout_long", "breakdown_short"],
                    "exempt_buckets": ["reversal_long", "reversal_short"]}}


@dataclass
class Snap:
    price: float
    atr14: float
    high_20d: Optional[float] = None
    low_20d: Optional[float] = None
    symbol: str = "TEST"


# --- Pullback bleibt unveraendert ----------------------------------------

def test_pullback_long_unveraendert():
    snap = Snap(price=100.0, atr14=2.0, high_20d=110.0, low_20d=90.0)
    rr, eng = _rr_proxy(snap, "long", CFG, bucket="long_trend_pullback")
    assert rr == pytest.approx(10.0 / 3.0)      # (110-100) / (1.5*2)
    assert eng is False


def test_pullback_short_unveraendert():
    snap = Snap(price=100.0, atr14=2.0, high_20d=110.0, low_20d=90.0)
    rr, eng = _rr_proxy(snap, "short", CFG, bucket="short_trend_pullback")
    assert rr == pytest.approx(10.0 / 3.0)      # (100-90) / (1.5*2)


def test_ohne_bucket_faellt_auf_pullback_zurueck():
    """Backward-Compat: Altaufrufer ohne bucket bekommen das alte Verhalten."""
    snap = Snap(price=100.0, atr14=2.0, high_20d=110.0, low_20d=90.0)
    assert _rr_proxy(snap, "long", CFG) == _rr_proxy(
        snap, "long", CFG, bucket="long_trend_pullback")


# --- Der eigentliche Befund: alte Definition toetet Ausbrueche ------------

def test_alte_definition_haette_breakdown_immer_verworfen():
    """IMB.L aus dem Lauf 2026-09-09 22:47, mit der Pullback-Definition."""
    snap = Snap(price=24.43, atr14=24.43 * 0.015, high_20d=27.0, low_20d=24.39)
    rr, eng = _rr_proxy(snap, "short", CFG, bucket="short_trend_pullback")
    assert rr < 0.1 and eng is True     # reward 0,04 gegen risk 0,55


@pytest.mark.parametrize("atr_pct", [0.5, 1.0, 1.5, 2.0, 3.0])
def test_measured_move_rettet_denselben_fall(atr_pct):
    """Gleicher Wert, richtige Zielstrecke: Range-Hoehe statt 0,04 EUR."""
    snap = Snap(price=24.43, atr14=24.43 * atr_pct / 100,
                high_20d=27.0, low_20d=24.39)
    rr, eng = _rr_proxy(snap, "short", CFG, bucket="breakdown_short")
    # Ziel = 24.39 - (27.0-24.39) = 21.78 -> reward = 24.43-21.78 = 2.65
    assert rr == pytest.approx(2.65 / (1.5 * snap.atr14), rel=1e-6)
    if atr_pct <= 1.5:
        assert eng is False, f"ATR {atr_pct} % sollte durchkommen"


def test_measured_move_long_spiegelbildlich():
    snap = Snap(price=100.0, atr14=1.5, high_20d=100.5, low_20d=90.0)
    rr, eng = _rr_proxy(snap, "long", CFG, bucket="breakout_long")
    # Ziel = 100.5 + (100.5-90.0) = 111.0 -> reward 11.0, risk 2.25
    assert rr == pytest.approx(11.0 / 2.25)
    assert eng is False


def test_measured_move_bleibt_streng_bei_sehr_hohem_atr():
    """Der Fix schaltet den Filter nicht ab — er misst nur die richtige Strecke."""
    snap = Snap(price=100.0, atr14=10.0, high_20d=100.5, low_20d=98.0)
    rr, eng = _rr_proxy(snap, "short", CFG, bucket="breakdown_short")
    assert eng is True      # Range 2,5 gegen Risk 15 -> rr 0,17


def test_measured_move_ohne_range_nicht_berechenbar():
    snap = Snap(price=100.0, atr14=2.0, high_20d=None, low_20d=95.0)
    assert _rr_proxy(snap, "short", CFG, bucket="breakdown_short") == (None, False)


def test_measured_move_bei_entarteter_range():
    snap = Snap(price=100.0, atr14=2.0, high_20d=95.0, low_20d=95.0)
    assert _rr_proxy(snap, "short", CFG, bucket="breakdown_short") == (None, False)


# --- Ausgenommene Buckets ------------------------------------------------

@pytest.mark.parametrize("bucket", ["reversal_long", "reversal_short"])
def test_reversal_ist_vom_FILTER_ausgenommen_nicht_von_der_ZAHL(bucket):
    """Die Ausnahme darf das Payload-Schema nicht loechrig machen.

    `rrprox` ist Pflichtfeld und Rangkriterium — ein None dort schlug im ersten
    Bauversuch als `round(None)` durch und riss zwei bestehende Pitch-Tests.
    Ausgenommen ist deshalb nur die Disqualifikation, nicht die Berechnung.
    """
    snap = Snap(price=100.0, atr14=2.0, high_20d=110.0, low_20d=90.0)
    rr, eng = _rr_proxy(snap, "long", CFG, bucket=bucket)
    assert rr is not None                      # Zahl bleibt
    assert _rr_exempt(bucket, CFG) is True     # Filter greift nicht


def test_enger_reversal_ueberlebt_den_pitch_filter():
    """Ein Reversal mit eng=True darf NICHT mehr aussortiert werden."""
    snap = Snap(price=100.0, atr14=20.0, high_20d=101.0, low_20d=99.0)
    rr, eng = _rr_proxy(snap, "long", CFG, bucket="reversal_long")
    assert eng is True                                  # waere frueher raus
    assert _rr_exempt("reversal_long", CFG) is True     # bleibt jetzt drin


def test_enger_pullback_fliegt_weiterhin_raus():
    """Gegenprobe: der Fix lockert NUR die ausgenommenen Klassen."""
    snap = Snap(price=100.0, atr14=20.0, high_20d=101.0, low_20d=99.0)
    rr, eng = _rr_proxy(snap, "long", CFG, bucket="long_trend_pullback")
    assert eng is True
    assert _rr_exempt("long_trend_pullback", CFG) is False


@pytest.mark.parametrize("bucket", ["long_trend_pullback", "breakdown_short", None])
def test_nicht_ausgenommene_buckets(bucket):
    assert _rr_exempt(bucket, CFG) is False


# --- Schalter ------------------------------------------------------------

def test_deaktivierter_proxy():
    snap = Snap(price=100.0, atr14=2.0, high_20d=110.0, low_20d=90.0)
    assert _rr_proxy(snap, "long", {"rr_proxy": {"enabled": False}},
                     bucket="breakout_long") == (None, False)


def test_listen_sind_konfigurierbar():
    cfg = {"rr_proxy": {"enabled": True, "atr_mult": 1.5, "min_rr": 1.4,
                        "measured_move_buckets": [], "exempt_buckets": []}}
    snap = Snap(price=24.43, atr14=0.37, high_20d=27.0, low_20d=24.39)
    rr, eng = _rr_proxy(snap, "short", cfg, bucket="breakdown_short")
    assert eng is True   # ohne Measured-Move-Liste wieder die alte Definition


def test_defaults_greifen_ohne_config_listen():
    """Ein Repo-Stand ohne die neuen YAML-Schluessel verhaelt sich wie mit."""
    cfg = {"rr_proxy": {"enabled": True, "atr_mult": 1.5, "min_rr": 1.4}}
    snap = Snap(price=24.43, atr14=0.37, high_20d=27.0, low_20d=24.39)
    rr, eng = _rr_proxy(snap, "short", cfg, bucket="breakdown_short")
    assert eng is False
    assert _rr_exempt("reversal_short", cfg) is True
