# marketdata-pipeline

GitHub-Action-basierte Pipeline für Marktdaten-Sync und Setup-Vorauswahl.

## Was macht das?

GitHub-Actions ziehen via yfinance Marktdaten für Watchlist + erweiterte Universen
und schreiben Markdown-Dateien nach Workspace Shared Drive `Trading-Pipeline/Briefing/`.

Architektur seit 2026-05-13 (siehe `docs/MIGRATION_NOTES.md` — Variante-A-Split):

| Tier | Inhalt | Symbole | Frequenz (cron-job.org) |
|------|--------|---------|---------------------------|
| Tier A | Watchlist + Indizes/Rohstoffe/Krypto/Positionen | ~48 | alle 30 Min Mo-Fr 08-21h + Sa 10:00 |
| Tier B | EU-Universum (DAX + MDAX + SDAX + EuroStoxx + SMI) | ~211 | Mo-Fr 08:30 + 15:00 |
| Tier C | US-Universum (NASDAQ-100) | ~96 | Mo-Fr 14:30 + 21:30 |

Output pro Lauf (zwei Dateien):

| Tier | Marketdata-File | Candidates-File |
|------|-----------------|------------------|
| A | `MARKETDATA-FULL-STD-{datetime}.md` | `CANDIDATES-{datetime}.md` |
| B | `MARKETDATA-FULL-EU-{datetime}.md`  | `GAMECHANGER-HUNT-EU-{datetime}.md` |
| C | `MARKETDATA-FULL-US-{datetime}.md`  | `GAMECHANGER-HUNT-US-{datetime}.md` |

Candidates-Files (Stufe 2 für alle Tiers) enthalten:
- **Stufe 1:** Status der STATE-Watchlist-Trigger (nur Tier A)
- **Stufe 2:** Neue Kandidaten aus Universe-Setup-Filter (Tier A: Watchlist-Vorfilter,
  Tier B/C: echte Gamechanger-/PEAD-Suche über das jeweilige Geographie-Universum)
- **Override-Werte:** priority_long/short Werte mit aktuellem Snapshot

## Build-Status (Roadmap-Phase 1)

Diese Pipeline ist Roadmap-Phase 1 („Pipeline-Foundation"). Build-Schritte
nachfolgend. Roadmap-Übersicht: siehe Top-Repo-`README.md`.

- [x] **Build 1.0:** Configs (yamls + STATE-Erweiterung + Architektur-Doku)
- [x] **Build 1.1:** Drive-Service-Account + GitHub Secret `GDRIVE_SA_KEY`
- [x] **Build 1.2:** Skript `marketdata_sync.py` (yfinance + zweistufige Filter-Engine)
- [x] **Build 1.3:** GitHub Actions Workflows (tier_a + tier_b + tier_c)
- [x] **Build 1.4:** V1.6-Routinen lesen Pipeline-Files (im Skill „Phase 4")
- [x] **Build 1.5:** Auto-Load bei Session-Start (im Skill „Phase 5")
- [x] **Build 1.6:** Variante-A-Split (Tier B → B + C) + SSL-Retry-Robustheit (2026-05-13)
- [x] **Build 1.7:** Anomaly-Layer V1 — Gap, ATR-Z, Volumen-Z, NR7 (2026-05-15, Note #50)
- [ ] **Build 1.8:** Earnings-Kalender-Sync + BaFin-Insider-Scrape (separate wöchentliche Action)
- [ ] **Build 2.0:** Anomaly-Layer V2 — Peer-Divergenz (siehe `../ROADMAP.md`)

> Der `derivate-trading`-Skill referenziert die Schritte 1.4 und 1.5 historisch
> als „Phase 4" / „Phase 5". Das ist Skill-intern stabil dokumentiert und
> bleibt erhalten — neue Doku verwendet das Build-Schema hier.

## Files

```
Repo-Root/
├── .github/workflows/                   ← Repo-Root, NICHT in marketdata-pipeline!
│   ├── tier_a_sync.yml                  ← alle 30 Min Mo-Fr + Sa 10:00
│   ├── tier_b_sync.yml                  ← EU-Universum, Mo-Fr 2× täglich
│   └── tier_c_sync.yml                  ← US-Universum, Mo-Fr 2× täglich (seit 2026-05-13)
└── marketdata-pipeline/
    ├── README.md                        ← du bist hier
    ├── requirements.txt                 ← Python-Dependencies
    ├── config/
    │   ├── tickers_tier_a.yaml          ← Indizes/Rohstoffe/Krypto/Positionen
    │   ├── tickers_tier_b.yaml          ← EU-Universum
    │   ├── tickers_tier_c.yaml          ← US-Universum (seit 2026-05-13)
    │   ├── filter_config.yaml           ← Setup-Schwellwerte
    │   ├── catalyst_seeds.yaml          ← kuratierte Termine für den Termin-Radar
    │   ├── STATE_extensions.md          ← STATE-Doc-Erweiterungen
    │   └── WATCHLIST_ARCHIV_template.md ← Vorlage für Drive-Archiv-Doc
    ├── src/
    │   ├── marketdata_sync.py           ← Main-Skript, Entry-Point
    │   ├── state_parser.py              ← STATE-Doc lesen + Watchlist parsen
    │   ├── market_data.py               ← yfinance-Pull + Indikatoren
    │   ├── filter_engine.py             ← Stufe 1 + Stufe 2
    │   ├── output_renderer.py           ← Markdown-Output erzeugen
    │   ├── drive_writer.py              ← Drive-Upload via Service-Account
    │   ├── insider_us_scanner.py        ← SEC-EDGAR-Form-4-Layer (Paket C1)
    │   └── catalyst_calendar_sync.py    ← Termin-Radar (Thesen-Zufuhr, seit 2026-08-04)
    └── docs/
        └── architecture.md              ← Wie die Filter-Engine arbeitet
```

## Single Source of Truth

| Datenart | Pflege wo |
|----------|-----------|
| Indizes/Rohstoffe/Krypto | `tickers_tier_a.yaml` (selten ändern) |
| Offene Positionen | `tickers_tier_a.yaml` (bei Trade-Eröffnung/Schluss) |
| **Aktive Watchlist** | **STATE-Doc (Workspace Shared Drive)** — NICHT yaml |
| **Watchlist-Archiv** | **WATCHLIST-ARCHIV-Doc (Drive)** — separates Doc |
| Filter-Schwellwerte | `filter_config.yaml` (Tuning) |
| **Kuratierte Termine** | **`catalyst_seeds.yaml`** — handgepflegt, überlebt jeden API-Ausfall |
| Filter-Override | STATE-Doc Sektion 4 |

## Anpassungen ohne Code-Push

- Watchlist-Wert hinzufügen/ändern → STATE-Doc editieren
- Filter-Schwellwert ändern → `filter_config.yaml` editieren + Repo-Push
- Override aktivieren → STATE-Doc Sektion 4

## Manueller Test (nach Push)

GitHub Action manuell auslösen:
1. `https://github.com/Mathematthias/Derivate-Trading-Automatisierung/actions`
2. Links den Workflow `Marketdata Sync Tier A` wählen
3. Rechts oben **`Run workflow`** → **`Run workflow`**
4. ~2 Minuten warten, dann in Drive `Trading-Pipeline/Briefing/` nachschauen

## Termin-Radar (catalyst_calendar_sync.py, seit 2026-08-04)

**Warum es das gibt.** Zwischen 2026-06-30 und 2026-08-04 entstand fünf Wochen lang keine
neue Handels-These. Die Ursache war strukturell: Die Pipeline liefert ATR-Distanzen, RRprox
und Setup-Flags — sie hat **kein Feld für „warum sollte das steigen"** und kann keins haben.
Die belastbarste These im Journal (#156, China/Seltene Erden) ist dagegen ein *Kalendereintrag*:
Sie lebt von einem Datum, nicht von einer Meinung, und hatte deshalb als einzige eine
terminierte Aktion. Dieser Job liefert genau diesen Rohstoff.

**Was er ausdrücklich NICHT tut:** bewerten. Ein Termin ist keine These. Konviktions-Gate und
Crowdedness-Messung bleiben manuell (Skill `references/deep-research-weekly.md`, Routine 9).

**Vier Collectoren, absteigend nach Verlässlichkeit:**

| Collector | Netz? | Confidence | Liefert |
|---|---|---|---|
| `index_reviews` | nein | `verified` | DAX/Nasdaq-100/MSCI-Termine aus publizierten Kalenderregeln — rechenbar, nicht recherchierbar |
| `seeds` | nein | aus YAML | kuratierte Termine aus `config/catalyst_seeds.yaml` |
| `federal_register` | ja | `verified`/`heuristic` | US-Regulierung mit `effective_on` (freie JSON-API, kein Key) |
| `sec_lockups` | ja | `heuristic` | IPO-Lockups aus 424B4 — Datum = Filing + 180 Tage, **geschätzt** |

Jeder Collector ist einzeln gekapselt: Fällt einer aus, wird das im Log als
`collector <name>: FEHLER` protokolliert und der Job läuft mit den übrigen weiter
(additiv wie GAMECHANGER, kein globaler Fallback).

**Output:** `CATALYST-CALENDAR-{datetime}.md` und `.json` im Briefing-Ordner, `keep_count=10`.
Der Markdown-Output ist in drei Aging-Blöcke gegliedert — **Einrückend** (≤28 Tage,
Bucket-0-relevant), **Horizont**, **Abgelaufen**. Der Abgelaufen-Block ist die Aging-Kontrolle:
Er verhindert, dass der Radar so verrottet, wie es dem Thesen-Log passiert ist
(zwei Re-Check-Termine verstrichen unbemerkt, Journal-Note #234).

**Lokal testen (ohne Drive, ohne Netz):**

```bash
cd marketdata-pipeline
CONFIG_DIR=./config PYTHONPATH=./src python src/catalyst_calendar_sync.py \
    --offline --output /tmp/cal.md --json-output /tmp/cal.json
```

**Erreichbarkeit der Netz-Collectoren prüfen:**

```bash
CONFIG_DIR=./config PYTHONPATH=./src python src/catalyst_calendar_sync.py --smoke-test
```

⚠️ **Vor dem ersten produktiven Lauf:** Die HTTP-Endpoints (federalregister.gov,
efts.sec.gov) wurden beim Bau **nicht live verifiziert** — gleiche Einschränkung wie bei
`insider_us_scanner.py` (Paket C1). Die deterministischen Collectoren laufen garantiert;
im Action-Log die Zeilen `collector <name>: N Events` prüfen.

## Wichtige Pipeline-Konstanten

In den Workflows:
- `STATE_DOC_ID = 1ZVmRDY1vQdw_5dv6X7GtqSym5MSnPlvp`
- `BRIEFING_FOLDER_ID = 1_oQBr6KH7u6FDCAUIs1liTnEFjn-b_Ht`
- Health-Check-Threshold: 80% der Ticker müssen erfolgreich sein

Falls IDs sich ändern, in Workflow-Files updaten.
