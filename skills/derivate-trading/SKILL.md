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

**🚨 AUSFÜHRUNGSREGEL — SOFORT HANDELN:** Bei den Codewörtern oben **nicht** fragen/erklären — Referenz lesen (wenn angegeben), Routine sofort ausführen. Bei „Trade eintragen" + vollständigen Daten → direkt Journal updaten. Bei „Morgen-Briefing" → erst Kompakt/Detail fragen, dann suchen.

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
Max. Verlust = Risikokapital × 0,02
Stückzahl    = Max. Verlust / (Einstieg − SL)
Einsatz      = Stückzahl × Briefkurs
Kaufsumme    = Einsatz + Gebühr Kauf    (ab v3 explizit einpflegen)
```
**Hybrid-Skala nach Score:** 5/7 = 1% (150€) · 6/7 = 2% (300€) · 7/7 = 3% (450€) · Insider+7/7 = 4% (600€). Korrelierte Positionen zählen als **ein** Block gegen das 2%-Budget.

**Minimum:** Unter 400€ sind KO-Zertifikate spread-ineffizient.

### Gebühren-Defaults (v3 — für Transparenz-Spalte)

| Broker / Handelsplatz | Gebühr pro Order | Hinweis |
|-----------------------|------------------|---------|
| Trade Republic | **1,00€** | Flatrate alle Börsen |
| Smartbroker+ / Gettex | **4,00€** | Minimum; default für SB+ ohne Plätz-Hinweis |
| Smartbroker+ / Frankfurt Zertifikate | **5,90€** | Nicht-Gettex-KOs (z.B. bei HSBC-IDs mit W-Endung) |
| Smartbroker+ / Xetra | 4,00€ + ~0,12% | Selten bei Derivaten |

**Pflicht beim Trade-Eintrag ab v3:** Kauf-Gebühr ist **in Kaufsumme einzurechnen** UND zusätzlich in Spalte N (SK) bzw. O (AV) explizit auszuweisen. Matthias liefert die Gebühr bei neuen Trades mit. Beim Close analog für die Verkauf-Gebühr.

## Die Lektionen (Kurzfassung)

1. FX-Underlyings erlaubt mit Pre-Trade-Check — Quanto-Default, Non-Quanto nur ≤10d; EM-Währungen (TRY/ZAR/ARS/MXN/RUB) ausgeschlossen; Rohstoff-Korrelation bei NOK/CAD/AUD/BRL explizit prüfen; kein Entry <90min vor Earnings. Volltext: Journal-Sheet „Lektionen". Universums-Logik: Abschnitt „Handelsuniversum" unten.
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
12. Position Sizing = 2%-Regel (Fixed-Fractional)
13. **TP von Chart → R:R — nie rückwärts:** Erst Widerstand finden, dann R:R rechnen. ATR-Plausibilitätscheck: > 5–6 ATRs in 2–3 Wochen = unrealistisch. Nach TP1-Treffer: SL = MAX(Breakeven, TP1 − 1,5×ATR).

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

## Counter-These-Checkliste (vor jedem Short)

1. Aktives Aktienrückkaufprogramm? → Stützt Kurs, Short-Squeeze-Risiko
2. Frische Analysten-Upgrades? → Sentiment dreht
3. Anstehende Dividende? → Ex-Dividenden-Effekt bei KO-Schwelle
4. Gegenläufige Effekte (Pricing Power, Hedging)?
5. Reagiert die Aktie schwächer als erwartet auf die Krise? → Markt sieht etwas, das du nicht siehst

Jeder Treffer wird als Risiko explizit benannt.

## Handelsuniversum (3 Stufen)

Das Research-Universum ist gestuft — Stufe 1 ist Default, Stufe 2 springt automatisch an wenn Stufe 1 dünn ist, Stufe 3 nur auf Makro-Trigger oder Codewort.

| Stufe | Scope | FX-Regel | Research-Trigger |
|-------|-------|----------|------------------|
| **1 Kerneuropa** | Xetra, Euronext, LSE, SIX, Borsa/BME, Nordics — DAX/MDAX/SDAX/Scale, große EU/UK/CH-Werte | EUR-direkt bevorzugt; GBP/CHF/SEK/DKK per Quanto erlaubt | Default in jedem News/Hidden/Insider-Scan |
| **2 Nordamerika** | NYSE, Nasdaq, US-ETF-Komplex + Asia-ADRs (TSM, BABA, TM, SONY, etc.) | USD per Quanto Default; Non-Quanto nur ≤10d (Lektion 1) | Automatischer Fallback wenn Stufe 1 < 2 reife Kandidaten; oder US-Makro-Thema aus Makro-Check |
| **3 Asia-Makro-Indizes** | Nikkei 225, Hang Seng (evtl. TOPIX falls Produkt verfügbar) — **keine Einzelwerte** | JPY/HKD per Quanto Pflicht (Gap-Risiko) | Nur bei explizitem Makro-Trigger (BoJ/PBoC-Event, Japan-Rally, HK-Bodenbildung) oder Codewort „Asien-Scan" |

**Produktverfügbarkeits-Vorstufe bei Stufe 2/3:** Bevor ein Nicht-EUR-Kandidat in die volle 7/7-Checkliste geht, Quick-Check — Quanto-KO auf Gettex/SB+ verfügbar? Spread akzeptabel? Wenn nein → Alternative (Sektor-ETF-KO, Direktaktie) oder SKIP. Details: `references/produktkenntnis.md` § 3a.

### Serendipity-Regel

Wenn beim **Makro-Check, Morgen-Briefing oder TP/SL-Analyse** ein Trade-Kandidat sichtbar wird — auch ohne News-/Hidden-Scan-Codewort — wird er proaktiv genannt. Zwei Ausprägungen:

- **Stufe 1 / Primäruniversum:** Voller Kandidaten-Eintrag mit Vorcheckliste (wie News-Scan-Output).
- **Stufe 2 / Stufe 3 (bei aktivem Makro-Thema):** **3-Zeilen-Micro-Pitch** — Underlying, These, grober Chart-Zustand + Produktverfügbarkeit ja/nein. User entscheidet, ob Vertiefung zur vollen Checkliste.

Stufe 3 nimmt am Serendipity-Mechanismus **nur** teil, wenn der Makro-Check aktiv ein Asien-Thema adressiert — sonst schweigt sie.

**Micro-Pitch-Format:**
```
💡 [Stufe 2|3] — [Name, Ticker]: [Long|Short]
These: [1 Satz, was bewegt es]
Chart/Produkt: [30d-Move, 52W-Abstand grob] | Quanto-KO: ✅/❌/❓
```

## Makro-Analyse-Workflow

Bei „Makro-Check"/„Nachrichtenlage": (1) Websuche 3–5 Queries — Geopolitik/Branche/Analysten, (2) Einordnung: Eskalation/Deeskalation/Status quo, (3) Auswirkung auf Positionen, (4) Handlungsempfehlung, (5) Neue Chancen → **Serendipity-Regel anwenden** (Micro-Pitch für Stufe-2/3-Kandidaten, voller Eintrag für Stufe 1). Suchtiefe vorher ansagen (Regel 18).

**US-Indikatoren im Detail-Briefing** (im Kompakt-Briefing nur 1 Zeile wenn auffällig):
- VIX (CBOE) — US-Pendant zu VDAX-NEW, Schwellen ähnlich (< 15 Euphorie, > 28 Stress)
- DXY (Dollar-Index) — Richtung USD gegen Majors; relevant für Non-Quanto-Entscheidung (Lektion 1)
- S&P 500 Indikation (vor Xetra-Open relevant, nach Xetra-Close für ADR-Exposure)
- Fed-Event-Kalender (FOMC, NFP, CPI) — wenn in ≤ 5 Tagen, als Event-Risiko gegen Stufe-2-Positionen prüfen

## Screenshot-Analyse (Trade Republic / Smartbroker+)

User schickt Screenshots von: Zertifikats-Detailseite, Derivate-Liste, Order-Bestätigung, Portfolio. Bei jedem: Zahlen explizit nennen, Gegenrechnung machen (Kernformeln!), Plausibilität prüfen.

## Journal-Workflow (Excel/openpyxl)

Journal ist `Trading_Journal_YYYYMMDD.xlsx` — User lädt aktuelle Version am Chat-Start hoch, Claude gibt mit neuem Datum im Dateinamen zurück.

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
| **7** Morgen-Briefing | „Morgen-Briefing", „Tagescheck" — proaktiv bei offenen Positionen | Vor Start: Kompakt (1–2 Suchen) oder Detail (4–6)? **Kompakt:** DAX-Indikation + Positionen-Ampel + Events + 1-Satz-Empfehlung. **Detail:** + News/Sektor/RSI/EMA + **Watchlist-Block (Pflicht, siehe Abschnitt „Watchlist-Abgleich")**. Sentiment-Block (VDAX/PCR/EUWAX) am Ende wenn User Werte liefert. |
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
| 7 Briefing | „Briefing bitte" | Detailformat? |
| 8/8b/8c | Codewort | — |

## Watchlist-Abgleich (Pflicht bei Morgen-Briefing & Kandidaten-Scans)

Die Watchlist (Sheet „Watchlist") enthält bereits durchdachte Setups mit definierten Triggern. Kandidaten, die darauf stehen, sind **keine neuen Kandidaten** — sie haben einen Plan, der entweder gerade getriggert wird oder weiter wartet. Deshalb:

### Routine 7 — Watchlist-Block im Detail-Briefing (Pflicht)

Im **Detail-Briefing** wird vor dem Kandidaten-Output ein Watchlist-Block erzeugt. Für jede Zeile der Watchlist:

| Status-Zeichen | Bedeutung | Aktion im Briefing |
|----------------|-----------|--------------------|
| 🟢 Trigger JETZT erreicht | Einstiegskriterium gerade erfüllt | Volle 7/7-Checkliste sofort starten |
| 🟡 Kurz vor Trigger | Annäherung an Entry-Zone (z.B. ≤ 3% vom Trigger-Kurs, oder Datum ≤ 2 Tage) | Alarm benennen, Checkliste vorbereiten |
| ⏸ Warten | Weder Kurs- noch Datumstrigger erreicht | 1-Zeiler-Status + Hinweis auf nächsten Trigger |
| ❌ Invalidiert | These durch neue Info gedreht oder Kurs-Invalidierung erreicht | Vorschlag: von Watchlist entfernen via `ju.remove_watchlist(...)` |

Datengrundlage: `ju.list_watchlist(wb)` liefert alle Einträge als Liste von Dicts.

### Routinen 8 / 8b / 8c — Watchlist-Pflicht-Abgleich

Jeder Kandidat aus News-Scan, Hidden Catalyst Scan oder Insider-Scan wird **vor** dem Output gegen die Watchlist abgeglichen. Code-seitig:

```python
match = ju.match_watchlist(wb, kandidat_name_oder_ticker)
if match:
    # NICHT als "neuer Kandidat" ausgeben — stattdessen:
    # "[BEREITS AUF WATCHLIST — Trigger: …, Status: …]"
```

Der Match-Algorithmus ist token-basiert (trifft Aktienname UND Kürzel wie `AIXA`, `EUZ`, `GV6`, wenn diese im Watchlist-Feld als Klammerzusatz vorhanden sind). Details und Testfälle: `references/journal-utils-api.md` § Watchlist.

**Output-Regel bei Watchlist-Match:** Kandidat wird **nicht** als neue Idee präsentiert. Stattdessen: Statuszeile „BEREITS AUF WATCHLIST seit {Datum} — Richtung: {Long/Short} — Trigger: {…} — aktueller Status: {…}" — und **nur dann** volle Checkliste, wenn der Trigger jetzt tatsächlich erreicht ist (dann aber mit Verweis „Watchlist-Trigger hit, nicht News-Scan-Trigger").

## Wichtige Warnsignale (proaktiv ansprechen)

- Position offen > 2 Wochen bei Open-End KO → Finanzierungskosten-Warnung
- Alle Positionen in dieselbe Richtung → Korrelationswarnung
- SL nicht gesetzt → sofort nachfragen
- Hebel > 7× → Risiko explizit betonen
- Trade nach > 15%-Move → Late-Entry-Warnung
- Earnings/Events in ≤ 5 Tagen → Positionsreduzierung empfehlen
- Sizing > 2% Risikokapital → sofort warnen
- ≥ 3 Positionen gleiche These/Richtung → als einen Risikoblock behandeln
- Chat-Start mit offenen Positionen → Morgen-Briefing anbieten
- So/Mo, vor Earnings, nach > 3% Move → TP/SL-Analyse anbieten

## Referenz-Dateien

| Datei | Laden wenn... |
|-------|---------------|
| `journal_utils.py` | Das Helper-Modul — wird per `import journal_utils as ju` eingebunden (siehe Journal-Workflow oben). Direkt anfassen nur, wenn das Journal-Layout sich ändert und das Modul nachgezogen werden muss. |
| `references/journal-utils-api.md` | API-Referenz des Moduls — vollständige Funktionsliste inkl. Notes-API, typische Workflows (Routine 1/1a/2/partial/Watchlist/Notes), Konstanten-Tabelle. |
| `references/trade-plan-templates.md` | Trade-Plan benötigt (Routine 1b, neue Position planen). KO-Template + Direktaktien-Template. |
| `references/journal-layout.md` | Detail-Fragen zu Sheet-Spalten, Saldo-Zeilen-Struktur, Formatting-Standards, Zellenfarben, Zebra-Streifen. |
| `references/news-scan.md` | News-Scan / Hidden Scan / Insider-Verkäufe — **SOFORT laden** bei Codewort, dann Routine ausführen. |
| `references/technische-analyse.md` | Fragen zu Indikatoren, Chart-Analyse, TradingView-Setup, Candlestick-Patterns, oder Chart-Abgleich im Makro-Workflow. |
| `references/produktkenntnis.md` | Ordertypen, Broker-Vergleich, **Zertifikat-Auswahl**, CFDs, Optionen, Kelly, Position-Sizing-Vertiefung, TR/SB+-Limitierungen. |

## Versioning-Konvention

Output-Dateien tragen das Datum des Updates im Dateinamen: `Trading_Journal_YYYYMMDD.xlsx` (z.B. `Trading_Journal_20260422.xlsx`). Alle State-Infos (TODOs, Milestones, ⚠️) leben im Journal-Sheet „Notes" selbst — keine externe STATE-Datei mehr. Kein semantisches Versioning (keine `1.x.x`-Nummern).
