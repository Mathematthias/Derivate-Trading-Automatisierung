# STATE-Doc Erweiterungen V0.2 — Phase 0 Rebuild
# Stand: 2026-04-25
#
# === ARCHITEKTUR-WICHTIG ===
# STATE-Doc ist Single Source of Truth für Watchlist.
# Pipeline liest die Watchlist hier raus, NICHT aus tickers_tier_a.yaml.
# Du pflegst Watchlist-Änderungen ausschließlich hier — kein Repo-Push nötig.
#
# Neue Sektion 5: WATCHLIST mit Yahoo-Symbol — der Pipeline-Parser
# liest exakt diese Tabelle. Bestehende Watchlist-Tabelle in deinem STATE
# wird durch diese ersetzt (Symbol-Spalte ergänzt).

# ====================================================================
# Sektion 1: TICKER-MAP (NUR für Indizes/Rohstoffe/Krypto/Positionen)
# Die Watchlist ist NICHT mehr in dieser Tabelle, siehe Sektion 5.
# ====================================================================

## TICKER-MAP (Yahoo-Symbole für Pipeline-Referenz)

| Wert | Yahoo-Symbol | Kategorie |
|------|--------------|-----------|
| ATOSS Software | AOF.DE | Position #53 |
| CTS Eventim | EVD.DE | Position #48 |
| Xtrackers Physical Gold ETC | XAD5.DE | Position #39 |
| BTC-EUR | BTC-EUR | Krypto Bison |
| ETH-EUR | ETH-EUR | Krypto Bison |
| SOL-EUR | SOL-EUR | Krypto Bison |
| BNB-EUR | BNB-EUR | Krypto Bison |
| BAT-EUR | BAT-EUR | Krypto Bison (Yahoo dünn — Fallback BAT-USD) |

# ====================================================================
# Sektion 2: WATCHLIST mit Yahoo-Symbol-Spalte (ERWEITERTE bestehende Tabelle)
#
# WICHTIG: Diese Tabelle ersetzt die bestehende Watchlist-Tabelle in deinem STATE.
# Spalte "Symbol" ist neu — Pipeline liest sie für yfinance-Calls.
# Spalte "Trigger" wird vom Parser geparsed:
#   - "EMA20", "EMA50" → Indikator-Match
#   - "33,40-33,60€" → Preis-Korridor extrahiert
#   - "+ Bounce", "+ Reversal" → Bounce-Detection aktiv
#   - "RSI<60" → RSI-Schwellwert
#   - "Vol ≥30D-Ø" → Volumen-Validierung
# ====================================================================

## Watchlist-Trigger (aktive Einträge)

> **Pflege:** Tot-Einträge (✅ gelaufen, ❌ These geplatzt, 📉 Chart-not)
> aus dieser Tabelle entfernen und in Sektion "Watchlist-Archiv" verschieben.
> Pipeline ignoriert archivierte Einträge automatisch.
>
> **Status-Werte (definiert):**
> - ⚠️ aktiv — Trigger nah/in Reichweite, Pipeline meldet täglich
> - 📅 pending — Datum-Constraint noch nicht erreicht
> - ⏸ paused — Bedingung temporär nicht da (RSI/Vol/etc.)
> - 🔍 beobachten — passive (>10% entfernt), These intakt
>
> **Tot-Werte (→ Archiv):** ✅ gelaufen / ❌ These geplatzt / 📉 Chart-not bestätigt

| Kandidat | Symbol | Richtung | Trigger (Kurzform) | Status |
|----------|--------|----------|--------------------|--------|
| Commerzbank (CBK) | CBK.DE | LONG | A: Touch EMA50 Daily 33,40–33,60€ + Bounce · B: Daily-Close >35,10€ auf Vol ≥30D-Ø | ⚠️ aktiv — Note #9 |
| Jungheinrich (JUN3) | JUN3.DE | LONG | Reverse-Close ≥25,70€ ODER Hammer TH ≥25,70€ | ⚠️ aktiv — Bodenbildung Mo/Di |
| Intel (INTC) | INTC | LONG | Pullback ~59$ + 4h-Reversal (nach Gap +28.9%) | 🔍 beobachten — Trigger weit weg |
| Procter & Gamble (PG) | PG | LONG | A: Pullback 147,50–149,00$ + 4h-Reversal · B: Daily-Close >152$ | ⚠️ aktiv — warten Mo/Di |
| Siemens Energy (ENR) | ENR.DE | LONG | Pullback EMA20 ~167€ + Reversal + RSI<60 | ⚠️ aktiv — Pullback-Only |
| Southwest (LUV) | LUV | SHORT | Daily-Close <36,85$ auf Vol ≥30D-Ø | ⚠️ aktiv — Mo/Di |
| Deutsche Börse | DB1.DE | LONG | Pullback 258€ + RSI Daily <60 | ⏸ paused — RSI 74 überkauft |
| Drägerwerk Vz (DRW3) | DRW3.DE | LONG | nach 2026-04-30: Pullback RSI<55 + −10% vom ATH | 📅 pending — 2026-05-01 |
| AIXTRON (AIXA) | AIXA.DE | SHORT | nach 2026-04-30: Rejection 44–45€, SL >46€ | 📅 pending — 2026-04-28 Pre-Trade |
| Eckert & Ziegler (EUZ) | EUZ.DE | LONG | A: nach 2026-05-12 >16,50€ + Vol · B: Pullback 13,50–14,00€ + Hammer | 📅 pending — Re-Entry nach #52 |
| TUI AG | TUI1.DE | LONG | nach 2026-05-13: >7,50€ + Hormus-Deeskalation | 📅 pending — 2026-05-13 |
| Adidas (ADS) | ADS.DE | LONG | nach 2026-04-29 neu bewerten | 📅 pending — 2026-04-29 |
| Avino Silver (GV6) | GV6.F | LONG | A: >6,50€ Vol · B: EMA200 ~5,17€ + Reversal | ⚠️ aktiv — Gold-Cluster |
| Sanofi (SAN) | SAN.PA | LONG | A: Pullback 80,30–80,50€ + Reversal · B: Close >83,20€ | ⚠️ aktiv — ⚠️ Ex-Div 2026-05-05 |
| Salesforce (CRM) | CRM | SHORT | Pullback EMA20-Zone 182–185$ + Rejection | ⚠️ aktiv — warten ~3–7 Tage |
| United Rentals (URI) | URI | LONG | A: Pullback 900–920$ + Stabilisierung · B: Close >1.000$ | ⚠️ aktiv — KO-Produkt prüfen |
| Heidelberg Druck | HDD.DE | LONG | ONBERG-Story (Defense/Drohnenabwehr) — Setup ergänzen wenn relevant | 🔍 beobachten — niedriges Vol |

# ====================================================================
# Sektion 3: FRIDAY-SNAPSHOT (Fallback wenn Pipeline ausfällt)
# ====================================================================

## FRIDAY-SNAPSHOT 2026-04-25

> **Pflege:** Freitag 17:35 CET (Xetra-Schluss) — TradingView-Watchlist
> Werte hier eintragen. Pipeline nutzt diese Werte als Fallback, wenn
> yfinance-Sync ausfällt oder wenn Pipeline-Daten älter als 24h sind.

### Underlying-Closes Xetra (TradingView)
- ATOSS (AOF.DE):       82,20€   (+3,27%)
- CTS Eventim (EVD.DE): noch eintragen
- Xtrackers Gold (XAD5.DE): noch eintragen
- Commerzbank (CBK.DE): 33,89€   (Trigger-Zone A 33,40-33,60)
- DAX:                  24.055,06   (-0,02%)

### Cert-Closes Smartbroker+ / TR (eigene Positionen)
- ATOSS Turbo MM3SVQ7:  2,43€  (Buy 2,57€ → -5,4%)
- CTS Eventim KO:       noch eintragen

### Krypto-Closes (Bison/Kraken-Referenz)
- BTC-EUR:    noch eintragen
- ETH-EUR:    noch eintragen
- SOL-EUR:    noch eintragen
- BNB-EUR:    noch eintragen
- BAT-EUR:    noch eintragen

### Sync-Status
- Letzter Eintrag: 2026-04-25 (manuell)
- Nächste Pflege:  2026-04-30 (Mittwoch optional, wenn DAX >2% bewegt)

# ====================================================================
# Sektion 4: FILTER-OVERRIDE (manuelle Pipeline-Steuerung)
# ====================================================================

## FILTER-OVERRIDE

> **Pflege:** Bei Bedarf — z.B. wenn ein Wert besondere Aufmerksamkeit verdient.
> Pipeline-Filter zeigt diese Werte prominenter im CANDIDATES-Output, auch wenn
> sie nicht durch alle Filter durchkommen.

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
# Sektion 5: WATCHLIST-ARCHIV — ausgelagertes separates Doc
# ====================================================================

## Watchlist-Archiv

> **Wo:** Separates Google Doc `WATCHLIST-ARCHIV.md` im selben Drive-Ordner
> wie das STATE-Doc. Damit bleibt das STATE schlank.
>
> **Pflege:** Wenn ein aktiver Watchlist-Eintrag tot ist (✅/❌/📉),
> aus Sektion 2 entfernen und im separaten Archiv-Doc eintragen.
>
> **Pipeline-Verhalten:** Pipeline liest NUR die aktive Watchlist (Sektion 2).
> Das Archiv-Doc wird komplett ignoriert — es ist reine Lern-History.
>
> **Initial-Setup:** Vorlage `WATCHLIST_ARCHIV_template.md` im Repo
> (`marketdata-pipeline/config/`) als Drive-Doc anlegen.

# ====================================================================
# Sektion 6: PIPELINE-STATUS (zur Info)
# ====================================================================

## PIPELINE-STATUS

### Aktueller Stand
- **Roadmap-Phase:** 1 — Pipeline-Foundation (Build seit 2026-04-24)
- **Build-Schritte 1.0–1.5:** ✅ am 2026-04-26
- **Offen:** Build-Schritt 1.6 (Earnings + BaFin-Insider)
- **Geplant scharf:** Mo 2026-04-27 08:45 CET — erster Live-Lauf

### Build-Schritte (innerhalb Roadmap-Phase 1)
- [x] **Build 1.0:** Configs (tickers_a/b.yaml, filter_config.yaml, STATE-Watchlist mit Symbolen)
- [x] **Build 1.1:** Drive-Auth (Service Account)
- [x] **Build 1.2:** marketdata_sync.py (yfinance + zweistufige Filter-Engine)
- [x] **Build 1.3:** GitHub Actions (2× Workflows: tier-a + tier-b)
- [x] **Build 1.4:** V1.6-Routinen lesen Pipeline-Files (im Skill „Phase 4")
- [x] **Build 1.5:** Auto-Load bei Session-Start (im Skill „Phase 5")
- [ ] **Build 1.6:** Earnings-Kalender-Sync + BaFin-Insider-Scrape (separate wöchentliche Action)

### Roadmap-Folgephasen
- **Phase 2:** Push-Mail via Resend bei Gamechanger-Kriterien (~4–6 Wochen nach Phase-1-Stabilität)
- **Phase 3:** Krypto-Briefing-Integration mit `krypto-grid-trading` + `krypto-portfolio` Skills
