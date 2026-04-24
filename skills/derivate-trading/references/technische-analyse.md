# Technische Analyse — Referenz

**Diese Datei wird geladen bei:** Indikator-Fragen, Chart-Analyse, TradingView-Setup, Candlestick-Patterns, Chart-Abgleich im Makro-Analyse-Workflow.

---

## Inhaltsverzeichnis
1. Progressive Lernpfade (Level 1–3)
2. Widerstände erkennen — Confluence-Modell
3. Indikatoren mit Formeln
4. Candlestick-Patterns Top 5
5. TradingView-Setup (Essential)
6. Watchlist-Ticker

---

## 1. Progressive Lernpfade

### Level 1 — Grundlagen (aktueller Stand)
- **EMAs:** EMA20, EMA50, EMA100, EMA200
- **RSI (14 Perioden):** Momentum, Überkauft/Überverkauft
- **Volumen:** Bestätigung von Moves
- **Support/Resistance:** horizontale Levels aus historischen Wendepunkten
- **Candlestick-Basics:** Doji, Hammer, Engulfing

### Level 2 — Fortgeschritten (nächster Schritt)
- **MACD:** Trendstärke und Momentum-Umkehr
- **Bollinger Bänder (20, 2):** Volatilität und Mean-Reversion
- **ATR (14):** Volatilitätsmessung für SL-Kalibrierung
- **Fibonacci Retracements:** 38,2% / 50% / 61,8% in Trends
- **Multi-Timeframe-Analyse:** 4h-Chart + Daily-Bestätigung

### Level 3 — Professionell (Ziel)
- **Ichimoku Cloud:** Trend + Momentum + S/R in einem Indikator
- **Volume Profile:** Preis-Volumen-Verteilung für echte S/R-Levels
- **Order Flow / Level 2:** Orderbuch-Analyse
- **Divergenzen:** RSI-Preis-Divergenzen als Frühwarnung
- **Sektorrotation:** Relative Stärke zwischen Sektoren

---

## 2. Widerstände erkennen — Confluence-Modell

**Grundprinzip:** Ein Widerstand/Support zählt erst, wenn **mehrere unabhängige Methoden** dasselbe Preisniveau markieren. Das nennt man **Confluence**. Eine einzelne runde Zahl allein ist kein Widerstand.

### Die fünf Methoden in Priorität

**1. Kerzen-Dochte (Wicks) — wichtigste Methode**
- Langer Docht nach oben = Kurs hat das Level angetestet und wurde abgewiesen
- Mehrere Dochte auf gleicher Höhe = mehrfache Abweisung = echter Widerstand
- Faustregel: 2 Tests reichen nicht, 3 Tests machen das Level "offiziell"
- Immer ZUERST im Chart suchen, nicht nachträglich aus dem Kopf konstruieren

**2. EMAs als dynamische Levels**
- Im Aufwärtstrend: Kurs > EMA20 > EMA50 > EMA100 > EMA200 = gesunde Staffelung
- EMA20 fängt leichte Pullbacks ab, EMA50 mittlere, EMA100/200 bei Trendwechsel-Verdacht
- Im Abwärtstrend umgekehrt: EMAs wirken als Widerstand bei Erholungen

**3. Vorherige Hochs/Tiefs (Marktgedächtnis)**
- ATH/ATL sind die stärksten historischen Levels
- Auf Daily-Chart wechseln für 6–12 Monate Kontext (4h zeigt nur ~2 Monate)
- Zwischenhochs in Korrekturen zählen ebenfalls

**4. Psychologische Marken (runde Zahlen)**
- Dezimal-Zehner (150, 250, 260) → schwach bis mittel
- Halbe Hunderter (150, 250, 350) → mittel
- Volle Hunderter (200, 300) → stark
- **NIE als Ersatz für Methode 1** — immer nur als Zusatz-Confluence

**5. Volumen-Profile**
- Volumen-Balken unter dem Chart zeigen Preisniveaus mit hohem Handelsvolumen
- Dort werden bei Rückläufen Stops liegen und Breakeven-Exits ausgelöst
- TradingView Essential: Volume-Balken reichen; Volume Profile ist Premium-Feature

### Anti-Muster (häufiger Fehler)

**Runde-Zahl-Extrapolation:** Eine runde Zahl in der Nähe picken und dann rückwärts "mehrfach abgewiesen" behaupten — ohne den Chart wirklich abzulesen. Dieser Fehler führt zu falschen TP1-Levels und verzerrtem R:R. Wenn ein Level nicht durch Methode 1, 2 oder 3 gestützt ist, zählt es nicht als Widerstand.

### Anwendungs-Reihenfolge

1. **Zoom auf Daily-Chart** (größerer Kontext)
2. **Horizontallinien** an allen Turning Points (Dochte-Cluster)
3. **EMAs** als dynamische Ergänzung
4. **Runde Zahlen** als Confluence-Ergänzung — nicht als Ausgangspunkt
5. **Confluence prüfen**: Je mehr Methoden auf dasselbe Niveau zeigen, desto stärker der Level

### Anwendung auf Trade-Setups

Wenn der User einen TradingView-Screenshot liefert:
- **Immer vom Chart ablesen**, nicht aus dem Kopf extrapolieren
- Bei Zielbestimmung explizit benennen: "Das lokale Hoch liegt bei ~X,XX € (Kerze vom TT.MM.)"
- TP1 = nächster echter Widerstand im Chart, NICHT die nächste runde Zahl
- Falls kein klarer Chart-Widerstand im Zielbereich: TP1 via ATR-Projektion (Einstieg + 2–3× Daily-ATR), **explizit als Schätzung kennzeichnen**

---

## 3. Indikatoren mit Formeln

### EMA (Exponential Moving Average)

**Formel:**
```
Multiplier k = 2 / (Perioden + 1)
EMA_heute = (Kurs_heute − EMA_gestern) × k + EMA_gestern
          = Kurs_heute × k + EMA_gestern × (1 − k)
```

**Mathe-Bezug:** Gewichtete Summe mit exponentiell abnehmenden Gewichten — neuere Daten haben überproportional mehr Einfluss (geometrische Reihe mit Quotient (1−k)).

**Standardeinstellungen:**
- EMA 20: Kurzfristiger Trend (ca. 4 Wochen Trading-Tage)
- EMA 50: Mittelfristiger Trend (ca. 10 Wochen)
- EMA 100: Mittelfristig, oft Support/Resistance-Zone
- EMA 200: Langfristiger Trend (ca. 1 Jahr)

**Trading-Signale:**
- **Bullish:** Kurs > EMA20 > EMA50 > EMA200 (bullisch aufgefächert, "Golden Cross")
- **Bearish:** Kurs < EMA20 < EMA50 < EMA200 (bärisch aufgefächert, "Death Cross")
- **Neutral/Range:** EMAs flach und verwoben

**EMA als dynamischer Support/Resistance:**
- Im Aufwärtstrend: EMA20/50 oft Support → Pullback-Kauf
- Im Abwärtstrend: EMA20/50 oft Resistance → Rally-Verkauf
- EMA200: stärkere Zone, selten durchbrochen ohne Trendwechsel

---

### RSI (Relative Strength Index, 14 Perioden)

**Formel:**
```
RS = Durchschnittlicher Gewinn (14) / Durchschnittlicher Verlust (14)
RSI = 100 − 100 / (1 + RS)
```

**Mathe-Bezug:** Normierung auf [0, 100] durch die Funktion f(x) = 100 − 100/(1+x). Bei RS = 1 (gleich viel Gewinn wie Verlust) → RSI = 50. Funktion konvergiert asymptotisch gegen 0 und 100.

**Interpretation:**
- **Überkauft:** RSI > 70 → Korrektur wahrscheinlich
- **Überverkauft:** RSI < 30 → Bounce wahrscheinlich
- **Neutral:** RSI 40–60 → kein klares Signal

**⚠️ RSI-Fehlsignale:**
- In starken Trends bleibt RSI oft überkauft (>70) oder überverkauft (<30) — "RSI reitet"
- RSI-Divergenz (Kurs steigt, RSI fällt) ist stärker als Absolut-Level
- Niemals allein auf RSI verlassen — immer mit EMA/Trendrichtung kombinieren

**Trading-Regeln:**
- **LONG Setup:** RSI < 30 UND Kurs nahe EMA50 im Aufwärtstrend → Bounce
- **SHORT Setup:** RSI > 70 UND Kurs nahe EMA20 im Abwärtstrend → Rejection
- **Kein Trade:** RSI extrem (>80 oder <20) ohne Divergenz

**RSI-Divergenz (starkes Signal):**
- **Bullish Divergence:** Kurs tieferes Tief, RSI höheres Tief → Trendumkehr möglich
- **Bearish Divergence:** Kurs höheres Hoch, RSI tieferes Hoch → Trendumkehr möglich

---

### ATR (Average True Range, 14 Perioden)

**Formel:**
```
True Range = max(High − Low, |High − Close_gestern|, |Low − Close_gestern|)
ATR = gleitender Durchschnitt der True Range über 14 Perioden
```

**Zweck:** Volatilitätsmessung — NICHT Trendrichtung!

**Verwendung im Trading:**
- **SL-Kalibrierung (Lektion 4):** SL-Abstand mindestens **1,5 × ATR** vom Einstieg entfernt
- **TP-Plausibilitätscheck (Lektion 13):** >5–6 ATRs in 2–3 Wochen = unrealistisches Ziel
- **Nachziehen bei TP1 (Lektion 13):** Neuer SL = MAX(Breakeven, TP1 − 1,5 × ATR)
- **ATR% im Markt:** ATR relativ zu Kurs → >4% täglich = sehr volatil

**Beispiel (AIXTRON 4h-Chart):** ATR 0,49 € → Tages-Range ca. 0,49 × 2,5 = ~1,22 €. SL-Abstand 1,83 € = 1,5 ATR. TP1 bei +1,22 € = 1 Tagesrange.

---

### MACD (Moving Average Convergence Divergence) — Level 2

**Formel:**
```
MACD-Linie  = EMA12(Kurs) − EMA26(Kurs)
Signal-Linie = EMA9(MACD)
Histogramm  = MACD − Signal
```

**Signale:**
- MACD kreuzt Signal von unten → bullish
- MACD kreuzt Signal von oben → bearish
- Histogramm wächst → Trendstärke nimmt zu
- Divergenz MACD vs. Kurs → Trendwende möglich

---

### Bollinger Bänder (20, 2) — Level 2

**Formel:**
```
Mittlere Linie = SMA20(Kurs)
Oberes Band   = SMA20 + 2 × σ20 (Standardabweichung der letzten 20 Kurse)
Unteres Band  = SMA20 − 2 × σ20
```

**Mathe-Bezug:** Innerhalb von ±2σ liegen ca. 95% aller Kurswerte (bei Normalverteilung).

**Signale:**
- Kurs berührt oberes Band → Mean-Reversion Short oder Trend-Durchbruch
- Kurs berührt unteres Band → Mean-Reversion Long oder Trend-Durchbruch
- **Bollinger Squeeze** (Bänder eng) → Volatilitäts-Ausbruch steht bevor
- **Bollinger Expansion** → Trend-Beschleunigung

---

## 4. Candlestick-Patterns Top 5

### 1. Hammer (bullish reversal)
- Kleiner Körper oben, langer unterer Docht (≥ 2× Körper), kaum oberer Docht
- **Kontext:** Am Ende eines Abwärtstrends
- **Signal:** Käufer übernehmen, Boden-Signal

### 2. Shooting Star (bearish reversal)
- Kleiner Körper unten, langer oberer Docht, kaum unterer Docht
- **Kontext:** Am Ende eines Aufwärtstrends
- **Signal:** Verkäufer übernehmen, Top-Signal

### 3. Bullish Engulfing (bullish reversal)
- Kleine rote Kerze, gefolgt von großer grüner Kerze, die die rote komplett umschließt
- **Kontext:** Abwärtstrend + Support-Zone
- **Signal:** Starke bullishe Umkehr

### 4. Bearish Engulfing (bearish reversal)
- Kleine grüne Kerze, gefolgt von großer roter Kerze, die die grüne komplett umschließt
- **Kontext:** Aufwärtstrend + Resistance-Zone
- **Signal:** Starke bärische Umkehr

### 5. Doji (indecision)
- Öffnungs- = Schlusskurs (kleinster Körper), lange Dochte nach oben und unten
- **Kontext:** Nach starkem Trend = Erschöpfung; in Range = normales Rauschen
- **Signal:** Trend-Pause; Bestätigung durch nächste Kerze nötig

---

## 5. TradingView-Setup (Essential)

**Matthias' TradingView Essential:**
- Max. **5 Indikatoren pro Chart**
- Alerts verfügbar
- Kein Pine Script (Custom Indicators)

### Standard-Setup für KO-Trades (4h-Chart)

| Indikator | Parameter | Zweck | Farbe (Empfehlung) |
|-----------|-----------|-------|---------------------|
| EMA 20 | Close | Kurzfristiger Trend | Grün |
| EMA 50 | Close | Mittelfristiger Trend | Gelb/Orange |
| EMA 200 | Close | Langfristiger Trend | Rot |
| RSI 14 | — | Momentum | Separates Panel |
| ATR 14 | — | Volatilität / SL-Kalibrierung | Separates Panel |

**Timeframes für Multi-Timeframe-Analyse:**
- **Daily:** Trendkontext
- **4h:** Entry-Signal (Hauptchart für KO-Trades mit 1–3 Wochen Haltedauer)
- **1h:** Feinjustierung Entry, bei besonders engen Setups

### Notation-Hinweis

TradingView zeigt Dezimalzahlen im englischen Format (Punkt): `132.50`
→ Immer in deutsche Notation umrechnen: `132,50 €`

---

## 6. Watchlist-Ticker

### Aktien (Xetra)

| Aktie | Ticker | Sektor |
|-------|--------|--------|
| Fraport | `XETR:FRA` | Aviation |
| Lufthansa | `XETR:LHA` | Aviation |
| Ströer | `XETR:SAX` | Medien |
| KION | `XETR:KGX` | Intralogistik |
| TUI | `XETR:TUI1` | Tourismus |
| Siemens Energy | `XETR:ENR` | Energie |
| Heidelberg Materials | `XETR:HEI` | Baustoffe |
| Salzgitter | `XETR:SZG` | Stahl |
| Beiersdorf | `XETR:BEI` | Consumer |
| AIXTRON | `XETR:AIXA` | Halbleiter |
| Jenoptik | `XETR:JEN` | Optik |
| CTS Eventim | `XETR:EVD` | Ticketing/Live |
| Deutsche Börse | `XETR:DB1` | Finanzinfrastruktur |
| Heidelberger Druck | `XETR:HDD` | Druck/Defense |

### Rohstoffe / ETPs

| Asset | Ticker | Hinweis |
|-------|--------|---------|
| WTI Crude Oil | `TVC:USOIL` / `NYMEX:CL1!` | USD-denominiert |
| Brent Crude Oil | `TVC:UKOIL` | USD-denominiert |
| EU Natural Gas (TTF) | `TVC:TTFG1!` | EUR-denominiert (TTF!) |
| Gold | `TVC:GOLD` | USD/Unze |
| Silber | `TVC:SILVER` | USD/Unze |

### Indizes / Sentiment

| Index | Ticker | Zweck |
|-------|--------|-------|
| DAX | `XETR:DAX` | Leitindex |
| MDAX | `XETR:MDAX` | Mid Caps |
| SDAX | `XETR:SDAX` | Small Caps |
| TecDAX | `XETR:TECDAX` | Tech-Werte |
| S&P 500 | `SP:SPX` | US-Leitindex |
| VIX | `TVC:VIX` | US-Volatilität |
| VDAX-NEW | `TVC:DV1X` | DAX-Volatilität |

---

## Watchlist-Pflege

- Neue Watchlist-Kandidaten mit Alert-Kurs (EMA-Bruch, RSI-Wert) hinterlegen
- Alle 1–2 Wochen durchsehen und inaktive Kandidaten entfernen
- Nach jeder Watchlist-Änderung ins Journal-Sheet "Watchlist" eintragen
