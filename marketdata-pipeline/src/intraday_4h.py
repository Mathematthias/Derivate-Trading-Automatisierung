"""4h-Layer für die Pipeline (v0.1, 2026-09-08).

ANLASS: Die Watchlist-Trigger verlangen durchgehend eine 4h-Bestätigung
("4h-Bullish-Reverse-Close", "RSI-4h Cross über die Signallinie"), aber das
Universum führte bisher ausschließlich 1D-Indikatoren. Der `filter_engine`
konnte diese Bedingungen deshalb nur als `conditions_pending` durchreichen —
der Verdeckt-BEREIT-Mechanismus (Note #118/#294) ist die Folge dieser Lücke,
nicht ihre Lösung. Zusätzlich braucht die neue Klasse Grinder-Continuation
(§ SKILL.md, 2026-09-08) eine 4h-Warnstufe.

WIE DIE 4h-KERZEN ENTSTEHEN — und warum nicht per Kalender-Resample:
yfinance kennt kein natives 4h-Intervall. Ein `resample("4h")` über die
Kalenderzeit erzeugt Balken, die NICHT zu TradingView passen, weil TradingView
Intraday-Balken an der SESSION-ERÖFFNUNG verankert und nicht an Mitternacht.

Der Algorithmus hier ist deshalb: 1h-Balken je Handelstag in Reihenfolge
bringen und in Blöcken zu je vier zusammenfassen. Das reproduziert TradingView
für die relevanten Börsen exakt:

    NYSE  09:30-16:00 (7 1h-Balken) -> 09:30-13:30 | 13:30-16:00 (Teilblock)
    XETRA 09:00-17:30 (9 1h-Balken) -> 09:00-13:00 | 13:00-17:00 | 17:00-17:30
    24h   (Krypto/Futures, 24 Balken) -> 6 Blöcke ab 00:00

Der jeweils LETZTE Block eines laufenden Handelstages ist unfertig. Alle
Auswertungen laufen deshalb auf `closed_only=True` — eine Bedingung, die
"4h-Reverse-CLOSE" heißt, darf nicht auf einem offenen Balken feuern.

⚠️ NICHT LIVE VERIFIZIERT (Stand 2026-09-08): In der Entwicklungsumgebung war
Yahoo nicht erreichbar. Die Resample-Semantik ist gegen synthetische Daten
getestet (tests/test_intraday_4h.py), die tatsächliche 1h-Abdeckung je Börse
ist es nicht. Vor dem Scharfschalten von `evaluate_reverse`:
`python -m scripts.verify_4h_coverage` laufen lassen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BARS_PER_BLOCK = 4


@dataclass
class Indicators4h:
    """Was der 4h-Layer je Symbol liefert. Alles optional — fehlende Daten
    sind der Normalfall, nicht der Fehlerfall (illiquide Werte, Feiertage,
    Börsen ohne Yahoo-Intraday-Abdeckung)."""

    bar_time: Optional[str] = None          # ISO-Zeit des letzten GESCHLOSSENEN Blocks
    bars_available: int = 0
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    prev_open: Optional[float] = None
    prev_close: Optional[float] = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    ema100: Optional[float] = None
    ema200: Optional[float] = None
    rsi14: Optional[float] = None
    rsi14_signal: Optional[float] = None
    atr14: Optional[float] = None
    stack: Optional[str] = None             # "bullish" | "bearish" | "neutral"
    reverse_bullish: Optional[bool] = None
    reverse_bearish: Optional[bool] = None
    reverse_reason: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


def resample_1h_to_4h(df: pd.DataFrame, closed_only: bool = True,
                      bars_per_block: int = BARS_PER_BLOCK) -> pd.DataFrame:
    """1h-OHLCV -> session-verankerte 4h-Balken.

    Gruppiert je Handelstag und fasst die Balken in ihrer zeitlichen Reihenfolge
    zu Blöcken von `bars_per_block` zusammen. Der letzte Block eines Tages darf
    kürzer sein (Teilblock) — das ist bei NYSE der Normalfall.

    `closed_only=True` verwirft den letzten Block, wenn er unvollständig ist UND
    zum jüngsten Handelstag gehört: ein laufender Balken ist kein Close.
    Vollständige Teilblöcke früherer Tage (NYSE 13:30-16:00) bleiben erhalten —
    sie sind abgeschlossen, nur kürzer.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    need = {"Open", "High", "Low", "Close"}
    if not need.issubset(set(df.columns)):
        return pd.DataFrame()

    df = df.dropna(subset=["Open", "High", "Low", "Close"]).sort_index()
    if df.empty:
        return pd.DataFrame()

    dates = pd.Series(df.index.date, index=df.index)
    # Laufende Nummer des Balkens INNERHALB seines Handelstages -> Blockindex
    seq = dates.groupby(dates).cumcount()
    block = seq // bars_per_block
    key = pd.Series(
        [f"{d.isoformat()}#{b:02d}" for d, b in zip(dates.values, block.values)],
        index=df.index,
    )
    # Der Blockschlüssel wird auf den Zeitstempel seines ERSTEN Balkens
    # abgebildet — dann trägt der 4h-Balken die Session-Zeit, die auch
    # TradingView anzeigt (NYSE 09:30/13:30, XETRA 09:00/13:00/17:00).
    block_start = df.index.to_series().groupby(key).transform("first")

    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
    if "Volume" in df.columns:
        agg["Volume"] = "sum"

    grouped = df.groupby(block_start, sort=True)
    out = grouped.agg(agg)
    out["_bars"] = grouped.size()
    out.index.name = None
    out = out.sort_index()

    if closed_only and not out.empty:
        last_day = df.index[-1].date()
        last_key_day = out.index[-1].date()
        if last_key_day == last_day and int(out["_bars"].iloc[-1]) < bars_per_block:
            # Kann ein laufender Block sein. Bei Börsen mit Teil-Blöcken am
            # Sessionende (NYSE) verwerfen wir damit gelegentlich einen
            # abgeschlossenen Balken — das ist die konservative Richtung: eine
            # Bestätigung zu spät zu sehen kostet einen Trade, eine zu früh
            # gesehene kostet Geld (L26-Logik).
            out = out.iloc[:-1]
    return out.drop(columns=["_bars"], errors="ignore")


def _ema(series: pd.Series, span: int) -> Optional[float]:
    if len(series) < span:
        return None
    return float(series.ewm(span=span, adjust=False).mean().iloc[-1])


def _rsi_series(closes: pd.Series, period: int = 14) -> Optional[pd.Series]:
    if len(closes) < period + 1:
        return None
    delta = closes.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    # Division durch 0 ergibt inf -> RSI 100. pd.NA waere hier falsch: eine
    # Serie ohne einen einzigen Verlust ist ein gueltiger Extremwert, kein
    # fehlender Wert (und bricht spaeter das astype(float)).
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
    out = 100 - 100 / (1 + rs)
    return out.replace([np.inf, -np.inf], 100.0).astype(float)


def _atr(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    if len(df) < period + 1:
        return None
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1 / period, adjust=False).mean().iloc[-1])


def detect_reverse(df4h: pd.DataFrame) -> tuple[Optional[bool], Optional[bool], Optional[str]]:
    """Reverse-Kerze auf dem letzten GESCHLOSSENEN 4h-Balken.

    Bullisch: Hammer (untere Wick >= 50 % der Range UND Close im oberen Drittel)
              ODER Bullish Engulfing (Close > prev Open, prev war rot).
    Bärisch:  Shooting Star (obere Wick >= 50 % UND Close im unteren Drittel)
              ODER Bearish Engulfing (Close < prev Open, prev war grün).

    Die Schwellen entsprechen der Daily-Logik des `filter_engine`; sie sind
    gesetzt, nicht gemessen (Lektion 24 — Hypothese, kein Veto).
    """
    if df4h is None or len(df4h) < 2:
        return None, None, None
    o, h, l, c = (float(df4h["Open"].iloc[-1]), float(df4h["High"].iloc[-1]),
                  float(df4h["Low"].iloc[-1]), float(df4h["Close"].iloc[-1]))
    po, pc = float(df4h["Open"].iloc[-2]), float(df4h["Close"].iloc[-2])
    rng = h - l
    if rng <= 0:
        return False, False, "Range 0"
    lower_wick = (min(o, c) - l) / rng
    upper_wick = (h - max(o, c)) / rng
    close_pos = (c - l) / rng

    hammer = lower_wick >= 0.5 and close_pos >= 0.66
    bull_eng = pc < po and c > po
    star = upper_wick >= 0.5 and close_pos <= 0.34
    bear_eng = pc > po and c < po

    reasons = []
    if hammer:
        reasons.append(f"Hammer (Wick {lower_wick:.0%}, Close-Pos {close_pos:.0%})")
    if bull_eng:
        reasons.append("Bullish-Engulfing")
    if star:
        reasons.append(f"Shooting-Star (Wick {upper_wick:.0%}, Close-Pos {close_pos:.0%})")
    if bear_eng:
        reasons.append("Bearish-Engulfing")
    return (hammer or bull_eng), (star or bear_eng), ("; ".join(reasons) or None)


def compute_4h(df_1h: pd.DataFrame, rsi_signal_len: int = 14,
               bars_per_block: int = BARS_PER_BLOCK) -> Indicators4h:
    """1h-Rohdaten -> Indikatoren auf dem letzten geschlossenen 4h-Balken."""
    ind = Indicators4h()
    df = resample_1h_to_4h(df_1h, closed_only=True, bars_per_block=bars_per_block)
    if df.empty:
        return ind
    ind.bars_available = len(df)
    ind.bar_time = df.index[-1].isoformat() if hasattr(df.index[-1], "isoformat") else str(df.index[-1])
    ind.open, ind.high = float(df["Open"].iloc[-1]), float(df["High"].iloc[-1])
    ind.low, ind.close = float(df["Low"].iloc[-1]), float(df["Close"].iloc[-1])
    if len(df) >= 2:
        ind.prev_open, ind.prev_close = float(df["Open"].iloc[-2]), float(df["Close"].iloc[-2])

    closes = df["Close"]
    ind.ema20, ind.ema50 = _ema(closes, 20), _ema(closes, 50)
    ind.ema100, ind.ema200 = _ema(closes, 100), _ema(closes, 200)
    rsi = _rsi_series(closes, 14)
    if rsi is not None and not rsi.dropna().empty:
        ind.rsi14 = float(rsi.iloc[-1])
        if len(rsi.dropna()) >= rsi_signal_len:
            ind.rsi14_signal = float(rsi.rolling(rsi_signal_len).mean().iloc[-1])
    ind.atr14 = _atr(df, 14)

    if None not in (ind.ema20, ind.ema50):
        if ind.ema100 is not None:
            bull = ind.ema20 > ind.ema50 > ind.ema100
            bear = ind.ema20 < ind.ema50 < ind.ema100
        else:
            bull, bear = ind.ema20 > ind.ema50, ind.ema20 < ind.ema50
        ind.stack = "bullish" if bull else ("bearish" if bear else "neutral")

    ind.reverse_bullish, ind.reverse_bearish, ind.reverse_reason = detect_reverse(df)
    return ind


def pull_4h(symbols: list[str], period: str = "60d",
            rsi_signal_len: int = 14,
            downloader=None) -> dict[str, Indicators4h]:
    """Batch-Pull 1h + Aggregation. `downloader` nur für Tests injizierbar."""
    if not symbols:
        return {}
    if downloader is None:
        import yfinance as yf
        downloader = lambda syms, **kw: yf.download(syms, **kw)  # noqa: E731

    logger.info(f"4h-Layer: pulling {len(symbols)} Ticker (1h, period={period})")
    try:
        raw = downloader(symbols, period=period, interval="1h",
                         group_by="ticker", auto_adjust=False,
                         progress=False, threads=False)
    except Exception as exc:  # pragma: no cover - Netzpfad
        logger.warning(f"4h-Layer: Download fehlgeschlagen ({exc}) — Layer fällt aus.")
        return {}

    out: dict[str, Indicators4h] = {}
    for sym in symbols:
        try:
            sub = raw[sym] if isinstance(raw.columns, pd.MultiIndex) else raw
            out[sym] = compute_4h(sub, rsi_signal_len=rsi_signal_len)
        except Exception as exc:
            logger.debug(f"4h-Layer: {sym} übersprungen ({exc})")
            out[sym] = Indicators4h()
    have = sum(1 for v in out.values() if v.bars_available)
    logger.info(f"4h-Layer: {have}/{len(symbols)} Ticker mit auswertbaren 4h-Balken.")
    return out
