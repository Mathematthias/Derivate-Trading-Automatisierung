"""
marketdata_sync.py — Main-Skript der Marktdaten-Pipeline

Orchestriert:
1. Configs laden (yamls aus Repo)
2. STATE-Doc aus Drive lesen, Watchlist + Overrides + Ticker-Map parsen
3. Vollständige Ticker-Liste zusammenbauen
4. yfinance-Batch-Pull + Indikatoren rechnen
5. Stufe 1: Watchlist-Trigger-Status auswerten
6. Stufe 2: Universe-Setup-Filter auswerten
7. Output-Files rendern und in Drive schreiben

Wird in GitHub Action mit folgenden Env-Variables aufgerufen:
- GDRIVE_SA_KEY: Service-Account-JSON als String
- STATE_DOC_ID: ID des STATE-Doc in Drive
- BRIEFING_FOLDER_ID: ID des Trading/Briefing-Ordners
- MODE: "tier_a" (default), "tier_b" (EU) oder "tier_c" (US)
- CONFIG_DIR: Pfad zum Configs-Verzeichnis (default: ./config)
- EARNINGS_PULL: "1" aktiviert pro-Symbol-Earnings-Pull (default: aus,
  empfohlen für Tier A; in Tier B/C laut Architektur ebenfalls aktiv für
  PEAD-Filter v0.1 — die paar Yahoo-Calls sind im Pull-Volumen verkraftbar)

Universe-Tag-Konvention (siehe Tag-Map weiter unten):
- tier_a → MARKETDATA-FULL-STD-...  + CANDIDATES-...
- tier_b → MARKETDATA-FULL-EU-...   + GAMECHANGER-HUNT-EU-...
- tier_c → MARKETDATA-FULL-US-...   + GAMECHANGER-HUNT-US-...

EMA200-MeanRev + PEAD-Window-Erweiterung (2026-05-08, Note #47/#49):
- Setup-Class-Flags (EMA200-MEANREV-CANDIDATE + PEAD-WINDOW-Aktive) werden
  in BEIDEN Tiers gerendert — am Anfang von CANDIDATES.md (Tier A) bzw.
  GAMECHANGER-HUNT.md (Tier B). Tier A trifft auf ~30 Watchlist-Symbole,
  Tier B auf ~280 Equities aus dem Universe — daher liefert Tier B die
  echte PEAD-Kandidatensuche, Tier A die Watchlist-Vorfilter-Sicht.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

# Module aus diesem Repo importieren — werden in src/ gefunden
from digest_renderer import build_briefing_digest
from drive_writer import (
    build_drive_service,
    cleanup_old_files,
    read_latest_json_file,
    write_json_file,
    write_markdown_file,
)
from filter_engine import (
    build_pitches_payload,
    apply_pitch_quota,
    build_grinders_report,
    dedupe_grinders,
    evaluate_universe,
    evaluate_watchlist,
)
from intraday_4h import pull_4h
from market_data import fetch_ticker_data
from output_renderer import render_candidates, render_marketdata_full
from state_parser import (
    active_watchlist_symbols,
    fetch_state_doc,
    parse_filter_overrides,
    parse_ticker_map,
    parse_watchlist,
)

# Logging-Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pipeline")


def dedupe_pitches(pitches: list[dict]) -> list[dict]:
    """Ein Symbol, ein Pitch — bestes rrprox gewinnt.

    Die Tier-Labels EU/US bezeichnen den JOB, nicht das Universum: beide Laeufe
    ueberlappen. Fuer die GRINDER wurde das am 2026-09-08 behoben
    (dedupe_grinders), fuer die Pitches nicht — obwohl dort dasselbe Argument
    gilt und sogar schwerer wiegt: bei einer Quote von 6/4 frisst jedes
    Duplikat einen von zehn Plaetzen.

    Gemessen am Digest 2026-09-15 17:02, dem ersten Lauf nach dem
    Pitch-Merge-Fix: SY1.DE stand zweimal im Block (as_of 16:57 und 16:59,
    identische Zahlen), ein Platz war verschenkt.

    Laeuft VOR apply_pitch_quota — sonst kappt die Quote auf einer Liste, in
    der Duplikate noch Plaetze belegen, und der Effekt bliebe bestehen.
    """
    best: dict[str, dict] = {}
    for p in pitches:
        if not isinstance(p, dict):
            continue
        sym = p.get("symbol")
        if not sym:
            continue
        cur = best.get(sym)
        if cur is None or (p.get("rrprox") or 0.0) > (cur.get("rrprox") or 0.0):
            best[sym] = p
    # Reihenfolge der ersten Vorkommen erhalten — apply_pitch_quota sortiert
    # anschliessend ohnehin je Lane nach rrprox.
    gesehen: set[str] = set()
    out: list[dict] = []
    for p in pitches:
        if not isinstance(p, dict):
            continue
        sym = p.get("symbol")
        if not sym or sym in gesehen:
            continue
        gesehen.add(sym)
        out.append(best[sym])
    return out


def load_merged_pitches(
    drive_service,
    briefing_folder_id: str,
    filter_config: dict,
) -> dict:
    """Liest die frischesten PITCHES-{EU,US}.json und merged sie zum Bucket-4-Satz.

    Vorgezogen vor den Pull (2026-09-15). Vorher lief dieser Block erst beim
    Digest-Rendern, also HINTER fetch_ticker_data — mit der Folge, dass ein
    Pitch-Symbol, das nicht ohnehin im Tier-A-Universum steht, keinen
    `universe`-Eintrag bekam. Gemessen am Digest 2026-09-15 15:32: 6 von 10
    Pitches ohne Kurs, ATR, Earnings und bar_date, also nicht rechenbar — weder
    SL noch Stückzahl noch R:R noch die Fächer-Prüfung. Dazu trugen die vier
    Symbole, die in beiden Blöcken standen, ZWEI verschiedene Kurse im selben
    Dokument (bis 1,15 % Abweichung, EU-Pitchlauf 11:35 gegen Digest 15:32).

    Weil der Drive-Service schon ab dem Start von main() verfügbar ist, kann der
    Merge vor den Pull. Die gemergten Symbole werden dort ins Pull-Universum
    aufgenommen und bekommen damit einen vollen, taggleichen Snapshot inklusive
    4h-Layer. Kosten: höchstens quota(trend)+quota(counter) Symbole, beim
    aktuellen 6/4 also 10 auf ~113 (+8,8 % Pull).

    Jeder Pitch bekommt zusätzlich `as_of` — den `generated`-Zeitstempel seiner
    Quelldatei. Auch nach dem Fix bleibt sichtbar, aus welchem Lauf die
    Rangfolge stammt; ohne das Feld wäre ein künftiger Zeitversatz wieder
    unsichtbar (dieselbe Lehre wie bei `bar_date`, Note #540-Klasse).

    Pure Lese-Funktion: fehlen die Files (noch kein B/C-Lauf), kommen leere
    Listen zurück und der Digest läuft ohne Pitches — Chat fällt dann wie
    bisher auf den GAMECHANGER-Fetch zurück.
    """
    merged_pitches: list[dict] = []
    merged_grinders: list[dict] = []
    grinders_total_by_tier: dict[str, int] = {}

    for prefix in ("PITCHES-EU-", "PITCHES-US-"):
        data = read_latest_json_file(drive_service, briefing_folder_id, prefix)
        if not data:
            continue
        generated = data.get("generated")
        rows = data.get("ranked", []) or []
        for row in rows:
            # setdefault: ein bereits gesetztes as_of (kuenftige Payload-
            # Versionen koennten es selbst schreiben) gewinnt.
            if generated and isinstance(row, dict):
                row.setdefault("as_of", generated)
        merged_pitches.extend(rows)
        merged_grinders.extend(data.get("grinders", []) or [])
        tag = prefix.split("-")[1]
        grinders_total_by_tier[tag] = data.get("grinders_total", 0)

    # DEDUPE VOR DER QUOTE (2026-09-15). Zuerst ein Symbol je Zeile, dann
    # kappen — in der anderen Reihenfolge belegen Duplikate noch Plaetze.
    vor = len(merged_pitches)
    merged_pitches = dedupe_pitches(merged_pitches)
    pitch_dupes = vor - len(merged_pitches)

    # Quote statt globalem RRprox-Top-N (2026-09-07). Eine gemeinsame
    # Sortierung ueber EU+US sortiert die Counter-Trend-Lane nach vorn, weil
    # RRprox den Abstand zur Zielzone misst und dieser Abstand durch
    # Extension entsteht. Gemessen am Lauf 2026-09-07 18:31: 8 von 8
    # zugestellten Pitches waren Reversals, 0 trendkonform.
    merged_pitches = apply_pitch_quota(merged_pitches, filter_config)

    # Grinder werden nach TEMPO gereiht, nicht nach RRprox — das ist der
    # ganze Zweck des zweiten Blocks (Note #527).
    merged_grinders.sort(key=lambda d: d.get("tempo", 0.0), reverse=True)
    # DEDUPE (2026-09-08): Die Tier-Labels EU/US bezeichnen den JOB, nicht
    # das Universum — beide Laeufe ueberlappen. Am 2026-09-08 stand KNIN.SW in
    # beiden PITCHES-Files (212,10 gegen 212,90, verschiedene Datenstaende) und
    # AD.AS ebenfalls. Bei top_n=5 frisst jedes Duplikat einen Platz. Die Liste
    # ist nach Tempo sortiert, das erste Vorkommen ist also das beste.
    deduped = dedupe_grinders(merged_grinders)
    dupes = len(merged_grinders) - len(deduped)
    grinders_unique_total = len(deduped)
    g_top = filter_config.get("grinders", {}).get("top_n", 3)

    return {
        "pitches": merged_pitches,
        "grinders": deduped[:g_top],
        "pitch_duplicates_removed": pitch_dupes,
        "meta": {
            "total_by_tier": grinders_total_by_tier,
            "unique_after_dedupe": grinders_unique_total,
            "shown": len(deduped[:g_top]),
            "duplicates_removed": dupes,
        },
    }


def pitch_symbols(bundle: dict | None) -> set[str]:
    """Symbole des gemergten Pitch-Satzes — das, was zusaetzlich gepullt wird."""
    if not bundle:
        return set()
    return {
        p["symbol"] for p in bundle.get("pitches", [])
        if isinstance(p, dict) and p.get("symbol")
    }


def build_pull_universe(
    mode: str,
    ticker_config: dict,
    watchlist_entries: list,
) -> tuple[set[str], set[str], set[str]]:
    """Baut die Symbol-Mengen für einen Pipeline-Lauf.

    Returns (all_symbols, excluded_symbols, excluded_category_symbols):
      all_symbols               — was via yfinance gepullt wird
      excluded_symbols          — Ethik-Ausschlüsse (nie pullen, nie rendern)
      excluded_category_symbols — Indizes/Rohstoffe/Krypto/Positionen, vom
                                  Universe-Setup-Filter ausgenommen (nur tier_a)

    Watchlist-Symbole sind Teil von all_symbols in JEDEM Tier (Fix
    watchlist_sync Bug 1, 2026-05-21). Vor dem Fix wurden sie nur in tier_a
    in den Pull aufgenommen — US-Watchlist-Werte (NET, CHKP, ...) bekamen so
    nie eine Auswertung zur US-Session, die in tier_c läuft. Folge:
    CHKP-Trigger-B-Miss 18.05.2026 (Note #68). Der frühere Workaround
    (NET/CHKP-Hardcode in tickers_tier_c.yaml) ist damit obsolet.

    Pure Funktion ohne I/O — testbar ohne Drive (test_marketdata_universe.py).
    """
    all_symbols: set[str] = set()
    excluded_symbols: set[str] = set()
    excluded_category_symbols: set[str] = set()

    if mode == "tier_a":
        # Indizes/Rohstoffe/Krypto/Positionen aus tickers_tier_a.yaml.
        # Diese Kategorien sind Makro-Kontext, kein Trade-Universum →
        # zusätzlich als excluded_category_symbols für den Setup-Filter.
        for category in ["indizes", "rohstoffe_forex", "krypto", "positionen"]:
            section = ticker_config.get(category, {}) or {}
            for sym in section.values():
                if sym:
                    all_symbols.add(sym)
                    excluded_category_symbols.add(sym)
    else:
        # Tier B / Tier C — Auto-Discover: alle Sektionen unter Root oder
        # unter 'categories:'. Tier B = EU-Universum, Tier C = US-Universum.
        container = ticker_config.get("categories", ticker_config)
        loaded_sections: list[tuple[str, int]] = []
        for name, section in container.items():
            if name == "ethik_excluded" or not isinstance(section, dict):
                continue
            count = 0
            for sym in section.values():
                if sym:
                    all_symbols.add(sym)
                    count += 1
            loaded_sections.append((name, count))
        logger.info(
            f"  {mode.upper()} sections loaded: "
            + ", ".join(f"{n}={c}" for n, c in loaded_sections)
        )

    # Ethik-Ausschlüsse (kommen NICHT in Pull, NICHT in Output)
    for sym in ticker_config.get("ethik_excluded", []) or []:
        excluded_symbols.add(sym)

    # Watchlist-Symbole — in JEDEM Tier Teil des Pull-Universums (Bug-1-Fix).
    watchlist_symbols = {
        e.symbol for e in watchlist_entries if getattr(e, "symbol", None)
    }
    all_symbols.update(watchlist_symbols)

    # Ethik gewinnt immer — auch gegen Watchlist-Einträge
    all_symbols -= excluded_symbols

    return all_symbols, excluded_symbols, excluded_category_symbols


def main():
    # === ENV LESEN ===
    state_doc_id = os.environ.get("STATE_DOC_ID")
    briefing_folder_id = os.environ.get("BRIEFING_FOLDER_ID")
    mode = os.environ.get("MODE", "tier_a")
    config_dir = Path(os.environ.get("CONFIG_DIR", "./config"))

    if not state_doc_id:
        raise RuntimeError("STATE_DOC_ID env variable not set")
    if not briefing_folder_id:
        raise RuntimeError("BRIEFING_FOLDER_ID env variable not set")

    logger.info(f"Pipeline start — mode={mode}")
    logger.info(f"  STATE_DOC_ID: {state_doc_id}")
    logger.info(f"  BRIEFING_FOLDER_ID: {briefing_folder_id}")
    logger.info(f"  CONFIG_DIR: {config_dir.resolve()}")
    logger.info(f"  EARNINGS_PULL: {os.environ.get('EARNINGS_PULL', '0')}")

    # === DRIVE SERVICE ===
    drive_service = build_drive_service()

    # === CONFIGS LADEN ===
    # Tag-Map: bestimmt sowohl welches Ticker-YAML geladen wird als auch
    # welcher Universe-Tag in den Output-Filenamen kommt.
    #   tier_a  → tickers_tier_a.yaml  → MARKETDATA-FULL-STD-..., CANDIDATES-...
    #   tier_b  → tickers_tier_b.yaml  → MARKETDATA-FULL-EU-...,  GAMECHANGER-HUNT-EU-...
    #   tier_c  → tickers_tier_c.yaml  → MARKETDATA-FULL-US-...,  GAMECHANGER-HUNT-US-...
    # Vor 2026-05-13 lief Tier B mit dem ganzen ~308-Symbol-Universum unter
    # Tag "GC". Nach Variante-A-Split (siehe MIGRATION_NOTES) heißt Tier B "EU"
    # und Tier C "US". Konsequenz auf der Skill-Seite: pipeline_utils.py muss
    # die neuen Tags kennen.
    tickers_file_map = {
        "tier_a": "tickers_tier_a.yaml",
        "tier_b": "tickers_tier_b.yaml",
        "tier_c": "tickers_tier_c.yaml",
    }
    if mode not in tickers_file_map:
        raise RuntimeError(
            f"Unknown MODE='{mode}'. Expected one of: {list(tickers_file_map)}"
        )
    tickers_file = tickers_file_map[mode]
    with open(config_dir / tickers_file, "r", encoding="utf-8") as f:
        ticker_config = yaml.safe_load(f)
    with open(config_dir / "filter_config.yaml", "r", encoding="utf-8") as f:
        filter_config = yaml.safe_load(f)

    # === STATE LESEN ===
    logger.info("Reading STATE-Doc from Drive...")
    state_text = fetch_state_doc(drive_service, state_doc_id)
    watchlist_entries = parse_watchlist(state_text)
    overrides = parse_filter_overrides(state_text)
    ticker_map = parse_ticker_map(state_text)
    logger.info(
        f"  Watchlist: {len(watchlist_entries)} entries, "
        f"Overrides: {len(overrides)}, TickerMap: {len(ticker_map)}"
    )

    # === TICKER-LISTE ZUSAMMENBAUEN ===
    # Universe-Aufbau ausgelagert in build_pull_universe() — pure Funktion,
    # testbar ohne Drive (siehe tests/test_marketdata_universe.py).
    # Watchlist-Symbole sind in JEDEM Tier Teil des Pull (Bug-1-Fix).
    all_symbols, excluded_symbols, excluded_category_symbols = build_pull_universe(
        mode, ticker_config, watchlist_entries,
    )

    # === PITCH-MERGE VOR DEM PULL (2026-09-15) ===
    # Der Merge stand bis heute HINTER fetch_ticker_data, beim Digest-Rendern.
    # Ein Pitch-Symbol, das nicht ohnehin im Tier-A-Universum steht, bekam
    # dadurch keinen `universe`-Eintrag: 6 von 10 Pitches waren am 2026-09-15
    # ohne Kurs, ATR, Earnings und bar_date, also nicht rechenbar. Und die
    # Symbole, die in beiden Bloecken standen, trugen zwei verschiedene Kurse
    # im selben Dokument. Beides faellt weg, wenn die Symbole mitgepullt werden.
    pitch_bundle = None
    if mode == "tier_a":
        pitch_bundle = load_merged_pitches(
            drive_service, briefing_folder_id, filter_config,
        )
        extra = pitch_symbols(pitch_bundle)
        # Ethik gewinnt immer — auch gegen einen gerankten Pitch.
        extra -= excluded_symbols
        neu = extra - all_symbols
        all_symbols |= extra
        # Nicht doppelt scannen: die Pitch-Symbole kommen bereits als Stufe-2-
        # Treffer aus Tier B/C. Ohne diese Zeile erschiene derselbe Wert zweimal
        # — einmal als Pitch, einmal als frischer Universe-Match des Tier-A-
        # Laufs — und die Bucket-4-Quote waere de facto ausgehebelt.
        excluded_category_symbols |= extra
        logger.info(
            f"  Pitch-Merge vorgezogen: {len(pitch_bundle['pitches'])} Pitches, "
            f"{len(extra)} Symbole ({len(neu)} neu im Pull): {sorted(neu)}"
        )

    logger.info(f"Total symbols to fetch: {len(all_symbols)}")

    # === YFINANCE PULL ===
    snapshots = fetch_ticker_data(sorted(all_symbols))

    # === 4h-LAYER (v0.1, 2026-09-08) ===
    # Zweiter, getrennter Pull auf 1h-Balken; die Aggregation zu session-
    # verankerten 4h-Kerzen macht intraday_4h.py. Additiv: schlaegt der Pull
    # fehl, bleibt snap.tf4h None und ALLES laeuft wie vorher weiter — der
    # Reverse-Check faellt dann auf den pending-Pfad zurueck (BEREIT* mit
    # Handcheck), nicht auf "Bedingung verletzt".
    tf4h_cfg = filter_config.get("intraday_4h", {})
    if tf4h_cfg.get("enabled", False):
        try:
            tf4h = pull_4h(
                sorted(all_symbols),
                period=tf4h_cfg.get("period", "60d"),
                rsi_signal_len=tf4h_cfg.get("rsi_signal_len", 14),
            )
            attached = 0
            for sym, ind in tf4h.items():
                snap = snapshots.get(sym)
                if snap is not None and ind.bars_available:
                    snap.tf4h = ind.as_dict()
                    attached += 1
            logger.info(f"4h-Layer: {attached}/{len(all_symbols)} Snapshots angereichert.")
        except Exception as exc:
            logger.warning(f"4h-Layer uebersprungen: {exc}")

    # === FILTER-EVALUATION ===
    timestamp = datetime.now(ZoneInfo("Europe/Berlin"))
    today = timestamp.date()
    # Für Vol-pending-Klassifikation: aktuelle UTC-Stunde (vor hard_evaluation_utc_hour
    # bleibt "Vol unter Schwelle" als pending, danach failed).
    now_utc_hour = timestamp.astimezone(ZoneInfo("UTC")).hour

    # Watchlist-Trigger werden in JEDEM Tier ausgewertet (Fix watchlist_sync
    # Bug 1, 2026-05-21). Vor dem Fix lief evaluate_watchlist nur in tier_a,
    # daher bekamen US-Watchlist-Werte nie eine Auswertung zur US-Session
    # (tier_c, 14:30/21:30 CEST) — CHKP-Trigger-B-Miss 18.05.2026 (Note #68).
    # Jeder Tier wertet jetzt die volle Watchlist gegen seine frischesten
    # Snapshots aus; der Skill pickt ohnehin die jüngste Ergebnisdatei, also
    # gewinnt für US-Werte der tier_c-Lauf mit echten US-Session-Daten.
    # Stufe-2-Ausnahme nur fuer LEBENDE Zeilen (Fix 2026-09-09).
    # Vorher standen hier ALLE Watchlist-Symbole. Weil watchlist_sync auch
    # archivierte Zeilen nach STATE schreibt, blockierte eine 🔴-Zeile das
    # Symbol dauerhaft in Stufe 2 — waehrend Stufe 1 es wegen des 🔴-Skips
    # ohnehin nicht auswertete. Ergebnis: das Symbol fiel komplett aus der
    # Pipeline (28 von 71 am Journal-Stand 2026-09-09). Der Pull bleibt
    # unveraendert (Z145 zieht weiter aus watchlist_entries), damit der
    # Re-Eval-Check die Kurse archivierter Zeilen behaelt.
    watchlist_symbols_set = active_watchlist_symbols(watchlist_entries)
    _tote = len([e for e in watchlist_entries if e.symbol]) - len(watchlist_symbols_set)
    if _tote:
        logger.info(
            f"  Stufe-2-Ausnahme: {len(watchlist_symbols_set)} lebende Symbole "
            f"blockieren, {_tote} archivierte wieder aufnahmefaehig"
        )

    watchlist_results = evaluate_watchlist(
        watchlist_entries, snapshots, filter_config, today, now_utc_hour,
    )
    universe_matches = evaluate_universe(
        snapshots,
        excluded_symbols=watchlist_symbols_set,
        config=filter_config,
        overrides=overrides,
        today=today,
        excluded_category_symbols=excluded_category_symbols,
    )
    logger.info(
        f"{mode.upper()} — Watchlist results: {len(watchlist_results)}, "
        f"Universe matches: {len(universe_matches)}"
    )

    # === OUTPUT RENDERN ===
    timestamp_str = timestamp.strftime("%Y-%m-%d-%H%M")

    # Universe-Tag pro Mode (siehe Header-Kommentar):
    universe_tag_map = {"tier_a": "STD", "tier_b": "EU", "tier_c": "US"}
    universe_tag = universe_tag_map[mode]

    marketdata_filename = f"MARKETDATA-FULL-{universe_tag}-{timestamp_str}.md"

    if mode == "tier_a":
        candidates_filename = f"CANDIDATES-{timestamp_str}.md"
        candidates_header = "CANDIDATES"
    else:
        # Tier B und Tier C nutzen GAMECHANGER-HUNT mit Universe-Suffix.
        candidates_filename = f"GAMECHANGER-HUNT-{universe_tag}-{timestamp_str}.md"
        candidates_header = "GAMECHANGER-HUNT"

    # Setup-Class-Flags (EMA200-MeanRev + PEAD-Window) in BEIDEN Tiers aktiv
    # (seit 2026-05-08, Note #47/#49). Tier B liefert die echte PEAD-Suche
    # über ~280 Equities; Tier A bleibt Watchlist-Vorfilter über ~30 Symbole.
    enable_setup_class_flags = True

    md_content = render_marketdata_full(snapshots, timestamp)
    # Paket B (2026-06-09): Watchlist-Block nur in CANDIDATES (Tier A);
    # GAMECHANGER-Files lassen ihn weg, sofern Config nicht widerspricht.
    include_wl = (
        mode == "tier_a"
        or filter_config.get("output", {}).get("gamechanger_include_watchlist", True)
    )
    cand_content = render_candidates(
        watchlist_results, universe_matches, overrides, timestamp,
        snapshots=snapshots,
        header_title=candidates_header,
        enable_setup_class_flags=enable_setup_class_flags,
        include_watchlist_block=include_wl,
    )

    # === DRIVE SCHREIBEN ===
    logger.info(f"Writing files to Drive folder {briefing_folder_id}...")
    write_markdown_file(drive_service, briefing_folder_id, marketdata_filename, md_content)
    write_markdown_file(drive_service, briefing_folder_id, candidates_filename, cand_content)

    # === PITCHES (nur Tier B/C, 2026-07-12) ===
    # Gerankte Stufe-2-Kandidaten als kleines JSON, damit der Tier-A-Digest sie
    # in Bucket 4 falten kann (Morning-Check = ein Fetch statt GAMECHANGER-Zweit-
    # download). Die Objekte liegen hier schon vor → kein Markdown-Reparse.
    if mode in ("tier_b", "tier_c"):
        pitches_payload = build_pitches_payload(
            universe_matches, filter_config, source_tag=universe_tag
        )
        # Zweiter Block (2026-09-04): Grinder aus dem GESAMTEN Universum, nicht
        # nur aus den Bucket-Treffern — ein Grinder erzeugt gerade kein
        # klassisches Setup-Signal (§ Pullback-Monokultur).
        # today/now_utc_hour: der harte Tempo-Boden greift nur auf einem
        # ABGESCHLOSSENEN Tagesbalken (Variante C, 2026-09-15). Ohne diese
        # beiden Argumente faellt build_grinders_report auf das alte harte
        # Gate zurueck — sie sind hier also nicht optional-kosmetisch.
        grinders_report = build_grinders_report(
            snapshots, filter_config, source_tag=universe_tag,
            today=today, now_utc_hour=now_utc_hour,
        )
        grinders_payload = grinders_report["items"]
        pitches_filename = f"PITCHES-{universe_tag}-{timestamp_str}.json"
        pitches_content = json.dumps(
            {
                "generated": timestamp.isoformat(),
                "from": candidates_filename,
                "ranked": pitches_payload,
                "grinders": grinders_payload,
                # 🆕 2026-09-08: ohne die ungedeckelte Trefferzahl kalibriert man
                # die Klasse gegen eine bei top_n abgeschnittene Liste und haelt
                # den Deckel faelschlich fuer den Marktzustand.
                "grinders_total": grinders_report["total"],
                "grinders_dropped_by_tempo": grinders_report["dropped_by_tempo"],
                "grinders_min_tempo": grinders_report["min_tempo"],
                # 🆕 2026-09-15: Schwelle, unterhalb derer ein Grinder nur
                # kleiner gesizt wird statt auszufallen. Ohne diesen Wert im
                # File kann der Morning-Check die Sizing-Stufe nicht rendern.
                "grinders_daempfer_tempo": grinders_report["daempfer_tempo"],
                # 🆕 2026-09-24: worauf Tempo gerechnet ist (trend20 = Regression
                # 20 HT, move30d = alter Endpunkt-Move). Ohne das Feld sind
                # PITCHES-Files vor und nach der Umstellung nicht unterscheidbar.
                "grinders_tempo_basis": grinders_report.get("tempo_basis", "trend20"),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        write_json_file(drive_service, briefing_folder_id, pitches_filename, pitches_content)

    # === BRIEFING-DIGEST (nur Tier A, 2026-07-10) ===
    # Kompaktes JSON aus denselben Objekten, aus denen oben Markdown gerendert
    # wurde. Ersetzt im Morning Check den STD+CANDIDATES-Doppel-Pull durch einen
    # kleinen Download. Läuft auf demselben Cronjob wie Tier A → kein neuer
    # PAT-Header. Siehe digest_renderer.py.
    if mode == "tier_a":
        # Pitches/Grinder wurden oben VOR dem Pull gelesen (load_merged_pitches),
        # damit ihre Symbole im Pull-Universum landen. Hier wird das Ergebnis nur
        # noch verwendet — kein zweiter Drive-Roundtrip, keine zweite Quote.
        bundle = pitch_bundle or {"pitches": [], "grinders": [], "meta": {}}
        merged_pitches = bundle["pitches"]
        merged_grinders = bundle["grinders"]
        g_meta = bundle["meta"]

        # Sync-Kontrolle: jedes Pitch-Symbol MUSS jetzt einen Snapshot haben.
        # Faellt ein Symbol im Pull aus (Ticker bei Yahoo verschwunden, Timeout),
        # ist das kein Grund den Lauf zu kippen — aber es gehoert ins Log, sonst
        # ist es wieder still. Der Skill-seitige digest_konsistenz_check meldet
        # denselben Fall im Briefing.
        fehlend = sorted(
            p["symbol"] for p in merged_pitches
            if p.get("symbol") and p["symbol"] not in snapshots
        )
        if fehlend:
            logger.warning(
                f"Digest: {len(fehlend)} Pitch-Symbole ohne Snapshot "
                f"(nicht rechenbar im Briefing): {fehlend}"
            )

        logger.info(
            f"Digest: {len(merged_pitches)} Pitches (Bucket 4, "
            f"{bundle.get('pitch_duplicates_removed', 0)} Duplikate entfernt) + "
            f"{len(merged_grinders)} Grinder "
            f"({g_meta.get('duplicates_removed', 0)} Duplikate entfernt, "
            f"Screen-Treffer je Lauf: {g_meta.get('total_by_tier', {})})."
        )

        digest_filename = f"BRIEFING-DIGEST-{timestamp_str}.json"
        digest_content = build_briefing_digest(
            snapshots, watchlist_results, universe_matches, overrides, timestamp,
            pitches=merged_pitches, grinders=merged_grinders,
            grinders_meta=g_meta,
        )
        write_json_file(drive_service, briefing_folder_id, digest_filename, digest_content)

    # === CLEANUP ALTE FILES ===
    cleanup_old_files(drive_service, briefing_folder_id, f"MARKETDATA-FULL-{universe_tag}-", keep_count=20)
    if mode == "tier_a":
        cleanup_old_files(drive_service, briefing_folder_id, "CANDIDATES-", keep_count=20)
        cleanup_old_files(drive_service, briefing_folder_id, "BRIEFING-DIGEST-", keep_count=10)
    else:
        cleanup_old_files(
            drive_service, briefing_folder_id,
            f"GAMECHANGER-HUNT-{universe_tag}-", keep_count=10,
        )
        cleanup_old_files(
            drive_service, briefing_folder_id,
            f"PITCHES-{universe_tag}-", keep_count=10,
        )

    logger.info("Pipeline done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")
        sys.exit(1)
