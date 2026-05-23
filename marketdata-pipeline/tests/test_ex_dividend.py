"""
Tests für V1.2 Ex-Dividende-Anreicherung (Note #67, 2026-05-23).

Deckt ab:
- _compute_ex_dividend_fields: Feld-Ableitung aus der Dividends-Spalte
- Pence-Normalisierung der Dividends-Spalte (.L-Listings)
- Breakdown-Short-Pre-Filter (last_ex_div_days_ago <= 2 -> kein Signal)
- MARKETDATA-FULL Ex-Div-Render-Zeile

Ausführen vom marketdata-pipeline/ Verzeichnis:
    PYTHONPATH=./src pytest tests/test_ex_dividend.py -v
"""

import datetime as dt
import os
import sys

import pandas as pd
import pytest
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
sys.path.insert(0, _SRC)

from market_data import (
    TickerSnapshot,
    _compute_ex_dividend_fields,
    _normalize_price_units,
)
from filter_engine import _check_bucket
from output_renderer import render_marketdata_full


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_div_df(n: int, dividends: dict | None = None) -> pd.DataFrame:
    """Synthetischer Daily-DataFrame inkl. Dividends-Spalte.

    dividends: {Zeilen-Index ab 0: Betrag} — alle anderen Zeilen 0.0.
    """
    idx = pd.bdate_range(start="2025-01-01", periods=n)
    div_col = [0.0] * n
    for pos, amount in (dividends or {}).items():
        div_col[pos] = amount
    return pd.DataFrame({
        "Open": [100.0] * n,
        "High": [101.0] * n,
        "Low": [99.0] * n,
        "Close": [100.0] * n,
        "Adj Close": [100.0] * n,
        "Volume": [1_000_000] * n,
        "Dividends": div_col,
    }, index=idx)


def make_div_df_dates(base: str, offsets: list, amount: float = 0.5) -> pd.DataFrame:
    """df (nur Dividends-Spalte) mit Ex-Tagen an base + offsets Kalendertagen,
    plus zwei dividendenfreie Folgetage nach dem letzten Ex-Tag."""
    base_ts = pd.Timestamp(base)
    ex_dates = [base_ts + pd.Timedelta(days=o) for o in offsets]
    tail = [ex_dates[-1] + pd.Timedelta(days=i) for i in (1, 2)]
    all_dates = sorted(ex_dates + tail)
    div_set = set(ex_dates)
    div_col = [amount if d in div_set else 0.0 for d in all_dates]
    return pd.DataFrame({"Dividends": div_col}, index=pd.DatetimeIndex(all_dates))


def empty_snap() -> TickerSnapshot:
    return TickerSnapshot(
        symbol="TEST",
        timestamp=dt.datetime(2026, 5, 23),
        price=100.0,
        prev_close=99.0,
        change_pct=0.0,
    )


def breakdown_match_snap(last_ex_div_days_ago=None) -> TickerSnapshot:
    """Snapshot, der ohne Ex-Div-Filter sicher in breakdown_short fällt:
    bearish EMA-Stack, am 20d-Tief, Volumen-Spike, RSI über Minimum.
    """
    snap = TickerSnapshot(
        symbol="HEIDE",
        timestamp=dt.datetime(2026, 5, 23),
        price=100.0,
        prev_close=108.0,
        change_pct=-7.16,
        ema20=110.0, ema50=115.0, ema200=120.0,  # bearish: 110<115<120
        low_20d=100.0,                            # dist_to_low = 0.0%
        volume_multiplier_today=2.0,              # >= volume_multiplier_min
        rsi14=35.0,                               # >= rsi_min
    )
    snap.last_ex_div_days_ago = last_ex_div_days_ago
    return snap


@pytest.fixture
def config():
    cfg_path = os.path.join(_HERE, "..", "config", "filter_config.yaml")
    with open(cfg_path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# 1) _compute_ex_dividend_fields — Feld-Ableitung
# ---------------------------------------------------------------------------

def test_no_dividends_column():
    """df ohne Dividends-Spalte -> alle Felder bleiben None."""
    snap = empty_snap()
    df = make_div_df(30).drop(columns=["Dividends"])
    _compute_ex_dividend_fields(snap, df)
    assert snap.last_ex_div_date is None
    assert snap.last_ex_div_days_ago is None
    assert snap.last_ex_div_amount is None
    assert snap.next_ex_div_date is None


def test_dividends_all_zero():
    """Dividends-Spalte ausschließlich 0.0 -> keine Ex-Tage erkannt."""
    snap = empty_snap()
    _compute_ex_dividend_fields(snap, make_div_df(30))
    assert snap.last_ex_div_date is None
    assert snap.last_ex_div_days_ago is None


def test_single_ex_dividend():
    """Ein Ex-Tag, 3 HT vor dem letzten -> days_ago=3, Betrag/Datum korrekt."""
    snap = empty_snap()
    n = 30
    df = make_div_df(n, dividends={n - 4: 2.50})  # Position n-4 -> 3 HT vor Ende
    _compute_ex_dividend_fields(snap, df)
    assert snap.last_ex_div_days_ago == 3
    assert snap.last_ex_div_amount == 2.50
    assert snap.last_ex_div_date == df.index[n - 4].date().isoformat()
    # Nur eine Dividende -> keine Kadenz-Schätzung
    assert snap.next_ex_div_date is None


def test_ex_dividend_today():
    """Ex-Tag ist die letzte Zeile -> days_ago=0."""
    snap = empty_snap()
    n = 30
    _compute_ex_dividend_fields(snap, make_div_df(n, dividends={n - 1: 1.0}))
    assert snap.last_ex_div_days_ago == 0


def test_next_ex_div_quarterly_cadence():
    """Vier Ex-Tage im 91-Tage-Raster -> next = last + 91 Tage."""
    snap = empty_snap()
    df = make_div_df_dates("2025-01-15", offsets=[0, 91, 182, 273])
    _compute_ex_dividend_fields(snap, df)
    assert snap.next_ex_div_date is not None
    gap = (dt.date.fromisoformat(snap.next_ex_div_date)
           - dt.date.fromisoformat(snap.last_ex_div_date)).days
    assert gap == 91, f"Quartals-Kadenz erwartet (91d), got {gap}"


def test_next_ex_div_annual_cadence():
    """Zwei Ex-Tage 365 Tage auseinander -> next = last + 365 Tage."""
    snap = empty_snap()
    df = make_div_df_dates("2024-05-20", offsets=[0, 365], amount=4.0)
    _compute_ex_dividend_fields(snap, df)
    assert snap.next_ex_div_date is not None
    gap = (dt.date.fromisoformat(snap.next_ex_div_date)
           - dt.date.fromisoformat(snap.last_ex_div_date)).days
    assert gap == 365, f"Jahres-Kadenz erwartet (365d), got {gap}"


def test_dividends_normalized_for_pence_listing():
    """Bei .L-Listings wird die Dividends-Spalte wie Preise durch 100 geteilt."""
    n = 10
    df = make_div_df(n, dividends={n - 1: 250.0})  # 250 Pence
    out = _normalize_price_units("SHEL.L", df)
    assert out["Dividends"].iloc[n - 1] == 2.50


# ---------------------------------------------------------------------------
# 2) Breakdown-Short-Pre-Filter (HEI.DE-Lehre, Note #67)
# ---------------------------------------------------------------------------

def test_breakdown_short_matches_without_recent_ex_div(config):
    """Kontroll-Test: ohne kürzlichen Ex-Tag fällt der Wert in breakdown_short."""
    match = _check_bucket(breakdown_match_snap(None), "breakdown_short", config)
    assert match is not None, "Snapshot sollte ohne Ex-Div-Filter matchen"
    assert match.bucket == "breakdown_short"


@pytest.mark.parametrize("days_ago", [0, 1, 2])
def test_breakdown_short_skipped_on_recent_ex_div(config, days_ago):
    """HEI.DE-Synthetic: Ex-Tag <=2 HT zurück -> kein Breakdown-Short-Signal."""
    match = _check_bucket(breakdown_match_snap(days_ago), "breakdown_short", config)
    assert match is None, (
        f"Ex-Tag {days_ago} HT zurück — Drop ist Buchungseffekt, "
        f"darf nicht als Breakdown gemeldet werden"
    )


def test_breakdown_short_not_skipped_after_cutoff(config):
    """Ex-Tag 3 HT zurück -> Cutoff überschritten, normale Breakdown-Logik greift."""
    match = _check_bucket(breakdown_match_snap(3), "breakdown_short", config)
    assert match is not None


# ---------------------------------------------------------------------------
# 3) MARKETDATA-FULL Render-Zeile
# ---------------------------------------------------------------------------

def test_marketdata_full_renders_ex_div_line():
    """MARKETDATA-FULL enthält die Ex-Div-Zeile, wenn die Felder gesetzt sind."""
    snap = empty_snap()
    snap.symbol = "AOF.DE"
    snap.last_ex_div_date = "2026-05-21"
    snap.last_ex_div_days_ago = 2
    snap.last_ex_div_amount = 4.0
    snap.next_ex_div_date = "2027-05-20"
    text = render_marketdata_full({"AOF.DE": snap}, dt.datetime(2026, 5, 23))
    assert "Ex-Div:" in text
    assert "2026-05-21" in text
    assert "2d ago" in text
    assert "geschätzt" in text


def test_marketdata_full_no_ex_div_line_when_absent():
    """Ohne Ex-Div-Daten keine Ex-Div-Zeile (Indizes/FX/dividendenlose Werte)."""
    text = render_marketdata_full({"TEST": empty_snap()}, dt.datetime(2026, 5, 23))
    assert "Ex-Div:" not in text
