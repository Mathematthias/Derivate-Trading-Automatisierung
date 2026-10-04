# Pipeline-Architektur — zweistufige Filter-Engine

**Stand:** 2026-04-25, V0.2

## Das Problem, das gelöst wird

Die Routinen (V1.5) schlagen täglich Kandidaten vor — die fast nie den
Chart-Test bestehen. Ursache: Die Routine sieht nur News + Kursbewegung
und labelt News-Mover als "Kandidaten", ohne Setup-Validierung.

Die Pipeline ändert das fundamental:
- Stufe 1 prüft DEINE konkreten Watchlist-Trigger gegen Live-Daten —
  keine Setup-Erfindung mehr.
- Stufe 2 sucht systematisch im Universe nach Setups, die deine
  Filter-Kriterien erfüllen — nicht nach News.

## Datenfluss

```
   STATE-Doc                tickers_tier_a.yaml
   (Watchlist mit              (Indizes/
    Triggern)                    Rohstoffe/
       │                         Krypto/
       │                         Positionen)
       │                            │
       ▼                            ▼
   ┌────────────────────────────────────────┐
   │      marketdata_sync.py                │
   │      (GitHub Action, alle 30 Min)      │
   │                                        │
   │   1. yfinance-Pull (Batch)             │
   │   2. Indikatoren-Berechnung            │
   │      (EMA20/50/200, RSI, ATR,          │
   │       30d-Move, 52W-Range)             │
   │                                        │
   │   3. Stufe 1: Watchlist-Trigger-Check  │
   │      → für jeden STATE-Watchlist-Wert  │
   │        wird Trigger-Status berechnet   │
   │                                        │
   │   4. Stufe 2: Universe-Setup-Filter    │
   │      → für nicht-Watchlist-Werte       │
   │        werden Setup-Buckets geprüft    │
   │                                        │
   │   5. Schreibt 2 Dateien in Drive:      │
   │      MARKETDATA-FULL-{datetime}.md     │
   │      CANDIDATES-{datetime}.md          │
   └────────────────────────────────────────┘
                  │
                  ▼
   ┌────────────────────────────────────────┐
   │  Routinen V1.6  +  Chat-Sessions       │
   │                                        │
   │  Lesen CANDIDATES.md zu Beginn         │
   │  → Setup-Klassifikation auf            │
   │    sauberen Daten, nicht Web-Suchen    │
   └────────────────────────────────────────┘
```

## Stufe 1 — Watchlist-Trigger-Check (Kern-Edge)

**Input:** Watchlist-Tabelle aus STATE-Doc Sektion 2.

**Was passiert pro Watchlist-Wert:**

1. Ticker aus Symbol-Spalte → yfinance-Lookup (Kurs, Volumen, Indikatoren).
2. Trigger-Spalte parsen:
   - Preis-Korridore extrahieren ("33,40–33,60€")
   - Indikator-Bezüge ("EMA50", "RSI<60")
   - Modifikatoren (`+ Bounce`, `+ Reversal`, `Vol ≥30D-Ø`)
   - Datum-Constraints ("nach 2026-04-30")
3. Status-Berechnung:
   - **In-Zone:** Kurs IN der Trigger-Zone
   - **Sehr nah:** ≤2% vor/nach
   - **Nah:** ≤5%
   - **Beobachten:** ≤10%
   - **Passive:** >10% entfernt
4. Bei Modifikatoren wie `+ Bounce`: prüfen ob letzte Daily-Kerze
   Bounce-Charakteristik hat (untere Wick ≥30%, Close > Open).
5. Bei Datum-Constraints: vor Datum → Status `pending`.

**Output:** Sortierte Liste der Watchlist-Werte nach Trigger-Nähe,
mit Status pro Trigger A und B.

**Beispiel-Output:**
```
## WATCHLIST-STATUS (Stufe 1)

### Trigger sehr nah / aktiv
- CBK.DE  (Long, Trigger A): in Zone 33,40–33,60€ — aktuell 33,52€ (IN-ZONE)
  Bounce-Validierung: Lower Wick 38%, Close > Open ✓
  → Setup BEREIT, Chart-Validierung empfohlen

- ENR.DE  (Long, Trigger A): nahe EMA20 167€ — aktuell 168,40€ (+0.8%)
  Bounce: noch nicht eingetreten (Close < Open)
  RSI 58 (<60 ✓)
  → BEOBACHTEN, abwarten auf Bounce-Bestätigung

### Trigger pending (Datum nicht erreicht)
- DRW3.DE: Trigger nach 2026-04-30 (in 5 Tagen)
- AIXA.DE: Trigger nach 2026-04-30, Pre-Trade 2026-04-28

### Trigger passive (>10% entfernt)
- INTC: Pullback ~59$ (aktuell 82,55$) — Distanz +40%, INVALIDIERT
  Empfehlung: Watchlist-Eintrag entfernen oder Trigger neu definieren
```

## Stufe 2 — Universe-Setup-Filter (für neue Kandidaten)

**Input:** Tier-A-Universe minus Watchlist-Werte.
Aktuell ~30 Ticker, später ~150 (geplante Erweiterung um Index-Komponenten).

**Pro Ticker werden geprüft:**

1. **Universal-Disqualifier:**
   - Liquidität: 20d-Avg-Volumen × Kurs ≥ 1M EUR
   - ATR-Deckel: ATR14/Kurs ≤ 8 %
   - Earnings: keine Quartalszahlen in den naechsten 7 Tagen
     (`earnings_blackout_days`; bis 2026-10-04 stand der Schluessel in der
     Config, wurde aber im Code nicht gelesen — seit dem Review aktiv)
   - 30d-Move: |move| > 15 % ist KEIN Ausschluss mehr, sondern Flag
     `late_entry` (⚠️REIFE im Summary, `sizing_hint: floor_1pct` im Pitch)

2. **Setup-Bucket-Klassifikation** (siehe filter_config.yaml für Schwellwerte):
   - Long-Trend-Pullback (Anker EMA20; EMA200-MeanRev ist dieselbe Klasse mit Anker EMA200)
   - Breakout-Retest Long (seit 2026-10-04: bestaetigter Ausbruch ≤10 HT zurueck,
     Vol ≥1,2×, Kurs im Retest-Band Niveau −0,5/+0,75 ATR; kein nackter Ausbruch mehr)
   - Short-Trend-Pullback (Ex-Dividende ≤14 Tage blockt)
   - Breakdown-Retest Short (Spiegel)
   - Reversal Long/Short: Bucket existiert, Klasse ist seit 2026-10-04
     GESTRICHEN (Review) — Treffer werden nicht gehandelt

3. **Pro Bucket maximal 5 Treffer**, sortiert nach Setup-Stärke
   (Bucket-spezifische Heuristik, z.B. Trigger-Nähe oder Volumen-Multiplier).

**Output-Beispiel:**
```
## NEW-CANDIDATES (Stufe 2)

### Long-Trend-Pullback
- HEN3.DE: 91,40€  EMA20=90,80  Distanz +0,7%  RSI=52  30d:+8%
- VOW3.DE: 102,30€ EMA20=101,80 Distanz +0,5%  RSI=48  30d:+11%

### Breakout Long
(heute keiner)

### Short-Trend-Pullback
- KGX.DE: 32,40€  EMA20=33,10  Distanz -2,1%  RSI=42  30d:-9%

### Reversal Long
(heute keiner)

### DISQUALIFIZIERT (kurze Gründe-Zusammenfassung)
- 18 Ticker durch Liquidität, 4 durch Earnings-Blackout,
  6 durch Trend-Bruch, ... (30d-Move ist seit 2026-10-04 nur noch Flag)
```

## Watchlist-Lifecycle-Mechanik

Seit 2026-10-04 (Workflow B) lebt die Watchlist in `state/watchlist.yaml`.
Jeder Eintrag traegt `status`, `klasse`, `anker` und bis zu drei Legs mit
Gate (🟢 scharf / 🟡 beobachten / ⏳ wartet / 🔴 tot) und Trigger-Text in der
unveraenderten Grammatik, die `state_parser._parse_triggers` versteht.

| Status | Pipeline-Verhalten |
|--------|--------------------|
| `aktiv` | Stufe-1-Check je Leg nach Gate; Symbol ist in jedem Tier Teil des Pulls |
| `position` | wie aktiv, Gate A ist 📍 (Position-Monitor, Exit-Regeln im Trigger-Text) |
| `archiviert` | alle Legs werden als 🔴 behandelt: Stufe 1 ueberspringt, Stufe 2 darf das Symbol wieder aufnehmen; `archived.date/reason` dokumentieren den Grund |

Verfall (`expiry`) und fruehestes Datum (`nach JJJJ-MM-TT` im Trigger-Text)
wirken wie bisher. Die alten STATE-Doc-Status (📅 pending, ⏸ paused,
🔍 beobachten ...) sind in den Gates aufgegangen.

**Aenderungen** kommen auf zwei Wegen in die Datei: Commit (Mensch) oder
INBOX-Aktion (Automat: `watchlist.set_status`, `set_gate`, `set_expiry`,
`set_field`, `add`; `radar.*`; `thesen.update`; `note.add`), angewendet von
`inbox_apply.yml`. Jede Aktion ist idempotent, jede INBOX-Datei wird genau
einmal verarbeitet (`state/inbox_processed.json`).

**Tuning-Quelle Archiv:** Quartalsweise die `archiviert`-Eintraege nach
`archived.reason` gruppieren. Uebergewicht eines Grundes deutet auf
systemische Schwaeche im aktuellen Filter-/Trigger-Setup hin.

## Stufe 1 vs Stufe 2 — Wichtiger Unterschied

| Aspekt | Stufe 1 (Watchlist) | Stufe 2 (Universe) |
|--------|---------------------|---------------------|
| Eingabe | DEINE Trigger aus `state/watchlist.yaml` | Generische Setup-Filter |
| Setup-Erkennung | Match gegen konkrete Spez | Heuristik aus Indikatoren |
| Falsch-Treffer-Risiko | gering (deine Trigger) | mittel (generisch) |
| Trade-Bereitschaft | hoch (du hast schon validiert) | brauchst Chart-Check |
| Veränderung | du pflegst `state/watchlist.yaml` (Commit/INBOX) | nur durch Tuning filter_config.yaml |

## Tuning-Strategie

Die Pipeline ist **bewusst konservativ in den Defaults**. Erste Wochen-Praxis
zeigt, ob die Schwellwerte zu eng oder zu locker sind.

**Beobachten:**
- Wie viele Treffer pro Bucket täglich? Wenn dauerhaft 0 → Schwellwerte
  zu eng. Wenn dauerhaft 5+ → zu locker.
- Wie viele Stufe-2-Treffer bestehen den Chart-Test? Wenn <30%, Filter
  ist zu naiv — Indikator-Ergänzung erwägen.
- Wie viele Stufe-1-Trigger werden tatsächlich aktiv? Wenn dauerhaft 0,
  vielleicht sind deine Trigger zu eng definiert oder Watchlist-Pflege
  hinterherhängend.

**Anpassen via filter_config.yaml** — kein Code-Push nötig, nur Repo-Push
und nächster Action-Lauf zieht Änderungen.

## Was die Pipeline NICHT kann

Ehrlich für Erwartungsmanagement:

- **Pre-Market-US-Live-Kurse** — yfinance verzögert 15-20 Min
- **Optionen-Chain / IV** — andere Datenquelle nötig (kein Roadmap-Slot definiert)
- **Insider-Käufe DE** — yfinance lückenhaft, BaFin-Scrape geplant für Build-Schritt 1.6
- **News-Sentiment** — bleibt Aufgabe der Routinen via web_search
- **Chart-Pattern-Erkennung** — Pipeline rechnet Indikatoren, erkennt aber
  keine Wedge/Flagge/Double-Top. Das bleibt deine Chart-Disziplin.

Die Pipeline ist **Daten-Filter**, nicht **Chart-Analyst**. Der Wert liegt
in der Trefferquote der Vorauswahl, nicht in vollständiger Trade-Generierung.
