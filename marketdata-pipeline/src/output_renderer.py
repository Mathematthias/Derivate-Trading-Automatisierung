"""
output_renderer.py — Erzeugt die beiden Output-Markdown-Files

MARKETDATA-FULL-{datetime}.md
   Dump aller TickerSnapshots mit Indikatoren. Wird vom Chat/Routinen
   gelesen wenn detaillierte Indikator-Werte gefragt sind.

CANDIDATES-{datetime}.md
   Stufe 1: Watchlist-Trigger-Status (sortiert nach Trigger-Nähe)
   Stufe 2: Universe-Setup-Filter-Treffer
   Plus: Override-Status und REVIEW-WARNINGs

EMA200-MeanRev + Earnings-Erweiterung (2026-05-08, Note #47/#49):
   - MARKETDATA-FULL: 4 neue EMA200-Felder + optional next_earnings_date
   - CANDIDATES + GAMECHANGER-HUNT: EMA200-MEANREV-CANDIDATE-Flag-Sektion und
     PEAD-WINDOW-Flag-Sektion am Anfang der Datei (sehr sichtbar). Beide
     Tiers seit 2026-05-08 — Tier B liefert die echte PEAD-Suche.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import numpy as np

from filter_engine import CandidateMatch, WatchlistResult
from market_data import TickerSnapshot
from state_parser import FilterOverride


# Watchlist-Verfall: ≤ dieser Handelstage bis zum Verfallsdatum → ⏰-Markierung
# (Patch 5, #42). Schwelle gewählt, nicht empirisch — leicht justierbar.
EXPIRY_NEAR_THRESHOLD_HT = 3


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

        # === EMA200-MeanRev-Felder (Note #49, 2026-05-08) ===
        # Output nur, wenn mindestens ein Feld gesetzt ist — verhindert
        # leere Zeile bei Indizes/Krypto/FX, wo die Vorprüfungen oft None sind.
        if (snap.ema200_distance_pct is not None
                or snap.days_since_last_ema200_touch is not None
                or snap.ema200_trend_qualified is not None
                or snap.weekly_higher_highs_lows is not None):
            parts: list[str] = []
            if snap.ema200_distance_pct is not None:
                parts.append(f"Dist={snap.ema200_distance_pct:+.2f}%")
            if snap.days_since_last_ema200_touch is not None:
                parts.append(f"LastTouch={snap.days_since_last_ema200_touch}d")
            if snap.ema200_trend_qualified is not None:
                parts.append(f"TrendQual={'✓' if snap.ema200_trend_qualified else '✗'}")
            if snap.weekly_higher_highs_lows is not None:
                parts.append(f"WeeklyHHHL={'✓' if snap.weekly_higher_highs_lows else '✗'}")
            lines.append(f"- **EMA200-MeanRev:** {' · '.join(parts)}")

        # === Anomaly-Layer V1 (Note #50, 2026-05-15) ===
        # Nur ausgeben wenn mindestens ein Anomaly-Flag aktiv ist — die Roh-
        # Werte (Z-Scores etc.) bleiben implizit im Code. Sichtbar wird der
        # Indikator nur, wenn er kippt.
        if snap.has_any_anomaly:
            lines.append(f"- **Anomalies:** {' · '.join(snap.anomaly_flag_labels())}")

        # === Earnings (optional) ===
        if snap.next_earnings_date or snap.last_earnings_date:
            ep: list[str] = []
            if snap.next_earnings_date:
                ep.append(f"Next={snap.next_earnings_date}")
            if snap.last_earnings_date:
                last_str = f"Last={snap.last_earnings_date}"
                if snap.days_since_last_earnings is not None:
                    last_str += f" ({snap.days_since_last_earnings}d ago)"
                ep.append(last_str)
            lines.append(f"- **Earnings:** {' · '.join(ep)}")

        # === Ex-Dividende (V1.2, Note #67) ===
        if snap.last_ex_div_date:
            last_part = f"Last={snap.last_ex_div_date}"
            details: list[str] = []
            if snap.last_ex_div_days_ago is not None:
                details.append(f"{snap.last_ex_div_days_ago}d ago")
            if snap.last_ex_div_amount is not None:
                details.append(f"Betrag {_fmt_price(snap.last_ex_div_amount)}")
            if details:
                last_part += f" ({', '.join(details)})"
            next_part = (
                f"Next={snap.next_ex_div_date} (geschätzt)"
                if snap.next_ex_div_date else "Next=unbekannt"
            )
            lines.append(f"- **Ex-Div:** {last_part} · {next_part}")

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
    header_title: str = "CANDIDATES",
    enable_setup_class_flags: bool = True,
) -> str:
    """Render die Stufe-1 + Stufe-2-Ergebnisse als Markdown.

    Args:
        snapshots: Optional dict {symbol: TickerSnapshot} für Override-Werte
            UND für die EMA200-MeanRev/PEAD-Window-Flag-Sektionen (siehe unten).
        header_title: Header-Titel der Markdown-Datei. Default "CANDIDATES"
            (Tier-A-Watchlist), für Tier-B-Gamechanger-Lauf "GAMECHANGER-HUNT"
            übergeben.
        enable_setup_class_flags: Wenn True (Default), werden die
            EMA200-MEANREV-CANDIDATE- und PEAD-WINDOW-Flag-Sektionen am Anfang
            der Datei gerendert. Seit 2026-05-08 in beiden Tiers aktiv — auf
            False nur setzen, wenn die Sektionen explizit unterdrückt werden
            sollen.
    """
    lines: list[str] = []
    lines.append(f"# {header_title} — {timestamp.strftime('%Y-%m-%d %H:%M %Z')}")
    lines.append("")

    # === Setup-Klassen-Flag-Sektionen (Note #47/#49, beide Tiers) ===
    # Bewusst sehr sichtbar oben, weil Routinen 7/8 in der ersten Sektion lesen
    # und manuelle Briefing-Lektüre den Watchlist-Block oben erwartet —
    # zusätzliche Setup-Klassen drumherum.
    if enable_setup_class_flags and snapshots:
        flag_lines = _render_setup_class_flags(snapshots)
        if flag_lines:
            lines.extend(flag_lines)
            lines.append("")
            lines.append("---")
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
    today_str = timestamp.strftime("%Y-%m-%d")
    active_overrides = [
        ov for ov in overrides
        if ov.valid_until is None
        or ov.valid_until.isoformat() >= today_str
    ]

    if snapshots is not None:
        watchlist_symbols = {r.entry.symbol for r in watchlist_results}
        universe_match_symbols = {m.symbol for m in universe_matches}

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

    # === LEKTION-4-SL-AUDIT (Note #88/#89/#92, 2026-05-22) ===
    # Sammel-Sektion aller Fix-SL-Verstöße/Grenzfälle über die ganze Watchlist.
    # Der Morgen-Briefing-Lauf (Routine 7) zieht diese als Wartungs-Einzeiler
    # in Bucket 5. ok/skip erscheinen hier NICHT.
    sl_audit: list[tuple[str, str]] = []
    for r in watchlist_results:
        for ts in r.trigger_results:
            if ts.sl_check is None:
                continue
            level, msg = ts.sl_check
            if level in ("verstoss", "grenz"):
                label = f"[{ts.label}] " if ts.label else ""
                sl_audit.append((level, f"**{r.entry.symbol}** {label}— {msg}"))

    if sl_audit:
        lines.append("---")
        lines.append("")
        lines.append("## ⚠️ Lektion-4-SL-Audit")
        lines.append("")
        # Verstöße zuerst, dann Grenzfälle
        for level, marker in (("verstoss", "⚠️"), ("grenz", "⚠")):
            for lv, text in sl_audit:
                if lv == level:
                    lines.append(f"- {marker} {text}")
        lines.append("")

    return "\n".join(lines)


def _render_setup_class_flags(snapshots: dict[str, TickerSnapshot]) -> list[str]:
    """Erzeugt die Setup-Klassen-Sektionen (EMA200-MeanRev + PEAD-Window + Anomaly-Layer V1).

    Sind sehr sichtbar am Dateianfang positioniert. Wenn keine Treffer in einer
    Sektion: die Sektion komplett weglassen. Alle leer → leere Liste zurück.

    PEAD-Window-Definition: last_earnings_date ≤ 5 HT in der Vergangenheit.
    Earnings-Daten kommen nur in den Snapshot, wenn ENV EARNINGS_PULL=1 ist —
    sonst überspringen wir die Sektion still.

    Anomaly-Layer V1 (Note #50, 2026-05-15): vier statistische Detektoren
    (Gap, Volumen-Z, ATR-Z, NR7). Ein Ticker erscheint nur einmal in der
    Sektion, mit aggregierten Flag-Labels. Sortiert nach "Auffälligkeits-
    Stärke" — Tickers mit mehreren parallelen Flags zuerst, dann nach
    Höhe des stärksten Z-Scores.
    """
    out: list[str] = []

    # ----- EMA200-MEANREV-CANDIDATE -----
    ema_candidates: list[TickerSnapshot] = []
    for snap in snapshots.values():
        if snap.ema200_meanrev_qualifies:
            ema_candidates.append(snap)

    if ema_candidates:
        out.append("## 🎯 EMA200-MEANREV-CANDIDATEs (Note #49)")
        out.append("")
        # Sortierung: nach absoluter Distanz aufsteigend (näher = relevanter)
        ema_candidates.sort(key=lambda s: abs(s.ema200_distance_pct or 999))
        for snap in ema_candidates:
            dist = snap.ema200_distance_pct
            days = snap.days_since_last_ema200_touch
            line = (
                f"🎯 EMA200-MEANREV-CANDIDATE | {snap.symbol} | "
                f"Distance {dist:+.2f}% | LastTouch {days}d | Trend ✓"
            )
            out.append(line)
        out.append("")

    # ----- PEAD-WINDOW (nur wenn Earnings-Daten vorhanden) -----
    pead_candidates: list[TickerSnapshot] = []
    for snap in snapshots.values():
        if snap.last_earnings_date is None:
            continue
        if snap.days_since_last_earnings is None:
            continue
        # Übergabe: ≤5 HT in der Vergangenheit
        if 0 <= snap.days_since_last_earnings <= 5:
            pead_candidates.append(snap)

    if pead_candidates:
        if out:
            # Trennlinie zwischen den beiden Setup-Sektionen
            out.append("---")
            out.append("")
        out.append("## 📅 PEAD-WINDOW-Aktive (Note #47-Vorfilter)")
        out.append("")
        # Sortierung: nach Tagen aufsteigend (frischer = relevanter)
        pead_candidates.sort(key=lambda s: s.days_since_last_earnings or 999)
        for snap in pead_candidates:
            line = (
                f"📅 PEAD-WINDOW | {snap.symbol} | "
                f"Earnings {snap.last_earnings_date} | "
                f"{snap.days_since_last_earnings}d ago"
            )
            out.append(line)
        out.append("")

    # ----- ANOMALY-FLAGS (Note #50) -----
    # V1.1: Indizes/Forex/Krypto/Futures rausfiltern — sind Makro-Kontext,
    # keine Trade-Kandidaten. Heuristik per Yahoo-Symbol-Konventionen.
    from market_data import ANOMALY_EXCLUDED_PREFIXES, ANOMALY_EXCLUDED_SUFFIXES

    def _is_excluded_anomaly_symbol(symbol: str) -> bool:
        if any(symbol.startswith(p) for p in ANOMALY_EXCLUDED_PREFIXES):
            return True
        if any(symbol.endswith(s) for s in ANOMALY_EXCLUDED_SUFFIXES):
            return True
        return False

    anomaly_snaps: list[TickerSnapshot] = [
        s for s in snapshots.values()
        if s.has_any_anomaly and not _is_excluded_anomaly_symbol(s.symbol)
    ]

    if anomaly_snaps:
        if out:
            out.append("---")
            out.append("")
        out.append("## ⚡ ANOMALY-FLAGS (Note #50)")
        out.append("")
        # Sortier-Score: Anzahl der Flags (mehr = wichtiger), dann max. |Z|.
        # Damit landen Mehrfach-Anomalien (z.B. Gap + Volumen-Spike) oben.
        def _anomaly_priority(s: TickerSnapshot) -> tuple[int, float]:
            n_flags = len(s.anomaly_flag_labels())
            max_z = max(
                abs(s.atr_zscore_60d or 0),
                abs(s.volume_zscore_60d or 0),
                abs(s.gap_pct or 0) / 2,  # /2 weil Gap-% in anderer Skala als σ
            )
            return (n_flags, max_z)

        anomaly_snaps.sort(key=_anomaly_priority, reverse=True)
        for snap in anomaly_snaps:
            labels = snap.anomaly_flag_labels()
            line = f"⚡ ANOMALY | {snap.symbol} | " + " · ".join(labels)
            out.append(line)
        out.append("")

    # ----- EX-DIV-RECENT (V1.2, Note #67) -----
    # Symbole mit Ex-Tag ≤7 HT zurück — Briefing-Warnung, damit ein Ex-Effekt-
    # Drop nicht als Verkaufsdruck fehlgelesen wird (HEI.DE-Lehre).
    exdiv_snaps: list[TickerSnapshot] = [
        s for s in snapshots.values()
        if s.last_ex_div_days_ago is not None and s.last_ex_div_days_ago <= 7
    ]
    if exdiv_snaps:
        if out:
            out.append("---")
            out.append("")
        out.append("## ⚠️ EX-DIVIDENDE kürzlich (V1.2, Note #67)")
        out.append("")
        exdiv_snaps.sort(key=lambda s: s.last_ex_div_days_ago or 999)
        for snap in exdiv_snaps:
            amt = (
                f" | Betrag {_fmt_price(snap.last_ex_div_amount)}"
                if snap.last_ex_div_amount is not None else ""
            )
            out.append(
                f"⚠️ EX-DIV | {snap.symbol} | ex {snap.last_ex_div_date} | "
                f"{snap.last_ex_div_days_ago}d ago{amt}"
            )
        out.append("")

    return out


def _expiry_flag(expiry_date: Optional[date], today: date) -> Optional[str]:
    """Verfall-Flag für eine Watchlist-Zeile. None wenn kein Verfallsdatum.

    Countdown in Handelstagen (Mo-Fr, ohne Feiertage — konsistent mit der
    '+N HT'-Konvention, mit der die Verfallsdaten im Journal gesetzt werden).
    ≤0 HT → verfallen, ≤EXPIRY_NEAR_THRESHOLD_HT → ⏰-Markierung, sonst Info.
    """
    if expiry_date is None:
        return None
    ht = int(np.busday_count(today, expiry_date))
    iso = expiry_date.isoformat()
    if ht <= 0:
        return f"⛔ verfallen (Verfall {iso})"
    if ht <= EXPIRY_NEAR_THRESHOLD_HT:
        return f"⏰ Verfall in {ht} HT ({iso})"
    return f"Verfall: {iso} ({ht} HT)"


def _render_watchlist_entry(r: WatchlistResult) -> list[str]:
    """Eine Watchlist-Zeile als Markdown."""
    lines: list[str] = []
    snap = r.snapshot
    price_str = _fmt_price(snap.price) if snap else "n/a"

    direction_arrow = "↑" if r.entry.direction == "LONG" else "↓"
    lines.append(
        f"- **{r.entry.symbol}** ({r.entry.direction} {direction_arrow}) — Kurs {price_str}"
    )
    # Verfall-Flag (Patch 5, #42) — Countdown bis zum Verfallsdatum.
    expiry_flag = _expiry_flag(r.entry.expiry_date, date.today())
    if expiry_flag:
        lines.append(f"  - {expiry_flag}")

    for ts in r.trigger_results:
        label_str = f"[{ts.label}] " if ts.label else ""
        lines.append(f"  - {label_str}{ts.summary}")
        for c in ts.conditions_met:
            lines.append(f"    ✓ {c}")
        for c in ts.conditions_pending:
            lines.append(f"    ⏳ {c}")
        for c in ts.conditions_missing:
            lines.append(f"    ✗ {c}")
        # Lektion-4-SL-Guard (Note #88/#89/#92): nur verstoss/grenz zeigen,
        # ok/skip bleiben still (sonst Output-Rauschen).
        if ts.sl_check is not None:
            level, msg = ts.sl_check
            if level == "verstoss":
                lines.append(f"    ⚠️ SL-WARNUNG: {msg}")
            elif level == "grenz":
                lines.append(f"    ⚠ SL-grenzwertig: {msg}")

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
