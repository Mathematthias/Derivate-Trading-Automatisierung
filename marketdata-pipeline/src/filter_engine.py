"""
filter_engine.py — Zweistufige Filter-Engine

Stufe 1: Watchlist-Trigger-Status-Check
   Für jeden Watchlist-Eintrag aus dem STATE wird geprüft, ob seine
   konkreten Trigger-Bedingungen erfüllt sind. Output ist ein Status:
   - in_zone: Kurs IN der Trigger-Zone, alle Bedingungen erfüllt
   - very_close / close / watching / far: Distanz-Buckets, ATR-normalisiert
     (Vielfache von ATR14-1D: <=0.75 / <=1.5 / <=3.0 / >3.0). Fallback auf
     rohe %-Schwellen (2/5/10) wenn ATR fehlt. distance_pct bleibt als %
     erhalten (Anzeige), distance_atr trägt das ATR-Vielfache.
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
    resolve_relative_zone,
)

logger = logging.getLogger(__name__)


# ============================================================
# KONSTANTEN
# ============================================================

# Lektion-4-SL-Guard (Note #88/#89/#92, 2026-05-22): Mindest-SL-Abstand zur
# ungünstigen Zonenkante, gemessen in ATR(14). Sind keine Tuning-Knöpfe,
# sondern methodisch fixe Werte (R:R-1,35-Kipppunkt aus Lektion 4/17) —
# darum Modul-Konstanten statt filter_config.yaml.
SL_LEKTION4_HARD_RATIO = 1.35   # ratio < 1,35 → Verstoß
SL_LEKTION4_WARN_RATIO = 1.5    # 1,35 ≤ ratio < 1,5 → grenzwertig


# ============================================================
# DATENMODELLE FÜR OUTPUT
# ============================================================

@dataclass
class TriggerStatus:
    """Auswertung eines einzelnen Triggers (A, B, ...) eines Watchlist-Eintrags."""

    label: str  # "A", "B", oder ""
    proximity: str  # "in_zone" | "very_close" | "close" | "watching" | "far"
    distance_pct: float  # signed: negativ = drunter, positiv = drüber
    distance_atr: Optional[float] = None  # signed Distanz in ATR14-Vielfachen (None wenn ATR fehlt)
    conditions_met: list[str] = field(default_factory=list)  # erfüllte Sub-Bedingungen
    conditions_missing: list[str] = field(default_factory=list)  # fehlende (hart durchgefallen)
    conditions_pending: list[str] = field(default_factory=list)  # noch offen (Tagesvolumen, etc.)
    summary: str = ""  # Kurzfassung für Output
    blown_through: bool = False  # Task 5: Breakout-Zone durchgelaufen (Kurs über Obergrenze)
    # Lektion-4-SL-Guard (Note #88/#89/#92, 2026-05-22): (level, msg) mit
    # level ∈ {'verstoss','grenz','ok','skip'}. None nur wenn der Trigger leer
    # ist. Rein diagnostisch — ändert KEIN Bucket-Verhalten.
    sl_check: Optional[tuple[str, str]] = None


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
    today: Optional[date] = None,
) -> str:
    """Bewertet die Volumen-Bedingung mit 4 Stati.

    Returns:
        'met'     — Tagesvolumen erreicht (oder bereits über) die Schwelle.
        'failed'  — Volumen unter Schwelle UND das Tagesvolumen ist final:
                    entweder nach der Hard-Evaluation-Stunde, ODER der letzte
                    Balken stammt aus einer bereits abgeschlossenen Sitzung
                    (Wochenend-/Feiertags-Lauf, Montag früh mit Freitags-Balken).
        'pending' — Volumen unter Schwelle, letzter Balken ist der heutige UND
                    vor der Hard-Evaluation-Stunde (Volumen kann sich noch füllen).
        'unknown' — Keine Volumen-Daten verfügbar.

    Hintergrund: Wenn die Pipeline tagsüber läuft (z.B. 14:30 CEST), ist das
    Tagesvolumen noch nicht endgültig. Eine harte "Vol fehlt"-Ablehnung
    blockiert dann unnötig den BEREIT-Bucket, obwohl das Volumen bis Tagesende
    noch ankommen kann. Erst nach `hard_evaluation_utc_hour` (Default 20 UTC
    = 21/22 CEST nach US-Close) wird "fehlend" zu "failed".

    Handelstags-Check (2026-05-24): Die Uhrzeit allein reicht nicht. Ein Lauf
    am Wochenende oder Feiertag liegt immer "vor 20 UTC" relativ zum nächsten
    Handelstag und würde fälschlich 'pending' liefern, obwohl der letzte Balken
    (z.B. Freitag) ein *finales* Volumen trägt — das blähte den BEREIT-Bucket
    auf. Daher: liegt `snap.last_bar_date` vor `today`, ist die gemessene
    Sitzung abgeschlossen → 'failed' statt 'pending'. Ein Nicht-Handelstag
    erzeugt schlicht keinen neuen Balken, der Datums-Vergleich deckt Wochenende
    und Feiertage damit implizit ab — ein expliziter Handelskalender entfällt.
    `today` optional für Backward-Compat: None → reine Uhrzeit-Logik wie zuvor.
    """
    if snap.volume_multiplier_today is None:
        return "unknown"

    threshold = vol_multiplier if vol_multiplier is not None else cfg["watchlist_trigger_parsing"]["volume_validation"]["require_multiplier"]
    if snap.volume_multiplier_today >= threshold:
        return "met"

    # Unter Schwelle. 'pending' (= warte auf mehr Volumen) ist nur plausibel,
    # wenn das gemessene Volumen überhaupt noch wachsen kann — also der letzte
    # Balken der heutige ist und die Sitzung noch läuft. Liegt der letzte
    # Balken vor heute (Wochenend-/Feiertags-Lauf, oder Montag früh mit
    # Freitags-Balken), ist die Sitzung abgeschlossen und das Volumen final.
    if today is not None and snap.last_bar_date is not None:
        # last_bar_date ist ISO YYYY-MM-DD; today kann date oder datetime sein.
        if snap.last_bar_date < today.isoformat()[:10]:
            return "failed"

    # Letzter Balken ist heute (oder Datum unbekannt) → Uhrzeit entscheidet.
    hard_hour = cfg["watchlist_trigger_parsing"].get("hard_evaluation_utc_hour", 20)
    if now_utc_hour is None:
        # Kein Zeit-Kontext vorhanden → konservativer Default: failed (altes Verhalten)
        return "failed"
    if now_utc_hour >= hard_hour:
        return "failed"
    return "pending"


# ------------------------------------------------------------------
# Carry-Forward bestätigter Tagesschluss-Breakouts (Note #110, 2026-05-29)
# ------------------------------------------------------------------
# Bug: Ein Daily-Close-Breakout, der im Abendlauf NACH Markt-Schluss als
# "BEREIT — alle Bedingungen erfüllt" (volles Tagesvolumen) bestätigt wurde,
# wird am Folgetag-Morgen gegen die WERDENDE (partielle) Tageskerze neu
# bewertet → Preis = Teilbalken-Kurs, Volumen resettet auf Intraday → der
# bestätigte Breakout fällt zurück auf BEREIT*/very_close und ist im
# Morning-Check unsichtbar. Fix: Für reine Close-Breakout-Trigger werden
# Preis UND Volumen gegen die zuletzt ABGESCHLOSSENE Tageskerze (prev_*)
# evaluiert, solange die aktuelle Sitzung noch läuft. Selbst-invalidierend:
# schließt eine Tageskerze zurück durch den Trigger, zeigt prev_close das.

def _is_close_breakout_trigger(trigger: ParsedTrigger) -> bool:
    """True für reine Daily-Close-Breakout-Trigger (Preis-Schwelle >/< oder
    Breakout-Zone) OHNE Reverse-Kerzen-/Bounce-Anforderung.

    Nur diese profitieren vom Carry-Forward: Ihre Bestätigung ist ein
    Tagesschluss-Ereignis. Pullback-/Touch-/Reversal-Trigger (require_hammer,
    require_bounce, approx-Touch) hängen an der Live-/Tageskerze und bleiben
    unangetastet — für sie ist die werdende Kerze die richtige Bezugsgröße.
    """
    if trigger.require_hammer or trigger.require_bounce:
        return False
    if trigger.price_op in (">", "<"):
        return True
    if trigger.price_op == "in_range" and trigger.zone_kind == "breakout":
        return True
    return False


def _last_bar_is_forming(
    snap: TickerSnapshot,
    today: Optional[date],
    now_utc_hour: Optional[int],
    hard_hour: int,
) -> bool:
    """True, wenn der letzte OHLC-Balken die heute noch laufende (nicht finale)
    Sitzung ist — dann sind `snap.price`/`volume_multiplier_today` partielle
    Intraday-Werte. Spiegelbild der "Sitzung final"-Logik aus _get_vol_status.

    Ohne Zeit-Kontext (today/now_utc_hour None) → False (konservativ: Live-Werte
    wie bisher, Backward-Compat). Letzter Balken aus abgeschlossener Sitzung
    (last_bar_date < today) → False (final). last_bar_date == today und vor
    Hard-Hour → True (Sitzung läuft).
    """
    if today is None or now_utc_hour is None or snap.last_bar_date is None:
        return False
    if snap.last_bar_date < today.isoformat()[:10]:
        return False
    return now_utc_hour < hard_hour


def _live_back_through_trigger(trigger: ParsedTrigger, snap: TickerSnapshot) -> bool:
    """Carry-Forward-Begleiter: ist der LIVE-Intraday-Kurs zurück durch den
    Trigger gelaufen (LONG: unter, SHORT: über)? Dann ist der Vortags-Breakout
    zwar bestätigt, aber am Verpuffen → Failing-Breakout-Watch im Summary.
    """
    live = snap.price
    if live is None:
        return False
    if trigger.price_op == ">" and trigger.price_single is not None:
        return live <= trigger.price_single
    if trigger.price_op == "<" and trigger.price_single is not None:
        return live >= trigger.price_single
    if trigger.price_op == "in_range" and trigger.price_low is not None and trigger.price_high is not None:
        return live < trigger.price_low or live > trigger.price_high
    return False


def check_sl_lektion4(
    trigger: ParsedTrigger,
    snap: Optional[TickerSnapshot],
    direction: str,
) -> tuple[str, str]:
    """Prüft den SL-Abstand eines Triggers gegen ATR(14) — Lektion-4-Guard.

    Note #88/#89/#92 (2026-05-22), Lektion 17. Hintergrund: Ein über die
    ganze Trigger-Zone fixer SL erfüllt die 1,5×ATR-Regel nur an einem Punkt.
    An der für die Handelsrichtung ungünstigen Zonenkante (Long: Untergrenze,
    Short: Obergrenze) wird der Abstand minimal — dort wird der Fix-SL zu eng.
    Reine Zonenbreite ist KEIN ausreichendes Kriterium (Befund CHKP-A: Zone
    1,11×ATR breit, Fix-SL trotzdem nur 0,93×ATR an der Untergrenze).

    Der Check ist rein diagnostisch: er flaggt, ändert aber kein Bucket.

    Returns:
        (level, msg) mit level ∈ {'ok','grenz','verstoss','skip'}.
        - 'ok'       — entry-relativ ODER Fix-SL ≥ 1,5×ATR.
        - 'grenz'    — Fix-SL 1,35–1,5×ATR: grenzwertig.
        - 'verstoss' — Fix-SL < 1,35×ATR: Lektion-4-Verstoß.
        - 'skip'     — nicht prüfbar (Pattern-SL, ATR fehlt, keine Preis-Zone).
    """
    if trigger.sl_kind == "entry_relativ":
        return ("ok", "SL entry-relativ — Lektion-4-konform per Konstruktion")
    if trigger.sl_kind in (None, "pattern"):
        return (
            "skip",
            "SL nicht numerisch (Pattern/Sonder-Konvention) — manueller Check",
        )

    # sl_kind == 'fix' → numerisches Level, sl_value gesetzt
    if trigger.sl_value is None:
        return ("skip", "Fix-SL ohne Wert — manueller Check")

    atr = getattr(snap, "atr14", None) if snap is not None else None
    if atr is None or atr <= 0:
        return ("skip", "ATR-Quelle fehlt (Ticker off-universe) — manueller Check")

    # Ungünstige Zonenkante bestimmen
    if trigger.price_op == "in_range":
        if trigger.price_low is None or trigger.price_high is None:
            return ("skip", "Zonenkante unbestimmt — manueller Check")
        # Long kauft tief → Untergrenze ist worst case (SL am nächsten).
        # Short verkauft hoch → Obergrenze ist worst case.
        kante = trigger.price_low if direction == "LONG" else trigger.price_high
    elif trigger.price_op in (">", "<", "approx"):
        # Pattern-/Schwellen-Trigger ohne echte Zone: die Schwelle ist die Kante.
        if trigger.price_single is None:
            return ("skip", "Trigger-Schwelle unbestimmt — manueller Check")
        kante = trigger.price_single
    else:
        return ("skip", "kein Preis-Trigger — SL-Abstand nicht prüfbar")

    abstand = abs(kante - trigger.sl_value)
    ratio = abstand / atr

    if ratio < SL_LEKTION4_HARD_RATIO:
        return (
            "verstoss",
            f"Fix-SL nur {ratio:.2f}×ATR an Zonenkante {kante:.2f} "
            f"(<1,35) — Lektion-4-Verstoß, SL entry-relativ umstellen",
        )
    if ratio < SL_LEKTION4_WARN_RATIO:
        return (
            "grenz",
            f"Fix-SL {ratio:.2f}×ATR an Zonenkante {kante:.2f} "
            f"(1,35–1,5) — grenzwertig, entry-relativ empfohlen",
        )
    return ("ok", f"Fix-SL {ratio:.2f}×ATR — konform")


def _distance_in_atr(
    distance_pct: float, price: Optional[float], atr14: Optional[float]
) -> Optional[float]:
    """Signed Distanz in ATR14-Vielfachen. None wenn ATR/Preis fehlt oder <=0.

    distance_pct ist relativ zum Trigger-Referenzpreis (ref):
        distance_pct = (price - ref) / ref * 100
    Daraus exakter Preis-Abstand: gap = price - ref = price * d / (1 + d),
    mit d = distance_pct/100. Das ATR-Vielfache = gap / ATR14.
    """
    if atr14 is None or atr14 <= 0 or price is None or price <= 0:
        return None
    d = distance_pct / 100.0
    denom = 1.0 + d
    if denom == 0:
        return None
    gap = price * d / denom
    return gap / atr14


def _classify_proximity(
    distance_pct: float,
    cfg: dict,
    price: Optional[float] = None,
    atr14: Optional[float] = None,
) -> str:
    """Wandelt Distanz in Proximity-Bucket.

    ATR-normalisiert (Vielfache von ATR14-1D) wenn ATR verfügbar und der
    ATR-Block aktiv ist; sonst Fallback auf rohe %-Schwellen. Die
    ATR-Normalisierung macht die Buckets vola-adaptiv: 2% sind bei einem
    ruhigen Wert (ATR 1%) 2 ATR = weit weg, bei einem zappeligen (ATR 6%)
    ein Drittel-ATR = praktisch in-zone.
    """
    wtp = cfg["watchlist_trigger_parsing"]
    atr_cfg = wtp.get("trigger_proximity_atr")
    dist_atr = _distance_in_atr(distance_pct, price, atr14)

    if atr_cfg and atr_cfg.get("enabled", False) and dist_atr is not None:
        a = abs(dist_atr)
        if a <= atr_cfg["in_zone"] + 0.01:  # Toleranz für 0.0
            return "in_zone"
        if a <= atr_cfg["very_close"]:
            return "very_close"
        if a <= atr_cfg["close"]:
            return "close"
        if a <= atr_cfg["watching"]:
            return "watching"
        return "far"

    # Fallback: rohe %-Schwellen (ATR fehlt oder Block deaktiviert)
    abs_dist = abs(distance_pct)
    prox_cfg = wtp["trigger_proximity"]
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
        ts = _evaluate_trigger(trigger, snap, entry.direction, config, now_utc_hour, today)
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
    today: Optional[date] = None,
) -> TriggerStatus:
    """Bewertet einen einzelnen Trigger gegen aktuelle Daten.

    `today` wird für den Vol-Guard-Handelstags-Check durchgereicht (siehe
    _get_vol_status); None → reine Uhrzeit-Logik (Backward-Compat).
    """
    # Journal-Gate-Skip (3-Trigger-Schema, 2026-05-23): Trigger, die im
    # Watchlist-Journal per 🚦-Ampel als tot (🔴) oder wartend (⏳) markiert
    # sind, werden NICHT inhaltlich ausgewertet. Sie erscheinen als 'far' im
    # Output (sichtbar, aber nie BEREIT/NAHE) — analog zum is_empty-Fall.
    # 🟢 (scharf) / 🟡 (beobachten) / None → normale Auswertung.
    if trigger.gate == "🔴":
        return TriggerStatus(
            label=trigger.label,
            proximity="far",
            distance_pct=0.0,
            conditions_missing=["🚦 🔴 — Trigger im Journal als tot markiert"],
            summary="🔴 Gate tot — übersprungen",
        )
    if trigger.gate == "⏳" and trigger.price_op is None:
        # ⏳ NUR überspringen, wenn der Trigger keinen auswertbaren Preis hat
        # (echte "warte auf Datum/Bedingung/Event"-Trigger, z.B. PEAD-Event-Legs).
        # Ein ⏳ MIT konkretem Preis-Op ist der stale-Fall (Blindfleck-Fix
        # 2026-07-23): normal auswerten — das Datum wird ohnehin entry-seitig
        # über earliest_date → pending gehandhabt, ein zweiter blinder Skip
        # versteckte sonst NAHE-Setups (Anlassfall MRK: 0,2 ATR am Trigger,
        # aber ⏳ → nie gebucketet). Preislose ⏳ bleiben 'far' wie 🔴.
        return TriggerStatus(
            label=trigger.label,
            proximity="far",
            distance_pct=0.0,
            conditions_pending=["🚦 ⏳ — Trigger wartet (kein Preis-Level, Datum/Event)"],
            summary="⏳ Gate wartet (preislos) — übersprungen",
        )

    # === Relative Zone auflösen (2026-09-04, Note #527) ===
    # Eine Zone der Form "Touch EMA20-1D ±0,30 ATR" trägt beim Parsen noch keine
    # Zahlen — sie wird HIER, mit den Daten dieses Laufs, in price_low/price_high
    # geschrieben. Damit läuft die gesamte nachfolgende Logik (Distanz, Buckets,
    # Durchgelaufen-Check, Digest-Ausgabe) unverändert weiter, und die Zone wandert
    # automatisch mit ihrer Anker-EMA mit, statt zu veralten.
    if trigger.rel_anchor is not None:
        _emas = {
            "EMA20": snap.ema20,
            "EMA50": snap.ema50,
            "EMA100": getattr(snap, "ema100", None),
            "EMA200": snap.ema200,
        }
        if not resolve_relative_zone(trigger, _emas, snap.atr14):
            # Nicht auflösbar (Anker-EMA oder ATR fehlt) → ehrlich als preislos
            # ausweisen statt mit halb gefüllter Zone weiterzurechnen.
            trigger.price_op = None
            _fehlt = "ATR-14" if not snap.atr14 else f"{trigger.rel_anchor}-1D"
            return TriggerStatus(
                label=trigger.label,
                proximity="far",
                distance_pct=0.0,
                conditions_missing=[
                    f"relative Zone nicht auflösbar — {_fehlt} fehlt für {snap.symbol}"
                ],
                summary=f"⚠️ relative Zone ({trigger.rel_anchor}) nicht auflösbar",
            )

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

    # Carry-Forward bestätigter Tagesschluss-Breakouts (Note #110): bei reinem
    # Close-Breakout-Trigger und noch laufender Sitzung Preis + Volumen gegen die
    # letzte ABGESCHLOSSENE Tageskerze (prev_*) evaluieren, statt gegen den
    # partiellen Teilbalken. Damit überlebt ein zum Schluss N bestätigter
    # Breakout den Morgen N+1 — und invalidiert sich selbst, sobald eine
    # Tageskerze zurück durch den Trigger schließt (prev_close zeigt es dann).
    hard_hour = config["watchlist_trigger_parsing"].get("hard_evaluation_utc_hour", 20)
    use_completed = (
        _is_close_breakout_trigger(trigger)
        and _last_bar_is_forming(snap, today, now_utc_hour, hard_hour)
        and snap.prev_close is not None
    )

    # === PREIS-DISTANZ ===
    price = snap.prev_close if use_completed else snap.price
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
        threshold = (
            trigger.vol_multiplier
            if trigger.vol_multiplier is not None
            else config["watchlist_trigger_parsing"]["volume_validation"]["require_multiplier"]
        )
        if use_completed and snap.prev_volume_multiplier is not None:
            # Abgeschlossene Kerze → Volumen final: met/failed direkt, nie pending.
            mul = snap.prev_volume_multiplier
            vol_status = "met" if mul >= threshold else "failed"
        else:
            vol_status = _get_vol_status(snap, config, trigger.vol_multiplier, now_utc_hour, today)
            mul = snap.volume_multiplier_today
        mul_str = f"{mul:.2f}×" if mul is not None else "n/a"
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
        elif trigger.reverse_tf == "4h":
            # Verdeckt-BEREIT-Fix (Note #118, 2026-06-01; Regression repariert
            # 2026-07-06): Der Reverse ist auf 4h spezifiziert, die Pipeline
            # sieht aber nur Daily-OHLC. Statt den fehlenden DAILY-Reverse hart
            # zu blocken (→ NAHE), wandert er in den pending-Kanal mit
            # 4h-Handcheck-Hinweis (→ BEREIT*). Feuert der Reverse sogar auf
            # Daily, greift bereits der conditions_met-Zweig oben — dieser Pfad
            # wird dann nicht erreicht.
            if not has_today:
                reason = "keine Tages-OHLC"
            elif snap.today_lower_wick_pct is not None:
                reason = f"Daily-Kerze schwach (Close-Pos {close_pos:.0%}, Wick {snap.today_lower_wick_pct:.0f}%)"
            else:
                reason = f"Daily-Kerze schwach (Close-Pos {close_pos:.0%})"
            conditions_pending.append(
                "4h-Reverse offen — 4h manuell prüfen (" + reason + ")"
            )
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

    _atr14 = getattr(snap, "atr14", None)
    proximity = _classify_proximity(distance_pct, config, price=price, atr14=_atr14)
    distance_atr = _distance_in_atr(distance_pct, price, _atr14)
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
        if use_completed:
            summary = (
                f"🎯 BEREIT — Daily-Close bestätigt (letzter Schluss {snap.prev_close:.2f}, "
                f"Carry-Forward Vortagsschluss)"
            )
            if _live_back_through_trigger(trigger, snap):
                summary += (
                    f" · ⚠ Kurs intraday {snap.price:.2f} zurück am/durch Trigger "
                    f"— Failing-Breakout-Watch (Re-Close abwarten)"
                )
        else:
            summary = "🎯 BEREIT — alle Bedingungen erfüllt"
    elif proximity == "in_zone" and not conditions_missing and conditions_pending:
        summary = f"🎯 BEREIT* — Preis & harte Conditions ok, offen: {', '.join(conditions_pending)}"
    elif proximity == "in_zone":
        summary = f"⚠️ in Zone, aber Bedingungen offen: {', '.join(conditions_missing)}"
    elif proximity in ("very_close", "close"):
        _atr_str = f", {abs(distance_atr):.1f}×ATR" if distance_atr is not None else ""
        summary = f"📍 {proximity} ({distance_pct:+.2f}%{_atr_str})"
    else:
        _atr_str = f", {abs(distance_atr):.1f}×ATR" if distance_atr is not None else ""
        summary = f"… {proximity} ({distance_pct:+.2f}%{_atr_str})"

    # Lektion-4-SL-Guard (Note #88/#89/#92): SL-Abstand ÷ ATR an der
    # ungünstigen Zonenkante. Rein diagnostisch — verändert proximity/Bucket
    # NICHT, hängt nur ein Flag an.
    sl_check = check_sl_lektion4(trigger, snap, direction)

    return TriggerStatus(
        label=trigger.label,
        proximity=proximity,
        distance_pct=distance_pct,
        distance_atr=distance_atr,
        conditions_met=conditions_met,
        conditions_missing=conditions_missing,
        conditions_pending=conditions_pending,
        summary=summary,
        blown_through=blown_through,
        sl_check=sl_check,
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

    # ATR-Deckel (2026-08-28): relative Volatilitaet zu hoch fuer die Methode.
    # Fehlt der Schluessel in der Config, ist der Filter inaktiv — damit bleibt
    # eine aeltere filter_config.yaml lauffaehig.
    max_atr_pct = cfg.get("max_atr_pct")
    if max_atr_pct is not None:
        if snap.atr14 is not None and snap.price is not None and snap.price > 0:
            if (snap.atr14 / snap.price) * 100.0 > max_atr_pct:
                return False

    return True




def _rr_proxy(
    snap: TickerSnapshot, direction: str, config: dict
) -> tuple[Optional[float], bool]:
    """Numerischer R:R-Proxy + ENG-Flag. (None, False) wenn nicht berechenbar.

    Reward = 20d-Hoch (Long) bzw. 20d-Tief (Short), Risk = atr_mult × ATR14.
    eng=True heißt strukturell enger Fall (rr < min_rr) — Warnflag, kein
    Disqualifikator im Rendering. Der Pitch-Payload filtert eng=True separat.
    """
    cfg = config.get("rr_proxy", {})
    if not cfg.get("enabled", False):
        return None, False
    if snap.atr14 is None or snap.atr14 <= 0 or snap.price is None:
        return None, False
    risk = cfg.get("atr_mult", 1.5) * snap.atr14
    if direction == "long":
        if snap.high_20d is None:
            return None, False
        reward = snap.high_20d - snap.price
    else:
        if snap.low_20d is None:
            return None, False
        reward = snap.price - snap.low_20d
    if risk <= 0:
        return None, False
    rr = reward / risk
    eng = rr < cfg.get("min_rr", 1.4)
    return rr, eng


def _rr_proxy_suffix(snap: TickerSnapshot, direction: str, config: dict) -> str:
    """R:R-Vorfilter (Paket A, 2026-06-09): Reward-Proxy / Lektion-4-Mindest-SL.

    Konservativ gerechnet: Entry = aktueller Kurs, TP1-Proxy = 20d-Hoch (Long)
    bzw. 20d-Tief (Short), Risk = atr_mult x ATR14 (Lektion-4-Minimum).
    Bei Pullback-Entries an der EMA20 ist das echte R:R tendenziell BESSER â
    der Proxy markiert nur strukturell enge Faelle (Flag), er disqualifiziert
    NICHT (False-Negative-Schutz fuer Breakout-Thesen ohne nahen TP).
    Anlass: 2026-06-09 starben 4 von 6 manuell geprueften Stufe-2-Kandidaten
    (ROST, ORLY, DDOG, BKNG) an genau dieser Stelle.
    """
    rr, eng = _rr_proxy(snap, direction, config)
    if rr is None:
        return ""
    flag = " ⚠️ENG" if eng else ""
    return f"  RRprox={rr:.2f}{flag}"

_PITCH_LONG_BUCKETS = {"long_trend_pullback", "breakout_long", "reversal_long"}


def build_pitches_payload(
    universe_matches: list[CandidateMatch],
    config: dict,
    source_tag: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Rankt Stufe-2-Kandidaten zu Bucket-4-Pitches für den Digest.

    Nur Kandidaten mit belastbarem R:R-Proxy (Trend-Pullbacks) kommen rein;
    ⚠️ENG und ethik-ausgeschlossene fliegen raus, trendlose (|30d| < Schwelle)
    auch. Kein OHLC/ATR im Payload — Entry/SL/TP bleiben chart-zu-verifizieren.
    Gereiht nach rrprox absteigend, Top-N.
    """
    pcfg = config.get("pitches", {})
    top_n = pcfg.get("top_n", 8)
    min_abs_move = pcfg.get("min_abs_move30d", 1.0)
    exclude = set(pcfg.get("ethics_exclude", []))
    grenz = set(pcfg.get("ethics_grenzfall", []))

    out: list[dict[str, Any]] = []
    for m in universe_matches:
        sym = m.symbol
        if sym in exclude:
            continue
        snap = m.snapshot
        direction = "long" if m.bucket in _PITCH_LONG_BUCKETS else "short"
        rr, eng = _rr_proxy(snap, direction, config)
        if rr is None or eng:
            continue
        move30 = snap.move_30d_pct
        if move30 is None or abs(move30) < min_abs_move:
            continue
        if snap.ema20 is None or snap.price is None:
            continue
        dist_pct = (snap.price - snap.ema20) / snap.ema20 * 100
        out.append({
            "symbol": sym,
            "dir": direction,
            "setup": m.bucket,
            "price": round(snap.price, 4),
            "ema20": round(snap.ema20, 4),
            "dist_pct": round(dist_pct, 2),
            "rsi": round(snap.rsi14, 1) if snap.rsi14 is not None else None,
            "move30d": round(move30, 1),
            "rrprox": round(rr, 2),
            "ethics": "grenzfall" if sym in grenz else "ok",
            "tier": source_tag,
        })
    out.sort(key=lambda d: d["rrprox"], reverse=True)
    return out[:top_n]


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
        summary += _rr_proxy_suffix(snap, "long", config)
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
        summary += _rr_proxy_suffix(snap, "short", config)
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
        # V1.2 Ex-Div-Pre-Filter (Note #67, Lektion 16): liegt der letzte
        # Ex-Tag 0-2 HT zurück, ist der Tagesverlust überwiegend Buchungs-
        # effekt, kein realer Verkaufsdruck (HEI.DE 15.05.2026: -7,16% am
        # Ex-Tag fälschlich als Breakdown gemeldet). Kein Breakdown-Signal.
        if snap.last_ex_div_days_ago is not None and snap.last_ex_div_days_ago <= 2:
            return None
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
