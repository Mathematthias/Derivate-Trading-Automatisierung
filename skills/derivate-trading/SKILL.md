---
name: derivate-trading
description: >
  KO-Zertifikate, Turbo-Shorts/Longs, Direktaktien, Trade Republic, Smartbroker+,
  Journal (openpyxl), Morgen-Briefing, TP/SL-Analyse, Makro-Check, Chart-Analyse,
  News-Scan, Hidden Scan, Skandal-Scan, Event-Trading, Insider-Kauf, Insider-Verkäufe,
  Cluster-Sells, DGAP Ad-hoc, Directors Dealings, Aktienveräußerungen, Aktientopf,
  §20 EStG, Vonovia, Direktkauf Aktie, Short Long KO Hebel Derivat TR Lufthansa
  TUI Salzgitter Fraport KION.
---

# Derivate-Trading Skill

Operatives Handbuch für gehebelte Derivate-Trades auf Trade Republic und Smartbroker+. Kodifiziert Regeln, Workflows und Lektionen aus der bisherigen Zusammenarbeit.

## Notation: „Note #N"

`Note #N` in diesem Skill bezeichnet einen **Skill-internen Changelog-Eintrag** — die fortlaufende Nummerierung der Regel-/Lektions-Ergänzungen dieses Handbuchs. Das **Journal-Notes-Sheet** (`Trading_Journal_*.xlsx`, Sheet „Notes") führt eine **eigene, unabhängige ID-Folge**. Die Nummern beider Systeme korrespondieren NICHT — `Note #66` im Skill ist nicht dasselbe wie Zeile/ID 66 im Journal-Notes-Sheet. Skill-Querverweise (`Note #N`, `siehe § …`) meinen immer den Skill-Changelog. Ist ausnahmsweise ein Journal-Eintrag gemeint, wird er explizit „Journal-Note #N" genannt.

## ⚡ Routinen-Schnellreferenz

| Codewort / Trigger | Routine | Detail in |
|--------------------|---------|-----------|
| „Trade eintragen" / „hab gekauft" (KO/ETF/ETP) | 1 | unten |
| „Aktie gekauft" / Direktaktie ohne KO-Kürzel | 1a | unten |
| „Aktie analysieren" / „Trade-Plan Aktie" | 1b | `references/trade-plan-templates.md` |
| „verkauft" / „ausgestoppt" / „Stop-Loss" | 2 | unten |
| TR-PDF hochladen | 3 | unten |
| „Aufräumen" / „⚠️ abarbeiten" | 4 | unten |
| Claude/ChatGPT-Rechnung nennen | 5 | unten |
| „Analyse erstellen" / „TP/SL-Übersicht" | 6 | unten |
| „Morgen-Briefing" / „Tagescheck" | 7 | unten |
| „News-Scan" / „Skandal-Scan" / „aktuelle Thesen" | 8 | `references/news-scan.md` |
| **„Hidden Scan"** / **„Randnotizen"** / **„was hat keiner auf dem Schirm"** | **8b** | `references/news-scan.md` |
| **„Insider-Verkäufe"** / **„Sells-Check"** / **„Short-Dealings"** | **8c** | `references/news-scan.md` |
| „Makro-Check" / „Nachrichtenlage" | Makro | unten |

**🚨 AUSFÜHRUNGSREGEL — SOFORT HANDELN:** Bei den Codewörtern oben **nicht** fragen/erklären — Referenz lesen (wenn angegeben), Routine sofort ausführen. Bei „Trade eintragen" + vollständigen Daten → direkt Journal updaten. Bei „Morgen-Briefing" → direkt im Action-Layer-Format ausgeben (6 Buckets, siehe Routine 7), kein Kompakt/Detail-Dialog.

## Kontext

Der User ist Anfänger mit wachsender Erfahrung. Primär Open-End Turbo KO-Zertifikate (Short/Long) + gelegentlich Direktaktien. Kapital explizit als spekulatives "Zock-Geld" getrennt vom langfristigen Portfolio.

**Ethik-Regel (15.04.2026):** Keine Investments in Angriffswaffen-Kerngeschäft (Panzer, Munition, Kampfflugzeuge, Raketen). Defensive Technologien OK wenn Defense-Umsatz < 30% und primär schützend. Ausschluss: Rheinmetall, KNDS, BAE. OK: Heidelberg Druck (via ONBERG), Jenoptik.

**Instrument-Erkennung vor Journal-Eintrag:**
- KO-Zertifikat / Turbo / ETP / ETF → Routine 1 → Sheet „Sonstige Kapitalerträge"
- Direktaktie (kein KO-Kürzel) → Routine 1a → Sheet „Aktienveräußerungen"

## Kernformeln

### Zertifikatspreis
```
Short KO: Zertpreis = (KO − Underlying) × BV
Long KO:  Zertpreis = (Underlying − KO) × BV
```
Bezugsverhältnis (BV) meist 1,0 oder 0,1.

### Hebel / KO-Abstand / Spread
```
Hebel       = Underlying / (Zertpreis / BV)
KO-Abstand  = |KO − Underlying| / Underlying × 100%    (Ziel ≥ 20%, Min. 15%)
Spread%     = (Brief − Geld) / Geld × 100%             (gut <1,5%, ok <3%, >5% Finger weg)
```

### Positionsgröße (Fixed-Fractional — Pflicht seit Lektion 12)
```
Max. Verlust = Risikokapital × Sizing-Faktor
Stückzahl    = Max. Verlust / (Einstieg − SL)
Einsatz      = Stückzahl × Briefkurs
Kaufsumme    = Einsatz + Gebühr Kauf    (ab v3 explizit einpflegen)
```

**🆕 Hybrid-Skala ist DEFAULT (seit 07.05.2026), nicht Ausnahme.** Score-abhängige Sizing-Klassen:

| Score | Sizing-Faktor | Max-Verlust (15.000€-Basis) | Charakter |
|-------|--------------|------------------------|-----------|
| 5/7   | 1%           | 150€                   | Standard-Frequenz-Position, häufiger Trigger akzeptabel |
| 6/7   | 2%           | 300€                   | Standard-Konviktion-Position |
| 7/7   | 3%           | 450€                   | Hohe Konviktion, alle Filter durch |
| Insider+7/7 | 4%     | 600€                   | Premium, nur bei Cluster-Insider-Kauf-Signal |
| Pre-Trigger (s.u.) | 1% | 150€                | Vor Bestätigungskerze, mit Limit/Stop-Buy |

**Wichtig zur Frequenz-Logik:** 5/7-Trades sind explizit erlaubt — sie sind die Frequenz-Klasse. Der Erwartungswert bleibt positiv solange Trefferquote ≥ 35% (bei R:R 2,0). Nicht als Trade-Pattern vermeiden.

Korrelierte Positionen zählen als **ein** Block.

**Sub-Cluster-Budget (risk-basiert, seit 22.05.2026 — ersetzt die frühere Stückzahl-Obergrenze „MAX 1"):** Pro Sub-Cluster (z.B. Insurance, Cyber-A2) gilt ein **Risk-Budget** statt einer Positions-Stückzahl. Das Budget = Sizing-Faktor der stärksten Score-Klasse im Cluster (Insider+7/7 → 4% = 600€; sonst entsprechend niedriger). Konkret **Insurance-Cluster {MUV2, HNR1, TLX}: Budget 4% Risikokapital.** Ein neuer Trade im Cluster ist zulässig, solange Σ(tatsächliches Risk der offenen Cluster-Positionen) + Risk des neuen Trades ≤ Budget. Beispiel: bei offener MUV2-Position mit ~2,3% Risk verbleibt ~1,7% Headroom = genau ein weiterer 1%-Trade. Bei Doppel-Trigger im selben Cluster entscheidet die Edge-Hierarchie (§ Pipeline-WL-Merge-Regel), bei gleichem Edge-Tier das R:R-beste Setup. Über alle Cluster hinweg bleibt die SB+-Liquiditäts-Formel (§ Kapital-Basis) das übergeordnete Cap.

**Minimum:** Unter 400€ sind KO-Zertifikate spread-ineffizient.

### Kapital-Basis & Plafond — SB+ (Stand 2026-05-23)

Zwei getrennte Ebenen, nicht verwechseln:

**Ebene 1 — Risikokapital (Loss-Sizing-Basis) = 15.000€.** Die Hybrid-Skala rechnet den Max-Verlust pro Trade als Prozentsatz dieser Basis (1/2/3/4% → 150/300/450/600€). Eine feste, notionale Bezugsgröße — sie läuft nicht mit dem Kontostand mit.

**Ebene 2 — SB+-Liquidität (Positionssummen-Cap) ≈ 12.000€.** Das tatsächlich auf SB+ liquide Kapital. Es begrenzt, wie viel *Einsatz* (Positionssumme in €) gleichzeitig im Markt sein darf — nicht den Risikobetrag. Vor jedem neuen Setup:

```
Einsetzbar = 12.000€ − 2.000€ Makro-Reserve − Σ(Einsatz offener Positionen)
```

- **2.000€ Makro-Reserve:** hart zurückgehalten für eine plötzlich auftretende Makro-These mit A+++-Trade-Gelegenheit. Wird für reguläre Watchlist-/Briefing-Setups **nicht** angetastet.
- **Σ(offene Positionen):** investierter Betrag (Einsatz, nicht Max-Verlust) aller laufenden Trades — aktuell MUV2 #60 ≈ 2.000€. Quelle: Sheet „Übersicht" Portfolio-Block. → aktuell einsetzbar ≈ 8.000€.
- Diese Formel ersetzt die ältere Faustregel „freies Gesamtrisiko-Budget < 70% Risikokapital" (Checklisten-Punkt 7) — bei Konflikt gilt die Formel.

**Divergenz Ebene 1 ↔ 2 ist gewollt:** Die Sizing-Basis (15.000€) liegt aktuell über dem real liquiden SB+-Kapital (~12.000€). Das ist bekannt und Teil des Plans, nicht ein Fehler — beim nächsten 5er-Block-Review (Block inkl. MUV2 #60) entscheidet der User über (a) Anhebung Risikokapital 15.000€ → 20.000€ und Aufstocken des SB+-Cash auf mehr liquides Kapital, und (b) ob 3% statt 2% das „normale" Sizing der Hybrid-Skala wird. Bis dahin: Basis 15.000€, Skala 2% = Standard-Konviktion.

### 🆕 Pre-Trigger-Orders (Limit-Buy / Stop-Buy)

Wenn Setup auf Bestätigungskerze wartet, kann statt Live-Beobachtung eine **Pre-Trigger-Order** scharfgeschaltet werden — mit reduziertem Sizing als Sicherheits-Compromise. Zwei Varianten:

| Variante | Order-Typ | Wann | Sizing |
|----------|-----------|------|--------|
| **Pre-Trigger Pullback** | Limit-Buy unter aktuellem Kurs | Reverse-Setup (Long am EMA20/50/200, oder Short am Hoch) | **1% (150€)** |
| **Pre-Trigger Breakout** | Stop-Buy über aktuellem Kurs | Breakout-Setup (Long über Resistance, Short unter Support) | **1% (150€)** |

**Anwendungsfall:** „Bauchgefühl will rein, Bestätigung fehlt noch." Counter-These muss sauber sein (Step-1-Check, s.u.). Bei Fill: SL **manuell innerhalb 1 Handelstag** setzen — SB+ erlaubt KEINE Pre-Trade-OCO, Sell-Orders nur nach Kauf-Fill anlegbar.

**Limitierungen:**
- Position zwischen Fill und manueller SL-Eingabe **ungesichert** → Stop-Buy bei volatilen Underlyings vorsichtig dosieren
- 1%-Sizing zwingend, keine Hochstufung „nachträglich auf 2%"
- Wenn Bestätigungskerze später doch kommt (Setup wird 6/7 oder 7/7), dürfen **nicht** zusätzlich aufgestockt werden — Position bleibt bei 1%, R:R bleibt sauber
- Pre-Trigger-Order verfällt mit Watchlist-Verfallsdatum (s.u.) automatisch
- **🆕 SB+-KO-Direkthandel kennt keinen Stop-Buy** (nur Limit-Buy). Die Variante *Pre-Trigger Breakout* ist auf SB+ deshalb **nicht** als KO-Order umsetzbar — nur per Direktaktie/Aktientopf mit Stop-Buy oder als bewusste Live-Order. Limit-Buy bildet sauber nur Pullback-Entries ab. Detail: § Momentum-Continuation-Long.

**Workflow im Watchlist-Eintrag:** Pre-Trigger-Order-Niveau zusätzlich zum normalen Trigger im Entry-Trigger-Feld dokumentieren (z.B. „Pre-Trigger Limit-Buy 117$ / 1% Sizing parallel zum 7/7-Trigger 122$ / 2%").

### 🆕 Volumen — Rolle nach Entry-Typ (Green/Red-Flag-Logik, 2026-05-23)

Volumen ist ein Bestätigungs-Sicherheitsnetz, kein Prädiktor — und **niedriges Volumen ist nicht per se ein Red Flag.** Was es bedeutet, hängt am Entry-Typ und daran, *wo* in der Bewegung gemessen wird:

| Entry-Typ | Relevante Volumen-Lesung | Niedriges Volumen bedeutet |
|-----------|--------------------------|-----------------------------|
| **Breakout** | Volumen am Ausbruchstag | **Red Flag** — minderwertiger Ausbruch, erhöhtes Fade-Risiko |
| **Pullback / Reversal** | Volumen der Bounce-/Reverse-Kerze, **nicht** des Rücksetzers | im Rücksetzer: **Green Flag** (erschöpfte Verkäufer, kein Distributions-Druck). Auf der Bounce-Kerze: dann Red Flag (Bestätigung fehlt) |
| **Limit-Buy / Pre-Trigger** | — (Order füllt vor jeder Volumen-Lesung) | strukturell nicht bewertbar; auf SB+ stets Pullback → Pullback-Logik gilt |

**Hartes Veto — ja/nein:** Volumen ist hartes Gegenkriterium **nur beim Breakout-Entry auf der bestätigten Tageskerze**, weil das Volumen dort final bekannt ist (Sub-Schwelle-Schluss → kein BEREIT). Intraday vor dem Close ist es „pending" — kein Veto möglich, nur das Volumen-*Tempo* als weicher Check (läuft das Tagesvolumen 1h vor Close schon Richtung ≥1,2×?) plus reduziertes Sizing. Limit-Buy-/Pre-Trigger-Orders füllen volumen-blind → das reduzierte 1%-Sizing **ist** die Kompensation, ein Vor-Veto wäre mechanisch unmöglich.

**False-Red-Flag-Schutz fürs Briefing und die Setup-Analyse:** „Schwaches Volumen" nur dann als ⚠️ ausweisen, wenn das Setup ein **Breakout mit abgeschlossenem Tag** ist. Bei **Pullback-/Reversal-Setups** niedriges Rücksetzer-Volumen neutral bis positiv einordnen — **nie als Mangel oder Red Flag flaggen.** Das Warnsignal wäre dort umgekehrt *hohes* Volumen *im* Rücksetzer (Distribution statt gesundem Pullback). Die richtige Frage beim Pullback ist „kommt die Bounce-Kerze auf Volumen?", nicht „war der Rücksetzer dünn?". Ergänzt 7/7-Punkt 2 (Technisches Signal).

**Post-Fill-Review:** Nur beim **Breakout**-Pre-Trigger — schloss der Ausbruchstag schwach aufs Volumen, Position als degradiert behandeln (SL zügiger Richtung Breakeven, nicht wie ein 7/7 laufen lassen). Beim Pullback-Limit-Buy entfällt das: dünnes Volumen war hier nie das Problem.

### 🆕 Watchlist-Verfallsdatum (seit 07.05.2026)

Jeder Watchlist-Eintrag hat ein **hartes Re-Eval-Datum** (Spalte H, oder im Status-/Datum-Feld dokumentiert). Default: **+14 Handelstage ab Eintrags-Datum**. Am Verfalltag passiert eines:

1. **Trigger erreicht oder Pre-Trigger-Order gefillt:** Setup wird zum Trade, Watchlist-Eintrag schließt
2. **Trigger nicht erreicht, These intakt:** Verfall um max. 7 weitere HT verlängern (einmalige Verlängerung, klar dokumentiert „Verlängert YYYY-MM-DD")
3. **Trigger nicht erreicht, These hinfällig:** Eintrag in Bucket „archived" (Audit), nicht löschen — Lehre für Filter-Kalibrierung

**Event-Ausnahme:** Wenn Setup auf einen konkreten Termin wartet (Earnings, HV, Ex-Div, regulatorisches Event), Verfall = **Event-Datum + 3 Handelstage** statt 14 HT. Beispiel: TUI Q2 13.05. → Verfall 18.05. Termin im Verfall-Feld benennen.

**Frequenz-Treiber:** Diese Regel zwingt Trade-Entscheidungen in definierten Fenstern, statt unendlich zu pausieren. Setups, die mehrfach „re-eval bei Pullback" geflaggt werden ohne dass der Pullback kommt, fallen automatisch raus — die strukturelle Inflation der Watchlist wird begrenzt.

### Gebühren-Defaults (v3 — für Transparenz-Spalte)

| Broker / Handelsplatz | Gebühr pro Order | Hinweis |
|-----------------------|------------------|---------|
| Trade Republic | **1,00€** | Flatrate alle Börsen |
| Smartbroker+ / Gettex | **4,00€** | Minimum; default für SB+ ohne Plätz-Hinweis |
| Smartbroker+ / Frankfurt Zertifikate | **5,90€** | Nicht-Gettex-KOs (z.B. bei HSBC-IDs mit W-Endung) |
| Smartbroker+ / Xetra | 4,00€ + ~0,12% | Selten bei Derivaten |

**Pflicht beim Trade-Eintrag ab v3:** Kauf-Gebühr ist **in Kaufsumme einzurechnen** UND zusätzlich in Spalte N (SK) bzw. O (AV) explizit auszuweisen. Matthias liefert die Gebühr bei neuen Trades mit. Beim Close analog für die Verkauf-Gebühr.

## Die Lektionen (Kurzfassung)

1. FX-Underlyings erlaubt mit Pre-Trade-Check — Quanto-Default, Non-Quanto über FX-adjustierten R:R-Check (Lektion 1 v2: adjust. R:R ≥ 1,4 nach FX-Drag-Abzug); EM-Währungen (TRY/ZAR/ARS/MXN/RUB/BRL) ausgeschlossen; Rohstoff-Korrelation bei NOK/CAD/AUD/BRL explizit prüfen; kein Entry <90min vor Earnings. Volltext: Journal-Sheet „Lektionen" und references/produktkenntnis.md. Universums-Logik: Abschnitt „Handelsuniversum" unten.
2. Mindestposition ~400–500€
3. Open-End KOs max. 2–3 Wochen halten — Finanzierungskosten
4. SL-Abstand ≥ 1,5× ATR — nicht nach Bauchgefühl
5. Gewinnziele VOR Einstieg — R:R ≥ 1,35:1
6. Gestaffelter Exit: TP1 50% verkaufen, SL auf Breakeven
7. Korrelierte Positionen = ein Risikoblock
8. Late-Entry: Underlying > 15% in **rollierenden 30 Tagen** gelaufen → stärkeres Setup nötig. **Nicht YTD** verwenden (zeitvariant: Jan ~2 Wochen, Dez ~12 Monate). Details zur Pre-Signal-Check-Reihenfolge: `references/news-scan.md`
9. „When in doubt, stay out" — Checkliste ≥ 5/7
10. Counter-These-Checkliste vor jedem Short
11. TP/SL-Begründungspflicht: Methode + charttechn. Bezug + R:R + Falsifizierung + Zeitstopp
12. Position Sizing = Hybrid-Skala (5/7=1%, 6/7=2%, 7/7=3%) — Default, nicht Ausnahme
13. **TP von Chart → R:R — nie rückwärts:** Erst Widerstand finden, dann R:R rechnen. ATR-Plausibilitätscheck: > 5–6 ATRs in 2–3 Wochen = unrealistisch. Nach TP1-Treffer: SL = MAX(Breakeven, TP1 − 1,5×ATR).
14. **🆕 Frequenz-Disziplin (07.05.2026):** Counter-These-Quick-Check ist Step 1, nicht Step 4. Watchlist-Einträge haben Verfallsdatum (max. 14 HT, Event-Ausnahme). Pre-Trigger-Orders mit 1%-Sizing sind erlaubt, wenn Bestätigungs-Wartezeit > 3 HT. 5/7-Class ist Frequenz-Klasse, nicht Reject-Klasse.
15. **🆕 Phasen-Audit für Sektor-Setups (15.05.2026, Note #62):** Setups, die für ein bestimmtes Marktregime kalibriert wurden (Spike-Regime: kurzer harter Schock; Slow-Burn-Regime: kontinuierlicher Trend ohne Spike-Days), verlieren bei Regime-Wechsel ihre Geometrie. Alle ~30 Tage Regime-Check pro Sektor-Setup: hat die Welt sich an die Story adaptiert? Wenn ja → Setup als "eingepreist/archived" markieren, Re-Activation nur bei Spike-Event (neuer Schock-Trigger). Volldetail: § Sektor-Setup-Phasen-Audit.
16. **🆕 Ex-Tag-Pre-Filter rückwärts vor Breakdown-Short (17.05.2026, Note #67):** Ein isolierter -3% bis -10%-Tagesverlust in der HV-Saison (April–Juli für DAX/MDAX/SDAX, Q1+Q4 für US) **muss vor jeder Breakdown-Short-Logik** gegen Ex-Dividende-Effekt geprüft werden. Pflicht-Check: TradingView-"D"-Marker auf dem Tag, oder Investor-Relations-Kalender / finanzen.net Dividenden-Datum. Wenn Ex-Tag bestätigt: **kein Setup**, weil der Drop kein realer Verkaufsdruck ist, sondern Buchhaltungs-Effekt. Re-Eval-Bedingung dokumentieren: echter Daily-Close unter dem **ex-adjustierten** 20d-Tief (Vortags-Tief minus Dividende) mit Vol >Avg-20d. Signal-Indikatoren für Ex-Tag-False-Positive: (a) -X%-Tag in HV-Saison, (b) hohes Vol bei sonst normalen Wochen, (c) kein Adhoc-/News-Auslöser zum Tag findbar, (d) RSI-Drop synchron zum Kurs-Drop ohne fundamentalen Trigger. Volldetail: § Pre-Filter Ex-Tag.

17. **🆕 Breakout-SL ist entry-relativ, nie Fix-Level (22.05.2026, Note #88/#89):** Bei Breakout-/Breakdown-Setups (`[breakout]`-Zone) ist der Entry-Preis = wo der Schluss landet, nicht vorab bekannt. Der SL gehört relativ zum tatsächlichen Entry definiert (LONG: Entry − 1,5×ATR; SHORT: Entry + 1,5×ATR) — nie als fixes Kurslevel. Ein fixer SL erzeugt einen künstlichen R:R-1,35-Kipppunkt und damit eine zu schmale `[breakout]`-Zone (<1×ATR), die ein normaler Breakout-Tag in einer Kerze überspringt → Fehl-DURCHGELAUFEN auf einem noch gültigen Setup. Die Zonen-Grenze in Trend-Richtung gehört als **ATR-Chase-Cap** (Trigger ± ~1×ATR) gesetzt, nicht als R:R-Kipp. Gegenprobe-Pflicht: R:R IMMER gegen einen Lektion-4-konformen SL (≥1,5×ATR) rechnen — eine R:R-Zahl, die nur mit einem zu engen SL über 1,35 kommt, ist eine Phantom-Zahl (Befund FDX/NET 22.05.2026). Abgrenzung `[pullback]` — korrigiert 22.05.2026 (Lektion-4-Audit, Note #92): Auch `[pullback]`-Zonen brauchen einen entry-relativen SL, sobald die Zone breiter als ~0,5×ATR ist. Ein über die ganze Zone fixer SL erfüllt Lektion 4 nur an einem Punkt; an der für die Richtung ungünstigen Zonenkante (LONG: Untergrenze, SHORT: Obergrenze) wird er zu eng. Fixer SL ist NUR bei sehr schmaler Pullback-Zone (≤~0,5×ATR, quasi Punkt) korrekt. Die frühere Aussage „[pullback] nicht betroffen" war zu pauschal. Volldetail: `references/pipeline-integration.md` § Zonen-Semantik-Tags.

## Signal-Checkliste (≥ 5/7 vor Einstieg)

| # | Kriterium | Prüfung |
|---|-----------|---------|
| 1 | Klare These | Konkreter, benennbarer Katalysator? |
| 2 | Technisches Signal | Chart bestätigt (Trendbruch, S/R, Volumen)? |
| 3 | Timing | **30d-Move** < 15%? (nicht YTD — Lektion 8). Bei Daily-Chart auch 52W-Hoch-Abstand prüfen. |
| 4 | R:R ≥ 1,35 | Von Chart-Widerstand gerechnet, nicht rückwärts |
| 5 | Kein Event-Risiko | Keine Earnings/HV/Trigger in 5 Tagen? |
| 6 | Korrelation geprüft | Kein Cluster mit bestehenden Positionen? |
| 7 | Kapital verfügbar | Einsatz ≥ 400€ und Gesamtrisiko < 70% Risikokapital? |

Score explizit dokumentieren (z.B. „6/7 — nur Event-Risiko aber > 5 Tage → GO").

### Markt-Sentiment-Check (optional)

| Indikator | Quelle | Warnsignal Long | Warnsignal Short |
|-----------|--------|-----------------|------------------|
| VDAX-NEW | TradingView `DV1X` | < 15 (Euphorie) | > 35 (Panik — Contrarian-Kauf) |
| Eurex PCR (Index) | eurex.com Tagesstatistik | < 0,7 (zu viele Calls) | > 1,5 (starke Absicherung) |
| EUWAX Sentiment | boerse-stuttgart.de | Stark positiv | Stark negativ |

Wenn User Werte liefert → Extremwerte immer kommentieren. Wenn nicht → einmal fragen, dann weglassen.

## 🆕 Counter-These-Quick-Check (Step 1 — VOR 7/7-Checkliste, seit 07.05.2026)

**Workflow-Reihenfolge umgekehrt:** Counter-These war früher der letzte Filter vor Order. Wenn sie raus-filterte, war die ganze Plan-Arbeit Sunk Cost (CRM-Lehre Note #38). Ab jetzt **immer als Step 1** nach Pipeline-Hit / News-Scan-Hit / Hidden-Scan-Hit:

| Reihenfolge | Schritt |
|-------------|---------|
| 1 | **Counter-These-Quick-Check** (max. 2 Web-Suchen) |
| 2 | Vorcheckliste 7/7 (Score) |
| 3 | Sizing-Klasse aus Score |
| 4 | Trade-Plan-Ausarbeitung (Trigger, SL, TP, R:R) |

**Quick-Check-Mindestumfang (alle Trades, Long und Short):**

1. **Aktives Aktienrückkaufprogramm?** → Bei Short tot, bei Long stützend (Buyback-Bid). Quelle: Quartalsbericht oder PR-Archiv letzten 90 Tage.
2. **Frische Analysten-Aktionen letzten 14 Tage?** → Konsens-Drift gegen die These ist hartes Counter-Signal. Quelle: aktiencheck.de, finanzen.net.
3. **Earnings/HV/Ex-Div in ≤ 5 Handelstagen?** → Event-Risiko. **🆕 Ex-Div bei Short-Setups = harter Block analog Earnings (Note #64, 15.05.2026)**: Cert-Emittent passt KO-Schwelle um Dividende an, mechanischer Bid-Druck weg, aber Day-of-Ex-Div oft Volatilitäts-Spike. Quelle: Investor-Relations-Kalender oder finanzen.net.
4. **🆕 Rückwärts-Check bei Breakdown-Short auf -3% bis -10%-Tag (Note #67, 17.05.2026):** War der Auslöser-Tag ein Ex-Dividende-Tag? Pflicht in HV-Saison April–Juli (DE/EU) und Q1/Q4 (US). Bestätigt → SKIP, der "Breakdown" ist artifiziell. Quelle: TradingView-"D"-Marker, finanzen.net Dividenden-Historie, yfinance `.actions`. Volldetail: § Pre-Filter Ex-Tag.

Wenn ≥ 1 Treffer **gegen die These** → SKIP oder Setup-Wechsel (z.B. Long statt Short, oder warten bis nach Event). Erst dann lohnt sich Schritt 2.

**Bei Hidden-Scan / Insider-Scan:** Cluster-Insider-Käufe sind selbst ein Counter-These-Signal gegen Short-Setups (Invers-Check). Bei Long-Setups: Cluster-Insider-Verkäufe als Counter-Signal prüfen.

## Counter-These-Checkliste (Vollversion vor jedem Short)

Step 1 oben deckt die Mindestpflicht ab. Bei Short-Setups zusätzlich:

1. Aktives Aktienrückkaufprogramm? → Stützt Kurs, Short-Squeeze-Risiko
2. Frische Analysten-Upgrades? → Sentiment dreht
3. Anstehende Dividende? → Ex-Dividenden-Effekt bei KO-Schwelle + harte 5-HT-Sperrfrist (Note #64)
4. Gegenläufige Effekte (Pricing Power, Hedging)?
5. Reagiert die Aktie schwächer als erwartet auf die Krise? → Markt sieht etwas, das du nicht siehst

Jeder Treffer wird als Risiko explizit benannt.

## 🆕 Counter-These-Checkliste (Vollversion vor jedem Long, Note #61, seit 15.05.2026)

Long-Setups brauchen genauso eine Counter-These-Prüfung. Die Signale sind invers zur Short-Liste:

1. **Cluster-Insider-Verkäufe letzten 30 Tage?** → Manager wissen mehr; Cluster-Sell-Signal ist invers zu Insider-Cluster-Kauf
2. **Frische Analysten-Downgrades?** → Sentiment dreht gegen den Long; bei ≥ 2 Downgrades in 14 Tagen ernst nehmen
3. **Anstehende Earnings/HV in ≤ 5 HT?** → Pre-Earnings-Sperre analog Short-Seite
4. **Gegenläufige Effekte:** aktive Sell-Ratings, Konsensus-Downside, schwaches Quartal noch nicht eingepreist
5. **Reagiert die Aktie schwächer als erwartet auf positive News?** → Markt sieht etwas, das du nicht siehst (Equivalent zur Short-Seite-Regel)
6. **Sektor-Stress mit binärem Catalyst?** → Long gegen den Sektor-Wind nur mit Edge auf 7/7 + Insider-Bonus

Jeder Treffer wird als Risiko explizit benannt — analog zur Short-Vollversion.

## 🆕 V2-Counter-These-Score-Modell (Arbeitshypothese, Note #65, seit 15.05.2026)

**Status:** Arbeitshypothese, nach 5-10 realen Trades retrospektiv prüfen. Modell aggregiert Counter-Signale gewichtet auf einen Score, der primär auf das Sizing wirkt, nicht binär Skip/Go entscheidet.

**Hintergrund:** Erste Version hatte einzelne Signale zu hart gewichtet (Buyback alleine konnte Skip auslösen, was bei Apple Q4 2022 / Meta 2022 / VW 2008-2009 / Boeing 2019-2020 als Gegenbeispiele falsch gewesen wäre). V2 weicher kalibriert, Sizing-Halbierung statt Skip bei moderater Counter-These.

### Score-Tabelle (Signale für Short-Setup)

**Counter-Signale (negativ, je stärker desto bearisher für Short-These):**

| Signal | Punkte |
|--------|--------|
| Buyback >15% Tagesvol, Restlaufzeit >90 HT | -2 |
| Buyback >15% Tagesvol, Restlaufzeit ≤30 HT | -1 |
| Buyback 5-15% Tagesvol | -1 |
| Buyback <5% Tagesvol | 0 |
| Q1/letztes Earnings deutlicher Beat | -1 |
| Konsens-Upside >25% | -2 |
| Konsens-Upside 10-25% | -1 |
| Konsens-Upside <10% | 0 |
| Keine Sell-Ratings, Buy-Mehrheit | -1 |
| Frische Upgrades ≥2 in letzten 14 HT | -2 |
| Bullische RSI-Divergenz am Setup-Punkt | -1 |
| Binärer Sektor-Catalyst potenziell positiv <90d | -1 |

**Pro-Short-Signale (positiv, je höher desto bullisher für Short-These):**

| Signal | Punkte |
|--------|--------|
| Q1-Miss + Outlook-Senkung | +2 |
| Insider-Sell-Cluster (Note #48-konform) | +3 |
| Frische Downgrades ≥2 in 14 HT | +2 |
| Aktive Sell-Ratings vorhanden | +1 |
| 30d-Move <-10% (frische Schwäche, kein Late-Entry-Filter-Bruch) | +1 |
| Bruch 52W-Tief mit Vol >1,5× | +2 |
| EBIT-Rückgang YoY >15% trotz Marge-Beat | +1 |

### Sizing-Regel V2

| Score | Sizing | Status |
|-------|--------|--------|
| ≥ +3 | 1,5× (≙ 7/7-Klasse) | Klarer Edge |
| 0 bis +2 | 1× (≙ Score-Klasse) | Standard |
| -1 bis -3 | 1× | Counter-These bekannt, nicht blockierend |
| -4 bis -5 | 0,5× | Deutliche Gegenkräfte, halbieren |
| -6 bis -7 | 0,25× oder Watch | Sehr starke Gegenkräfte |
| ≤ -8 | Skip / Watch-only | Strukturell verloren |

### Buyback-Berechnung (für % Tagesvolumen)

```
Wochen-Buyback aus Ad-hoc-Meldung / 5 HT = Avg-Buyback/Tag
Buyback-Anteil % = Avg-Buyback/Tag / Avg-Tagesvolumen-20d × 100
```

**Caveats:** Vereinfachung. (1) Programme kaufen oft mehr an Schwäche-Tagen — Anteil dort höher. (2) Avg-Vol-20d enthält Buyback bereits → konservative Variante. (3) Restlaufzeit nicht in Berechnung, deshalb als zweiter Faktor in Punkte-Tabelle.

### Retrospektive Anwendungsbeispiele (15.05.2026)

- **MBG.DE Short:** Buyback ~26% Tagesvol langfristig, Q1-Pkw-Marge-Beat, Konsens +22,6%, keine Sell-Ratings, Tarif-Catalyst, RSI-Divergenz → Score ~-6 → Watch-only ✓
- **VOW3.DE Short:** Kein Buyback, Q1-Miss + "reshape", Konsens +29%, keine Sell-Ratings, RSI-Div, Vol-Anstieg auf Bounce, Audi/Porsche-Druck → Score ~-3 → 1× Standard
- **KRN.DE Short:** Kein Buyback, Q1-Marge-Beat aber Markt-Reaktion skeptisch, Konsens +24-32%, frische Upgrades Jefferies+DB, Q1-Umsatz-FX-bedingt rückläufig → Score ~-4 → 0,5×

### Long-Variante (spiegelbildlich, Note #61-konform)

Für Long-Setups Vorzeichen umkehren: aktives Buyback wird +1/+2 (statt -1/-2 wie für Short), Cluster-Insider-Käufe +3, Q1-Beat +1, Analystenkonsens-Upside +2, etc. Konkrete Anwendung beim ersten Long-Setup, das die V2-Methodik vollständig durchlaufen soll — bis dahin Arbeitshypothese ohne Pflicht-Anwendung.

## 🆕 Sektor-Setup-Phasen-Audit (Spike vs. Slow-Burn, Note #62, seit 15.05.2026)

Setups, die für ein bestimmtes Marktregime kalibriert wurden, müssen periodisch re-evaluiert werden, ob das Regime noch passt. Andernfalls werden tote Setups gepflegt und blockieren Watchlist-Slots.

### Regime-Klassifikation

| Regime | Charakteristik | Beispiel |
|--------|----------------|----------|
| **Spike-Regime** | Kurzer harter Schock, Vol-Anstieg, gerichtete Bewegung in 1-5 HT, klare Pullback-Geometrie | Iran-Hormus-Eskalation Januar 2026 (initial), Tarif-Drohung Trump 04.05.2026 |
| **Slow-Burn-Regime** | Kontinuierlicher Trend ohne Vol-Spike, Markt adaptiert sich an Story, Aktien-Effekte abgeflacht | Iran-Hormus seit ~Februar 2026 (5-Monate-Slow-Burn, Brent 108$ statt prognostizierte 150$) |

### Audit-Frequenz und Trigger

**Alle ~30 Tage pro Sektor-Setup-Cluster:** Regime-Re-Check mit drei Fragen:

1. **Hat sich der Markt an die Story adaptiert?** → Wenn ja, Spike-Trigger-Schwellen sind tot
2. **Ist die ursprüngliche Pullback-Geometrie noch verfügbar?** → Wenn Aktien-Setups durch Slow-Burn-Adaption nahe High laufen (Lektion-8-Filter aktiv), ist Pullback nicht mehr handelbar
3. **Welche Bedingung würde Spike-Regime reaktivieren?** → Konkretes Trigger-Event benennen

### Konsequenz bei Regime-Wechsel zu Slow-Burn

- Setup-Klasse als "eingepreist/archived" markieren (siehe § Watchlist-Archived-Status)
- Re-Activation nur bei explizitem Spike-Event (z.B. "Brent +5$ in <3 HT" oder neuer Schock-Trigger)
- Alternative Profiteure suchen, die noch nicht abgegrast sind

### Beispiel-Anwendung (15.05.2026)

Iran-Setups (TTE.PA, SHEL.L, EQNR.OL): nach 5 Monaten Slow-Burn → archived. Trigger-Schwelle "Brent ≥113$" war für Spike-Regime kalibriert, läuft im Slow-Burn nie. Aktien sind nahe 52W-High, Pullback-Geometrie zerstört, Lektion 8 (Late-Entry-Filter) blockt sowieso. Re-Eval-Bedingung im "archived"-Status festgeschrieben.

## 🆕 Pre-Filter Ex-Tag rückwärts vor Breakdown-Short (Note #67, seit 17.05.2026)

**Anlass (HEI.DE-Lehre 17.05.2026):** Am 15.05.2026 wurde Heidelberg Materials mit -7,16% bei Vol 1,89× Avg-20d aus der Gamechanger-Pipeline als Breakdown-Short-Kandidat geliefert (RSI 1D 32 oversold, 20d-Tief 168,80€ touched, bearish EMA-Stack). Beim Setup-Aufbau wurde der Tag als realer Verkaufsdruck interpretiert. Tatsächlich war der 15.05. der **Ex-Dividende-Tag** nach HV — der dominante Anteil des -7,16% war buchhalterischer Effekt, kein Breakdown. Das Setup war tot, der Watchlist-Eintrag wurde noch am Tag des Aufbaus auf 📦 STRUKTURELL-ARCHIVED gesetzt.

### Wann der Rückwärts-Check Pflicht ist

Jedes Breakdown-Short-Setup auf einen **isolierten -3% bis -10%-Tagesverlust** unterliegt dem Pflicht-Check:

| Bedingung | Aktion |
|-----------|--------|
| Tagesverlust ≥ 3% und Symbol ist DE/EU-Aktie | Pflicht-Check in HV-Saison **April–Juli** |
| Tagesverlust ≥ 3% und Symbol ist US-Aktie | Pflicht-Check in **Q1 (Jan–Mär)** und **Q4 (Okt–Dez)** |
| Tagesverlust ≥ 5% jederzeit | Pflicht-Check unabhängig vom Monat |
| Symbol-Index-Mitgliedschaft DAX/MDAX/SDAX/STOXX 600 | Verschärfter Check, weil Index-Rebalancing am Ex-Tag zusätzliche Vol-Spikes erzeugt |

### Indikatoren für Ex-Tag-False-Positive

Die folgende Kombination ist ein starkes Signal, dass der Drop ex-Tag-bedingt ist:

1. **Tag liegt in HV-Saison** (siehe Tabelle oben)
2. **Hohes Vol-Multiple** (1,5× bis 3× Avg) bei sonst ruhigen Vorwochen — typisch für Ex-Tag-Arbitrage und Index-Rebalancing-Flows
3. **Kein Adhoc-/News-Auslöser** zum Tag findbar (dgap-news.de, eqs-news.com, Reuters-Feed)
4. **RSI-Drop synchron zum Kurs-Drop** ohne fundamentalen Trigger — bei realem Breakdown geht meist ein Sektor-Druck voraus oder eine News-Eskalation
5. **20d-Tief wird "auf der Nase" touched**, ohne dass Kurs vor dem Tag schon schwächelte — bei realem Breakdown ist meist eine 1-2-tägige Vorlauf-Schwäche zu sehen

### Quellen-Check (in dieser Reihenfolge)

1. **TradingView**: "D"-Marker direkt am Bar — schnellster Check, eine Sekunde
2. **finanzen.net Dividenden-Historie** oder **finanzen.net Aktien-Profil** → Section "Dividenden"
3. **Investor-Relations-Seite der Aktiengesellschaft** → "Hauptversammlung" / "Dividende"
4. **yfinance `.actions` oder `.dividends`** Property bei Pipeline-Integration (siehe Pipeline-Roadmap V1.2)

### Konsequenz und Re-Eval-Bedingung

Bei bestätigtem Ex-Tag: **SKIP**, Setup wird nicht eingetragen oder als 📦 STRUKTURELL-ARCHIVED dokumentiert (Audit-Trail). Re-Eval-Bedingung dokumentieren:

> Echter Daily-Close unter dem **ex-adjustierten 20d-Tief** (Formel: vortägliches 20d-Tief minus Bardividende) mit Vol >Avg-20d und **ohne weiteren Ex-Tag-Beitrag**.

Beispiel HEI.DE (geschätzte Dividende 4€): ex-adj. 20d-Tief = 168,80 − 4,00 = ca. 164,80€. Re-Eval-Trigger wäre Daily-Close <162€ (konservativ) mit Vol-Bestätigung.

### Beispiel-Anwendung (17.05.2026)

HEI.DE: -7,16% am 15.05. mit Vol 1,89×, RSI-Drop 35→32, 20d-Tief 168,80€ auf der Nase touched, kein Adhoc-Auslöser im DGAP-Feed → 4 von 5 Indikatoren passen. Ex-Tag bestätigt durch User-Hinweis. SKIP, Status auf 📦 STRUKTURELL-ARCHIVED mit Korrektur-Note im Trigger-Feld.

## 🆕 Sell-the-News-Continuation-Short (Setup-Klasse v0.1, Note #66, seit 16.05.2026)

**Anlass (Sanofi-Lehre 15.05.2026):** Am 23.04.2026 hatten wir Sanofi nach Q1-Beat (+13,6% Sales, +14% EPS) mit Rejection-Kerze an EMA200 als Long-Watch eingetragen (Pullback ODER Ausbruch). Aktie ist NICHT zurück gepullback'd, sondern ohne Bounce -11% gefallen (81,55€ → 72€) bis Invalidator <78,50€ griff. Wir dachten in zwei Optionen: Long-Pullback vs. Long-Ausbruch. Die dritte Option — Short als eigenständige Setup-Klasse auf die Sell-the-News-Continuation — stand nicht auf dem Radar.

**Abgrenzung zu "Short gegen Q1-Beat":** Das ist NICHT dasselbe. Short-gegen-Beat (fundamentaler Short) verliert strukturell gegen positive Fundamentals. Sell-the-News-Continuation-Short ist sentiment-/positioning-getrieben: Beat war eingepreist (Pre-Earnings-Run), Markt verkauft die News, technische Continuation der Rejection-Kerze.

### Setup-Charakteristik

Erkennungsmerkmale am Earnings-Tag oder Folgetag:
- **Earnings-Beat (positiv)** — kein Miss, ansonsten ist es Standard-Continuation
- **Intraday-Rejection an oberem Widerstand** (EMA200, 52W-High, Range-Top): Intraday-Hoch ≥2,5% über Schluss
- **Aktie war pre-Earnings im Aufwärts-Lauf** (≥+5% in 10 HT vor Earnings = Beat-Erwartung eingepreist)
- **Schluss am unteren Tagesdrittel** (Rejection bestätigt)
- **Vol am Rejection-Tag ≥1,2× Avg-20d** (institutionelle Verteilung)

### Filter 7/7 für Entry

| # | Bedingung |
|---|-----------|
| 1 | Rejection-Kerze sauber (alle 4 Merkmale oben) |
| 2 | Counter-These positiv-fundamental aber bekannt (Buyback OK, Konsens-Upside akzeptabel) — sonst klassischer Short-Versuch gegen Beat |
| 3 | Daily-Close in den nächsten 1-5 HT <Rejection-Tags-Schluss + Vol >Avg-20d (Continuation-Bestätigung) |
| 4 | EMA20 1D als nächster Magnet-Bereich UNTER aktuellem Niveau (verfügbarer TP1-Raum) |
| 5 | RSI 1D <60 zum Entry-Zeitpunkt (kein Oversold-Entry, kein Chase) |
| 6 | Kein Ex-Div/HV in ≤ 5 HT (Note #64 — Ex-Div macht Short mechanisch ungünstig) |
| 7 | R:R ≥ 1,5 brutto, FX-adj. ≥ 1,4 (Lektion 1 v2) |

### Trigger-Logik

**Trigger A (bevorzugt):** Daily-Close <Rejection-Tags-Schluss-1% + Vol >Avg-20d + RSI 1D Cross unter 50

**Trigger B (aggressiver):** 4h-Bearish-Engulfing in Zone Rejection-Tags-Schluss-Bereich + RSI 4h Cross unter 45

### Exit

- **SL:** über Rejection-Tags-Hoch + 0,5×ATR
- **TP1:** EMA20 1D (50% Teil-Exit + SL→BE, Lektion 6)
- **TP2:** EMA50 1D oder 52W-Range-Mitte
- **Halte:** 5-15 HT (Sell-the-News-Drift kürzer als PEAD-Drift weil sentiment-getrieben)
- **Time-Stop:** Hard 1 HT vor nächstem Earnings (zwingend), Soft 15 HT

### Sizing

1% Risikokapital (150€ Max-Verlust) für erste 5 Trades als Pilot. Nach Re-Eval Hit-Ratio + R-Multiple Übergang auf Standard-Score-Sizing.

### V2-Counter-These-Score-Anwendung (Note #65)

Sell-the-News-Continuation-Short ist Short-Setup → V2-Score-Tabelle Short anwenden. **Wichtig:** Q1-Beat als Counter-Signal zählt (-1 Punkt), aber wenn Sell-the-News-Pattern klar erkennbar (Aktie -5% am Earnings-Tag trotz Beat), kann das als Pro-Short +1 gewertet werden (klassisches "Markt sieht was, was wir nicht sehen"-Signal aus Counter-These-Vollversion Punkt 5).

### Negativ-Beispiel (Validierungs-Anker)

**Sanofi 23.04.2026:** Hätte funktioniert. Rejection-Kerze 84,16€ → 81,55€ Schluss (3,8% vom Hoch), Vol-Spike, EMA200-Test gescheitert, Q1 war Beat aber Pre-Earnings-Run ~+5% war eingepreist. Trigger A ~30.04. (Daily-Close <81€) + Continuation bis 72€ ≈ -11% Bewegung. Nicht erkannt damals, weil Setup-Klasse fehlte.

### Nächste Schritte

- Manueller Watch auf 2-3 weitere Earnings-Tags-Rejection-Setups in den nächsten 4-6 Wochen
- Nach 3 Beispielen: Skill-Status von v0.1-Pilot auf vollwertige Setup-Klasse heben
- Pipeline-Integration prüfen: GAMECHANGER-HUNT-Layer für "Earnings-Day-Rejection" als Filter

## 🆕 PEAD-Short (Setup-Klasse v0.1, seit 2026-05-22)

**Anlass (INTU-Lehre 22.05.2026):** INTU (Intuit) meldete am 20.05.2026 einen Headline-Beat (adj. EPS 12,80$ vs. 12,28$, Guidance angehoben) — und fiel trotzdem mit einem **-18,7%-Gap** ab, weil der Markt 17%-Stellenabbau plus KI-Disruptionsangst (gen-AI bedroht das DIY-Steuer-/Buchhaltungsgeschäft) als das eigentliche, qualitativ negative Signal las. Bei der Aufarbeitung fehlte der Klassen-Begriff: PEAD ist im Skill bisher nur als Long-Variante (Note #47, „PEAD-Filter v0.1") und über das Pipeline-Flag `📅 PEAD-WINDOW` präsent. Das Short-Pendant — Underreaction auf eine **negative** Earnings-Überraschung, abwärts gedriftet — war nie als eigene Klasse formalisiert. INTU ist für PEAD-Short das, was Sanofi für die Sell-the-News-Klasse war: der Anlassfall.

PEAD-Short ist das **Spiegelbild von PEAD-Long (Note #47)**: dieselbe Mechanik, invertierte Richtung. Die Mutter-Spec für Schwellen-Begründung bleibt Note #47; dieser Abschnitt dokumentiert nur die Short-spezifischen Abweichungen und die Trigger-/Exit-Mechanik nach aktueller Zonen-Konvention.

**Abgrenzung — drei Verwechslungsgefahren:**
- **Kein „Short gegen einen Beat" (fundamentaler Short).** Short-gegen-Beat verliert strukturell gegen positive Fundamentals. PEAD-Short braucht eine **negative** Überraschung als Treibstoff — entweder quantitativ (EPS-/Revenue-Miss) oder qualitativ (Guidance-/Outlook-Cut, der einen Headline-Beat überlagert — der INTU-Fall).
- **Nicht Sell-the-News-Continuation-Short.** Sell-the-News (§ oben) ist ein *sauberer Beat* + intraday Rejection-Kerze + eingepreister Pre-Earnings-Run — sentiment-/positioning-getrieben, Drift kurz (5–15 HT). PEAD-Short ist ein *negatives Surprise-Repricing*, das der Markt über mehrere Tage verdaut — informations-/revisions-getrieben, Drift länger. Faustregel zur Trennung: Beat + Rejection → Sell-the-News; Miss (oder Outlook-Cut) + Folge-Drift → PEAD-Short.
- **Nicht Standard-Reversal-Short.** Reversal-Short braucht einen vorherigen Aufwärtstrend, der kippt. PEAD-Short braucht keinen Trendkontext — nur das frische Earnings-Event und die Underreaction.

### Setup-Charakteristik

Erkennungsmerkmale am Earnings-Tag oder Folgetag:
- **Negative Earnings-Überraschung** — quantitativer Miss oder qualitativer Outlook-/Guidance-Cut (s. Surprise-Gate).
- **Maßvolle, nicht überschießende Reaktion** am Earnings-Tag — der Markt hat *unter*reagiert, der Drift-Raum ist noch offen (s. 7/7-Punkt 2).
- Aktie ist **nicht** bereits ausverkauft/oversold — sonst tradest du in eine Bounce-Falle (s. 7/7-Punkt 5).

### Surprise-Gate (Vorbedingung — analog Maschinen-Gate)

Harte Vorbedingung, bevor das Setup überhaupt gebaut wird. Erfüllt eine Meldung das Gate nicht, ist es **kein** PEAD-Short, egal wie verlockend der Chart aussieht:

> **Es liegt eine qualifizierte negative Überraschung mit ≥ 4–5% Magnitude vor.**

Drei Ausprägungen, absteigend nach Drift-Güte:
- **Doppel-Miss (sauberste Klasse):** EPS ≥10% *unter* Konsens **UND** Revenue ≥2% *unter* Konsens — exaktes Spiegelbild des PEAD-Long-Hard-Filters.
- **Revenue-Miss-only:** handelbar, aber reduziert — empirisch driftet ein Revenue-Miss besser als ein EPS-Miss, ein Single-Side-Miss schwächer als ein Doppel-Miss. Sizing-Abschlag (s.u.).
- **EPS-Miss-only / qualitativer Cut:** nur handelbar **mit** einem zweiten bestätigenden Negativ — Guidance-/Outlook-Senkung, struktureller Schock (INTU: KI-Disruption + Stellenabbau). Reiner EPS-Miss ohne Begleitsignal ist zu oft ein Einmal-Repricing ohne Drift → kein Trade.

Konsens-/Surprise-Daten sind **kein Pipeline-Scope** (Note #47) — Beat/Miss/Surprise-% werden im Morning-Check manuell aus Reuters / Marketwatch / Investing.com gezogen. Das Pipeline-Flag `📅 PEAD-WINDOW` ist richtungsneutral; ob Long- oder Short-Drift, entscheidet das Vorzeichen der Überraschung.

### Liquiditäts-Filter

Wie PEAD-Long: Marktkap ≥ 1 Mrd€, Tagesvolumen ≥ 100k Stk im 30-Tage-Schnitt. Schließt illiquide Werte aus, die beim Exit reißen. Zusätzlich Pflicht: KO-Coverage auf SB+ samt Spread vorab prüfen (BNP-#59-Lehre).

### 7/7-Filter für Entry

| # | Bedingung |
|---|-----------|
| 1 | Surprise-Gate erfüllt — qualifizierte negative Überraschung, Konsens vs. Actual dokumentiert |
| 2 | **Underreaction-Fenster:** Reaktion am Earnings-Tag (bzw. Folgetag bei AMC-Meldung) im Bereich **−1% bis −6%**. > −1% oder positiv trotz Miss → Markt zweifelt am Negativ, kein Drift → SKIP. < −6% → schon eingepreist, Late-Short-Risiko → SKIP, bis ein Bounce den Entry wiederherstellt (Lektion 8). |
| 3 | Counter-These-Block Short sauber (s.u.) — max. 1–2 weiche Flags; 3 harte Flags → SKIP |
| 4 | Nächstes Chart-Support-Level (EMA-Magnet, altes Tief, Gap-Unterkante, Volumenzone) **unter** dem Kurs vorhanden → verfügbarer TP1-Raum |
| 5 | RSI 1D **> 40** zum Entry-Zeitpunkt — kein Oversold-Short, kein Bounce-Trap-Chase (Spiegel von PEAD-Long „RSI < 60") |
| 6 | Kein Ex-Div/HV in ≤ 5 HT (Note #64 — Ex-Div macht Short mechanisch ungünstig) |
| 7 | R:R ≥ 1,5 brutto, FX-adj. ≥ 1,4 (Lektion 1 v2) — vom Chart-Support gerechnet, nie rückwärts (Lektion 13) |

**Counter-These-Block Short (zu Punkt 3) — die Asymmetrie beachten:** Käufe und Verkäufe wirken nicht symmetrisch. Harte rote Flags *gegen* den Short: Analysten-**Upgrades** trotz Miss (wenn die Sell-Side den Miss nicht abstraft, sieht sie etwas Stützendes), Insider-**Cluster-Käufe** in den letzten 30 HT, frisch aufgelegtes/aufgestocktes Buyback-Programm (Squeeze-Treibstoff). Weiche Flags: Sektorstärke, naher 52W-Tief-Support. Drei harte → SKIP, ein bis zwei → reduziertes Sizing.

### Trigger-Logik — zwei Trigger, beide als Zone

Nach Zonen-Konvention (Task 5, 2026-05-22): Punkt-Trigger verschweigen die R:R-Erosion, deshalb beide Trigger als **Zone mit Ober- und Untergrenze**.

**Trigger A — Bounce-Pullback (Zone, bevorzugt):**
- Die Aktie erholt sich 1–3% vom Earnings-Tags-Schluss nach oben in eine Widerstandszone, bildet dort eine **bärische Reversal-Kerze** (Bearish-Engulfing / Shooting-Star / 4h-Reverse-Close abwärts) → Short an der Bestätigungskerze.
- **Zone** = Earnings-Tags-Schluss bis Earnings-Tags-Schluss + 3% (das Bounce-Fenster).
- `[pullback]`-Tag — ein Kurs außerhalb der Zone ist legitimes Warten, kein Durchgelaufen-Flag.
- Bevorzugt, weil der Short aus einer Stärke heraus eröffnet wird → besseres R:R, kein Einstieg am Tagestief.

**Trigger B — Continuation-Breakdown (Zone, aggressiver):**
- Daily-Close **unter** dem Earnings-Tags-Tief + Vol ≥ 30D-Ø (institutionelle Fortsetzung).
- **Zone** = Earnings-Tags-Tief − 0,3×ATR(14)-Puffer (Obergrenze = Trigger, gegen Rauschen) bis Trigger − ~1×ATR(14) (Untergrenze = ATR-Chase-Cap). SL **entry-relativ** (Entry + 1,5×ATR), KEIN Fix-SL — Lektion 17.
- `[breakout]`-Tag — der Parser liest für SHORT: Daily-Close unter der Untergrenze → **durchgelaufen**, R:R gerissen, `proximity=far`. Kein Chase.
- Schwächeres Setup als A (schon weiter gelaufen) — nur nehmen, wenn A nicht kommt und R:R noch passt.

Beide Trigger können parallel im selben Watchlist-Eintrag stehen (A)/B)-Label-Konvention, Parser-Pflichtcheck beachten). Entry-Fenster insgesamt: **1–5 HT nach dem Earnings-Tag** — danach ist die Zone zu weit gelaufen.

**SB+-Einschränkung (Pflicht-Hinweis):** Der SB+-KO-Direkthandel kennt nur **Limit-Buy, keinen Stop-Buy**. Für einen KO-**Short** gilt invers zur Long-Logik:
- **Trigger A (Bounce-Pullback):** der Basiswert steigt → das KO-Short-Zertifikat *fällt* → Limit-Buy auf das Zertifikat greift sauber, während es billiger wird. **SB+-KO-fähig.**
- **Trigger B (Continuation-Breakdown):** der Basiswert fällt unter das Tief → das KO-Short-Zertifikat *steigt* → bräuchte einen Stop-Buy → **auf SB+-KO nicht umsetzbar.** Direktaktien-Leerverkauf scheidet aus → nur als bewusste **Live-Order** auf den Daily-Close. Trigger B daher praktisch nur live handelbar.

### Exit

- **SL:** *über* dem Entry — bei Trigger A über dem Bounce-Hoch + 0,5×ATR, bei Trigger B über dem Earnings-Tags-Tief (Reclaim-Level) + 0,5×ATR. Floor: ≥ 1,5×ATR(14) Abstand (Lektion 4) — ist der strukturelle SL enger, auf 1,5×ATR aufweiten.
- **TP1:** nächstes Chart-Support-Level (EMA-Magnet, altes Tief, Gap-Unterkante, Volumenzone) → 50% Teil-Exit, danach SL → Breakeven (Lektion 6).
- **Nach TP1:** SL = MIN(Breakeven, TP1 + 1,5×ATR) — Spiegel der Long-Regel MAX(BE, TP1 − 1,5×ATR), Lektion 13.
- **TP2:** übergeordnetes Support-Level / Measured-Move-Extension nach unten. Kein Chart-Level vorhanden → kein TP2 (Lektion 13), Restposition über Drift-Fenster laufen lassen.
- **Halte / Time-Stop:** Drift-Fenster nach Surprise-Güte — Doppel-Miss 10–20 HT, Revenue-Miss-only / qualitativer Cut eher 5–10 HT (Drift-Halbwertszeit kürzer). Open-End-KO → Finanzierungskosten (Lektion 3), harter Zeitstopp nach 2–3 Wochen. **Hart 1 HT vor dem nächsten Earnings** (zwingend — sonst binäres Risiko gegen die Position).
- **FX:** PEAD-Kandidaten sind oft US-Tech (USD) → non-Quanto KO, FX-Drag einplanen, R:R FX-adj. ≥ 1,4 (Lektion 1 v2, FX-Drag-Schätzung nach Halte-Dauer).

### Sizing

1% Risikokapital (150€ Max-Verlust) für die ersten 5 Trades als Pilot — wie PEAD-Long und Sell-the-News. Kein Score-Sizing im Pilot-Stadium. Ein Modifikator: bei **Revenue-Miss-only** oder **qualitativem Cut** (statt sauberem Doppel-Miss) Sizing-Abschlag auf 0,5–0,75% — die schwächere Drift-Güte wird über die kleinere Position abgefangen. Nach Re-Eval (Hit-Ratio + R-Multiple über die ersten 5 Trades) Übergang auf Standard-Score-Sizing.

### V2-Counter-These-Score (Note #65)

PEAD-Short ist Short-Setup → V2-Score-Tabelle Short anwenden. Die negative Überraschung selbst ist Pro-Short. **Wichtig:** Analysten-**Downgrades** nach dem Miss bestätigen die Short-These (Pro-Short, +1) — die Sell-Side reiht sich ein. Umgekehrt zählen Analysten-Upgrades trotz Miss, Insider-Cluster-Käufe und ein frisches Buyback als harte Counter-Signale (−1 je). Edge-Hierarchie (Note #59): PEAD-Short rangiert auf der **PEAD-Tier** — bei Doppel-Hit gegen Reversal/Trend-Pullback/Breakout gewinnt PEAD-Short, gegen Insider verliert es.

### Pipeline- und Parser-Hinweise

- **`📅 PEAD-WINDOW`-Flag** existiert bereits richtungsneutral (Pipeline, ≤ 5 HT nach Earnings) — PEAD-Short braucht **kein** neues Flag, nur den manuellen Surprise-/Vorzeichen-Check im Morning-Check.
- **Trigger A** (Bounce-Pullback-Zone) ist als `in_range` mit `[pullback]`-Tag vom `state_parser` sauber lesbar.
- **Trigger B** (Breakdown-Zone) mit `[breakout]`-Tag formulieren — der Tag deckt die Short-Richtung ab (Kurs unter Untergrenze → durchgelaufen). Ohne Tag bliebe die Zone fälschlich „BEREIT".
- **Bärische Reversal-Kerze** (Trigger A): der Parser kennt nur `require_hammer` (bullisch) — der Bearish-Engulfing-/Shooting-Star-Check ist **Handarbeit am Chart**, manueller Pflichtpunkt vor dem Entry.
- **Surprise-Gate** ist nicht pipeline-rechenbar (Konsens-Daten kein Scope) — bleibt manuell.

### Watchlist-Trigger — parser-konformes Beispiel

Werte illustrativ (Earnings-Tags-Schluss 100,00€, Earnings-Tags-Tief 96,00€, ATR-14 2,50€, Support-EMA50 88,00€) — SL/R:R pro Fill final rechnen:

```
A) Touch 100,00–103,00$ [pullback] + 4h-Bearish-Engulfing/Reverse-Close + RSI 1D >40. B) Daily-Close 92,75–95,25$ [breakout] + Vol >Avg-20d. SL A >104€ / SL B >97,75€. TP1 88€. R:R A 1,5–4,0.
```

A-Zone = Earnings-Tags-Schluss bis +3% (100,00–103,00€); B-Zone-Obergrenze (= Trigger) = 96,00 − 0,3×2,50 ≈ 95,25€, Untergrenze = Trigger − ~1×ATR ≈ 92,75€ (ATR-Chase-Cap); SL B entry-relativ (Entry + 1,5×ATR), kein Fix-SL — Lektion 17. Parser-Pflichtcheck (7 Punkte, SKILL.md § Watchlist-Eintrag) vor dem Anlegen durchgehen. Trigger B wegen SB+-Stop-Buy-Lücke als Live-Order-Hinweis im Status-Feld vermerken.

### Validierungs-Anker (INTU 20.05.2026)

INTU ist der Anlassfall **und** zugleich der Beleg, dass die Filter greifen. Headline-Beat, aber qualitativ negative Überraschung (KI-Disruption + 17%-Stellenabbau) → Surprise-Gate-Ausprägung „qualitativer Cut" erfüllt. **Aber:** die −18,7%-Gap-Reaktion lag weit jenseits des −6%-Underreaction-Fensters (7/7-Punkt 2 verletzt) und RSI 1D ~28,6 war tief im Oversold (Punkt 5 verletzt). PEAD-Short sagt damit korrekt **SKIP-jetzt** — kein Chase in den Gap hinein. Ein handelbarer Trigger-A-Entry entstünde erst, wenn ein Bounce RSI und Reaktionsfenster wiederherstellt. Genau dieser Bounce ist für einen anderen Trader die Reversal-Long-Chance — beide Lesarten desselben Charts schließen sich nicht aus, sie unterscheiden sich nur in Richtung und Trigger.

### Nächste Schritte

- **Journal-Note anlegen** (nächste Journal-Session): PEAD-Short v0.1 als Notes-Eintrag analog #47/#66/#86 dokumentieren — dieser Skill-Abschnitt verweist bis dahin auf Note #47 als Mutter-Spec.
- Manueller Watch auf 2–3 PEAD-Short-Setups in den nächsten 4–6 Wochen (Earnings-Saison Q2-Berichte).
- Nach 3–5 dokumentierten Trades: Hit-Ratio + R-Multiple retrospektiv prüfen, dann Status von v0.1-Pilot auf vollwertige Setup-Klasse heben.
- Pilot-Cluster-Disziplin: max. 1 PEAD-Short-Trade pro Woche, max. 2 Pilot-Trades parallel über alle v0.1-Klassen.

## 🆕 Momentum-Continuation-Long (Setup-Klasse v0.1, Note #86, seit 2026-05-22)

**Anlass (Watchlist-Monokultur-Diagnose 2026-05-22):** Bei ~56 Watchlist-Einträgen liefen über Wochen kaum Trades — 29 von 41 aktiven Zeilen waren Pullback-Setups, die in einem Momentum-Markt nie füllen, weil der tiefe Rücksetzer schlicht nicht kommt. Long-Trends laufen hoch, wir stehen daneben. Die fehlende Klasse: ein definierter Einstieg in einen *bereits etablierten, gesunden Aufwärtstrend* — ohne auf einen tiefen Rücksetzer zu warten.

**Abgrenzung:**
- **Kein Trend-Pullback:** Trend-Pullback wartet auf einen tiefen Retrace (EMA50/EMA100/EMA200). Momentum-Continuation-Long fängt explizit den Fall, dass dieser tiefe Rücksetzer ausbleibt.
- **Kein Boden-Breakout:** Trigger A ist ein Ausbruch, aber aus einer *Konsolidierung innerhalb eines laufenden Trends* — nicht der erste Ausbruch aus einer Bodenformation.
- **Kein Late-Entry-Verbot:** Lektion 8 wird für diese Klasse von „Block" zu „Sizing-Frage" umgewidmet (s.u.) — sonst würde die Klasse sich in einem starken Trend selbst abschalten.

### Setup-Charakteristik

Erkennungsmerkmale am Tageschart:
- **Etablierter Aufwärtstrend** — EMA-Stack intakt, alle gleitenden Durchschnitte steigend
- **Höhere Hochs / höhere Tiefs** über die letzten ~6 Wochen, am Chart sichtbar
- Aktie steht **entweder** in einer Konsolidierung nahe dem Trend-Hoch (→ Trigger A) **oder** hat gerade einen *flachen* Rücksetzer zur EMA20 gemacht (→ Trigger B)

### Maschinen-Gate (Pipeline-rechenbar)

Harte Vorbedingung, bevor das Setup überhaupt gebaut wird:

> **EMA20 > EMA50 > EMA100 auf dem Tageschart, alle drei steigend.**

Das ist der Filter, den die Pipeline (GAMECHANGER-/Setup-Layer) automatisch prüfen kann. Ohne sauberen EMA-Stack kein Momentum-Continuation-Setup.

### 7/7-Filter für Entry

| # | Bedingung |
|---|-----------|
| 1 | Maschinen-Gate erfüllt: EMA20 > EMA50 > EMA100 (1D), alle drei steigend |
| 2 | **Höhere Hochs / höhere Tiefs der letzten ~6 Wochen am Chart bestätigt** — manueller Pflichtpunkt, ersetzt das generische „technisches Signal". Pipeline kann das nicht, das ist Handarbeit am Chart. |
| 3 | Trigger sauber als **Zone** definiert (A oder B); bei Trigger A sitzt die Zonen-Obergrenze auf dem ATR-Chase-Cap (Trigger + ~1×ATR), SL entry-relativ — kein Fix-SL/R:R-Kipp (Lektion 17) |
| 4 | R:R ≥ 1,35 vom Chart-Widerstand gerechnet (nächstes Alt-Hoch / Measured-Move / Gap-Oberkante) — nie rückwärts (Lektion 13) |
| 5 | Kein Event-Risiko: keine Earnings/HV/Ex-Div in ≤ 5 HT |
| 6 | Counter-These-Quick-Check Long sauber (Note #61): keine Cluster-Insider-Verkäufe letzten 30 HT, keine ≥ 2 Analysten-Downgrades in 14 HT, kein schwaches, noch unverdautes Quartal |
| 7 | Kapital: Einsatz je Tranche ≥ 400€, freies Gesamtrisiko-Budget < 70% Risikokapital |

Die generische These-Frage (Punkt 1 der Standard-7/7) entfällt — die These *ist* der intakte Trend. Der generische 30d-Move-Timing-Punkt entfällt ebenfalls und wird zur Sizing-Frage (s.u.).

### Trigger-Logik — zwei Trigger, beide als Zone

Punkt-Trigger verschweigen die R:R-Erosion („über Schwelle" sagt nichts darüber, *wie weit* über der Schwelle). Beide Trigger dieser Klasse sind deshalb **Zonen mit Ober- und Untergrenze**.

**Trigger A — Breakout (Zone):**
- Daily-Close in der Zone über dem Konsolidierungshoch
- **Zonen-Untergrenze** = Konsolidierungshoch + 0,3×ATR(14)-Puffer (gegen Pre-Market-Rauschen — ein 1-Cent-Spike über das Hoch soll nicht auslösen)
- **Zonen-Obergrenze** = das Entry-Niveau, bei dem R:R (zum nächsten Chart-TP) unter 1,35 fällt
- **Daily-Close oberhalb der Obergrenze → Setup ist durchgelaufen, tot.** Kein Chase.

**Trigger B — flacher Pullback (Zone):**
- Zone = EMA20(1D) bis EMA20 + 3%
- Einstieg per Touch in die Zone (flacher Rücksetzer an die steigende EMA20, keine Bestätigungskerze nötig — du kaufst kontrolliert in die Schwäche)
- **Harte Verfallsfrist ~8 HT:** kommt der flache Pullback nicht innerhalb von ~8 Handelstagen, ist Trigger B tot — nur Trigger A bleibt aktiv. Verfall im Status-Feld als Datum dokumentieren.

Beide Trigger können parallel im selben Watchlist-Eintrag stehen (A)/B)-Label-Konvention, Parser-Pflichtcheck beachten).

### Late-Entry → Sizing statt Verbot (Lektion 8, klassen-spezifisch angepasst)

In einem starken Trend ist „weit gelaufen" der Normalzustand — ein harter Late-Entry-Block (Lektion 8) würde diese Klasse abschalten. Deshalb für Momentum-Continuation-Long:

- **30d-Move ≤ 15%:** normale Score-Size (5/7 = 1%, 6/7 = 2%, 7/7 = 3%)
- **30d-Move > 15% und Trigger weiterhin valide:** Sizing-Cap **hart auf 1%**, unabhängig vom Score
- Lektion 8 ist damit *angepasst, nicht abgeschaltet*: Der Late-Entry kostet keinen Checklistenpunkt, aber die kleinere Position fängt das erhöhte Rücksetzer-Risiko ab.

### Gestaffelte Tranchen

Statt einer Ganz-oder-gar-nicht-Order wird die Position in zwei Tranchen aufgebaut:

- **Tranche 1:** 1%-Limit, vorab scharf als Pre-Trigger-Order in der Trigger-Zone (Limit-Buy)
- **Tranche 2:** bei Fill von Tranche 1 **und** Live-Verfügbarkeit → zweite Tranche, hochgezogen auf die Score-Size-Differenz, mit **eigener Bestätigung** (Bestätigungskerze / Live-Chart-Check)
- Beide Tranchen zusammen ergeben die saubere Score-Size (7/7: 1% + 2% = 3%; 6/7: 1% + 1% = 2%)

Wichtig — das ist **kein** verbotenes „Aufstocken einer Pre-Trigger-Position": Tranche 2 ist ein eigenständiger, frisch bestätigter Entry, keine nachträgliche Hochstufung derselben Order. Für diese Klasse ist die alte Pre-Trigger-Regel „bleibt bei 1%, kein Hochstufen" damit kontrolliert aufgelöst.

Staffelung greift erst **ab Score 6/7** — bei 5/7 ist 1% bereits die volle Größe (und zugleich der Late-Entry-Floor), dann nur eine Tranche.

### Pre-Trigger-Regel (ersetzt die Pre-Trigger-Pause, Note #57/#79)

Die alte Pre-Trigger-Pause wird aufgehoben. Auslöser der Pause waren Pre-Market-Spike-Fills in unreife Setups — nicht Limit-Orders an sich. An ihre Stelle treten **drei Leitplanken**:

1. **Order-Level mit ~0,3×ATR-Puffer**, damit Rauschen die Order nicht auslöst (bei Trigger A bereits in der Zonen-Untergrenze enthalten; bei Trigger B das Limit im Zonen-Inneren platzieren, nicht am oberen Rand).
2. **1%-Sizing-Floor** für die vorab scharfe Tranche — nie mehr als 1% per Pre-Trigger-Order.
3. **SL nach Fill mit ≥ 1,5×ATR Abstand** (Lektion 4) — kein enger SL, nur weil es eine Pre-Trigger-Order war.

**SB+-Einschränkung (Pflicht-Hinweis):** Der SB+-Direkthandel auf KO-Zertifikate kennt **nur Limit-Buy, keinen Stop-Buy**.
- **Trigger B (Pullback, Limit-Buy unter Kurs):** sauber auf SB+-KO abbildbar — das KO fällt mit dem zurückkommenden Kurs, das Limit greift.
- **Trigger A (Breakout, Stop-Buy über Kurs):** auf SB+-KO-Direkthandel **nicht** umsetzbar. Nur per **Direktaktie (Aktientopf)** mit Stop-Buy oder als **bewusste Live-Order** auf den Daily-Close.

### Exit

- **SL:** ≥ 1,5×ATR(14) unter Entry (Lektion 4 als Floor). Strukturell: bei Trigger A unter dem Konsolidierungshoch, bei Trigger B unter EMA20 − Puffer bzw. unter dem letzten Higher-Low. Ist der strukturelle SL enger als 1,5×ATR → auf 1,5×ATR aufweiten.
- **TP1:** nächstes Chart-Level (Measured-Move der Konsolidierungs-/Range-Höhe, altes Hoch, Gap-Kante) → 50% Teil-Exit, danach SL → Breakeven (Lektion 6).
- **Nach TP1:** SL = MAX(Breakeven, TP1 − 1,5×ATR) (Lektion 13).
- **TP2:** übergeordnetes Level / Measured-Move-Extension. Kein Chart-Level vorhanden → kein TP2 (Lektion 13). Restposition stattdessen über EMA20-Trail laufen lassen, solange der EMA-Stack intakt ist.
- **Time-Stop:** Open-End-KO → Finanzierungskosten (Lektion 3), harter Zeitstopp nach 2–3 Wochen. Trend kann länger laufen → bei intaktem EMA-Stack Rollover in ein frisches KO erwägen statt blind weiterhalten. Hart 1 HT vor Earnings.

### Sizing

Standard-Hybrid-Skala (5/7 = 1%, 6/7 = 2%, 7/7 = 3%) — diese Klasse ist **kein** Pilot-Sonderfall, sie nutzt die reguläre Score-Size. Zwei Modifikatoren:
- **Late-Entry-Cap:** 30d-Move > 15% → hart auf 1% (s.o.)
- **Gestaffelt:** Tranche 1 = 1%, Tranche 2 = Rest auf Score-Size (ab 6/7)

### Pipeline- und Parser-Hinweise

- **Maschinen-Gate** (EMA-Stack) ist pipeline-rechenbar — Kandidat für einen GAMECHANGER-/Setup-Layer-Filter „Momentum-Continuation".
- **Trigger B** (Pullback-Zone) ist als `in_range` heute vom `state_parser` sauber lesbar.
- **Trigger A** (Breakout-Zone): mit `[breakout]`-Tag formulieren — der Evaluator erkennt damit automatisch, wenn der Kurs über die Obergrenze (ATR-Chase-Cap, Trigger + ~1×ATR) durchgelaufen ist, und setzt `proximity=far` statt BEREIT. Seit Task 5 (2026-05-22) kein manueller Pre-Trade-Check mehr nötig. Tag-Syntax: `references/pipeline-integration.md` § Zonen-Semantik-Tags.
- **Trigger-B-Verfall (~8 HT):** der Parser kennt nur `nach YYYY-MM-DD` als Aktivierungs-, nicht als Verfallsdatum → B-Verfall als Status-Feld-Datum (📅) führen und manuell prüfen.
- **HH/HL-Pflichtpunkt** ist Handarbeit am Chart, nicht pipeline-rechenbar.

### Watchlist-Trigger — parser-konformes Beispiel

Werte illustrativ (Konsol-Hoch 120,00€, ATR-14 1,20€, EMA20 113,00€) — SL/R:R pro Fill final rechnen:

```
A) Daily-Close 120,40–121,60€ + Vol >Avg-20d. B) Touch 113,00–116,40€ (EMA20-Zone). SL A <119,20€ / SL B <110,80€. TP1 134€. R:R A ~7.
```

Zonen-Untergrenze A = 120,00 + 0,3×1,20 ≈ 120,40€; Obergrenze A = 120,40 + ~1×ATR ≈ 121,60€ (ATR-Chase-Cap); SL A entry-relativ (Entry − 1,5×ATR), nicht fix — Lektion 17. B-Zone = EMA20 113,00€ bis +3% (116,40€). B-Verfall (~8 HT) ins Status-Feld. Parser-Pflichtcheck (7 Punkte) vor dem Anlegen durchgehen.

### Nächste Schritte

- v0.1-Pilot: erste 3–5 Momentum-Continuation-Trades dokumentieren, danach Hit-Ratio + R-Multiple retrospektiv prüfen, dann Status auf vollwertige Setup-Klasse heben.
- Task 5 (Punkt→Zone-Migration): Breakout-Zonen-Obergrenzen-Invalidierung in `state_parser` generisch nachziehen — diese Klasse ist die Vorlage für die Zonen-Konvention.
- Pipeline: Maschinen-Gate als Setup-Layer-Filter prüfen.

## Handelsuniversum (3 Stufen)

Das Research-Universum ist gestuft — Stufe 1 ist Default, Stufe 2 springt automatisch an wenn Stufe 1 dünn ist, Stufe 3 nur auf Makro-Trigger oder Codewort.

| Stufe | Scope | FX-Regel | Research-Trigger |
|-------|-------|----------|------------------|
| **1 Kerneuropa** | Xetra, Euronext, LSE, SIX, Borsa/BME, Nordics — DAX/MDAX/SDAX/Scale, große EU/UK/CH-Werte | EUR-direkt bevorzugt; GBP/CHF/SEK/DKK per Quanto erlaubt | Default in jedem News/Hidden/Insider-Scan |
| **2 Nordamerika** | NYSE, Nasdaq, US-ETF-Komplex + Asia-ADRs (TSM, BABA, TM, SONY, etc.) | USD per Quanto Default; Non-Quanto erlaubt mit FX-adjustiertem R:R-Check (Lektion 1 v2: adjust. R:R ≥ 1,4) | Automatischer Fallback wenn Stufe 1 < 2 reife Kandidaten; oder US-Makro-Thema aus Makro-Check |
| **3 Asia-Makro-Indizes** | Nikkei 225, Hang Seng (evtl. TOPIX falls Produkt verfügbar) — **keine Einzelwerte** | JPY/HKD per Quanto Pflicht (Gap-Risiko) | Nur bei explizitem Makro-Trigger (BoJ/PBoC-Event, Japan-Rally, HK-Bodenbildung) oder Codewort „Asien-Scan" |

**Produktverfügbarkeits-Vorstufe bei Stufe 2/3:** Bevor ein Nicht-EUR-Kandidat in die volle 7/7-Checkliste geht, Quick-Check — Quanto-KO auf Gettex/SB+ verfügbar? Spread akzeptabel? Wenn nein → Alternative (Sektor-ETF-KO, Direktaktie) oder SKIP. Details: `references/produktkenntnis.md` § 3a.

### Serendipity-Regel

Wenn beim **Makro-Check oder TP/SL-Analyse** ein Trade-Kandidat sichtbar wird — auch ohne News-/Hidden-Scan-Codewort — wird er proaktiv genannt. Zwei Ausprägungen:

- **Stufe 1 / Primäruniversum:** Voller Kandidaten-Eintrag mit Vorcheckliste (wie News-Scan-Output).
- **Stufe 2 / Stufe 3 (bei aktivem Makro-Thema):** **3-Zeilen-Micro-Pitch** — Underlying, These, grober Chart-Zustand + Produktverfügbarkeit ja/nein. User entscheidet, ob Vertiefung zur vollen Checkliste.

Stufe 3 nimmt am Serendipity-Mechanismus **nur** teil, wenn der Makro-Check aktiv ein Asien-Thema adressiert — sonst schweigt sie.

**Im Morgen-Briefing gilt die Serendipity-Regel nicht** — dort läuft strikt das Action-Layer-Format (Bucket 4 Pitches, max 2–3, vorgefiltert durch Late-Entry → 5/7 → Counter-Thesis). Stufe-2/3-Micro-Pitches ohne 5/7-Plausibilität erscheinen nicht im Briefing.

**Micro-Pitch-Format:**
```
💡 [Stufe 2|3] — [Name, Ticker]: [Long|Short]
These: [1 Satz, was bewegt es]
Chart/Produkt: [30d-Move, 52W-Abstand grob] | Quanto-KO: ✅/❌/❓
```

## Makro-Analyse-Workflow

Bei „Makro-Check"/„Nachrichtenlage": (1) Websuche 3–5 Queries — Geopolitik/Branche/Analysten, (2) Einordnung: Eskalation/Deeskalation/Status quo, (3) Auswirkung auf Positionen, (4) Handlungsempfehlung, (5) Neue Chancen → **Serendipity-Regel anwenden** (Micro-Pitch für Stufe-2/3-Kandidaten, voller Eintrag für Stufe 1). Suchtiefe vorher ansagen (Regel 18).

**US-Indikatoren auf Nachfrage** (nicht mehr im Standard-Briefing — Drill auf Anfrage):
- VIX (CBOE) — US-Pendant zu VDAX-NEW, Schwellen ähnlich (< 15 Euphorie, > 28 Stress)
- DXY (Dollar-Index) — Richtung USD gegen Majors; relevant für Non-Quanto-Entscheidung (Lektion 1)
- S&P 500 Indikation (vor Xetra-Open relevant, nach Xetra-Close für ADR-Exposure)
- Fed-Event-Kalender (FOMC, NFP, CPI) — wenn in ≤ 5 Tagen, als Event-Risiko gegen Stufe-2-Positionen prüfen

## Screenshot-Analyse (Trade Republic / Smartbroker+)

User schickt Screenshots von: Zertifikats-Detailseite, Derivate-Liste, Order-Bestätigung, Portfolio. Bei jedem: Zahlen explizit nennen, Gegenrechnung machen (Kernformeln!), Plausibilität prüfen.

## Journal-Workflow (Excel/openpyxl)

Journal ist `Trading_Journal_YYYYMMDD.xlsx` — User lädt aktuelle Version am Chat-Start hoch, Claude gibt mit neuem Datum im Dateinamen zurück.

### 🔴 PFLICHT: File-Flow für Journal-Edits

**Eingang: immer Chat-Upload, nie Drive-Download.** Der User lädt die aktuelle xlsx als Anhang im Chat hoch. Datei landet in `/mnt/user-data/uploads/` und ist direkt mit `openpyxl.load_workbook()` lesbar. **Drive-Download via `Google Drive:download_file_content` ist NICHT geeignet für Edit-Roundtrips** — das Tool liefert den File-Inhalt als base64-String, der dann durch zwei weitere Tool-Boundaries muss (lokal speichern → editieren → für Upload wieder base64-encoden → in `Google Drive:create_file` reichen). Bei einem ~70 KB xlsx sind das ~95 KB base64, und das übersteigt die Tool-Argument-Größe in der Praxis. Der Versuch hat am 2026-04-30 mehrere fehlgeschlagene Anläufe gekostet. **Konsequenz: Drive-Tools (`download_file_content`, `read_file_content`) nur fürs Lesen** — z.B. wenn der User in einem neuen Chat das Journal noch nicht hochgeladen hat und Claude den letzten Stand braucht. Für Edits immer Chat-Upload anfordern.

**Ausgang: `present_files` aus `/mnt/user-data/outputs/`.** Die fertige Datei landet im Outputs-Verzeichnis und wird dem User als Download präsentiert. Der User lädt sie selbst nach Drive hoch — der Pipeline-Sync (Tier-A-Lauf, alle 30 Min Mo–Fr) zieht sie dann beim nächsten Lauf als neue Source-of-Truth.

**Dateinamens-Pattern bei Mehrfach-Updates am selben Tag:** Erstes Update des Tages → `Trading_Journal_YYYYMMDD.xlsx`. Zweites Update → `Trading_Journal_YYYYMMDDa.xlsx`. Drittes → `…b.xlsx`. Usw. Rationale: monoton aufsteigende Dateinamen, der Pipeline-Selektor kann eindeutig die jüngste Datei picken. Beim Chat-Start lädt der User die Datei mit dem höchsten Suffix hoch.

**Mini-Workflow für Hygiene-Edits / Note-Inserts / Watchlist-Pflege:**

```python
import sys; sys.path.insert(0, '/mnt/skills/user/derivate-trading')
import journal_utils as ju

src = '/mnt/user-data/uploads/Trading_Journal_20260430.xlsx'
dst = '/mnt/user-data/outputs/Trading_Journal_20260430a.xlsx'

wb = ju.open_journal(src)
# … Edits via ju.* oder direkt openpyxl …
ju.save_journal(wb, dst)
# Danach: present_files mit dst-Pfad
```

### 🔴 PFLICHT: Journal ist Single Source of Truth

**Alle State-Infos leben im Journal selbst** — keine externe STATE-Datei mehr (bis 22.04.2026 gab es `references/JOURNAL_STATE.md`, jetzt abgeschafft weil Divergenz-Risiko). Die relevanten Infos kommen aus diesen Sheets:

| Info | Quelle |
|------|--------|
| Letzte Trade-Nr. Derivate | `ju.find_next_trade_nr(wb[SHEET_SK]) - 1` |
| Letzte Trade-Nr. Aktien | max(Spalte A) in „Aktienveräußerungen" |
| Portfolio-Stand, SL/TP/Zeitstopp | „Übersicht" Z18+ (bis SUMME OFFEN) |
| Saldo-Werte | „Übersicht" Z9–Z11 (Formeln, aktualisiert automatisch) |
| Zeitstopp-Radar | Spalte H im Portfolio-Block |
| Watchlist | Sheet „Watchlist" |
| Zuletzt geschlossen | Sheet „Geschlossene Trades" (letzte ~5 Zeilen) |
| **Handlungsbedarf, TODOs, Milestones, ⚠️** | **Sheet „Notes"** (siehe unten) |

**Standard-Chat-Start:**

```python
import sys; sys.path.insert(0, '/mnt/skills/user/derivate-trading')
import journal_utils as ju

wb = ju.open_journal(path)

# Handlungsbedarf / Merkposten lesen
for note in ju.list_notes(wb, nur_offen=True):
    print(f"#{note['id']} [{note['kategorie']}] {note['text']}")

# Portfolio-Stand
positions = ju.collect_open_positions(wb)
```

Das ist schnell (1–2 bash-Calls), immer aktuell, und es gibt keine zweite Wahrheit mehr.

### Phase 5 — Pipeline-Auto-Load bei Trading-Kontext (seit 2026-04-26)

Nach dem Standard-Chat-Start läuft **bei eindeutigem Trading-Kontext** ein zusätzlicher Block, der die Pipeline-Files (MARKETDATA-Standard, CANDIDATES, GAMECHANGER) vorab aus Drive lädt. Damit haben Routinen 7/8/8b/8c die Daten schon im Kontext, wenn der User „Morgen-Briefing"/„Hidden Scan"/etc. sagt — kein zweiter Drive-Roundtrip mehr.

**Trigger (beide müssen erfüllt sein):**
1. Journal-Datei wurde im aktuellen Chat hochgeladen (Dateiname enthält `Trading_Journal`)
2. Aktuelles Datum/Uhrzeit liegt im Auto-Load-Fenster: **Mo–Fr, 06:00–22:00 CEST**

Sa/So oder außerhalb des Zeitfensters: **kein Auto-Load**, Routinen ziehen Pipeline weiter on demand (= Phase-4-Verhalten).

**Stil — silent:**
- Kein Vorspann im User-Output („Pipeline geladen ✓" o.ä.)
- Keine ungefragte Routine-7-Antwort
- Pipeline-Daten sind einfach im Kontext, wenn die nächste User-Frage trading-bezogen ist
- Wenn die nächste User-Frage NICHT trading-bezogen ist (Skill-Frage, Dokumenten-Hilfe, …): Pipeline-Daten ignorieren, normaler Chat

**Auto-Load-Block (unmittelbar nach Standard-Chat-Start ausführen, wenn Trigger erfüllt):**

```python
import sys; sys.path.insert(0, '/mnt/skills/user/derivate-trading')
import pipeline_utils as pu

# 1. Files in Drive finden — Briefing-Ordner
#    Tool: Google Drive search_files
#    Query: title contains 'MARKETDATA-FULL' or title contains 'CANDIDATES'
#           or title contains 'GAMECHANGER-HUNT'
#    pageSize=15 reicht (typisch ~6–9 Files in 24h-Fenster)

# 2. MARKETDATA-Files laden (alle MARKETDATA-Treffer, für Universum-Filter)
#    Tool pro Treffer: Google Drive read_file_content
md_files = []
for f in marketdata_search_results:
    md_files.append({**f, "content": read_file_content(f["id"])})

# 3. Standard-Universum picken (NICHT naiv jüngste mtime — siehe pipeline-integration.md § Zwei MARKETDATA-Universen)
md_pick = pu.select_latest_marketdata(md_files, universe="standard")

# 4. CANDIDATES + GAMECHANGER (jüngstes pro Typ)
cand_pick = max((f for f in cand_search_results if f["title"].startswith("CANDIDATES")),
                key=lambda f: f["modifiedTime"], default=None)
gc_pick   = max((f for f in gc_search_results if f["title"].startswith("GAMECHANGER-HUNT")),
                key=lambda f: f["modifiedTime"], default=None)

if cand_pick: cand_pick["content"] = read_file_content(cand_pick["id"])
if gc_pick:   gc_pick["content"]   = read_file_content(gc_pick["id"])

# Damit liegen md_pick / cand_pick / gc_pick im Kontext bereit für die Routinen.
# Optional Frische-Check schon hier — oder erst beim Routinen-Run.
```

**Bei Pipeline-Ausfall (Drive nicht erreichbar oder File >24h alt):** Nichts tun — silent fail. Wenn später eine Routine kommt, läuft sie auf Web-Fallback wie vor Phase 4. Den 🔴-Header zeigt sie dann selbst.

**Konsequenz für Routine 7:** Wenn die User-Frage „Briefing" / „Tagescheck" kommt und Pipeline-Daten schon vorgeladen sind → direkt ins Action-Layer-Format (6 Buckets), ohne erneuten Drive-Roundtrip. Wenn nicht (Wochenende, kein Journal, Pipeline-Ausfall): Routine läuft wie in Phase 4 mit Web-Fallback.

### Operationen via `journal_utils`

Seit Layout v2 (17.04.2026) werden alle Journal-Operationen über das Helper-Modul `journal_utils.py` (im Skill-Ordner) abgewickelt — nicht mehr direkt mit openpyxl-Rezepten. Das Modul kapselt Saldo-Berechnung, Gelb-Markierung, Portfolio-Sync, Archivierung und den Ghost-Value-Reload nach `save`.

```python
import sys; sys.path.insert(0, '/mnt/skills/user/derivate-trading')
import journal_utils as ju

wb = ju.open_journal('/mnt/user-data/uploads/Trading_Journal_YYYYMMDD.xlsx')
# … Operationen (siehe Routinen-Tabelle unten) …
wb = ju.save_journal(wb, '/mnt/user-data/outputs/Trading_Journal_YYYYMMDD.xlsx')
```

API-Referenz und Workflow-Beispiele: `references/journal-utils-api.md`.

**Ausnahmen — direkt openpyxl bleibt okay für:** Sparplan-Updates, Werbungskosten-Einträge (Routine 5), Krypto-Sheets (anderer Skill), Ad-hoc-Korrekturen an Altdaten.

### Mini-Checkliste nach jedem Journal-Update

Am Ende jedes Trade-Updates explizit bestätigen:
- ✅ Zeile im Detail-Sheet („Sonstige Kapitalerträge" oder „Aktienveräußerungen")
- ✅ **Gebühr Kauf (Spalte N/O) bei Entry gesetzt, Gebühr Verkauf bei Close gesetzt** — sonst fehlt der Trade in der Übersichts-Summenzeile R15
- ✅ Übersicht-Sheet synchron (Portfolio-Block + SUMME)
- ✅ Saldo + Steuer + Netto aktualisiert
- ✅ Gelbe Markierung entfernt (bei Close) oder gesetzt (bei neuer OFFEN)
- ✅ Notes-Sheet: erledigte TODOs via `ju.resolve_note(...)` geschlossen, neue via `ju.add_note(...)` ergänzt

### Sheet-Struktur

Detaillierte Spalten-Layouts → `references/journal-layout.md`
Kurzform (Journal-Layout v3, Stand 24.04.2026):
- **„Übersicht"** (Blatt 1): Portfolio-Dashboard, synchron mit Detail-Blättern halten. **R15: Gebühren kumuliert 2026** (Info-Zeile, bereits in Saldi verrechnet)
- **„Sonstige Kapitalerträge"** (Blatt 2, Spalten A–O): Derivate + ETFs/ETPs. **N = Gebühr Kauf, O = Gebühr Verkauf**
- **„Aktienveräußerungen"** (Blatt 3, Spalten A–P): Direktaktien, **separater Steuertopf**! **O = Gebühr Kauf, P = Gebühr Verkauf**
- **„Krypto §23 EStG"** (Blatt 4): Krypto-Skill zuständig
- **„Werbungskosten"** (Blatt 7): Abos/Rechnungen
- **„Watchlist"**: Aktien unter Beobachtung
- **„Geschlossene Trades"**: Archiv (automatisch via `close_trade_complete`), **M = Gebühr Kauf, N = Gebühr Verkauf**
- **„Notes"**: Handlungsbedarf, Milestones, ⚠️ (siehe Notes-Workflow oben)

**⚠️ Steuertopf-Kritik:** Aktienverluste (§20 Abs. 2 Nr. 1 EStG) sind **nur** mit Aktiengewinnen verrechenbar — NICHT mit KO/ETF/ETP-Gewinnen aus „Sonstige Kapitalerträge". TR führt den Aktientopf automatisch getrennt. Bei Broker-Wechsel (TR ↔ SB+): Verlustbescheinigung bis 15.12. beantragen.

### Routinen — kompakte Übersicht

| Routine | Trigger | Ablauf |
|---------|---------|--------|
| **1** Derivate-Trade eintragen | „Trade eintragen" + KO/ETF/ETP | `ju.add_trade_complete(wb, trade={..., 'gebuehr_kauf': 4.00}, portfolio_kurzname=..., kind='derivate')` — macht Detail-Zeile in „Sonstige Kapitalerträge" + OFFEN/gelb + Portfolio-Zeile + Timestamp + **Gebühr Kauf in N** in einem Aufruf. **Pflicht ab v3:** `gebuehr_kauf` im trade-Dict; Default-Tabelle siehe „Gebühren-Defaults". Trade-Plan-Template → `references/trade-plan-templates.md` |
| **1a** Direktaktie eintragen | Instrument ist Aktie (kein KO-Kürzel) | `ju.add_aktie(wb, {..., 'gebuehr': 1.00})` (Sheet „Aktienveräußerungen") — Einsatz = Stk×Kurs + Gebühr, **zusätzlich in Spalte O** (Transparenz). **⚠️ Nie in „Sonstige Kapitalerträge"!** Aktientopf-Hinweis in die Notiz. |
| **1b** Direktaktie analysieren | „Aktie analysieren", „soll ich X kaufen" | Pre-Trade-Plan aus `references/trade-plan-templates.md` + Websuche 1–3 Queries (Fundamentaldaten, Ex-Div, Analysten) → Checkliste 7/7 + Counter-These → GO/NO GO |
| **2** Trade schließen | „verkauft", „ausgestoppt", „Stop-Loss" | Komplett: `ju.close_trade_complete(wb, nr, verkaufsdatum, erloes, lektion=..., kind='derivate'\|'aktie', gebuehr_verkauf=4.00)` — schließt Zeile + Saldo + Archiv + Portfolio + **Gebühr Verkauf in O (SK) bzw. P (AV)**. `erloes` muss bereits Gebühr-netto sein. Teilverkauf: `ju.partial_exit_derivate(...)`. |
| **3** Depotauszug abgleichen | TR-PDF hochladen | Depot lesen → alle OFFEN-Einträge sammeln → Soll-Ist-Vergleich (fehlt in Journal → ⚠️; fehlt im Depot → schließen ⚠️) → Timestamp → speichern |
| **4** ⚠️-Marker abarbeiten | „Aufräumen", „⚠️ abarbeiten" | Alle Sheets nach ⚠️ durchsuchen → gebündelt nachfragen → eintragen → speichern |
| **5** Werbungskosten | Claude/ChatGPT-Abo, Rechnung | Sheet „Werbungskosten" (Blatt 7) → nächste freie Zeile → Datum/Anbieter/Beschreibung/Betrag/Nachweis → SUMME-Zeile aktualisieren |
| **6** TP/SL-Analyse .docx | „Analyse erstellen", „TP/SL-Übersicht" — proaktiv So/Mo, vor Earnings, nach > 3% Move | Journal + TradingView-Screenshots → `TP_SL_Analyse_YYYYMMDD.docx`: Makro + RSI/EMA farbkodiert + Einzelanalysen (SL/TP/R:R) + Gesamtübersicht + Handlungstabelle + Fazit. docx-SKILL.md lesen. |
| **7** Morgen-Briefing | „Morgen-Briefing", „Tagescheck" — proaktiv bei offenen Positionen | **Pipeline-First + Action-Layer-Format (6 Buckets — siehe § Routine 7 — Action-Layer):** MARKETDATA-STD + CANDIDATES + GAMECHANGER aus Drive laden (`pu.select_latest_marketdata(files, universe="standard")`), Frische prüfen. **Direkt in Buckets rendern, keine Kompakt/Detail-Frage.** Reihenfolge: (1) Insider-Cluster (2) BEREIT (3) NAHE (4) Pitches (max 2–3, vorgefiltert) (5) Dringend (6) Offene Positionen. Bei Pipeline-Ausfall: Web-Fallback mit 🔴-Header. Makro/Ad-hoc-Drill nur auf explizite User-Nachfrage. |
| **8 / 8b / 8c** | „News-Scan" / „Hidden Scan" / „Insider-Verkäufe" | **→ `references/news-scan.md`** (enthält alle drei Routinen inkl. 4-Schichten-Modell und Output-Formate) |

### Pro Routine benötigte Daten

| Routine | Mindestdaten | Optional |
|---------|-------------|----------|
| 1 Derivate | Datum, Instrument, Kaufsumme, Richtung, **Gebühr Kauf** | ISIN, Stk, Kurs, SL/TP, These |
| 1a Direktaktie | Datum, Aktie, Stück, Kurs, **Gebühr Kauf** | ISIN, Börse, SL/TP, These |
| 1b Analyse | Aktie/Ticker/ISIN | Zeithorizont, Kapital, These |
| 2 Schließen | Welcher Trade, Erlös ODER Verkaufskurs, **Gebühr Verkauf** | Datum, Lektion |
| 3 Depotauszug | PDF oder Textliste | — |
| 6 TP/SL | Journal, TV-Screenshots | Makro, spezifische Fragen |
| 7 Briefing | „Briefing bitte" | — (direkt Action-Layer) |
| 8/8b/8c | Codewort | — |

## Pipeline-Integration (Phase 4, seit 26.04.2026)

Drei Routinen ziehen ihre Markt-, Watchlist- und Gamechanger-Daten primär aus drei Markdown-Files im **Workspace Shared Drive → Trading-Pipeline/Briefing/**, die eine GitHub-Action alle 30 Min Mo–Fr (Tier A) bzw. 1×/Tag 07:30 (Tier B) schreibt:

| Routine | Zeitfenster | Frische-Schwelle |
|---------|-------------|------------------|
| `morning_check` (Routine 7) | 08:45 CEST | ≤ 30 Min |
| `scan_afternoon` (Routine 8/8b) | 15:45 CEST | ≤ 30 Min |
| `scan_evening` (Routine 8b/8c) | 20:30 CEST | ≤ 60 Min |

**Files:**
- `MARKETDATA-FULL-STD-YYYY-MM-DD-HHMM.md` / `MARKETDATA-FULL-GC-YYYY-MM-DD-HHMM.md` — Indikator-Set (Kurs, EMA20/50/200 mit Stack, RSI-14, ATR-14, 30d-Move, 52W-Range, 20d-Range, Volumen). **Pipeline schreibt zwei Universen** (seit Action-Edit 2026-04-26 mit Filename-Tag): `STD` (~47 Ticker mit Indizes/Krypto/FX/Watchlist) für Routinen 7/8, `GC` (~44 Wachstumsaktien) als Setup-Pool. `pu.select_latest_marketdata(..., universe="standard")` picken — siehe `references/pipeline-integration.md` § Zwei MARKETDATA-Universen.
- `CANDIDATES-YYYY-MM-DD-HHMM.md` — Watchlist-Trigger-Status in 7 Buckets + Filter-Overrides + priority_long/short Overrides.
- `GAMECHANGER-HUNT-YYYY-MM-DD-HHMM.md` — Setup-getriggerte Stufe-2-Kandidaten aus dem Universe-Scan (z.B. Long-Trend-Pullback, Short-Trend-Pullback). Additiv zur Watchlist.

**Helper:** `pipeline_utils.py` — Parser, Frische-Check, Lookup. Volltextschema, Workflow und Fallback-Verhalten: `references/pipeline-integration.md`.

**Fallback-Granularität:**
- **Core (MARKETDATA + CANDIDATES):** Bei `status='ok'` → Pipeline-Daten ohne Web-Fetch nutzen. Bei `status='stale'` → Pipeline-Daten + 🟡-Warnung im Header. Bei `status='ausfall'` oder `'missing'` → komplettes Fallback auf bisherige Web-Logik (Routine läuft wie vor Phase 4) + 🔴-Header.
- **Additiv (GAMECHANGER-HUNT):** Ausfall löst KEINEN globalen Fallback aus — der Gamechanger-Block fällt im Briefing einfach weg, der Rest läuft normal weiter.

## Watchlist-Abgleich (Pflicht bei Morgen-Briefing & Kandidaten-Scans)

Die Watchlist (Sheet „Watchlist") enthält bereits durchdachte Setups mit definierten Triggern. Kandidaten, die darauf stehen, sind **keine neuen Kandidaten** — sie haben einen Plan, der entweder gerade getriggert wird oder weiter wartet. Deshalb:

**🆕 Phase 4.1 (seit 29.04.2026) — Watchlist-Sync:** Das Excel-Sheet „Watchlist" im Trading-Journal ist **Single Source of Truth**. Die Pipeline syncht den Watchlist-Block bei jedem Tier-A-Lauf (alle 30 Min) automatisch ins STATE-Doc. Pflege also nur im Excel — Edits am STATE-Watchlist-Block werden überschrieben. Pflichtspalte: `Symbol` (Yahoo-Ticker). Detail in `references/pipeline-integration.md` § Watchlist-Sync.

**🆕 Watchlist-Verfallsdatum (seit 07.05.2026 — Frequenz-Disziplin):** Jeder Eintrag hat ein Verfallsdatum (Spalte H oder im Datum-Feld). Default = +14 HT. Event-Ausnahme = Event-Datum + 3 HT. Bei Verfall ohne Trigger: Setup geht in Bucket „archived" (nicht löschen — Audit). Einmalige Verlängerung um max. 7 HT erlaubt. Details: SKILL.md § Watchlist-Verfallsdatum.

**🆕 Watchlist-Archived-Status mit Re-Eval-Trigger (Note #63, seit 15.05.2026):** „Archived" ist nicht nur Verfalls-Bucket, sondern aktive Status-Klasse für **strukturell tote Setups** (z.B. Slow-Burn-eingepreiste Sektor-Setups, siehe Note #62). Unterschied zu klassischem Verfall:

| Stadium | Auslöser | Re-Eval-Bedingung |
|---------|----------|-------------------|
| BEREIT / Watch | Trigger pending | Trigger-Hit oder Verfall |
| Verfall-Archived | 14 HT ohne Trigger | Manuell, beim nächsten Sektor-Scan |
| **Strukturell-Archived** | Phasen-Audit → Slow-Burn / Regime-Wechsel | **Explizit definiertes Spike-Event** (z.B. „Brent +5$ in <3 HT", „neuer Tarif-Schock") |

Strukturell-archived-Einträge werden im Trigger-Feld mit `[STRUKTURELL-ARCHIVED, Re-Eval bei: <konkrete Bedingung>]` markiert. Pipeline parser ignoriert diese standardmäßig (kein Bucket-Eintrag), Re-Activation passiert manuell beim Erkennen der Re-Eval-Bedingung.

**🆕 Phase 4 (seit 26.04.2026):** Der Trigger-Status der Watchlist wird **primär aus der Pipeline-Datei `CANDIDATES.md`** gelesen — nicht mehr live via `ju.list_watchlist(wb)` im Briefing-Lauf. Die Pipeline (GitHub Action, alle 30 Min Mo–Fr) hat die Trigger schon ausgewertet und in 7 Buckets sortiert: 🎯 BEREIT, 📍 ≤2%, ≤5%, ≤10%, 📅 Pending (Datum), ⏸ Paused, 🔍 Passive (>10%). Helper: `pipeline_utils.parse_candidates(content)`. Details und Fallback: `references/pipeline-integration.md`.

`ju.list_watchlist` und `ju.match_watchlist` bleiben aktiv für Edge-Cases (Off-Universe-Kandidat aus News-Scan, der nicht in den 47 Pipeline-Tickern liegt) und als Fallback bei Pipeline-Ausfall.

### Routine 7 — Action-Layer-Format (Pflicht, seit 2026-05-17)

**Briefing folgt strikt 6 Buckets in dieser Reihenfolge.** Jede Watchlist-Position muss in genau einem Bucket erscheinen (BEREIT / NAHE / Dringend-Wartung) oder unsichtbar bleiben (WATCH ≤5%/≤10%/passive). Makro und Ad-hoc laufen im Hintergrund (Pipeline + DGAP-Check), fließen nur sichtbar ein, wenn sie ein Bucket bewegen.

**Bucket 1 — Insider-Cluster** (immer ganz oben). Datenquellen: EQS/DGAP-Auswertung der letzten 1–3 HT + Insider-Layer aus Pipeline. Trigger: ≥2 Org-Personen (Vorstand/AR), Volumen pro Person ≥100k€, zeitlich gebündelt (idealerweise ≤5 HT), bevorzugt um Earnings/Adhoc. Setup-Klasse Note #48 hat **eigene** Trigger-Logik (Trigger A/B), nicht in BEREIT/NAHE mischen.

**Bucket 2 — BEREIT** (CANDIDATES-Bucket `bereit`). Trigger vollständig erfüllt → volle 7/7-Checkliste + Pre-Trade-Plan + Hebel/Zertifikat-Vorschlag inline. Output-Template siehe `references/trade-plan-templates.md`.

**Bucket 3 — NAHE** (CANDIDATES-Bucket `very_close`, harte Schwelle: **eine Restbedingung offen**). Konkreten Auslöser benennen („Schluss >78,40 fehlt", „Volumen-Spike fehlt"). Keine volle Checkliste, nur Vorbereitung.

**Bucket 4 — Pitches** aus GAMECHANGER (EU + US). **Max 2–3, vorgefiltert** durch dreistufigen Filter:
1. Late-Entry: 30d-Move ≤15% (Lektion 8), sonst raus.
2. 5/7-Plausibilität: Realistisch erreichbar nach Checkliste — wenn 4/7 oder schlechter wahrscheinlich, raus.
3. Counter-Thesis: Aktive Buybacks, Analyst-Upgrades, parallele Insider-Verkäufe, Earnings <72h, sektoraler Gegenwind — inline prüfen und Verdikt nennen.

Nur was alle drei Stufen überlebt, wird als Pitch gezeigt — mit Setup-Logik (1–2 Sätze) + Counter-Thesis-Verdikt. Rest verschwindet (kein Anhang, kein „weitere Treffer").

**Bucket 5 — Dringend.** Offene Positionen mit konkretem Action-Bedarf: Trail-SL nach TP1 fällig, Zeitstopp erreicht, Buchverlust an SL. **Plus Wartungs-Einzeiler:** Watchlist-Verfall <14 HT, Re-Eval-Date überfällig, Skill-Fristen (PAT-Renewal 2026-07-21, Tier-3-Krypto-Haltefrist-Fenster Juni/Juli 2026). Macht den WATCH-Failure-Mode (vergessene Setups) wett, ohne tägliche WATCH-Liste.

**Bucket 6 — Offene Positionen.** Einzeiler „N Positionen im Plan, keine Action" wenn ruhig — sonst entfällt der Bucket (alle Action-Punkte stehen schon in Dringend).

**Nicht im Briefing** (auf Nachfrage):
- WATCH-Buckets: `close` ≤5%, `watching` ≤10%, `passive` >10%, `pending` ohne Trigger-Bewegung
- Makro-Roundup ohne Trade-Bezug (DAX-Indikation, US-Indikatoren, Asien-Schluss)
- Ad-hoc-Vollliste / Insider-Listen ohne Bucket-Bezug
- Sektor-RSI/EMA-Dump
- Sentiment-Block (VDAX/PCR/EUWAX)

Bei expliziter Nachfrage („Makro bitte", „volle Ad-hoc", „Sektor-Check") wird der jeweilige Block nachgeliefert.

#### Bucket-Mapping CANDIDATES → Action-Layer

| Pipeline-Bucket | Action-Layer-Bucket | Aktion |
|-----------------|---------------------|--------|
| `bereit` | **BEREIT** | 7/7 + Pre-Trade-Plan |
| `very_close` (≤2%) | **NAHE** | Auslöser benennen |
| `close` (≤5%), `watching` (≤10%), `passive` (>10%) | — (unsichtbar) | Nicht ins Briefing |
| `pending` (Datum) | — bzw. **Dringend** wenn Verfall <14 HT | Verfall-Wartung in Dringend |
| `paused` | — (unsichtbar) | Nicht ins Briefing |
| Filter-Override `priority_long/short` | **NAHE** oder **BEREIT** je nach Trigger-Status | Vorgezogen mit Begründung |
| Insider-Cluster (EQS/DGAP, ≥2 Personen, ≥100k€) | **Insider-Cluster** | Bucket 1, eigene Trigger-Logik |

**Bei Pipeline-Ausfall** (Frische-Status `missing` oder `ausfall`): Fallback auf `ju.list_watchlist(wb)` mit Live-Trigger-Check, 🔴-Header mit Status, Buckets BEREIT/NAHE/Dringend werden manuell aus Watchlist + Web-Daten gefüllt. Bucket 1 (Insider) und 4 (Pitches) fallen weg, wenn keine alternative Datenquelle vorhanden.

### Routinen 8 / 8b / 8c — Watchlist-Pflicht-Abgleich

Jeder Kandidat aus News-Scan, Hidden Catalyst Scan oder Insider-Scan wird **vor** dem Output gegen die CANDIDATES-Pipeline abgeglichen. Wenn der Kandidat dort schon in einem Bucket steht, ist er **kein neuer Kandidat** — der Plan existiert bereits. Code-seitig:

```python
import pipeline_utils as pu

# Pipeline laden (siehe pipeline-integration.md)
snap = pu.parse_candidates(candidates_content)

match = pu.find_candidate_in_buckets(snap, kandidat_name_oder_ticker)
if match:
    # NICHT als "neuer Kandidat" ausgeben — stattdessen:
    # "[BEREITS AUF WATCHLIST — Bucket: …, Trigger-Status: …]"
```

Bei Pipeline-Ausfall fällt der Abgleich auf `ju.match_watchlist(wb, name)` zurück (token-basiertes Matching, das auch Aktienname UND Kürzel wie `AIXA`, `EUZ`, `GV6` trifft, wenn diese im Watchlist-Feld als Klammerzusatz vorhanden sind). Details und Testfälle: `references/journal-utils-api.md` § Watchlist.

**Output-Regel bei Pipeline-Match:** Kandidat wird **nicht** als neue Idee präsentiert. Stattdessen: Statuszeile „BEREITS AUF WATCHLIST — Bucket: {bereit/very_close/...} — Richtung: {Long/Short} — Details: {…}" — und **nur dann** volle Checkliste, wenn der Bucket `bereit` ist (dann mit Verweis „Watchlist-Trigger hit, nicht News-Scan-Trigger").

**🆕 Pipeline-WL-Merge-Regel bei Trigger-Konflikt (Note #60, seit 15.05.2026):** Wenn Pipeline einen Kandidaten in eine Richtung wirft (z.B. Long-Pullback aus Pipeline-Scan) und Watchlist denselben Wert in entgegengesetzter Richtung hält (z.B. Short-Setup aus Sektor-These), nicht suppressen, sondern **erweitern**:

- **Gleiche Richtung:** Pipeline-Trigger als **Refinement** des WL-Eintrags behandeln (z.B. RSI-Bedingung verfeinern). WL bleibt führend.
- **Andere Richtung:** Zweiten Trigger ins WL-Trigger-Feld ergänzen mit **Edge-Klassifizierung** in eckigen Klammern: `[Trigger A Short — Sektor-These] | [Trigger B Long — Pipeline-Pullback]`.
- **Doppel-Hit (beide Trigger gleichzeitig aktiv):** Edge-Hierarchie aus Note #59 entscheidet — Insider > PEAD > EMA200-MeanRev > Reversal > Trend-Pullback > Breakout. Bei gleichem Edge-Tier: **R:R-bestes Setup gewinnt**.
- **Output im Briefing:** Beide Trigger nennen, Konflikt-Bemerkung „⚠️ Bidirectional-WL-Eintrag — Hierarchie: …"

### Watchlist-Eintrag — Parser-Pflichtcheck (Pflicht vor jedem Anlegen/Edit)

Watchlist-Trigger werden von `state_parser.py` automatisch in strukturierte Bedingungen zerlegt (earliest_date, price_op, price_single, vol_mult, rsi_min/max, require_bounce). Falsch formulierte Trigger laufen entweder ins Leere („kein konkreter Trigger im STATE" → Setup landet ohne Bucket-Status in Passive) oder produzieren False-Positives (BEREIT, obwohl Bedingung gar nicht erfüllt ist — z.B. Brent-Trigger gegen NOK-Kurs). **Beide Fehler sind teuer und müssen vor dem Anlegen vermieden werden.**

**Sieben-Punkte-Check vor jedem neuen oder geänderten Trigger:**

| # | Regel | Kompatibel | Inkompatibel |
|---|-------|------------|--------------|
| 1 | Datum-Constraint: ISO `nach YYYY-MM-DD` am Trigger-Anfang | `nach 2026-05-14 (...)` | `Ab 02.05.2026`, `NACH Q1 07.05.2026` |
| 2 | Operator + Preis + Currency-Suffix (Currency HINTEN, kein Space dazwischen) | `>180€`, `<58$`, `≥240€` | `>$180`, `>180 €` (Space) |
| 3 | Externe Trigger (Brent, FX, Underlying ≠ Symbol): KEIN Operator-Pattern, sondern Wort-Form | `Brent (BZ=F) über 113 USD` | `Brent >113$` (Parser matcht gegen eigenen Symbol-Kurs!) |
| 4 | Touch-Setup: `Touch` oder `Daily-Touch` als Schlüsselwort | `Touch EMA20 1D ~174€` | `Pullback auf EMA20 ~174€` |
| 5 | Volumen-Schwelle: `Vol >Avg-20d` oder `Vol ≥1,2× Avg` (kein Space vor Avg/Multiplier) | `Vol >Avg-20d`, `Vol ≥1,2× Avg` | `Vol ≥ Avg-20d` (Space), `Vol > 30D-Schnitt` |
| 6 | Mehrere Trigger: A)/B)-Labels mit Punkt-Klammer-Schluss, kein `ODER` zwischen Preispunkten | `A) ... B) ...` | `A) ~240€ ODER ~237€` → splitten in A und B |
| 7 | Zonen-Tag: Breakout-/Breakdown-Zonen mit `[breakout]` taggen, Pullback-Zonen mit `[pullback]` (hinter dem Range) | `380-384$ [breakout]`, `49,80-50,50$ [pullback]` | Breakout-Zone ohne Tag → Durchlaufen wird nicht erkannt |

**Komponenten, die der Parser sauber strippt (bedenkenlos drin lassen):**
- `SL <X€`, `SL X%`
- `TP1 ...€`, `TP2 ...€`, `TP X%`
- `R:R 1,2 / 2,4`, `R:R ~2,5`
- ATR-Hinweise wie `-1,2 ATR`, `+0,5 ATR`

**Status-Datum-Konvention (watchlist_sync):**
- Trigger-Text: ISO `nach 2026-05-14`
- Status-Spalte F: Punkt-Form `📅 nach 14.05.2026` (für STATE-Doc-Render)
- Bei mehreren Daten im Status: Re-Eval-Datum als ERSTES — Parser nimmt First-Match

**Sub-Cluster-Tag-Konvention:** Cluster-Constraints in eckigen Klammern am Trigger-Ende: `[A2 · Insurance-Oversold-Cluster MAX 1 mit MUV2]`, analog zu CRWD/PANW-Beispiel.

**Workflow:**
1. Trigger formulieren
2. 7-Punkte-Check durchgehen
3. Bei Brent-/Externe-Trigger-Fällen besonders aufpassen (Regel 3 — häufigster Bug-Quelle, siehe 13.05.2026-Patch)
4. Erst dann ins Journal schreiben

Volldetail mit allen Edge-Cases (Range-Notation, Volumen-Multiplier-Variationen, Modifikatoren wie Bounce/Hammer, RSI-Bedingungen): `references/pipeline-integration.md` § Trigger-Syntax — was der Parser versteht.

## Wichtige Warnsignale (proaktiv ansprechen)

- Position offen > 2 Wochen bei Open-End KO → Finanzierungskosten-Warnung
- Alle Positionen in dieselbe Richtung → Korrelationswarnung
- SL nicht gesetzt → sofort nachfragen
- Hebel > 7× → Risiko explizit betonen
- Trade nach > 15%-Move → Late-Entry-Warnung
- Earnings/Events in ≤ 5 Tagen → Positionsreduzierung empfehlen
- **🆕 Ex-Div in ≤ 5 Tagen bei Short-Setup → harter Block (Note #64)**
- Sizing > Score-Klasse erlaubt (5/7→1%, 6/7→2%, 7/7→3%, Insider+7/7→4%) → sofort warnen
- Pre-Trigger-Order ohne 1%-Sizing → sofort warnen
- Watchlist-Eintrag ohne Verfalldatum → bei Anlage einmal nachfragen, dann +14 HT default
- ≥ 3 Positionen gleiche These/Richtung → als einen Risikoblock behandeln
- Chat-Start mit offenen Positionen → Morgen-Briefing anbieten
- So/Mo, vor Earnings, nach > 3% Move → TP/SL-Analyse anbieten
- **🆕 V2-Counter-These-Score ≤ -6 → Watch-only oder 0,25× Sizing (Note #65, Arbeitshypothese)**
- **🆕 Sektor-Setup älter als 30 HT ohne Phasen-Audit → Regime-Check anbieten (Note #62)**
- **🆕 Breakdown-Short-Kandidat mit -3% bis -10%-Tagesverlust → Ex-Tag-Pre-Filter rückwärts pflichtig (Note #67)**
- **🆕 Zonen-Trigger (`[breakout]` ODER `[pullback]`) mit fixem SL → SL-Abstand ÷ ATR(14) an der ungünstigen Zonenkante prüfen. < 1,5×ATR = Lektion-4-Verstoß → SL entry-relativ umstellen (Lektion 17, Note #88/#89/#92). Reine Zonenbreite ist KEIN ausreichendes Kriterium — auch eine breite Zone kann einen zu engen Fix-SL haben (Befund CHKP-A 22.05.2026: Zone 1,11×ATR, Fix-SL 0,93×ATR).**

## Referenz-Dateien

| Datei | Laden wenn... |
|-------|---------------|
| `journal_utils.py` | Das Helper-Modul — wird per `import journal_utils as ju` eingebunden (siehe Journal-Workflow oben). Direkt anfassen nur, wenn das Journal-Layout sich ändert und das Modul nachgezogen werden muss. |
| `pipeline_utils.py` | Helper für Phase-4-Pipeline-Integration — wird per `import pipeline_utils as pu` eingebunden. Parst MARKETDATA-FULL.md und CANDIDATES.md aus Drive, liefert Frische-Status + Lookups für Routinen 7/8/8b/8c. |
| `references/pipeline-integration.md` | **SOFORT laden** vor jedem Lauf von Routine 7, 8, 8b oder 8c — definiert den vollen Workflow (Drive holen → parsen → Frische → Briefing rendern), File-Schemata, Fallback-Verhalten und Helper-Aufrufe. |
| `references/journal-utils-api.md` | API-Referenz des Moduls — vollständige Funktionsliste inkl. Notes-API, typische Workflows (Routine 1/1a/2/partial/Watchlist/Notes), Konstanten-Tabelle. |
| `references/trade-plan-templates.md` | Trade-Plan benötigt (Routine 1b, neue Position planen). KO-Template + Direktaktien-Template. |
| `references/setup-klassen.md` | Setup-Klassen-Spezifikation gebraucht — PEAD-Pilot v0.1 (+ Unterklasse News-Catalyst-Continuation-Long), Insider-Buys-Cluster v0.1, EMA200-Mean-Reversion v0.1. Enthält je Klasse Vorprüfung, 7/7-Filter, Entry/Exit, Haltedauer, Sizing, Anker. |
| `references/journal-layout.md` | Detail-Fragen zu Sheet-Spalten, Saldo-Zeilen-Struktur, Formatting-Standards, Zellenfarben, Zebra-Streifen. |
| `references/news-scan.md` | News-Scan / Hidden Scan / Insider-Verkäufe — **SOFORT laden** bei Codewort, dann Routine ausführen. |
| `references/technische-analyse.md` | Fragen zu Indikatoren, Chart-Analyse, TradingView-Setup, Candlestick-Patterns, oder Chart-Abgleich im Makro-Workflow. |
| `references/produktkenntnis.md` | Ordertypen, Broker-Vergleich, **Zertifikat-Auswahl**, CFDs, Optionen, Kelly, Position-Sizing-Vertiefung, TR/SB+-Limitierungen. |
| `references/iran-watchlist-yaml-patch.md` | Pipeline-YAML-Erweiterungs-Skizze für Iran-Watchlist + XAD5 (Note #30). Laden bei Pipeline-Maintenance, vor Patch des Standard-Universums. |

## Versioning-Konvention

Output-Dateien tragen das Datum des Updates im Dateinamen: `Trading_Journal_YYYYMMDD.xlsx` (z.B. `Trading_Journal_20260422.xlsx`). Alle State-Infos (TODOs, Milestones, ⚠️) leben im Journal-Sheet „Notes" selbst — keine externe STATE-Datei mehr. Kein semantisches Versioning (keine `1.x.x`-Nummern).
