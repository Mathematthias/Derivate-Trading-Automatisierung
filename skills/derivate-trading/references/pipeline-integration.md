# Pipeline-Integration — Referenz für Routinen 7 / 8 / 8b / 8c

**Diese Datei wird geladen bei:**
- Jedem Lauf von Routine 7 (Morgen-Briefing)
- Jedem Lauf von Routine 8 / 8b / 8c (News-/Hidden-/Insider-Scan)
- Jeder Frage zur MARKETDATA- oder CANDIDATES-Pipeline

**Ziel:** Die drei Routinen lesen ihre Markt- und Watchlist-Daten **primär** aus drei Markdown-Files im Workspace Shared Drive — nicht mehr aus Web-Snippets. Die Pipeline (GitHub Action) hat Indikatoren, Trigger-Status und Setup-Kandidaten bereits zentral berechnet; die Routinen verbrauchen nur noch.

**Stand:** Phase 4 produktiv seit 2026-04-26.

---

## Architektur in einem Satz

```
GitHub Action  →  Workspace Drive  →  Drive-Connector  →  pipeline_utils.py  →  Routine
   (yfinance)     (timestamped MD)      (read_file)        (parse + frische)    (Briefing)
```

Bei Pipeline-Ausfall (Drive nicht erreichbar oder File >24h alt) → Fallback auf bisherige Web-Logik wie vor Phase 4.

---

## Watchlist-Sync: Trading-Journal als Single Source of Truth

**Stand:** Aktiv seit 2026-04-29.

Die Watchlist wird **nicht mehr im STATE-Doc gepflegt**, sondern im Trading-Journal Excel (`Trading_Journal_*.xlsx`, Sheet "Watchlist"). Die Pipeline syncht den Watchlist-Block bei jedem Tier-A-Lauf (alle 30 Min) automatisch ins STATE-Doc — manuelle Edits am STATE-Watchlist-Block werden überschrieben.

### Datenfluss

```
Excel-Watchlist-Sheet  →  Drive-Upload (manuell oder via Drive Desktop)
                              ↓
Tier-A-Action-Runner: src/watchlist_sync.py (Pre-Step vor marketdata_sync.py)
   1. find_latest_journal()      → jüngstes Trading_Journal_*.xlsx
   2. read_journal_watchlist()   → Excel-Zeilen → Dicts
   3. read_state_doc()           → STATE-Doc-Inhalt
   4. render_watchlist_block()   → neuer Markdown-Block
   5. replace_watchlist_block()  → nur Watchlist-Sektion ersetzt
   6. write_state_doc()          → files().update() auf STATE-Doc
                              ↓
marketdata_sync.py liest STATE wie gewohnt — Watchlist ist jetzt frisch
```

### Excel-Format (Pflichtspalten)

| Aktie | **Symbol** | Richtung | Entry-Trigger | These | Status | Datum hinzugefügt |

- **Symbol** ist Pflicht (Yahoo-Symbol, z.B. `CBK.DE`, `AAPL`). Ohne Symbol wird die Zeile geskippt mit Warnung.
- **Status** wird über das erste Emoji erkannt:
  - `⚠️` → `aktiv` (Pipeline meldet täglich)
  - `📅` → `pending` (Datum aus Status wird extrahiert ins ISO-Format)
  - `⏸` → `paused`
  - `👀` / `🔍` → `beobachten`
  - kein Emoji → default `aktiv`
- **Trigger** wird auf 120 Zeichen gekürzt; bei A)/B)-Multi-Triggern nur A) gezeigt mit `· (B) ...`-Hinweis.

### Trigger-Syntax — was der Parser versteht (Stand 2026-05-13)

Der Trigger-Parser (`state_parser.py`) versucht, die freie Trigger-Beschreibung in
strukturierte Bedingungen zu zerlegen. Damit das zuverlässig klappt, sind ein paar
Konventionen wichtig — Trigger, die diese verletzen, landen entweder gar nicht oder
falsch in der Pipeline.

**Mehrere Trigger auseinanderhalten — Label-Marker:**

| Form | Beispiel | Funktioniert? |
|------|----------|---------------|
| `A) ... B) ...` | "A) Daily-Close <60€ … B) Daily-Close <58€" | ✓ |
| `A: ... · B: ...` | "A: Touch EMA50 33–34€ · B: Daily-Close >35€" | ✓ |
| `Trigger A: ...` | "Trigger A: 4h-Bearish-Engulfing …" | ✓ |
| `A) ... ODER ... ` | "A) ~240€ ODER ~237€" | ✗ — nur erster Preis wird genommen. Splitten in A und B. |
| Kein Label | "Daily-Close >50€ + Vol ≥30D-Ø" | ✓ (1 Trigger ohne Label) |

Label-Whitelist ist A–E. "R:R 1,2" wird **nicht** als Label gelesen
(Konstrukt `R:R` hat kein Whitespace nach dem ersten `:`).

**Preis-Operatoren:**

| Form | Beispiel | Bedeutung |
|------|----------|-----------|
| Range mit `–` oder `-` und Currency hinten | `33,40–33,60€`, `1.720-1.789$` | `in_range` |
| Single mit Operator | `>35,10€`, `<58,00$`, `≥25,70€`, `≤60€` | `>`/`<` |
| Approx mit Tilde | `~167€`, `~5,17€` | `approx` (±2% Toleranz) |
| Punkt-Touch (Touch-Wort + Preis) | `Daily-Touch 52,33$`, `Touch EMA50 ~240€` | `approx` + `is_touch=True` |

**Was nicht erkannt wird** (vermeiden):
- Currency **vor** der Zahl in Range: `$1.720–$1.789` → wird nicht gematcht.
  Reformulieren zu `1.720-1.789$` (Currency hinten).
- Range mit Punkten/Tausendertrennung im englischen Stil ohne Kontextzeichen
  → `_parse_eu_number` versucht die Heuristik, aber bei `1.720` braucht es
  genau 3 Nachkommastellen, damit es als Tausender erkannt wird.

**SL/TP/R:R-Komponenten im Trigger-Text:**

Sind unschädlich — der Parser strippt vor dem Preis-Matching:
- `SL <370$`, `SL <235€`, `SL X%`
- `TP1 392$`, `TP2 404$`, `TP 50€`
- `R:R 1,2 / 2,4`, `R:R ~2,5`, `R:R primär 1,8`
- ATR-Hinweise wie `-1,2ATR`

Heißt: `"Daily-Close >380$. SL <370$. TP1 392$"` wird korrekt als `price_op=">", price_single=380` geparst, nicht als `<370`.

**Volumen-Bedingungen — was matcht:**

| Form | Vol-Multiplier |
|------|----------------|
| `Vol ≥30D-Ø`, `auf Vol ≥30D-Ø` | Default aus Config (1.0) |
| `Vol >Avg-30d`, `Volumen >Avg-20d` | Default (1.0) |
| `Volumen ≥ 1,2× Avg-20d`, `Vol ≥ 1,5× Avg` | aus Trigger (1.2 bzw. 1.5) |
| `Volumen ≥ 0,9× Avg` | aus Trigger (0.9) |

Trigger-Multiplier überschreibt den Config-Default. Wert wird auch in der
Pending/Failed-Meldung angezeigt (`Vol 0.7× < 1.20×`).

**Modifikatoren weiterer Art:**

| Form | Effekt |
|------|--------|
| `+ Bounce`, `+ Reversal`, `+ Stabilisierung` | `require_bounce=True` |
| `Hammer`, `Reverse-Close`, `Hammer/Reverse-Close` | `require_hammer=True` |
| `RSI 1D <35`, `RSI Daily <70` | `rsi_max=35` bzw. 70 |
| `RSI >55`, `RSI 1D >55` | `rsi_min=55` |
| `EMA20`, `EMA50`, `EMA100`, `EMA200` | `ema_ref=...` (informational) |

**Zonen-Semantik-Tags** (Task 5, seit 2026-05-22):

Trigger-Zonen tragen einen Typ-Tag in eckigen Klammern direkt hinter dem Range.
Er steuert, wie der Evaluator den Bereich *jenseits* der Zone liest:

| Tag | `zone_kind` | Kurs außerhalb der Zone |
|-----|-------------|-------------------------|
| `[breakout]` | `breakout` | LONG: über Obergrenze → **durchgelaufen** (Chase-Cap überschritten, `proximity=far`, Summary „📛 DURCHGELAUFEN"). SHORT: unter Untergrenze → durchgelaufen. |
| `[pullback]` | `pullback` | außerhalb der Zone → legitimes Warten, kein Durchgelaufen-Flag. |
| (kein Tag) | `None` | Heuristik-Fallback, sonst Alt-Verhalten (kein Durchgelaufen-Check). |

- Position: hinter dem Range, vor weiteren Bedingungen — `Daily-Close 411-415$ [breakout] + Vol >Avg-20d`. `-zone`-Suffix erlaubt (`[breakout-zone]`).
- **Breakout-/Breakdown-Zonen brauchen den Tag.** Ohne ihn bemerkt der Parser das Durchlaufen nicht — die Zone bliebe „BEREIT", auch wenn der Kurs längst über den Chase-Cap gelaufen ist.
- Ohne Tag greift eine **Heuristik** auf den Trigger-Text: „Breakout"/„Ausbruch" → `breakout`, „Pullback"/„Touch"/„Rücksetzer" → `pullback`. Nur bei Eindeutigkeit — beide oder keines → `None`. Der explizite Tag hat Vorrang und ist die sichere Variante.
- **Konvention für die Zonen-Grenze in Trend-Richtung (Breakout: Obergrenze, Breakdown: Untergrenze) — korrigiert 2026-05-22:** Diese Grenze ist ein **ATR-basierter Chase-Cap**: Trigger ± ~1–1,5×ATR(14) — NICHT ein R:R-1,35-Kipppunkt.
  - *Warum nicht R:R-Kipp:* Der R:R-Kipp setzt einen **fixen** SL voraus. Bei Breakout-/Breakdown-Setups ist der Entry-Preis aber = wo der Schluss landet, nicht vorab bekannt — der SL gehört **entry-relativ** definiert (LONG: Entry − 1,5×ATR; SHORT: Entry + 1,5×ATR). Mit entry-relativem SL ist R:R über alle Entry-Preise konstant; es gibt gar keinen festen Kipp. Ein kipp-basierter Zonen-Rand fällt je nach R:R-Höhe mal extrem schmal aus (<1×ATR) → ein normaler Breakout-Tag schließt in einer Kerze jenseits der Zone → **Fehl-DURCHGELAUFEN** auf einem Setup, das mit nachgezogenem SL noch handelbar wäre.
  - *Abgrenzung `[pullback]` — korrigiert 22.05.2026 (Lektion-4-Audit, Note #92):* Der entry-relative SL gilt NICHT nur für `[breakout]`. Auch `[pullback]`-Zonen brauchen ihn, sobald die Zone breiter als ~0,5×ATR ist — über eine breite Zone variiert der Fix-SL-Abstand, an der ungünstigen Zonenkante (LONG: Untergrenze) wird er zu eng. Fixer SL ist nur bei sehr schmaler Pullback-Zone (≤~0,5×ATR) korrekt. Der Chase-Cap als Zonen-Obergrenze bleibt `[breakout]`-spezifisch; der entry-relative SL gilt für beide Tag-Typen.
  - *Bedeutung der DURCHGELAUFEN-Flagge:* von „R:R-1,35 gerissen" → „Kurs > ~1×ATR über/unter den Trigger gelaufen = Chase, kein Einstieg mehr".
  - *SL-Konformitätscheck (statt reiner Mindestbreite):* Vor dem Anlegen jedes Zonen-Triggers — `[breakout]` wie `[pullback]` — den SL-Abstand ÷ ATR(14) an der für die Richtung ungünstigen Zonenkante rechnen. < 1,5×ATR = Lektion-4-Verstoß → SL entry-relativ formulieren. Die frühere Heuristik „Zonenbreite < 1×ATR" fängt nur einen Teil der Fälle (eine breite Zone kann trotzdem einen zu engen Fix-SL haben — Befund CHKP-A 22.05.2026: Zone 1,11×ATR, Fix-SL 0,93×ATR an der Untergrenze).
  - Hintergrund: Journal-Notes #88/#89 (2026-05-22), SKILL.md Lektion 17.

**Was die Pipeline NICHT parst** (manuell pre-trade prüfen):
- Liquiditäts-Bedingungen wie `Gettex-Liquidität ≥ 30k Stk Avg/Tag`
- Datums-Bedingungen außer ISO `YYYY-MM-DD`: `Nach Earnings 12.05.2026` →
  reformulieren zu `nach 2026-05-12` damit `earliest_date` gesetzt wird, oder
  als manuelle Pre-Trade-Bedingung führen.
- Mehrere konkurrierende Preis-Punkte mit `ODER` im selben Trigger →
  in zwei separate Trigger A) und B) splitten.

### STATE-Doc-Verhalten

Die Watchlist-Sektion im STATE-Doc enthält jetzt einen Auto-Sync-Hinweis:

```
> **AUTO-SYNC:** Diese Tabelle wird bei jedem Tier-A-Lauf (alle 30 Min) aus
> dem Watchlist-Sheet des Trading-Journals neu generiert. Manuelle Edits
> hier werden überschrieben — bitte Watchlist im Journal pflegen.

> _Auto-Sync zuletzt: YYYY-MM-DD HH:MM UTC (N Einträge)_
```

Andere STATE-Sektionen (Offene Positionen, Filter-Override, Notes, Pipeline-Status) bleiben **unverändert** und werden weiter manuell gepflegt — der Sync ersetzt nur den Watchlist-Block.

### Was der Trader tun muss

1. **Journal in den Workspace-Shared-Drive "Trading-Pipeline" hochladen.** Entweder manuell (nach Watchlist-Updates) oder via Drive Desktop (automatisch). Dateiname-Pattern `Trading_Journal_*.xlsx` — das jüngste wird genommen.
2. **Symbol-Spalte in der Excel-Watchlist pflegen.** Yahoo-Symbol, z.B. `CBK.DE`, `AAPL`, `BTC-EUR`. Ohne Symbol → Zeile übersprungen.
3. **Watchlist im Journal editieren**, nicht im STATE-Doc. STATE-Edits werden beim nächsten Tier-A-Lauf überschrieben.

### Failure-Modi

| Symptom | Vermutliche Ursache | Behandlung |
|---|---|---|
| Sync-Step fail mit `Kein Trading_Journal_*.xlsx im Drive gefunden` | Journal noch nicht hochgeladen oder im falschen Ordner | Journal in Trading-Pipeline-Drive hochladen |
| Sync-Step fail mit `Symbol-Spalte nicht gefunden` | Excel hat keine Symbol-Spalte | Spalte hinzufügen mit Yahoo-Tickern |
| Sync läuft, aber STATE-Doc unverändert | Excel und STATE waren schon identisch | Erwartetes Verhalten |
| Pipeline-Lauf zeigt alte Watchlist | `continue-on-error: true` hat einen stillen Fehler verschluckt | Action-Log prüfen, Step-Output anschauen |
| Doppelter Eintrag in STATE | Race Condition (zwei Sync-Läufe gleichzeitig) | Nicht kritisch, beim nächsten Lauf überschrieben |

### Warum `continue-on-error: true`

Der Watchlist-Sync ist **additiv**. Wenn er fehlschlägt (z.B. Journal nicht im Drive, Symbol-Spalte fehlt, Drive-API hakt), läuft der Hauptpipeline-Step `marketdata_sync.py` trotzdem mit der alten Watchlist aus dem STATE-Doc. Kein Komplettausfall — nur Daten möglicherweise nicht ganz frisch.

---

## Zwei MARKETDATA-Universen (seit Befund 2026-04-26)

Die Pipeline schreibt in der Praxis **mehrere MARKETDATA-FULL-Files mit unterschiedlichen Tickerlisten** in den Briefing-Ordner — vermutlich aus zwei separaten GitHub-Action-Pfaden:

| Universum | Inhalt | Relevant für |
|-----------|--------|--------------|
| **standard** | Indizes (^GDAXI, ^GSPC, ^IXIC, ^VIX, …), Major-Krypto (BTC-EUR, ETH-EUR, SOL-EUR, BNB-EUR, BAT-EUR), FX (EURUSD=X, …), Rohstoffe (GC=F, CL=F, …), **Watchlist-Aktien** (PG, CBK.DE, ATOSS, EVD.DE, …) | Routine 7 (Morgen-Briefing), Routine 8/8b/8c (Indikator-Lookup beim Watchlist-Abgleich) |
| **gamechanger** | Breiteres Wachstums-/Tech-Universum für Universe-Setup-Scan (ABNB, AMD, PLTR, ZS, NEM.DE, IONQ, SNOW, …) — KEINE Indizes, KEIN Krypto, KEIN FX | Quelle für GAMECHANGER-HUNT.md (dort schon vorausgewertet) |

**Konsequenz:** Das absolut jüngste MARKETDATA-File ist **nicht automatisch das richtige** für Routine 7. Wenn die Routine naiv "neueste mtime" nimmt, kann sie ins Gamechanger-Universum greifen und hat dann weder DAX noch BTC noch eine einzige Watchlist-Aktie — Briefing kaputt.

**Lösung — Filename-Tag (preferred, seit Action-Edit 2026-04-26):** Die GitHub-Action schreibt MARKETDATA-Files mit Universum-Tag im Filename:

| Universum | Filename-Schema |
|-----------|-----------------|
| standard | `MARKETDATA-FULL-STD-YYYY-MM-DD-HHMM.md` |
| gamechanger | `MARKETDATA-FULL-GC-YYYY-MM-DD-HHMM.md` |

`pipeline_utils.classify_universe(content, filename=...)` erkennt das Tag und returnt direkt — kein Content-Parse nötig. `select_latest_marketdata` nutzt das automatisch.

**Lösung — Sentinel-Heuristik (Fallback):** Wenn ein File ohne `-STD-`/`-GC-`-Tag im Briefing-Ordner liegt (z.B. Pre-Action-Edit-Files oder Pipeline-Bug), klassifiziert `classify_universe` anhand bekannter Sentinel-Ticker (`^GDAXI`, `BTC-EUR`, `EURUSD=X`, …). Damit bleiben Bestand und neue Files bruchfrei nutzbar.

**Offen / an Pipeline-Maintenance:**
- Soll die Pipeline am Wochenende überhaupt laufen? Aktien-Daten sind eingefroren (Fr-Schluss bis Mo-Open), nur Krypto bewegt sich — und ausgerechnet das Gamechanger-Universum (das Sa-Nacht oft als einziges frisch ist) hat KEIN Krypto.
- ~~File-Naming-Konvention um Universum erweitern~~ ✅ erledigt 2026-04-26.
- ~~GAMECHANGER-File-Header-Bug (`# CANDIDATES — …` statt `# GAMECHANGER — …`)~~ ✅ erledigt 2026-04-26.

---

## Drive-Workflow (Schritt-für-Schritt)

### Schritt 1 — Jüngste Files finden

Die Pipeline schreibt drei timestamped Files in den Briefing-Ordner:

- `MARKETDATA-FULL-YYYY-MM-DD-HHMM.md` — Indikator-Stack für ~47 Ticker
- `CANDIDATES-YYYY-MM-DD-HHMM.md` — Watchlist-Trigger-Status (Stufe 1)
- `GAMECHANGER-HUNT-YYYY-MM-DD-HHMM.md` — Setup-getriggerte Stufe-2-Kandidaten aus dem Universe-Scan

Jüngste Datei via `search_files` mit Title-Filter, sortiert nach `modifiedTime` (Drive-API liefert sortiert, aber zur Sicherheit clientseitig nach `modifiedTime` DESC sortieren):

```
search_files(query="title contains 'MARKETDATA-FULL' or title contains 'CANDIDATES' or title contains 'GAMECHANGER-HUNT'", pageSize=15)
```

Aus dem Ergebnis pro File-Typ den Eintrag mit dem höchsten `modifiedTime` nehmen → File-IDs `md_id`, `cand_id`, `gc_id` und Timestamps `md_mtime`, `cand_mtime`, `gc_mtime`.

**Achtung:** Der Title-Filter `title contains 'CANDIDATES'` matcht aktuell **auch** GAMECHANGER-HUNT-Files, weil deren File-Header `# CANDIDATES — ...` lautet (Pipeline-Cosmetic-Bug). Daher: streng über den **Filename** trennen, nicht über Header-Inhalt.

**Achtung MARKETDATA (seit Befund 2026-04-26):** Die jüngste MARKETDATA-Datei ist ggf. der **Gamechanger-Lauf** (anderes Universum, ohne Indizes/Krypto). Für Routine 7 muss das jüngste **Standard-Universum-File** gepickt werden — siehe Schritt 2 + Abschnitt „Zwei MARKETDATA-Universen" oben. Nimm hier alle MARKETDATA-Treffer aus search_files (nicht nur den jüngsten) und filtere im nächsten Schritt nach Universum.

### Schritt 2 — Inhalte lesen

Für CANDIDATES und GAMECHANGER (jeweils nur 1 File pro Typ relevant):

```
read_file_content(fileId=cand_id)  → cand_content (escaped Markdown)
read_file_content(fileId=gc_id)    → gc_content (escaped Markdown)
```

Für MARKETDATA: **alle** Treffer aus search_files laden (nicht nur den jüngsten), damit `select_latest_marketdata` zwischen Standard- und Gamechanger-Universum wählen kann:

```python
md_files = []
for f in marketdata_search_results:  # aus Schritt 1
    md_files.append({
        "id": f["id"],
        "title": f["title"],
        "modifiedTime": f["modifiedTime"],
        "content": read_file_content(fileId=f["id"]),
    })
```

In der Praxis reicht es, die jüngsten 3–5 MARKETDATA-Files zu laden — ältere sind selten relevant. Wenn man Tokens sparen will, erst die jüngsten 2 laden, klassifizieren, und nur bei `universe="unknown"` weiter zurücklaufen.

Hinweis zum Escaping: `read_file_content` liefert Markdown mit Backslash-Escapes (`\#\#`, `\*\*`, etc.). Die Parser in `pipeline_utils.py` (inkl. `classify_universe`) kümmern sich darum — kein manuelles Cleanup nötig.

### Schritt 3 — Universum wählen, Frische prüfen, parsen

```python
import sys; sys.path.insert(0, '/mnt/skills/user/derivate-trading')
import pipeline_utils as pu

ROUTINE = 'morning_check'  # oder 'scan_afternoon' / 'scan_evening'

# Standard-Universum picken (NICHT naiv den jüngsten nehmen)
md_pick = pu.select_latest_marketdata(md_files, universe="standard")
if md_pick is None:
    md_status = pu.freshness_status(None, ROUTINE)  # → 'missing'
    md_content = ""
else:
    md_content = md_pick["content"]
    md_status = pu.freshness_status(md_pick["modifiedTime"], ROUTINE)

cand_status = pu.freshness_status(cand_mtime, ROUTINE)
gc_status   = pu.freshness_status(gc_mtime, ROUTINE)

# Fallback-Entscheidung — Gamechanger ist additiv, nicht Pflicht
core_fallback = (md_status['status'] in ('ausfall', 'missing') or
                 cand_status['status'] in ('ausfall', 'missing'))

if not core_fallback:
    md   = pu.parse_marketdata(md_content)        # dict[ticker -> TickerData]
    snap = pu.parse_candidates(cand_content)      # PipelineSnapshot
    if gc_status['status'] not in ('ausfall', 'missing'):
        gc = pu.parse_gamechanger(gc_content)     # GamechangerSnapshot
    else:
        gc = pu.GamechangerSnapshot()             # leerer Snapshot

# Briefing-Header (leer wenn alles ok, 1–4 Zeilen sonst)
header = pu.render_freshness_header(md_status, cand_status, ROUTINE, gc_status=gc_status)
```

### Schritt 4 — Briefing rendern

Routinen-spezifisch — siehe SKILL.md (Routine 7) bzw. news-scan.md (Routine 8/8b/8c).

---

## File-Schemata

### MARKETDATA-FULL.md

```
# MARKETDATA-FULL — 2026-04-25 23:36 CEST

**Source:** yfinance | **Ticker erfolgreich:** 47

## TICKER1

- **Kurs:** 129.6 (-0.25%)
- **EMAs:** EMA20=130.7 · EMA50=131.5 · EMA200=119.7 [(bullish-Stack ↑) | (bearish-Stack ↓) | weglassen]
- **RSI-14:** 46.0
- **ATR-14:** 2.472
- **30d-Move:** +5.90%
- **52W-Range:** 89.29 – 149.1 (High-Distanz -13.05%, Low-Distanz +45.21%)
- **20d-Range:** 122.2 – 132.8
- **Volumen:** Avg-20d 189,832 Stk · 24,611,718 EUR (heute 0.31× avg)
- **EMA200-MeanRev:** Dist=-0.53% · LastTouch=215d · TrendQual=✓ · WeeklyHHHL=✓     ← seit 2026-05-08, Note #49
- **Earnings:** Next=2026-08-01 · Last=2026-05-06 (2d ago)                          ← seit 2026-05-08, optional (EARNINGS_PULL=1)

## TICKER2
...
```

**Universum (Stand 26.04.2026):** ~47 Ticker — DAX-Indizes (`^GDAXI`, `^MDAXI`, `^SDAXI`, `^TECDAX`, `^STOXX50E`), US-Indizes (`^GSPC`, `^IXIC`, `^DJI`, `^RUT`, `^VIX`), Asian (`^N225`, `^HSI`, `^FTSE`), Krypto (`BTC-EUR`, `ETH-EUR`, `SOL-EUR`, `BNB-EUR`, `BAT-EUR`), Rohstoffe (`GC=F`, `SI=F`, `CL=F`, `BZ=F`, `NG=F`, `HG=F`), FX (`EURUSD=X`, `EURGBP=X`, `USDJPY=X`), Watchlist-Aktien (PG, CBK.DE, SAN.PA, CRM, URI, JUN3.DE, LUV, INTC, ENR.DE, AIXA.DE, EUZ.DE, TUI1.DE, ADS.DE, DB1.DE, DRW3.DE, GV6.F, HDD.DE, EVD.DE, AOF.DE, AS, 4GLD.DE, …).

**Edge-Case Off-Universe:** Wenn ein News-/Insider-Scan einen Ticker außerhalb des Universums liefert (z.B. neuer SDAX-Wert), gibt `pu.get_ticker_data(md, ticker)` `None` zurück — die Routine macht **gezielte Web-Suche nur für diesen Ticker** und ergänzt die übrigen Indikatoren so.

**Neue Felder seit 2026-05-08 (Note #49 + Übergabe-Spec):**
- **EMA200-MeanRev-Zeile** wird für ALLE Symbole gerendert, sobald mind. eines der vier Felder gesetzt ist. Indizes/Krypto/FX zeigen die Zeile typischerweise nur teilweise (Trend-/Wochen-Kriterien greifen nur bei Aktien sauber). Felder: `Dist=±X.XX%` (= `(close − ema200) / ema200 × 100`), `LastTouch=Nd` (Handelstage seit letztem |close − ema200| ≤ 1×ATR), `TrendQual=✓/✗` (EMA200 steigend ≥80% der letzten 120 HT), `WeeklyHHHL=✓/✗` (höhere Hochs UND höhere Tiefs auf 26-Wochen-Fenster, Halbjahr-Heuristik).
- **Earnings-Zeile** wird nur gerendert, wenn die Pipeline mit `EARNINGS_PULL=1` läuft (Tier-A-Default seit 2026-05-08, Tier-B aus). Felder: `Next=YYYY-MM-DD` (nächster Earnings-Termin), `Last=YYYY-MM-DD (Nd ago)` (letzter Termin in HT zurück, näherungsweise via Kalendertage minus volle Wochenenden).

### CANDIDATES.md

```
# CANDIDATES — 2026-04-25 23:36 CEST

## Setup-Klassen-Flags                                ← seit 2026-05-08, beide Tiers

🎯 EMA200-MEANREV-CANDIDATE | TICKER | Distance -1.20% | LastTouch 215d | Trend ✓
📅 PEAD-WINDOW | TICKER | Earnings 2026-05-06 | 2d ago

## Stufe 1 — Watchlist-Trigger-Status

### 🎯 BEREIT — Trigger erfüllt, Chart-Validierung empfohlen

- **TICKER** (LONG/SHORT ↑↓) — Kurs X
  - [A] 🎯 BEREIT — alle Bedingungen erfüllt
  - _Note: …_
- **TICKER2** (LONG ↑) — Kurs X
  - [A] 🎯 BEREIT* — Preis & harte Conditions ok, offen: Vol 0.7× (Schwelle 1.20×) — Tagesvolumen noch offen
    ✓ Preis 381.20 > 380.00
    ✓ RSI 58.4 > 55
    ⏳ Vol 0.70× (Schwelle 1.20×) — Tagesvolumen noch offen

### 📍 Sehr nah am Trigger (≤2%)
- **TICKER** (DIR) — …

### Nah am Trigger (≤5%)
### Auf Radar (≤10%)
### 📅 Pending (Datum-Constraint)
- **TICKER** (DIR) — erst ab YYYY-MM-DD (Nd)
### ⏸ Paused (Bedingung temporär nicht da)
### 🔍 Passive (>10% entfernt)

## Stufe 2 — Neue Kandidaten aus Universe
(heute keine Treffer | Liste)

## Override-Werte (priority_long / priority_short)
- **TICKER** (↑↓) — Kurs X EMA20=… RSI=… 30d=…%
  - _Grund: …_

## Aktive Filter-Overrides
- **TICKER** [priority_long | priority_short | wait_for] — Begründung (gültig bis YYYY-MM-DD)
```

Die Pipeline hat den Trigger-Status der Watchlist bereits ausgewertet — die Routine muss **nicht** mehr selbst rechnen, ob ein Trigger getroffen wurde. Lediglich die Bucket-Information lesen und im Briefing rendern.

**BEREIT vs. BEREIT\* (seit 2026-05-13):** `BEREIT*` (mit Stern) signalisiert, dass Preis und alle harten Conditions (RSI, Bounce, Hammer, EMA-Bezug) erfüllt sind, aber das Tagesvolumen noch unter der Schwelle liegt und sich theoretisch noch füllen kann (Pipeline-Lauf vor `hard_evaluation_utc_hour` = 20 UTC = 21/22 CEST nach US-Close). `⏳`-Bullets im Detail zeigen die noch offenen Bedingungen. **Routine-seitig wird BEREIT\* wie BEREIT behandelt** (gleicher Bucket, volle Checkliste); der Stern ist nur ein "Schaut nochmal vor Marktschluss aufs Volumen"-Hinweis, falls der Trigger sonst geblockt aussehen würde. Nach 20 UTC wird "Vol unter Schwelle" hart zu `✗` → fällt aus dem BEREIT-Bucket.

**Setup-Klassen-Flags (seit 2026-05-08, Note #47/#49):**

Die Sektion `## Setup-Klassen-Flags` erscheint in **beiden Tiers** — am Anfang von CANDIDATES.md (Tier A, ~30 Watchlist-Symbole) und GAMECHANGER-HUNT.md (Tier B, ~280 Equities aus dem Universe). Tier B liefert die echte PEAD-Kandidatensuche, Tier A bleibt Watchlist-Vorfilter. Sie listet alle Symbole, die mind. eine der aktuell aktiven Setup-Klassen erfüllen — derzeit zwei:

- **🎯 EMA200-MEANREV-CANDIDATE** — Mean-Reversion-Setup auf den 200er-EMA. Trigger: `abs(ema200_distance_pct) ≤ 2.0` UND `days_since_last_ema200_touch ≥ 120` UND `ema200_trend_qualified` UND `weekly_higher_highs_lows`. Hintergrund-Doku: Note #49 im Trading-Journal.
- **📅 PEAD-WINDOW** — Symbol hat in den letzten ≤5 Handelstagen Earnings veröffentlicht und befindet sich im Post-Earnings-Announcement-Drift-Fenster. Trigger nur wenn `EARNINGS_PULL=1` aktiv. Hintergrund-Doku: Note #47. Konsens-/Surprise-Daten sind kein Pipeline-Scope, bleiben manuell im Morning-Check.

Auswertung in der Routine: `pu.list_ema200_meanrev_candidates(md)` bzw. `pu.list_pead_window_candidates(md)`. Beide liefern Listen von TickerData-Objekten — leere Liste wenn keine Treffer (kein Header in CANDIDATES.md gerendert in dem Fall).

### GAMECHANGER-HUNT.md

Setup-getriggerte Stufe-2-Kandidaten aus dem systematischen Universe-Scan. Im Gegensatz zu CANDIDATES.md (Watchlist-Trigger) sind das **neue, vorher nicht beobachtete** Kandidaten, die die Pipeline anhand technischer Setup-Muster (Trend-Pullback, Bounce, Breakout, …) identifiziert hat.

```
# CANDIDATES — 2026-04-26 00:31 CEST              ← Header-Bug, eigentlich GAMECHANGER

## Setup-Klassen-Flags                              ← seit 2026-05-08, beide Tiers

🎯 EMA200-MEANREV-CANDIDATE | TICKER | Distance -1.20% | LastTouch 215d | Trend ✓
📅 PEAD-WINDOW | TICKER | Earnings 2026-05-06 | 2d ago

## Stufe 1 — Watchlist-Trigger-Status              ← in GAMECHANGER-HUNT immer leer

---

## Stufe 2 — Neue Kandidaten aus Universe

### Long-Trend-Pullback

- TICKER1: KURS EMA20=X Dist=±X% RSI=X 30d=±X%
- TICKER2: ...

### Short-Trend-Pullback

- TICKER3: KURS EMA20=X Dist=±X% RSI=X 30d=±X%

### [weitere Setup-Typen, falls Pipeline sie bringt]

---

## Aktive Filter-Overrides
[redundant zu CANDIDATES.md — wird von parse_gamechanger ignoriert]
```

**Beobachtungen:**
- Das Bullet-Format ist **kompakter** als in CANDIDATES.md — kein `**TICKER**`-Wrapper, kein `(DIR) —`-Trenner. Direction wird aus dem Setup-Namen abgeleitet (`Long` / `Short`).
- Setup-Bucket-Namen sind nicht enumeriert; der Parser erkennt jeden `### NAME`-Header als Setup-Kategorie.
- Filter-Overrides am Ende des Files sind redundant zu CANDIDATES.md und werden von `parse_gamechanger` bewusst ignoriert.
- **File-Header-Bug:** Die Pipeline schreibt aktuell `# CANDIDATES — ...` auch in GAMECHANGER-HUNT-Files. Der Parser ist robust dagegen (akzeptiert beide Header-Varianten). Empfehlung an Pipeline-Maintenance: in der Action den Header-String an den Filename anpassen.

---

### INSIDER-US.md (seit 2026-06-10, Paket C1)

SEC-EDGAR-Form-4-Scan fürs Tier-C-Universum (NASDAQ-100). Eigener Workflow
`insider_us_sync.yml`, 1×/Tag Mo–Fr ~07:00 Berlin via cron-job.org —
erfasst den kompletten US-Vortag, liegt vorm Morgen-Briefing. Filename:
`INSIDER-US-YYYY-MM-DD-HHMM.md`, keep_count 10.

```
# INSIDER-US — 2026-06-10 07:00 CEST

## 🟢 Insider-Kauf-Cluster (Trigger-Pfad Note #48)

### 📅 Earnings-Nähe (±5 KT) — BEVORZUGT
- **TICKER** (Issuer Name) — 2 Insider, Σ 370,000 USD, Fenster 2026-06-03→2026-06-06 · 📅 Earnings 2026-06-05 (last, ±5KT)
  - Jane Doe (Director) — 2026-06-04 · 120,000 USD
  - John Smith (Chief Financial Officer) — 2026-06-05 · 250,000 USD ⚙️10b5-1

### Ohne Earnings-Nähe
[gleiche Bullet-Form]

## 🔴 Insider-Sell-Signale (Gegensignal-Check für Long-Kandidaten)
[Cluster-Sells oder CEO/CFO-Einzel-Sell ≥500k USD + Earnings-Nähe]

## ℹ️ Einzelkäufe ≥ Schwelle (kein Cluster — nur Kontext)
[wird vom Parser bewusst ignoriert]
```

**Semantik und Routine-Verbrauch:**
- Schwellen: 55.000 USD/Person (fix, kein FX-Bezug), Cluster ≥2 Organe,
  Fenster 7 Kalendertage (≈ 5 HT). Nur transactionCode P (Open-Market).
- **Earnings-Nähe = ±5 Kalendertage** (Obermenge von ±3 HT aus Note #48,
  Entscheid 2026-06-10). Pipeline-Flag ist Vorfilter — die exakte
  ±3-HT-Prüfung bleibt in der manuellen 7/7-Checkliste.
- Earnings-nahe Buy-Cluster werden **bevorzugt** gerendert/behandelt
  (eigene Sub-Sektion, Sortierung near-first).
- ⚙️10b5-1 = Plan-Trade (maschinenlesbare Checkbox seit SEC-Amendment
  2023). Markiert, nicht verworfen — Signalwert manuell abwerten.
- Sells: nur Cluster bzw. CEO/CFO ≥500k USD **mit** Earnings-Nähe.
  Einzel-Sells erscheinen gar nicht erst im File.
- File ist **additiv** wie GAMECHANGER: bei `missing`/`ausfall` Bucket 1
  ohne US-Teil rendern, kein Web-Fallback. Frische-Threshold sinnvoll:
  ~26h (1×/Tag-Kadenz — NICHT die 30/60-Min-Thresholds anwenden).

**Parse:** `pu.parse_insider_us(content)` → `InsiderUsSnapshot` mit
`buy_clusters` / `sell_signals` (Listen von `InsiderUsSignal`), Methoden
`.find(ticker)` und `.sell_counter_signal(ticker)` (Gegensignal-Check für
Long-Kandidaten, Counter-These-Punkt 1).

---

## pipeline_utils.py — API-Schnellreferenz

| Funktion | Input | Output |
|----------|-------|--------|
| `parse_marketdata(content)` | MD-Content (escaped/clean) | `dict[ticker -> TickerData]` |
| `parse_candidates(content)` | MD-Content (escaped/clean) | `PipelineSnapshot` |
| `parse_gamechanger(content)` | MD-Content (escaped/clean) | `GamechangerSnapshot` |
| `freshness_status(iso_ts, routine, now=None)` | ISO-Timestamp + Routine-Name | `dict mit status, age_minutes, warning_text` |
| `get_ticker_data(md, ticker)` | Marketdata-Dict + Ticker | `TickerData` oder `None` (Off-Universe) |
| `find_candidate_in_buckets(snap, ticker)` | Snapshot + Ticker | `CandidateEntry` (mit `bucket`-Feld) oder `None` |
| `render_freshness_header(md_status, cand_status, routine, gc_status=None)` | Status-Dicts | Header-String (leer bei `ok`) |
| `classify_universe(content, filename=None)` | MD-Content (escaped/clean) + optional Filename | `"standard" \| "gamechanger" \| "unknown"` |
| `select_latest_marketdata(files_with_content, universe="standard")` | Liste Drive-File-Dicts mit `content` | jüngstes File-Dict mit `universe`-Schlüssel oder `None` |
| `ema200_meanrev_qualifies(td)` | TickerData | `bool` — alle vier EMA200-MeanRev-Bedingungen erfüllt? |
| `list_ema200_meanrev_candidates(md)` | Marketdata-Dict | Liste TickerData-Objekte mit erfülltem EMA200-MeanRev-Setup |
| `list_pead_window_candidates(md, max_days=5)` | Marketdata-Dict + max-Tage | Liste TickerData-Objekte mit Earnings ≤ `max_days` zurück |
| `parse_insider_us(content)` | MD-Content (escaped/clean) | `InsiderUsSnapshot` (`.buy_clusters`, `.sell_signals`, `.find`, `.sell_counter_signal`) |

**Konstanten:**
- `FRESHNESS_THRESHOLDS_MIN = {'morning_check': 30, 'scan_afternoon': 30, 'scan_evening': 60}`
- `AUSFALL_THRESHOLD_HOURS = 24`
- `PIPELINE_DRIVE_PARENT_ID = '1_oQBr6KH7u6FDCAUIs1liTnEFjn-b_Ht'` (Briefing-Ordner)
- `STANDARD_UNIVERSE_SENTINELS` (frozenset) — Index/Krypto/FX/Rohstoff-Sentinels für Universum-Erkennung
- `STANDARD_UNIVERSE_MIN_HITS = 3` — Mindesttreffer für `classify_universe → "standard"`

**TickerData-Felder:** `ticker`, `kurs`, `change_pct`, `ema20`, `ema50`, `ema200`, `ema_stack` (`'bullish'|'bearish'|'neutral'`), `rsi`, `atr`, `move_30d`, `low_52w`, `high_52w`, `hi_52w_dist`, `lo_52w_dist`, `low_20d`, `high_20d`, `vol_avg_stk`, `vol_avg_eur`, `vol_today_ratio`. **Seit 2026-05-08 (Note #49 / Übergabe-Spec):** `ema200_distance_pct`, `days_since_ema200_touch`, `ema200_trend_qualified` (bool), `weekly_higher_highs_lows` (bool), `next_earnings_date` (ISO-String), `last_earnings_date` (ISO-String), `days_since_last_earnings` (int).

**PipelineSnapshot-Felder:** `marketdata`, `candidates` (Dict mit Buckets `bereit`, `very_close`, `close`, `watching`, `pending`, `paused`, `passive`, `stufe2_neu`), `overrides` (priority_long/short Override-Liste), `filter_overrides`, `candidates_timestamp`, `marketdata_freshness`, `candidates_freshness`, `fallback_active`, `fallback_reason`.

**CandidateEntry-Felder:** `ticker`, `direction` (`'LONG'|'SHORT'|None`), `raw_direction`, `details`, `bucket`.

**GamechangerSnapshot-Felder:** `timestamp`, `candidates_by_setup` (Dict[setup_name -> list[GamechangerCandidate]]). Methoden: `.all_candidates()` (flache Liste), `.find(ticker)` (Fuzzy-Lookup quer durch alle Setups).

**GamechangerCandidate-Felder:** `ticker`, `setup` (Setup-Name wörtlich), `direction` (`'LONG'|'SHORT'|'NEUTRAL'` aus Setup-Name abgeleitet), `kurs`, `ema20`, `distance_pct`, `rsi`, `move_30d`.

---

## Frische und Fallback

| Status | Bedeutung | Verhalten |
|--------|-----------|-----------|
| `ok` | File frisch (≤ Threshold) | Pipeline-Daten ohne Web-Suche nutzen, Header schweigt |
| `stale` | File älter als Threshold, aber <24h | Pipeline-Daten nutzen, 🟡-Warnung im Header |
| `ausfall` | File >24h alt | **Komplettes Web-Fallback** wie vor Phase 4, 🔴-Header |
| `missing` | File nicht gefunden | **Komplettes Web-Fallback**, 🔴-Header |

**Fallback-Granularität — wichtige Unterscheidung:**

- **MARKETDATA + CANDIDATES = Core**. Fallen sie aus oder sind missing → komplettes Web-Fallback der Routine, wie vor Phase 4.
- **GAMECHANGER-HUNT = Additiv**. Fällt es aus oder ist missing → Routine läuft normal weiter, Gamechanger-Block wird einfach weggelassen, optional kurzer Hinweis im Header. Kein Web-Fallback, weil die Gamechanger-Logik der Pipeline (Universe-Scan nach Setups) ohnehin nicht über Web replizierbar wäre.

**Fallback-Verhalten (Status `ausfall` oder `missing` für MARKETDATA oder CANDIDATES):**
- Routine 7: Wie vor Phase 4 — DAX-Indikation per Web, Watchlist-Block via `ju.list_watchlist(wb)` mit Live-Trigger-Check
- Routine 8/8b/8c: Wie vor Phase 4 — Kurs/RSI/EMA per Web pro Kandidat, Watchlist-Abgleich via `ju.match_watchlist(wb, name)`

**Briefing-Header bei Stale/Fallback:**
```
🟡 PIPELINE-WARNUNG für scan_afternoon:
MARKETDATA: ⚠️ Pipeline-File 45 Min alt (Threshold 30 Min für scan_afternoon). Daten möglicherweise nicht aktuell.
```
oder
```
🔴 PIPELINE-FALLBACK aktiv für morning_check — Briefing nutzt Web-Suchen statt Pipeline-Files.
MARKETDATA: ⚠️ Pipeline-File 26h alt (letzter Lauf 2026-04-25 21:36 UTC). Möglicher Pipeline-Ausfall — Web-Fallback aktiv.
```

---

## Routine-spezifischer Briefing-Output

### Routine 7 — Morgen-Briefing (Detail)

Empfohlene Output-Struktur:

```
[render_freshness_header — falls nicht ok]

🌅 MORGEN-BRIEFING — 2026-04-26 08:45 CEST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Index-Lage (aus MARKETDATA, Stand: HH:MM):
- DAX  XXXXX (±X.XX%) — RSI YY, EMA-Stack [bullish/bearish/neutral], 30d ±X%
- MDAX, SDAX, S&P 500, Nasdaq, VIX, …

📌 Offene Positionen (Kurs aus MARKETDATA):
- #XX [Ticker]: Kurs ±X% gegen Entry, SL/TP-Status

🎯 Watchlist-Block (aus CANDIDATES):
🟢 BEREIT (1):
  - PG (LONG) — Bucket: bereit — Kurs 148.2 IN-ZONE [147.50–149.00]
🟡 ≤2% (2):
  - CBK.DE (LONG), SAN.PA (LONG)
⏸ Pending (5): DRW3.DE (LONG, ab 30.04), AIXA.DE (SHORT, ab 30.04), …
⚠️ Override aktiv: BTC-EUR [priority_short] — Position #24 Zeitstopp 27.04 vor FOMC

🎯 Gamechanger-Funde (aus GAMECHANGER-HUNT):
Long-Trend-Pullback (1):
  - NDX1.DE — Kurs 44.94 (am EMA20), RSI 53, 30d +4.0%
Short-Trend-Pullback (3):
  - PLTR — Kurs 143.09 (-0.66% unter EMA20), RSI 49, 30d -7.7%
  - ZS, NEM.DE — knappe Daten, Vorcheckliste empfohlen
[Bei leerem Setup-Bucket: ganzen Block weglassen, NICHT "(keine Treffer)" schreiben]

🗓 Events heute / nächste 5 Tage (Web):
- [Earnings, ECB, Fed, …]

💡 Empfehlung: [1 Satz]
```

**Gamechanger-Hinweis:** Die Gamechanger-Funde sind **frische Setup-Hits** aus dem Universe-Scan, kein Watchlist-Override — sie haben keine vor-überlegte These, nur ein technisches Setup. Im Briefing als kompakter Block (Ticker + Kerndaten), keine volle 7/7-Checkliste. Wenn ein Kandidat interessant aussieht, geht er via Routine 1b in die Trade-Plan-Erstellung.

**Cross-Check Watchlist:** Wenn ein Gamechanger-Ticker auch in CANDIDATES auftaucht (selten — Watchlist und Gamechanger kommen aus verschiedenen Pipeline-Pfaden), den Watchlist-Eintrag priorisieren und Gamechanger-Eintrag im Block weglassen, sonst Doppel-Erwähnung.

### Routine 8/8b/8c — Scan-Output

Standard-Format aus news-scan.md, ergänzt um Pipeline-Status-Header und vorausgewertete Indikatoren:

```
[render_freshness_header — falls nicht ok]

NEWS-SCAN [Datum]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Kandidat: TICKER — Long/Short — Stufe 1
Meldung:  [aus Web-Suche]
Pipeline-Indikatoren (Stand HH:MM): RSI YY, 30d-Move ±X%, 52W-Hoch-Abstand -Y%, EMA-Stack [bullish/bearish]
Watchlist-Status: [bereit | very_close | nicht auf Watchlist]
Vorcheckliste: X/7 vorläufig
Empfehlung: GO / SKIP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Edge-Cases und Sonderfälle

**Off-Universe-Ticker (News-Scan-Fund nicht im Pipeline-Universum):**
```python
td = pu.get_ticker_data(md, "NEU.DE")
if td is None:
    # Web-Suche NUR für diesen Ticker — Rest bleibt Pipeline
    web_data = web_search(...)
```

**Watchlist-Eintrag aus Sheet, der nicht in CANDIDATES auftaucht:**
Pipeline filtert bei extremer Distanz oder fehlenden Daten. Dann hilft nur ein direkter Blick ins Watchlist-Sheet via `ju.list_watchlist(wb)`. Im Detail-Briefing optional ergänzen, im Scan-Briefing nicht nötig.

**Krypto-Daten am Wochenende:** Krypto handelt 24/7 → Pipeline-Daten von Sa/So sind aktuell. Aktien-Daten dagegen sind eingefroren auf den letzten Handelstag (Fr-Schluss). Bei Wochenend-Briefings die Aktien-Werte mit „Stand letzter Handelstag" labeln. **Achtung:** Das Gamechanger-Universum-MARKETDATA enthält KEIN Krypto — am Wochenende muss zusätzlich das Standard-Universum-MARKETDATA (Fr-Stand) gezogen werden, dort sind die Krypto-Werte enthalten und durch die 24/7-Märkte trotzdem aktuell. `select_latest_marketdata(..., universe="standard")` macht das automatisch.

**Pipeline-Lauf manuell getriggert (z.B. außerhalb der Mo–Fr 30-Min-Kadenz):** Der `freshness_status` reagiert nur auf Alter, nicht auf Schedule-Konformität — manuelle Testläufe werden wie reguläre behandelt. Ist gewünscht so.

**Mehrere Files mit gleichem Datum:** Pipeline schreibt mindestens 1×/30 Min — selber Tag, mehrere Files. Immer die neueste pro File-Typ nehmen (höchstes `modifiedTime`).

---

## Phase 5 — Auto-Load bei Trading-Kontext (aktiv seit 2026-04-26)

Wenn beim Chat-Start eine Journal-Datei hochgeladen wurde **und** das aktuelle Datum/Uhrzeit im Mo–Fr 06:00–22:00 CEST-Fenster liegt, lädt der Skill die Pipeline-Files (MARKETDATA-Standard, CANDIDATES, GAMECHANGER) automatisch und silent vor. Routinen 7/8/8b/8c finden die Daten dann bereits im Kontext, wenn die User-Anfrage kommt — kein zweiter Drive-Roundtrip nötig.

**Trigger-Logik und Code-Block:** siehe SKILL.md § Phase 5.

**Wichtig:** Auto-Load passiert silent — kein Vorspann im User-Output, keine ungefragte Briefing-Antwort. Die Daten sind einfach „bereit" für den Fall, dass eine Trading-Frage kommt.

**Wenn Auto-Load nicht greift (Wochenende, kein Journal, Pipeline-Ausfall):** Routinen laufen weiter wie in Phase 4 — sie laden Pipeline-Files erst beim Codewort. Verhalten ist also additiv, nicht ersetzend.
