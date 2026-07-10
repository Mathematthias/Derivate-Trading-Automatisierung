"""BRIEFING-DIGEST v1 — kompaktes, maschinenlesbares Morning-Check-File.

Motivation (2026-07-10): Der Morning Check zog bisher MARKETDATA-FULL-STD
(~45 KB Markdown) + CANDIDATES (~8 KB) als zwei separate Downloads und parste
beide clientseitig per Regex aus dem Drive-base64 zurück. Der Umweg über
Markdown mit Emoji-Bucket-Markern ist die Quelle der decode-Fragilität
(decode_drive_b64) und des Verdeckt-Bereit-Blindflecks (Note #118): beim
Zurückparsen aus Markdown ist nicht sauber unterscheidbar, ob ein in-Zone-
Kandidat wirklich BEREIT ist oder ob noch Bedingungen offen sind.

Dieses Modul rendert stattdessen EIN JSON-File direkt aus den reichen
TickerSnapshot- und WatchlistResult-Objekten — vor dem Markdown-Flatten.
Vorteile:
  - Ein Download statt zwei; ~7-11 KB base64 statt ~70 KB.
  - Kein Emoji/Markdown-Escaping → clientseitig plain json.loads, deterministisch,
    keine stille Trunkierung.
  - Bucket-Zuordnung explizit (eigener in_zone_partial-Bucket + conditions_missing
    als strukturierte Liste) → Note-#118-Blindfleck aufgelöst.
  - universe-Block enthält ALLE Ticker kompakt → ersetzt auch STD, deckt
    offene-Positions-Kurse und Ad-hoc-Lookups ohne Zweit-Pull.

Der Digest ist BEWUSST auf Tier A beschränkt (Watchlist + Kern-Universum).
GAMECHANGER-EU/US und INSIDER-US bleiben separate, lazy nachziehbare Files.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Optional

from output_renderer import classify_watchlist_results

SCHEMA_VERSION = "briefing-digest/v1"

# Makro-Header-Symbole: Indizes/FX/Commodities/Krypto, die im Briefing-Kopf als
# kompakte Lage-Zeile erscheinen (nicht als Trade-Kandidaten). Der Client rendert
# aus dem Schnitt {diese Menge} ∩ {vorhandene Snapshots} den Index-Header.
MACRO_HEADER_SYMBOLS: tuple[str, ...] = (
    "^GDAXI", "^MDAXI", "^SDAXI", "^TECDAX", "^STOXX50E",
    "^GSPC", "^IXIC", "^DJI", "^RUT", "^N225", "^HSI", "^FTSE", "^VIX",
    "BTC-EUR", "ETH-EUR", "SOL-EUR", "BNB-EUR",
    "EURUSD=X", "USDJPY=X", "EURGBP=X",
    "GC=F", "SI=F", "HG=F", "CL=F", "BZ=F", "NG=F",
)

# Buckets, die in den Digest wandern (far/paused/no_data bleiben draußen — nicht
# briefing-relevant, gehen aber in counts ein).
DIGEST_BUCKETS: tuple[str, ...] = (
    "ready", "in_zone_partial", "very_close", "close", "watching", "pending",
)


def _r(x: Optional[float], n: int = 2) -> Optional[float]:
    """Rundet, lässt None durch. Hält das JSON klein und lesbar."""
    if x is None:
        return None
    try:
        return round(float(x), n)
    except (TypeError, ValueError):
        return None


def _stack(snap: Any) -> str:
    """Leitet den EMA-Stack aus ema20/50/200 ab (wie MARKETDATA-FULL)."""
    e20, e50, e200 = snap.ema20, snap.ema50, snap.ema200
    if e20 is None or e50 is None or e200 is None:
        return "neutral"
    if e20 > e50 > e200:
        return "bullish"
    if e20 < e50 < e200:
        return "bearish"
    return "neutral"


def _ext_gate(snap: Any) -> Optional[float]:
    """Extension-Gate (Lektion 22): (Kurs − EMA20) ÷ ATR14. Vorberechnet,
    damit der Chat-Renderer nicht clientseitig rechnen muss."""
    if snap.ema20 is None or snap.atr14 in (None, 0):
        return None
    return _r((snap.price - snap.ema20) / snap.atr14, 2)


def _compact_snap(snap: Any) -> dict[str, Any]:
    """Kompakte Snapshot-Serialisierung — nur briefing-relevante Felder,
    kurze Keys, gerundet. ~180-240 Bytes/Ticker."""
    d: dict[str, Any] = {
        "kurs": _r(snap.price, 4),
        "chg": _r(snap.change_pct, 2),
        "ema20": _r(snap.ema20, 4),
        "ema50": _r(snap.ema50, 4),
        "ema200": _r(snap.ema200, 4),
        "stack": _stack(snap),
        "rsi": _r(snap.rsi14, 1),
        "atr": _r(snap.atr14, 4),
        "ext_gate": _ext_gate(snap),
        "move30d": _r(snap.move_30d_pct, 2),
        "dist52wH": _r(snap.distance_from_52w_high_pct, 2),
        "dist52wL": _r(snap.distance_from_52w_low_pct, 2),
        "ema200_dist": _r(snap.ema200_distance_pct, 2),
        "ema200_touch_d": snap.days_since_last_ema200_touch,
        "weekly_hhll": snap.weekly_higher_highs_lows,
    }
    # Optionale Felder nur setzen, wenn belegt — spart Platz.
    if snap.next_earnings_date:
        d["earn_next"] = snap.next_earnings_date
    if snap.last_earnings_date:
        d["earn_last"] = snap.last_earnings_date
        d["earn_days"] = snap.days_since_last_earnings
    if snap.last_ex_div_days_ago is not None and snap.last_ex_div_days_ago <= 7:
        d["exdiv_d"] = snap.last_ex_div_days_ago
        d["exdiv_amt"] = _r(snap.last_ex_div_amount, 4)
    # OHLC der heutigen Kerze (für Chart-Header-Ableitung ohne Zweit-Pull)
    if snap.today_open is not None:
        d["ohlc"] = [
            _r(snap.today_open, 4), _r(snap.today_high, 4),
            _r(snap.today_low, 4), _r(snap.today_close, 4),
        ]
    if snap.gap_pct is not None:
        d["gap"] = _r(snap.gap_pct, 2)
    if snap.atr_zscore_60d is not None:
        d["atr_z"] = _r(snap.atr_zscore_60d, 2)
    return d


def _best_trigger_status(r: Any) -> Optional[Any]:
    """Wählt den TriggerStatus, der den Bucket bestimmt hat — gleiche Prioritäts-
    logik wie classify_watchlist_results (in_zone-ohne-missing zuerst, sonst
    beste Proximity)."""
    if not r.trigger_results:
        return None
    ready = [ts for ts in r.trigger_results
             if ts.proximity == "in_zone" and not ts.conditions_missing]
    if ready:
        return ready[0]
    order = {"in_zone": 0, "very_close": 1, "close": 2, "watching": 3, "far": 4}
    return min(r.trigger_results, key=lambda ts: order.get(ts.proximity, 5))


def _parsed_trigger_for(entry: Any, label: str) -> Optional[Any]:
    """Findet den ParsedTrigger (mit Preis-Leveln) zum gegebenen Label."""
    triggers = getattr(entry, "triggers", None) or []
    for pt in triggers:
        if pt.label == label:
            return pt
    # Kein Label-Match (z.B. unbenannter Einzeltrigger) → ersten nehmen
    return triggers[0] if triggers else None


def _trigger_levels(pt: Any) -> dict[str, Any]:
    """Serialisiert die handelbaren Level eines ParsedTriggers für den
    Pre-Trade-Plan (Zone, SL, EMA-Referenz, Zusatzbedingungen)."""
    if pt is None:
        return {}
    lvl: dict[str, Any] = {
        "zone_low": _r(pt.price_low, 4),
        "zone_high": _r(pt.price_high, 4),
        "price_single": _r(pt.price_single, 4),
        "op": pt.price_op,
        "ema_ref": pt.ema_ref,
        "sl_value": _r(pt.sl_value, 4),
        "sl_kind": pt.sl_kind,
    }
    # Zusatzbedingungen nur, wenn gesetzt (spart Platz)
    flags: list[str] = []
    if pt.require_bounce:
        flags.append("bounce")
    if pt.require_hammer:
        flags.append("hammer")
    if pt.require_volume:
        flags.append(
            f"vol≥{pt.vol_multiplier}×" if pt.vol_multiplier else "vol≥avg"
        )
    if pt.is_touch:
        flags.append("touch")
    if pt.reverse_tf:
        flags.append(f"reverse:{pt.reverse_tf}")
    if pt.rsi_max is not None:
        flags.append(f"rsi<{pt.rsi_max}")
    if pt.rsi_min is not None:
        flags.append(f"rsi>{pt.rsi_min}")
    if flags:
        lvl["conds"] = flags
    if pt.raw:
        lvl["raw"] = pt.raw
    return {k: v for k, v in lvl.items() if v not in (None, {}, [])}


def _bucket_entry(r: Any) -> dict[str, Any]:
    """Baut den Digest-Eintrag für ein WatchlistResult im jeweiligen Bucket."""
    entry = r.entry
    ts = _best_trigger_status(r)
    out: dict[str, Any] = {
        "symbol": entry.symbol,
        "name": getattr(entry, "name", entry.symbol),
        "direction": entry.direction,
    }
    if getattr(entry, "expiry_date", None):
        out["expiry"] = entry.expiry_date.isoformat()
    if r.note:
        out["note"] = r.note
    if ts is not None:
        out["label"] = ts.label
        out["proximity"] = ts.proximity
        out["distance_pct"] = _r(ts.distance_pct, 2)
        out["blown_through"] = ts.blown_through
        if ts.conditions_met:
            out["met"] = ts.conditions_met
        if ts.conditions_missing:
            out["missing"] = ts.conditions_missing
        if ts.conditions_pending:
            out["pending"] = ts.conditions_pending
        if ts.summary:
            out["summary"] = ts.summary
        if ts.sl_check:
            out["sl_check"] = list(ts.sl_check)  # tuple → JSON-Liste
        levels = _trigger_levels(_parsed_trigger_for(entry, ts.label))
        if levels:
            out["trigger"] = levels
    return out


def _setup_class_flags(snapshots: dict[str, Any]) -> dict[str, list[Any]]:
    """Symbol-Listen der Setup-Klassen (spiegelt _render_setup_class_flags-
    Kriterien, aber als strukturierte Daten statt Markdown)."""
    try:
        from market_data import (
            ANOMALY_EXCLUDED_PREFIXES, ANOMALY_EXCLUDED_SUFFIXES,
        )
    except Exception:
        ANOMALY_EXCLUDED_PREFIXES, ANOMALY_EXCLUDED_SUFFIXES = (), ()

    def _excluded(sym: str) -> bool:
        return (any(sym.startswith(p) for p in ANOMALY_EXCLUDED_PREFIXES)
                or any(sym.endswith(s) for s in ANOMALY_EXCLUDED_SUFFIXES))

    ema200: list[dict[str, Any]] = []
    pead: list[dict[str, Any]] = []
    anomaly: list[dict[str, Any]] = []
    for snap in snapshots.values():
        if getattr(snap, "ema200_meanrev_qualifies", False):
            ema200.append({"symbol": snap.symbol,
                           "dist": _r(snap.ema200_distance_pct, 2),
                           "touch_d": snap.days_since_last_ema200_touch})
        if (snap.last_earnings_date and snap.days_since_last_earnings is not None
                and 0 <= snap.days_since_last_earnings <= 5):
            pead.append({"symbol": snap.symbol,
                         "earn": snap.last_earnings_date,
                         "days": snap.days_since_last_earnings})
        if getattr(snap, "has_any_anomaly", False) and not _excluded(snap.symbol):
            anomaly.append({"symbol": snap.symbol,
                            "flags": snap.anomaly_flag_labels()})
    ema200.sort(key=lambda d: abs(d["dist"] if d["dist"] is not None else 999))
    pead.sort(key=lambda d: d["days"] if d["days"] is not None else 999)
    return {"ema200_meanrev": ema200, "pead_window": pead, "anomaly": anomaly}


def build_briefing_digest(
    snapshots: dict[str, Any],
    watchlist_results: list[Any],
    universe_matches: list[Any],
    overrides: list[Any],
    timestamp: datetime,
    expiry_window_days: int = 14,
) -> str:
    """Baut den BRIEFING-DIGEST als JSON-String.

    Args:
        snapshots: {symbol: TickerSnapshot} — alle Tier-A-Ticker.
        watchlist_results: Ergebnis von check_watchlist (Bucket-Quelle).
        universe_matches: CandidateMatch-Liste (Setup-Klassen-Treffer).
        overrides: FilterOverride-Liste (priority/wait_for/disqualified).
        timestamp: Pipeline-Laufzeit (tz-aware).
        expiry_window_days: Watchlist-Einträge mit Verfall ≤ N Kalendertagen
            werden im expiry-Block gelistet.

    Returns:
        JSON-String (UTF-8, ensure_ascii=False), fertig für write_json_file.
    """
    buckets_raw = classify_watchlist_results(watchlist_results)
    today = timestamp.date()

    buckets: dict[str, list[dict[str, Any]]] = {}
    for name in DIGEST_BUCKETS:
        rows = buckets_raw.get(name, [])
        if rows:
            buckets[name] = [_bucket_entry(r) for r in rows]

    # Watchlist-Verfall: alle Einträge mit expiry_date ≤ Fenster
    expiry: list[dict[str, Any]] = []
    for r in watchlist_results:
        exp: Optional[date] = getattr(r.entry, "expiry_date", None)
        if exp is None:
            continue
        days_left = (exp - today).days
        if days_left <= expiry_window_days:
            expiry.append({
                "symbol": r.entry.symbol,
                "expiry": exp.isoformat(),
                "tage_rest": days_left,
            })
    expiry.sort(key=lambda d: d["tage_rest"])

    # Overrides kompakt (priority/wait_for/disqualified) — für Bucket-Kontext
    ovr: list[dict[str, Any]] = []
    for o in overrides:
        row = {
            "symbol": getattr(o, "symbol", None),
            "type": getattr(o, "override_type", None),
            "reason": getattr(o, "reason", None),
        }
        vu = getattr(o, "valid_until", None)
        if vu is not None:
            row["valid_until"] = vu.isoformat() if hasattr(vu, "isoformat") else vu
        ovr.append(row)

    # Position-Monitore: passive Watchlist-Einträge, die journal_utils beim Kauf
    # anlegt (Richtung "POSITION-MONITOR (…)"), damit offene Positionen im
    # Universum bleiben und weiter Indikatoren bekommen. Wir heben sie in einen
    # eigenen Block, damit Bucket 6 (offene Positionen) im Chat sofort da ist.
    # Die TIW-Schwelle selbst steht NICHT hier — sie lebt im Journal (bewusst
    # parser-sicher, kein Entry) und wird clientseitig gegen den Kurs geprüft.
    position_monitors: list[dict[str, Any]] = []
    for r in watchlist_results:
        direction = (getattr(r.entry, "direction", "") or "").upper()
        name = getattr(r.entry, "name", "") or ""
        if direction.startswith("POSITION-MONITOR") or "[MONITOR" in name.upper():
            row = {"symbol": r.entry.symbol, "name": name}
            if getattr(r.entry, "direction", None):
                row["label"] = r.entry.direction
            if r.note:
                row["note"] = r.note
            position_monitors.append(row)

    universe = {sym: _compact_snap(snap) for sym, snap in snapshots.items()}
    macro_present = [s for s in MACRO_HEADER_SYMBOLS if s in snapshots]

    digest: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "generated": timestamp.isoformat(),
        "tier": "A",
        "counts": {
            "universe": len(universe),
            **{name: len(buckets_raw.get(name, [])) for name in
               ("ready", "in_zone_partial", "very_close", "close",
                "watching", "pending", "paused", "no_data", "far")},
        },
        "macro": macro_present,
        "universe": universe,
        "buckets": buckets,
        "setup_class_flags": _setup_class_flags(snapshots),
        "position_monitors": position_monitors,
        "overrides": ovr,
        "watchlist_expiry": expiry,
    }
    return json.dumps(digest, ensure_ascii=False, separators=(",", ":"))
