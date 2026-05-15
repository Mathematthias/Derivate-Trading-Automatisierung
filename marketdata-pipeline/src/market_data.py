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

EMA200-MeanRev-Erweiterung (2026-05-08, Note #49):
- 4 zusätzliche Felder pro Snapshot: ema200_distance_pct, days_since_last_ema200_touch,
  ema200_trend_qualified, weekly_higher_highs_lows
- Berechnung läuft IMMER (auch in Tier B), kostet quasi nichts extra. Das Output-Flag
  wird nur in Tier-A-Files gesetzt (siehe output_renderer.py).

Earnings-Termin (optional, 2026-05-08):
- Pro-Symbol-Pull via yfinance Ticker.earnings_dates — separater Network-Call,
  daher per ENV `EARNINGS_PULL=1` aktivierbar (Default: aus).
- Schreibt next_earnings_date + last_earnings_date in den Snapshot. PEAD-Window-
  Flag (≤5 HT seit Earnings) wird vom Renderer gesetzt.
"""

from __future__ import annotations

import logging
import os
import random
import socket
import ssl
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# yfinance loggt "No earnings dates found" pro Symbol als ERROR — auch bei
# Indizes/Krypto/FX/Futures, wo das kein Fehler ist. Wir filtern Equity-only
# (siehe _is_equity_symbol), aber zur Sicherheit den yfinance-Logger auf
# WARNING heben, damit künftige Edge-Cases (kleine Werte ohne Earnings-History)
# nicht das Pipeline-Log fluten.
logging.getLogger("yfinance").setLevel(logging.WARNING)

# Mindestanteil erfolgreich gepullter Ticker, sonst Fehler
HEALTH_THRESHOLD = 0.80

# Retry-Konfiguration für yf.download (analog drive_writer._with_retry)
YF_RETRY_MAX_ATTEMPTS = 3        # 1 Initial + 2 Retries
YF_RETRY_BASE_SECONDS = 2.0      # 2, 4, 8 ...
YF_RETRY_JITTER_SECONDS = 1.0

_YF_RETRYABLE = (
    ssl.SSLEOFError,
    ssl.SSLError,
    ConnectionError,
    socket.timeout,
    TimeoutError,
    OSError,
)


@contextmanager
def _silence_yfinance_logger():
    """Temporär yfinance-Logger auf CRITICAL — verhindert die ERROR-Flut
    "No earnings dates found, symbol may be delisted" für Werte ohne
    Earnings-History (Special-Purpose-Vehicles, SDAX-Werte mit unregelmäßiger
    Reporting, Tageskurs-Ticker etc.). Wird nur im _enrich_with_earnings-Loop
    genutzt — der Haupt-Pull bleibt auf WARNING."""
    yf_logger = logging.getLogger("yfinance")
    prev_level = yf_logger.level
    yf_logger.setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        yf_logger.setLevel(prev_level)


def _yf_download_with_retry(symbols, **kwargs):
    """Wrappt yf.download mit Exponential-Backoff bei TLS/Connection-Resets.

    Yahoo-API drosselt bei vielen Symbolen mit `threads=True` gelegentlich
    via TLS-RST. Bei Tier B/C (~100-211 Symbole) ist das Risiko überschaubar
    aber nicht null. Retry kostet bei 1 Initial + 2 Retries und Backoff 2/4s
    maximal 6s pro Fehlversuch — verkraftbar gegenüber Komplett-Ausfall.

    Returns das raw DataFrame; auf Fehler-Catch nicht; ein Pipeline-Crash
    nach 3 Versuchen ist OK (besser als stilles Halbsynchronisieren).
    """
    last_exc: Optional[BaseException] = None
    for attempt in range(1, YF_RETRY_MAX_ATTEMPTS + 1):
        try:
            return yf.download(symbols, **kwargs)
        except _YF_RETRYABLE as e:
            last_exc = e
            if attempt == YF_RETRY_MAX_ATTEMPTS:
                logger.error(
                    f"yf.download: final retry failed after {attempt} attempts "
                    f"({type(e).__name__}: {e})"
                )
                raise
            wait = YF_RETRY_BASE_SECONDS ** attempt + random.uniform(0, YF_RETRY_JITTER_SECONDS)
            logger.warning(
                f"yf.download: attempt {attempt}/{YF_RETRY_MAX_ATTEMPTS} failed "
                f"({type(e).__name__}: {e}) — retrying in {wait:.1f}s"
            )
            time.sleep(wait)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("yf.download retry loop ended without result")

# Preis-Einheiten-Normierung pro Suffix.
# Yahoo liefert manche Listings in Subeinheiten (Pence statt Pound, Agorot
# statt Schekel). OHLC-Werte werden durch den Divisor geteilt; Volume bleibt
# unverändert. Erweiterbar wenn weitere Listings auffallen.
PRICE_DIVISORS: dict[str, float] = {
    ".L": 100.0,  # London Stock Exchange — Pence (GBp) → Pound (GBP)
}

# === EMA200-MeanRev-Konstanten (Note #49) ===
EMA200_TREND_LOOKBACK_HT = 120   # Vorprüfung (a): EMA200 steigt ≥80% der letzten 120 HT
EMA200_TREND_RISING_RATIO = 0.80
EMA200_TOUCH_TOL_ATR = 1.0       # |close - ema200| ≤ 1×ATR = "Touch"
WEEKLY_TREND_LOOKBACK_WK = 26    # Wochen-HH/HL-Check Fenster

# === Earnings (optional) ===
# Aktivierung per ENV: EARNINGS_PULL=1
EARNINGS_PULL_ENABLED = os.environ.get("EARNINGS_PULL", "0") == "1"


# === Anomaly-Layer V1 (2026-05-15, Note #50) ===
# Vier statistische Anomalie-Detektoren oberhalb der schwellenwert-basierten
# Bucket-Filter. Ziel: ungewöhnliche Bewegungen identifizieren, die durch das
# normale Setup-Raster fallen, weil sie kontextuell auffällig sind statt
# absolut-schwellenwert-überschreitend.
ANOMALY_LOOKBACK_DAYS = 60           # Vergleichsfenster für Z-Scores (HT)
ANOMALY_ATR_Z_THRESHOLD = 2.0        # |Z| ≥ 2.0 = Volatilitäts-Regime-Shift
ANOMALY_GAP_PCT_THRESHOLD = 2.0      # |Gap| ≥ 2.0% = Anomalie-würdig
ANOMALY_GAP_PCT_EXTREME = 5.0        # |Gap| ≥ 5.0% = Gamechanger-Klasse
ANOMALY_VOLUME_Z_THRESHOLD = 2.0     # |Z| ≥ 2.0 auf log-Volumen = Spike
ANOMALY_NR7_LOOKBACK = 7             # True-Range-Vergleichsfenster für NR7


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

    # === EMA200-MeanRev-Felder (Note #49, 2026-05-08) ===
    ema200_distance_pct: Optional[float] = None
    """Distanz zum EMA200 in % — (close - ema200) / ema200 × 100. Negativ = unter EMA200."""

    days_since_last_ema200_touch: Optional[int] = None
    """Handelstage seit letztem |close - ema200| ≤ 1×ATR. None = kein Touch im History-Fenster
    oder Daten zu kurz. 0 = Touch heute aktiv."""

    ema200_trend_qualified: Optional[bool] = None
    """EMA200 steigt in ≥80% der letzten 120 HT. None = History zu kurz für 120-Tage-Fenster."""

    weekly_higher_highs_lows: Optional[bool] = None
    """Höhere Hochs UND höhere Tiefs auf Wochen-Chart der letzten 26 Wochen.
    Implementiert als Halbjahr-Heuristik: max(jüngste 13 Wo) > max(älteste 13 Wo)
    UND min(jüngste 13 Wo) > min(älteste 13 Wo). None = History zu kurz."""

    # === Earnings-Felder (optional, 2026-05-08) ===
    next_earnings_date: Optional[str] = None
    """Nächster Earnings-Termin als ISO YYYY-MM-DD. None wenn nicht verfügbar oder
    EARNINGS_PULL=0."""

    last_earnings_date: Optional[str] = None
    """Letzter (vergangener) Earnings-Termin als ISO YYYY-MM-DD. Wird vom Renderer
    für das PEAD-WINDOW-Flag (≤5 HT seit Earnings) genutzt."""

    days_since_last_earnings: Optional[int] = None
    """Handelstage seit last_earnings_date (näherungsweise via Kalendertage minus
    Wochenende). None wenn kein last_earnings_date."""

    # === Anomaly-Layer V1 (Note #50, 2026-05-15) ===
    atr_zscore_60d: Optional[float] = None
    """Z-Score des heutigen ATR-14 gegen die letzten 60 HT ATR-Werte.
    |Z| ≥ 2.0 = Volatilitäts-Regime-Shift. None bei History < 60 HT."""

    gap_pct: Optional[float] = None
    """Eröffnungs-Gap zum Vortags-Close in %: (today_open - prev_close) / prev_close × 100.
    Positiv = Gap nach oben, negativ = Gap nach unten. None bei fehlenden Daten."""

    volume_zscore_60d: Optional[float] = None
    """Z-Score von log(volume_today) gegen log(volume) der letzten 60 HT.
    Log-Transform macht den Score robust gegen Volumen-Verteilungen mit langem
    rechten Tail. |Z| ≥ 2.0 = Volumen-Spike-Anomalie. None bei History < 60 HT
    oder ungültigen Volumen-Daten (≤0)."""

    nr7: Optional[bool] = None
    """True wenn die heutige True-Range die niedrigste der letzten 7 Handelstage ist.
    Klassisches Pre-Breakout-Signal (Volatility Contraction → Expansion).
    None bei History < 7 HT."""

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

    # === EMA200-MeanRev-Convenience ===
    @property
    def ema200_meanrev_qualifies(self) -> bool:
        """True wenn alle 4 Vorprüfungs-Bedingungen erfüllt sind (Note #49 + Übergabe).

        Trigger-Definition aus Übergabe:
        - abs(ema200_distance_pct) ≤ 2.0
        - days_since_last_ema200_touch ≥ 120
        - ema200_trend_qualified == True
        - weekly_higher_highs_lows == True
        """
        if self.ema200_distance_pct is None or abs(self.ema200_distance_pct) > 2.0:
            return False
        if self.days_since_last_ema200_touch is None or self.days_since_last_ema200_touch < 120:
            return False
        if not self.ema200_trend_qualified:
            return False
        if not self.weekly_higher_highs_lows:
            return False
        return True

    # === Anomaly-Convenience (Note #50) ===
    @property
    def is_atr_anomaly(self) -> bool:
        """True wenn ATR-Z-Score in den extremen Bereich (|Z| ≥ 2.0) fällt."""
        if self.atr_zscore_60d is None:
            return False
        return abs(self.atr_zscore_60d) >= ANOMALY_ATR_Z_THRESHOLD

    @property
    def is_gap_anomaly(self) -> bool:
        """True wenn der Eröffnungs-Gap ≥ 2.0% beträgt (in beide Richtungen)."""
        if self.gap_pct is None:
            return False
        return abs(self.gap_pct) >= ANOMALY_GAP_PCT_THRESHOLD

    @property
    def is_gap_extreme(self) -> bool:
        """True wenn der Eröffnungs-Gap ≥ 5.0% beträgt (Gamechanger-Klasse)."""
        if self.gap_pct is None:
            return False
        return abs(self.gap_pct) >= ANOMALY_GAP_PCT_EXTREME

    @property
    def is_volume_anomaly(self) -> bool:
        """True wenn Log-Volumen-Z-Score |Z| ≥ 2.0."""
        if self.volume_zscore_60d is None:
            return False
        return abs(self.volume_zscore_60d) >= ANOMALY_VOLUME_Z_THRESHOLD

    @property
    def is_range_compressed(self) -> bool:
        """True wenn NR7-Bedingung erfüllt (heutige True-Range = niedrigste der letzten 7 HT)."""
        return self.nr7 is True

    @property
    def has_any_anomaly(self) -> bool:
        """True wenn mindestens ein Anomaly-Flag aktiv ist. Convenience für Renderer."""
        return (
            self.is_atr_anomaly
            or self.is_gap_anomaly
            or self.is_volume_anomaly
            or self.is_range_compressed
        )

    def anomaly_flag_labels(self) -> list[str]:
        """Liste der aktiven Anomaly-Flags als Kurz-Labels für Renderer.

        Reihenfolge: Gap zuerst (am sichtbarsten), dann Volumen, ATR, Range.
        Range-Compression ist letzter, weil es das schwächste Einzelsignal ist —
        es lebt erst in Kombination mit anderen Anomalien.
        """
        labels: list[str] = []
        if self.is_gap_extreme:
            labels.append(f"GAP-EXTREME {self.gap_pct:+.1f}%")
        elif self.is_gap_anomaly:
            labels.append(f"GAP {self.gap_pct:+.1f}%")
        if self.is_volume_anomaly:
            labels.append(f"VOL-Z {self.volume_zscore_60d:+.1f}σ")
        if self.is_atr_anomaly:
            labels.append(f"ATR-Z {self.atr_zscore_60d:+.1f}σ")
        if self.is_range_compressed:
            labels.append("NR7")
        return labels


def fetch_ticker_data(
    symbols: list[str],
    period: str = "2y",
) -> dict[str, TickerSnapshot]:
    """Holt für alle Symbole History und berechnet Indikatoren.

    Args:
        symbols: Liste von Yahoo-Symbolen
        period: yfinance period string. 2y (statt früher 1y) ab 2026-05-08, weil
                der EMA200-Touch-Lookback bis zu 120 HT zurückblickt und der
                Wochen-HH/HL-Check 26 Wochen braucht — beides bei 1y zu knapp.

    Returns:
        dict {symbol: TickerSnapshot}, fehlende Ticker fehlen im dict
    """
    if not symbols:
        return {}

    logger.info(f"Pulling {len(symbols)} tickers via yfinance batch (period={period})")

    # Batch-Pull: ein Aufruf für alle Ticker
    # group_by='ticker' macht nested DataFrame (level 0 = Symbol)
    raw = _yf_download_with_retry(
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

    # Optional: Earnings-Termine pro Symbol nachziehen (separater Loop, weil
    # Pro-Symbol-Network-Call). Nur wenn ENV gesetzt — schützt Tier B vor
    # 300+ extra Calls.
    if EARNINGS_PULL_ENABLED and snapshots:
        _enrich_with_earnings(snapshots)

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

    # === EMA200-MeanRev-Felder (Note #49) ===
    # Brauchen: ema200, atr; History ≥ EMA200_TREND_LOOKBACK_HT = 120 HT
    _compute_ema200_meanrev_fields(snap, df)

    # === Wochen-Trend (höhere Hochs + höhere Tiefs auf 26-Wochen-Fenster) ===
    _compute_weekly_trend_field(snap, df)

    # === Anomaly-Layer V1 (Note #50) ===
    # Brauchen: 60 HT History für die Z-Scores, 7 HT für NR7.
    _compute_anomaly_fields(snap, df)

    return snap


def _compute_anomaly_fields(snap: TickerSnapshot, df: pd.DataFrame) -> None:
    """Berechnet die vier V1-Anomaly-Felder — modifiziert snap in-place.

    - atr_zscore_60d:    Z-Score des heutigen ATR-14 vs. letzte 60 HT ATR-Werte
    - gap_pct:           Eröffnungs-Gap zum Vortags-Close in %
    - volume_zscore_60d: Z-Score von log(volume_today) vs. letzte 60 HT log-Volumen
    - nr7:               True-Range heute = niedrigste der letzten 7 HT

    Stille Defaults bei zu kurzer History (60 HT bzw. 7 HT): die jeweiligen
    Felder bleiben None. Convenience-Properties (is_*_anomaly) interpretieren
    None als "kein Flag", nicht als Anomalie — sicheres Verhalten bei dünnen
    Daten (z.B. frische IPOs).
    """
    # --- gap_pct: nur today_open vs. prev_close ---
    if snap.today_open is not None and snap.prev_close is not None and snap.prev_close > 0:
        snap.gap_pct = (snap.today_open - snap.prev_close) / snap.prev_close * 100

    # --- ATR-Z-Score über 60 HT ---
    # Bedingung: mindestens 60 HT ATR-Werte oberhalb der initialen 14-HT-Warmup
    # → effektiv brauchen wir ≥ 74 HT Daten
    if len(df) >= ANOMALY_LOOKBACK_DAYS + 14 and "High" in df.columns and "Low" in df.columns:
        atr_series = _compute_atr_series(df, period=14)
        # Letzten N + 1 Werte (Vergleichsfenster + heute selbst)
        recent_atr = atr_series.dropna().tail(ANOMALY_LOOKBACK_DAYS + 1)
        if len(recent_atr) >= ANOMALY_LOOKBACK_DAYS + 1:
            today_atr = float(recent_atr.iloc[-1])
            # Baseline OHNE den heutigen Wert (sonst zerrt der eigene Wert den Mittelwert)
            baseline = recent_atr.iloc[:-1]
            mean_atr = float(baseline.mean())
            std_atr = float(baseline.std(ddof=1))
            if std_atr > 0:
                snap.atr_zscore_60d = (today_atr - mean_atr) / std_atr

    # --- Volumen-Z-Score über 60 HT (log-transformiert) ---
    if (
        "Volume" in df.columns
        and len(df) >= ANOMALY_LOOKBACK_DAYS + 1
        and snap.volume_today is not None
        and snap.volume_today > 0
    ):
        vols = df["Volume"].tail(ANOMALY_LOOKBACK_DAYS + 1)
        # Volumen > 0 erzwingen (log(0) = -inf, NaN-Tage rauswerfen)
        vols_clean = vols[vols > 0].dropna()
        if len(vols_clean) >= ANOMALY_LOOKBACK_DAYS + 1:
            import numpy as _np  # lokal, weil oben nicht zwingend importiert
            log_vols = _np.log(vols_clean.astype(float))
            today_log = float(log_vols.iloc[-1])
            baseline = log_vols.iloc[:-1]
            mean_log = float(baseline.mean())
            std_log = float(baseline.std(ddof=1))
            if std_log > 0:
                snap.volume_zscore_60d = (today_log - mean_log) / std_log

    # --- NR7: True-Range heute = niedrigste der letzten 7 HT ---
    if len(df) >= ANOMALY_NR7_LOOKBACK + 1 and all(c in df.columns for c in ["High", "Low", "Close"]):
        recent = df.tail(ANOMALY_NR7_LOOKBACK)
        # True Range = max(H-L, |H-prev_close|, |L-prev_close|)
        # Für saubere TR brauchen wir den prev_close der Reihe, also einen Eintrag
        # mehr.
        tr_window = df.tail(ANOMALY_NR7_LOOKBACK + 1).copy()
        tr_window["prev_close"] = tr_window["Close"].shift(1)
        tr_window["tr"] = tr_window.apply(
            lambda r: max(
                r["High"] - r["Low"],
                abs(r["High"] - r["prev_close"]) if pd.notna(r["prev_close"]) else 0,
                abs(r["Low"] - r["prev_close"]) if pd.notna(r["prev_close"]) else 0,
            ),
            axis=1,
        )
        # Letzte 7 vollständigen TRs (also ohne den allerersten, dessen prev_close
        # NaN ist)
        last_7_tr = tr_window["tr"].dropna().tail(ANOMALY_NR7_LOOKBACK)
        if len(last_7_tr) == ANOMALY_NR7_LOOKBACK:
            today_tr = float(last_7_tr.iloc[-1])
            min_tr = float(last_7_tr.min())
            # NR7 = strikt: heutige TR ist genau (oder eines der) Minima
            # Wir nehmen "≤ min + Epsilon" um Floating-Point-Vergleiche zu robusten
            eps = 1e-9
            snap.nr7 = today_tr <= min_tr + eps


def _compute_ema200_meanrev_fields(snap: TickerSnapshot, df: pd.DataFrame) -> None:
    """Berechnet ema200_distance_pct, days_since_last_ema200_touch und
    ema200_trend_qualified — modifiziert snap in-place.

    Stille Defaults bei zu kurzer History: alle drei bleiben None. Filter-Engine
    behandelt None korrekt (keine Qualifikation, kein Flag).
    """
    closes = df["Close"]

    # 1) ema200_distance_pct
    if snap.ema200 is not None and snap.ema200 > 0:
        snap.ema200_distance_pct = (snap.price - snap.ema200) / snap.ema200 * 100

    # 2) days_since_last_ema200_touch
    # Touch = |close - ema200_jenes_tages| ≤ 1 × atr_jenes_tages
    # Wir brauchen ema200- und ATR-Series, nicht nur den letzten Wert.
    if len(closes) >= 200 and "High" in df.columns and "Low" in df.columns:
        ema200_series = closes.ewm(span=200, adjust=False).mean()
        atr_series = _compute_atr_series(df, period=14)

        # Distanz pro Tag, dann Touch-Bool
        # Aligned auf gleichen Index; alte Zeilen mit NaN-ATR (erste 14 HT)
        # zählen als kein Touch.
        diff_abs = (closes - ema200_series).abs()
        touch_bool = (diff_abs <= atr_series * EMA200_TOUCH_TOL_ATR) & atr_series.notna()

        # Letzten True-Index suchen (jüngster Touch)
        if touch_bool.any():
            last_touch_idx = touch_bool[touch_bool].index[-1]
            today_idx = closes.index[-1]
            # Anzahl Trading-Tage zwischen den beiden Indizes
            # (df ist auf Daily-Trading-Tage indexiert, also: positionsbasiert)
            try:
                last_touch_pos = df.index.get_loc(last_touch_idx)
                today_pos = df.index.get_loc(today_idx)
                snap.days_since_last_ema200_touch = int(today_pos - last_touch_pos)
            except (KeyError, TypeError):
                # Falls Index-Lookup fehlschlägt, lassen wir das Feld None.
                pass
        # Wenn KEIN Touch in der 2y-History gefunden wurde:
        #   → Setup ist im Zweifel sehr gut qualifiziert (langer ungebrochener Lauf).
        #   Wir setzen auf len(df) - 1 als untere Schranke. Das genügt der
        #   ≥120-HT-Bedingung sicher.
        else:
            snap.days_since_last_ema200_touch = len(df) - 1

    # 3) ema200_trend_qualified
    # EMA200 steigt in ≥80% der letzten 120 HT
    if len(closes) >= 200 + EMA200_TREND_LOOKBACK_HT:
        ema200_series = closes.ewm(span=200, adjust=False).mean()
        recent = ema200_series.tail(EMA200_TREND_LOOKBACK_HT)
        diffs = recent.diff().dropna()
        if len(diffs) > 0:
            rising_share = (diffs > 0).mean()
            snap.ema200_trend_qualified = bool(rising_share >= EMA200_TREND_RISING_RATIO)
    elif len(closes) >= 200:
        # History reicht für EMA200 selbst, aber nicht für das volle 120-Tage-
        # Trend-Fenster. Mit dem, was da ist, abschätzen — aber nur wenn
        # mind. 60 HT verfügbar sind, sonst zu unsicher.
        ema200_series = closes.ewm(span=200, adjust=False).mean()
        # tail(EMA200_TREND_LOOKBACK_HT) ist gleichbedeutend mit "die letzten N",
        # auch wenn N > Länge — pandas gibt einfach alles.
        recent = ema200_series.tail(EMA200_TREND_LOOKBACK_HT)
        diffs = recent.diff().dropna()
        if len(diffs) >= 60:
            rising_share = (diffs > 0).mean()
            snap.ema200_trend_qualified = bool(rising_share >= EMA200_TREND_RISING_RATIO)


def _compute_weekly_trend_field(snap: TickerSnapshot, df: pd.DataFrame) -> None:
    """Setzt weekly_higher_highs_lows.

    Pragmatische Halbjahr-Heuristik: Resampling Daily → Weekly (W-FRI für
    Wochen-Schluss-Konvention), dann letzte 26 Wochen in zwei Hälften teilen
    und Hoch/Tief vergleichen.

    True wenn: max(jüngste 13 Wo) > max(älteste 13 Wo)
            UND min(jüngste 13 Wo) > min(älteste 13 Wo)

    Bewusst robust statt streng: Pivot-für-Pivot-HHHL ist vom Pivot-Algorithmus
    abhängig und falsch-positiv-empfindlich. Halbjahr-Vergleich ist klar
    definiert und liefert das, was Note #49 in der Sache will: ein intakter
    mehrmonatiger Wochen-Aufwärtstrend.
    """
    if "High" not in df.columns or "Low" not in df.columns:
        return

    # Wochenbalken bauen — High = Max, Low = Min innerhalb der Woche
    weekly = df.resample("W-FRI").agg({"High": "max", "Low": "min"}).dropna()
    if len(weekly) < WEEKLY_TREND_LOOKBACK_WK:
        return

    last26 = weekly.tail(WEEKLY_TREND_LOOKBACK_WK)
    half = WEEKLY_TREND_LOOKBACK_WK // 2  # 13
    older = last26.iloc[:half]
    newer = last26.iloc[half:]

    higher_high = float(newer["High"].max()) > float(older["High"].max())
    higher_low = float(newer["Low"].min()) > float(older["Low"].min())
    snap.weekly_higher_highs_lows = bool(higher_high and higher_low)


def _is_equity_symbol(symbol: str) -> bool:
    """Heuristik: Hat das Symbol potenziell Earnings-Dates?

    Erkennt Equity-Symbole anhand von Yahoo-Finance-Konventionen:
    - Indizes beginnen mit `^`            (^GDAXI, ^GSPC, ...)
    - FX-Paare enden mit `=X`             (EURUSD=X, USDJPY=X, ...)
    - Futures enden mit `=F`              (GC=F, CL=F, ...)
    - Krypto enthält `-EUR`/`-USD`/`-USDT` (BTC-EUR, ETH-USD, ...)

    Hardcoded-Skipliste für ETCs/ETFs ohne Earnings, die wie Aktien aussehen.
    """
    if not symbol:
        return False
    if symbol.startswith("^"):
        return False
    if symbol.endswith("=X") or symbol.endswith("=F"):
        return False
    if "-EUR" in symbol or "-USD" in symbol or "-USDT" in symbol:
        return False
    if symbol in NON_EQUITY_HARDCODE_SKIP:
        return False
    return True


# ETCs/ETFs ohne Earnings, die nach Equity-Symbol aussehen.
# Erweiterbar wenn weitere Symbole im Pipeline-Log auffallen.
NON_EQUITY_HARDCODE_SKIP: frozenset[str] = frozenset({
    "4GLD.DE",   # Xetra-Gold ETC
    "XAD5.DE",   # Xtrackers Physical Gold ETC
})


def _enrich_with_earnings(snapshots: dict[str, TickerSnapshot]) -> None:
    """Holt next_earnings_date + last_earnings_date pro Symbol via yfinance.

    Pro-Symbol-Network-Call (kein Batch in yfinance). Pre-Filter via
    _is_equity_symbol → Indizes/FX/Futures/Krypto/bekannte ETCs werden
    übersprungen. Try/Except pro Symbol für unerwartete Edge-Cases.

    Aktivierung: ENV `EARNINGS_PULL=1`. Default: aus.

    Abhängigkeit: yfinance ruft intern lxml zum Parsen der Earnings-HTML auf,
    daher muss lxml in requirements.txt enthalten sein.
    """
    today = date.today()
    skipped = 0
    # yfinance loggt "No earnings dates found, symbol may be delisted" als
    # ERROR für jeden Equity ohne Earnings-History (BVB, EKT, HAB, KSB3, STO3
    # in unserem Universum, weil unregelmäßig reportende SDAX-Werte). Das
    # füllt das Pipeline-Log mit Pseudo-Errors. Daher Logger für den Loop
    # auf CRITICAL — eigene Logs bleiben auf logger.debug erhalten.
    with _silence_yfinance_logger():
        for symbol, snap in snapshots.items():
            if not _is_equity_symbol(symbol):
                skipped += 1
                continue
            try:
                tk = yf.Ticker(symbol)
                ed = tk.earnings_dates
            except Exception as e:
                logger.debug(f"earnings_dates failed for {symbol}: {e}")
                continue

            if ed is None or len(ed) == 0:
                continue

            try:
                # Index ist Timestamp; in Date konvertieren
                dates = pd.to_datetime(ed.index).date

                future_dates = [d for d in dates if d > today]
                past_dates = [d for d in dates if d <= today]

                if future_dates:
                    snap.next_earnings_date = min(future_dates).isoformat()

                if past_dates:
                    last = max(past_dates)
                    snap.last_earnings_date = last.isoformat()
                    # Handelstage-Approximation: Kalendertage minus volle Wochenenden
                    cal_days = (today - last).days
                    full_weekends = cal_days // 7 * 2
                    snap.days_since_last_earnings = max(0, cal_days - full_weekends)
            except Exception as e:
                logger.debug(f"earnings parse failed for {symbol}: {e}")
                continue

    if skipped:
        logger.info(f"earnings_pull: skipped {skipped} non-equity symbols (indices/FX/futures/crypto/ETCs)")


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
    """ATR nach Wilder's Smoothing-Methode (letzter Wert)."""
    return float(_compute_atr_series(df, period=period).iloc[-1])


def _compute_atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """ATR-Series (für Touch-Detection brauchen wir die volle Reihe, nicht nur den letzten Wert)."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    return atr
