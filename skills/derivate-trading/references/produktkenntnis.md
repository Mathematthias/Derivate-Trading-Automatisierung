# Produktkenntnis — Ordertypen, Broker, Instrumente, Sizing

**Diese Datei wird geladen bei:** Ordertypen-Fragen, Broker-Vergleich, CFDs vs. KOs, Optionen-Interesse, Kelly-Criterion, Position-Sizing-Vertiefung, TR-Limitierungen.

---

## Inhaltsverzeichnis
1. Ordertypen (Market, Limit, Stop, OCO, Trailing, If-Done)
2. Broker-Vergleich für Derivate-Trading
3. **Zertifikat-Auswahl auf TR/SB+** (Such- und Ausschlusskriterien, Produktcheck)
4. CFDs vs. Knock-Out-Zertifikate
5. Faktor-Zertifikate — Warnung
6. ETPs / ETCs
7. Optionen — Lernpfad
8. Position Sizing: Kelly-Criterion & Fixed-Fractional

---

## 1. Ordertypen

### Market Order
Sofort zum nächsten verfügbaren Kurs. Nur bei liquiden Instrumenten sinnvoll — bei Zertifikaten mit breitem Spread gefährlich.

### Limit Order
Kauf/Verkauf nur zum angegebenen Preis oder besser. Kein Slippage-Risiko, aber keine Garantie auf Ausführung.

### Stop Order (Stop-Loss / Stop-Buy)
Wird bei Erreichen des Stop-Preises zu einer Market Order. Schützt vor weiteren Verlusten, aber Slippage möglich bei Gaps.

### Stop-Limit
Wird beim Stop-Niveau zu einer Limit Order. Verhindert Ausführung bei Gapping, aber Risiko dass die Order gar nicht ausgeführt wird.

### OCO (One-Cancels-Other) — ⚠️ NICHT auf Trade Republic
Zwei Orders werden gleichzeitig platziert — z.B. SL + TP. Wird eine ausgeführt, wird die andere automatisch storniert.

**Verfügbar bei:** flatex, Consorsbank, Interactive Brokers, **Smartbroker+** (seit Ende 2025)

**Warum OCO wichtig ist:** Ohne OCO muss der User nach Auslösung des SL manuell die TP-Order stornieren (und umgekehrt). Bei schnellen Moves kann das zu Doppelausführungen oder verpassten Stornierungen führen — besonders kritisch bei KOs mit engen Spreads.

**Smartbroker+-Hinweis:** OCO wird als eigenständiger Ordertyp angelegt, NICHT durch Kombination von bestehenden Limit- und Stop-Orders. Falls Limit/Stop bereits gesetzt → löschen und neu als OCO anlegen.

**Kraken Pro:** Unterstützt "Conditional Close" — SL/TP direkt bei Orderaufgabe, kein Nachplatzieren nötig (gilt nicht für Bison).

### Trailing Stop — ⚠️ NICHT auf Trade Republic
Stop-Preis zieht automatisch nach, wenn der Kurs in die gewünschte Richtung läuft. Abstand in €, % oder ATR-Einheiten.

**Workaround auf TR:** Manuell nachziehen. Preisalarm bei Zielkurs setzen, dann SL manuell anpassen. Routinemäßig im Morgen-Briefing prüfen.

### If-Done / If-Touched
Automatische Folge-Order, die erst aktiv wird, wenn eine Bedingung erfüllt ist. Nur bei wenigen Brokern (flatex teilweise, IB vollständig).

---

## 2. Broker-Vergleich für KO-Zertifikate

| Broker | OCO | Trailing | Kosten (KO 1.000€) | Emittenten | Besonderheit |
|--------|-----|----------|---------------------|------------|-------------|
| **Trade Republic** | ❌ | ❌ | 1€ flat | HSBC, UBS, SocGen, Vontobel | Einfachste App, günstigste Kosten bei Standardorders |
| **Smartbroker+** | ✅ | ✅ | 0€ (gettex ab 500€) / 1€ | Breites Spektrum | OCO-Ordertyp erst seit Ende 2025; günstig; UBS-Emittentenhandel oft kostenfrei |
| **flatex** | ✅ | ✅ | 0€ (Premium-Partner) / 3,90€ | 7 Premium-Emittenten | flatex Trader 2.0 mit Realtime-Push; **Top-Empfehlung** für aktive Derivate-Trader |
| **Consorsbank** | ✅ | ✅ | ~3,95€ + 0,25% | Breites Spektrum | Etabliert, gute App |
| **S-Broker** | ✅ | ✅ | ~4,99€ | Breites Spektrum | Sparkassen-Tochter |
| **finanzen.net ZERO** | ✅ | — | 0€ | Nur gettex/Baader | Nur ein Handelsplatz — bei Zertifikaten einschränkend |

**Aktuelle Strategie:**
- **TR:** Sparpläne, einfache Positionen, laufende Positionen
- **Smartbroker+:** Neue Derivate-Positionen (OCO + Trailing Stop verfügbar), schrittweise Migration
- **flatex (perspektivisch):** Wenn Handelsvolumen weiter steigt

**Kostenbeispiel: Premium-Emittent auf flatex** → 0€ bei ≥ 500€ Ordervolumen → günstiger als TR bei kleinen Volumina, gleich bei Standardorders.

**⚠️ Verlustverrechnungstöpfe:** TR und SB+ haben jeweils eigene Verlustverrechnungstöpfe. Wechsel zwischen Brokern bedeutet, dass Verluste aus TR nicht automatisch mit Gewinnen aus SB+ verrechnet werden — Verlustbescheinigung bis 15.12. des Jahres beantragen und in die Steuererklärung einreichen.

---

## 3. Zertifikat-Auswahl auf TR/SB+

### Suchkriterien
- **Typ:** Knock-Out / Turbo (keine Optionsscheine, keine Faktor-Zertifikate)
- **Laufzeit:** Open End
- **Richtung:** Short oder Long je nach These
- **Hebel:** 2,5–5× (Sweet Spot; über 7× nur bei sehr guter Checkliste und enger Überwachung)
- **Emittent:** HSBC, Société Générale, UBS, Vontobel

### Ausschlusskriterien
- Kein „Smart Turbo" (kompliziertere Doppel-Schwellen-Logik)
- Kein Hebel > 7× beim aktuellen Erfahrungsstand
- Keine Laufzeitbegrenzung unter 4 Wochen
- Spread > 5% → Finger weg
- KO-Abstand < 15% → zu riskant
- Fremdwährungs-Underlying in **EM-/Inflationswährung** (TRY, ZAR, ARS, MXN, RUB) → NO GO (Lektion 1 v2)
- Fremdwährungs-Underlying **ohne Quanto und ohne FX-adjustierten R:R-Plan** → NO GO (Lektion 1 v2)

### 3a. Produktverfügbarkeits-Vorstufe (Stufe 2/3 Universum)

Bei Nicht-EUR-Underlyings vor der vollen Produktcheck-Reihenfolge ein schneller Vorab-Check — verhindert, dass du R:R-Rechnungen für nicht-handelbare Produkte machst:

1. **Quanto-KO auf Gettex oder SB+ verfügbar?** (TradeRepublic-Suche oder Smartbroker+-Derivatesuche, Filter: Quanto + Knock-Out + Emittent HSBC/SG/Vontobel/UBS)
2. **Wenn Quanto nicht verfügbar: FX-adjustierter R:R-Plan nach Lektion 1 v2** (siehe unten). Pauschal-Zeitlimit existiert nicht mehr — Setup-R:R nach FX-Drag-Abzug muss Mindest-Schwelle erreichen.
3. **FX-Szenario explizit:** Bei Non-Quanto-Entry Richtung dokumentieren (Rückenwind / neutral / bewusst akzeptiert), DXY-Stack und EUR/USD ATR-14 prüfen.
4. **Rohstoff-Korrelationscheck** bei NOK/CAD/AUD/BRL-Underlyings: These unabhängig vom Rohstoffzyklus, oder spiele ich denselben Makro-Trade zweimal?
5. **Ergebnis:** Produkt handelbar → weiter mit Produktcheck-Reihenfolge unten. Nicht handelbar → Alternative (Sektor-ETF-KO, Direktaktie) oder SKIP.

### Lektion 1 v2 — FX-adjustierter R:R-Buffer (statt pauschales Zeitlimit)

**Hintergrund:** Lektion 1 v1 hatte ein pauschales 10-Tage-Limit auf Non-Quanto-FX-Underlyings. Das schützt nicht das eigentliche Risiko — sondern verbietet auch saubere R:R-Setups, die FX-Drag verkraften, und erlaubt umgekehrt R:R-knappe Setups innerhalb der 10 Tage, die im FX-Verlust enden würden. **Echtes Risiko ist nicht die Halte-Dauer, sondern der R:R-Buffer-Verlust durch FX-Drift während der Halte.**

**Mechanik FX-Drag-Abschätzung:**

EUR/USD-Tagesvola ≈ 0,3-0,5%, gelegentlich 0,8-1% bei Makro-Events. Erwartete kumulierte Drift über Halte-Periode `n` Tage (statistische Erfahrung, kein hartes Modell):

| Halte-Tage | Erwarteter FX-Drag (Median-Szenario) | Worst-Case-Szenario (Top 10%) |
|---|---|---|
| 1-2 Tage | 0,3-0,8% | 1,5% |
| 3-5 Tage | 0,8-1,5% | 2,5% |
| 6-10 Tage | 1,5-2,5% | 4% |
| 11-20 Tage | 2,5-4% | 6% |
| > 20 Tage | nicht mehr planbar — Quanto Pflicht |

**Anwendungsregel — Lektion 1 v2:**

Bei Non-Quanto-KOs auf Foreign-Currency-Underlyings (insbes. USD-Underlyings):

1. **Halte-Plan kalkulieren** (z.B. 5 Tage bis TP1, 10 Tage bis TP2)
2. **FX-Drag aus Tabelle ablesen** (Median-Szenario)
3. **FX-Drag von TP-Reward abziehen, zu SL-Risiko hinzuzählen** (konservativ in beide Richtungen)
4. **Adjustiertes R:R berechnen:** (TP-Reward − FX-Drag) / (SL-Risiko + FX-Drag)
5. **Mindestschwelle:** adjustiertes R:R **≥ 1,4** (statt 1,35 wie bei EUR-Underlyings)
6. **Setup nicht handelbar wenn adjust. R:R < 1,4** → SKIP oder Quanto erzwingen oder Direktaktien-Alternative

**Beispiel-Berechnung CTSH-Setup (Halte 5 Tage, ohne Quanto):**

- Underlying-Plan Entry 52,00 / SL 50,90 / TP1 56,00 (USD)
- Underlying-R:R = 4,00 / 1,10 = 3,64
- FX-Drag bei 5 Tagen Halte ≈ 1,2% (Median aus Tabelle)
- Cert ≈ 50€ Risiko, ≈ 180€ Reward (Annahme)
- 1,2% von 180€ = 2,16€ FX-Drag-Abzug auf Reward → 177,84€
- 1,2% von 50€ = 0,60€ FX-Drag-Aufschlag auf Risiko → 50,60€
- Adjustiertes R:R = 177,84 / 50,60 = **3,51 ✅** (deutlich über 1,4)

→ Setup **handelbar** unter Lektion 1 v2, war unter v1 nur durch das Zeitlimit erlaubt, R:R hätte aber jederzeit gestimmt.

**Sonderfälle — FX-Vola-Phasen erfordern strengere Schwelle:**

- **EUR/USD ATR-14 > 0,8%** ODER **DXY mit klarem Trend-Stack (alle EMAs gestapelt)** → adjustiertes R:R-Minimum auf **1,7** anheben statt 1,4
- **Pre-Fed/EZB-Termine** in Halte-Periode → entweder Quanto erzwingen oder Halte-Periode unter Termin verkürzen

**Was Lektion 1 v2 NICHT erlaubt:**

- EM-/Inflationswährungen (TRY, ZAR, ARS, MXN, RUB, BRL als Reserve-Schwelle prüfen) — bleiben pauschal NO GO. Tagesvola dort ist nicht statistisch berechenbar
- Halte > 20 Tage ohne Quanto — kumulierte FX-Drift wird zu groß, Quanto Pflicht
- Setups, deren Underlying-R:R < 1,5 ist — die haben keinen Sicherheitspuffer für FX-Drag

### Produktcheck-Reihenfolge

1. **Briefkurs ablesen** auf der Zertifikats-Detailseite
2. **Gegencheck:** Inneren Wert berechnen und mit Briefkurs vergleichen
   - Short: `(KO − Underlying) × BV`
   - Long:  `(Underlying − KO) × BV`
   - Aufgeld = (Briefkurs − Innerer Wert) / Innerer Wert × 100%
   - Aufgeld sollte **< 3%** sein
3. **Spread prüfen:** `(Brief − Geld) / Geld × 100%` — Ziel < 1,5%, akzeptabel < 3%
4. **KO-Abstand berechnen:** `|KO − Underlying| / Underlying × 100%` — Ziel ≥ 20%, Min. 15%
5. **SL/TP auf Zertifikatsebene berechnen:**
   - SL-Underlying festlegen (z.B. 1,5 × ATR vom Einstieg)
   - SL-Zertifikat = `(KO − SL-Underlying) × BV` (Short) bzw. `(SL-Underlying − KO) × BV` (Long)
   - Analog TP1 und TP2
6. **R:R prüfen:** `(TP1 − Einstieg) / (Einstieg − SL)` ≥ 1,35:1 (Lektion 5)
7. **Positionsgröße bestimmen:** Fixed-Fractional, 2%-Regel (siehe Abschnitt 8)

### Vergleich mehrerer Kandidaten

Bei mehreren passenden Zertifikaten auf denselben Underlying: R:R und Spread als Tiebreaker verwenden, nicht den Hebel. Ein leicht niedrigerer Hebel mit besserem Spread schlägt oft den höheren Hebel mit schlechtem Spread.

---

## 4. CFDs vs. Knock-Out-Zertifikate

| Merkmal | KO-Zertifikat | CFD |
|---------|--------------|-----|
| Struktur | Schuldverschreibung (Emittent-Risiko) | Differenzkontrakt (Broker-Gegenpartei) |
| Steuer (DE) | §20 EStG, Abgeltungssteuer 26,375% | §20 EStG, Abgeltungssteuer 26,375% (Sonderregeln bei Termingeschäften beachten!) |
| Nachschusspflicht | **Nein** — max. Verlust = Einsatz | **Teilweise ja.** Bei regulierten EU-Brokern (ESMA) begrenzt durch Hebel-Caps; außerhalb EU möglich |
| KO-Risiko | Ja — feste KO-Schwelle | Nein — aber Margin Call möglich |
| Dividenden | Long KO: kein Anspruch; Short KO: Kosten | Long CFD: Dividende gutgeschrieben; Short: Abzug |
| Verfügbarkeit TR | ✅ | ❌ |
| Leerverkäufe einzelner Nebenwerte | Nur via KO Short (begrenzte Produktauswahl) | Ja, für fast jeden Wert |

**Fazit für aktuellen Stand:** KO-Zertifikate bleiben das primäre Instrument — kein Nachschussrisiko, klares Risiko, auf TR/SB+ verfügbar. CFDs erst perspektivisch, wenn:
- Nebenwerte geshortet werden sollen, für die kein liquides KO-Short existiert (z.B. Heidelberger Druck war zu illiquide)
- Größere Positionen mit professionellen Order-Tools nötig werden
- Steuerliche Implikationen geklärt sind

---

## 5. Faktor-Zertifikate — ⚠️ Warnung

Faktor-Zertifikate haben **tägliche Pfadabhängigkeit** — ein gravierendes Risiko, das Anfänger unterschätzen.

**Mathematisches Beispiel (Long-Faktor-5):**

| Tag | Underlying | Veränderung | Faktor-Zertifikat |
|-----|------------|-------------|-------------------|
| 0 | 100 | — | 100 |
| 1 | 110 | +10% | 100 × 1,50 = 150 (entspricht +5×10%) |
| 2 | 99 | −10% | 150 × 0,50 = **75** (entspricht +5×(−10%)) |

**Ergebnis:** Underlying ist bei 99 (−1%), Faktor-Zertifikat bei **75 (−25%)**. Der Trader hätte nach der These "Underlying bleibt konstant, ich hebele" verloren.

**Grund:** Tägliche Neuhebelung (Daily Reset) führt zu Compounding-Effekten gegen den Trader in volatilen Seitwärtsmärkten.

**Fazit:** Faktor-Zertifikate eignen sich **ausschließlich für Intraday-Trades** oder klare, einseitige Trendbewegungen. Über Nacht halten = Pfad-Decay-Risiko. **Niemals** als KO-Ersatz für mehrtägige Positionen.

---

## 6. ETPs / ETCs (Exchange Traded Products / Commodities)

Börsengehandelte Schuldverschreibungen, die Rohstoffpreise abbilden — mit oder ohne Hebel.

**Vorteile:**
- Kein KO-Risiko (im Gegensatz zu Turbos)
- Auf TR verfügbar (z.B. WisdomTree WTI 2x/3x, EU Natural Gas)
- EUR-gehedged-Versionen für Fremdwährungs-Underlyings verfügbar

**Nachteile:**
- **Rollkosten** bei Futures-basierten Produkten (Contango-Markt frisst Wert)
- **Tägliche Hebelanpassung** bei Leveraged ETPs → Compounding-Effekt wie bei Faktor-Zertifikaten (Pfadabhängigkeit bei >1x Hebel)
- Open-End-Finanzierungskosten erodieren den Wert täglich

**Lektion 3 (anwendbar):** Max. 2–3 Wochen halten, dann neu bewerten.

---

## 7. Optionen — Lernpfad

Optionen sind mächtiger als KOs, aber komplexer. Der Mathe-Hintergrund ist ideal für Optionen — Black-Scholes, Greeks, Implied Volatility sind alle mathematische Konzepte.

### Vorteile gegenüber KOs
- Kein Knock-Out-Risiko
- Zeitwert transparent (Theta quantifizierbar)
- Vielfältige Strategien (Spreads, Straddles, Iron Condor)
- Impliziten Volatilitäts-Edge handelbar (Vega-Trading)

### Nachteile
- In DE weniger Angebot, IBKR / CapTrader nötig
- Höhere Einstiegshürde, Theta-Decay erzieht teuer
- Steuerlich: Termingeschäfte-Verlustverrechnungsbeschränkung beachten (Sonderregel §20 EStG)

### Lernpfad

1. **Grundkonzepte:** Call/Put, Strike, Laufzeit, Prämie, Moneyness (ITM/ATM/OTM)
2. **Greeks:**
   - **Delta** — Preissensitivität (∂Prämie/∂Kurs)
   - **Gamma** — Sensitivität des Delta (∂Delta/∂Kurs)
   - **Theta** — täglicher Zeitwertverlust (∂Prämie/∂t)
   - **Vega** — Sensitivität gegenüber Volatilität (∂Prämie/∂σ)
3. **Einfache Strategien:** Long Call/Put, Covered Call, Protective Put
4. **Spreads:** Bull Call Spread, Bear Put Spread
5. **Fortgeschritten:** Iron Condor, Straddle/Strangle
6. **Plattform:** IBKR (Interactive Brokers) für Optionen auf europäische Aktien

**Aktueller Rat:** Erst mit KOs zur Konsistenz kommen, dann Optionen lernen. Optionen verzeihen Anfängerfehler weniger (Theta-Decay + Volatility Crush).

---

## 8. Position Sizing — Kelly-Criterion & Fixed-Fractional

### Fixed-Fractional (2%-Regel) — aktuelle Pflicht (Lektion 12)

```
Max. Verlust pro Trade = Risikokapital × 0,02
Stückzahl = Max. Verlust / (Einstieg − SL-Kurs)
Investitionssumme = Stückzahl × Briefkurs
```

**Hybrid-Skala (je nach Checklisten-Score):**
| Score | Einsatz-Faktor | Max. Verlust |
|-------|----------------|--------------|
| 5/7 | 1,0 % | 150 € |
| 6/7 | 2,0 % | 300 € |
| 7/7 | 3,0 % | 450 € |
| Insider + 7/7 | 4,0 % | 600 € |

**Beispielrechnung Fraport Short (retrospektiv):**
- Risikokapital 5.000 €, Max. Verlust (2%) = 100 €
- Einstieg Cert 19,40 €, SL Cert 15,50 € → Abstand 3,90 € pro Stk
- Max. Stückzahl: 100 / 3,90 = 25 Stk
- Investitionssumme: 25 × 19,40 € = **485 €**
- Tatsächlicher Einsatz war 1.533 € (79 Stk) → bei SL-Auslösung 308 € Verlust = **6,2 %** → klare Regelverletzung

### Kelly-Criterion (Kontext / Theorie)

```
f* = (p × b − q) / b
```
- p = Gewinnwahrscheinlichkeit
- q = 1 − p
- b = Gewinn/Verlust-Verhältnis (durchschnittliches R:R)

**Beispielberechnung aus Journal:**
- Gewinnrate ≈ 60 % (9 von 15 Trades positiv zu einem Zeitpunkt)
- Durchschnittliches R:R ≈ 1,8 : 1
- Kelly: f* = (0,60 × 1,8 − 0,40) / 1,8 = 0,68 / 1,8 ≈ **37,8 %**

**Interpretation:** Voll-Kelly würde 37,8 % des Kapitals pro Trade vorschlagen — für die tatsächliche Trade-Statistik. Das ist **viel zu aggressiv**, weil:
1. Die 60% Gewinnrate über wenige Trades kann Zufall sein (Stichprobenfehler)
2. Voll-Kelly maximiert geometrischen Erwartungswert, aber mit extremen Drawdowns
3. Ein Verlust-Strähne von 3–4 Trades vernichtet einen Großteil des Kapitals

### Praxisempfehlung

**Fixed-Fractional 2 % als Basis** — niemals höher ohne starke statistische Evidenz.

Nach **20 Trades mit Fixed-Fractional** (ab Trade #59):
- Trefferquote auswerten
- Drawdown-Verhalten prüfen
- Dann ggf. auf **Half-Kelly** (also 0,5 × f*) oder **Quarter-Kelly** (0,25 × f*) hochstufen
- Maximum aktuell vorstellbar: 3 % pro Trade (bei 7/7-Score und starker Confluence)

### Korrelationsregel (Lektion 7)

Korrelierte Positionen = ein Risikoblock. Das aggregierte Maximum-Risiko aller korrelierten Positionen darf die Fixed-Fractional-Grenze nicht überschreiten.

**Beispiel:** 3 Long-Positionen in deutschen Tech-Nebenwerten (AIXTRON, Jenoptik, Nemetschek) sind nicht 3× 2 % = 6 % Risiko, sondern **ein gemeinsamer Risikoblock**. Maximum aggregiert: 2–3 %.

**Signal:** ≥ 3 Positionen mit gleicher These/Richtung → als einen Block behandeln, aggregierten Max-Verlust berechnen, ggf. Positionen reduzieren.
