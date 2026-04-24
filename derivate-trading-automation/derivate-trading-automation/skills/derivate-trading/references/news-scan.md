# News-Scan & Hidden Catalyst Scan — Referenz

**Diese Datei wird geladen bei:**
- "News-Scan" / "Skandal-Scan" / "aktuelle Thesen" → Routine 8
- "Hidden Scan" / "Randnotizen" / "was hat keiner auf dem Schirm" / "tiefer suchen" → Routine 8b
- **"Insider-Verkäufe" / "Sells-Check" / "Short-Dealings" / "Cluster-Verkäufe" → Routine 8c**

**🚨 AUSFÜHRUNGSREGEL: NICHT fragen. NICHT erklären. SOFORT ausführen.**

---

## ⚠️ Pflicht-Schritt 0 — Watchlist-Abgleich (gilt für 8, 8b, 8c)

**Bevor ein Kandidat ausgegeben wird**, wird sein Name (und ggf. Kürzel/Ticker) gegen die Watchlist abgeglichen. Grund: Watchlist-Einträge haben bereits durchdachte Trigger und Thesen — sie sind **keine neuen Kandidaten**, und wenn sie erneut auftauchen, ist die relevante Information „Trigger jetzt erreicht / noch nicht" — nicht „hier ist eine neue Idee".

**Implementation:**

```python
match = ju.match_watchlist(wb, kandidat_name)
if match:
    # Output-Format siehe unten — NICHT als neuer Kandidat!
```

**Output bei Watchlist-Match (ersetzt den normalen Kandidaten-Block):**

```
🔔 WATCHLIST-TREFFER — nicht als neuer Kandidat
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Kandidat: [Name] — [Long/Short]
Auf Watchlist seit: [Datum]
Trigger:  [Trigger-Text aus Watchlist]
Status:   [aktueller Status aus Watchlist]
Check:    [Ist der Trigger JETZT erreicht? 🟢/🟡/⏸]
Aktion:   [volle Checkliste JETZT / weiter warten / invalidiert → remove]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Nur wenn der **Watchlist-Trigger jetzt tatsächlich erreicht ist**, geht der Kandidat in die volle 7/7-Checkliste — mit dem Hinweis, dass es ein Watchlist-Trigger-Hit ist, nicht ein News-/Hidden-/Insider-Scan-Hit. Dem User ist damit klar, dass die These schon vorher vereinbart war.

---

## Routine 8: News-Scan (Schlagzeilen)

**Zweck:** Identifikation von Trade-Kandidaten aus offensichtlichen News-Flows (Earnings-Überraschungen, Gewinnwarnungen, Analyst-Upgrades/Downgrades, Skandale, M&A).

**Universums-Stufen** (siehe SKILL.md § Handelsuniversum):
- **Stufe 1 (Default):** DAX, MDAX, SDAX, Scale, Euronext, LSE, SIX, Nordics
- **Stufe 2 (Auto-Fallback):** NYSE, Nasdaq + Asia-ADRs — aktiviert wenn Stufe 1 < 2 reife Kandidaten
- **Stufe 3 (nur auf Codewort „Asien-Scan" oder expliziten Makro-Trigger):** Nikkei, Hang Seng

**Vorfilter (alle Stufen):**
- Meldung max. **48h alt**
- Kursreaktion bisher **<15%** (Late-Entry-Schutz — Lektion 8)
- Bei Stufe 2/3: Produktverfügbarkeits-Vorstufe (Quanto-KO auf Gettex/SB+?) vor voller Checkliste

### Pre-Signal-Check-Reihenfolge (Pflicht vor Kandidaten-Bewertung)

Bei jedem Kandidaten **in dieser Reihenfolge** prüfen, bevor die News-These bewertet wird. Grund: News-Katalysator kommt zuletzt, nicht zuerst — sonst klingt jede Schlagzeile nach Trade.

1. **30d-Move** (primäre Late-Entry-Metrik): >15% = stärkeres Setup nötig. **Nicht YTD verwenden** — zeitvariant (im Januar ~2 Wochen, im Dezember ~12 Monate) und deshalb als Timing-Filter ungeeignet.
2. **52W-Hoch-Abstand**: Am ATH = wenig Raum nach oben. 10–30% unter Hoch = komfortabler Puffer.
3. **RSI (Daily)**: <60 für Long-Kandidaten erwünscht; >70 = überkauft, nicht einsteigen.
4. **EMA-Staffelung**: Kurs über EMA20>EMA50>EMA100>EMA200 = gesunder Uptrend. Andernfalls Trend-Zustand einordnen, bevor gekauft wird.
5. **News-Katalysator erst jetzt bewerten**: Hat der Markt die Information schon eingepreist (Rally vor der Meldung) oder ist noch Reaktion offen?

**Makro-Phasen-Beobachtung:** Nach abrupten Makro-Wenden (z.B. Iran-Hormus-Öffnung 17.04.2026) sind News-Scan-Long-Kandidaten systemisch Late-Entries — der Markt hat die Information im Vorfeld der Schlagzeile verarbeitet. In solchen Phasen: Pullbacks abwarten oder Short-Setups priorisieren.

### Ablauf (SOFORT starten)

1. **Primär-Websuche (Stufe 1):** `DAX MDAX SDAX Aktie Kurseinbruch Skandal Gewinnwarnung heute [aktuelles Datum]`
2. **Websuche:** `[auffälliger Kandidat] Aktie Ursache [aktuelles Datum]` (nur wenn konkreter Kandidat aus Schritt 1)
3. **Sekundär-Websuche (Stufe 2 — automatisch bei <2 reifen Stufe-1-Kandidaten):** `S&P 500 Nasdaq biggest movers earnings surprise [aktuelles Datum]`
4. **Stufe 3 nur auf Codewort „Asien-Scan"** oder expliziten Makro-Trigger aus Makro-Check (BoJ/PBoC-Event, China-Stimulus): `Nikkei Hang Seng movers [aktuelles Datum]`
5. **Watchlist-Abgleich (Pflicht — Schritt 0 oben):** Jeder Kandidat durch `ju.match_watchlist(wb, name)`. Bei Treffer → Watchlist-Treffer-Format, nicht Kandidaten-Format.
6. Ausgabe im NEWS-SCAN-Format, Kandidaten mit Stufen-Kennzeichnung

### Output-Format

```
NEWS-SCAN [Datum]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Kandidat: [Name] — [Short/Long] — [Stufe 1|2|3]
Meldung:  [1 Satz, Quelle, Datum]
Kursreaktion: [%] — [noch nicht / teilweise / voll eingepreist]
Produkt (Stufe 2/3): [Quanto-KO verfügbar ✅/❌/zu prüfen]
Vorcheckliste: [X/7 vorläufig]
Empfehlung: [GO zur vollen Checkliste / SKIP]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Standard: 2–3 Websuchen für reine Stufe 1; 4–5 wenn Stufe 2 automatisch triggert; 5–6 bei explizitem Asien-Scan.

---

## Routine 8b: Hidden Catalyst Scan

**Zweck:** Kursrelevante Informationen finden, die noch **NICHT** in den Kursen eingepreist sind. Der Edge entsteht durch Informationsvorsprung gegenüber dem breiten Markt, nicht durch Reaktion auf bereits sichtbare Schlagzeilen.

**Zielsektoren:** SDAX, Scale, Nebenmarkt (weniger Analysten-Coverage = mehr Edge). **Bei dünner DE-Lage** (Schicht 1 + 2 liefern nichts): **Schicht 2b für US-Insider** aktivieren.

**Credit-Hinweis (Regel 18):** 3–5 Suchen nötig — tiefer als Standard-Scan.

### Vorfilter (Hidden Catalyst = strenger als News-Scan)

- Meldung max. **48h alt**
- Kursreaktion bisher **<5%** (Markt hat noch nicht reagiert)
- Bevorzugt SDAX/Scale/Nebenmarkt
- Mindestens 1 bestätigender Faktor (Chart, Sektor, Timing)

### 4 Schichten der Suche

**Schicht 1 — EQS/DGAP Ad-hoc Pflichtmeldungen (IMMER):**
- Websuche: `DGAP Ad-hoc Meldung heute [aktuelles Datum] Nebenwert Deutschland`
- Alternative: `EQS-News Ad-hoc [aktuelles Datum] SDAX`
- Ziel: Aufträge, Beteiligungen, strategische Entscheidungen, Prognoseänderungen, noch nicht eingepreist

**Schicht 2 — WpHG §40 Insider-Käufe / Directors' Dealings (IMMER):**
- Websuche: `Insider Kauf WpHG Directors Dealings Deutschland [aktueller Monat Jahr]`
- BaFin-Datenbank: https://www.bafin.de/DE/PublikationenDaten/Datenbanken/DirectorsDealings/
- Ziel: Käufe von Insidern als Frühindikator. **Cluster-Verkäufe** (CEO + CFO) = Warnsignal; Einzelverkäufe ignorieren.
- Hinweis: Seit 01.01.2026 Schwelle bei 50.000 € (vorher 20.000 €)

**Schicht 2b — SEC Form 4 / US-Insider-Käufe (Stufe 2, auf Wunsch oder bei leerer Schicht 1+2):**
- Websuche: `OpenInsider cluster buys [aktueller Monat Jahr]`
- Primärquelle: https://openinsider.com/top-insider-purchases-of-the-month
- Alternative: https://finviz.com/insidertrading.ashx?tc=7 (Cluster Buys Filter)
- Cluster-Logik identisch zu BaFin (CEO+CFO, seriell, Großvolumen ≥ 500k USD)
- **Produktverfügbarkeits-Vorstufe beachten** bevor Kandidat in volle Checkliste geht

**Schicht 3 — Behörden-Entscheidungen (auf Wunsch):**
- Websuche: `Kartellamt Freigabe [Monat Jahr]` oder `BaFin Entscheidung [Monat Jahr]`
- Ziel: M&A-Katalysatoren, Zulassungen (FDA, EMA)

**Schicht 4 — Sektor-Frühindikatoren (auf Wunsch):**
- Baltic Dry Index, Gasflüsse (GIE AGSI), Rohstoff-Moves, FDA-Kalender
- Ziel: Trendwende in Sektor-Daten bevor sich Einzeltitel bewegen

### 6 Hidden-Catalyst-Muster

1. **Stiller Großauftrag** — Auftragseingang ohne PR-Kampagne
2. **Insider kauft nach Kursrückgang** — Eigenkapital-Signal
3. **Kartellamt-Freigabe für Übernahme** — M&A-Katalysator
4. **Behörden-Zulassung** (BaFin, FDA, EMA) vor Bekanntheit
5. **Sektor-Frühdaten drehen** (z.B. Baltic Dry dreht hoch → Bulk-Shipping)
6. **EU-Vergabe-Gewinner** — öffentliche Ausschreibung still gewonnen

### Watchlist-Abgleich (Pflicht)

Vor Output jeder Kandidaten-Karte: `ju.match_watchlist(wb, name)`. Bei Treffer → Watchlist-Treffer-Format statt Hidden-Catalyst-Block (siehe Schritt 0 oben).

### Output-Format

```
HIDDEN CATALYST SCAN [Datum]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Schicht [1/2/3/4] — [Quellentyp]

Kandidat: [Name] — [Short/Long]
Meldung: [1 Satz, Quelle, Datum der Meldung]
Kursreaktion bisher: [%] — [noch nicht / teilweise / voll eingepreist]
Warum keiner es sieht: [1 Satz]
Vorcheckliste: [X/7 vorläufig]
Empfehlung: [GO zur vollen Checkliste / SKIP]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Routine 8c: Insider-Verkäufe-Scan (Short-Kandidaten & Short-Gegenindikator)

**Zweck:** Cluster-Verkäufe von Insidern als Short-Signal nutzen — und gleichzeitig laufende Short-Positionen gegen Insider-Käufe stresstesten (Invers-Check).

**Trigger:** "Insider-Verkäufe", "Sells-Check", "Short-Dealings", "Cluster-Verkäufe prüfen" oder proaktiv wenn News-Scan/Hidden-Scan keine reifen Short-Kandidaten liefert.

**Credit-Hinweis (Regel 18):** 2–4 Suchen.

### Filter: Was zählt als Short-Signal?

**Grundregel:** Einzelverkäufe IGNORIEREN — zu viele harmlose Gründe (Steueroptimierung, Diversifikation, Scheidung, Immobilienkauf). Nur Cluster haben echten Informationsgehalt.

**Cluster-Definition (mind. 1 der 3 Kriterien muss erfüllt sein):**
1. **CEO + CFO + mind. 1 weitere Führungskraft** verkaufen binnen 14 Tagen
2. **Gleicher Insider verkauft 3+ Mal** innerhalb von 30 Tagen (serielles Abstoßen)
3. **Großvolumen ≥ 500.000 €** Einzelverkauf von CEO/CFO ohne Zusammenhang mit Optionsprogramm-Ablauf

**Kontext-Filter (zusätzlich):**
- Bei Rally nach starkem Aufwärtsmove: weniger aussagekräftig (normale Mitnahmen)
- Bei Aktie am Allzeithoch mit wenig Rücksetzer: Signal stärker
- Verkäufe während Closed Period (Schweigeperiode vor Earnings): sehr starkes Signal
- Steht ein Aktienrückkaufprogramm im Gegensatz dazu? (Unternehmen kauft, Insider verkaufen = gemischtes Signal)

### Ablauf (SOFORT starten)

1. **Websuche (Stufe 1 — DE):** `Insider Verkauf Directors Dealings Deutschland [aktueller Monat Jahr]`
2. **Websuche (Stufe 1 — DE):** `Cluster Insiderverkauf CEO CFO DAX MDAX [aktueller Monat Jahr]`
3. **Stufe 2 — US (auf Wunsch oder bei dünner DE-Lage):** `OpenInsider cluster sells [aktueller Monat Jahr]`
4. Optional — falls spezifischer Kandidat aus 1–3: gezielte Suche nach Analyst-Einschätzung und Earnings-Datum
5. Datenquellen prüfen:
   - **Eulerpool (DE):** https://eulerpool.com/insiderverkaeufe (aggregiert, Cluster-Tagging)
   - **BaFin Directors' Dealings (DE):** Primärquelle
   - **OpenInsider (US):** https://openinsider.com/top-insider-sales-of-the-month — Cluster-Sells mit SEC-Form-4-Primärdaten
   - **Finviz Insider (US):** https://finviz.com/insidertrading.ashx?tc=1 (Cluster Sales Filter)
6. **Watchlist-Abgleich (Pflicht — Schritt 0 oben):** Jeder Kandidat durch `ju.match_watchlist(wb, name)`. Bei Treffer → Watchlist-Treffer-Format statt Short-Kandidaten-Block.
7. Ausgabe im Format unten — bei Stufe-2-Kandidaten Produktverfügbarkeit als Zusatzzeile

### Output-Format

```
INSIDER-VERKÄUFE-SCAN [Datum]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Kandidat: [Name] — Short
Cluster-Typ: [CEO+CFO / seriell / Großvolumen]
Meldungen:
  - [Datum]: [Person, Rolle] verkauft X Aktien zu Y € = Z €
  - [Datum]: [Person, Rolle] verkauft ...
Kursreaktion bisher: [%] — [noch nicht / teilweise / voll eingepreist]
Kontext: [Aktie nahe ATH / Closed Period / Aktienrückkaufprogramm aktiv / …]
Aktien-Rückkauf-Gegensignal: [Ja / Nein]
Vorcheckliste: [X/7 vorläufig]
Empfehlung: [GO zur vollen Short-Checkliste / SKIP]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Invers-Check: Insider-**Käufe** gegen laufende Shorts

Bei bestehenden Short-Positionen **zusätzlich** prüfen:
- Kaufen Insider des Short-Underlyings nach Kurseinbruch? → **Warnsignal gegen Short**
- Das ist ein klassisches Übertreibungs-Reversal-Muster (Beispiel LHA 20.03.2026: Insider-Kauf 250.510 € nach Pilotenstreik bei −6% Wochenverlust)

**Handlung:** Short-Position auf Rejection-Signal prüfen — SL nach oben ziehen, Teil-Exit erwägen, oder Position schließen wenn mehrere Warnsignale zusammenkommen.

**Output-Zusatz bei offenen Shorts:**
```
⚠️ INSIDER-CHECK FÜR OFFENE SHORTS:
- [Short #xx, Underlying]: [Insider-Käufe ja/nein] — [Handlungsempfehlung]
```

### Übergang zur Standard-Short-Checkliste

Sobald ein Cluster-Verkauf ein Short-Kandidat wird (GO-Signal):
→ Signal-Checkliste 7/7 + **Counter-These-Checkliste** (SKILL.md) durchlaufen. Cluster-Verkäufe allein reichen nicht — die Short-These braucht immer noch technisches Setup, R:R, und Counter-These-Prüfung.

---

## Zusammenspiel 8 + 8b + 8c

- **Routine 8** findet die offensichtlichen Moves (Earnings-Shocks, Skandale) — Kandidaten die der Markt bereits sieht, aber noch nicht voll eingepreist hat
- **Routine 8b** findet die unentdeckten Long/Short-Moves — Kandidaten vor der Schlagzeilen-Welle (Ad-hoc + Insider-Käufe + Behörden + Sektordaten)
- **Routine 8c** findet Short-Kandidaten durch **Cluster-Verkäufe** von Insidern — und schützt bestehende Shorts durch Invers-Check auf Insider-**Käufe**
- Ideal: erst 8, dann 8b als Vertiefung. 8c gezielt für Short-Ideen oder als Sicherheits-Check für laufende Short-Positionen.

---

## Übergang zur Standard-Checkliste

Sobald ein Kandidat GO-Signal hat (≥ 5/7 in der Vorcheckliste):
→ Normale Signal-Checkliste (7/7) + Counter-These + Trade-Plan-Template aus SKILL.md durchlaufen.

**Keine Abkürzungen.** Jeder Trade braucht die volle Pre-Trade-Prüfung.

---

## Quellen-Landkarte (Schnellzugriff)

| Quelle | URL / Ticker | Was | Stufe |
|--------|--------------|-----|-------|
| EQS/DGAP Ad-hoc | https://www.eqs-news.com/ | Ad-hoc-Meldungen, Corporate News | 1 |
| BaFin Directors' Dealings | https://www.bafin.de/DE/PublikationenDaten/Datenbanken/DirectorsDealings/ | Insider-Käufe/Verkäufe DE | 1 |
| Eulerpool Insider (Käufe) | https://eulerpool.com/insiderkaeufe | Aggregierte Directors' Dealings DE — Käufe | 1 |
| Eulerpool Insider (Verkäufe) | https://eulerpool.com/insiderverkaeufe | Aggregierte Directors' Dealings DE — Verkäufe mit Cluster-Tagging | 1 |
| aktiencheck.de | https://www.aktiencheck.de/analysen/DAX_MDAX | Analyst-Ratings-Flow DE | 1 |
| boerse-social.com | https://www.boerse-social.com/ | "Guten Morgen mit …"-Übersichten | 1 |
| GIE AGSI | https://agsi.gie.eu/ | Europäische Gasspeicher | 1 |
| VDAX-NEW | TradingView: `DV1X` | Volatilitätsindex DAX | 1 |
| Eurex PCR | https://www.eurex.com/ | Put/Call-Ratio Aktienindexderivate | 1 |
| EUWAX Sentiment | https://www.boerse-stuttgart.de/ | Retail-Sentiment | 1 |
| **OpenInsider** | **https://openinsider.com/** | **SEC Form 4 aggregiert, Cluster-Tagging (US)** | **2** |
| **Finviz Insider** | **https://finviz.com/insidertrading.ashx** | **US Insider-Trades mit Screener-Integration** | **2** |
| **SEC EDGAR Full-Text** | **https://efts.sec.gov/** | **8-K-Filings (Ad-hoc-Äquivalent US), Form-4-Originale** | **2** |
| **CBOE VIX** | **cboe.com/vix** bzw. TradingView `VIX` | **US-Marktangst-Barometer** | **2** |
| **Fed FOMC Calendar** | **federalreserve.gov/monetarypolicy/fomccalendars.htm** | **FOMC-Termine, Protokoll-Releases** | **2** |
| **Nikkei / Nikkei 225** | TradingView: `NI225` | **Japan-Leitindex** | **3** |
| **Hang Seng** | TradingView: `HSI` | **Hongkong-Leitindex** | **3** |
| **BoJ / PBoC Calendar** | boj.or.jp / pbc.gov.cn | **Zentralbank-Termine Asien** | **3** |
