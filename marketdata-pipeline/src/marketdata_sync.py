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

import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

# Module aus diesem Repo importieren — werden in src/ gefunden
from drive_writer import (
    build_drive_service,
    cleanup_old_files,
    write_markdown_file,
)
from filter_engine import evaluate_universe, evaluate_watchlist
from market_data import fetch_ticker_data
from output_renderer import render_candidates, render_marketdata_full
from state_parser import (
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
    all_symbols: set[str] = set()
    excluded_symbols: set[str] = set()

    if mode == "tier_a":
        # Indizes/Rohstoffe/Krypto/Positionen aus tickers_a.yaml
        for category in ["indizes", "rohstoffe_forex", "krypto", "positionen"]:
            section = ticker_config.get(category, {}) or {}
            for sym in section.values():
                if sym:
                    all_symbols.add(sym)

        # Watchlist-Symbole aus STATE
        watchlist_symbols = {entry.symbol for entry in watchlist_entries}
        all_symbols.update(watchlist_symbols)

        # Ethik-Ausschlüsse merken (kommen NICHT in Pull, NICHT in Output)
        for sym in ticker_config.get("ethik_excluded", []) or []:
            excluded_symbols.add(sym)
    else:
        # Tier B / Tier C — Auto-Discover: alle Sektionen unter Root oder
        # unter 'categories:' werden eingelesen. Tier B = EU-Universum,
        # Tier C = US-Universum. Code-Pfad identisch.
        container = ticker_config.get("categories", ticker_config)
        loaded_sections: list[tuple[str, int]] = []
        for name, section in container.items():
            if name == "ethik_excluded":
                continue
            if not isinstance(section, dict):
                continue
            count = 0
            for sym in section.values():
                if sym:
                    all_symbols.add(sym)
                    count += 1
            loaded_sections.append((name, count))
        for sym in ticker_config.get("ethik_excluded", []) or []:
            excluded_symbols.add(sym)
        logger.info(
            f"  {mode.upper()} sections loaded: "
            + ", ".join(f"{n}={c}" for n, c in loaded_sections)
        )

    # Sicher: keine ethik-excluded in Pull
    all_symbols = all_symbols - excluded_symbols

    logger.info(f"Total symbols to fetch: {len(all_symbols)}")

    # === KATEGORIEN-AUSSCHLUSS für Universe-Setup-Filter ===
    excluded_category_symbols: set[str] = set()
    if mode == "tier_a":
        for category in ["indizes", "rohstoffe_forex", "krypto", "positionen"]:
            section = ticker_config.get(category, {}) or {}
            for sym in section.values():
                if sym:
                    excluded_category_symbols.add(sym)

    # === YFINANCE PULL ===
    snapshots = fetch_ticker_data(sorted(all_symbols))

    # === FILTER-EVALUATION ===
    timestamp = datetime.now(ZoneInfo("Europe/Berlin"))
    today = timestamp.date()
    # Für Vol-pending-Klassifikation: aktuelle UTC-Stunde (vor hard_evaluation_utc_hour
    # bleibt "Vol unter Schwelle" als pending, danach failed).
    now_utc_hour = timestamp.astimezone(ZoneInfo("UTC")).hour

    watchlist_results = []
    universe_matches = []

    if mode == "tier_a":
        watchlist_results = evaluate_watchlist(
            watchlist_entries, snapshots, filter_config, today, now_utc_hour,
        )

        watchlist_symbols_set = {e.symbol for e in watchlist_entries}
        universe_matches = evaluate_universe(
            snapshots,
            excluded_symbols=watchlist_symbols_set,
            config=filter_config,
            overrides=overrides,
            today=today,
            excluded_category_symbols=excluded_category_symbols,
        )

        logger.info(
            f"Watchlist results: {len(watchlist_results)}, "
            f"Universe matches: {len(universe_matches)}"
        )

    else:
        universe_matches = evaluate_universe(
            snapshots,
            excluded_symbols=set(),
            config=filter_config,
            overrides=overrides,
            today=today,
        )
        logger.info(f"{mode.upper()} Universe matches: {len(universe_matches)}")

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
    cand_content = render_candidates(
        watchlist_results, universe_matches, overrides, timestamp,
        snapshots=snapshots,
        header_title=candidates_header,
        enable_setup_class_flags=enable_setup_class_flags,
    )

    # === DRIVE SCHREIBEN ===
    logger.info(f"Writing files to Drive folder {briefing_folder_id}...")
    write_markdown_file(drive_service, briefing_folder_id, marketdata_filename, md_content)
    write_markdown_file(drive_service, briefing_folder_id, candidates_filename, cand_content)

    # === CLEANUP ALTE FILES ===
    cleanup_old_files(drive_service, briefing_folder_id, f"MARKETDATA-FULL-{universe_tag}-", keep_count=20)
    if mode == "tier_a":
        cleanup_old_files(drive_service, briefing_folder_id, "CANDIDATES-", keep_count=20)
    else:
        cleanup_old_files(
            drive_service, briefing_folder_id,
            f"GAMECHANGER-HUNT-{universe_tag}-", keep_count=10,
        )

    logger.info("Pipeline done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")
        sys.exit(1)
