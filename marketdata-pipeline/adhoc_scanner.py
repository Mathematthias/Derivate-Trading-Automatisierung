"""
adhoc_scanner.py — Hidden-Catalyst-Layer für die Trading-Pipeline (Tier B).

Pflückt Ad-hoc-Meldungen, Directors' Dealings und kursrelevante Corporate-News
aus öffentlichen RSS-Aggregatoren, filtert auf echte Catalysts (keine
Routine-Meldungen wie Stimmrechtsmitteilungen oder AGM-Einladungen) und
schreibt das Resultat als Markdown-File ins Workspace Drive — analog zur
bestehenden GAMECHANGER-HUNT-Konvention.

Aufruf im GitHub-Action-Workflow:
    python adhoc_scanner.py \
        --state-file ./pipeline_state/STATE.md \
        --output ./output/ADHOC-CATALYSTS-2026-04-28-0830.md \
        --hours 24

Nicht-Ziel:
- Bewertung der Catalysts. Das macht weiterhin der Trader / Claude in der
  Hidden-Scan-Routine 8b. Layer 1 liefert nur die Kandidaten.
- Live-Push. Das ist Sache des Tier-B-Schedules (3×/Tag).

Stand: 2026-04-28 Erstversion, ungetestet. Vor Produktiv-Einsatz im Workflow:
1. RSS-Endpoints einmal lokal mit `python adhoc_scanner.py --smoke-test` prüfen.
2. Ergebnis-Sample manuell auf Filterqualität durchschauen.
3. Filterregeln (CATALYST_KEYWORDS, BLACKLIST_KEYWORDS) bei Bedarf nachschärfen.
"""

from __future__ import annotations

import argparse
import dataclasses as dc
import datetime as dt
import logging
import re
import sys
from typing import Iterable
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

# feedparser ist Standard im Python-Ökosystem für RSS/Atom — bei GitHub Actions
# einfach in requirements.txt mit aufnehmen. Falls nicht verfügbar, fällt der
# Code auf reines XML-Parsing zurück.
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
# Inhalt liefert, wird genutzt. Weitere Quellen sind Fallback.
#
# WICHTIG: Diese URLs sind plausibel angesetzt, aber NICHT live verifiziert
# (Sandbox-Restriktion). Beim ersten Smoke-Test prüfen, ggf. nachjustieren.
RSS_SOURCES: list[dict[str, str]] = [
    {
        "name": "finanznachrichten_adhoc",
        "url": "https://www.finanznachrichten.de/rss-news-ad-hoc-mitteilungen.htm",
        "encoding": "utf-8",
    },
    {
        "name": "finanznachrichten_directors",
        "url": "https://www.finanznachrichten.de/rss-news-directors-dealings.htm",
        "encoding": "utf-8",
    },
    {
        "name": "deutsche_boerse_adhoc",
        "url": "https://live.deutsche-boerse.com/rss/all/news/ad-hoc",
        "encoding": "utf-8",
    },
]

# HTTP-Setup
HTTP_TIMEOUT = 15  # Sekunden
HTTP_HEADERS = {
    # Realistischer User-Agent — manche Aggregatoren blocken sonst.
    "User-Agent": "Mozilla/5.0 (compatible; TradingPipeline/1.0; +adhoc-scanner)"
}

# Catalyst-Klassifikation — Whitelist (positiv) und Blacklist (Drop)
# Reihenfolge der Keys ist die Klassifikations-Priorität bei Mehrfach-Match.
CATALYST_KEYWORDS: dict[str, list[str]] = {
    "Gewinnwarnung": [
        "gewinnwarnung", "profit warning", "prognose gesenkt", "prognose nach unten",
        "ergebnis unter erwartung", "ergebnisrückgang",
    ],
    "Prognose-Anhebung": [
        "prognose angehoben", "prognose erhöht", "prognose-anhebung",
        "guidance raised", "guidance increased", "übertrifft erwartung",
        "outperform", "exceeds expectation",
    ],
    "M&A / Übernahme": [
        "übernahme", "übernahmeangebot", "squeeze-out", "squeeze out",
        "merger", "acquisition", "takeover", "delisting-angebot", "tender offer",
        "kaufangebot",
    ],
    "Insider / Directors' Dealings": [
        "directors' dealings", "directors dealings", "eigengeschäft",
        "eigengeschäfte", "managers' transactions", "insider", "art. 19 mar",
    ],
    "Aktienrückkauf": [
        "aktienrückkauf", "rückkaufprogramm", "buyback", "share buyback",
        "rückerwerb eigener aktien",
    ],
    "Kapitalmaßnahme": [
        "kapitalerhöhung", "wandelanleihe", "convertible bond", "refinanzierung",
        "anleiheemission", "bond issuance", "bezugsrechtsausschluss",
    ],
    "Strategie / Vorstand": [
        "strategie-update", "strategiewechsel", "neuer ceo", "neuer cfo",
        "vorstandswechsel", "ceo announcement", "geschäftsmodell",
        "rücktritt", "stepping down",
    ],
    "Sondersituation": [
        "klage", "schadensersatz", "sanierungsverfahren", "insolvenz",
        "bafin", "aufsichtsverfahren", "ermittlungen", "sec investigation",
        "fda approval", "marketing authorisation", "zulassung erteilt",
        "zulassung versagt", "rückruf", "recall",
    ],
}

# Drop-Keywords — wenn ein Item *nur* damit matcht (oder primär damit),
# kein Catalyst.
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
    "release according to article 50",  # WpHG-Distribution-Header allein
]


# ---------------------------------------------------------------------------
# Datenmodell
# ---------------------------------------------------------------------------

@dc.dataclass
class FeedItem:
    """Eine einzelne Meldung aus dem RSS-Feed."""
    title: str
    link: str
    published: dt.datetime  # immer in UTC
    summary: str = ""
    source: str = ""

    def matches_blacklist(self) -> bool:
        text = (self.title + " " + self.summary).lower()
        return any(bl in text for bl in BLACKLIST_KEYWORDS)

    def classify(self) -> str | None:
        """Returnt den Catalyst-Typ oder None, wenn kein Match."""
        text = (self.title + " " + self.summary).lower()
        for category, keywords in CATALYST_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return category
        return None

    def extract_company_hint(self) -> str:
        """
        Extrahiert das wahrscheinliche Unternehmen aus dem Titel.
        Heuristik: alles vor dem ersten ':' oder '/' ist meist der Emittent.
        """
        for sep in (":", "/"):
            if sep in self.title:
                return self.title.split(sep, 1)[0].strip()
        return self.title[:60]


@dc.dataclass
class ScanResult:
    """Aggregat-Ergebnis eines Scan-Laufs."""
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
    """Holt einen RSS-Feed und parsed ihn zu FeedItem-Liste."""
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
    """Bevorzugter Parser. Robust gegenüber RSS/Atom/Encoding-Quirks."""
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
    """Fallback ohne feedparser. Nur RSS 2.0."""
    items: list[FeedItem] = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        logger.warning("XML-Parse-Fehler für %s: %s", source_name, e)
        return items

    # RSS 2.0 hat <channel><item>...</item></channel>
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
    """Akzeptiert RFC 822 und ISO 8601, liefert UTC-aware datetime."""
    if not raw:
        return None
    try:
        # Try RFC 822: "Mon, 27 Apr 2026 21:30:00 +0200"
        from email.utils import parsedate_to_datetime
        d = parsedate_to_datetime(raw)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc)
    except (TypeError, ValueError):
        pass
    try:
        # Try ISO 8601
        d = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Filterung und Klassifikation
# ---------------------------------------------------------------------------

def filter_and_classify(
    items: Iterable[FeedItem],
    cutoff: dt.datetime,
) -> ScanResult:
    """Filtert nach Cutoff, droppt Blacklist, klassifiziert den Rest."""
    result = ScanResult(cutoff_utc=cutoff)
    seen_keys: set[tuple[str, str]] = set()  # Dedupe über (source, link)

    for item in items:
        result.total_items_seen += 1

        if item.published < cutoff:
            continue
        # Dedupe
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

    # Pro Kategorie absteigend nach Veröffentlichungszeit sortieren
    for cat in result.items_by_category:
        result.items_by_category[cat].sort(
            key=lambda it: it.published, reverse=True
        )

    return result


# ---------------------------------------------------------------------------
# Watchlist-Cross-Match (optional)
# ---------------------------------------------------------------------------

def load_watchlist_names(state_path: str | None) -> list[str]:
    """
    Lädt Firmennamen/Tickern aus dem STATE-File.
    Robust gegenüber STATE-Format-Schwankungen — sucht einfach nach Zeilen,
    die nach Watchlist-Einträgen aussehen.
    """
    if not state_path:
        return []
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        logger.warning("STATE-File %s nicht lesbar — Watchlist-Match übersprungen", state_path)
        return []

    # Sehr toleranter Parser: jede Zeile, die einen Ticker-artigen
    # Token enthält (1-6 Großbuchstaben, optional .DE/.PA/-EUR), zählt.
    # Plus: Die Zeile darf nicht Header sein.
    candidates = set()
    ticker_re = re.compile(r"\b[A-Z][A-Z0-9]{0,5}(?:\.[A-Z]{1,3}|-[A-Z]{3,4})?\b")
    for line in text.splitlines():
        # Header und Erklärtext überspringen
        if line.lstrip().startswith("#"):
            continue
        for match in ticker_re.findall(line):
            # Ein paar offensichtliche False Positives raus
            if match in {"DE", "EUR", "USD", "STATE", "TODO", "OK", "GO"}:
                continue
            if len(match) >= 2:
                candidates.add(match)
    return sorted(candidates)


def watchlist_hit(item: FeedItem, watchlist: list[str]) -> str | None:
    """Returnt den Watchlist-Eintrag, falls Match — sonst None."""
    if not watchlist:
        return None
    text = (item.title + " " + item.extract_company_hint()).upper()
    for entry in watchlist:
        # Tickern oft direkt im Titel oder via Firmenname-Kontext.
        # Hier konservativ: nur Direkt-Treffer auf Token-Ebene.
        if re.search(rf"\b{re.escape(entry)}\b", text):
            return entry
    return None


# ---------------------------------------------------------------------------
# Markdown-Output
# ---------------------------------------------------------------------------

def render_markdown(
    result: ScanResult,
    watchlist: list[str],
    now_utc: dt.datetime,
) -> str:
    """Rendert das Ergebnis als Markdown im Pipeline-Stil."""
    cest_offset = dt.timedelta(hours=2)  # CEST grob — DST-Edge nicht perfekt
    now_cest = now_utc + cest_offset

    lines: list[str] = []
    lines.append(f"# ADHOC-CATALYSTS — {now_cest.strftime('%Y-%m-%d %H:%M')} CEST")
    lines.append("")
    lines.append(
        f"**Scan-Fenster:** {result.cutoff_utc.strftime('%Y-%m-%d %H:%M UTC')} "
        f"bis {now_utc.strftime('%Y-%m-%d %H:%M UTC')}"
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
        lines.append("Bei wiederholten Null-Läufen: RSS-Endpoints prüfen und Smoke-Test laufen lassen.")
        return "\n".join(lines)

    # Watchlist-Hits zuerst (höchste Priorität)
    watchlist_section: list[tuple[str, str, FeedItem]] = []  # (cat, hit, item)
    for cat, items in result.items_by_category.items():
        for item in items:
            hit = watchlist_hit(item, watchlist)
            if hit:
                watchlist_section.append((cat, hit, item))

    if watchlist_section:
        lines.append("## 🎯 Watchlist-Direkttreffer")
        lines.append("")
        for cat, hit, item in watchlist_section:
            lines.append(_render_item(item, category=cat, watchlist_hit=hit))
        lines.append("")

    # Restliche Catalysts nach Kategorie
    lines.append("## 🔍 Weitere Catalysts (nach Kategorie)")
    lines.append("")
    for cat in CATALYST_KEYWORDS.keys():  # stabile Reihenfolge
        items = result.items_by_category.get(cat, [])
        # Watchlist-Hits in dieser Kategorie schon oben — hier raus
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
    watchlist_hit: str | None = None,
) -> str:
    timestamp = item.published.strftime("%Y-%m-%d %H:%M UTC")
    company = item.extract_company_hint()
    bullet = f"- **{company}**"
    if watchlist_hit:
        bullet += f" `[{watchlist_hit}]`"
    if category:
        bullet += f" — _{category}_"
    bullet += f"\n  {item.title}"
    if item.link:
        bullet += f"\n  [Quelle]({item.link})"
    bullet += f" · {timestamp} · _{item.source}_"
    return bullet


# ---------------------------------------------------------------------------
# Orchestrierung
# ---------------------------------------------------------------------------

def run_scan(
    sources: list[dict[str, str]],
    cutoff_hours: int,
    state_path: str | None,
) -> tuple[ScanResult, list[str]]:
    """Führt den kompletten Scan durch."""
    now_utc = dt.datetime.now(dt.timezone.utc)
    cutoff = now_utc - dt.timedelta(hours=cutoff_hours)

    all_items: list[FeedItem] = []
    result_meta = ScanResult(cutoff_utc=cutoff)

    for src in sources:
        result_meta.sources_attempted.append(src["name"])
        items = fetch_feed(src)
        if items:
            result_meta.sources_succeeded.append(src["name"])
            all_items.extend(items)

    result = filter_and_classify(all_items, cutoff=cutoff)
    # Meta-Felder von Quellen-Tracking übernehmen
    result.sources_attempted = result_meta.sources_attempted
    result.sources_succeeded = result_meta.sources_succeeded

    watchlist = load_watchlist_names(state_path)
    return result, watchlist


def smoke_test() -> int:
    """Lokaler Quick-Check: erreiche ich die RSS-URLs überhaupt?"""
    print("=== Smoke-Test: RSS-Endpoints ===\n")
    any_success = False
    for src in RSS_SOURCES:
        print(f"→ {src['name']}: {src['url']}")
        items = fetch_feed(src)
        if items:
            print(f"  ✅ {len(items)} Items, jüngstes: {items[0].published} — {items[0].title[:80]}")
            any_success = True
        else:
            print("  ❌ Keine Items oder Feed nicht erreichbar")
        print()
    if not any_success:
        print("KEINE Quelle hat geliefert. URLs prüfen, ggf. User-Agent oder Pfad anpassen.")
        return 1
    print("Mindestens eine Quelle funktioniert — Layer kann produktiv genutzt werden.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", required=False,
        help="Ausgabe-Pfad für ADHOC-CATALYSTS-Markdown.",
    )
    parser.add_argument(
        "--state-file", required=False, default=None,
        help="Pfad zum STATE.md für Watchlist-Cross-Match (optional).",
    )
    parser.add_argument(
        "--hours", type=int, default=24,
        help="Scan-Fenster zurück in Stunden (default: 24).",
    )
    parser.add_argument(
        "--smoke-test", action="store_true",
        help="Nur RSS-Erreichbarkeit prüfen, kein File schreiben.",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Mehr Logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.smoke_test:
        return smoke_test()

    if not args.output:
        parser.error("--output ist Pflicht (außer bei --smoke-test).")

    result, watchlist = run_scan(
        sources=RSS_SOURCES,
        cutoff_hours=args.hours,
        state_path=args.state_file,
    )

    now_utc = dt.datetime.now(dt.timezone.utc)
    md = render_markdown(result, watchlist, now_utc)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(md)

    logger.info(
        "Scan abgeschlossen: %d Catalysts, geschrieben nach %s",
        result.total_catalysts(), args.output,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
