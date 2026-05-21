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
    conditions_missing: list[str] = field(default_factory=list)  # fehlende (hart durchgefallen)
    conditions_pending: list[str] = field(default_factory=list)  # noch offen (Tagesvolumen, etc.)
    summary: str = ""  # Kurzfassung für Output
    blown_through: bool = False  # Task 5: Breakout-Zone durchgelaufen (Kurs über Obergrenze)


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


def _has_volume_validation(snap: TickerSnapshot, cfg: dict, vol_multiplier: Optional[float] = None) -> bool:
    """Prüft ob heutiges Volumen über Schwelle ist.

    Args:
        vol_multiplier: Falls der Trigger einen expliziten Multiplier mitbringt
            (z.B. "Vol ≥ 1,2× Avg-20d"), dieser überschreibt den Config-Default.
    """
    if snap.volume_multiplier_today is None:
        return False
    threshold = vol_multiplier if vol_multiplier is not None else cfg["watchlist_trigger_parsing"]["volume_validation"]["require_multiplier"]
    return snap.volume_multiplier_today >= threshold


def _get_vol_status(
    snap: TickerSnapshot,
    cfg: dict,
    vol_multiplier: Optional[float],
    now_utc_hour: Optional[int],
) -> str:
    """Bewertet die Volumen-Bedingung mit 4 Stati.

    Returns:
        'met'     — Tagesvolumen erreicht (oder bereits über) die Schwelle.
        'failed'  — Volumen unter Schwelle UND wir sind nach der Hard-Evaluation-Stunde
                    (= Tagesvolumen ist defacto final).
        'pending' — Volumen unter Schwelle, aber vor der Hard-Evaluation-Stunde
                    (= Tagesvolumen kann sich noch füllen).
        'unknown' — Keine Volumen-Daten verfügbar.

    Hintergrund: Wenn die Pipeline tagsüber läuft (z.B. 14:30 CEST), ist das
    Tagesvolumen noch nicht endgültig. Eine harte "Vol fehlt"-Ablehnung
    blockiert dann unnötig den BEREIT-Bucket, obwohl das Volumen bis Tagesende
    noch ankommen kann. Erst nach `hard_evaluation_utc_hour` (Default 20 UTC
    = 21/22 CEST nach US-Close) wird "fehlend" zu "failed".
    """
    if snap.volume_multiplier_today is None:
        return "unknown"

    threshold = vol_multiplier if vol_multiplier is not None else cfg["watchlist_trigger_parsing"]["volume_validation"]["require_multiplier"]
    if snap.volume_multiplier_today >= threshold:
        return "met"

    # Unter Schwelle — pending oder failed je nach Uhrzeit
    hard_hour = cfg["watchlist_trigger_parsing"].get("hard_evaluation_utc_hour", 20)
    if now_utc_hour is None:
        # Kein Zeit-Kontext vorhanden → konservativer Default: failed (alter Verhalten)
        return "failed"
    if now_utc_hour >= hard_hour:
        return "failed"
    return "pending"


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
    now_utc_hour: Optional[int] = None,
) -> list[WatchlistResult]:
    """Wertet jeden Watchlist-Eintrag gegen aktuelle Daten aus.

    Args:
        now_utc_hour: Aktuelle Stunde in UTC (0–23). Wird gebraucht, um
            "Vol noch nicht gefüllt"-Fälle als pending (nicht failed) zu
            klassifizieren. Optional für Backward-Compat: None → konservativer
            Modus (Vol fehlend = failed wie vor dem Patch).
    """
    results: list[WatchlistResult] = []
    for entry in entries:
        snap = snapshots.get(entry.symbol)
        result = _evaluate_single_entry(entry, snap, config, today, now_utc_hour)
        results.append(result)
    return results


def _evaluate_single_entry(
    entry: WatchlistEntry,
    snap: Optional[TickerSnapshot],
    config: dict,
    today: date,
    now_utc_hour: Optional[int] = None,
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
        ts = _evaluate_trigger(trigger, snap, entry.direction, config, now_utc_hour)
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
    now_utc_hour: Optional[int] = None,
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
            conditions_pending=[],
            summary="ohne konkreten Trigger — Setup im STATE ergänzen",
        )

    distance_pct = 0.0
    conditions_met: list[str] = []
    conditions_missing: list[str] = []
    conditions_pending: list[str] = []
    blown_through = False  # Task 5: Breakout-Zone durchgelaufen

    # === PREIS-DISTANZ ===
    price = snap.price
    if trigger.price_op == "in_range":
        # Distanz = 0 wenn IN range, sonst nach unten/oben gemessen.
        # Durchgelaufen-Logik (Task 5) ist richtungsabhängig:
        #   breakout + LONG  → über Obergrenze = durchgelaufen
        #   breakout + SHORT → unter Untergrenze = durchgelaufen (Breakdown)
        if trigger.price_low <= price <= trigger.price_high:
            distance_pct = 0.0
            conditions_met.append(f"Preis {price:.2f} IN-ZONE [{trigger.price_low:.2f}–{trigger.price_high:.2f}]")
        elif price < trigger.price_low:
            distance_pct = (price - trigger.price_low) / trigger.price_low * 100
            if trigger.zone_kind == "breakout" and direction == "SHORT":
                # Short-Breakdown: unter der Untergrenze = durchgelaufen. Die
                # Untergrenze sitzt auf dem R:R-1,35-Kipppunkt (Task 5).
                blown_through = True
                conditions_missing.append(
                    f"Preis {price:.2f} UNTER Breakdown-Zone "
                    f"[{trigger.price_low:.2f}–{trigger.price_high:.2f}] ({distance_pct:+.2f}%) "
                    f"— DURCHGELAUFEN: R:R-Schwelle gerissen, Setup tot"
                )
            else:
                # Long-Breakout noch nicht erfolgt / Pullback-Zone: legitimes Warten.
                conditions_missing.append(
                    f"Preis {price:.2f} unter Range [{trigger.price_low:.2f}–{trigger.price_high:.2f}] ({distance_pct:+.2f}%)"
                )
        else:  # price > price_high
            distance_pct = (price - trigger.price_high) / trigger.price_high * 100
            if trigger.zone_kind == "breakout" and direction == "LONG":
                # Long-Breakout: über der Obergrenze = durchgelaufen. Die
                # Obergrenze sitzt auf dem R:R-1,35-Kipppunkt (Task 5).
                blown_through = True
                conditions_missing.append(
                    f"Preis {price:.2f} ÜBER Breakout-Zone "
                    f"[{trigger.price_low:.2f}–{trigger.price_high:.2f}] ({distance_pct:+.2f}%) "
                    f"— DURCHGELAUFEN: R:R-Schwelle gerissen, Setup tot"
                )
            else:
                # Short-Breakdown noch nicht erfolgt / Pullback-Zone: legitimes Warten.
                conditions_missing.append(
                    f"Preis {price:.2f} über Range [{trigger.price_low:.2f}–{trigger.price_high:.2f}] ({distance_pct:+.2f}%)"
                )

    elif trigger.price_op == ">":
        # Trigger erfüllt wenn Kurs > Schwelle. Distance dann 0 (analog in_range
        # IN-Zone) — "drüber" ist nicht weiter weg, sondern erfüllt.
        if price > trigger.price_single:
            distance_pct = 0.0
            conditions_met.append(f"Preis {price:.2f} > {trigger.price_single:.2f}")
        else:
            distance_pct = (price - trigger.price_single) / trigger.price_single * 100
            conditions_missing.append(
                f"Preis {price:.2f} ≤ {trigger.price_single:.2f} ({distance_pct:+.2f}%)"
            )

    elif trigger.price_op == "<":
        # Spiegel zu ">": erfüllt wenn Kurs < Schwelle.
        if price < trigger.price_single:
            distance_pct = 0.0
            conditions_met.append(f"Preis {price:.2f} < {trigger.price_single:.2f}")
        else:
            distance_pct = (price - trigger.price_single) / trigger.price_single * 100
            conditions_missing.append(
                f"Preis {price:.2f} ≥ {trigger.price_single:.2f} ({distance_pct:+.2f}%)"
            )

    elif trigger.price_op == "approx":
        # Approx: ±2% Toleranz um den Approx-Preis (für is_touch enger ginge,
        # aber 2% deckt Touch-Praxis sauber ab und hält die Bucket-Logik einfach).
        raw_distance = (price - trigger.price_single) / trigger.price_single * 100
        if abs(raw_distance) <= 2.0:
            # Erfüllt → distance auf 0 (analog ">"/"in_range"-IN-Zone)
            distance_pct = 0.0
            touch_label = " (Touch)" if trigger.is_touch else ""
            conditions_met.append(
                f"Preis {price:.2f} ≈ {trigger.price_single:.2f} ({raw_distance:+.2f}%){touch_label}"
            )
        else:
            distance_pct = raw_distance
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
        vol_status = _get_vol_status(snap, config, trigger.vol_multiplier, now_utc_hour)
        mul = snap.volume_multiplier_today
        mul_str = f"{mul:.2f}×" if mul is not None else "n/a"
        threshold = (
            trigger.vol_multiplier
            if trigger.vol_multiplier is not None
            else config["watchlist_trigger_parsing"]["volume_validation"]["require_multiplier"]
        )
        if vol_status == "met":
            conditions_met.append(f"Vol {mul_str} ≥ {threshold:.2f}× ✓")
        elif vol_status == "pending":
            conditions_pending.append(
                f"Vol {mul_str} (Schwelle {threshold:.2f}×) — Tagesvolumen noch offen"
            )
        elif vol_status == "failed":
            conditions_missing.append(f"Vol {mul_str} < {threshold:.2f}×")
        else:  # unknown
            conditions_missing.append("Vol n/a — keine Volumen-Daten")

    if trigger.require_hammer:
        # Reverse-Close-Check (Note #70, 2026-05-19): zwei zulässige Patterns —
        # (a) Klassischer Hammer: langer unterer Docht ≥50% der Range +
        #     Close im oberen Drittel.
        # (b) Bullish-Engulfing: gestrige Kerze bearish, heutige bullish,
        #     heutiger Body schluckt gestrigen Body (Open ≤ prev_close,
        #     Close ≥ prev_open) + Close im oberen Drittel.
        # Anlass: CTSH 19.05.2026 (Open 47,96 / Tief 47,31 / Close 51,40)
        # war klares Bullish-Engulfing am 52W-Tief, fiel aber durch reinen
        # Hammer-Filter (Lower-Wick nur ~16%, Close-Position 100%).
        hammer_match = False
        engulfing_match = False
        match_label = ""

        has_today = (snap.today_close is not None and snap.today_high is not None
                     and snap.today_low is not None and snap.today_open is not None)
        if has_today:
            range_total = snap.today_high - snap.today_low
            close_pos = (snap.today_close - snap.today_low) / range_total if range_total > 0 else 0
            close_in_upper_third = close_pos >= 0.6

            # Pattern (a) — Hammer
            if (snap.today_lower_wick_pct is not None
                    and snap.today_lower_wick_pct >= 50
                    and close_in_upper_third):
                hammer_match = True
                match_label = f"Hammer ✓ (Wick {snap.today_lower_wick_pct:.0f}%, Close-Pos {close_pos:.0%})"

            # Pattern (b) — Bullish-Engulfing (lockere Definition):
            # Heute bullish (Close > Open) + gestern bearish (Close < Open)
            # + heute schließt ÜBER gestern's Open (= heutiger Body schluckt
            # den gestrigen Bearish-Move). Strict Engulfing verlangt zusätzlich
            # today_open ≤ prev_close — das filtert CTSH-Style aus, obwohl der
            # Reversal-Effekt da ist (siehe Note #70).
            elif (snap.prev_open is not None and snap.prev_close is not None
                    and close_in_upper_third):
                today_bullish = snap.today_close > snap.today_open
                prev_bearish = snap.prev_close < snap.prev_open
                close_above_prev_open = snap.today_close > snap.prev_open
                if today_bullish and prev_bearish and close_above_prev_open:
                    engulfing_match = True
                    # Strict-Marker für Diagnose (informativ, kein Filter)
                    strict = snap.today_open <= snap.prev_close
                    qualifier = "strict" if strict else "loose"
                    match_label = (
                        f"Bullish-Engulfing ✓ ({qualifier}: Close {snap.today_close:.2f} "
                        f"> prev_open {snap.prev_open:.2f}, Close-Pos {close_pos:.0%})"
                    )

        if hammer_match or engulfing_match:
            conditions_met.append(match_label)
        elif not has_today:
            conditions_missing.append("keine Reverse-Kerze (keine Tages-OHLC)")
        else:
            # Diagnostik: welches der beiden Patterns ist warum gescheitert?
            details = []
            if snap.today_lower_wick_pct is not None:
                details.append(f"Wick {snap.today_lower_wick_pct:.0f}% (Hammer ≥50)")
            details.append(f"Close-Pos {close_pos:.0%} (≥60% nötig)")
            if snap.prev_open is None or snap.prev_close is None:
                details.append("kein Vortag")
            conditions_missing.append(
                "keine Reverse-Kerze (" + ", ".join(details) + ")"
            )

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
    if blown_through:
        # Durchgelaufener Breakout darf NICHT als very_close/close erscheinen —
        # die R:R-Erosion macht das Setup untauglich. Hart auf "far".
        proximity = "far"

    # Summary kurz formulieren — BEREIT* differenziert "alles okay, nur Vol pending"
    if blown_through:
        summary = (
            f"📛 DURCHGELAUFEN — Kurs {price:.2f} über Breakout-Zonen-Obergrenze "
            f"({distance_pct:+.2f}%), R:R gerissen"
        )
    elif proximity == "in_zone" and not conditions_missing and not conditions_pending:
        summary = "🎯 BEREIT — alle Bedingungen erfüllt"
    elif proximity == "in_zone" and not conditions_missing and conditions_pending:
        summary = f"🎯 BEREIT* — Preis & harte Conditions ok, offen: {', '.join(conditions_pending)}"
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
        conditions_pending=conditions_pending,
        summary=summary,
        blown_through=blown_through,
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
    """Prüft Liquidität + 30d-Move (Earnings-Check folgt in Build-Schritt 1.6)."""
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
