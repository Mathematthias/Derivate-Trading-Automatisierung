# Migration Notes - Pipeline-Architektur

## 2026-05-13 — Variante-A-Split (Tier B → B + C)

### Anlass

Tier B lief seit 2026-04-30 mit ~308 Symbolen in einem Pull. Ergebnis:
- 06.-08.05.: Schedule 4×/Tag, lief sauber durch
- 09.-11.05.: nur 1×/Tag gestartet, einige Runs gescheitert
- 12.05. 12:07: letzter erfolgreicher Run
- 13.05. 14:07 CEST: SSL-Crash beim Drive-Upload (`ssl.SSLEOFError: EOF
  occurred in violation of protocol`). yfinance-Pull war ok (305/306),
  Drive-Side hat den TLS-Stream gekappt, vermutlich Load-Balancer-side.

Tier A mit ~48 Symbolen alle 30 Min blieb stabil — der Größenfaktor war
der entscheidende Stressor.

### Was geändert wurde

**Universum-Split nach Geographie:**
- `tickers_tier_b.yaml` enthält jetzt nur das EU-Universum (~211 Symbole)
- `tickers_tier_c.yaml` neu, enthält das US-Universum NASDAQ-100 (~96 Symbole)

**Output-Tag-Konvention:**
- `MARKETDATA-FULL-STD-...` + `CANDIDATES-...`        — Tier A (unverändert)
- `MARKETDATA-FULL-EU-...`  + `GAMECHANGER-HUNT-EU-...` — Tier B (war: `-GC-`)
- `MARKETDATA-FULL-US-...`  + `GAMECHANGER-HUNT-US-...` — Tier C (neu)

**Workflow:**
- `tier_b_sync.yml` Header: EU-Scope dokumentiert, Schedule-Empfehlung 2×/Tag
- `tier_c_sync.yml` neu, identische Struktur

**Robustheit (alle drei Tiers):**
- `drive_writer.py`: `_with_retry()` wrappt jeden Drive-API-`.execute()`,
  fängt SSLEOFError + Connection-Errors + HTTP 5xx/429 mit Exponential-Backoff.
- `watchlist_sync.py`: gleiche Retry-Logik für STATE-Doc und Journal-Download
- `market_data.py`: `_yf_download_with_retry()` als Defensiv-Wrapper für
  yfinance; plus Logger-Silence für `_enrich_with_earnings` (Log-Hygiene gegen
  "No earnings dates found"-ERROR-Flut bei Werten ohne Earnings-History).
- `adhoc_scanner.py`: Catch erweitert um OSError/SSL-Fehler (Pipeline darf
  nicht wegen RSS-Hick-up sterben).

### Folge-TODOs (Skill-Side, NICHT in diesem Repo)

- `pipeline_utils.py` (im Skill `/mnt/skills/user/derivate-trading/`) muss
  die neuen Tags `EU` / `US` kennen — bisher kannte `select_latest_marketdata`
  nur `standard` und `gamechanger`. Suche-Queries auf den Drive müssen
  `GAMECHANGER-HUNT-EU-` und `GAMECHANGER-HUNT-US-` finden, nicht nur
  `GAMECHANGER-HUNT-`.
- Skill-`references/pipeline-integration.md` Tag-Tabelle anpassen.
- Briefing-Routinen (`scan_morning`/`scan_afternoon`/`scan_evening`) bei
  Bedarf um getrennte EU-/US-Frische-Checks erweitern.

### Erweiterungs-Roadmap (post-Stabilisierung)

Erst wenn 1-2 Wochen Tier B + Tier C ohne SSL-Crashes durchlaufen:

1. **S&P 100 ex-NDX** (~40 US-Werte) zu Tier C addieren — schließt Lücke bei
   Banken (JPM/BAC/WFC), Pharma (JNJ/PFE/LLY), Industrie (CAT/HON/RTX),
   Energie (XOM/CVX). Tier C wächst auf ~136 — unter 200er-Robustheitsschwelle.
2. **FTSE 50** (~50 UK-Werte) zu Tier B addieren — BP/Rio Tinto/Anglo/AstraZeneca/
   GSK/Glencore für Brent-/Pharma-/Mining-Coverage. Tier B wächst auf ~261 —
   nur sinnvoll, wenn UK-Quanto-Realität pro Setup geklärt (Memory Note #39
   sagt: Quanto-Probleme bei US-Einzelaktien; GBP wahrscheinlich ähnlich).

NICHT geplant: gesamtes S&P 500 oder Russell 2000 — KO-Handelbarkeit bei SB+/
Gettex nicht gegeben, und Mid-/Small-Cap-Coverage hat MDAX/SDAX schon.

---

## 2026-04-29 — Universe-Erweiterung (historisch)

### Was diese Aenderung bewirkt

Erweiterung des Pipeline-Universums von ~63 Werten (Tier A: 12 + Tier B: 53)
auf insgesamt ~330 Werte durch Aufnahme aller deutschen Index-Komponenten
plus NASDAQ-100, EuroStoxx 50 (ex-DAX) und SMI 20.

## Neue Tier-B-Sektionen

| Sektion | Werte | Inhalt |
|---|---|---|
| `dax_komponenten` | 39 | DAX 40 minus Rheinmetall |
| `mdax_komponenten` | 50 | komplett |
| `sdax_komponenten` | 70 | komplett |
| `nasdaq_100` | 97 | minus PDD/JD/Karteileichen |
| `eurostoxx_ex_dax` | 32 | EuroStoxx 50 ohne DAX-Doubletten und ohne Rheinmetall |
| `smi_20` | 20 | komplett |

**Gesamt neu: 308 Werte** (vor Konflikt-Check mit bestehenden Sektionen)

## Was unveraendert bleibt

- **Tier A komplett** (Indizes/Rohstoffe/Krypto/Positionen + nebenwerte_de mit 12 Werten)
- **Bestehende Tier-B-Sektionen** (biotech_de, ma_hot_list, ai_quantum, nasdaq_growth, tecdax_kern)

## Doubletten-Strategie

Pro Wert genau ein Eintrag in den neuen Index-Sektionen. Wenn ein Wert
in mehreren Indizes ist (z.B. SAP in DAX + EuroStoxx + TecDAX), erscheint
er nur in der Sektion mit hoechster Prioritaet (DAX > MDAX > SDAX), in
den anderen Sektionen wird er ausgelassen, im YAML-Kommentar markiert.

**Doubletten zu Tier-A-nebenwerte_de:** Werte werden in den neuen Sektionen
trotzdem aufgenommen (mit Kommentar `auch tier_a/nebenwerte_de`), da die
Pipeline beim yfinance-Pull dedupliziert. Falls die Pipeline NICHT
dedupliziert, im Skript fixen oder Tier-A-Werte hier auslassen.

**Konflikte mit bestehenden Tier-B-Sektionen:** vorerst belassen.
- `tecdax_kern` (10) wird hinfaellig - alle 30 TecDAX-Werte sind in
  DAX/MDAX/SDAX/tier_a abgedeckt. Sektion kann geloescht werden.
- `nasdaq_growth` (21) wird hinfaellig - alle Werte sind in `nasdaq_100`.
  Sektion kann geloescht werden.
- `biotech_de` (11): 4 Werte (Bayer, Merck_KGaA, Sartorius, Qiagen) sind
  jetzt in `dax_komponenten`, 4 weitere (Evotec, HelloFresh, Eckert_Ziegler,
  Formycon) in `sdax_komponenten`. Verbleibend: BioNTech, Curevac, MorphoSys
  (delistet pruefen).
- `ma_hot_list` (6): alle 6 Werte sind jetzt in DAX/MDAX/SDAX. Sektion
  kann geloescht oder als Tag-Filter weiterverwendet werden.
- `ai_quantum` (5): keine Doubletten, bleibt unveraendert.

## Offene Punkte / Verifikationen (Stand nach DAX-Verify 29.04.2026)

Alle vier urspruenglich offenen Punkte sind durch finanzen.net DAX-Fetch
geklaert:

1. **Sartorius:** NICHT im DAX. Sartorius VZ (SRT3.DE / DE0007165631) ist
   im MDAX. Stamm-Aktie nicht relevant.

2. **Porsche AG vs. Porsche SE:** Nur Porsche Automobil Holding SE
   (PAH3.DE / DE000PAH0038) im DAX. Porsche AG operative (P911.DE) im MDAX.

3. **Fresenius Medical Care (FME.DE) im DAX** ergaenzt (urspruenglich
   nicht in der Wissensliste).

4. **Scout24 (G24.DE) im DAX** ergaenzt (war frueher MDAX, mittlerweile DAX).

5. **Walmart in NASDAQ-100:** finanzen.net fuehrt Walmart (WMT) im NDX-Fetch.
   WMT ist NYSE-listed. Nicht aufgeloest - beim ersten Pull verifizieren.

## L-Konfidenz-Werte (manuelle Pruefung)

- `S9I.DE` (Shelly, BG-ISIN, SDAX) - Frankfurt-Listing-Ticker unsicher
- `M8G.DE` (Verve_Group, SE-ISIN, SDAX) - Frankfurt-Listing-Ticker unsicher
- `AMRZ.SW` (Amrize, Holcim-Spinoff 2025, SMI) - Ticker verifizieren
- `WMT` (Walmart, NASDAQ-100) - NDX-Aufnahme unklar

## Refactoring-Empfehlung (optional, naechste Session)

Nach erfolgreichem ersten Pull mit dem neuen Universum:
1. `tecdax_kern` und `nasdaq_growth` aus tickers_tier_b.yaml entfernen
   (komplett von neuen Sektionen abgedeckt).
2. `biotech_de` reduzieren auf nicht-Index-Biotech (BioNTech, Curevac).
3. `ma_hot_list` aufloesen oder zu `m_a_tags`-Filter umbauen.

## Naechster manueller Refresh

Quartalsweise (immer nach Index-Reviews der Deutschen Boerse):
- Dezember: Annual Review SMI/EuroStoxx
- September: Quartals-Review DAX-Familie + Annual Review NASDAQ-100/EuroStoxx
- Maerz, Juni: Quartals-Review DAX-Familie

Workflow: pro Index `https://www.finanzen.net/index/<X>/werte` aufrufen,
Tabelle hierher pasten, Skript neu laufen lassen.
