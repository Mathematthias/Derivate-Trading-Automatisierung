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
- MODE: "tier_a" (default) oder "tier_b"
- CONFIG_DIR: Pfad zum Configs-Verzeichnis (default: ./config)
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

    # === DRIVE SERVICE ===
    drive_service = build_drive_service()

    # === CONFIGS LADEN ===
    tickers_file = "tickers_tier_a.yaml" if mode == "tier_a" else "tickers_tier_b.yaml"
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
        # Tier B
        for category in ["tecdax_kern", "biotech_de", "nasdaq_growth", "ai_quantum"]:
            section = ticker_config.get(category, {}) or {}
            for sym in section.values():
                if sym:
                    all_symbols.add(sym)
        ma_hot_list = ticker_config.get("ma_hot_list", {}) or {}
        for sym in ma_hot_list.values():
            if sym:
                all_symbols.add(sym)
        for sym in ticker_config.get("ethik_excluded", []) or []:
            excluded_symbols.add(sym)

    # Sicher: keine ethik-excluded in Pull
    all_symbols = all_symbols - excluded_symbols

    logger.info(f"Total symbols to fetch: {len(all_symbols)}")

    # === YFINANCE PULL ===
    snapshots = fetch_ticker_data(sorted(all_symbols))

    # === FILTER-EVALUATION ===
    timestamp = datetime.now(ZoneInfo("Europe/Berlin"))
    today = timestamp.date()

    watchlist_results = []
    universe_matches = []

    if mode == "tier_a":
        watchlist_results = evaluate_watchlist(
            watchlist_entries, snapshots, filter_config, today,
        )

        # Universe-Filter: nur über Werte die NICHT in der Watchlist sind
        watchlist_symbols_set = {e.symbol for e in watchlist_entries}
        universe_matches = evaluate_universe(
            snapshots,
            excluded_symbols=watchlist_symbols_set,
            config=filter_config,
            overrides=overrides,
            today=today,
        )

        logger.info(
            f"Watchlist results: {len(watchlist_results)}, "
            f"Universe matches: {len(universe_matches)}"
        )

    else:
        # Tier B: später Gamechanger-Logik einbauen — vorerst Universe-Setup-Filter
        universe_matches = evaluate_universe(
            snapshots,
            excluded_symbols=set(),
            config=filter_config,
            overrides=overrides,
            today=today,
        )
        logger.info(f"Tier-B Universe matches: {len(universe_matches)}")

    # === OUTPUT RENDERN ===
    timestamp_str = timestamp.strftime("%Y-%m-%d-%H%M")
    marketdata_filename = f"MARKETDATA-FULL-{timestamp_str}.md"
    candidates_filename = (
        f"CANDIDATES-{timestamp_str}.md" if mode == "tier_a"
        else f"GAMECHANGER-HUNT-{timestamp_str}.md"
    )

    md_content = render_marketdata_full(snapshots, timestamp)
    cand_content = render_candidates(
        watchlist_results, universe_matches, overrides, timestamp,
    )

    # === DRIVE SCHREIBEN ===
    logger.info(f"Writing files to Drive folder {briefing_folder_id}...")
    write_markdown_file(drive_service, briefing_folder_id, marketdata_filename, md_content)
    write_markdown_file(drive_service, briefing_folder_id, candidates_filename, cand_content)

    # === CLEANUP ALTE FILES ===
    cleanup_old_files(drive_service, briefing_folder_id, "MARKETDATA-FULL-", keep_count=20)
    cleanup_old_files(drive_service, briefing_folder_id, "CANDIDATES-", keep_count=20)
    if mode == "tier_b":
        cleanup_old_files(drive_service, briefing_folder_id, "GAMECHANGER-HUNT-", keep_count=10)

    logger.info("Pipeline done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")
        sys.exit(1)
