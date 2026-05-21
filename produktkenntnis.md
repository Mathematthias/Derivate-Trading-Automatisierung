# STATE-Dokument — Struktur und Pflege-Regeln

Das **STATE-Dokument** ist die einzige persistierende Datei im Ordner
`Trading/Briefing/`. Es wird von Matthias + Claude (im Chat) manuell
gepflegt und ausschließlich von den Routinen **gelesen**.

Alle Briefings und Scans entstehen als **neue Daily-Docs**, nicht als
Updates an einem persistenten Dokument. Grund: Der Google-Drive-MCP-
Connector hat nur `create_file`, kein Update/Append/Delete.

## Dateiname und Speicherort

- **Google Doc Name:** `STATE` (ohne Datum, ohne Versionssuffix)
- **Ordner:** `Trading/Briefing/`
- **Alternative Namen** erkennt die Routine nicht. Muss exakt `STATE` heißen.

## Inhalt

```markdown
# STATE START

## Offene Positionen

| # | Instrument | Richtung | Buy-In | TP1 / TP2 | SL orig / empf | Zeitstopp | Notiz |
|---|------------|----------|--------|-----------|----------------|-----------|-------|
| 39 | Physical Gold ETC (4 Stk) | LONG | 367,00€ | 415 / 455€ | 334 / 334€ | — | Gold-Cluster mit Avino-Watchlist |
| 48 | CTS Eventim KO Long (65 Stk Rest) | LONG | 12,24€ | 16,74 / 20,74€ | 9,24 / 12,24€ (BE) | 2026-05-04 | Zeitstopp in 6 Handelstagen |
| 53 | ATOSS MS OE Turbo Long (290 Stk, WKN MM3SVQ7) | LONG | 2,57€ (Cert) | 2,75 / 3,19€ | 2,24€ | 2026-05-09 | Underlying Entry 82,10€, KO ~57,90€, Hebel 3,06x, Post-Q1-Beat |
| — | JPM Sparplan (Rest) | passiv | — | — | — | — | 315,55€, TEIL-GESCHL. |

Summe aktiv-offen: 3.009,90€ | Portfolio gesamt: 3.325,45€ (inkl. JPM).

## Watchlist-Trigger

| Kandidat | Richtung | Trigger (Kurzform) | Status |
|----------|----------|--------------------|--------|
| Commerzbank (CBK) | LONG | A: Touch EMA50 Daily 33,40–33,60€ + Bounce · B: Daily-Close >35,10€ auf Vol ≥30D-Ø | ⚠️ aktiv — Note #9 |
| Jungheinrich (JUN3) | LONG | Reverse-Close ≥25,70€ ODER Hammer TH ≥25,70€ | Bodenbildung Mo/Di |
| Intel (INTC) | LONG | Pullback ~59$ + 4h-Reversal (nach Gap +28.9%) | warten 2–3 Tage |
| Procter & Gamble (PG) | LONG | A: Pullback 147,50–149,00$ + 4h-Reversal · B: Daily-Close >152$ | warten Mo/Di |
| Siemens Energy (ENR) | LONG | Pullback EMA20 ~167€ + Reversal + RSI<60 | Pullback-Only, kein ATH-Chase |
| Southwest (LUV) | SHORT | Daily-Close <36,85$ auf Vol ≥30D-Ø | Mo/Di (nicht Freitag-Bounce) |
| Deutsche Börse AG | LONG | Pullback 258€ + RSI Daily <60 | ⏸ RSI 74 überkauft |
| Drägerwerk Vz (DRW3) | LONG | nach 2026-04-30: Pullback RSI<55 + −10% vom ATH | 📅 2026-05-01 |
| AIXTRON (AIXA) | SHORT | nach 2026-04-30: Rejection 44–45€, SL >46€ | 📅 2026-04-28 Pre-Trade |
| Eckert & Ziegler (EUZ) | LONG | A: nach 2026-05-12 >16,50€ + Vol · B: Pullback 13,50–14,00€ + Hammer | Re-Entry nach #52 |
| TUI AG | LONG | nach 2026-05-13: >7,50€ + Hormus-Deeskalation | 📅 2026-05-13 |
| Adidas (ADS) | LONG | nach 2026-04-29 neu bewerten | 📅 2026-04-29 |
| Avino Silver (GV6) | LONG | A: >6,50€ Vol · B: EMA200 ~5,17€ + Reversal | Direktaktie, Gold-Cluster |
| Sanofi (SAN) | LONG | A: Pullback 80,30–80,50€ + Reversal · B: Close >83,20€ | ⚠️ Ex-Div 2026-05-05 |
| Salesforce (CRM) | SHORT | Pullback EMA20-Zone 182–185$ + Rejection | warten ~3–7 Tage |
| United Rentals (URI) | LONG | A: Pullback 900–920$ + Stabilisierung · B: Close >1.000$ | KO-Produkt prüfen |

## Offene Notes (relevant für Routinen)

- **#2** Trade #59 Milestone (20 Trades unter 2%-Regel) → Hit-Rate + Drawdown Review
- **#3** BTC #24 Zeitstopp 2026-04-27 vor FOMC (0,0112 BTC @ 63.500€ Limit-Buy, OTO-Stop 59.800€)
- **#4** Helper `ju.suggest_trail_sl()` implementieren (ab ~8 offenen Positionen)
- **#6** BAT Bison 37.572 Stk: 2-Tranchen-Exit-Plan (Disposition Effect aktiv)
- **#7** Crypto Tier-3 (XRP, ADA, AXS): Haltefrist-Fenster Juni/Juli 2026
- **#9** ⚠️ Commerzbank Trigger aktiv (Pullback-Level in Reichweite)
- **#10** ATOSS #53 Mo-Review: Weekend-Gap-Szenario + Revenge-Trading-Reflexion

---

**Letzte State-Aktualisierung:** 2026-04-24 nach Trade #53 eröffnet
**Maintainer:** Matthias + Claude (Chat)

# STATE END
```

## Pflege-Regeln

**Wer ändert STATE?**
- Matthias manuell, oder
- Claude generiert den neuen Inhalt im Chat, Matthias kopiert in STATE.gdoc.

**Routinen** schreiben NIE in STATE. Sie lesen nur.

**Wann ändern?**
- Sofort nach Trade-Eintrag im Journal (Excel)
- TP1 erreicht → SL auf Breakeven → STATE-Update
- Watchlist-Eintrag neu/entfernt/Trigger geändert
- Offene Notes resolved oder neu

**Format-Disziplin:**
- Instrumente konsistent benennen (gleiche Schreibweise)
- Preise mit Währungskennzeichen (€/$)
- Trigger kurz halten (1 Satz pro Trigger)
- Datums-Wartenden: 📅-Emoji
- "Letzte Aktualisierung"-Zeile am Ende immer updaten

## Fallback wenn Chat STATE nicht updaten kann

Wenn `create_file` kein `update` erlaubt, kann Claude im Chat nicht direkt
den STATE-Inhalt ändern. Workflow:
1. Claude generiert **neuen vollen STATE-Text** als Code-Block im Chat
2. Matthias öffnet `STATE.gdoc` in Google Docs
3. Cmd/Ctrl+A (alles markieren), Löschen
4. Neuen Text einfügen
5. Speichert automatisch

Alternative bei stabilem Claude-Web-Access in Phase 2: manuelles
Update-Script lokal (Python + Google Drive API mit eigenen Credentials).

## Data-Flow-Diagramm

```
                              ┌──────────────────┐
                              │  Excel Journal   │
                              │ (authoritative)  │
                              └────────┬─────────┘
                                       │
                                       │ manuell synchronisiert
                                       ▼
                  ┌────────────────────────────────────┐
                  │  STATE.gdoc in Drive               │
                  │  (read-only für Routinen)          │
                  └────────────────────────────────────┘
                                       │
                                       │ gelesen von
                          ┌────────────┼────────────┐
                          ▼            ▼            ▼
                   ┌──────────┐ ┌──────────┐ ┌──────────┐
                   │Morning   │ │Scan 15:45│ │Scan 20:30│
                   │Check     │ │          │ │          │
                   └─────┬────┘ └─────┬────┘ └─────┬────┘
                         │            │            │
                         │ create_file│ create_file│ create_file
                         ▼            ▼            ▼
                   ┌──────────────────────────────────────┐
                   │ Trading/Briefing/                    │
                   │ ├── Briefing-2026-04-28              │
                   │ ├── Scan-2026-04-28-1545             │
                   │ └── Scan-2026-04-28-2030             │
                   └──────────────────────────────────────┘
                                       │
                                       │ gelesen beim Chat-Start
                                       ▼
                            ┌─────────────────────┐
                            │ Projekt-Chat        │
                            │ (Kryptoinvestments) │
                            └─────────────────────┘
```
