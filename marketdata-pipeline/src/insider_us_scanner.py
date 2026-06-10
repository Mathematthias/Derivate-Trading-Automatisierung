"""
insider_us_scanner.py — SEC-EDGAR-Form-4-Layer für die Trading-Pipeline (Paket C1).

Erschließt den US-Trigger-Pfad für die Setup-Klasse Insider-Buys-Cluster v0.1
(Journal-Note #48). Zieht für das Tier-C-Universum (NASDAQ-100, ~96 Symbole)
die Form-4-Filings der letzten N Tage aus SEC EDGAR, filtert auf
Open-Market-Käufe (transactionCode P), aggregiert pro Insider und erkennt
Cluster (≥2 Organmitglieder über Schwelle im Fenster). Resultat als
Markdown-File ins Workspace Drive — analog ADHOC-CATALYSTS-Konvention.

Design-Entscheidungen (Session 2026-06-10):
  1. Output:    eigenes File INSIDER-US-{datetime}.md, eigener Parser-Block
                in pipeline_utils.py
  2. Kadenz:    eigener Cron 1×/Tag ~07:00 CEST (cron-job.org →
                workflow_dispatch) — erfasst den kompletten US-Vortag
  3. Sells:     nur Cluster-Signal (≥2 Organe im Fenster) bzw. CEO/CFO groß
                + Earnings-Nähe. Einzel-Sells werden verworfen.
  4. 10b5-1:    erkennen und MARKIEREN (⚙️-Flag), nicht verwerfen —
                maschinenlesbare Checkbox <aff10b5One> seit SEC-Amendment 2023
  5. Schwelle:  fix 55.000 USD/Person (statt 50k€ + EURUSD-Umrechnung)
  6. Zeitlogik: KALENDERTAGE statt Handelstage (User-Entscheid 2026-06-10):
                - Earnings-Nähe-Flag: ±5 Kalendertage (Obermenge von ±3 HT,
                  exakte Note-#48-Prüfung bleibt in der manuellen Checkliste)
                - Cluster-Fenster = Scan-Fenster: 7 Kalendertage (≈ 5 HT)
                Kein Handelstags-Kalender nötig.

SEC Fair Access (https://www.sec.gov/os/accessing-edgar-data):
  - Pflicht: deklarativer User-Agent mit Kontakt → ENV SEC_CONTACT
    (Format: "Vorname Nachname email@domain.tld"). Ohne SEC_CONTACT bricht
    der Scanner ab — die SEC blockt anonyme Clients.
  - Max 10 req/s → hier gedrosselt auf ~6 req/s (THROTTLE_SECONDS).

Aufruf-Modi (analog adhoc_scanner.py):

1. Produktiv (GitHub-Action):
       python src/insider_us_scanner.py
   Erwartet GDRIVE_SA_KEY, BRIEFING_FOLDER_ID, SEC_CONTACT als ENV.

2. Smoke-Test (nur EDGAR-Erreichbarkeit, kein Drive):
       SEC_CONTACT="..." python src/insider_us_scanner.py --smoke-test

3. Local-File (Trockentest, Output als Datei):
       SEC_CONTACT="..." python src/insider_us_scanner.py --output ./out.md

WICHTIG: EDGAR-Endpoints sind plausibel angesetzt, aber NICHT live verifiziert
(Sandbox-Restriktion beim Bau, kein sec.gov-Zugriff). Beim ersten produktiven
Lauf Action-Log prüfen — Symptom-Tabelle im README-Abschnitt Insider-US.

Stand: 2026-06-10 v1 — Paket C1.
"""

from __future__ import annotations

import argparse
import dataclasses as dc
import datetime as dt
import json
import logging
import os
import sys
import time
from typing import Iterable, Optional
from xml.etree import ElementTree as ET

import requests

logger = logging.getLogger("insider_us_scanner")


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

# Schwellen — fixe USD-Beträge (Design-Entscheidung 5, kein FX-Bezug)
BUY_THRESHOLD_USD = 55_000        # je Insider, Summe P-Käufe im Fenster
SELL_THRESHOLD_USD = 55_000       # je Insider, für Cluster-Sell-Zählung
SELL_BIG_SINGLE_USD = 500_000     # CEO/CFO-Einzel-Sell gilt nur ab hier
CLUSTER_MIN_INSIDERS = 2          # Note #48: ≥2 Organmitglieder

# Zeitfenster — Kalendertage (Design-Entscheidung 6)
SCAN_WINDOW_DAYS = 7              # = Cluster-Fenster (≈ 5 HT)
EARNINGS_PROXIMITY_DAYS = 5       # ±5 KT ≈ ±3 HT (Obermenge)

# SEC-Endpoints
SEC_TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

HTTP_TIMEOUT = 20
THROTTLE_SECONDS = 0.17           # ~6 req/s, unter SEC-Limit 10 req/s

# Drive-Konvention
INSIDER_FILENAME_PREFIX = "INSIDER-US-"
INSIDER_KEEP_COUNT = 10

# Universum: Tier-C-YAML (NASDAQ-100)
DEFAULT_UNIVERSE_YAML = os.path.join(
    os.environ.get("CONFIG_DIR", "./config"), "tickers_tier_c.yaml"
)

# Rollen-Erkennung CEO/CFO aus officerTitle (lowercase-Match)
_CEO_CFO_MARKERS = (
    "chief executive", "ceo",
    "chief financial", "cfo",
)


# ---------------------------------------------------------------------------
# Datenmodell
# ---------------------------------------------------------------------------

@dc.dataclass
class InsiderTx:
    """Eine Form-4-Transaktionszeile (aggregierbar pro Owner)."""
    ticker: str
    issuer_name: str
    owner_name: str
    is_director: bool
    is_officer: bool
    officer_title: str            # "" wenn kein Officer
    code: str                     # "P" oder "S"
    date: dt.date
    shares: float
    price: float                  # 0.0 wenn nicht angegeben (z.B. Gift)
    value_usd: float              # shares × price
    is_10b5_1: bool               # Plan-Trade-Flag (Filing-Ebene)
    accession: str

    @property
    def role_label(self) -> str:
        if self.is_officer and self.officer_title:
            return self.officer_title
        if self.is_officer:
            return "Officer"
        if self.is_director:
            return "Director"
        return "10%-Owner/Sonstige"

    @property
    def is_ceo_cfo(self) -> bool:
        t = self.officer_title.lower()
        return any(m in t for m in _CEO_CFO_MARKERS)


@dc.dataclass
class OwnerAggregate:
    """Pro Insider und Richtung aggregierte Käufe/Verkäufe im Fenster."""
    owner_name: str
    role_label: str
    is_ceo_cfo: bool
    total_usd: float
    first_date: dt.date
    last_date: dt.date
    any_10b5_1: bool
    all_10b5_1: bool
    txs: list[InsiderTx]


@dc.dataclass
class IssuerSignal:
    """Cluster- oder Einzel-Signal pro Issuer."""
    ticker: str
    issuer_name: str
    direction: str                       # "BUY" | "SELL"
    owners: list[OwnerAggregate]
    total_usd: float
    window_start: dt.date
    window_end: dt.date
    is_cluster: bool
    # Earnings-Nähe (±EARNINGS_PROXIMITY_DAYS Kalendertage)
    earnings_near: bool = False
    earnings_date: Optional[str] = None  # ISO, das nähere von last/next
    earnings_kind: Optional[str] = None  # "last" | "next"


@dc.dataclass
class ScanResult:
    buy_clusters: list[IssuerSignal] = dc.field(default_factory=list)
    sell_signals: list[IssuerSignal] = dc.field(default_factory=list)
    single_buys: list[OwnerAggregate] = dc.field(default_factory=list)
    single_buy_tickers: dict[str, str] = dc.field(default_factory=dict)  # owner_key -> ticker
    filings_checked: int = 0
    filings_parsed: int = 0
    tickers_resolved: int = 0
    tickers_total: int = 0
    errors: list[str] = dc.field(default_factory=list)


# ---------------------------------------------------------------------------
# HTTP-Layer (SEC Fair Access)
# ---------------------------------------------------------------------------

def build_session() -> requests.Session:
    contact = os.environ.get("SEC_CONTACT", "").strip()
    if not contact or "@" not in contact:
        raise SystemExit(
            "SEC_CONTACT env fehlt oder enthält keine E-Mail. SEC Fair Access "
            "verlangt einen deklarativen User-Agent mit Kontakt, z.B. "
            'SEC_CONTACT="Max Mustermann max@example.org"'
        )
    s = requests.Session()
    s.headers.update({
        "User-Agent": f"Derivate-Trading-Pipeline insider_us_scanner ({contact})",
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json, text/xml, application/xml, */*;q=0.1",
    })
    return s


def _get(session: requests.Session, url: str) -> Optional[requests.Response]:
    """GET mit Throttle und 1 Retry bei transienten Fehlern. None bei Fail."""
    for attempt in (1, 2):
        try:
            time.sleep(THROTTLE_SECONDS)
            r = session.get(url, timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 500, 502, 503) and attempt == 1:
                logger.warning("HTTP %s auf %s — Retry in 3s", r.status_code, url)
                time.sleep(3)
                continue
            logger.warning("HTTP %s auf %s — übersprungen", r.status_code, url)
            return None
        except requests.RequestException as e:
            if attempt == 1:
                logger.warning("Request-Fehler %s auf %s — Retry", type(e).__name__, url)
                time.sleep(3)
                continue
            logger.warning("Request-Fehler %s auf %s — übersprungen", type(e).__name__, url)
            return None
    return None


# ---------------------------------------------------------------------------
# Universum + CIK-Mapping
# ---------------------------------------------------------------------------

def load_universe_tickers(yaml_path: str) -> list[str]:
    """Liest alle Ticker aus tickers_tier_c.yaml (categories → name: 'TICKER')."""
    import yaml
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    tickers: list[str] = []
    for cat in (data.get("categories") or {}).values():
        if isinstance(cat, dict):
            tickers.extend(str(v).strip() for v in cat.values() if v)
    # Dedupe, Reihenfolge stabil
    seen: set[str] = set()
    out = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def fetch_cik_map(session: requests.Session) -> dict[str, int]:
    """SEC company_tickers.json → {TICKER: CIK}. Leeres Dict bei Fail."""
    r = _get(session, SEC_TICKER_MAP_URL)
    if r is None:
        return {}
    try:
        raw = r.json()
    except json.JSONDecodeError:
        logger.error("company_tickers.json nicht parsebar")
        return {}
    out: dict[str, int] = {}
    # Format: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    for entry in raw.values():
        try:
            out[str(entry["ticker"]).upper()] = int(entry["cik_str"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


# ---------------------------------------------------------------------------
# Form-4-Discovery + Parse
# ---------------------------------------------------------------------------

def list_recent_form4(
    session: requests.Session, cik: int, cutoff: dt.date,
) -> list[dict]:
    """Liest data.sec.gov/submissions und liefert Form-4-Filings ab cutoff.

    Returns Liste von Dicts: {accession, primary_doc, filing_date}.
    """
    r = _get(session, SEC_SUBMISSIONS_URL.format(cik=cik))
    if r is None:
        return []
    try:
        recent = r.json()["filings"]["recent"]
        forms = recent["form"]
        accs = recent["accessionNumber"]
        dates = recent["filingDate"]
        docs = recent["primaryDocument"]
    except (KeyError, json.JSONDecodeError) as e:
        logger.warning("Submissions-JSON CIK %s unerwartet: %s", cik, e)
        return []
    out = []
    for form, acc, date_s, doc in zip(forms, accs, dates, docs):
        if form != "4":
            continue
        try:
            fdate = dt.date.fromisoformat(date_s)
        except ValueError:
            continue
        if fdate < cutoff:
            continue
        out.append({"accession": acc, "primary_doc": doc, "filing_date": fdate})
    return out


def _xml_url_candidates(base: str, primary_doc: str) -> list[str]:
    """Kandidaten-URLs fürs Raw-XML aus dem primaryDocument-Feld.

    Gotcha (Live-Befund 2026-06-10, 186/186 Fails im Erstlauf): Bei
    Ownership-Filings liefert die submissions-API als primaryDocument oft
    den Pfad in die XSL-gerenderte Viewer-Version, z.B.
    'xslF345X05/form4.xml'. Das Raw-XML liegt unter dem Basename OHNE
    xsl-Verzeichnis. Daher: Basename zuerst, gelieferten Pfad als Fallback.
    """
    out: list[str] = []
    doc_base = primary_doc.split("/")[-1]
    if doc_base.lower().endswith(".xml"):
        out.append(f"{base}/{doc_base}")
        if "/" in primary_doc:
            out.append(f"{base}/{primary_doc}")
    return out


def fetch_form4_xml(
    session: requests.Session, cik: int, accession: str, primary_doc: str,
) -> Optional[str]:
    """Holt das ownershipDocument-XML eines Filings.

    Reihenfolge: (1) Basename des primaryDocument (xsl-Prefix gestrippt),
    (2) primaryDocument wie geliefert, (3) Directory-index.json — erstes
    Nicht-Index-File mit .xml-Endung. Der index.json-Fallback läuft IMMER,
    wenn die direkten Kandidaten scheitern (v1-Bug: lief nur bei
    Nicht-.xml-Docs → 186/186 Fails, gefixt 2026-06-10).
    """
    acc_nodash = accession.replace("-", "")
    base = f"{SEC_ARCHIVES_BASE}/{cik}/{acc_nodash}"

    for url in _xml_url_candidates(base, primary_doc):
        r = _get(session, url)
        if r is not None and b"ownershipDocument" in r.content:
            return r.text

    # Fallback: Directory-Listing nach Raw-XML absuchen
    r = _get(session, f"{base}/index.json")
    if r is not None:
        try:
            items = r.json()["directory"]["item"]
        except (KeyError, json.JSONDecodeError):
            items = []
        for it in items:
            name = str(it.get("name", ""))
            if name.lower().endswith(".xml") and "index" not in name.lower():
                rx = _get(session, f"{base}/{name}")
                if rx is not None and b"ownershipDocument" in rx.content:
                    return rx.text
    return None


def _xml_text(node: Optional[ET.Element], default: str = "") -> str:
    return node.text.strip() if node is not None and node.text else default


def _xml_bool(node: Optional[ET.Element]) -> bool:
    return _xml_text(node).lower() in ("1", "true")


def parse_form4(xml_text: str, accession: str) -> list[InsiderTx]:
    """Parst ein ownershipDocument-XML zu InsiderTx-Zeilen (nur Codes P/S).

    Mehrere reportingOwner pro Filing möglich (Joint Filings) — alle Owner
    erhalten die Transaktionszeilen zugeordnet (konservativ; bei Joint
    Filings ist der Wert dem Cluster ohnehin gemeinsam zuzurechnen).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning("XML-Parse-Fehler %s: %s", accession, e)
        return []

    ticker = _xml_text(root.find(".//issuer/issuerTradingSymbol")).upper()
    issuer_name = _xml_text(root.find(".//issuer/issuerName"))
    # 10b5-1-Checkbox auf Dokument-Ebene (SEC-Amendment 2023)
    is_plan = _xml_bool(root.find(".//aff10b5One"))

    owners: list[dict] = []
    for ro in root.findall(".//reportingOwner"):
        rel = ro.find("reportingOwnerRelationship")
        owners.append({
            "name": _xml_text(ro.find("reportingOwnerId/rptOwnerName")),
            "is_director": _xml_bool(rel.find("isDirector")) if rel is not None else False,
            "is_officer": _xml_bool(rel.find("isOfficer")) if rel is not None else False,
            "officer_title": _xml_text(rel.find("officerTitle")) if rel is not None else "",
        })
    if not owners:
        return []

    txs: list[InsiderTx] = []
    for tx in root.findall(".//nonDerivativeTable/nonDerivativeTransaction"):
        code = _xml_text(tx.find("transactionCoding/transactionCode")).upper()
        if code not in ("P", "S"):
            continue
        date_s = _xml_text(tx.find("transactionDate/value"))
        try:
            tdate = dt.date.fromisoformat(date_s)
        except ValueError:
            continue
        try:
            shares = float(_xml_text(tx.find("transactionAmounts/transactionShares/value"), "0") or 0)
        except ValueError:
            shares = 0.0
        try:
            price = float(_xml_text(tx.find("transactionAmounts/transactionPricePerShare/value"), "0") or 0)
        except ValueError:
            price = 0.0
        value = shares * price
        for o in owners:
            txs.append(InsiderTx(
                ticker=ticker, issuer_name=issuer_name,
                owner_name=o["name"],
                is_director=o["is_director"], is_officer=o["is_officer"],
                officer_title=o["officer_title"],
                code=code, date=tdate, shares=shares, price=price,
                value_usd=value, is_10b5_1=is_plan, accession=accession,
            ))
    return txs


# ---------------------------------------------------------------------------
# Aggregation + Cluster-Logik
# ---------------------------------------------------------------------------

def _aggregate_owners(txs: list[InsiderTx], code: str) -> list[OwnerAggregate]:
    """Aggregiert Transaktionen eines Issuers pro Owner für einen Code."""
    by_owner: dict[str, list[InsiderTx]] = {}
    for t in txs:
        if t.code != code:
            continue
        # Nur Organmitglieder zählen (Note #48: Organe; 10%-Owner ohne
        # Organfunktion sind kein Cluster-Bestandteil)
        if not (t.is_director or t.is_officer):
            continue
        by_owner.setdefault(t.owner_name, []).append(t)

    out: list[OwnerAggregate] = []
    for name, otxs in by_owner.items():
        total = sum(t.value_usd for t in otxs)
        out.append(OwnerAggregate(
            owner_name=name,
            role_label=otxs[0].role_label,
            is_ceo_cfo=any(t.is_ceo_cfo for t in otxs),
            total_usd=total,
            first_date=min(t.date for t in otxs),
            last_date=max(t.date for t in otxs),
            any_10b5_1=any(t.is_10b5_1 for t in otxs),
            all_10b5_1=all(t.is_10b5_1 for t in otxs),
            txs=sorted(otxs, key=lambda t: t.date),
        ))
    out.sort(key=lambda o: -o.total_usd)
    return out


def evaluate_issuer(
    ticker: str, issuer_name: str, txs: list[InsiderTx],
) -> tuple[Optional[IssuerSignal], Optional[IssuerSignal], list[OwnerAggregate]]:
    """Liefert (buy_cluster, sell_signal, single_buys) für einen Issuer.

    Cluster-Fenster = Scan-Fenster (7 KT) — siehe Modul-Doku, Entscheidung 6.
    """
    buy_aggs = [o for o in _aggregate_owners(txs, "P") if o.total_usd >= BUY_THRESHOLD_USD]
    sell_aggs = [o for o in _aggregate_owners(txs, "S") if o.total_usd >= SELL_THRESHOLD_USD]

    buy_cluster: Optional[IssuerSignal] = None
    single_buys: list[OwnerAggregate] = []
    if len(buy_aggs) >= CLUSTER_MIN_INSIDERS:
        buy_cluster = IssuerSignal(
            ticker=ticker, issuer_name=issuer_name, direction="BUY",
            owners=buy_aggs,
            total_usd=sum(o.total_usd for o in buy_aggs),
            window_start=min(o.first_date for o in buy_aggs),
            window_end=max(o.last_date for o in buy_aggs),
            is_cluster=True,
        )
    else:
        single_buys = buy_aggs  # 0 oder 1 Eintrag

    sell_signal: Optional[IssuerSignal] = None
    if len(sell_aggs) >= CLUSTER_MIN_INSIDERS:
        sell_signal = IssuerSignal(
            ticker=ticker, issuer_name=issuer_name, direction="SELL",
            owners=sell_aggs,
            total_usd=sum(o.total_usd for o in sell_aggs),
            window_start=min(o.first_date for o in sell_aggs),
            window_end=max(o.last_date for o in sell_aggs),
            is_cluster=True,
        )
    else:
        # CEO/CFO-Einzel-Sell nur ab SELL_BIG_SINGLE_USD; Earnings-Nähe wird
        # nachgelagert geprüft und ist Pflichtbedingung (Memory-Regel).
        big = [o for o in sell_aggs if o.is_ceo_cfo and o.total_usd >= SELL_BIG_SINGLE_USD]
        if big:
            sell_signal = IssuerSignal(
                ticker=ticker, issuer_name=issuer_name, direction="SELL",
                owners=big,
                total_usd=sum(o.total_usd for o in big),
                window_start=min(o.first_date for o in big),
                window_end=max(o.last_date for o in big),
                is_cluster=False,
            )
    return buy_cluster, sell_signal, single_buys


# ---------------------------------------------------------------------------
# Earnings-Nähe (yfinance, nur für qualifizierte Signale)
# ---------------------------------------------------------------------------

def fetch_earnings_dates(ticker: str) -> tuple[Optional[dt.date], Optional[dt.date]]:
    """(last, next) Earnings-Datum via yfinance. (None, None) bei Fail.

    Eigener Mini-Pull statt MARKETDATA-File-Abhängigkeit — nur für die
    wenigen Signal-Ticker (typisch 0–5/Tag), Last vernachlässigbar.
    """
    try:
        import yfinance as yf
        edf = yf.Ticker(ticker).earnings_dates
        if edf is None or edf.empty:
            return None, None
        today = dt.date.today()
        dates = sorted({d.date() for d in edf.index})
        last = max((d for d in dates if d <= today), default=None)
        nxt = min((d for d in dates if d > today), default=None)
        return last, nxt
    except Exception as e:  # noqa: BLE001 — yfinance wirft bunt
        logger.warning("Earnings-Pull %s fehlgeschlagen: %s", ticker, e)
        return None, None


def annotate_earnings_proximity(sig: IssuerSignal) -> None:
    """Setzt earnings_near/earnings_date, wenn ein Trade-Datum des Signals
    ±EARNINGS_PROXIMITY_DAYS Kalendertage an last/next Earnings liegt."""
    last, nxt = fetch_earnings_dates(sig.ticker)
    trade_dates = {t.date for o in sig.owners for t in o.txs}
    best: Optional[tuple[int, dt.date, str]] = None
    for edate, kind in ((last, "last"), (nxt, "next")):
        if edate is None:
            continue
        for td in trade_dates:
            dist = abs((td - edate).days)
            if dist <= EARNINGS_PROXIMITY_DAYS and (best is None or dist < best[0]):
                best = (dist, edate, kind)
    if best is not None:
        sig.earnings_near = True
        sig.earnings_date = best[1].isoformat()
        sig.earnings_kind = best[2]


# ---------------------------------------------------------------------------
# Scan-Orchestrierung
# ---------------------------------------------------------------------------

def run_scan(window_days: int, universe_yaml: str) -> ScanResult:
    session = build_session()
    result = ScanResult()
    cutoff = dt.date.today() - dt.timedelta(days=window_days)

    tickers = load_universe_tickers(universe_yaml)
    result.tickers_total = len(tickers)
    cik_map = fetch_cik_map(session)
    if not cik_map:
        result.errors.append("company_tickers.json nicht ladbar — Scan abgebrochen")
        return result

    all_txs_by_issuer: dict[str, list[InsiderTx]] = {}
    issuer_names: dict[str, str] = {}

    for t in tickers:
        cik = cik_map.get(t.upper())
        if cik is None:
            logger.info("Kein CIK für %s — übersprungen", t)
            continue
        result.tickers_resolved += 1
        filings = list_recent_form4(session, cik, cutoff)
        for f in filings:
            result.filings_checked += 1
            xml = fetch_form4_xml(session, cik, f["accession"], f["primary_doc"])
            if xml is None:
                result.errors.append(f"{t}: XML nicht ladbar ({f['accession']})")
                continue
            txs = parse_form4(xml, f["accession"])
            if txs:
                result.filings_parsed += 1
                # Issuer-Ticker aus dem XML kann vom Universum-Ticker
                # abweichen (Aktienklassen) — Universum-Ticker führt.
                all_txs_by_issuer.setdefault(t.upper(), []).extend(txs)
                issuer_names.setdefault(t.upper(), txs[0].issuer_name)

    for tkr, txs in all_txs_by_issuer.items():
        buy_cluster, sell_signal, single_buys = evaluate_issuer(
            tkr, issuer_names.get(tkr, tkr), txs,
        )
        if buy_cluster:
            annotate_earnings_proximity(buy_cluster)
            result.buy_clusters.append(buy_cluster)
        if sell_signal:
            annotate_earnings_proximity(sell_signal)
            # CEO/CFO-Einzel-Sell NUR mit Earnings-Nähe (Memory-Regel);
            # Cluster-Sells immer.
            if sell_signal.is_cluster or sell_signal.earnings_near:
                result.sell_signals.append(sell_signal)
        for o in single_buys:
            key = f"{tkr}::{o.owner_name}"
            result.single_buy_tickers[key] = tkr
            result.single_buys.append(o)

    # Sortierung: Earnings-Nähe zuerst (bevorzugt, User-Entscheid), dann Volumen
    result.buy_clusters.sort(key=lambda s: (not s.earnings_near, -s.total_usd))
    result.sell_signals.sort(key=lambda s: (not s.earnings_near, -s.total_usd))
    result.single_buys.sort(key=lambda o: -o.total_usd)
    return result


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def _fmt_usd(v: float) -> str:
    return f"{v:,.0f} USD"


def _owner_line(o: OwnerAggregate) -> str:
    flag = " ⚙️10b5-1" if o.all_10b5_1 else (" ⚙️teilw. 10b5-1" if o.any_10b5_1 else "")
    dates = o.first_date.isoformat() if o.first_date == o.last_date else (
        f"{o.first_date.isoformat()}→{o.last_date.isoformat()}"
    )
    return f"  - {o.owner_name} ({o.role_label}) — {dates} · {_fmt_usd(o.total_usd)}{flag}"


def _signal_block(sig: IssuerSignal) -> list[str]:
    earn = ""
    if sig.earnings_near:
        earn = f" · 📅 Earnings {sig.earnings_date} ({sig.earnings_kind}, ±{EARNINGS_PROXIMITY_DAYS}KT)"
    kind = f"{len(sig.owners)} Insider" if sig.is_cluster else "CEO/CFO-Einzel-Sell"
    lines = [
        f"- **{sig.ticker}** ({sig.issuer_name}) — {kind}, "
        f"Σ {_fmt_usd(sig.total_usd)}, Fenster {sig.window_start.isoformat()}"
        f"→{sig.window_end.isoformat()}{earn}"
    ]
    lines.extend(_owner_line(o) for o in sig.owners)
    return lines


def render_markdown(result: ScanResult, now_berlin: dt.datetime) -> str:
    tz_label = now_berlin.strftime("%Z") or "CEST"
    L: list[str] = [
        f"# INSIDER-US — {now_berlin.strftime('%Y-%m-%d %H:%M')} {tz_label}",
        "",
        f"_Quelle: SEC EDGAR Form 4 · Universum: Tier C (NASDAQ-100) · "
        f"Fenster: {SCAN_WINDOW_DAYS} KT · Schwelle: {_fmt_usd(BUY_THRESHOLD_USD)}/Person · "
        f"Cluster: ≥{CLUSTER_MIN_INSIDERS} Organe · Code P=Open-Market-Kauf_",
        "",
    ]

    near = [s for s in result.buy_clusters if s.earnings_near]
    far = [s for s in result.buy_clusters if not s.earnings_near]

    if result.buy_clusters:
        L.append("## 🟢 Insider-Kauf-Cluster (Trigger-Pfad Note #48)")
        L.append("")
        if near:
            L.append(f"### 📅 Earnings-Nähe (±{EARNINGS_PROXIMITY_DAYS} KT) — BEVORZUGT")
            L.append("")
            for s in near:
                L.extend(_signal_block(s))
            L.append("")
        if far:
            L.append("### Ohne Earnings-Nähe")
            L.append("")
            for s in far:
                L.extend(_signal_block(s))
            L.append("")

    if result.sell_signals:
        L.append("## 🔴 Insider-Sell-Signale (Gegensignal-Check für Long-Kandidaten)")
        L.append("")
        for s in result.sell_signals:
            L.extend(_signal_block(s))
        L.append("")

    if result.single_buys:
        L.append(f"## ℹ️ Einzelkäufe ≥ Schwelle (kein Cluster — nur Kontext)")
        L.append("")
        for o in result.single_buys[:15]:
            tkr = next(
                (t for k, t in result.single_buy_tickers.items()
                 if k.endswith(f"::{o.owner_name}")), "?",
            )
            L.append(f"- **{tkr}** —" + _owner_line(o).lstrip()[1:])
        L.append("")

    if not (result.buy_clusters or result.sell_signals or result.single_buys):
        L.append("_Keine Insider-Signale über Schwelle im Fenster._")
        L.append("")

    L.append("---")
    L.append(
        f"_Stats: {result.tickers_resolved}/{result.tickers_total} Ticker→CIK "
        f"aufgelöst · {result.filings_checked} Form-4-Filings geprüft · "
        f"{result.filings_parsed} geparst · {len(result.errors)} Fehler_"
    )
    if result.errors:
        L.append("")
        L.append("```")
        L.extend(result.errors[:20])
        L.append("```")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# Entry-Points
# ---------------------------------------------------------------------------

def smoke_test() -> int:
    print("=== Smoke-Test: SEC-EDGAR-Endpoints ===\n")
    session = build_session()
    r = _get(session, SEC_TICKER_MAP_URL)
    print(f"→ company_tickers.json: {'✅' if r else '❌'}")
    cik_map = {}
    if r:
        cik_map = fetch_cik_map(session)
        print(f"  {len(cik_map)} Ticker im Mapping")
    aapl = cik_map.get("AAPL")
    if aapl:
        filings = list_recent_form4(session, aapl, dt.date.today() - dt.timedelta(days=14))
        print(f"→ submissions AAPL: ✅ ({len(filings)} Form-4 in 14d)")
        if filings:
            xml = fetch_form4_xml(session, aapl, filings[0]["accession"], filings[0]["primary_doc"])
            txs = parse_form4(xml, filings[0]["accession"]) if xml else []
            print(f"→ Form-4-XML: {'✅' if xml else '❌'} ({len(txs)} P/S-Zeilen geparst)")
    else:
        print("→ submissions: ❌ (kein AAPL-CIK)")
        return 1
    return 0


def run_with_drive(args) -> int:
    try:
        from drive_writer import build_drive_service, write_markdown_file, cleanup_old_files
    except ImportError as e:
        logger.error("Drive-Module nicht importierbar: %s — PYTHONPATH=./src gesetzt?", e)
        return 1
    briefing_folder_id = os.environ.get("BRIEFING_FOLDER_ID")
    if not briefing_folder_id:
        logger.error("BRIEFING_FOLDER_ID env variable nicht gesetzt")
        return 1

    result = run_scan(args.window_days, args.universe)

    try:
        from zoneinfo import ZoneInfo
        now_berlin = dt.datetime.now(ZoneInfo("Europe/Berlin"))
    except ImportError:
        now_berlin = dt.datetime.now()

    filename = f"{INSIDER_FILENAME_PREFIX}{now_berlin.strftime('%Y-%m-%d-%H%M')}.md"
    md = render_markdown(result, now_berlin)

    drive_service = build_drive_service()
    logger.info("Writing %s to Drive folder %s ...", filename, briefing_folder_id)
    write_markdown_file(drive_service, briefing_folder_id, filename, md)
    cleanup_old_files(drive_service, briefing_folder_id,
                      INSIDER_FILENAME_PREFIX, keep_count=INSIDER_KEEP_COUNT)
    logger.info(
        "Insider-US-Scan fertig: %d Buy-Cluster, %d Sell-Signale, %d Einzelkäufe.",
        len(result.buy_clusters), len(result.sell_signals), len(result.single_buys),
    )
    return 0


def run_with_local_file(args) -> int:
    result = run_scan(args.window_days, args.universe)
    now = dt.datetime.now()
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(render_markdown(result, now))
    logger.info("Scan abgeschlossen, geschrieben nach %s", args.output)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Lokaler Output-Pfad (Trockentest, kein Drive).")
    parser.add_argument("--window-days", type=int, default=SCAN_WINDOW_DAYS,
                        help=f"Scan-/Cluster-Fenster in Kalendertagen (default {SCAN_WINDOW_DAYS}).")
    parser.add_argument("--universe", default=DEFAULT_UNIVERSE_YAML,
                        help="Pfad zur Universum-YAML (default Tier C).")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    if args.smoke_test:
        return smoke_test()
    if args.output:
        return run_with_local_file(args)
    return run_with_drive(args)


if __name__ == "__main__":
    sys.exit(main())
