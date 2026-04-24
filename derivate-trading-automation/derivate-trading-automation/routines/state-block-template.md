# STATE-Block Template für "Trading-Briefing Latest.gdoc"

Dies ist die Struktur, die im Google-Doc zwischen `# STATE START` und
`# STATE END` stehen muss. Wird von Matthias + Claude (im Chat) gepflegt,
wenn Trades eröffnet/geschlossen oder Watchlist-Einträge geändert werden.
Die Routines **lesen** den Block, schreiben aber nur unter `# STATE END`.

---

```markdown
# STATE START

## Offene Positionen

| # | Instrument | Richtung | Buy-In | TP1 / TP2 | SL orig / empf | Zeitstopp | Notiz |
|---|------------|----------|--------|-----------|----------------|-----------|-------|
| 39 | Physical Gold ETC (4 Stk) | LONG | 367,00€ | 415 / 455€ | 334 / 334€ | — | Gold-Cluster mit Avino-Watchlist beachten |
| 48 | CTS Eventim KO Long (65 Stk Rest) | LONG | 12,24€ | 16,74 / 20,74€ | 9,24 / 12,24€ (BE) | 2026-05-04 | Zeitstopp in 6 Handelstagen |
| 53 | ATOSS MS OE Turbo Long (290 Stk, WKN MM3SVQ7) | LONG | 2,57€ (Cert) | 2,75 / 3,19€ | 2,24€ | 2026-05-09 | Underlying Entry 82,10€, KO ~57,90€, Hebel 3,06x, Post-Q1-Beat |
| — | JPM Sparplan (Rest) | passiv | — | — | — | — | 315,55€, TEIL-GESCHL. |

Summe aktiv-offen: 3.009,90€ (+745,30€ ATOSS) | Portfolio gesamt 3.325,45€.

## Watchlist-Trigger

| Kandidat | Richtung | Trigger (Kurzform) | Status |
|----------|----------|-------|--------|
| Commerzbank (CBK) | LONG | A: Touch EMA50 Daily 33,40-33,60€ + Bounce · B: Daily-Close >35,10€ auf Vol ≥30D-Ø | ⚠️ aktiv — Note #9 |
| Jungheinrich (JUN3) | LONG | Reverse-Close ≥25,70€ ODER Hammer TH ≥25,70€ | Bodenbildung Mo/Di |
| Intel (INTC) | LONG | Pullback ~59$ + 4h-Reversal (nach Gap +28.9%) | warten 2-3 Tage |
| Procter & Gamble (PG) | LONG | A: Pullback 147,50-149,00$ + 4h-Reversal · B: Daily-Close >152$ | warten Mo/Di |
| Siemens Energy (ENR) | LONG | Pullback EMA20 ~167€ + Reversal + RSI<60 | Pullback-Only, kein ATH-Chase |
| Southwest (LUV) | SHORT | Daily-Close <36,85$ auf Vol ≥30D-Ø | Mo/Di (nicht Freitag-Bounce) |
| Deutsche Börse AG | LONG | Pullback 258€ + RSI Daily <60 | ⏸ RSI 74 überkauft |
| Drägerwerk Vz (DRW3) | LONG | nach 30.04.: Pullback RSI<55 + −10% vom ATH | 📅 01.05. |
| AIXTRON (AIXA) | SHORT | nach 30.04.: Rejection 44-45€, SL >46€ | 📅 28.04. Pre-Trade |
| Eckert & Ziegler (EUZ) | LONG | A: nach 12.05. >16,50€ + Vol · B: Pullback 13,50-14,00€ + Hammer | Re-Entry nach #52 |
| TUI AG | LONG | nach 13.05.: >7,50€ + Hormus-Deeskalation | 📅 13.05. |
| Adidas (ADS) | LONG | nach 29.04. neu bewerten | 📅 29.04. |
| Avino Silver (GV6) | LONG | A: >6,50€ Vol · B: EMA200 ~5,17€ + Reversal | Direktaktie, Gold-Cluster |
| Sanofi (SAN) | LONG | A: Pullback 80,30-80,50€ + Reversal · B: Close >83,20€ | ⚠️ Ex-Div 2026-05-05 |
| Salesforce (CRM) | SHORT | Pullback EMA20-Zone 182-185$ + Rejection | warten ~3-7 Tage |
| United Rentals (URI) | LONG | A: Pullback 900-920$ + Stabilisierung · B: Close >1.000$ | KO-Produkt prüfen |

## Offene Notes (relevant für Routinen)

- Trade #59 Milestone (20 Trades unter 2%-Regel) → Hit-Rate + Drawdown Review
- BTC #24 Zeitstopp 2026-04-27 vor FOMC (OTO-Stop 59.800€)
- BAT Bison 37.572 Stk: 2-Tranchen-Exit
- Crypto Tier-3 (XRP, ADA, AXS): Haltefrist-Fenster Juni/Juli 2026
- ATOSS #53 Mo-Review: Weekend-Gap-Szenario + Revenge-Trading-Reflexion (3 Sätze)

Letzte State-Aktualisierung: 2026-04-24 nach Trade #53 eröffnet

# STATE END
```

---

## Pflege-Regeln

**Wer ändert den STATE?**
- Matthias oder Claude im Chat (gemeinsam), wenn:
  - Neuer Trade eröffnet (neue Zeile in "Offene Positionen")
  - Trade geschlossen (Zeile entfernen)
  - TP1 erreicht → SL auf Breakeven nachziehen → STATE-Update
  - Watchlist-Eintrag neu/entfernt/Trigger geändert
- **Routines NIE** — sie lesen nur.

**Wann aktualisieren?**
- Sofort nach Trade-Eintrag im Journal (Excel).
- Watchlist-Änderungen: im selben Chat-Turn, wo sie beschlossen werden.

**Format-Disziplin:**
- Instrument-Namen konsistent (gleiche Schreibweise über Einträge hinweg)
- Underlying-Preise immer mit "€" bzw. "$", damit Routinen die Währung klar haben
- Triggers möglichst kurz: "Pullback X + Bounce" reicht, nicht 3 Sätze
- Bei Post-Earnings-Wartenden: `📅 Datum` Emoji fürs Auge

## Daten-Fluss-Diagramm

```
Matthias trades/changes                Chat (Matthias + Claude)
          │                                       │
          ▼                                       ▼
    Excel Journal               ←→          Google-Doc STATE
  (authoritative Wahrheit)                       (Read-Source für Routinen)
          │                                       │
          │                                       ▼
          │                              Routine liest STATE (08:45/15:45/20:30)
          │                                       │
          │                                       ▼
          │                              Routine schreibt LATEST BRIEFING ins Doc
          │                                       │
          │                                       ▼
          └──────────────────────────────→  Chat liest beides am nächsten Tag
```
