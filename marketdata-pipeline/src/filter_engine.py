"""
filter_engine.py — Zweistufige Filter-Engine

Stufe 1: Watchlist-Trigger-Status-Check
   Für jeden Watchlist-Eintrag aus dem STATE wird geprüft, ob seine
   konkreten Trigger-Bedingungen erfüllt sind. Output ist ein Status:
   - in_zone: Kurs IN der Trigger-Zone, alle Bedingungen erfüllt
   - very_close: <= 2% entfernt
   - close: <= 5%
   - watching: <= 10%
   - far: > 10%, passive
   - pending: Datum-Constraint noch nicht erreicht
   - paused: Status im STATE ist 'paused' — Bedingung temporär weg

Stufe 2: Universe-Setup-Filter
   Für nicht-Watchlist-Werte werden generische Setup-Buckets geprüft:
   - long_trend_pullback / short_trend_pullback
   - breakout_long / breakdown_short
   - reversal_long / reversal_short
   Mit Universal-Disqualifiern (Liquidität, Earnings, 30d-Move).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from market_data import TickerSnapshot
from state_parser import (
    FilterOverride,
    ParsedTrigger,
    WatchlistEntry,
)

logger = logging.getLogger(__name__)


# ============================================================
# DATENMODELLE FÜR OUTPUT
# ============================================================

@dataclass
class TriggerStatus:
    """Auswertung eines einzelnen Triggers (A, B, ...) eines Watchlist-Eintrags."""

    label: str  # "A", "B", oder ""
    proximity: str  # "in_zone" | "very_close" | "close" | "watching" | "far"
    distance_pct: float  # signed: negativ = drunter, positiv = drüber
    conditions_met: list[str] = field(default_factory=list)  # erfüllte Sub-Bedingungen
    conditions_missing: list[str] = field(default_factory=list)  # fehlende
    summary: str = ""  # Kurzfassung für Output


@dataclass
class WatchlistResult:
    """Auswertung eines Watchlist-Eintrags zum aktuellen Marktstand."""

    entry: WatchlistEntry
    snapshot: Optional[TickerSnapshot]  # None falls Daten fehlen
    overall_status: str  # "active" | "pending" | "paused" | "stale_data" | "no_data"
    trigger_results: list[TriggerStatus] = field(default_factory=list)
    note: str = ""  # zusätzliche Anmerkung (z.B. "Pre-Trade-Datum erreicht in 3 Tagen")


@dataclass
class CandidateMatch:
    """Ein Stufe-2-Treffer aus dem Universe-Setup-Filter."""

    symbol: str
    bucket: str  # z.B. "long_trend_pullback"
    snapshot: TickerSnapshot
    score: float  # höher = besser, je nach Bucket-Heuristik
    summary: str


# ============================================================
# HELPER
# ============================================================

def _has_bounce(snap: TickerSnapshot, cfg: dict) -> bool:
    """Prüft ob die heutige Kerze Bounce-Charakteristik hat."""
    bounce_cfg = cfg["watchlist_trigger_parsing"]["bounce_detection"]
    if snap.today_lower_wick_pct is None:
        return False
    if snap.today_lower_wick_pct < bounce_cfg["require_lower_wick_pct"]:
        return False
    if bounce_cfg["require_close_above_open"]:
        if snap.today_close is None or snap.today_open is None:
            return False
        if snap.today_close <= snap.today_open:
            return False
    return True


def _has_volume_validation(snap: TickerSnapshot, cfg: dict) -> bool:
    """Prüft ob heutiges Volumen über Schwelle ist."""
    vol_cfg = cfg["watchlist_trigger_parsing"]["volume_validation"]
    if snap.volume_multiplier_today is None:
        return False
    return snap.volume_multiplier_today >= vol_cfg["require_multiplier"]


def _classify_proximity(distance_pct: float, cfg: dict) -> str:
    """Wandelt absolute Distanz in Proximity-Bucket."""
    abs_dist = abs(distance_pct)
    prox_cfg = cfg["watchlist_trigger_parsing"]["trigger_proximity"]
    if abs_dist <= prox_cfg["in_zone"] + 0.01:  # Toleranz für 0.0
        return "in_zone"
    if abs_dist <= prox_cfg["very_close"]:
        return "very_close"
    if abs_dist <= prox_cfg["close"]:
        return "close"
    if abs_dist <= prox_cfg["watching"]:
        return "watching"
    return "far"


# ============================================================
# STUFE 1: WATCHLIST-TRIGGER-CHECK
# ============================================================

def evaluate_watchlist(
    entries: list[WatchlistEntry],
    snapshots: dict[str, TickerSnapshot],
    config: dict,
    today: date,
) -> list[WatchlistResult]:
    """Wertet jeden Watchlist-Eintrag gegen aktuelle Daten aus."""
    results: list[WatchlistResult] = []
    for entry in entries:
        snap = snapshots.get(entry.symbol)
        result = _evaluate_single_entry(entry, snap, config, today)
        results.append(result)
    return results


def _evaluate_single_entry(
    entry: WatchlistEntry,
    snap: Optional[TickerSnapshot],
    config: dict,
    today: date,
) -> WatchlistResult:
    """Wertet einen einzelnen Watchlist-Eintrag aus."""
    # Status 'paused' aus STATE direkt durchreichen
    if entry.status == "paused":
        return WatchlistResult(
            entry=entry,
            snapshot=snap,
            overall_status="paused",
            note=entry.status_note,
        )

    # Datum-Constraint prüfen
    if entry.earliest_date is not None and today < entry.earliest_date:
        days_until = (entry.earliest_date - today).days
        return WatchlistResult(
            entry=entry,
            snapshot=snap,
            overall_status="pending",
            note=f"erst ab {entry.earliest_date.isoformat()} ({days_until}d)",
        )

    # Snapshot fehlt
    if snap is None:
        return WatchlistResult(
            entry=entry,
            snapshot=None,
            overall_status="no_data",
            note="yfinance lieferte keine Daten",
        )

    # Trigger einzeln bewerten
    trigger_results: list[TriggerStatus] = []
    for trigger in entry.triggers:
        ts = _evaluate_trigger(trigger, snap, entry.direction, config)
        trigger_results.append(ts)

    return WatchlistResult(
        entry=entry,
        snapshot=snap,
        overall_status="active",
        trigger_results=trigger_results,
    )


def _evaluate_trigger(
    trigger: ParsedTrigger,
    snap: TickerSnapshot,
    direction: str,
    config: dict,
) -> TriggerStatus:
    """Bewertet einen einzelnen Trigger gegen aktuelle Daten."""
    # Edge case: leerer Trigger ohne Preis-Op und ohne Modifier
    # (z.B. "ONBERG-Story — Setup ergänzen wenn relevant")
    is_empty = (
        trigger.price_op is None
        and not trigger.require_bounce
        and not trigger.require_volume
        and not trigger.require_hammer
        and trigger.rsi_max is None
        and trigger.rsi_min is None
        and trigger.ema_ref is None
    )
    if is_empty:
        return TriggerStatus(
            label=trigger.label,
            proximity="far",  # damit nicht in BEREIT-Bucket
            distance_pct=0.0,
            conditions_met=[],
            conditions_missing=["kein konkreter Trigger im STATE definiert"],
            summary="ohne konkreten Trigger — Setup im STATE ergänzen",
        )

    distance_pct = 0.0
    conditions_met: list[str] = []
    conditions_missing: list[str] = []

    # === PREIS-DISTANZ ===
    price = snap.price
    if trigger.price_op == "in_range":
        # Distanz = 0 wenn IN range, sonst nach unten/oben gemessen
        if trigger.price_low <= price <= trigger.price_high:
            distance_pct = 0.0
            conditions_met.append(f"Preis {price:.2f} IN-ZONE [{trigger.price_low:.2f}–{trigger.price_high:.2f}]")
        elif price < trigger.price_low:
            distance_pct = (price - trigger.price_low) / trigger.price_low * 100
            conditions_missing.append(
                f"Preis {price:.2f} unter Range [{trigger.price_low:.2f}–{trigger.price_high:.2f}] ({distance_pct:+.2f}%)"
            )
        else:  # price > price_high
            distance_pct = (price - trigger.price_high) / trigger.price_high * 100
            conditions_missing.append(
                f"Preis {price:.2f} über Range [{trigger.price_low:.2f}–{trigger.price_high:.2f}] ({distance_pct:+.2f}%)"
            )

    elif trigger.price_op == ">":
        # Trigger erfüllt wenn Kurs > Schwelle
        distance_pct = (price - trigger.price_single) / trigger.price_single * 100
        if price > trigger.price_single:
            conditions_met.append(f"Preis {price:.2f} > {trigger.price_single:.2f}")
        else:
            conditions_missing.append(
                f"Preis {price:.2f} ≤ {trigger.price_single:.2f} ({distance_pct:+.2f}%)"
            )

    elif trigger.price_op == "<":
        distance_pct = (price - trigger.price_single) / trigger.price_single * 100
        if price < trigger.price_single:
            conditions_met.append(f"Preis {price:.2f} < {trigger.price_single:.2f}")
        else:
            conditions_missing.append(
                f"Preis {price:.2f} ≥ {trigger.price_single:.2f} ({distance_pct:+.2f}%)"
            )

    elif trigger.price_op == "approx":
        # Approx: ±2% Toleranz um den Approx-Preis
        distance_pct = (price - trigger.price_single) / trigger.price_single * 100
        if abs(distance_pct) <= 2.0:
            conditions_met.append(f"Preis {price:.2f} ≈ {trigger.price_single:.2f} ({distance_pct:+.2f}%)")
        else:
            conditions_missing.append(
                f"Preis {price:.2f} ≠ {trigger.price_single:.2f} ({distance_pct:+.2f}%)"
            )

    # === MODIFIKATOREN ===
    if trigger.require_bounce:
        if _has_bounce(snap, config):
            conditions_met.append("Bounce-Kerze ✓")
        else:
            wick = snap.today_lower_wick_pct
            wick_str = f"{wick:.0f}%" if wick is not None else "n/a"
            conditions_missing.append(f"keine Bounce-Kerze (Wick {wick_str}, Close>Open: {snap.today_close > snap.today_open if snap.today_close and snap.today_open else 'n/a'})")

    if trigger.require_volume:
        if _has_volume_validation(snap, config):
            conditions_met.append(f"Vol {snap.volume_multiplier_today:.2f}× avg ✓")
        else:
            mul = snap.volume_multiplier_today
            mul_str = f"{mul:.2f}×" if mul is not None else "n/a"
            conditions_missing.append(f"Vol {mul_str} unter Schwelle")

    if trigger.require_hammer:
        # Vereinfachter Hammer-Check: Lower-Wick > 50% UND Close oben in Range
        if (snap.today_lower_wick_pct is not None
                and snap.today_lower_wick_pct >= 50
                and snap.today_close and snap.today_high and snap.today_low):
            range_total = snap.today_high - snap.today_low
            close_pos = (snap.today_close - snap.today_low) / range_total if range_total > 0 else 0
            if close_pos >= 0.6:
                conditions_met.append(f"Hammer-Kerze ✓ (Wick {snap.today_lower_wick_pct:.0f}%)")
            else:
                conditions_missing.append(f"keine Hammer-Kerze (Close-Position {close_pos:.0%})")
        else:
            conditions_missing.append("keine Hammer-Kerze")

    if trigger.rsi_max is not None:
        if snap.rsi14 is not None and snap.rsi14 < trigger.rsi_max:
            conditions_met.append(f"RSI {snap.rsi14:.1f} < {trigger.rsi_max:.0f}")
        else:
            rsi_str = f"{snap.rsi14:.1f}" if snap.rsi14 is not None else "n/a"
            conditions_missing.append(f"RSI {rsi_str} ≥ {trigger.rsi_max:.0f}")

    if trigger.rsi_min is not None:
        if snap.rsi14 is not None and snap.rsi14 > trigger.rsi_min:
            conditions_met.append(f"RSI {snap.rsi14:.1f} > {trigger.rsi_min:.0f}")
        else:
            rsi_str = f"{snap.rsi14:.1f}" if snap.rsi14 is not None else "n/a"
            conditions_missing.append(f"RSI {rsi_str} ≤ {trigger.rsi_min:.0f}")

    proximity = _classify_proximity(distance_pct, config)

    # Summary kurz formulieren
    if proximity == "in_zone" and not conditions_missing:
        summary = "🎯 BEREIT — alle Bedingungen erfüllt"
    elif proximity == "in_zone":
        summary = f"⚠️ in Zone, aber Bedingungen offen: {', '.join(conditions_missing)}"
    elif proximity in ("very_close", "close"):
        summary = f"📍 {proximity} ({distance_pct:+.2f}%)"
    else:
        summary = f"… {proximity} ({distance_pct:+.2f}%)"

    return TriggerStatus(
        label=trigger.label,
        proximity=proximity,
        distance_pct=distance_pct,
        conditions_met=conditions_met,
        conditions_missing=conditions_missing,
        summary=summary,
    )


# ============================================================
# STUFE 2: UNIVERSE-SETUP-FILTER
# ============================================================

def evaluate_universe(
    snapshots: dict[str, TickerSnapshot],
    excluded_symbols: set[str],
    config: dict,
    overrides: list[FilterOverride],
    today: date,
    excluded_category_symbols: Optional[set[str]] = None,
) -> list[CandidateMatch]:
    """Prüft alle Snapshots (außer excluded) gegen Setup-Buckets.

    Args:
        snapshots: alle gepullten Snapshots
        excluded_symbols: Watchlist-Symbole (sollen Stufe 1, nicht Stufe 2)
        excluded_category_symbols: Indizes/Forex/Krypto/Positionen — sind
            Makro-Kontext, keine Trade-Kandidaten. Default leer.
    """
    matches: list[CandidateMatch] = []
    if excluded_category_symbols is None:
        excluded_category_symbols = set()

    override_symbols_disqualified = {
        ov.symbol for ov in overrides
        if ov.override_type == "disqualified"
        and (ov.valid_until is None or ov.valid_until >= today)
    }
    override_symbols_wait = {
        ov.symbol for ov in overrides
        if ov.override_type == "wait_for"
        and ov.valid_until is not None and ov.valid_until > today
    }

    for symbol, snap in snapshots.items():
        if symbol in excluded_symbols:
            continue
        if symbol in excluded_category_symbols:
            # Indizes/Forex/Krypto sind Makro-Kontext, kein Setup-Kandidat
            continue
        if symbol in override_symbols_disqualified:
            continue
        if symbol in override_symbols_wait:
            continue

        # Universal-Disqualifier
        if not _passes_universal_disqualifier(snap, config):
            continue

        # Pro Bucket prüfen
        for bucket_name in [
            "long_trend_pullback",
            "short_trend_pullback",
            "breakout_long",
            "breakdown_short",
            "reversal_long",
            "reversal_short",
        ]:
            match = _check_bucket(snap, bucket_name, config)
            if match is not None:
                matches.append(match)

    # Pro Bucket auf max_new_candidates_per_bucket reduzieren
    max_per_bucket = config["output"]["max_new_candidates_per_bucket"]
    bucket_groups: dict[str, list[CandidateMatch]] = {}
    for m in matches:
        bucket_groups.setdefault(m.bucket, []).append(m)

    final_matches: list[CandidateMatch] = []
    for bucket, ms in bucket_groups.items():
        ms.sort(key=lambda x: x.score, reverse=True)
        final_matches.extend(ms[:max_per_bucket])

    return final_matches


def _passes_universal_disqualifier(snap: TickerSnapshot, config: dict) -> bool:
    """Prüft Liquidität + 30d-Move (Earnings-Check folgt in Phase 6)."""
    cfg = config["universal_disqualifier"]

    # Liquidität
    if snap.volume_eur_avg_20d is not None:
        if snap.volume_eur_avg_20d < cfg["min_avg_volume_eur"]:
            return False

    # 30d-Move
    if snap.move_30d_pct is not None:
        if abs(snap.move_30d_pct) > cfg["thirty_day_move_max_pct"]:
            return False

    return True


def _check_bucket(
    snap: TickerSnapshot,
    bucket: str,
    config: dict,
) -> Optional[CandidateMatch]:
    """Prüft ob ein Snapshot in einen Bucket fällt."""
    cfg = config.get(bucket)
    if not cfg:
        return None

    # Long-Trend-Pullback
    if bucket == "long_trend_pullback":
        if cfg.get("require_bullish_ema_stack") and not snap.has_bullish_stack:
            return None
        if snap.ema20 is None:
            return None
        # 30d-Move muss positiv sein für echten Long-Trend
        if snap.move_30d_pct is None or snap.move_30d_pct <= 0:
            return None
        ema_dist = (snap.price - snap.ema20) / snap.ema20 * 100
        if not (cfg["ema_distance_min_pct"] <= ema_dist <= cfg["ema_distance_max_pct"]):
            return None
        if snap.rsi14 is None or snap.rsi14 > cfg["rsi_max"]:
            return None
        if snap.distance_from_52w_high_pct is None:
            return None
        if abs(snap.distance_from_52w_high_pct) < cfg["min_distance_from_52w_high_pct"]:
            return None
        # Score: niedriger ema_dist (näher an EMA) + niedriger RSI = besser
        score = -abs(ema_dist) - snap.rsi14 * 0.1
        summary = (
            f"{snap.symbol}: {snap.price:.2f}  EMA20={snap.ema20:.2f} "
            f"Dist={ema_dist:+.2f}%  RSI={snap.rsi14:.0f}  "
            f"30d={snap.move_30d_pct:+.1f}%"
        )
        return CandidateMatch(
            symbol=snap.symbol, bucket=bucket, snapshot=snap,
            score=score, summary=summary,
        )

    # Short-Trend-Pullback (Spiegel)
    if bucket == "short_trend_pullback":
        if cfg.get("require_bearish_ema_stack") and not snap.has_bearish_stack:
            return None
        if snap.ema20 is None:
            return None
        # 30d-Move muss negativ sein für echten Short-Trend
        if snap.move_30d_pct is None or snap.move_30d_pct >= 0:
            return None
        ema_dist = (snap.price - snap.ema20) / snap.ema20 * 100
        if not (cfg["ema_distance_min_pct"] <= ema_dist <= cfg["ema_distance_max_pct"]):
            return None
        if snap.rsi14 is None or snap.rsi14 < cfg["rsi_min"]:
            return None
        if snap.distance_from_52w_low_pct is None:
            return None
        if abs(snap.distance_from_52w_low_pct) < cfg["min_distance_from_52w_low_pct"]:
            return None
        score = -abs(ema_dist) + snap.rsi14 * 0.1
        summary = (
            f"{snap.symbol}: {snap.price:.2f}  EMA20={snap.ema20:.2f} "
            f"Dist={ema_dist:+.2f}%  RSI={snap.rsi14:.0f}  "
            f"30d={snap.move_30d_pct:+.1f}%"
        )
        return CandidateMatch(
            symbol=snap.symbol, bucket=bucket, snapshot=snap,
            score=score, summary=summary,
        )

    # Breakout Long
    if bucket == "breakout_long":
        if cfg.get("require_bullish_ema_stack") and not snap.has_bullish_stack:
            return None
        if snap.high_20d is None:
            return None
        dist_to_high = (snap.high_20d - snap.price) / snap.high_20d * 100
        if dist_to_high > cfg["distance_to_20d_high_pct"]:
            return None
        if dist_to_high < -1.0:  # zu weit drüber = nicht mehr Breakout
            return None
        if snap.volume_multiplier_today is None or snap.volume_multiplier_today < cfg["volume_multiplier_min"]:
            return None
        if snap.rsi14 is None or snap.rsi14 > cfg["rsi_max"]:
            return None
        score = snap.volume_multiplier_today + 1.0 / max(0.1, dist_to_high)
        summary = (
            f"{snap.symbol}: {snap.price:.2f}  20d-High={snap.high_20d:.2f} "
            f"({dist_to_high:+.2f}%)  Vol={snap.volume_multiplier_today:.1f}×  "
            f"RSI={snap.rsi14:.0f}"
        )
        return CandidateMatch(
            symbol=snap.symbol, bucket=bucket, snapshot=snap,
            score=score, summary=summary,
        )

    # Breakdown Short
    if bucket == "breakdown_short":
        if cfg.get("require_bearish_ema_stack") and not snap.has_bearish_stack:
            return None
        if snap.low_20d is None:
            return None
        dist_to_low = (snap.price - snap.low_20d) / snap.low_20d * 100
        if dist_to_low > cfg["distance_to_20d_low_pct"]:
            return None
        if dist_to_low < -1.0:
            return None
        if snap.volume_multiplier_today is None or snap.volume_multiplier_today < cfg["volume_multiplier_min"]:
            return None
        if snap.rsi14 is None or snap.rsi14 < cfg["rsi_min"]:
            return None
        score = snap.volume_multiplier_today + 1.0 / max(0.1, dist_to_low)
        summary = (
            f"{snap.symbol}: {snap.price:.2f}  20d-Low={snap.low_20d:.2f} "
            f"({dist_to_low:+.2f}%)  Vol={snap.volume_multiplier_today:.1f}×  "
            f"RSI={snap.rsi14:.0f}"
        )
        return CandidateMatch(
            symbol=snap.symbol, bucket=bucket, snapshot=snap,
            score=score, summary=summary,
        )

    # Reversal Long
    if bucket == "reversal_long":
        if snap.distance_from_52w_low_pct is None:
            return None
        if snap.distance_from_52w_low_pct > cfg["distance_from_52w_low_pct"]:
            return None
        if snap.rsi14 is None or snap.rsi14 > cfg["rsi_max"]:
            return None
        score = -snap.distance_from_52w_low_pct - snap.rsi14
        summary = (
            f"{snap.symbol}: {snap.price:.2f}  52W-Low={snap.low_52w:.2f} "
            f"(+{snap.distance_from_52w_low_pct:.2f}%)  RSI={snap.rsi14:.0f}"
        )
        return CandidateMatch(
            symbol=snap.symbol, bucket=bucket, snapshot=snap,
            score=score, summary=summary,
        )

    # Reversal Short
    if bucket == "reversal_short":
        if snap.distance_from_52w_high_pct is None:
            return None
        if abs(snap.distance_from_52w_high_pct) > cfg["distance_from_52w_high_pct"]:
            return None
        if snap.rsi14 is None or snap.rsi14 < cfg["rsi_min"]:
            return None
        score = snap.distance_from_52w_high_pct + snap.rsi14
        summary = (
            f"{snap.symbol}: {snap.price:.2f}  52W-High={snap.high_52w:.2f} "
            f"({snap.distance_from_52w_high_pct:.2f}%)  RSI={snap.rsi14:.0f}"
        )
        return CandidateMatch(
            symbol=snap.symbol, bucket=bucket, snapshot=snap,
            score=score, summary=summary,
        )

    return None
