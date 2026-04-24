# `journal_utils.py` — API-Referenz

**Zweck:** Modul kapselt alle Journal-Operationen. Ersetzt die openpyxl-Rezepte der SKILL.md für Trade-Updates.

**Ort:** `/mnt/skills/user/derivate-trading/journal_utils.py`

**Stand:** 24.04.2026 — Layout v3 (Gebühren-Transparenz). Neue optionale Parameter: `gebuehr_kauf` im trade-Dict (für `add_*`), `gebuehr_verkauf` in `close_*`/`close_trade_complete`.

---

## Typische Workflows

### Neuer Trade (Derivate) — Routine 1

```python
import sys; sys.path.insert(0, '/mnt/skills/user/derivate-trading')
import journal_utils as ju

wb = ju.open_journal('/mnt/user-data/uploads/Trading_Journal_20260417.xlsx')

ju.add_trade_complete(
    wb,
    trade={
        'kaufdatum': '18.04.2026',
        'instrument': 'HSBC OE Turbo Long Ströer',
        'isin': 'DE000HM5XXXX',
        'typ': 'KO Long',
        'richtung': 'Long',
        'kaufsumme': 514.00,                # 150 × 3,40€ + 4€ SB+/Gettex
        'gebuehr_kauf': 4.00,               # v3: zusätzlich Transparenz-Spalte N
        'notizen': '150 Stk @ 3,40€ | SB+/Gettex/HSBC | KO 28,50€ | Hebel 4,2× | SL 3,00€ / TP1 4,20€',
    },
    portfolio_kurzname='Ströer KO Long',
    portfolio_buy_in=3.40,
    portfolio_tp1=4.20,
    portfolio_sl_ori=3.00,
    portfolio_sl_empf=3.00,
    portfolio_zeitstopp='09.05.2026',
    portfolio_stk=150,
    kind='derivate',
    grund_timestamp='Neuer Ströer Long',
)

wb = ju.save_journal(wb, '/mnt/user-data/outputs/Trading_Journal_20260418.xlsx')
```

`add_trade_complete` macht in einem Aufruf: Zeile in SK einfügen + OFFEN/gelb + Portfolio-Zeile + Timestamp + **Gebühr Kauf in Spalte N**.

**Merke:** `kaufsumme` muss die Gebühr bereits enthalten (steuerlich korrekt). `gebuehr_kauf` ist die zusätzliche Transparenz-Spalte für die Übersichts-Summenzeile R15.

### Trade schließen — Routine 2

```python
wb = ju.open_journal(path)
ju.close_trade_complete(
    wb, nr=50, verkaufsdatum='18.04.2026',
    erloes=392.90,                        # 396,90€ brutto − 4€ Gebühr
    gebuehr_verkauf=4.00,                 # v3: Transparenz-Spalte O (SK) / P (AV)
    lektion='SL @ 0,54€ ausgelöst — Underlying sprang über 1,80€',
    grund_timestamp='HDD Short ausgestoppt',
    kind='derivate',
)
wb = ju.save_journal(wb, out_path)
```

Macht: Detail-Zeile mit C/I/J/K/L aktualisieren, Gelb weg, Lektion anhängen, SALDO neu rechnen, Archiv-Eintrag in „Geschlossene Trades" (inkl. Gebühren-Spalten M/N), Portfolio-Zeile raus, Timestamp.

**Merke:** `erloes` muss bereits Gebühr-netto sein (steuerlich korrekt). `gebuehr_verkauf` ist die zusätzliche Transparenz-Spalte.

### Teilexit — Routine 2 (partial)

```python
wb = ju.open_journal(path)

# FIFO: 1000 Stk @ 0,60€ verkauft @ 0,74€
# Anteiliger Einstand verkauft = 600€, Erlös = 740€
# Rest: 1000 Stk × 0,60€ = 600€ Einstand
ju.partial_exit_derivate(
    wb, nr=51,
    verkaufsdatum='18.04.2026',
    verkaufte_einstand=600.00,
    verkaufter_erloes=740.00,
    rest_einstand=600.00,
    notiz_verkauft='1000 Stk TP1 @ 0,74€',
    notiz_rest='1000 Stk Rest | SL auf 0,60€ (Breakeven)',
)
# Portfolio-Wert aktualisieren (manuell, da Teilexit = Wert-Änderung)
ju.update_portfolio_row(wb, nr=51, wert=600.00, sl_ori=0.60, sl_empf=0.60)

wb = ju.save_journal(wb, out_path)
```

### Aktie — Routine 1a

```python
nr = ju.add_aktie(wb, {
    'kaufdatum': '20.04.2026',
    'aktie': 'Ströer SE',
    'isin': 'DE0007493991',
    'boerse': 'Xetra',
    'stueck': 20,
    'kaufpreis_stk': 34.00,
    'gebuehr': 1.00,                      # default 1€ TR; wird in Einsatz UND Spalte O geschrieben
    'notizen': '20 Stk @ 34,00€ | Dividende 3,75€ erwartet für Mai',
})
```

### Aktie schließen

```python
ju.close_trade_complete(wb, nr=3, verkaufsdatum='02.05.2026',
                         erloes=719.00,          # 720€ brutto − 1€ Gebühr
                         gebuehr_verkauf=1.00,   # v3: in Spalte P
                         lektion='Ex-Div-Effekt wie erwartet',
                         grund_timestamp='Ströer geschlossen', kind='aktie')
```

### Watchlist

```python
# Eintrag hinzufügen
ju.add_watchlist(wb, {
    'aktie': 'Porsche AG',
    'richtung': 'LONG',
    'trigger': 'Nach Q1-Earnings 29.04.',
    'these': 'Nachholbedarf nach Sell-off',
    'status': '👀 beobachten',
    'datum': '18.04.2026',
})

ju.update_watchlist_status(wb, 'Porsche', '🟡 Trigger nah (RSI 53)')
ju.remove_watchlist(wb, 'Porsche')  # Trade eröffnet oder verworfen

# Read-Only: alle Einträge für Morgen-Briefing (Watchlist-Block)
for e in ju.list_watchlist(wb):
    print(f"{e['aktie']:30} {e['richtung']:20} {e['status']}")

# Fuzzy-Match: News-Scan / Hidden-Scan / Insider-Scan — vor Kandidaten-Output
for kandidat in neue_kandidaten:
    match = ju.match_watchlist(wb, kandidat['name'])
    if match:
        # Nicht als neuer Kandidat ausgeben → Watchlist-Treffer-Format
        watchlist_treffer_format(match)
    else:
        neuer_kandidaten_format(kandidat)
```

**Match-Logik:** Token-basiert über den Aktien-Namen. Treffer, wenn mind. 1 Token (≥3 Zeichen, ohne Stopwords wie „AG", „SE") aus der Query exakt einem Token im Eintrag entspricht. Damit matchen sowohl Langname als auch Klammer-Kürzel (`AIXTRON` → `AIXTRON (AIXA)`; `AIXA` → ebenso). Umlaute werden normalisiert (`ä → ae`, `ö → oe`, `ü → ue`). Bewusst **kein** Zeichen-Substring-Match — sonst würde `RWE` fälschlich auf `Drägerwerk` matchen (erw**rwe**rk).

### Notes — Handlungsbedarf, Milestones, ⚠️

Ersetzt seit 22.04.2026 die externe `JOURNAL_STATE.md`. Alles, was nicht aus Übersicht/Watchlist/Geschlossene Trades direkt ablesbar ist, landet hier.

```python
# Beim Chat-Start: Offene Notes lesen
for note in ju.list_notes(wb, nur_offen=True):
    print(f"#{note['id']} [{note['kategorie']}] {note['text']}")

# Neue TODO hinzufügen
ju.add_note(wb, 'ISIN freenet SW363W gegen Broker-Bestätigung verifizieren',
            kategorie='⚠️')

# Milestone festhalten (einmalig, chat-übergreifend)
ju.add_note(wb, 'Trade #59 = 20-Trades-Review: Hit-Rate + Drawdown auswerten, 3%-Regel-Diskussion',
            kategorie='MILESTONE')

# Erledigen — entweder per ID oder per Substring
ju.resolve_note(wb, 3)                    # per ID
ju.resolve_note(wb, 'freenet SW363W')     # per Substring (case-insensitive)

# Gefilterte Listen
offen_todos = ju.list_notes(wb, nur_offen=True, kategorie='TODO')
alle_milestones = ju.list_notes(wb, nur_offen=False, kategorie='MILESTONE')
```

**Kategorien:** `TODO` (Handlung aus), `⚠️` (Klärungsbedarf), `MILESTONE` (chat-übergreifend), `INFO` (Merkposten).

### Portfolio SL/TP anpassen (ohne Trade-Exit)

```python
ju.update_portfolio_row(wb, nr=47, sl_empf=7.20)  # nur SLempf nachziehen
ju.update_portfolio_row(wb, nr=48, tp1=17.50, tp2=21.00, zeitstopp='10.05.2026')
```

### Gebühren-Handling (v3)

Gebühren werden **doppelt erfasst** — einmal in Kaufsumme/Erlös (steuerlich korrekt), einmal als Transparenz-Spalte für die Übersichts-KPI R15.

**Default-Gebühren-Tabelle:**

| Broker / Handelsplatz | Gebühr | Hinweis |
|-----------------------|--------|---------|
| Trade Republic | 1,00€ | Flatrate |
| Smartbroker+ / Gettex | 4,00€ | Minimum, SB+-Default |
| Smartbroker+ / Frankfurt Zertifikate | 5,90€ | Nicht-Gettex-Produkte |

**Entry (Kauf):**
- `kaufsumme` = Stückzahl × Kurs + Gebühr (Gebühr drin!)
- `trade['gebuehr_kauf']` = Gebühr als Zahl (Transparenz-Spalte N bei SK, O bei AV)

**Exit (Verkauf):**
- `erloes` = Stückzahl × Verkaufskurs − Gebühr (Gebühr abgezogen!)
- `gebuehr_verkauf` = Gebühr als Zahl (Transparenz-Spalte O bei SK, P bei AV)

**Rückwirkende Korrektur:** Wenn beim Entry eine Gebühr vergessen wurde (z.B. Kaufsumme = Stk×Kurs ohne Gebühr), dann:
1. H-Zelle in SK/AV direkt auf korrekte Kaufsumme+Gebühr hochziehen
2. `gebuehr_kauf` in N/O nachtragen
3. Hinweis in Notiz-Spalte ergänzen (z.B. „Kauf-Gebühr retroaktiv korrigiert")

---

## Vollständige Funktions-Übersicht

### Öffnen / Speichern

| Funktion | Zweck |
|----------|-------|
| `open_journal(path)` | Workbook laden |
| `save_journal(wb, path)` | Speichern + reload (Ghost-Value-Workaround), neues wb zurückgeben |
| `reload_journal(path)` | Explizites Neu-Laden |

### Finder (Read-Only)

| Funktion | Zweck |
|----------|-------|
| `find_saldo_rows(ws)` | Dict `{saldo, steuer, netto}` für SK-Sheet |
| `find_next_trade_nr(ws)` | Nächste freie Nr im SK-Sheet |
| `find_trade_row(ws, nr, status_filter=None)` | Zeile einer Trade-Nr finden |
| `find_all_trade_rows(ws, nr)` | Alle Zeilen (für TEIL-EXIT) |
| `find_summe_offen_row(ws_ub)` | Zeile der SUMME OFFEN im Portfolio-Block |
| `collect_open_positions(wb)` | Alle OFFEN-Positionen aus SK + AV als Liste von Dicts |

### Derivate (Sheet „Sonstige Kapitalerträge")

| Funktion | Zweck |
|----------|-------|
| `add_derivate_trade(wb, trade)` | Nur Detail-Sheet — neue OFFEN-Zeile. `trade['gebuehr_kauf']` → Spalte N |
| `close_derivate_trade(wb, nr, verkaufsdatum, erloes, lektion=None, archiv=True, gebuehr_verkauf=None)` | Detail-Sheet + Saldo + Archiv. `gebuehr_verkauf` → Spalte O |
| `partial_exit_derivate(wb, nr, verkaufsdatum, verkaufte_einstand, verkaufter_erloes, rest_einstand, notiz_verkauft='', notiz_rest='', archiv=True)` | TEIL-EXIT-Zeile + neue OFFEN-Rest-Zeile |

### Aktien (Sheet „Aktienveräußerungen")

| Funktion | Zweck |
|----------|-------|
| `add_aktie(wb, trade)` | Neue OFFEN-Zeile in AV. `trade['gebuehr']` → Einsatz + Spalte O |
| `close_aktie(wb, nr, verkaufsdatum, verkaufspreis_stk, erloes=None, lektion=None, archiv=True, gebuehr_verkauf=None)` | AV-Zeile schließen + Archiv. `gebuehr_verkauf` → Spalte P |

### Übersicht (Portfolio + Timestamp)

| Funktion | Zweck |
|----------|-------|
| `update_timestamp(wb, grund, datum=None)` | Z4 Stand-Zeile + Z16 Portfolio-Header |
| `add_portfolio_row(wb, nr, instrument, kurzname, wert, buy_in=None, tp1=…, …)` | Neue Zeile vor SUMME OFFEN |
| `update_portfolio_row(wb, nr, wert=None, buy_in=None, tp1=None, tp2=None, sl_ori=None, sl_empf=None, zeitstopp=None)` | Einzelne Felder ändern |
| `remove_portfolio_row(wb, nr)` | Zeile entfernen + SUMME neu |

### Watchlist

| Funktion | Zweck |
|----------|-------|
| `add_watchlist(wb, entry)` | Neuer Eintrag |
| `update_watchlist_status(wb, aktie, status)` | Status-Update (Substring-Match) |
| `remove_watchlist(wb, aktie)` | Eintrag entfernen |
| `list_watchlist(wb) → List[Dict]` | Alle Einträge lesen (Morgen-Briefing-Block) |
| `match_watchlist(wb, query) → Dict \| None` | Fuzzy-Match gegen Watchlist (Token-basiert, normalisiert) — vor News-/Hidden-/Insider-Scan-Output |

### Notes

| Funktion | Zweck |
|----------|-------|
| `ensure_notes_sheet(wb)` | Stellt Sheet sicher (legt an falls fehlt) — idempotent |
| `add_note(wb, text, kategorie='TODO', datum=None)` | Neue Notiz, gibt neue ID zurück |
| `resolve_note(wb, match, datum=None)` | ERLEDIGT setzen, `match` = ID (int) oder Substring (str) |
| `list_notes(wb, nur_offen=True, kategorie=None)` | Liste von Dicts (id, datum, kategorie, text, status, erledigt_am) |

### High-Level Wrapper (machen alles in einem Aufruf)

| Funktion | Zweck |
|----------|-------|
| `add_trade_complete(wb, trade, portfolio_kurzname, …, kind='derivate'\|'aktie')` | Detail + Portfolio + Timestamp. `trade['gebuehr_kauf']` (derivate) / `trade['gebuehr']` (aktie) |
| `close_trade_complete(wb, nr, verkaufsdatum, erloes, …, kind=…, gebuehr_verkauf=None)` | Detail + Saldo + Archiv + Portfolio-Raus + Timestamp |

---

## Konstanten & Styling

| Konstante | Wert | Zweck |
|-----------|------|-------|
| `SHEET_SK` | `'Sonstige Kapitalerträge'` | Sheet-Name |
| `SHEET_AV` | `'Aktienveräußerungen'` | |
| `SHEET_UEBERSICHT` | `'Übersicht'` | |
| `SHEET_WATCHLIST` | `'Watchlist'` | |
| `SHEET_GESCHLOSSEN` | `'Geschlossene Trades'` | Archiv |
| `SHEET_NOTES` | `'Notes'` | Handlungsbedarf / Milestones / ⚠️ |
| `FILL_GELB` | `PatternFill('solid', fgColor='FFFFFF00')` | OFFEN-Markierung |
| `FILL_ZEBRA` | hellgrau `FFF5F5F5` | Zebra-Streifen Portfolio |
| `COLOR_GEWINN` | `FF1B7A2B` | Grün |
| `COLOR_VERLUST` | `FFCC0000` | Rot |
| `FMT_EURO` | `'#,##0.00" €"'` | Zahlenformat €-Beträge |
| `FMT_PROZENT` | `'0.0%'` | Zahlenformat G/V% |
| `STEUERSATZ` | `0.26375` | Abgeltungssteuer |

---

## Was das Modul NICHT macht

- **FIFO-Berechnungen** bei Teilexits — der anteilige Einstand muss manuell ausgerechnet und als Parameter übergeben werden. Das war bewusst so entschieden, weil FIFO bei mehreren Tranchen (z.B. Lufthansa #36/#37 mit Nachkauf) nicht-trivial ist und die Berechnung im Chat-Dialog sauberer ist.
- **Übersicht Z9–Z11** (Aktientopf / Krypto / Staking) — dafür gibt es separate Funktionen (noch nicht implementiert) oder manuelles Nachtragen.
- **Sparplan-Aktualisierungen** (JPM u.ä.) — weil diese keine einheitliche Struktur haben.
- **Werbungskosten** — Routine 5, simple Zeilen-Anhängung, die via `bash_tool` trivial ist.

Für diese Fälle sind ad-hoc openpyxl-Skripte nach wie vor der richtige Weg.

---

## Pflege-Regel

Wenn sich das Journal-Layout ändert (neue Spalte, verschobener Portfolio-Start, neuer Sheet-Name):
1. `journal-layout.md` zuerst aktualisieren
2. `journal_utils.py` anpassen — **Konstanten-Block oben** ist die primäre Stellschraube
3. End-to-End-Test auf einer Kopie des Journals ausführen (alle Szenarien aus den „Typische Workflows"-Beispielen oben)
