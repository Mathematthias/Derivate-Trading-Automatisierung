# Trade-Plan-Templates

**Wird geladen bei:** Routine 1b (Direktaktie analysieren), neue Position planen, "Trade-Plan erstellen".

---

## 🆕 Step 0 — Counter-These-Quick-Check (seit 07.05.2026)

**Bevor das Template ausgefüllt wird**, Quick-Check (max. 2 Web-Suchen):

```
=== COUNTER-THESE QUICK-CHECK ===
1. Aktienrückkauf-Programm aktiv?      [ja / nein / unbekannt]
2. Frische Analyst-Aktionen ≤14d?      [Treiber pro/contra These]
3. Earnings/HV/Ex-Div ≤5 HT?           [Datum oder "kein Event"]

ERGEBNIS: [PASS — weiter zu Template] / [FAIL — Setup-Wechsel oder SKIP]
```

Bei FAIL: Setup-Wechsel prüfen (Long↔Short, oder warten auf nach Event), oder SKIP. Nicht ins Template gehen, bevor Quick-Check sauber ist.

---

## Template A: KO-Zertifikat / Hebel-Trade

```
=== TRADE-PLAN ===
Datum:          [Datum]
Underlying:     [Name, ISIN/Ticker]
Richtung:       Short / Long
These:          [1-2 Sätze, konkreter Katalysator]
Zeithorizont:   [Tage/Wochen]

PRODUKT:
ISIN:           [Zertifikat-ISIN]
Emittent:       [HSBC / SocGen / UBS / Vontobel]
KO-Schwelle:    [€]
Bezugsverh.:    [1,0 / 0,1]
Hebel:          [x]
KO-Abstand:     [%]
Spread:         [%]
Briefkurs:      [€]

SIZING (2%-Regel):
Risikokapital:   [€]
Max. Verlust:    [€]  (= 2% des Risikokapitals)
SL-Abstand:      [€]  (Einstieg − SL-Kurs)
Stückzahl:       [= Max. Verlust / SL-Abstand]
Einsatz:         [= Stückzahl × Briefkurs]

EXIT-REGELN:
SL (Zertifikat): [€]  → Underlying [€] → Max. Verlust [€]
TP1 (Zertifikat): [€] → Underlying [€] → Gewinn [€]
TP2 (optional):  [€]  → Underlying [€] → Gewinn [€]
R:R:             [x:x]   (Mindest: 1,35:1 — Lektion 5)
Exit bei Thesis-Bruch: [konkretes Szenario, z.B. "Deeskalation"]
Zeitlimit:       [max. X Wochen, dann raus — Lektion 3]

CHECKLISTEN:
Signal-Check:    [X/7] → [GO / NO GO]
Counter-These:   [Ergebnisse auflisten, jeder Treffer = Risiko]

STAGING (gestaffelter Exit — Lektion 6 + 13):
TP1: 50% verkaufen, SL nachziehen auf MAX(Breakeven, TP1 − 1,5×ATR)
Rest: Trailing-Stop bei [€], oder TP2
```

**Wichtige Plausibilitäts-Checks VOR Eintrag:**
- Cert-Kurs aus Kernformel gegenrechnen (Short: (KO−Und)×BV, Long: (Und−KO)×BV) — Aufgeld < 3%?
- Spread < 3% (gut < 1,5%, > 5% NO GO)
- KO-Abstand ≥ 15% (Ziel 20%)
- ATR-Plausibilität: Ziel erreichbar in < 5–6 ATRs über Zeithorizont?
- Fremdwährungs-Underlying? → **Lektion 1 v2 prüfen:** (a) EM/Inflations-Währung (TRY/ZAR/ARS/MXN/RUB/BRL) → NO GO. (b) USD/GBP/CHF/JPY mit Quanto verfügbar → ok wie EUR. (c) Non-Quanto: FX-Drag-Adjustierung des R:R berechnen, adjust. R:R ≥ 1,4 (≥ 1,7 bei DXY-Trend / EUR/USD ATR > 0,8%). FX-Drag-Tabelle: 1-2d=0,5%, 3-5d=1,2%, 6-10d=2%, 11-20d=3,5%. Halte > 20d ohne Quanto NO GO.
- **Notations-Falle UK-Listings (seit 06.05.2026):** Yahoo Finance gibt UK-Listings (Suffix `.L`) standardmäßig in **Pence (GBp)** aus, NICHT in Pound (GBP) — Faktor 100. Beispiele: SHEL.L „3192,00" = 31,92 GBP, nicht 3.192 GBP. Gilt für alle LSE-Werte (BP.L, AZN.L, GSK.L, RIO.L etc.). Vor Pre-Trade-Plan-Eintrag prüfen: (1) Yahoo-Wert mit Broker-Kurs (Frankfurt/Xetra-EUR-Listing oder ADR) plausibilisieren — Größenordnung muss stimmen. (2) Falls Pipeline-MARKETDATA für UK-Werte direkt aus Yahoo zieht: ATR-Distanzen, KO-Abstand, R:R-Zielwerte sind alle um 100 daneben → Pence-zu-Pound-Divisor in der Pipeline-Anbindung setzen (saubere Lösung), oder UK-Werte nur über ein Cross-Listing mit ausreichender Liquidität ziehen (Vorsicht: Cross-Listings sind oft Sekundär-Listings mit weniger Volumen, deutsche KO-Zertifikate basieren meist auf dem Primär-Underlying am LSE — Datenquelle und Zertifikats-Underlying sollten übereinstimmen). (3) Lektion 1 v2 (FX-Drag) bleibt davon unberührt — die wirkt erst nach der Notations-Korrektur.
- **Geopol-Bucket-Check (seit 06.05.2026):** Steht der Wert in einem Iran-/Geopol-Bucket (Sheet "Iran-Universum" oder Hauptwatchlist mit `[A1..A5]`/`[B1..B3]`/`[C]`-Tag in der Trigger-Spalte)? Wenn ja: (a) Bucket-Logik passt zur Setup-Richtung → konfluent, kein Problem. (b) Bucket-Logik widerspricht (z.B. ADS-Long im B1-Short-Bucket): **Soft-Hinweis im Plan**, kein hartes Veto — Eigen-Setup-Trigger kann Bucket schlagen. (c) Sub-Cluster A2 Cyber: max **1** von {CRWD, PANW, FTNT, ZS, NET, CHKP} parallel offen. (d) Hormus-Korrelation A1↔A5: Soft-Note "beide reagieren auf Hormus-Reopen, A5 zeitverzögert" wenn schon einer der Buckets offen. (e) STATE-Doc-Phase prüfen — in `acute`-Phase Wochenend-Halte-Regel beachten (Position vor Fr-Schluss um ~50% reduzieren bei aktivem Headline-Risiko, statt pauschalem Risiko-Aufschlag).
- Minimum-Einsatz ≥ 400€ (Lektion 2)

---

## Template B: Direktaktie (ohne Hebel)

```
=== DIREKTAKTIEN-TRADE-PLAN ===
Datum:            [Datum]
Aktie:            [Name, Ticker, ISIN]
Richtung:         Long / Short (Leerverkauf via TR?)
These:            [1–2 Sätze, konkreter Katalysator]
Zeithorizont:     [Wochen / Monate]

KURS & BEWERTUNG:
Aktueller Kurs:   [€]
52-Wochen-H/T:    [€ / €]
KGV (aktuell):    [x]
KGV (Sektor):     [x]  → Aufschlag/Abschlag?
Dividendenrendite:[%]
Nächster Ex-Tag:  [Datum oder "unbekannt"]
  ⚠️ Vor Ex-Tag kaufen = Dividende erhalten + Kursabschlag
     Nach Ex-Tag  = kein Dividenden-Anspruch, aber auch kein Abschlag

CHART (technisch):
Trend (Wochen-Chart):  [Aufwärts / Seitwärts / Abwärts]
Nächster Support:      [€]
Nächster Widerstand:   [€]
RSI (14):              [Wert] → [überkauft / neutral / überverkauft]
Besonderheiten:        [z.B. Gap, Ausbruch, Trendbruchlinie]

RISIKEN (Counter-These):
□ Aktives Rückkaufprogramm?    [Ja / Nein]
□ Frische Analysten-Upgrades?  [Ja / Nein / Quelle]
□ Dividende demnächst?         [Ja / Nein / Ex-Datum]
□ Strukturelle Gegenthese?     [z.B. Marktanteilsverlust, Regulierung]
□ Schwache Kursreaktion auf negative News? → Markt sieht etwas, das du nicht siehst
□ Geopol-Bucket-Konflikt?      [siehe Sheet "Iran-Universum" / Hauptwatchlist-Tag] → Soft-Hinweis, kein Veto
□ A2-Cyber-Sub-Cluster?        [max 1 von {CRWD, PANW, FTNT, ZS, NET, CHKP} parallel — wenn schon einer offen: SKIP]
□ Hormus-Korrelation A1↔A5?    [wenn schon A1 oder A5 offen: Soft-Note]

SIZING (2%-Regel):
Risikokapital gesamt: [€]
Max. Verlust (2%):    [€]
Einstiegskurs:        [€]
Stop-Loss-Kurs:       [€]  → Abstand: [%]
Stückzahl:            [= Max. Verlust / (Einstieg − SL)]
Einsatz:              [= Stück × Kurs + 1€ TR-Gebühr (bzw. 0€ bei SB+ über gettex)]

EXIT-REGELN:
SL:         [€]  → Max. Verlust [€]
TP1:        [€]  → Gewinn [€]  → bei TP1: 50% verkaufen, SL auf MAX(Breakeven, TP1 − 1,5×ATR)
TP2:        [€]  → Gewinn [€]  (optional — nur wenn charttechnisch begründet!)
R:R:        [x:x]  → Mindest 1,35:1
Thesis-Bruch: [konkretes Szenario, z.B. "Nachricht X dreht die These um"]
Zeitlimit:    [max. X Wochen — danach Neubewertung]

STEUER:
Aktientopf (§20 Abs. 2 Nr. 1 EStG) — Verluste NUR mit Aktiengewinnen verrechenbar.
Haltezeit > 1 Jahr: KEINE Steuerfreiheit (≠ Krypto!) — Abgeltungsteuer fällt immer an.

CHECKLISTE:
Signal-Check: [X/7] → [GO / NO GO]
Counter-These abgehakt: [Ja / Nein]
Aktientopf-Hinweis bestätigt: ✅
```

### Dividenden-Hinweis (immer prüfen)

- Kauf **vor** Ex-Dividenden-Tag → Dividende wird ausgezahlt, aber Kurs fällt um ca. Dividendenbetrag am Ex-Tag
- Kauf **nach** Ex-Tag → kein Dividenden-Anspruch, aber kein Kursabschlag-Risiko
- Bei Short-Positionen: Dividendenzahlung geht zu Lasten der Short-Position (synthetische Dividendenpflicht)

### Schritte zur Erstellung (Routine 1b)

1. Websuche (1–3 Abfragen): Fundamentaldaten, Ex-Dividenden-Datum, aktuelle Analystenstimmen
2. Template ausfüllen — fehlende Felder mit ⚠️ markieren
3. Signal-Checkliste 7 Punkte + Counter-These durchgehen
4. R:R und Positionsgröße berechnen
5. Ergebnis: GO / NO GO mit Begründung

---

## 🆕 Template C: Pre-Trigger-Order (Optional, seit 07.05.2026)

**Anwendungsfall:** Setup wartet auf Bestätigungskerze, Wartezeit > 3 Handelstage erwartbar, Counter-These sauber. Statt Live-Beobachtung Pre-Trigger-Order scharfschalten — mit reduziertem Sizing.

```
=== PRE-TRIGGER-ORDER ===
Datum:               [Datum]
Underlying:          [Name, Ticker]
Setup-Variante:      Pullback (Limit-Buy) / Breakout (Stop-Buy)
Aktueller Kurs:      [€/$]
Pre-Trigger-Niveau:  [€/$]   (Limit unter Kurs, oder Stop über Kurs)

PRODUKT (KO oder Aktie wie Template A/B):
Cert/Aktie-Trigger:  [Cert-Preis bei Underlying = Pre-Trigger-Niveau]

SIZING (1%-Klasse — fix, keine Hochstufung):
Max. Verlust:        150€
SL Underlying:       [€]
SL Cert (falls KO):  [€]
Stückzahl:           [= 150 / (Cert-Trigger − Cert-SL)]
Einsatz:             [Stk × Cert-Trigger + Gebühr]

ORDER-WORKFLOW:
□ Limit-Buy / Stop-Buy bei [Cert-Preis] — GTC bis [Verfall-Datum]
□ Bei Fill: Push-Notification von SB+ (Mail/App)
□ Reaktionsfrist 1 HT: SL-Order manuell anlegen (Stop-Loss-Sell bei Cert-SL)
□ Optional TP-Order anlegen (Limit-Sell bei Cert-TP1)

EXIT-REGELN (nach Fill):
SL Underlying:       [€]   → Cert-Preis ca. [€]
TP1 Underlying:      [€]   → Cert-Preis ca. [€]
R:R:                 [x:x] (Mindest 1,35)
Zeitstopp:           [Verfall-Datum]

VERFALL:
Pre-Trigger-Order verfällt mit Watchlist-Verfallsdatum (max. 14 HT, oder Event-bezogen).
Wenn Order bis Verfall nicht gefillt → Order stornieren, Setup re-evaluieren.
```

**Limitierungen (wichtig):**
- **SB+ erlaubt KEINE Pre-Trade-OCO** — Sell-Orders nur nach Kauf-Fill anlegbar. Position zwischen Fill und manueller SL-Eingabe **ungesichert**.
- 1%-Sizing **fix**, keine Hochstufung „nachträglich auf 2%" wenn Bestätigungskerze später kommt
- Bei volatilen Underlyings (ATR > 4% des Kurses) Pre-Trigger-Stop-Buy vorsichtig dosieren — Gap-Risiko
- Pre-Trigger ist **kein Ersatz** für Live-Trading bei 6/7- oder 7/7-Setups — bei hoher Konviktion lohnt die Live-Beobachtung wegen besserem Sizing

**Anwendungsfall am konkreten Beispiel:**
Setup: CF Long am EMA50, Bestätigung erwartet im Range 117–119$. Statt nur auf Daily-Close zu warten:
- Pre-Trigger Limit-Buy bei z.B. Cert-Preis entsprechend Underlying 117$ (1% Sizing, 150€ Risk)
- Wenn intraday auf 117 gefüllt → SL bei 115 manuell setzen, TP1 130 wie Plan
- Wenn Daily-Close zusätzlich Bestätigungskerze zeigt → KEINE Aufstockung. Position bleibt bei 1%, R:R bleibt sauber.
- Wenn Pre-Trigger nicht gefüllt UND Daily-Close-Bestätigung am gleichen Tag → normaler 6/7-Trigger mit 2% Sizing am Folgetag
