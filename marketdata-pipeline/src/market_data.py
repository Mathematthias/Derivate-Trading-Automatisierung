"""
market_data.py — yfinance-Pull und technische Indikatoren

Bietet eine einheitliche Schnittstelle, um für eine Liste von Yahoo-Symbolen
die nötigen Markt- und Indikator-Daten zu holen. Output ist ein dict
{symbol: TickerSnapshot}, das von der Filter-Engine konsumiert wird.

Design-Entscheidungen:
- Batch-Pull statt einzelner Calls (yfinance.download für viele Ticker auf einmal)
- Failover: Wenn ein einzelner Ticker fehlt, wird er übersprungen und geloggt
- Health-Check: Wenn weniger als HEALTH_THRESHOLD% der Ticker erfolgreich,
  wirft das Skript einen Fehler statt unbrauchbares Output zu schreiben
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# Mindestanteil erfolgreich gepullter Ticker, sonst Fehler
HEALTH_THRESHOLD = 0.80

# Preis-Einheiten-Normierung pro Suffix.
# Yahoo liefert manche Listings in Subeinheiten (Pence statt Pound, Agorot
# statt Schekel). OHLC-Werte werden durch den Divisor geteilt; Volume bleibt
# unverändert. Erweiterbar wenn weitere Listings auffallen.
PRICE_DIVISORS: dict[str, float] = {
    ".L": 100.0,  # London Stock Exchange — Pence (GBp) → Pound (GBP)
}


@dataclass
class TickerSnapshot:
    """Aggregierte Daten und Indikatoren für einen Ticker zum aktuellen Zeitpunkt."""

    symbol: str
    timestamp: datetime

    # Aktueller Stand
    price: float
    prev_close: Optional[float]
    change_pct: Optional[float]  # heutige Bewegung vs. Vortag
    volume_today: Optional[int]

    # Indikatoren auf Daily-Basis
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema200: Optional[float] = None
    rsi14: Optional[float] = None
    atr14: Optional[float] = None  # absoluter ATR-Wert in EUR/USD

    # Range / Bewegung
    move_30d_pct: Optional[float] = None  # Kurs heute vs. Kurs vor 30 Tagen
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    distance_from_52w_high_pct: Optional[float] = None  # negativ = drunter
    distance_from_52w_low_pct: Optional[float] = None  # positiv = drüber

    # Volumen
    volume_avg_20d: Optional[int] = None
    volume_eur_avg_20d: Optional[float] = None  # Avg-Volumen × Kurs in EUR
    volume_multiplier_today: Optional[float] = None  # heute vs. avg

    # 20d Range (für Breakout-Detection)
    high_20d: Optional[float] = None
    low_20d: Optional[float] = None

    # Heutige Kerze (für Bounce-Detection)
    today_open: Optional[float] = None
    today_high: Optional[float] = None
    today_low: Optional[float] = None
    today_close: Optional[float] = None
    today_lower_wick_pct: Optional[float] = None  # untere Wick als % der Range

    # EMA-Stack (Hilfsmethoden)
    @property
    def has_bullish_stack(self) -> bool:
        """EMA20 > EMA50 > EMA200."""
        if None in (self.ema20, self.ema50, self.ema200):
            return False
        return self.ema20 > self.ema50 > self.ema200

    @property
    def has_bearish_stack(self) -> bool:
        """EMA20 < EMA50 < EMA200."""
        if None in (self.ema20, self.ema50, self.ema200):
            return False
        return self.ema20 < self.ema50 < self.ema200


def fetch_ticker_data(
    symbols: list[str],
    period: str = "1y",
) -> dict[str, TickerSnapshot]:
    """Holt für alle Symbole History und berechnet Indikatoren.

    Args:
        symbols: Liste von Yahoo-Symbolen
        period: yfinance period string (1y reicht für 200d-EMA + Buffer)

    Returns:
        dict {symbol: TickerSnapshot}, fehlende Ticker fehlen im dict
    """
    if not symbols:
        return {}

    logger.info(f"Pulling {len(symbols)} tickers via yfinance batch")

    # Batch-Pull: ein Aufruf für alle Ticker
    # group_by='ticker' macht nested DataFrame (level 0 = Symbol)
    raw = yf.download(
        symbols,
        period=period,
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )

    snapshots: dict[str, TickerSnapshot] = {}
    failed: list[str] = []

    for symbol in symbols:
        try:
            # Bei einzelnem Ticker hat raw nicht die nested Struktur
            if len(symbols) == 1:
                df = raw
            else:
                df = raw[symbol]

            if df.empty or "Close" not in df.columns:
                failed.append(symbol)
                continue

            # Cleanup: nur echte Daten-Zeilen
            df = df.dropna(subset=["Close"])
            if len(df) < 2:
                failed.append(symbol)
                continue

            # Preis-Einheiten normieren (z.B. UK-Listings Pence → Pound)
            df = _normalize_price_units(symbol, df)

            snap = _compute_snapshot(symbol, df)
            if snap is None:
                failed.append(symbol)
            else:
                snapshots[symbol] = snap

        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"  Failed {symbol}: {type(e).__name__}: {e}")
            failed.append(symbol)

    success_rate = len(snapshots) / len(symbols)
    logger.info(
        f"  Success: {len(snapshots)}/{len(symbols)} "
        f"({success_rate:.0%}), Failed: {failed}"
    )

    if success_rate < HEALTH_THRESHOLD:
        raise RuntimeError(
            f"Health-Check failed: nur {success_rate:.0%} der Ticker "
            f"erfolgreich (Threshold {HEALTH_THRESHOLD:.0%}). "
            f"Failed: {failed}"
        )

    return snapshots


def _compute_snapshot(symbol: str, df: pd.DataFrame) -> Optional[TickerSnapshot]:
    """Berechnet alle Indikatoren für einen einzelnen Ticker."""
    if len(df) < 2:
        return None

    # Aktuelle Werte = letzter Close
    last_row = df.iloc[-1]
    price = float(last_row["Close"])
    if pd.isna(price):
        return None

    timestamp = datetime.now()

    # Vortag (vorletzter Close)
    prev_close: Optional[float] = None
    change_pct: Optional[float] = None
    if len(df) >= 2:
        prev_close_val = df.iloc[-2]["Close"]
        if not pd.isna(prev_close_val):
            prev_close = float(prev_close_val)
            change_pct = (price - prev_close) / prev_close * 100

    # Volumen heute
    volume_today: Optional[int] = None
    vol_val = last_row.get("Volume")
    if vol_val is not None and not pd.isna(vol_val):
        volume_today = int(vol_val)

    snap = TickerSnapshot(
        symbol=symbol,
        timestamp=timestamp,
        price=price,
        prev_close=prev_close,
        change_pct=change_pct,
        volume_today=volume_today,
    )

    closes = df["Close"]

    # EMAs
    if len(closes) >= 20:
        snap.ema20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
    if len(closes) >= 50:
        snap.ema50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])
    if len(closes) >= 200:
        snap.ema200 = float(closes.ewm(span=200, adjust=False).mean().iloc[-1])

    # RSI-14 (klassisch via Wilder's smoothing)
    if len(closes) >= 15:
        snap.rsi14 = _compute_rsi(closes, period=14)

    # ATR-14
    if len(df) >= 15 and "High" in df.columns and "Low" in df.columns:
        snap.atr14 = _compute_atr(df, period=14)

    # 30d-Move
    if len(closes) >= 22:  # ~30 Kalendertage = ~22 Handelstage
        ref_price = float(closes.iloc[-22])
        if ref_price > 0:
            snap.move_30d_pct = (price - ref_price) / ref_price * 100

    # 52W-Range (252 Handelstage)
    lookback = min(252, len(df))
    if lookback >= 50 and "High" in df.columns and "Low" in df.columns:
        recent = df.tail(lookback)
        snap.high_52w = float(recent["High"].max())
        snap.low_52w = float(recent["Low"].min())
        if snap.high_52w > 0:
            snap.distance_from_52w_high_pct = (
                (price - snap.high_52w) / snap.high_52w * 100
            )
        if snap.low_52w > 0:
            snap.distance_from_52w_low_pct = (
                (price - snap.low_52w) / snap.low_52w * 100
            )

    # Volumen-Avg 20d
    if "Volume" in df.columns and len(df) >= 20:
        vol20 = df["Volume"].tail(20)
        if not vol20.isna().all():
            snap.volume_avg_20d = int(vol20.mean())
            snap.volume_eur_avg_20d = snap.volume_avg_20d * price
            if snap.volume_avg_20d > 0 and volume_today is not None:
                snap.volume_multiplier_today = volume_today / snap.volume_avg_20d

    # 20d-High/Low (für Breakout)
    if len(df) >= 20 and "High" in df.columns:
        recent20 = df.tail(20)
        snap.high_20d = float(recent20["High"].max())
        snap.low_20d = float(recent20["Low"].min())

    # Heutige Kerze (für Bounce-Detection)
    if all(c in df.columns for c in ["Open", "High", "Low", "Close"]):
        snap.today_open = float(last_row["Open"]) if not pd.isna(last_row["Open"]) else None
        snap.today_high = float(last_row["High"]) if not pd.isna(last_row["High"]) else None
        snap.today_low = float(last_row["Low"]) if not pd.isna(last_row["Low"]) else None
        snap.today_close = float(last_row["Close"]) if not pd.isna(last_row["Close"]) else None
        # Lower Wick % = (Close oder Open, je nachdem was tiefer - Low) / Range
        if all(v is not None for v in [snap.today_high, snap.today_low, snap.today_open, snap.today_close]):
            day_range = snap.today_high - snap.today_low
            if day_range > 0:
                body_low = min(snap.today_open, snap.today_close)
                lower_wick = body_low - snap.today_low
                snap.today_lower_wick_pct = lower_wick / day_range * 100

    return snap


def _normalize_price_units(symbol: str, df: pd.DataFrame) -> pd.DataFrame:
    """Normiert OHLC-Preisspalten auf Hauptwährungs-Einheiten.

    Aktuell: UK-Listings (.L) von Pence (GBp) zu Pound (GBP) — Faktor 100.
    Hintergrund: Yahoo Finance liefert LSE-Listings standardmäßig in Pence,
    obwohl der Currency-Field "GBP" angibt. Beispiel SHEL.L: Yahoo-Close
    3192.00 entspricht 31.92 GBP.
    Volume bleibt unverändert (Stückzahl, nicht Preis).
    Erweiterbar für weitere Subunit-Listings (z.B. .TA für Tel Aviv = Agorot).
    """
    for suffix, divisor in PRICE_DIVISORS.items():
        if symbol.endswith(suffix):
            df = df.copy()
            for col in ("Open", "High", "Low", "Close", "Adj Close"):
                if col in df.columns:
                    df[col] = df[col] / divisor
            return df
    return df


def _compute_rsi(closes: pd.Series, period: int = 14) -> float:
    """RSI nach Wilder's Smoothing-Methode."""
    delta = closes.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - 100 / (1 + rs)
    return float(rsi.iloc[-1])


def _compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    """ATR nach Wilder's Smoothing-Methode."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    return float(atr.iloc[-1])
