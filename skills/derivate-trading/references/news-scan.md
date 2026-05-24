# News-Scan & Hidden Catalyst Scan — Referenz

**Diese Datei wird geladen bei:**
- "News-Scan" / "Skandal-Scan" / "aktuelle Thesen" → Routine 8
- "Hidden Scan" / "Randnotizen" / "was hat keiner auf dem Schirm" / "tiefer suchen" → Routine 8b
- **"Insider-Verkäufe" / "Sells-Check" / "Short-Dealings" / "Cluster-Verkäufe" → Routine 8c**

**🚨 AUSFÜHRUNGSREGEL: NICHT fragen. NICHT erklären. SOFORT ausführen.**

---

## ⚡ Pflicht-Schritt 0a — Pipeline-Load (seit Phase 4, 26.04.2026)

**Vor jeder Recherche** wird die jüngste MARKETDATA + CANDIDATES + GAMECHANGER-HUNT aus dem Workspace Shared Drive geladen — die ersten beiden liefern für 47 Ticker bereits Kurs/EMA/RSI/30d-Move/Volumen und Watchlist-Trigger-Status, GAMECHANGER-HUNT zusätzlich Setup-getriggerte Stufe-2-Kandidaten. Volltext: `references/pipeline-integration.md`. Kurzform:

```python
import sys; sys.path.insert(0, '/mnt/skills/user/derivate-trading')
import pipeline_utils as pu

# (1) Drive: jüngste 3 Files finden — search_files mit modifiedTime DESC
# (2) Drive: read_file_content für alle drei Files
# (3) Frische prüfen
ROUTINE = 'scan_afternoon'  # oder 'scan_evening'
md_status   = pu.freshness_status(md_modified_time_iso, ROUTINE)
cand_status = pu.freshness_status(cand_modified_time_iso, ROUTINE)
gc_status   = pu.freshness_status(gc_modified_time_iso, ROUTINE)

core_fallback = (md_status['status'] in ('ausfall', 'missing') or
                 cand_status['status'] in ('ausfall', 'missing'))

if core_fallback:
    # 🔴 Pipeline-Fallback aktiv — komplette Web-Logik wie vor Phase 4
    fallback = True
else:
    # 🟢/🟡 Pipeline-Daten nutzen
    md = pu.parse_marketdata(md_content)
    snap = pu.parse_candidates(cand_content)
    # Gamechanger ist additiv — bei Ausfall einfach leer
    gc = (pu.parse_gamechanger(gc_content)
          if gc_status['status'] not in ('ausfall', 'missing')
          else pu.GamechangerSnapshot())
    fallback = False
```

**Header-Pflicht im Output:** Bei `stale` (🟡) oder Core-Fallback (🔴) muss der Briefing-Header das nennen — `pu.render_freshness_header(md_status, cand_status, ROUTINE, gc_status=gc_status)`. Bei reinem Gamechanger-Ausfall: kompakte Hinweiszeile, kein roter Fallback (siehe Reference, Abschnitt „Fallback-Granularität").

---

## ⚠️ Pflicht-Schritt 0b — Watchlist-Abgleich (gilt für 8, 8b, 8c)

**Bevor ein Kandidat ausgegeben wird**, wird sein Name (und ggf. Kürzel/Ticker) gegen die Watchlist abgeglichen. Grund: Watchlist-Einträge haben bereits durchdachte Trigger und Thesen — sie sind **keine neuen Kandidaten**, und wenn sie erneut auftauchen, ist die relevante Information „Trigger jetzt erreicht / noch nicht" — nicht „hier ist eine neue Idee".

**Implementation (Pipeline-First):**

```python
match = pu.find_candidate_in_buckets(snap, kandidat_name)  # snap aus Schritt 0a
if match:
    # Output-Format siehe unten — NICHT als neuer Kandidat!
    # match.bucket = 'bereit' | 'very_close' | 'close' | ...
```

Bei Pipeline-Fallback (Schritt 0a `fallback=True`): Auf `ju.match_watchlist(wb, name)` zurückfallen — Logik unverändert wie vor Phase 4.

**Output bei Watchlist-Match (ersetzt den normalen Kandidaten-Block):**

```
🔔 WATCHLIST-TREFFER — nicht als neuer Kandidat
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Kandidat: [Name] — [Long/Short]
Bucket:   [bereit / very_close / close / watching / pending / paused / passive]
Details:  [Detail-Text aus CANDIDATES — z.B. "Preis 33.94 IN-ZONE [33.40-33.60]"]
Aktion:   [bereit → volle Checkliste JETZT / very_close → vorbereiten / sonst → weiter warten]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Nur wenn der Bucket **`bereit`** ist (= Pipeline hat Trigger als erfüllt geflaggt), geht der Kandidat in die volle 7/7-Checkliste — mit dem Hinweis, dass es ein Watchlist-Trigger-Hit ist, nicht ein News-/Hidden-/Insider-Scan-Hit. Dem User ist damit klar, dass die These schon vorher vereinbart war.

---

## ⚠️ Pflicht-Schritt 0c — Counter-These-Quick-Check (seit 07.05.2026)

**Vor jeder vollen Kandidaten-Bewertung** läuft Counter-These als Step 1 (siehe SKILL.md § Counter-These-Quick-Check). Drei Punkte, max. 2 Web-Suchen:

1. Aktiver Aktienrückkauf? (gegen Short tot, für Long stützend)
2. Frische Analysten-Aktionen letzte 14 Tage? (Konsens-Drift = hartes Counter-Signal)
3. Earnings/HV/Ex-Div in ≤ 5 Handelstagen? (Event-Risiko)

≥ 1 Treffer gegen die These → SKIP oder Setup-Wechsel, **nicht** in volle Vorcheckliste gehen. Erst nach Quick-Check-Pass:
- Schritt 0a (Pipeline-Load) bereits erledigt
- Schritt 0b (Watchlist-Abgleich) bereits erledigt
- Schritt 0c (Counter-These) erledigt → jetzt Kandidaten-Bewertung mit 7/7-Vorcheckliste

**Rationale:** Workflow-Korrektur aus der CRM-Lehre (07.05.2026). Counter-These als letzter Filter erzeugte Sunk-Cost bei Plan-Arbeit. Ab Step 1 spart das Zeit und Klar-Disziplin: Setups, die durch Buyback-/Analyst-/Event-Filter fallen, werden nicht zu Plänen.

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

**🆕 Phase 4:** Wenn der Kandidat im Pipeline-Universe (47 Ticker) liegt → alle Werte aus `pu.get_ticker_data(md, ticker)`. Liefert das `None` (Off-Universe) → gezielte Web-Suche nur für diesen Ticker. Bei Pipeline-Fallback: alles per Web wie bisher.

1. **30d-Move** (primäre Late-Entry-Metrik): >15% = stärkeres Setup nötig. **Nicht YTD verwenden** — zeitvariant (im Januar ~2 Wochen, im Dezember ~12 Monate) und deshalb als Timing-Filter ungeeignet. → `td.move_30d`
2. **52W-Hoch-Abstand**: Am ATH = wenig Raum nach oben. 10–30% unter Hoch = komfortabler Puffer. → `td.hi_52w_dist`
3. **RSI (Daily)**: <60 für Long-Kandidaten erwünscht; >70 = überkauft, nicht einsteigen. → `td.rsi`
4. **EMA-Staffelung**: Kurs über EMA20>EMA50>EMA100>EMA200 = gesunder Uptrend. Andernfalls Trend-Zustand einordnen, bevor gekauft wird. → `td.ema_stack` (`'bullish' | 'bearish' | 'neutral'`) plus `td.ema20/50/200`
5. **News-Katalysator erst jetzt bewerten**: Hat der Markt die Information schon eingepreist (Rally vor der Meldung) oder ist noch Reaktion offen? → Bleibt Web-Suche.

**Makro-Phasen-Beobachtung:** Nach abrupten Makro-Wenden (z.B. Iran-Hormus-Öffnung 17.04.2026) sind News-Scan-Long-Kandidaten systemisch Late-Entries — der Markt hat die Information im Vorfeld der Schlagzeile verarbeitet. In solchen Phasen: Pullbacks abwarten oder Short-Setups priorisieren.

### Ablauf (SOFORT starten)

1. **Primär-Websuche (Stufe 1):** `DAX MDAX SDAX Aktie Kurseinbruch Skandal Gewinnwarnung heute [aktuelles Datum]`
2. **Websuche:** `[auffälliger Kandidat] Aktie Ursache [aktuelles Datum]` (nur wenn konkreter Kandidat aus Schritt 1)
3. **Sekundär-Websuche (Stufe 2 — automatisch bei <2 reifen Stufe-1-Kandidaten):** `S&P 500 Nasdaq biggest movers earnings surprise [aktuelles Datum]`
4. **Stufe 3 nur auf Codewort „Asien-Scan"** oder expliziten Makro-Trigger aus Makro-Check (BoJ/PBoC-Event, China-Stimulus): `Nikkei Hang Seng movers [aktuelles Datum]`
5. **Watchlist-Abgleich (Pflicht — Schritt 0b oben):** Jeder Kandidat durch `pu.find_candidate_in_buckets(snap, name)` (Pipeline) oder bei Fallback `ju.match_watchlist(wb, name)`. Bei Treffer → Watchlist-Treffer-Format, nicht Kandidaten-Format.
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

**Schicht 0 — GAMECHANGER-HUNT aus Pipeline (seit Phase 4, IMMER zuerst):**
- Quelle: Bereits in Schritt 0a geladen (`gc = pu.parse_gamechanger(gc_content)`). Liefert Setup-getriggerte Stufe-2-Kandidaten (Long/Short-Trend-Pullback etc.) aus dem Universe-Scan — genau die Art „chartbasiert sichtbar, aber noch keine News dazu", die Hidden Catalyst sucht.
- Verarbeitung: Jeden Gamechanger-Kandidaten als Vor-Kandidat aufnehmen, Schicht 1 (EQS/DGAP) und Schicht 2 (Insider) **gezielt für diese Tickers** durchsuchen statt breit. Das spart Web-Calls und fokussiert auf Setups, die die Pipeline ohnehin als plausibel markiert hat.
- Wenn Gamechanger leer ist (oder Pipeline ausgefallen): Schicht 1 und 2 wie bisher breit suchen.
- Watchlist-Cross-Check: Gamechanger-Kandidaten via `pu.find_candidate_in_buckets(snap, ticker)` prüfen — falls Treffer in CANDIDATES, Watchlist-Treffer-Format ausgeben (Schritt 0b).

**Schicht 1 — EQS/DGAP Ad-hoc Pflichtmeldungen (IMMER):**
- Websuche: `DGAP Ad-hoc Meldung heute [aktuelles Datum] Nebenwert Deutschland`
- Alternative: `EQS-News Ad-hoc [aktuelles Datum] SDAX`
- Ziel: Aufträge, Beteiligungen, strategische Entscheidungen, Prognoseänderungen, noch nicht eingepreist
- **Bei Schicht-0-Kandidaten zusätzlich:** Pro Gamechanger-Ticker gezielt: `[Ticker-Name] DGAP EQS Meldung [aktuelles Datum]`

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

**Schicht 3 — Behörden-Entscheidungen (automatisch bei Eskalation, sonst auf Wunsch):**
- Websuche: `Kartellamt Freigabe [Monat Jahr]` oder `BaFin Entscheidung [Monat Jahr]`
- Ziel: M&A-Katalysatoren, Zulassungen (FDA, EMA)

**Schicht 4 — Sektor-Frühindikatoren (automatisch bei Eskalation, sonst auf Wunsch):**
- Baltic Dry Index, Gasflüsse (GIE AGSI), Rohstoff-Moves, FDA-Kalender
- Ziel: Trendwende in Sektor-Daten bevor sich Einzeltitel bewegen

**Sektor-Mapping-Hinweis Gas (seit 21.05.2026):** Ein Gaspreis-Anstieg macht **nicht** LNG-Shipping oder Gasinfrastruktur zu Profiteuren — verbreiteter Denkfehler. LNG-Carrier (Flex LNG etc.) verdienen an **Charterraten**, nicht am Gaspreis (Spot-Raten können bei hohem Gaspreis sogar fallen). Regulierte Gasnetzbetreiber (Snam, Enagas) haben **RAB-basierte, gaspreis-unabhängige** Erlöse — das sind defensive Zins-/Regulierungs-Plays. Echtes Gas-Beta sitzt bei **US-E&P-Produzenten** (EQT, Antero, Range, Expand Energy), deren Erlöse direkt mit dem Henry-Hub-Preis skalieren. Konsequenz: Bei einem Schicht-4-Gas-Signal direkt auf E&P-Produzenten gehen, nicht auf Carrier oder Netzbetreiber.

### Eskalations-Automatik Schicht 3 + 4 (seit 2026-05-21)

Schicht 3 und 4 sind grundsätzlich on-demand — mit **einer** Ausnahme, die sie ohne Rückfrage auslöst:

**Trigger:** Wenn Schicht 1 + 2 (sowie 2b, sofern wegen dünner DE-Lage aktiviert) **keinen neuen handelbaren Kandidaten** liefern, werden Schicht 3 **und** 4 automatisch nachgezogen.

**Was als „handelbarer Kandidat" zählt:** ein neuer Wert, der in einen Bucket BEREIT oder NAHE mündet bzw. eine Stufe-1-GO-Empfehlung trägt. **Nicht** ausreichend, um die Eskalation zu unterdrücken: Bestätigungen bereits offener Positionen, reine Kontext-Funde (operative News ohne Setup), Kandidaten die schon auf der Watchlist stehen, oder Negativ-Befunde („geprüft, kein Cluster").

**Gilt für:** Routine 8b (Hidden Catalyst Scan) und den Hidden-Scan-Teil im Morgen-Briefing (Routine 7 — dort laufen Schichten 0–2 ohnehin ungefragt, die Eskalation hängt 3 + 4 bei Bedarf an).

**Greift nicht:** Liefern Schicht 1/2/2b mindestens einen neuen Kandidaten, bleiben 3 + 4 on-demand. Manuell sind beide jederzeit auch ohne Eskalations-Trigger anforderbar.

**Credit-Hinweis (Regel 18):** Die Eskalation kostet typisch 3–5 zusätzliche Web-Calls, greift aber nur bei wirklich leerem Schicht-1/2/2b-Ertrag — an Tagen mit Insider- oder Ad-hoc-Fund läuft sie nicht.

### 6 Hidden-Catalyst-Muster

1. **Stiller Großauftrag** — Auftragseingang ohne PR-Kampagne
2. **Insider kauft nach Kursrückgang** — Eigenkapital-Signal
3. **Kartellamt-Freigabe für Übernahme** — M&A-Katalysator
4. **Behörden-Zulassung** (BaFin, FDA, EMA) vor Bekanntheit
5. **Sektor-Frühdaten drehen** (z.B. Baltic Dry dreht hoch → Bulk-Shipping)
6. **EU-Vergabe-Gewinner** — öffentliche Ausschreibung still gewonnen

### Watchlist-Abgleich (Pflicht)

Vor Output jeder Kandidaten-Karte: `pu.find_candidate_in_buckets(snap, name)` (Pipeline) oder bei Fallback `ju.match_watchlist(wb, name)`. Bei Treffer → Watchlist-Treffer-Format statt Hidden-Catalyst-Block (siehe Schritt 0b oben).

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
6. **Watchlist-Abgleich (Pflicht — Schritt 0b oben):** Jeder Kandidat durch `pu.find_candidate_in_buckets(snap, name)` (Pipeline) oder bei Fallback `ju.match_watchlist(wb, name)`. Bei Treffer → Watchlist-Treffer-Format statt Short-Kandidaten-Block.
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
