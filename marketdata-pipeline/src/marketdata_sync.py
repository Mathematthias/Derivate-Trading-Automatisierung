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
    build_grinders_payload,
    evaluate_universe,
    evaluate_watchlist,
)
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
    logger.info(f"Total symbols to fetch: {len(all_symbols)}")

    # === YFINANCE PULL ===
    snapshots = fetch_ticker_data(sorted(all_symbols))

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
    watchlist_symbols_set = {e.symbol for e in watchlist_entries if e.symbol}

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
        grinders_payload = build_grinders_payload(
            snapshots, filter_config, source_tag=universe_tag
        )
        pitches_filename = f"PITCHES-{universe_tag}-{timestamp_str}.json"
        pitches_content = json.dumps(
            {
                "generated": timestamp.isoformat(),
                "from": candidates_filename,
                "ranked": pitches_payload,
                "grinders": grinders_payload,
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
        # Pitches (Bucket 4) aus den letzten Tier-B/C-Läufen einlesen und mergen.
        # Fehlen die Files (noch kein B/C-Lauf), bleibt pitches leer → Chat fällt
        # sauber auf den GAMECHANGER-Fetch zurück.
        merged_pitches: list[dict] = []
        merged_grinders: list[dict] = []
        for prefix in ("PITCHES-EU-", "PITCHES-US-"):
            data = read_latest_json_file(drive_service, briefing_folder_id, prefix)
            if data:
                merged_pitches.extend(data.get("ranked", []))
                merged_grinders.extend(data.get("grinders", []))
        merged_pitches.sort(key=lambda d: d.get("rrprox", 0.0), reverse=True)
        top_n = filter_config.get("pitches", {}).get("top_n", 8)
        merged_pitches = merged_pitches[:top_n]
        # Grinder werden nach TEMPO gereiht, nicht nach RRprox — das ist der
        # ganze Zweck des zweiten Blocks (Note #527).
        merged_grinders.sort(key=lambda d: d.get("tempo", 0.0), reverse=True)
        g_top = filter_config.get("grinders", {}).get("top_n", 3)
        merged_grinders = merged_grinders[:g_top]
        logger.info(
            f"Digest: {len(merged_pitches)} Pitches (Bucket 4) + "
            f"{len(merged_grinders)} Grinder gemergt."
        )

        digest_filename = f"BRIEFING-DIGEST-{timestamp_str}.json"
        digest_content = build_briefing_digest(
            snapshots, watchlist_results, universe_matches, overrides, timestamp,
            pitches=merged_pitches, grinders=merged_grinders,
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
