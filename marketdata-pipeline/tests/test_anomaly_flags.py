"""
Tests für Anomaly-Layer V1 (Note #50, 2026-05-15).

Vier Anomaly-Detektoren:
- atr_zscore_60d:     Volatilitäts-Regime-Shift
- gap_pct:            Eröffnungs-Gap
- volume_zscore_60d:  Volumen-Spike (log-transformiert)
- nr7:                Range-Compression (Pre-Breakout-Signal)

Ausführen vom marketdata-pipeline/ Verzeichnis:
    PYTHONPATH=./src python tests/test_anomaly_flags.py
oder mit pytest:
    PYTHONPATH=./src pytest tests/test_anomaly_flags.py -v
"""

import os
import sys

import numpy as np
import pandas as pd
from unittest.mock import patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
sys.path.insert(0, _SRC)

from market_data import (
    TickerSnapshot,
    _compute_anomaly_fields,
    _compute_snapshot,
    ANOMALY_ATR_Z_THRESHOLD,
    ANOMALY_GAP_PCT_THRESHOLD,
    ANOMALY_GAP_PCT_EXTREME,
    ANOMALY_VOLUME_Z_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Test-Helpers
# ---------------------------------------------------------------------------

def make_df(
    closes: list[float],
    highs: list[float] = None,
    lows: list[float] = None,
    opens: list[float] = None,
    volumes: list[int] = None,
    start_date: str = "2024-01-01",
) -> pd.DataFrame:
    """Erzeugt einen synthetischen Daily-DataFrame.

    Defaults: highs = closes*1.01, lows = closes*0.99, opens = closes, volume = 1M.
    """
    n = len(closes)
    if highs is None:
        highs = [c * 1.01 for c in closes]
    if lows is None:
        lows = [c * 0.99 for c in closes]
    if opens is None:
        opens = list(closes)  # vereinfacht: open = close
    if volumes is None:
        volumes = [1_000_000] * n

    idx = pd.bdate_range(start=start_date, periods=n)
    return pd.DataFrame({
        "Open": opens,
        "High": highs,
        "Low": lows,
        "Close": closes,
        "Volume": volumes,
    }, index=idx)


def empty_snap() -> TickerSnapshot:
    """Frischer Snapshot ohne Pre-Population."""
    from datetime import datetime
    return TickerSnapshot(
        symbol="TEST",
        timestamp=datetime(2026, 5, 15),
        price=100.0,
        prev_close=None,
        change_pct=None,
        volume_today=None,
    )


def force_eod():
    """Context-Manager: erzwingt is_eod=True im Anomaly-Guard.

    Ohne diesen Override berechnet _compute_anomaly_fields volume_zscore/nr7
    nur nach 20:00 UTC (ANOMALY_VOLUME_EOD_HOUR_UTC) — die Suite wäre sonst
    laufzeitabhängig und vor 20:00 UTC rot. Patcht das ausgelagerte
    market_data._is_eod_now. Nutzung: `with force_eod(): ...`.
    """
    return patch("market_data._is_eod_now", return_value=True)


# ---------------------------------------------------------------------------
# 1) gap_pct
# ---------------------------------------------------------------------------

def test_gap_pct_no_data():
    """Ohne prev_close oder today_open → gap_pct bleibt None."""
    snap = empty_snap()
    df = make_df([100.0] * 10)
    _compute_anomaly_fields(snap, df)
    assert snap.gap_pct is None, f"Expected None, got {snap.gap_pct}"


def test_gap_pct_positive():
    """Gap nach oben: open=105, prev_close=100 → +5.0%."""
    snap = empty_snap()
    snap.today_open = 105.0
    snap.prev_close = 100.0
    df = make_df([100.0] * 10)
    _compute_anomaly_fields(snap, df)
    assert snap.gap_pct is not None
    assert abs(snap.gap_pct - 5.0) < 0.001, f"Expected ~5.0, got {snap.gap_pct}"
    assert snap.is_gap_anomaly  # ≥ 2.0%
    assert snap.is_gap_extreme  # ≥ 5.0%


def test_gap_pct_negative_moderate():
    """Gap nach unten -3%: anomaly aber nicht extrem."""
    snap = empty_snap()
    snap.today_open = 97.0
    snap.prev_close = 100.0
    df = make_df([100.0] * 10)
    _compute_anomaly_fields(snap, df)
    assert abs(snap.gap_pct + 3.0) < 0.001, f"Expected ~-3.0, got {snap.gap_pct}"
    assert snap.is_gap_anomaly
    assert not snap.is_gap_extreme


def test_gap_pct_below_threshold():
    """Gap +1.5%: kein Flag."""
    snap = empty_snap()
    snap.today_open = 101.5
    snap.prev_close = 100.0
    df = make_df([100.0] * 10)
    _compute_anomaly_fields(snap, df)
    assert not snap.is_gap_anomaly


# ---------------------------------------------------------------------------
# 2) atr_zscore_60d
# ---------------------------------------------------------------------------

def test_atr_zscore_insufficient_history():
    """History < 60 + 14 HT → bleibt None."""
    snap = empty_snap()
    df = make_df([100.0] * 50)
    _compute_anomaly_fields(snap, df)
    assert snap.atr_zscore_60d is None


def test_atr_zscore_normal_volatility():
    """Konstante (verrauschte) Volatilität → Z-Score nahe 0, kein Flag."""
    snap = empty_snap()
    # 100 HT mit verrauschter aber stationärer Range
    np.random.seed(11)
    closes = [100.0 + 0.5 * np.sin(i * 0.3) for i in range(100)]
    # Range ~2 ± 0.4: realistische Variation
    ranges = [2.0 + 0.4 * np.random.randn() for _ in range(100)]
    highs = [c + r / 2 for c, r in zip(closes, ranges)]
    lows = [c - r / 2 for c, r in zip(closes, ranges)]
    df = make_df(closes, highs=highs, lows=lows)
    _compute_anomaly_fields(snap, df)
    assert snap.atr_zscore_60d is not None, (
        "Bei verrauschter Range muss Std > 0 sein, Z muss berechnet werden"
    )
    assert abs(snap.atr_zscore_60d) < 2.0, (
        f"Stationäre Vola sollte |Z|<2 ergeben, got {snap.atr_zscore_60d}"
    )
    assert not snap.is_atr_anomaly


def test_atr_zscore_volatility_explosion():
    """Plötzliche Vola-Explosion am Ende → Z-Score ≥ 2.0, Flag aktiv.

    EWMA-ATR glättet, deshalb braucht der Spike Druck über mehrere Tage,
    nicht nur eine extreme Einzelkerze. Wir setzen die letzten 3 Tage auf
    deutlich höhere Range.
    """
    snap = empty_snap()
    np.random.seed(42)
    closes = [100.0 + 0.3 * np.random.randn() for _ in range(97)]
    # Stationäre Range mit Rauschen
    ranges = [2.0 + 0.3 * np.random.randn() for _ in range(97)]
    # Letzte 3 Tage: 5× Range
    closes += [100.0, 100.0, 100.0]
    ranges += [10.0, 10.0, 10.0]
    highs = [c + r / 2 for c, r in zip(closes, ranges)]
    lows = [c - r / 2 for c, r in zip(closes, ranges)]
    df = make_df(closes, highs=highs, lows=lows)
    _compute_anomaly_fields(snap, df)
    assert snap.atr_zscore_60d is not None
    assert snap.atr_zscore_60d > ANOMALY_ATR_Z_THRESHOLD, (
        f"Vola-Spike sollte Z > {ANOMALY_ATR_Z_THRESHOLD} ergeben, got {snap.atr_zscore_60d}"
    )
    assert snap.is_atr_anomaly


# ---------------------------------------------------------------------------
# 3) volume_zscore_60d
# ---------------------------------------------------------------------------

def test_volume_zscore_insufficient_history():
    """History < 61 HT → bleibt None."""
    snap = empty_snap()
    snap.volume_today = 1_500_000
    df = make_df([100.0] * 30, volumes=[1_000_000] * 30)
    _compute_anomaly_fields(snap, df)
    assert snap.volume_zscore_60d is None


def test_volume_zscore_normal():
    """Konstantes Volumen → Z-Score ≈ 0."""
    snap = empty_snap()
    snap.volume_today = 1_000_000
    closes = [100.0] * 100
    # Realistisches Rauschen ± 10% um 1M
    np.random.seed(42)
    vols = [int(1_000_000 * (1 + 0.1 * np.random.randn())) for _ in range(100)]
    df = make_df(closes, volumes=vols)
    with force_eod():
        _compute_anomaly_fields(snap, df)
    assert snap.volume_zscore_60d is not None
    assert abs(snap.volume_zscore_60d) < 2.0, (
        f"Normales Volumen, Z sollte |Z|<2 sein, got {snap.volume_zscore_60d}"
    )


def test_volume_zscore_spike():
    """Plötzlicher Volumen-Spike an Tag 100 → Z-Score deutlich positiv."""
    snap = empty_snap()
    snap.volume_today = 5_000_000  # 5× Spike
    closes = [100.0] * 100
    # 99 Tage Normalvolumen, letzter Tag Spike
    np.random.seed(42)
    vols = [int(1_000_000 * (1 + 0.1 * np.random.randn())) for _ in range(99)]
    vols.append(5_000_000)
    df = make_df(closes, volumes=vols)
    with force_eod():
        _compute_anomaly_fields(snap, df)
    assert snap.volume_zscore_60d is not None
    assert snap.volume_zscore_60d > ANOMALY_VOLUME_Z_THRESHOLD, (
        f"5×-Spike sollte Z > {ANOMALY_VOLUME_Z_THRESHOLD} ergeben, "
        f"got {snap.volume_zscore_60d}"
    )
    assert snap.is_volume_anomaly


def test_volume_zscore_zero_volume_skipped():
    """0-Volumen-Tage sollen log-transform nicht crashen lassen."""
    snap = empty_snap()
    snap.volume_today = 1_000_000
    closes = [100.0] * 100
    vols = [1_000_000] * 100
    vols[42] = 0  # ein 0-Tag mittendrin
    df = make_df(closes, volumes=vols)
    # Sollte nicht crashen
    _compute_anomaly_fields(snap, df)
    # Z-Score kann None sein (wenn zu viele 0-Tage rausfallen), Hauptsache: kein Crash


# ---------------------------------------------------------------------------
# 4) NR7
# ---------------------------------------------------------------------------

def test_nr7_insufficient_history():
    """History < 8 HT → bleibt None."""
    snap = empty_snap()
    df = make_df([100.0] * 5)
    _compute_anomaly_fields(snap, df)
    assert snap.nr7 is None


def test_nr7_compression_detected():
    """Heutige Range ist klar die kleinste der letzten 7 HT → True."""
    snap = empty_snap()
    # 7 Tage Range groß, letzter Tag Range minimal
    highs = [105.0] * 7 + [100.5]
    lows = [95.0] * 7 + [99.5]
    closes = [100.0] * 8
    df = make_df(closes, highs=highs, lows=lows)
    with force_eod():
        _compute_anomaly_fields(snap, df)
    assert snap.nr7 is True
    assert snap.is_range_compressed


def test_nr7_not_compressed():
    """Heutige Range nicht kleinste → False.

    Vorige 7 Tage haben kleine Range, heute hat größere Range.
    """
    snap = empty_snap()
    # Vorige 7 Tage: enge Range. Heute: weite Range.
    highs = [100.5] * 7 + [105.0]
    lows = [99.5] * 7 + [95.0]
    closes = [100.0] * 8
    df = make_df(closes, highs=highs, lows=lows)
    with force_eod():
        _compute_anomaly_fields(snap, df)
    assert snap.nr7 is False, f"Expected False, got {snap.nr7}"
    assert not snap.is_range_compressed


# ---------------------------------------------------------------------------
# Integration: _compute_snapshot inkl. Anomaly-Felder
# ---------------------------------------------------------------------------

def test_compute_snapshot_integration():
    """Voller Snapshot-Compute mit Anomaly-Daten."""
    # 80 HT History mit normalem Verlauf + Spike am letzten Tag
    np.random.seed(7)
    closes = [100.0 + 0.5 * np.random.randn() for _ in range(79)]
    closes.append(108.0)  # +8% am letzten Tag
    highs = [c * 1.01 for c in closes]
    lows = [c * 0.99 for c in closes]
    opens = closes[:-1] + [107.0]  # Tag 80: Open 107, Close 108 → Gap zum Vortag
    vols = [1_000_000] * 79 + [4_000_000]  # Volumen-Spike

    df = make_df(closes, highs=highs, lows=lows, opens=opens, volumes=vols)
    with force_eod():
        snap = _compute_snapshot("INTEG", df)

    assert snap is not None
    # gap_pct: open=107 vs. prev_close=closes[-2]
    assert snap.gap_pct is not None
    # volume_zscore: spike sollte hoch sein
    assert snap.volume_zscore_60d is not None
    assert snap.volume_zscore_60d > 2.0
    # has_any_anomaly muss True sein
    assert snap.has_any_anomaly
    # Flag-Labels nicht leer
    labels = snap.anomaly_flag_labels()
    assert len(labels) > 0


def test_flag_labels_ordering_and_format():
    """Flag-Labels: korrekte Reihenfolge und Format."""
    snap = empty_snap()
    snap.gap_pct = 6.0   # extreme
    snap.volume_zscore_60d = 3.5
    snap.atr_zscore_60d = 2.5
    snap.nr7 = True

    labels = snap.anomaly_flag_labels()
    # Reihenfolge: Gap, Vol, ATR, NR7
    assert labels[0].startswith("GAP-EXTREME")
    assert labels[1].startswith("VOL-Z")
    assert labels[2].startswith("ATR-Z")
    assert labels[3] == "NR7"


def test_no_anomalies_clean_state():
    """Snapshot ohne Anomalien: alle Properties False, leere Label-Liste."""
    snap = empty_snap()
    snap.gap_pct = 0.5
    snap.volume_zscore_60d = 0.3
    snap.atr_zscore_60d = -0.8
    snap.nr7 = False

    assert not snap.has_any_anomaly
    assert snap.anomaly_flag_labels() == []


# ---------------------------------------------------------------------------
# Renderer-Integration
# ---------------------------------------------------------------------------

def test_renderer_anomaly_section_present():
    """Renderer baut ANOMALY-FLAGS-Sektion ein, wenn Snapshots Anomalien haben."""
    from output_renderer import _render_setup_class_flags

    snap_a = empty_snap()
    snap_a.symbol = "AAA"
    snap_a.gap_pct = 6.5
    snap_a.volume_zscore_60d = 3.0

    snap_b = empty_snap()
    snap_b.symbol = "BBB"
    snap_b.nr7 = True

    snap_clean = empty_snap()
    snap_clean.symbol = "CCC"
    snap_clean.gap_pct = 0.1  # nichts auffällig

    snapshots = {"AAA": snap_a, "BBB": snap_b, "CCC": snap_clean}
    lines = _render_setup_class_flags(snapshots)
    text = "\n".join(lines)

    assert "ANOMALY-FLAGS" in text, "Sektions-Header muss enthalten sein"
    assert "AAA" in text
    assert "BBB" in text
    assert "CCC" not in text, "Sauberer Ticker darf nicht in der Sektion erscheinen"
    # AAA (Mehrfach-Flag) soll vor BBB (Einzel-NR7) stehen
    aaa_pos = text.find("AAA")
    bbb_pos = text.find("BBB")
    assert aaa_pos < bbb_pos, "Mehrfach-Anomalie muss vor Einzel-Anomalie sortiert sein"


def test_renderer_anomaly_section_empty_when_clean():
    """Wenn alle Snapshots sauber sind: keine ANOMALY-FLAGS-Sektion."""
    from output_renderer import _render_setup_class_flags

    snap = empty_snap()
    snap.gap_pct = 0.3
    snap.nr7 = False

    lines = _render_setup_class_flags({"X": snap})
    text = "\n".join(lines)
    assert "ANOMALY-FLAGS" not in text


# ---------------------------------------------------------------------------
# Test-Runner für direkten Aufruf
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_funcs = [
        # gap_pct
        test_gap_pct_no_data,
        test_gap_pct_positive,
        test_gap_pct_negative_moderate,
        test_gap_pct_below_threshold,
        # atr_zscore
        test_atr_zscore_insufficient_history,
        test_atr_zscore_normal_volatility,
        test_atr_zscore_volatility_explosion,
        # volume_zscore
        test_volume_zscore_insufficient_history,
        test_volume_zscore_normal,
        test_volume_zscore_spike,
        test_volume_zscore_zero_volume_skipped,
        # NR7
        test_nr7_insufficient_history,
        test_nr7_compression_detected,
        test_nr7_not_compressed,
        # Integration
        test_compute_snapshot_integration,
        test_flag_labels_ordering_and_format,
        test_no_anomalies_clean_state,
        # Renderer
        test_renderer_anomaly_section_present,
        test_renderer_anomaly_section_empty_when_clean,
    ]
    failed = 0
    for f in test_funcs:
        try:
            f()
            print(f"  ✓ {f.__name__}")
        except AssertionError as e:
            print(f"  ✗ {f.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {f.__name__}: UNEXPECTED {type(e).__name__}: {e}")
            failed += 1
    total = len(test_funcs)
    if failed == 0:
        print(f"\nAlle {total} Tests grün.")
    else:
        print(f"\n{failed}/{total} Tests fehlgeschlagen.")
        sys.exit(1)
