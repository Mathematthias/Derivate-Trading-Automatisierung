"""
adhoc_scanner.py — Hidden-Catalyst-Layer für die Trading-Pipeline (Tier B).

Zieht RSS-Feeds von DGAP/EQS-News-Aggregatoren der letzten N Stunden,
filtert auf echte Catalysts (Gewinnwarnung, M&A, Insider, Rückkauf,
Kapitalmaßnahme, Strategie, Sondersituation) und schreibt das Resultat
als Markdown-File ins Workspace Drive — analog zur GAMECHANGER-HUNT-
Konvention.

Aufruf-Modi:

1. Produktiv (in GitHub-Action):
   Erwartet GDRIVE_SA_KEY, STATE_DOC_ID, BRIEFING_FOLDER_ID als ENV.
   Schreibt direkt ins Drive, holt Watchlist aus STATE-Doc.

       python src/adhoc_scanner.py --hours 24

2. Smoke-Test (lokal, kein Drive nötig):
   Prüft nur RSS-Erreichbarkeit.

       python src/adhoc_scanner.py --smoke-test

3. Local-File (lokaler Trockentest mit Output als Datei):

       python src/adhoc_scanner.py --output ./out.md --hours 24

Stand: 2026-04-29 v2 — Drive-Upload und STATE-Watchlist integriert.
"""

from __future__ import annotations

import argparse
import dataclasses as dc
import datetime as dt
import logging
import os
import re
import sys
from typing import Iterable
from xml.etree import ElementTree as ET

try:
    import feedparser  # type: ignore
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

import requests

logger = logging.getLogger("adhoc_scanner")


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

# RSS-Quellen — Reihenfolge ist Priorität. Erste Quelle, die antwortet UND
# Inhalt liefert, wird genutzt. Weitere Quellen sind Fallback/Ergänzung.
#
# WICHTIG: Diese URLs sind plausibel angesetzt aber NICHT live verifiziert
# (Sandbox-Restriktion beim Bau). Beim ersten produktiven Lauf prüfen,
# ggf. nachjustieren — README hat Symptom-Tabelle.
RSS_SOURCES: list[dict[str, str]] = [
    {
        # Hauptquelle: alle Ad-hoc-Mitteilungen (DGAP/EQS/PTA), inkl. Directors'
        # Dealings, da diese als Pflichtveröffentlichung im selben Feed laufen.
        "name": "finanznachrichten_adhoc",
        "url": "https://www.finanznachrichten.de/rss-aktien-adhoc",
    },
    {
        # Ergänzung: breiterer Aktien-Newsfeed. Enthält Corporate-News, die
        # nicht meldepflichtig waren, aber kursrelevant sind (z.B. Strategie).
        "name": "finanznachrichten_aktien",
        "url": "https://www.finanznachrichten.de/rss-aktien-nachrichten",
    },
]

HTTP_TIMEOUT = 15
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/atom+xml, text/xml, application/xml, */*;q=0.1",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

# Filename-Prefix für Drive — Cleanup nutzt das auch
ADHOC_FILENAME_PREFIX = "ADHOC-CATALYSTS-"
ADHOC_KEEP_COUNT = 10

# Catalyst-Klassifikation
# Zwei Match-Modi pro Kategorie:
#   "title_only"  — Keyword muss im Title selbst stehen (strict)
#   "text"        — Keyword darf in Title oder Summary stehen (lenient)
# Reihenfolge der Keys ist die Klassifikations-Priorität bei Mehrfach-Match.
CATALYST_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "Gewinnwarnung": {
        "title_only": [
            "gewinnwarnung", "profit warning",
        ],
        "text": [
            "prognose gesenkt", "prognose nach unten",
            "ergebnis unter erwartung", "ergebnisrückgang",
        ],
    },
    "Prognose-Anhebung": {
        "title_only": [
            "prognose angehoben", "prognose erhöht", "prognose-anhebung",
            "guidance raised", "guidance increased",
        ],
        "text": [
            "übertrifft erwartung", "outperform", "exceeds expectation",
        ],
    },
    "M&A / Übernahme": {
        "title_only": [
            "übernahme", "übernahmeangebot", "squeeze-out", "squeeze out",
            "merger", "acquisition", "takeover", "delisting-angebot",
            "tender offer", "kaufangebot", "aktienkaufvertrag",
        ],
        "text": [],
    },
    "Insider / Directors' Dealings": {
        # Strict: nur wenn der Title selbst das Insider-Geschäft als
        # Hauptthema hat. Vermeidet Boilerplate-False-Positive aus dem
        # EQS-Pflicht-Footer ("Art. 17 MAR", "Art. 19 MAR" etc.).
        "title_only": [
            "directors' dealings", "directors dealings",
            "eigengeschäfte von führungskräften", "managers' transactions",
            "meldepflichtige geschäfte", "stock dealings",
        ],
        "text": [],
    },
    "Aktienrückkauf": {
        "title_only": [
            "aktienrückkauf", "rückkaufprogramm", "buyback", "share buyback",
            "rückerwerb eigener aktien",
        ],
        "text": [],
    },
    "Kapitalmaßnahme": {
        "title_only": [
            "kapitalerhöhung", "wandelanleihe", "convertible bond",
            "anleiheemission", "bond issuance", "bezugsrechtsausschluss",
        ],
        "text": [
            "refinanzierung",
        ],
    },
    "Strategie / Vorstand": {
        "title_only": [
            "strategie-update", "strategiewechsel", "neuer ceo", "neuer cfo",
            "vorstandswechsel", "ceo announcement", "geschäftsmodell",
        ],
        "text": [
            "rücktritt", "stepping down",
        ],
    },
    "Sondersituation": {
        "title_only": [
            "klage", "schadensersatz", "sanierungsverfahren", "insolvenz",
            "verlustanzeige", "§ 92 aktg", "§92 aktg",
            "rückruf", "recall",
            "fda approval", "marketing authorisation",
            "zulassung erteilt", "zulassung versagt",
            "bafin", "aufsichtsverfahren", "ermittlungen",
            "sec investigation",
        ],
        "text": [],
    },
}

BLACKLIST_KEYWORDS: list[str] = [
    "stimmrechtsmitteilung", "voting rights announcement", "total voting rights",
    "gesamtstimmrechte",
    "hauptversammlung", "agm announcement", "annual general meeting",
    "einladung zur hauptversammlung", "einladung zur ordentlichen hauptversammlung",
    "tagesordnung der hauptversammlung",
    "dividendenvorschlag", "dividend payment", "dividenden-zahlungstermin",
    "investorenkonferenz", "investor conference", "capital markets day",
    "tag der offenen tür",
    "bekanntmachung gemäß § 40", "release according to article 40",
    "release according to article 50",
]


# ---------------------------------------------------------------------------
# Datenmodell
# ---------------------------------------------------------------------------

@dc.dataclass
class FeedItem:
    title: str
    link: str
    published: dt.datetime
    summary: str = ""
    source: str = ""

    def matches_blacklist(self) -> bool:
        text = (self.title + " " + self.summary).lower()
        return any(bl in text for bl in BLACKLIST_KEYWORDS)

    def classify(self) -> str | None:
        title_lower = self.title.lower()
        text_lower = (self.title + " " + self.summary).lower()
        for category, kw_groups in CATALYST_KEYWORDS.items():
            # Strict: nur Title prüfen
            for kw in kw_groups.get("title_only", []):
                if kw in title_lower:
                    return category
            # Lenient: Title + Summary
            for kw in kw_groups.get("text", []):
                if kw in text_lower:
                    return category
        return None

    def extract_company_hint(self) -> str:
        for sep in (":", "/"):
            if sep in self.title:
                return self.title.split(sep, 1)[0].strip()
        return self.title[:60]


@dc.dataclass
class ScanResult:
    items_by_category: dict[str, list[FeedItem]] = dc.field(default_factory=dict)
    sources_attempted: list[str] = dc.field(default_factory=list)
    sources_succeeded: list[str] = dc.field(default_factory=list)
    total_items_seen: int = 0
    total_items_dropped_blacklist: int = 0
    total_items_dropped_unmatched: int = 0
    cutoff_utc: dt.datetime | None = None

    def total_catalysts(self) -> int:
        return sum(len(v) for v in self.items_by_category.values())


# ---------------------------------------------------------------------------
# Feed-Parsing
# ---------------------------------------------------------------------------

def fetch_feed(source: dict[str, str]) -> list[FeedItem]:
    url = source["url"]
    name = source["name"]
    logger.info("Hole RSS-Feed: %s (%s)", name, url)

    try:
        resp = requests.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Feed %s nicht erreichbar: %s", name, e)
        return []

    if HAS_FEEDPARSER:
        return _parse_with_feedparser(resp.content, name)
    else:
        return _parse_with_etree(resp.content, name)


def _parse_with_feedparser(content: bytes, source_name: str) -> list[FeedItem]:
    parsed = feedparser.parse(content)
    items: list[FeedItem] = []
    for entry in parsed.entries:
        published = _parse_date(
            entry.get("published") or entry.get("updated") or ""
        )
        if published is None:
            continue
        items.append(
            FeedItem(
                title=entry.get("title", "").strip(),
                link=entry.get("link", "").strip(),
                published=published,
                summary=re.sub(r"<[^>]+>", " ", entry.get("summary", "")).strip(),
                source=source_name,
            )
        )
    return items


def _parse_with_etree(content: bytes, source_name: str) -> list[FeedItem]:
    items: list[FeedItem] = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        logger.warning("XML-Parse-Fehler für %s: %s", source_name, e)
        return items
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = item.findtext("pubDate") or ""
        published = _parse_date(pub)
        if published is None:
            continue
        desc = (item.findtext("description") or "").strip()
        desc = re.sub(r"<[^>]+>", " ", desc)
        items.append(
            FeedItem(
                title=title, link=link, published=published,
                summary=desc, source=source_name,
            )
        )
    return items


def _parse_date(raw: str) -> dt.datetime | None:
    if not raw:
        return None
    try:
        from email.utils import parsedate_to_datetime
        d = parsedate_to_datetime(raw)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc)
    except (TypeError, ValueError):
        pass
    try:
        d = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Filterung
# ---------------------------------------------------------------------------

def filter_and_classify(
    items: Iterable[FeedItem],
    cutoff: dt.datetime,
) -> ScanResult:
    result = ScanResult(cutoff_utc=cutoff)
    seen_keys: set[tuple[str, str]] = set()

    for item in items:
        result.total_items_seen += 1
        if item.published < cutoff:
            continue
        key = (item.source, item.link or item.title)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        if item.matches_blacklist():
            result.total_items_dropped_blacklist += 1
            continue

        category = item.classify()
        if category is None:
            result.total_items_dropped_unmatched += 1
            continue

        result.items_by_category.setdefault(category, []).append(item)

    for cat in result.items_by_category:
        result.items_by_category[cat].sort(
            key=lambda it: it.published, reverse=True
        )
    return result


# ---------------------------------------------------------------------------
# Watchlist (zwei Modi: Drive-STATE oder lokaler Fallback)
# ---------------------------------------------------------------------------

def load_watchlist_from_state_doc(drive_service, state_doc_id: str) -> list[str]:
    """Holt die Watchlist-Symbole aus dem STATE-Doc via Drive."""
    try:
        # Imports hier, damit der Smoke-Test ohne google-api-Pakete läuft
        from state_parser import fetch_state_doc, parse_watchlist
    except ImportError as e:
        logger.warning("state_parser nicht importierbar: %s", e)
        return []
    try:
        state_text = fetch_state_doc(drive_service, state_doc_id)
        entries = parse_watchlist(state_text)
        symbols = sorted({e.symbol for e in entries if e.symbol})
        logger.info("Watchlist aus STATE-Doc: %d Symbole", len(symbols))
        return symbols
    except Exception as e:
        logger.warning("STATE-Doc-Lesen fehlgeschlagen: %s", e)
        return []


def load_watchlist_from_local_file(state_path: str | None) -> list[str]:
    """Heuristischer Fallback für lokale Trockentests."""
    if not state_path:
        return []
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return []
    candidates = set()
    ticker_re = re.compile(r"\b[A-Z][A-Z0-9]{0,5}(?:\.[A-Z]{1,3}|-[A-Z]{3,4})?\b")
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        for match in ticker_re.findall(line):
            if match in {"DE", "EUR", "USD", "STATE", "TODO", "OK", "GO"}:
                continue
            if len(match) >= 2:
                candidates.add(match)
    return sorted(candidates)


def watchlist_hit(item: FeedItem, watchlist: list[str]) -> str | None:
    if not watchlist:
        return None
    text = (item.title + " " + item.extract_company_hint()).upper()
    for entry in watchlist:
        if re.search(rf"\b{re.escape(entry)}\b", text):
            return entry
    return None


# ---------------------------------------------------------------------------
# Markdown-Output
# ---------------------------------------------------------------------------

def render_markdown(
    result: ScanResult,
    watchlist: list[str],
    now_berlin: dt.datetime,
) -> str:
    lines: list[str] = []
    lines.append(f"# ADHOC-CATALYSTS — {now_berlin.strftime('%Y-%m-%d %H:%M %Z')}")
    lines.append("")
    cutoff_str = result.cutoff_utc.strftime('%Y-%m-%d %H:%M UTC') if result.cutoff_utc else "?"
    lines.append(
        f"**Scan-Fenster:** {cutoff_str} bis "
        f"{dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    lines.append(
        f"**Quellen versucht:** {len(result.sources_attempted)} "
        f"(erfolgreich: {len(result.sources_succeeded)})"
    )
    lines.append(
        f"**Items gesehen:** {result.total_items_seen} | "
        f"Blacklist gedroppt: {result.total_items_dropped_blacklist} | "
        f"Kein Catalyst-Match: {result.total_items_dropped_unmatched} | "
        f"**Catalysts gefunden: {result.total_catalysts()}**"
    )
    lines.append("")

    if result.total_catalysts() == 0:
        lines.append("_Keine Catalysts im Scan-Fenster._")
        lines.append("")
        lines.append("Häufige Gründe: ruhige Newslage, falsche RSS-URL, Filter zu strikt.")
        return "\n".join(lines)

    # Watchlist-Hits zuerst
    watchlist_section: list[tuple[str, str, FeedItem]] = []
    for cat, items in result.items_by_category.items():
        for item in items:
            hit = watchlist_hit(item, watchlist)
            if hit:
                watchlist_section.append((cat, hit, item))

    if watchlist_section:
        lines.append("## 🎯 Watchlist-Direkttreffer")
        lines.append("")
        for cat, hit, item in watchlist_section:
            lines.append(_render_item(item, category=cat, hit=hit))
        lines.append("")

    lines.append("## 🔍 Weitere Catalysts (nach Kategorie)")
    lines.append("")
    for cat in CATALYST_KEYWORDS.keys():
        items = result.items_by_category.get(cat, [])
        items = [it for it in items if watchlist_hit(it, watchlist) is None]
        if not items:
            continue
        lines.append(f"### {cat} ({len(items)})")
        lines.append("")
        for item in items:
            lines.append(_render_item(item, category=None))
        lines.append("")

    return "\n".join(lines)


def _render_item(
    item: FeedItem,
    category: str | None,
    hit: str | None = None,
) -> str:
    timestamp = item.published.strftime("%Y-%m-%d %H:%M UTC")
    company = item.extract_company_hint()
    bullet = f"- **{company}**"
    if hit:
        bullet += f" `[{hit}]`"
    if category:
        bullet += f" — _{category}_"
    bullet += f"\n  {item.title}"
    if item.link:
        bullet += f"\n  [Quelle]({item.link})"
    bullet += f" · {timestamp} · _{item.source}_"
    return bullet


# Backward-Compat-Alias für Tests aus v1
def watchlist_hit_legacy(item, watchlist):
    return watchlist_hit(item, watchlist)


# ---------------------------------------------------------------------------
# Orchestrierung
# ---------------------------------------------------------------------------

def run_scan(
    cutoff_hours: int,
    drive_service=None,
    state_doc_id: str | None = None,
    local_state_path: str | None = None,
) -> tuple[ScanResult, list[str]]:
    """Führt den Scan durch — RSS holen, filtern, Watchlist laden."""
    now_utc = dt.datetime.now(dt.timezone.utc)
    cutoff = now_utc - dt.timedelta(hours=cutoff_hours)

    all_items: list[FeedItem] = []
    sources_attempted: list[str] = []
    sources_succeeded: list[str] = []

    for src in RSS_SOURCES:
        sources_attempted.append(src["name"])
        items = fetch_feed(src)
        if items:
            sources_succeeded.append(src["name"])
            all_items.extend(items)

    result = filter_and_classify(all_items, cutoff=cutoff)
    result.sources_attempted = sources_attempted
    result.sources_succeeded = sources_succeeded

    if drive_service is not None and state_doc_id:
        watchlist = load_watchlist_from_state_doc(drive_service, state_doc_id)
    else:
        watchlist = load_watchlist_from_local_file(local_state_path)

    return result, watchlist


# ---------------------------------------------------------------------------
# Entry-Points
# ---------------------------------------------------------------------------

def smoke_test() -> int:
    print("=== Smoke-Test: RSS-Endpoints ===\n")
    any_success = False
    for src in RSS_SOURCES:
        print(f"→ {src['name']}: {src['url']}")
        items = fetch_feed(src)
        if items:
            jüngstes = items[0]
            print(f"  ✅ {len(items)} Items, jüngstes: {jüngstes.published} — {jüngstes.title[:80]}")
            any_success = True
        else:
            print("  ❌ Keine Items oder Feed nicht erreichbar")
        print()
    if not any_success:
        print("KEINE Quelle hat geliefert. URLs prüfen.")
        return 1
    print("Mindestens eine Quelle funktioniert — Layer ist nutzbar.")
    return 0


def run_with_drive(args) -> int:
    """Produktiver Modus — Upload ins Drive, Cleanup, Watchlist aus STATE."""
    try:
        from drive_writer import (
            build_drive_service, write_markdown_file, cleanup_old_files,
        )
    except ImportError as e:
        logger.error("Drive-Module nicht importierbar: %s — PYTHONPATH=./src gesetzt?", e)
        return 1

    state_doc_id = os.environ.get("STATE_DOC_ID")
    briefing_folder_id = os.environ.get("BRIEFING_FOLDER_ID")
    if not briefing_folder_id:
        logger.error("BRIEFING_FOLDER_ID env variable nicht gesetzt")
        return 1

    drive_service = build_drive_service()

    result, watchlist = run_scan(
        cutoff_hours=args.hours,
        drive_service=drive_service,
        state_doc_id=state_doc_id,
    )

    # Berlin-Zeit für Filename und Header (analog marketdata_sync.py)
    try:
        from zoneinfo import ZoneInfo
        now_berlin = dt.datetime.now(ZoneInfo("Europe/Berlin"))
    except ImportError:
        now_berlin = dt.datetime.now()

    filename = f"{ADHOC_FILENAME_PREFIX}{now_berlin.strftime('%Y-%m-%d-%H%M')}.md"
    md_content = render_markdown(result, watchlist, now_berlin)

    logger.info("Writing %s to Drive folder %s ...", filename, briefing_folder_id)
    write_markdown_file(drive_service, briefing_folder_id, filename, md_content)

    cleanup_old_files(
        drive_service, briefing_folder_id,
        ADHOC_FILENAME_PREFIX, keep_count=ADHOC_KEEP_COUNT,
    )

    logger.info(
        "Adhoc-Scan fertig: %d Catalysts (Watchlist-Hits werden im File markiert).",
        result.total_catalysts(),
    )
    return 0


def run_with_local_file(args) -> int:
    """Lokaler Trockentest — schreibt in Datei statt Drive."""
    result, watchlist = run_scan(
        cutoff_hours=args.hours,
        local_state_path=args.state_file,
    )
    now_berlin = dt.datetime.now()
    md = render_markdown(result, watchlist, now_berlin)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(md)
    logger.info(
        "Scan abgeschlossen: %d Catalysts, geschrieben nach %s",
        result.total_catalysts(), args.output,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", required=False,
        help="Lokaler Output-Pfad. Wenn gesetzt: KEIN Drive-Upload (Trockentest).",
    )
    parser.add_argument(
        "--state-file", required=False,
        help="Pfad zu lokalem STATE-File (nur in Local-File-Modus genutzt).",
    )
    parser.add_argument(
        "--hours", type=int, default=24,
        help="Scan-Fenster zurück in Stunden (default: 24).",
    )
    parser.add_argument(
        "--smoke-test", action="store_true",
        help="Nur RSS-Erreichbarkeit prüfen, keine Datei und kein Drive.",
    )
    parser.add_argument(
        "--verbose", action="store_true",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.smoke_test:
        return smoke_test()
    if args.output:
        return run_with_local_file(args)
    # Default: Drive-Modus
    return run_with_drive(args)


if __name__ == "__main__":
    sys.exit(main())
