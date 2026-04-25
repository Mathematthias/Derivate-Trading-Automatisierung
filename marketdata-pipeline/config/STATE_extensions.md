# STATE-Doc Erweiterungen — Phase 0 Output
# Stand: 2026-04-25
#
# In dein bestehendes STATE-Doc unten anhängen (zwischen die existierenden
# Sektionen einsortieren). Inhalt initial füllen mit aktuellem Stand.
#
# Diese Sektionen sind Brücke zwischen STATE-Doc und der Pipeline:
# - Pipeline LIEST: Filter-Override-Sektion, Friday-Snapshot (Fallback)
# - Du PFLEGST: Friday-Snapshot freitags, Filter-Override bei Bedarf
# - Routinen LESEN: alle Sektionen
#
# WICHTIG: Pipeline schreibt NICHT ins STATE-Doc. STATE bleibt dein Dokument,
# exklusiv. Pipeline schreibt nur in MARKETDATA-*.md und CANDIDATES-*.md.

# ====================================================================
# Sektion 1: TICKER-MAP (kopiere & paste die folgenden Zeilen ins STATE)
# ====================================================================

## TICKER-MAP (Yahoo-Symbole für interne Referenz)

| Wert | Yahoo-Symbol | Kategorie |
|------|--------------|-----------|
| ATOSS Software | AOF.DE | Position #53 |
| CTS Eventim | EVD.DE | Position #48 |
| Xetra-Gold ETC | 4GLD.DE | Position #39 |
| Commerzbank | CBK.DE | Watchlist Long |
| Drägerwerk | DRW3.DE | Watchlist Long |
| Heidelberg Druck | HDD.DE | Watchlist Long (ONBERG) |
| Jenoptik | JEN.DE | Watchlist Long |
| AIXTRON | AIXA.DE | Watchlist Long |
| Eurofins | ERF.PA | Watchlist Long (Paris-Listing primär) |
| TUI | TUI1.DE | Watchlist Long |
| Adidas | ADS.DE | Watchlist Long |
| Symrise | SY1.DE | Watchlist Long |
| Jungheinrich VZ | JUN3.DE | Watchlist Long |
| SAP | SAP.DE | Watchlist Long |
| Salzgitter | SZG.DE | Watchlist SHORT |
| Lufthansa | LHA.DE | Watchlist SHORT |
| Fraport | FRA.DE | Watchlist Long/Short |
| KION | KGX.DE | Watchlist SHORT |
| Intel | INTC | Watchlist (invalidiert nach Q1) |
| Krypto BTC/ETH/SOL/BNB/BAT | BTC-EUR / ETH-EUR / SOL-EUR / BNB-EUR / BAT-EUR | Krypto |

# ====================================================================
# Sektion 2: FRIDAY-SNAPSHOT (Fallback wenn Pipeline ausfällt)
# ====================================================================

## FRIDAY-SNAPSHOT 2026-04-25

> **Pflege:** Freitag 17:35 CET (Xetra-Schluss) — TradingView-Watchlist
> Werte hier eintragen. Pipeline nutzt diese Werte als Fallback, wenn
> yfinance-Sync ausfällt oder wenn Pipeline-Daten älter als 24h sind.
>
> **Format:** Position/Ticker | Close | Tagesveränderung %

### Underlying-Closes Xetra (TradingView)
- ATOSS (AOF):        82,20€   (+3,27%)
- CTS Eventim (EVD):  noch eintragen
- Xetra-Gold (4GLD):  noch eintragen
- Commerzbank (CBK):  33,89€   (Trigger-Zone A 33,40-33,60)
- DAX:                24.055,06   (-0,02%)

### Cert-Closes Smartbroker+ / TR (eigene Positionen)
- ATOSS Turbo MM3SVQ7: 2,43€  (Buy 2,57€ → -5,4%)
- CTS Eventim KO:      noch eintragen
- 4GLD ETC:            n/a (ETC ist Underlying selbst)

### Krypto-Closes (Bison/Kraken-Referenz)
- BTC-EUR:    noch eintragen
- ETH-EUR:    noch eintragen
- SOL-EUR:    noch eintragen
- BNB-EUR:    noch eintragen
- BAT-EUR:    noch eintragen

### Sync-Status
- Letzter Eintrag: 2026-04-25 (manuell)
- Nächste Pflege:  2026-04-30 (Mittwochs auch optional, wenn DAX >2% bewegt)

# ====================================================================
# Sektion 3: FILTER-OVERRIDE (manuelle Pipeline-Steuerung)
# ====================================================================

## FILTER-OVERRIDE

> **Pflege:** Bei Bedarf — z.B. wenn ein Wert besondere Aufmerksamkeit verdient.
> Pipeline-Filter zeigt diese Werte prominenter im CANDIDATES-Output, auch wenn
> sie nicht durch alle Filter durchkommen.
>
> **Format:** Ticker | Override-Typ | Begründung | gültig bis

### Aktive Overrides

| Ticker | Override-Typ | Begründung | Gültig bis |
|--------|-------------|------------|------------|
| CBK.DE | priority_long | Trigger A 33,40-33,60 sehr nah, Note #9 | 2026-05-02 |
| DRW3.DE | wait_for | Vollzahlen 30.04 abwarten, dann Pullback-Check | 2026-05-07 |
| BTC-EUR | priority_short | Position #24 Zeitstopp 27.04 vor FOMC | 2026-04-29 |
| HDD.DE | priority_long | ONBERG-Story (Defense/Drohnenabwehr), Vol ~1,6M EUR — Liquiditäts-Bypass nötig | 2026-06-30 |

### Override-Typen
- `priority_long`: Wert immer in CANDIDATES anzeigen, auch wenn Filter-Bucket leer
- `priority_short`: dito für Short-Setup
- `wait_for`: Wert NICHT in CANDIDATES bis Datum, dann re-evaluate
- `disqualified`: Wert NIE in CANDIDATES (z.B. Skandal, Übernahme-Stop)

# ====================================================================
# Sektion 4: PIPELINE-STATUS (Read-Only, zur Info)
# ====================================================================

## PIPELINE-STATUS

> Pipeline schreibt nicht hierher. Du hältst Stand der Pipeline-Builds fest.

### Aktuelle Phase
- **Aktueller Stand:** Phase 0 fertig (Configs, STATE-Erweiterung)
- **Nächste Phase:** Phase 1 — Drive-Service-Account (Sonntag)
- **Geplant scharf:** Mo 2026-04-27 — V1.6-Routinen mit Pipeline-Daten

### Phase-Übersicht
- [x] **Phase 0:** Configs (tickers_a/b.yaml, filter_config.yaml, STATE)
- [ ] **Phase 1:** Drive-Auth (Service Account)
- [ ] **Phase 2:** marketdata_sync.py (yfinance + Filter-Engine)
- [ ] **Phase 3:** GitHub Actions (2× Workflows: tier-a + tier-b)
- [ ] **Phase 4:** V1.6-Routinen (lesen MARKETDATA + CANDIDATES)
- [ ] **Phase 5:** Chat-Custom-Instruction (Auto-Load bei Session-Start)
- [ ] **Phase 6:** Earnings-Kalender-Sync (separate wöchentliche Action)
