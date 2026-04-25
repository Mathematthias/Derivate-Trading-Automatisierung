"""
output_renderer.py — Erzeugt die beiden Output-Markdown-Files

MARKETDATA-FULL-{datetime}.md
   Dump aller TickerSnapshots mit Indikatoren. Wird vom Chat/Routinen
   gelesen wenn detaillierte Indikator-Werte gefragt sind.

CANDIDATES-{datetime}.md
   Stufe 1: Watchlist-Trigger-Status (sortiert nach Trigger-Nähe)
   Stufe 2: Universe-Setup-Filter-Treffer
   Plus: Override-Status und REVIEW-WARNINGs
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from filter_engine import CandidateMatch, WatchlistResult
from market_data import TickerSnapshot
from state_parser import FilterOverride


# ============================================================
# MARKETDATA-FULL.md
# ============================================================

def render_marketdata_full(
    snapshots: dict[str, TickerSnapshot],
    timestamp: datetime,
) -> str:
    """Vollständiger Indikator-Dump aller Snapshots."""
    lines: list[str] = []
    lines.append(f"# MARKETDATA-FULL — {timestamp.strftime('%Y-%m-%d %H:%M %Z')}")
    lines.append("")
    lines.append(f"**Source:** yfinance | **Ticker erfolgreich:** {len(snapshots)}")
    lines.append("")

    # Sortiert nach Symbol
    for symbol in sorted(snapshots.keys()):
        snap = snapshots[symbol]
        lines.append(f"## {symbol}")
        lines.append("")
        lines.append(f"- **Kurs:** {_fmt_price(snap.price)}  ({_fmt_pct(snap.change_pct)})")

        if snap.ema20 is not None or snap.ema50 is not None or snap.ema200 is not None:
            ema_parts = []
            if snap.ema20 is not None:
                ema_parts.append(f"EMA20={_fmt_price(snap.ema20)}")
            if snap.ema50 is not None:
                ema_parts.append(f"EMA50={_fmt_price(snap.ema50)}")
            if snap.ema200 is not None:
                ema_parts.append(f"EMA200={_fmt_price(snap.ema200)}")
            stack = ""
            if snap.has_bullish_stack:
                stack = " (bullish-Stack ↑)"
            elif snap.has_bearish_stack:
                stack = " (bearish-Stack ↓)"
            lines.append(f"- **EMAs:** {' · '.join(ema_parts)}{stack}")

        if snap.rsi14 is not None:
            lines.append(f"- **RSI-14:** {snap.rsi14:.1f}")

        if snap.atr14 is not None:
            lines.append(f"- **ATR-14:** {snap.atr14:.3f}")

        if snap.move_30d_pct is not None:
            lines.append(f"- **30d-Move:** {_fmt_pct(snap.move_30d_pct)}")

        if snap.high_52w is not None and snap.low_52w is not None:
            lines.append(
                f"- **52W-Range:** {_fmt_price(snap.low_52w)} – {_fmt_price(snap.high_52w)}  "
                f"(High-Distanz {_fmt_pct(snap.distance_from_52w_high_pct)}, "
                f"Low-Distanz {_fmt_pct(snap.distance_from_52w_low_pct)})"
            )

        if snap.high_20d is not None and snap.low_20d is not None:
            lines.append(f"- **20d-Range:** {_fmt_price(snap.low_20d)} – {_fmt_price(snap.high_20d)}")

        if snap.volume_avg_20d is not None:
            mul = ""
            if snap.volume_multiplier_today is not None:
                mul = f" (heute {snap.volume_multiplier_today:.2f}× avg)"
            lines.append(
                f"- **Volumen:** Avg-20d {snap.volume_avg_20d:,} Stk · "
                f"{snap.volume_eur_avg_20d:,.0f} EUR{mul}"
            )

        lines.append("")

    return "\n".join(lines)


# ============================================================
# CANDIDATES.md
# ============================================================

def render_candidates(
    watchlist_results: list[WatchlistResult],
    universe_matches: list[CandidateMatch],
    overrides: list[FilterOverride],
    timestamp: datetime,
    snapshots: Optional[dict] = None,
) -> str:
    """Render die Stufe-1 + Stufe-2-Ergebnisse als Markdown.

    Args:
        snapshots: Optional dict {symbol: TickerSnapshot} für Override-Werte,
            die weder in Stufe 1 noch Stufe 2 erscheinen aber im STATE als
            priority_long/priority_short markiert sind.
    """
    lines: list[str] = []
    lines.append(f"# CANDIDATES — {timestamp.strftime('%Y-%m-%d %H:%M %Z')}")
    lines.append("")

    # === STUFE 1: WATCHLIST-STATUS ===
    lines.append("## Stufe 1 — Watchlist-Trigger-Status")
    lines.append("")

    # Bereit-Treffer (in_zone + alle Conditions met)
    ready: list[WatchlistResult] = []
    in_zone_partial: list[WatchlistResult] = []
    very_close: list[WatchlistResult] = []
    close_list: list[WatchlistResult] = []
    watching: list[WatchlistResult] = []
    pending: list[WatchlistResult] = []
    paused: list[WatchlistResult] = []
    no_data: list[WatchlistResult] = []
    far: list[WatchlistResult] = []

    for r in watchlist_results:
        if r.overall_status == "pending":
            pending.append(r)
            continue
        if r.overall_status == "paused":
            paused.append(r)
            continue
        if r.overall_status == "no_data":
            no_data.append(r)
            continue

        # Trigger-Auswertung kategorisieren
        best_proximity = "far"
        best_ready = False
        for ts in r.trigger_results:
            if ts.proximity == "in_zone" and not ts.conditions_missing:
                best_ready = True
                best_proximity = "in_zone"
                break
            if ts.proximity == "in_zone" and best_proximity not in ("in_zone",):
                best_proximity = "in_zone"
            elif ts.proximity == "very_close" and best_proximity not in ("in_zone", "very_close"):
                best_proximity = "very_close"
            elif ts.proximity == "close" and best_proximity not in ("in_zone", "very_close", "close"):
                best_proximity = "close"
            elif ts.proximity == "watching" and best_proximity == "far":
                best_proximity = "watching"

        if best_ready:
            ready.append(r)
        elif best_proximity == "in_zone":
            in_zone_partial.append(r)
        elif best_proximity == "very_close":
            very_close.append(r)
        elif best_proximity == "close":
            close_list.append(r)
        elif best_proximity == "watching":
            watching.append(r)
        else:
            far.append(r)

    if ready:
        lines.append("### 🎯 BEREIT — Trigger erfüllt, Chart-Validierung empfohlen")
        lines.append("")
        for r in ready:
            lines.extend(_render_watchlist_entry(r))
        lines.append("")

    if in_zone_partial:
        lines.append("### ⚠️ In Zone, aber Bedingungen offen")
        lines.append("")
        for r in in_zone_partial:
            lines.extend(_render_watchlist_entry(r))
        lines.append("")

    if very_close:
        lines.append("### 📍 Sehr nah am Trigger (≤2%)")
        lines.append("")
        for r in very_close:
            lines.extend(_render_watchlist_entry(r))
        lines.append("")

    if close_list:
        lines.append("### Nah am Trigger (≤5%)")
        lines.append("")
        for r in close_list:
            lines.extend(_render_watchlist_entry(r))
        lines.append("")

    if watching:
        lines.append("### Auf Radar (≤10%)")
        lines.append("")
        for r in watching:
            lines.extend(_render_watchlist_entry(r))
        lines.append("")

    if pending:
        lines.append("### 📅 Pending (Datum-Constraint)")
        lines.append("")
        for r in pending:
            lines.append(f"- **{r.entry.symbol}** ({r.entry.direction}) — {r.note}")
        lines.append("")

    if paused:
        lines.append("### ⏸ Paused (Bedingung temporär nicht da)")
        lines.append("")
        for r in paused:
            lines.append(f"- **{r.entry.symbol}** ({r.entry.direction}) — {r.entry.status_note}")
        lines.append("")

    if far:
        lines.append("### 🔍 Passive (>10% entfernt)")
        lines.append("")
        for r in far:
            # Sind alle Trigger leer (kein konkreter Trigger im STATE)?
            all_empty = all(
                ts.summary.startswith("ohne konkreten Trigger")
                for ts in r.trigger_results
            )
            if all_empty:
                lines.append(
                    f"- **{r.entry.symbol}** ({r.entry.direction}) — "
                    f"Status `{r.entry.status}`, kein konkreter Trigger im STATE"
                )
            else:
                best_dist = min(
                    (ts.distance_pct for ts in r.trigger_results
                     if not ts.summary.startswith("ohne konkreten Trigger")),
                    key=abs,
                    default=0.0,
                )
                lines.append(
                    f"- **{r.entry.symbol}** ({r.entry.direction}) — Distanz "
                    f"{best_dist:+.1f}%"
                )
        lines.append("")

    if no_data:
        lines.append("### ⚠️ Keine Daten")
        lines.append("")
        for r in no_data:
            lines.append(f"- **{r.entry.symbol}** ({r.entry.direction}) — {r.note}")
        lines.append("")

    # === STUFE 2: UNIVERSE-MATCHES ===
    lines.append("---")
    lines.append("")
    lines.append("## Stufe 2 — Neue Kandidaten aus Universe")
    lines.append("")

    if not universe_matches:
        lines.append("(heute keine Treffer)")
        lines.append("")
    else:
        # Gruppiert nach Bucket
        bucket_map: dict[str, list[CandidateMatch]] = {}
        for m in universe_matches:
            bucket_map.setdefault(m.bucket, []).append(m)

        bucket_titles = {
            "long_trend_pullback": "Long-Trend-Pullback",
            "short_trend_pullback": "Short-Trend-Pullback",
            "breakout_long": "Breakout Long",
            "breakdown_short": "Breakdown Short",
            "reversal_long": "Reversal Long",
            "reversal_short": "Reversal Short",
        }

        for bucket in [
            "long_trend_pullback", "breakout_long", "reversal_long",
            "short_trend_pullback", "breakdown_short", "reversal_short",
        ]:
            ms = bucket_map.get(bucket, [])
            if not ms:
                continue
            lines.append(f"### {bucket_titles.get(bucket, bucket)}")
            lines.append("")
            for m in ms:
                lines.append(f"- {m.summary}")
            lines.append("")

    # === OVERRIDE-WERTE mit Snapshot-Daten ===
    # Werte die priority_long/priority_short Override haben, aber NICHT in der
    # Watchlist sind und keinen Universe-Match haben — z.B. BTC-EUR (Position
    # Override). Damit man sie nicht aus Versehen vergisst.
    today_str = timestamp.strftime("%Y-%m-%d")
    active_overrides = [
        ov for ov in overrides
        if ov.valid_until is None
        or ov.valid_until.isoformat() >= today_str
    ]

    if snapshots is not None:
        watchlist_symbols = {r.entry.symbol for r in watchlist_results}
        universe_match_symbols = {m.symbol for m in universe_matches}

        # Welche Override-Werte sind nicht in Stufe 1 oder 2?
        override_priority = [
            ov for ov in active_overrides
            if ov.override_type in ("priority_long", "priority_short")
            and ov.symbol not in watchlist_symbols
            and ov.symbol not in universe_match_symbols
            and ov.symbol in snapshots
        ]

        if override_priority:
            lines.append("---")
            lines.append("")
            lines.append("## Override-Werte (priority_long / priority_short)")
            lines.append("")
            for ov in override_priority:
                snap = snapshots[ov.symbol]
                direction = "↑" if ov.override_type == "priority_long" else "↓"
                ema_str = ""
                if snap.ema20 is not None:
                    ema_str = f" EMA20={_fmt_price(snap.ema20)}"
                rsi_str = ""
                if snap.rsi14 is not None:
                    rsi_str = f" RSI={snap.rsi14:.0f}"
                move_str = ""
                if snap.move_30d_pct is not None:
                    move_str = f" 30d={snap.move_30d_pct:+.1f}%"
                lines.append(
                    f"- **{ov.symbol}** ({direction}) — Kurs {_fmt_price(snap.price)} "
                    f"({_fmt_pct(snap.change_pct)}){ema_str}{rsi_str}{move_str}"
                )
                lines.append(f"  - _Grund: {ov.reason}_")
            lines.append("")

    # === ACTIVE OVERRIDES (übersicht aller noch gültigen) ===
    if active_overrides:
        lines.append("---")
        lines.append("")
        lines.append("## Aktive Filter-Overrides")
        lines.append("")
        for ov in active_overrides:
            until = ov.valid_until.isoformat() if ov.valid_until else "∞"
            lines.append(f"- **{ov.symbol}** [{ov.override_type}] — {ov.reason} (gültig bis {until})")
        lines.append("")

    return "\n".join(lines)


def _render_watchlist_entry(r: WatchlistResult) -> list[str]:
    """Eine Watchlist-Zeile als Markdown."""
    lines: list[str] = []
    snap = r.snapshot
    price_str = _fmt_price(snap.price) if snap else "n/a"

    direction_arrow = "↑" if r.entry.direction == "LONG" else "↓"
    lines.append(
        f"- **{r.entry.symbol}** ({r.entry.direction} {direction_arrow}) — Kurs {price_str}"
    )

    for ts in r.trigger_results:
        label_str = f"[{ts.label}] " if ts.label else ""
        lines.append(f"  - {label_str}{ts.summary}")
        for c in ts.conditions_met:
            lines.append(f"    ✓ {c}")
        for c in ts.conditions_missing:
            lines.append(f"    ✗ {c}")

    if r.entry.status_note:
        lines.append(f"  - _Note: {r.entry.status_note}_")

    return lines


def _fmt_price(p: Optional[float]) -> str:
    if p is None:
        return "n/a"
    if p < 100:
        return f"{p:.2f}"
    if p < 10_000:
        return f"{p:.1f}"
    return f"{p:.0f}"


def _fmt_pct(p: Optional[float]) -> str:
    if p is None:
        return "n/a"
    return f"{p:+.2f}%"
