# Trade-Plan-Templates

**Wird geladen bei:** Routine 1b (Direktaktie analysieren), neue Position planen, "Trade-Plan erstellen".

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
- Fremdwährungs-Underlying? → NO GO (Lektion 1)
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
