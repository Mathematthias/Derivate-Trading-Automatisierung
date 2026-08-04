"""
catalyst_calendar_sync.py — Termin-Radar-Layer für die Trading-Pipeline.

Sammelt DATIERTE Ereignisse, aus denen sich Thesen ableiten lassen, und schreibt
sie als CATALYST-CALENDAR-{datetime}.md + .json ins Workspace Drive. Damit wird
die Thesenfindung von "mir fällt was ein" auf "ich lese den Kalender" gedreht.

ANLASS (5er-Block-Review 2026-08-04, Journal-Notes #233/#234/#241):
  Zwischen 2026-06-30 und 2026-08-04 entstand fünf Wochen lang keine einzige
  neue These. Ursache war nicht Ideenmangel, sondern dass der Tagesablauf
  keinen Ort für Thesen hatte: Die Pipeline liefert ATR-Distanzen, RRprox und
  Setup-Flags — kein Feld für "warum sollte das steigen", und sie kann keins
  haben. Die belastbarste These im Journal (#156, China/Seltene Erden) ist ein
  KALENDEREINTRAG: sie lebt von einem Datum (2026-11-10), nicht von einer
  Meinung, und hat deshalb als einzige eine terminierte Aktion.

ABGRENZUNG — was dieser Job NICHT tut:
  Er bewertet nicht. Ein Termin ist keine These. Dass am 10.11. etwas ausläuft,
  sagt nichts darüber, ob es eingepreist ist oder in welche Richtung es wirkt.
  Der Job füttert Routine 9 (Wochen-Research) mit Rohstoff; das Konviktions-Gate
  und die Crowdedness-Messung bleiben manuell (references/deep-research-weekly.md).

VIER COLLECTOREN, absteigend nach Verlässlichkeit:

  1. index_reviews    — DETERMINISTISCH, kein Netzwerk. Index-Überprüfungen
                        folgen publizierten Kalenderregeln (DAX: 3. Arbeitstag
                        im Monat / Verkettung nach 3. Freitag; Nasdaq-100:
                        2. Freitag Dezember; MSCI: Feb/Mai/Aug/Nov). Diese
                        Termine sind rechenbar und brauchen keine Quelle.
                        confidence='verified'
  2. seeds            — kuratierte YAML (config/catalyst_seeds.yaml). Enthält
                        die am 2026-08-04 recherchierten Termine mit Quelle und
                        Abrufdatum. Handgepflegt, überlebt jeden API-Ausfall.
                        confidence aus der YAML.
  3. federal_register — US-Regulierung über die freie JSON-API
                        (federalregister.gov/api/v1). Liefert effective_on und
                        comments_close_on. Kein API-Key nötig.
                        confidence='verified' bei Datum aus dem Feld,
                        'heuristic' wenn nur publication_date vorliegt.
  4. sec_lockups      — IPO-Lockups aus S-1/424B4-Filings (EDGAR full-text).
                        Das Lockup-Datum wird als Filing + LOCKUP_DEFAULT_DAYS
                        GESCHÄTZT — Prospekte nennen die Frist im Fließtext,
                        nicht maschinenlesbar. confidence='heuristic'.
                        Vor Nutzung im Prospekt gegenprüfen.

⚠️ NETZWERK-VERIFIKATION: Wie bei insider_us_scanner.py (Paket C1) sind die
   HTTP-Endpoints beim Bau NICHT live geprüft worden (Sandbox ohne Zugriff auf
   federalregister.gov / sec.gov). Die deterministischen Collectoren 1 und 2
   laufen garantiert. Beim ersten produktiven Lauf das Action-Log auf die
   Zeile "collector X: N Events / FEHLER" prüfen — jeder Collector ist einzeln
   gekapselt und darf ausfallen, ohne den Job zu killen (Design wie
   GAMECHANGER: additiv, kein globaler Fallback).

Aufruf-Modi (analog insider_us_scanner.py):

  1. Produktiv (GitHub-Action):
         python src/catalyst_calendar_sync.py --horizon-days 210
     Erwartet GDRIVE_SA_KEY, BRIEFING_FOLDER_ID als ENV.

  2. Smoke-Test (nur Erreichbarkeit, kein Drive):
         python src/catalyst_calendar_sync.py --smoke-test

  3. Local-File (Trockentest):
         python src/catalyst_calendar_sync.py --output ./cal.md

  4. Nur deterministische Collectoren (kein Netz):
         python src/catalyst_calendar_sync.py --offline --output ./cal.md

Stand: 2026-08-04 v1.
"""

from __future__ import annotations

import argparse
import calendar
import dataclasses as dc
import datetime as dt
import json
import logging
import os
import sys
from typing import Callable, Iterable, Optional

import requests

logger = logging.getLogger("catalyst_calendar_sync")

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

FILENAME_PREFIX = "CATALYST-CALENDAR-"
KEEP_COUNT = 10

DEFAULT_HORIZON_DAYS = 210          # ~7 Monate: deckt 2-6-Wochen-Swing + Vorlauf
IMMINENT_DAYS = 28                  # ab hier "einrückend" — Bucket-0-relevant
DEFAULT_SEEDS_YAML = os.path.join(
    os.environ.get("CONFIG_DIR", "./config"), "catalyst_seeds.yaml"
)

HTTP_TIMEOUT = 25
USER_AGENT_FALLBACK = "derivate-trading-pipeline catalyst_calendar_sync"

FEDERAL_REGISTER_API = "https://www.federalregister.gov/api/v1/documents.json"
# Suchbegriffe für Kategorie 1. Bewusst eng: breite Begriffe fluten den Kalender
# mit Verwaltungsroutine. Erweitern nur, wenn ein Lauf zu wenig liefert.
FEDERAL_REGISTER_TERMS = [
    "Section 301 exclusion",
    "Section 232",
    "export control rare earth",
    "tariff exclusion extension",
]

SEC_FULLTEXT_API = "https://efts.sec.gov/LATEST/search-index"
LOCKUP_DEFAULT_DAYS = 180           # Marktstandard; Prospekt schlägt die Annahme

# Kategorien (identisch zum Journal-Sheet "Termin-Radar")
KAT_REGULIERUNG = 1
KAT_AUKTION = 2
KAT_LOCKUP = 3
KAT_INDEX = 4
KAT_KAPAZITAET = 5

KAT_LABEL = {
    KAT_REGULIERUNG: "Regulierung/Frist",
    KAT_AUKTION: "Auktion/Vergabe",
    KAT_LOCKUP: "IPO-Lockup",
    KAT_INDEX: "Index-Umstellung",
    KAT_KAPAZITAET: "Kapazitaet/Zulassung",
}

# Ethik-Ausschluss (SKILL.md § Ethik-Regel). Greift auf Ticker UND Namen.
ETHIK_BLOCKLIST = {
    "RHM.DE", "RHM", "BA.L", "BAES", "LMT", "NOC", "GD", "RTX", "KNDS",
}
ETHIK_NAME_TOKENS = ("rheinmetall", "lockheed", "northrop", "general dynamics",
                     "raytheon", "bae systems", "knds")


# ---------------------------------------------------------------------------
# Datenmodell
# ---------------------------------------------------------------------------

@dc.dataclass
class CatalystEvent:
    """Ein datiertes Ereignis. `date_to` nur bei Zeitfenstern gesetzt."""
    date_from: dt.date
    kategorie: int
    titel: str
    tickers: list[str] = dc.field(default_factory=list)
    wirkung: str = ""
    quelle: str = ""
    url: str = ""
    confidence: str = "unverified"      # verified | heuristic | unverified
    collector: str = ""
    date_to: Optional[dt.date] = None

    @property
    def key(self) -> tuple:
        """Dedupe-Schluessel: gleiches Datum + gleiche Kategorie + aehnlicher Titel."""
        return (self.date_from, self.kategorie, _norm_title(self.titel)[:60])

    def days_until(self, today: dt.date) -> int:
        return (self.date_from - today).days

    def status(self, today: dt.date) -> str:
        d = self.days_until(today)
        if d < 0:
            return "passed"
        if d <= IMMINENT_DAYS:
            return "imminent"
        return "upcoming"

    def date_str(self) -> str:
        if self.date_to and self.date_to != self.date_from:
            return f"{self.date_from.isoformat()} -> {self.date_to.isoformat()}"
        return self.date_from.isoformat()

    def to_dict(self, today: dt.date) -> dict:
        return {
            "date": self.date_from.isoformat(),
            "date_to": self.date_to.isoformat() if self.date_to else None,
            "kat": self.kategorie,
            "kat_label": KAT_LABEL.get(self.kategorie, "?"),
            "titel": self.titel,
            "tickers": self.tickers,
            "wirkung": self.wirkung,
            "quelle": self.quelle,
            "url": self.url,
            "confidence": self.confidence,
            "collector": self.collector,
            "days_until": self.days_until(today),
            "status": self.status(today),
        }


def _norm_title(s: str) -> str:
    return "".join(ch.lower() for ch in s if ch.isalnum() or ch == " ").strip()


def _ethik_ok(ev: CatalystEvent) -> bool:
    if any(t.upper() in ETHIK_BLOCKLIST for t in ev.tickers):
        return False
    hay = (ev.titel + " " + " ".join(ev.tickers)).lower()
    return not any(tok in hay for tok in ETHIK_NAME_TOKENS)


# ---------------------------------------------------------------------------
# Collector 1 — Index-Reviews (deterministisch, kein Netzwerk)
# ---------------------------------------------------------------------------

def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """n-ter <weekday> (0=Mo) im Monat. n=1 -> erster."""
    first = dt.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + dt.timedelta(days=offset + 7 * (n - 1))


def _nth_business_day(year: int, month: int, n: int) -> dt.date:
    """n-ter Arbeitstag (Mo-Fr, ohne Feiertage) im Monat."""
    d = dt.date(year, month, 1)
    count = 0
    while True:
        if d.weekday() < 5:
            count += 1
            if count == n:
                return d
        d += dt.timedelta(days=1)


def collect_index_reviews(today: dt.date, horizon: dt.date) -> list[CatalystEvent]:
    """Index-Ueberpruefungen aus publizierten Kalenderregeln.

    Diese Termine sind rechenbar, nicht recherchierbar — deshalb der
    verlaesslichste Collector. Regeln:
      DAX-Familie : Bekanntgabe 3. Arbeitstag im Ueberpruefungsmonat
                    (Mrz/Jun/Sep/Dez), Verkettung nach Schluss des 3. Freitags,
                    wirksam am naechsten Handelstag.
      Nasdaq-100  : Jahres-Rekonstitution, Bekanntgabe 2. Freitag im Dezember,
                    wirksam vor Handelsbeginn am Montag nach dem 3. Freitag.
      MSCI        : Quartals-Reviews Feb/Mai/Aug/Nov; Ankuendigung ~2. Mittwoch,
                    wirksam per Monatsende-Close (hier: 1. des Folgemonats).
    """
    out: list[CatalystEvent] = []
    years = sorted({today.year, horizon.year})

    for year in years:
        # --- DAX-Familie: Mrz, Jun, Sep, Dez ---
        for month in (3, 6, 9, 12):
            announce = _nth_business_day(year, month, 3)
            third_friday = _nth_weekday(year, month, 4, 3)
            effective = third_friday + dt.timedelta(days=3)  # Montag danach
            out.append(CatalystEvent(
                date_from=announce, date_to=effective, kategorie=KAT_INDEX,
                titel=(f"DAX-Familie planmaessige Ueberpruefung: Bekanntgabe "
                       f"{announce.isoformat()}, Verkettung nach Schluss "
                       f"{third_friday.isoformat()}, wirksam {effective.isoformat()}"),
                tickers=["DAX/MDAX/SDAX/TecDAX Auf- und Absteiger"],
                wirkung="+ Aufsteiger / - Absteiger; Flow konzentriert in der Schlussauktion",
                quelle="Deutsche Boerse Index-Regelwerk (Kalenderregel)",
                url="https://live.deutsche-boerse.com/wissen/wertpapiere/aktien/indexanpassungen",
                confidence="verified", collector="index_reviews",
            ))
        # --- Nasdaq-100 Jahres-Rekonstitution ---
        announce = _nth_weekday(year, 12, 4, 2)              # 2. Freitag Dez
        third_friday = _nth_weekday(year, 12, 4, 3)
        out.append(CatalystEvent(
            date_from=announce, date_to=third_friday + dt.timedelta(days=3),
            kategorie=KAT_INDEX,
            titel=("Nasdaq-100 Jahres-Rekonstitution: Bekanntgabe 2. Freitag Dezember, "
                   "wirksam vor Handelsbeginn am Montag nach dem 3. Freitag"),
            tickers=["Nasdaq-100 Auf-/Absteiger"],
            wirkung="+ Aufsteiger / - Absteiger; ETF-Flow in der Schlussauktion",
            quelle="Nasdaq Index Methodology (Kalenderregel)",
            url="https://ir.nasdaq.com/news-releases",
            confidence="verified", collector="index_reviews",
        ))
        # --- MSCI Quartals-Reviews ---
        for month in (2, 5, 8, 11):
            announce = _nth_weekday(year, month, 2, 2)       # 2. Mittwoch
            eff_month = month + 1 if month < 12 else 1
            eff_year = year if month < 12 else year + 1
            effective = dt.date(eff_year, eff_month, 1)
            semi = month in (5, 11)
            out.append(CatalystEvent(
                date_from=announce, date_to=effective, kategorie=KAT_INDEX,
                titel=(f"MSCI {'Semi-Annual' if semi else 'Quarterly'} Index Review: "
                       f"Ankuendigung ~{announce.isoformat()}, wirksam {effective.isoformat()}"
                       + (" — groesster passiver Flow-Termin des Halbjahres" if semi else "")),
                tickers=["MSCI-Kandidaten EU/US"],
                wirkung="passiver Flow um den Wirksamkeitstermin; Richtung wertabhaengig",
                quelle="MSCI Index Review Calendar (Kalenderregel)",
                url="https://www.msci.com/our-solutions/indexes/index-review",
                confidence="verified", collector="index_reviews",
            ))

    return [e for e in out if today <= e.date_from <= horizon]


# ---------------------------------------------------------------------------
# Collector 2 — Seeds aus YAML (kuratiert)
# ---------------------------------------------------------------------------

def collect_seeds(path: str, today: dt.date, horizon: dt.date) -> list[CatalystEvent]:
    """Handgepflegte Termine aus config/catalyst_seeds.yaml.

    Ueberlebt jeden API-Ausfall und haelt die am 2026-08-04 recherchierten
    Termine fest. Format je Eintrag siehe YAML-Kopf.
    """
    try:
        import yaml  # lokal importiert: offline-Modus soll ohne PyYAML laufen
    except ImportError:
        logger.warning("PyYAML nicht verfuegbar — Seeds uebersprungen")
        return []
    if not os.path.exists(path):
        logger.warning("Seeds-YAML nicht gefunden: %s", path)
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    out: list[CatalystEvent] = []
    for raw in data.get("events", []):
        try:
            d_from = _parse_date(raw["date"])
            d_to = _parse_date(raw["date_to"]) if raw.get("date_to") else None
        except (KeyError, ValueError) as e:
            logger.warning("Seed uebersprungen (Datum unlesbar): %s (%s)", raw.get("titel"), e)
            continue
        out.append(CatalystEvent(
            date_from=d_from, date_to=d_to,
            kategorie=int(raw.get("kat", KAT_REGULIERUNG)),
            titel=str(raw.get("titel", "")).strip(),
            tickers=[t.strip() for t in str(raw.get("tickers", "")).split(",") if t.strip()],
            wirkung=str(raw.get("wirkung", "")).strip(),
            quelle=str(raw.get("quelle", "")).strip(),
            url=str(raw.get("url", "")).strip(),
            confidence=str(raw.get("confidence", "verified")).strip(),
            collector="seeds",
        ))
    return [e for e in out if e.date_from <= horizon]   # passed bleibt drin (Aging)


def _parse_date(v) -> dt.date:
    if isinstance(v, dt.date):
        return v
    return dt.datetime.strptime(str(v).strip(), "%Y-%m-%d").date()


# ---------------------------------------------------------------------------
# Collector 3 — Federal Register (US-Regulierung)
# ---------------------------------------------------------------------------

def collect_federal_register(today: dt.date, horizon: dt.date,
                             terms: Optional[list[str]] = None,
                             session: Optional[requests.Session] = None
                             ) -> list[CatalystEvent]:
    """US-Regulierung mit Wirksamkeits-/Fristdatum aus der freien JSON-API.

    Kein API-Key noetig. Wir fragen je Suchbegriff die Dokumente ab, deren
    `effective_on` im Horizont liegt; faellt das Feld leer aus, wird
    `comments_close_on` genommen (dann confidence='heuristic', weil eine
    Kommentarfrist kein Wirksamkeitsdatum ist).
    """
    sess = session or requests.Session()
    sess.headers.setdefault("User-Agent", os.environ.get("SEC_CONTACT", USER_AGENT_FALLBACK))
    out: list[CatalystEvent] = []
    for term in (terms or FEDERAL_REGISTER_TERMS):
        params = {
            "per_page": 40,
            "order": "newest",
            "conditions[term]": term,
            "conditions[publication_date][gte]": (today - dt.timedelta(days=365)).isoformat(),
            "fields[]": ["title", "html_url", "effective_on", "comments_close_on",
                         "publication_date", "agencies", "document_number"],
        }
        try:
            r = sess.get(FEDERAL_REGISTER_API, params=params, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            payload = r.json()
        except Exception as e:  # noqa: BLE001 — Collector darf ausfallen
            logger.warning("federal_register('%s') fehlgeschlagen: %s", term, e)
            continue
        for doc in payload.get("results", []):
            eff, conf = doc.get("effective_on"), "verified"
            if not eff:
                eff, conf = doc.get("comments_close_on"), "heuristic"
            if not eff:
                continue
            try:
                d = _parse_date(eff)
            except ValueError:
                continue
            if not (today <= d <= horizon):
                continue
            out.append(CatalystEvent(
                date_from=d, kategorie=KAT_REGULIERUNG,
                titel=(doc.get("title") or "").strip()[:220],
                tickers=[], wirkung="",
                quelle=f"Federal Register {doc.get('document_number','')} (Suchbegriff: {term})",
                url=doc.get("html_url", ""), confidence=conf,
                collector="federal_register",
            ))
    return out


# ---------------------------------------------------------------------------
# Collector 4 — IPO-Lockups (heuristisch)
# ---------------------------------------------------------------------------

def collect_sec_lockups(today: dt.date, horizon: dt.date,
                        lookback_days: int = 240,
                        session: Optional[requests.Session] = None
                        ) -> list[CatalystEvent]:
    """IPO-Lockup-Termine aus 424B4-Filings, Datum GESCHAETZT.

    Prospekte nennen die Lockup-Frist im Fliesstext, nicht maschinenlesbar.
    Deshalb: Filing-Datum + LOCKUP_DEFAULT_DAYS. Immer confidence='heuristic'
    — vor jeder Nutzung im Prospekt gegenpruefen (Journal-Note #148 zeigt,
    wie teuer eine falsche Lockup-Annahme wird).

    SEC Fair Access: User-Agent mit Kontakt Pflicht -> ENV SEC_CONTACT.
    """
    contact = os.environ.get("SEC_CONTACT")
    if not contact:
        logger.warning("SEC_CONTACT nicht gesetzt — sec_lockups uebersprungen")
        return []
    sess = session or requests.Session()
    sess.headers.update({"User-Agent": contact, "Accept": "application/json"})
    since = today - dt.timedelta(days=lookback_days)
    params = {"q": '"lock-up"', "forms": "424B4",
              "dateRange": "custom", "startdt": since.isoformat(),
              "enddt": today.isoformat()}
    try:
        r = sess.get(SEC_FULLTEXT_API, params=params, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        hits = r.json().get("hits", {}).get("hits", [])
    except Exception as e:  # noqa: BLE001
        logger.warning("sec_lockups fehlgeschlagen: %s", e)
        return []
    out: list[CatalystEvent] = []
    for h in hits:
        src = h.get("_source", {})
        filed = src.get("file_date") or src.get("filedAt")
        names = src.get("display_names") or []
        if not filed:
            continue
        try:
            d = _parse_date(str(filed)[:10]) + dt.timedelta(days=LOCKUP_DEFAULT_DAYS)
        except ValueError:
            continue
        if not (today <= d <= horizon):
            continue
        out.append(CatalystEvent(
            date_from=d, kategorie=KAT_LOCKUP,
            titel=(f"IPO-Lockup-Ablauf (GESCHAETZT: Filing + {LOCKUP_DEFAULT_DAYS} Tage) — "
                   f"{'; '.join(names)[:120]}"),
            tickers=[], wirkung="- Angebotsdruck bei Ablauf",
            quelle="SEC EDGAR 424B4 full-text",
            url="https://efts.sec.gov/LATEST/search-index",
            confidence="heuristic", collector="sec_lockups",
        ))
    return out


# ---------------------------------------------------------------------------
# Merge, Aging, Rendering
# ---------------------------------------------------------------------------

def merge_events(groups: Iterable[list[CatalystEvent]]) -> list[CatalystEvent]:
    """Dedupliziert ueber (Datum, Kategorie, normalisierter Titel).

    Bei Dubletten gewinnt die hoehere Confidence, danach der laengere Titel
    (mehr Kontext). Seeds schlagen damit in der Regel API-Funde — gewollt,
    weil Seeds handgeprueft sind.
    """
    rank = {"verified": 3, "heuristic": 2, "unverified": 1}
    best: dict[tuple, CatalystEvent] = {}
    for grp in groups:
        for ev in grp:
            if not _ethik_ok(ev):
                logger.info("Ethik-Filter: '%s' verworfen", ev.titel[:60])
                continue
            cur = best.get(ev.key)
            if cur is None:
                best[ev.key] = ev
                continue
            if (rank.get(ev.confidence, 0), len(ev.titel)) > (rank.get(cur.confidence, 0), len(cur.titel)):
                best[ev.key] = ev
    return sorted(best.values(), key=lambda e: (e.date_from, e.kategorie))


def render_markdown(events: list[CatalystEvent], now: dt.datetime,
                    stats: dict) -> str:
    today = now.date()
    L = [f"# CATALYST-CALENDAR — {now.strftime('%Y-%m-%d %H:%M')} CEST", ""]
    L.append(f"_Datierte Ereignisse als Thesen-Input. Horizont bis "
             f"{stats.get('horizon','?')} · {len(events)} Eintraege_")
    L.append("")
    L.append("_Kat: 1=Regulierung/Frist 2=Auktion/Vergabe 3=IPO-Lockup "
             "4=Index-Umstellung 5=Kapazitaet/Zulassung_")
    L.append("")
    L.append("> **Ein Termin ist keine These.** Dieser Kalender liefert Rohstoff fuer "
             "Routine 9 — Konviktions-Gate und Crowdedness-Messung bleiben manuell.")
    L.append("")

    imminent = [e for e in events if e.status(today) == "imminent"]
    upcoming = [e for e in events if e.status(today) == "upcoming"]
    passed = [e for e in events if e.status(today) == "passed"]

    def block(title: str, items: list[CatalystEvent], note: str = "") -> None:
        if not items:
            return
        L.append(f"## {title}")
        if note:
            L.append(f"_{note}_")
        L.append("")
        for e in items:
            flag = "" if e.confidence == "verified" else f" [{e.confidence.upper()}]"
            dd = e.days_until(today)
            when = f"in {dd}d" if dd >= 0 else f"{-dd}d her"
            L.append(f"- **{e.date_str()}** ({when}) · Kat {e.kategorie} "
                     f"{KAT_LABEL.get(e.kategorie,'')}{flag}")
            L.append(f"  - {e.titel}")
            if e.tickers:
                L.append(f"  - Werte: {', '.join(e.tickers)}")
            if e.wirkung:
                L.append(f"  - Wirkung: {e.wirkung}")
            if e.quelle:
                L.append(f"  - _Quelle: {e.quelle}_" + (f" — {e.url}" if e.url else ""))
        L.append("")

    block(f"⏰ Einrueckend (<= {IMMINENT_DAYS} Tage)", imminent,
          "Bucket-0-relevant: hier entscheidet sich, ob eine These gebaut wird.")
    block("📅 Horizont", upcoming)
    block("✅ Abgelaufen", passed,
          "Aging-Kontrolle — im Journal-Sheet Termin-Radar auf 'erledigt' setzen.")

    L.append("---")
    L.append("_Collector-Statistik: " + " · ".join(
        f"{k}: {v}" for k, v in stats.get("collectors", {}).items()) + "_")
    return "\n".join(L)


def render_json(events: list[CatalystEvent], now: dt.datetime, stats: dict) -> str:
    today = now.date()
    return json.dumps({
        "schema": "catalyst-calendar/v1",
        "generated": now.isoformat(),
        "horizon": stats.get("horizon"),
        "counts": {
            "total": len(events),
            "imminent": sum(1 for e in events if e.status(today) == "imminent"),
            "upcoming": sum(1 for e in events if e.status(today) == "upcoming"),
            "passed": sum(1 for e in events if e.status(today) == "passed"),
        },
        "collectors": stats.get("collectors", {}),
        "events": [e.to_dict(today) for e in events],
    }, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------------------
# Orchestrierung
# ---------------------------------------------------------------------------

def run_collect(horizon_days: int, seeds_path: str, offline: bool = False
                ) -> tuple[list[CatalystEvent], dict]:
    today = dt.date.today()
    horizon = today + dt.timedelta(days=horizon_days)
    stats: dict = {"horizon": horizon.isoformat(), "collectors": {}}

    def guarded(name: str, fn: Callable[[], list[CatalystEvent]]) -> list[CatalystEvent]:
        """Jeder Collector einzeln gekapselt — Ausfall killt den Job nicht."""
        try:
            res = fn()
            stats["collectors"][name] = len(res)
            logger.info("collector %s: %d Events", name, len(res))
            return res
        except Exception as e:  # noqa: BLE001
            stats["collectors"][name] = f"FEHLER: {type(e).__name__}"
            logger.error("collector %s: FEHLER %s: %s", name, type(e).__name__, e)
            return []

    groups = [
        guarded("index_reviews", lambda: collect_index_reviews(today, horizon)),
        guarded("seeds", lambda: collect_seeds(seeds_path, today, horizon)),
    ]
    if not offline:
        groups.append(guarded("federal_register",
                              lambda: collect_federal_register(today, horizon)))
        groups.append(guarded("sec_lockups",
                              lambda: collect_sec_lockups(today, horizon)))
    else:
        logger.info("--offline: Netzwerk-Collectoren uebersprungen")

    return merge_events(groups), stats


def _now_berlin() -> dt.datetime:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:  # noqa: BLE001
        return dt.datetime.now()


def run_with_drive(args) -> int:
    from drive_writer import (build_drive_service, cleanup_old_files,
                              write_json_file, write_markdown_file)
    folder = os.environ.get("BRIEFING_FOLDER_ID")
    if not folder:
        logger.error("BRIEFING_FOLDER_ID env variable nicht gesetzt")
        return 1
    events, stats = run_collect(args.horizon_days, args.seeds, args.offline)
    now = _now_berlin()
    stamp = now.strftime("%Y-%m-%d-%H%M")
    svc = build_drive_service()
    write_markdown_file(svc, folder, f"{FILENAME_PREFIX}{stamp}.md",
                        render_markdown(events, now, stats))
    write_json_file(svc, folder, f"{FILENAME_PREFIX}{stamp}.json",
                    render_json(events, now, stats))
    cleanup_old_files(svc, folder, FILENAME_PREFIX, keep_count=KEEP_COUNT)
    logger.info("Catalyst-Calendar fertig: %d Events (%s)", len(events), stats["collectors"])
    return 0


def run_with_local_file(args) -> int:
    events, stats = run_collect(args.horizon_days, args.seeds, args.offline)
    now = _now_berlin()
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(render_markdown(events, now, stats))
    if args.json_output:
        with open(args.json_output, "w", encoding="utf-8") as f:
            f.write(render_json(events, now, stats))
    logger.info("Geschrieben nach %s (%d Events)", args.output, len(events))
    return 0


def smoke_test() -> int:
    """Prueft Erreichbarkeit der Netz-Collectoren, ohne Drive."""
    today = dt.date.today()
    horizon = today + dt.timedelta(days=DEFAULT_HORIZON_DAYS)
    ok = True
    det = collect_index_reviews(today, horizon)
    print(f"index_reviews (deterministisch): {len(det)} Events — OK")
    try:
        fr = collect_federal_register(today, horizon, terms=FEDERAL_REGISTER_TERMS[:1])
        print(f"federal_register: {len(fr)} Events — erreichbar")
    except Exception as e:  # noqa: BLE001
        print(f"federal_register: FEHLER {e}")
        ok = False
    if os.environ.get("SEC_CONTACT"):
        try:
            lk = collect_sec_lockups(today, horizon)
            print(f"sec_lockups: {len(lk)} Events — erreichbar")
        except Exception as e:  # noqa: BLE001
            print(f"sec_lockups: FEHLER {e}")
            ok = False
    else:
        print("sec_lockups: uebersprungen (SEC_CONTACT nicht gesetzt)")
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--horizon-days", type=int, default=DEFAULT_HORIZON_DAYS)
    p.add_argument("--seeds", default=DEFAULT_SEEDS_YAML)
    p.add_argument("--output", help="Lokaler Markdown-Output (kein Drive).")
    p.add_argument("--json-output", help="Zusaetzlicher lokaler JSON-Output.")
    p.add_argument("--offline", action="store_true",
                   help="Nur deterministische Collectoren (index_reviews, seeds).")
    p.add_argument("--smoke-test", action="store_true")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    if args.smoke_test:
        return smoke_test()
    if args.output:
        return run_with_local_file(args)
    return run_with_drive(args)


if __name__ == "__main__":
    sys.exit(main())
