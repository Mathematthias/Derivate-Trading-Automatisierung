"""Test: Pence-zu-Pound-Konvertierung für UK-Listings.

Ausführen vom marketdata-pipeline/ Verzeichnis:
    PYTHONPATH=./src python tests/test_pence_normalization.py
"""

import sys

import pandas as pd

from market_data import _normalize_price_units


def test_uk_listing_divides_by_100():
    """SHEL.L: yfinance liefert Pence, muss durch 100 geteilt werden."""
    df = pd.DataFrame({
        "Open":   [3100.0, 3120.0],
        "High":   [3200.0, 3210.0],
        "Low":    [3080.0, 3100.0],
        "Close":  [3192.0, 3180.0],
        "Volume": [1_500_000, 1_400_000],
    })
    result = _normalize_price_units("SHEL.L", df)
    assert result["Close"].iloc[-1] == 31.80
    assert result["High"].iloc[-1] == 32.10
    assert result["Open"].iloc[0] == 31.00
    assert result["Low"].iloc[0] == 30.80
    # Volume bleibt unverändert (Stückzahl, nicht Preis)
    assert result["Volume"].iloc[-1] == 1_400_000


def test_non_uk_listing_unchanged():
    """TTE.PA: Paris-Listing in Euro, keine Konvertierung."""
    df = pd.DataFrame({
        "Open":   [76.00],
        "High":   [76.50],
        "Low":    [75.80],
        "Close":  [76.02],
        "Volume": [2_000_000],
    })
    result = _normalize_price_units("TTE.PA", df)
    assert result["Close"].iloc[-1] == 76.02
    pd.testing.assert_frame_equal(result, df)


def test_us_ticker_unchanged():
    """US-Ticker ohne Suffix: keine Konvertierung."""
    df = pd.DataFrame({
        "Close":  [476.53],
        "Volume": [3_000_000],
    })
    result = _normalize_price_units("CRWD", df)
    assert result["Close"].iloc[-1] == 476.53


def test_german_ticker_unchanged():
    """XAD5.DE: Xetra-Listing in Euro, keine Konvertierung."""
    df = pd.DataFrame({
        "Open":   [380.50],
        "High":   [383.20],
        "Low":    [379.10],
        "Close":  [382.00],
        "Volume": [50_000],
    })
    result = _normalize_price_units("XAD5.DE", df)
    assert result["Close"].iloc[-1] == 382.00
    pd.testing.assert_frame_equal(result, df)


def test_adj_close_also_normalized():
    """Adj Close muss ebenfalls konvertiert werden (für Splitschätzungen etc.)."""
    df = pd.DataFrame({
        "Close":     [3192.0],
        "Adj Close": [3150.0],
        "Volume":    [1_000_000],
    })
    result = _normalize_price_units("SHEL.L", df)
    assert result["Close"].iloc[-1] == 31.92
    assert result["Adj Close"].iloc[-1] == 31.50


def test_original_df_not_mutated():
    """Funktion muss df kopieren, nicht in-place modifizieren."""
    df = pd.DataFrame({
        "Close":  [3192.0],
        "Volume": [1_000_000],
    })
    original_close = df["Close"].iloc[0]
    _ = _normalize_price_units("SHEL.L", df)
    assert df["Close"].iloc[0] == original_close, "Original df wurde mutiert!"


if __name__ == "__main__":
    fns = [
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    ]
    passed = 0
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  ✅ {name}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ {name}: UNEXPECTED — {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
