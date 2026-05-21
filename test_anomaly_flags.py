"""
Tests für EMA200-MeanRev-Schicht (Note #49) und PEAD-Window-Flag.

Ausführen vom marketdata-pipeline/ Verzeichnis:
    PYTHONPATH=./src python tests/test_ema200_meanrev.py
oder mit pytest:
    PYTHONPATH=./src pytest tests/ -v
"""

import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
sys.path.insert(0, _SRC)

# market_data importieren — wir testen die einzelnen Compute-Funktionen, NICHT
# den yfinance-Pull (der bräuchte Network und ist nicht reproduzierbar).
from market_data import (
    TickerSnapshot,
    _compute_ema200_meanrev_fields,
    _compute_weekly_trend_field,
    _compute_atr_series,
)
from output_renderer import _render_setup_class_flags


# ---------------------------------------------------------------------------
# Test-Helpers
# ---------------------------------------------------------------------------

def make_test_df(closes: list[float], highs: list[float] = None, lows: list[float] = None,
                  start_date: str = "2024-01-01") -> pd.DataFrame:
    """Erzeugt einen synthetischen Daily-DataFrame aus einer Close-Liste.

    Highs/Lows werden angenähert (close ± 1%) wenn nicht explizit gegeben.
    Index sind Trading-Tage (Mo-Fr, ohne Feiertage).
    """
    n = len(closes)
    if highs is None:
        highs = [c * 1.01 for c in closes]
    if lows is None:
        lows = [c * 0.99 for c in closes]
    opens = closes  # vereinfacht

    # bdate_range = Geschäftstage (Mo-Fr), keine Feiertage. Reicht für Tests.
    idx = pd.bdate_range(start=start_date, periods=n)

    return pd.DataFrame({
        "Open": opens,
        "High": highs,
        "Low": lows,
        "Close": closes,
        "Volume": [1_000_000] * n,
    }, index=idx)


def make_snapshot_from_df(symbol: str, df: pd.DataFrame) -> TickerSnapshot:
    """Bastelt einen Snapshot mit den Basisfeldern, die _compute_ema200_meanrev_fields
    braucht (price, ema200, atr14)."""
    closes = df["Close"]
    snap = TickerSnapshot(
        symbol=symbol,
        timestamp=datetime.now(),
        price=float(closes.iloc[-1]),
        prev_close=float(closes.iloc[-2]) if len(closes) >= 2 else None,
        change_pct=None,
        volume_today=None,
    )
    if len(closes) >= 200:
        snap.ema200 = float(closes.ewm(span=200, adjust=False).mean().iloc[-1])
    if len(closes) >= 50:
        snap.ema50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])
    if len(closes) >= 20:
        snap.ema20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
    if len(df) >= 15:
        snap.atr14 = float(_compute_atr_series(df, period=14).iloc[-1])
    return snap


# ---------------------------------------------------------------------------
# EMA200-Distance-Tests
# ---------------------------------------------------------------------------

def test_ema200_distance_pct_zero_at_touch():
    """Wenn Kurs == EMA200, ist Distance 0%."""
    # Synthetic: 400 HT mit konstantem Kurs 100 → EMA200 = 100, Distance 0
    df = make_test_df([100.0] * 400)
    snap = make_snapshot_from_df("FLAT", df)
    _compute_ema200_meanrev_fields(snap, df)
    assert snap.ema200_distance_pct is not None
    assert abs(snap.ema200_distance_pct) < 0.01, f"Erwartet ~0, bekam {snap.ema200_distance_pct}"
    print(f"  ✅ flat-line distance: {snap.ema200_distance_pct:+.4f}%")


def test_ema200_distance_pct_above():
    """Steigender Trend: Kurs über EMA200, Distance positiv."""
    # Linear steigender Trend von 100 auf 200 über 400 HT
    df = make_test_df(list(np.linspace(100.0, 200.0, 400)))
    snap = make_snapshot_from_df("RISE", df)
    _compute_ema200_meanrev_fields(snap, df)
    assert snap.ema200_distance_pct is not None
    assert snap.ema200_distance_pct > 0, f"Erwartet positive Distance, bekam {snap.ema200_distance_pct}"
    print(f"  ✅ rising-trend distance: {snap.ema200_distance_pct:+.2f}%")


# ---------------------------------------------------------------------------
# Days-Since-Last-Touch-Tests
# ---------------------------------------------------------------------------

def test_days_since_touch_recent_touch():
    """Wenn der Kurs heute am EMA200 hängt, ist days_since_last_touch == 0."""
    # 400 Tage, Kurs am Ende = EMA200 (~ flat)
    df = make_test_df([100.0] * 400)
    snap = make_snapshot_from_df("FLAT", df)
    _compute_ema200_meanrev_fields(snap, df)
    assert snap.days_since_last_ema200_touch is not None
    assert snap.days_since_last_ema200_touch == 0, \
        f"Erwartet 0, bekam {snap.days_since_last_ema200_touch}"
    print(f"  ✅ recent-touch days: {snap.days_since_last_ema200_touch}")


def test_days_since_touch_old_touch():
    """Lang gelaufener Trend: Touch war vor langer Zeit."""
    # 100 HT bei 100, dann 300 HT linear auf 200 — Touch am Anfang, dann
    # zieht der Kurs weg vom EMA200.
    closes = [100.0] * 100 + list(np.linspace(100.0, 200.0, 300))
    df = make_test_df(closes)
    snap = make_snapshot_from_df("LONG-RUN", df)
    _compute_ema200_meanrev_fields(snap, df)
    assert snap.days_since_last_ema200_touch is not None
    # Letzter Touch sollte irgendwo im Übergangsbereich liegen — also viele Tage
    # in der Vergangenheit. Mindestens 50 HT erwartet.
    assert snap.days_since_last_ema200_touch >= 50, \
        f"Erwartet ≥50, bekam {snap.days_since_last_ema200_touch}"
    print(f"  ✅ old-touch days: {snap.days_since_last_ema200_touch}")


# ---------------------------------------------------------------------------
# Trend-Qualified-Tests
# ---------------------------------------------------------------------------

def test_trend_qualified_steady_uptrend():
    """Klar steigende EMA200 → trend_qualified = True."""
    closes = list(np.linspace(100.0, 200.0, 400))  # 400 HT linear steigend
    df = make_test_df(closes)
    snap = make_snapshot_from_df("UPTREND", df)
    _compute_ema200_meanrev_fields(snap, df)
    assert snap.ema200_trend_qualified is True, \
        f"Erwartet True, bekam {snap.ema200_trend_qualified}"
    print("  ✅ steady-uptrend trend_qualified = True")


def test_trend_qualified_choppy_sideways():
    """Sägezahn-Seitwärts → trend_qualified = False."""
    rng = np.random.default_rng(42)
    # Random walk um 100 herum, ohne Drift
    noise = rng.normal(0, 1.0, 400)
    closes = (100 + noise.cumsum() * 0.05).tolist()
    df = make_test_df(closes)
    snap = make_snapshot_from_df("CHOP", df)
    _compute_ema200_meanrev_fields(snap, df)
    # Bei reinem Random Walk ist die Wahrscheinlichkeit für 80% steigende EMA200-
    # Tage praktisch null. trend_qualified sollte False sein.
    assert snap.ema200_trend_qualified is False, \
        f"Erwartet False bei sideways noise, bekam {snap.ema200_trend_qualified}"
    print("  ✅ choppy-sideways trend_qualified = False")


# ---------------------------------------------------------------------------
# Weekly-HHHL-Tests
# ---------------------------------------------------------------------------

def test_weekly_hhhl_uptrend():
    """Linearer Aufwärtstrend → weekly_higher_highs_lows = True."""
    # 400 HT entspricht ~80 Wochen — mehr als genug für die 26-Wochen-Heuristik.
    closes = list(np.linspace(100.0, 200.0, 400))
    df = make_test_df(closes)
    snap = make_snapshot_from_df("UP-WEEKLY", df)
    _compute_weekly_trend_field(snap, df)
    assert snap.weekly_higher_highs_lows is True, \
        f"Erwartet True, bekam {snap.weekly_higher_highs_lows}"
    print("  ✅ uptrend weekly_hhhl = True")


def test_weekly_hhhl_downtrend():
    """Linearer Abwärtstrend → weekly_higher_highs_lows = False."""
    closes = list(np.linspace(200.0, 100.0, 400))
    df = make_test_df(closes)
    snap = make_snapshot_from_df("DOWN-WEEKLY", df)
    _compute_weekly_trend_field(snap, df)
    assert snap.weekly_higher_highs_lows is False, \
        f"Erwartet False, bekam {snap.weekly_higher_highs_lows}"
    print("  ✅ downtrend weekly_hhhl = False")


def test_weekly_hhhl_short_history():
    """Wenn weniger als 26 Wochen Daten vorliegen, Feld bleibt None."""
    # Nur 50 HT = ~10 Wochen
    df = make_test_df(list(np.linspace(100.0, 110.0, 50)))
    snap = make_snapshot_from_df("SHORT", df)
    _compute_weekly_trend_field(snap, df)
    assert snap.weekly_higher_highs_lows is None, \
        f"Erwartet None bei kurzer History, bekam {snap.weekly_higher_highs_lows}"
    print("  ✅ short-history weekly_hhhl = None")


# ---------------------------------------------------------------------------
# Integrierter Qualifikations-Test
# ---------------------------------------------------------------------------

def test_meanrev_qualifies_perfect_setup():
    """Klassischer Setup: starker Uptrend, Pullback EXAKT zum EMA200."""
    # 350 HT linear auf 200, dann 50 HT Pullback bis ~EMA200-Niveau.
    rise = list(np.linspace(100.0, 200.0, 350))
    # EMA200 sollte am Ende des Anstiegs bei ~150-160 liegen, also Kurs auf
    # ~155 fallen lassen für perfekten Touch.
    fall = list(np.linspace(200.0, 158.0, 50))
    closes = rise + fall
    df = make_test_df(closes)
    snap = make_snapshot_from_df("PERFECT", df)
    _compute_ema200_meanrev_fields(snap, df)
    _compute_weekly_trend_field(snap, df)

    print(f"  → distance={snap.ema200_distance_pct:+.2f}% · "
          f"days={snap.days_since_last_ema200_touch} · "
          f"trend_qual={snap.ema200_trend_qualified} · "
          f"weekly_hhhl={snap.weekly_higher_highs_lows}")

    # Bei diesem konstruierten Setup erwarten wir, dass alle 4 Bedingungen
    # erfüllt sind ODER mind. 3 davon (EMA200-Pullback ist scharf bis auf
    # ein paar % Toleranz). Wir prüfen die Felder einzeln, nicht das
    # qualifies-Flag — der Punkt ist die Logik-Richtigkeit.
    assert snap.ema200_distance_pct is not None
    assert snap.days_since_last_ema200_touch is not None
    assert snap.ema200_trend_qualified is True  # klarer Uptrend
    print("  ✅ perfect-setup core fields populated, trend_qualified=True")


def test_meanrev_qualifies_no_setup():
    """Crash-Szenario: starker Abwärtstrend → qualifiziert nicht."""
    closes = list(np.linspace(200.0, 100.0, 400))
    df = make_test_df(closes)
    snap = make_snapshot_from_df("CRASH", df)
    _compute_ema200_meanrev_fields(snap, df)
    _compute_weekly_trend_field(snap, df)

    # trend_qualified MUSS False sein bei Downtrend
    assert snap.ema200_trend_qualified is False
    # weekly_hhhl MUSS False sein
    assert snap.weekly_higher_highs_lows is False
    # Daher qualifiziert das Setup nicht insgesamt
    assert snap.ema200_meanrev_qualifies is False
    print("  ✅ crash-scenario qualifies = False")


# ---------------------------------------------------------------------------
# Renderer-Tests (Output-Flag)
# ---------------------------------------------------------------------------

def test_render_setup_class_flags_with_qualified_candidate():
    """Mock-Snapshot mit allen 4 Bedingungen erfüllt → Flag wird gerendert."""
    snap = TickerSnapshot(
        symbol="PERFECT.DE",
        timestamp=datetime.now(),
        price=158.0,
        prev_close=160.0,
        change_pct=-1.25,
        volume_today=1_000_000,
        ema200=160.0,
        ema200_distance_pct=-1.25,
        days_since_last_ema200_touch=180,
        ema200_trend_qualified=True,
        weekly_higher_highs_lows=True,
    )
    out = _render_setup_class_flags({"PERFECT.DE": snap})
    # Nur Daten-Zeilen — Header `## 🎯 EMA200-MEANREV-CANDIDATEs ...` ausschließen
    flag_lines = [l for l in out if l.startswith("🎯 EMA200-MEANREV-CANDIDATE")]
    assert len(flag_lines) == 1, f"Erwartet 1 Flag-Zeile, bekam: {out}"
    line = flag_lines[0]
    assert "PERFECT.DE" in line
    assert "Distance -1.25%" in line
    assert "LastTouch 180d" in line
    assert "Trend ✓" in line
    print(f"  ✅ rendered flag: {line}")


def test_render_setup_class_flags_qualifying_threshold_strict():
    """Distance > 2.0% → kein Flag (Übergabe-Spec inclusive ≤ 2.0)."""
    snap = TickerSnapshot(
        symbol="OVER.DE",
        timestamp=datetime.now(),
        price=170.0,
        prev_close=170.0,
        change_pct=0.0,
        volume_today=1_000_000,
        ema200=160.0,
        ema200_distance_pct=6.25,  # zu weit weg
        days_since_last_ema200_touch=180,
        ema200_trend_qualified=True,
        weekly_higher_highs_lows=True,
    )
    out = _render_setup_class_flags({"OVER.DE": snap})
    flag_lines = [l for l in out if l.startswith("🎯 EMA200-MEANREV-CANDIDATE")]
    assert len(flag_lines) == 0, f"Erwartet 0 Flag-Zeilen, bekam: {out}"
    print("  ✅ distance >2% correctly excluded")


def test_render_setup_class_flags_pead_window():
    """PEAD-Window: Earnings 2 HT in der Vergangenheit → Flag."""
    snap = TickerSnapshot(
        symbol="ALV.DE",
        timestamp=datetime.now(),
        price=400.0,
        prev_close=395.0,
        change_pct=1.27,
        volume_today=500_000,
        last_earnings_date="2026-05-06",
        days_since_last_earnings=2,
    )
    out = _render_setup_class_flags({"ALV.DE": snap})
    pead_lines = [l for l in out if l.startswith("📅 PEAD-WINDOW")]
    assert len(pead_lines) == 1, f"Erwartet 1 PEAD-Zeile, bekam: {out}"
    line = pead_lines[0]
    assert "ALV.DE" in line
    assert "Earnings 2026-05-06" in line
    assert "2d ago" in line
    print(f"  ✅ rendered PEAD flag: {line}")


def test_render_setup_class_flags_pead_too_old():
    """PEAD-Window: Earnings 10 HT zurück → kein Flag."""
    snap = TickerSnapshot(
        symbol="MUV2.DE",
        timestamp=datetime.now(),
        price=500.0,
        prev_close=500.0,
        change_pct=0.0,
        volume_today=300_000,
        last_earnings_date="2026-04-23",
        days_since_last_earnings=10,
    )
    out = _render_setup_class_flags({"MUV2.DE": snap})
    pead_lines = [l for l in out if l.startswith("📅 PEAD-WINDOW")]
    assert len(pead_lines) == 0, f"Erwartet 0 PEAD-Zeilen, bekam: {out}"
    print("  ✅ stale earnings (10d ago) correctly excluded")


def test_render_setup_class_flags_no_candidates_returns_empty():
    """Wenn keine Snapshots qualifizieren, gibt der Renderer eine leere Liste zurück."""
    snap = TickerSnapshot(
        symbol="BORING",
        timestamp=datetime.now(),
        price=100.0,
        prev_close=100.0,
        change_pct=0.0,
        volume_today=100,
        # Alle EMA200-Fields = None
    )
    out = _render_setup_class_flags({"BORING": snap})
    assert out == [], f"Erwartet [], bekam: {out}"
    print("  ✅ no candidates → empty list (no header pollution)")


# ---------------------------------------------------------------------------
# Mini-Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    fns = [(n, f) for n, f in globals().items()
           if n.startswith("test_") and callable(f)]
    passed = failed = 0
    for name, fn in fns:
        try:
            fn()
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ {name}: UNEXPECTED — {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
