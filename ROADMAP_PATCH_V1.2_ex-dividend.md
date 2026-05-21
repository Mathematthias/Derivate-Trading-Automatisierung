# Journal-Layout & Formatting-Standards

**Wird geladen bei:** Detail-Fragen zu Sheet-Spalten, Saldo-Zeilen, Formatting, Zellenfarben, Umbau des Journals.

**Stand:** 24.04.2026 — Layout v3 (Gebühren-Transparenz: SK N+O, AV O+P, Archiv M+N, Übersicht R15)

---

## Sheet-Übersicht (Reihenfolge im Journal)

| # | Sheet | Zweck |
|---|-------|-------|
| 1 | **Übersicht** | Dashboard: Steuertöpfe + Portfolio |
| 2 | **Watchlist** | Kandidaten-Liste mit Trigger, These, Status |
| 3 | **Geschlossene Trades** | Archiv aller geschlossenen Trades (Derivate + Aktien) |
| 4 | **Sonstige Kapitalerträge** | Detail: Derivate + ETFs + ETPs + ETCs |
| 5 | **Aktienveräußerungen** | Detail: Direktaktien (separater Steuertopf!) |
| 6 | **Krypto §23 EStG** | Krypto-Skill |
| 7 | **Staking §22 Nr.3** | Krypto-Skill |
| 8 | **Sparpläne** | JPM Sparplan + regelmäßige Investments |
| 9 | **Werbungskosten** | Abos, Trading-Tools, Literatur |
| 10 | **Lektionen** | Fallbeispiele der Handelslektionen |

---

## Sheet „Übersicht" (Blatt 1)

### Struktur

- **Z1–Z3:** Titel + Untertitel
- **Z4:** Timestamp — `Stand: DD.MM.YYYY – (Grund)`, B4 = Datum als String
- **Z6:** „Steuerliche Verrechnungstöpfe"
- **Z7:** Header (dunkelblau `FF1B3A5C`, weiß-bold)
- **Z8:** Sonstige Kapitalerträge — **Formeln** auf „Sonstige Kapitalerträge":
  - `C8 =SUMIFS('Sonstige Kapitalerträge'!J:J,'Sonstige Kapitalerträge'!J:J,">0",'Sonstige Kapitalerträge'!A:A,">=1")`
  - `D8 =SUMIFS(…J:J,…J:J,"<0",…A:A,">=1")`
  - `E8 =INDEX('Sonstige Kapitalerträge'!J:J,MATCH("REALISIERTER SALDO",'Sonstige Kapitalerträge'!A:A,0))`
  - `H8 =E8*0.26375`
- **Z9:** Aktienveräußerungen — C/D manuelle Werte, E9 = C9+D9
- **Z10:** Krypto §23 — manuelle Werte
- **Z11:** Staking §22
- **Z12:** Werbungskosten
- **Z13:** GESAMT (grün hinterlegt `FFE2EFDA`, bold) — Summe aus Z8–Z11
- **Z14:** GESAMT NETTO (dunkelblau, weiß-bold)
- **Z15:** `Gebühren kumuliert 2026` (Info-Zeile, kursiv grau `FF555555`)
  - `A15` = Label, `B15` = „(Info — bereits in Saldi verrechnet)"
  - `C15 =SUMIFS('Sonstige Kapitalerträge'!N:N,'Sonstige Kapitalerträge'!A:A,">=1")+SUMIFS('Aktienveräußerungen'!O:O,'Aktienveräußerungen'!A:A,">=1")` — Summe Kauf-Gebühren
  - `D15 =SUMIFS('Sonstige Kapitalerträge'!O:O,'Sonstige Kapitalerträge'!A:A,">=1")+SUMIFS('Aktienveräußerungen'!P:P,'Aktienveräußerungen'!A:A,">=1")` — Summe Verkauf-Gebühren
  - `E15 =C15+D15` — Gesamt-Gebühren YTD
  - **Wichtig:** Nicht in Z13/GESAMT addieren — ist eine reine Transparenz-KPI, die Gebühren sind schon in Kaufsumme/Erlös der einzelnen Trades drin.
- **Z16:** `PORTFOLIO — Offene Positionen (Stand DD.MM.YYYY)`
- **Z17:** Portfolio-Header (dunkelblau, weiß-bold)
- **Ab Z18:** Offene Positionen (eine pro Zeile, Zebra-Streifen)
- **Nach letzter Position:** `SUMME OFFEN:` (grün hinterlegt, bold, Summe Spalte B)

### Portfolio-Block — Spalten (9)

| Spalte | Inhalt | Format |
|--------|--------|--------|
| A | Position — z.B. `Jenoptik KO Long (#47, 78 Stk REST)` | Calibri 11 bold |
| B | Wert (€) — aktueller Einsatz | `#,##0.00" €"` |
| C | Buy In (€/Stk) | `#,##0.00" €"` |
| D | TP1 | `#,##0.00" €"` oder `'—'` |
| E | TP2 | `#,##0.00" €"` oder `'—'` |
| F | SLori (ursprünglicher SL) | `#,##0.00" €"` oder `'—'` |
| G | SLempf (empfohlener / nachgezogener SL) | `#,##0.00" €"` oder `'—'` |
| H | Zeitstopp (Datum-String) | `'DD.MM.YYYY'` oder `'—'` |
| I | Status — `OFFEN` / `TEIL-GESCHL.` | Calibri bold |

### Zebra-Streifen

Ungerade Positionen im Portfolio-Block (Z18 = 1, Z19 = 2, …) werden alternierend eingefärbt:
- Ungerade (Z18, Z20, Z22): kein Fill
- Gerade (Z19, Z21, Z23): `FFF5F5F5` (hellgrau)

Regel im Modul: `position_in_block = row - PORTFOLIO_HEADER_ROW`; wenn `position_in_block % 2 == 1` → hellgrau.

### Synchronisations-Regel

Nach jedem Trade-Update (Eintrag, Close, Teil-Exit):
1. Detail-Sheet aktualisieren (SK oder AV)
2. Übersicht Z4 (Timestamp + Grund, B4 Datum)
3. Übersicht Z16 (Datum in Überschrift)
4. Portfolio-Block: Zeile einfügen (vor SUMME OFFEN) oder entfernen
5. SUMME OFFEN neu berechnen
6. Z8-Formeln laufen automatisch — **kein** manueller Eingriff nötig

---

## Sheet „Watchlist" (Blatt 2)

### Zweck
Kandidaten-Liste. Persistent über Chats hinweg.

### Spalten

| Spalte | Inhalt | Format |
|--------|--------|--------|
| A | Aktie (Name) | Text |
| B | Richtung (`LONG` / `SHORT`) | Text |
| C | Entry-Trigger | Text |
| D | These (kurz) | Text |
| E | Status — z.B. `👀 beobachten`, `🟡 Trigger nah`, `🟢 Setup reif`, `✅ Trade #XX eröffnet`, `❌ verworfen` | Text mit Emoji |
| F | Datum hinzugefügt | `'DD.MM.YYYY'` |

Kein Saldo-Block. Status-Änderungen per Substring-Match auf Spalte A.

---

## Sheet „Geschlossene Trades" (Blatt 3)

### Zweck
Archiv aller geschlossenen Positionen — Derivate, ETFs, Aktien. Entsteht durch automatisches Kopieren beim `close_trade`-Aufruf.

### Spalten (14)

| Spalte | Inhalt |
|--------|--------|
| A | Nr. |
| B | Kaufdatum |
| C | Verkaufsdatum |
| D | Instrument |
| E | ISIN |
| F | Typ — `KO Short`, `KO Long`, `ETF`, `ETP`, `ETC`, `Aktie` |
| G | Richtung |
| H | Kaufsumme (€) |
| I | Erlös (€) |
| J | G/V (€) — grün bei Gewinn, rot bei Verlust |
| K | G/V % |
| L | Notizen |
| **M** | **Gebühr Kauf (€)** |
| **N** | **Gebühr Verkauf (€)** |

**Sortierung:** Append-only (neue Einträge ans Ende). Sortierung kann bei Bedarf per Hand nach Verkaufsdatum vorgenommen werden.

---

## Sheet „Sonstige Kapitalerträge" (Blatt 4)

### Zweck
Derivate (KO-Zertifikate, Turbos) + ETFs + ETPs + ETCs. §20 Abs. 1 EStG, Verrechnung mit sonstigen Kapitalerträgen.

### Spalten (15)

| Spalte | Inhalt | Format |
|--------|--------|--------|
| A | Nr. (fortlaufend) | Integer (oder `'—'` für Steuerkorrekturen) |
| B | Kaufdatum | String `'DD.MM.YYYY'` — **nie** datetime! |
| C | Verkaufsdatum | String `'DD.MM.YYYY'` |
| D | Instrument (Name) | Text |
| E | ISIN | Text |
| F | Typ | `KO Short`, `KO Long`, `ETF`, `ETP`, `ETC` |
| G | Richtung | `Short` / `Long` |
| H | Kaufsumme (€) **inkl. Kauf-Gebühr** | `#,##0.00" €"` |
| I | Erlös (€) **netto — abzgl. Verkauf-Gebühr** | `#,##0.00" €"` |
| J | G/V (€) | `#,##0.00" €"`, grün/rot |
| K | G/V % | `0.0%`, grün/rot |
| L | Status | `OFFEN` / `GESCHLOSSEN` / `TEIL-EXIT` / `TEIL-GESCHL.` / `VERBUCHT` |
| M | Notizen | Stk, Kurs, SL/TP, These, Lektionen, ⚠️-Marker |
| **N** | **Gebühr Kauf (€)** | `#,##0.00" €"` — Transparenz, ist bereits in H drin |
| **O** | **Gebühr Verkauf (€)** | `#,##0.00" €"` — Transparenz, ist bereits in I abgezogen |

**Gelb-Markierung (OFFEN)** erstreckt sich ab v3 auf Spalten A–O (vorher A–M).

### Saldo-Block (am Ende)

Drei Zeilen am Ende, ohne Leerzeile zwischen Daten und Saldo:

| Zeile | A | H | I | J | Styling |
|-------|---|---|---|---|---------|
| Saldo | `REALISIERTER SALDO` | `"Gewinne: X.XX€"` (String) | `"Verluste: X.XX€"` (String) | Zahl `#,##0.00" €"` | A/H/I: Arial 10 bold; J: Cambria 12 bold grün |
| Steuer | `STEUER (26,375%)` | — | — | Zahl `#,##0.00" €"` (negativ) | J: Cambria 11 rot |
| Netto | `REINGEWINN (NETTO)` | — | — | Zahl `#,##0.00" €"` | J: Cambria 11 bold grün |

**⚠️ Saldo-Zeilen verschieben sich bei `insert_rows()`** — das Modul findet sie dynamisch per Label in Spalte A, keine fixen Zeilen-Nummern mehr.

### Gelbe Markierung (OFFEN)

- **Gelb** `FFFFFF00` → Position OFFEN (Spalten A–M)
- **Beim Schließen:** Gelb entfernen (`PatternFill(fill_type=None)`)
- **Bei TEIL-EXIT:** Die TEIL-EXIT-Zeile hat **kein** Gelb (nicht mehr offen), die neu angelegte Rest-Zeile hat wieder Gelb

### TEIL-EXIT-Pattern (FIFO)

Beispiel Jenoptik #47:
- Zeile A: Status `TEIL-EXIT`, H = anteiliger Einstand verkauft, I = Erlös, G/V ausgerechnet
- Zeile B (direkt darunter): Status `OFFEN`, H = anteiliger Einstand Rest, I = leer

Beide Zeilen tragen dieselbe Trade-Nr in Spalte A.

---

## Sheet „Aktienveräußerungen" (Blatt 5)

### Zweck
Direktaktien (§20 Abs. 2 Nr. 1 EStG). **Separater Verrechnungstopf!** — Verluste nur mit Aktiengewinnen verrechenbar.

### Spalten (16)

| Spalte | Inhalt |
|--------|--------|
| A | Nr. (fortlaufend, **eigener** Zähler) |
| B | Kaufdatum |
| C | Verkaufsdatum |
| D | Aktie (Name) |
| E | ISIN |
| F | Börse (z.B. `Xetra`, `Lang & Schwarz`, `gettex`) |
| G | Stück |
| H | Kaufpreis/Stk (€) |
| I | Verkaufspreis/Stk (€) |
| J | Einsatz (€) = Stück × Kaufpreis + **Gebühr Kauf** |
| K | Erlös (€) — netto abzgl. Verkauf-Gebühr |
| L | G/V (€) — grün/rot |
| M | Status |
| N | Notizen |
| **O** | **Gebühr Kauf (€)** — Transparenz, ist bereits in J drin |
| **P** | **Gebühr Verkauf (€)** — Transparenz, ist bereits in K abgezogen |

**Gelb-Markierung (OFFEN)** erstreckt sich ab v3 auf Spalten A–P.

**⚠️ STEUERLICH KRITISCH:** Niemals Aktien in „Sonstige Kapitalerträge" eintragen. Niemals KO/ETF/ETP in „Aktienveräußerungen". TR führt Töpfe automatisch getrennt — das Journal spiegelt das.

---

## Weitere Sheets

### „Krypto §23 EStG" (Blatt 6) / „Staking §22 Nr.3" (Blatt 7)
→ Krypto-Skill zuständig (`krypto-portfolio` / `krypto-grid-trading`).

### „Sparpläne" (Blatt 8)
JPM Sparplan und sonstige regelmäßige Investments.

### „Werbungskosten" (Blatt 9)

| Spalte | Inhalt |
|--------|--------|
| A | Datum |
| B | Anbieter |
| C | Beschreibung |
| D | Betrag (€) |
| E | Nachweis (Link/Dateiname) |

### „Lektionen" (Blatt 10)
Verankerte Handelslektionen mit Fallbeispielen.

---

## Formatting-Standards (PFLICHT bei jedem Eintrag)

### Zahlenformate

| Kontext | Format |
|---------|--------|
| Euro-Beträge (H/I/J in SK, J/K/L in AV, B/C/D/E/F/G in Portfolio) | `#,##0.00" €"` |
| Prozent (K in SK, G/V%-Spalte im Archiv) | `0.0%` |
| Datum (B/C in SK, B/C in AV) | String `'DD.MM.YYYY'` — NIE datetime! |

### Schriftfarben

| Kontext | Font | Farbe |
|---------|------|-------|
| Gewinn-G/V in Trade-Zeile | Cambria 11 | `FF1B7A2B` (grün) |
| Verlust-G/V in Trade-Zeile | Cambria 11 | `FFCC0000` (rot) |
| Saldo-Zahl (positiv) | Cambria 12 bold | `FF1B7A2B` |
| Saldo-Zahl (negativ) | Cambria 12 bold | `FFCC0000` |
| Steuer-Zahl | Cambria 11 | `FFCC0000` |
| Netto-Zahl | Cambria 11 bold | grün/rot je nach Vorzeichen |

### Gelb-Markierung

- `PatternFill('solid', fgColor='FFFFFF00')` → OFFEN
- `PatternFill(fill_type=None)` → GESCHLOSSEN / TEIL-EXIT

Systematischer Check nach jedem Status-Wechsel: Alle Zeilen derselben Trade-Nr prüfen.

---

## Sheet „Notes" (chat-übergreifende Memos)

### Zweck
Handlungsbedarf, Milestones und offene Klärungen, die sonst zwischen den Sheets verloren gingen. Ersetzt seit 22.04.2026 die frühere externe `JOURNAL_STATE.md`. Wird über `journal_utils.add_note/resolve_note/list_notes` gepflegt.

### Spalten

| Spalte | Inhalt | Format |
|--------|--------|--------|
| A | ID (laufende Nummer, automatisch) | int |
| B | Datum-erstellt | String `dd.mm.yyyy` |
| C | Kategorie | `TODO` / `⚠️` / `MILESTONE` / `INFO` |
| D | Notiz-Text | String (Wrap-Text, Spaltenbreite 80) |
| E | Status | `OFFEN` / `ERLEDIGT` |
| F | Erledigt-am | String `dd.mm.yyyy` (bei Status OFFEN leer) |

### Styling
- Zeile 1: Header dunkelblau (`FILL_HEADER_BLAU`), Schrift weiß fett, Freeze `A2`
- Datenzeilen: Calibri 11, Spalte D mit Wrap-Text
- Keine Gelb-Markierung — OFFEN erkennt man an Spalte E

### Kategorien-Konvention

| Kategorie | Verwendung |
|-----------|------------|
| `TODO` | konkrete Handlung steht aus (ISIN eintragen, SL nachziehen, Watchlist pflegen) |
| `⚠️` | Klärungs-/Verifikationsbedarf (fehlende Daten, zweifelhafte Werte) |
| `MILESTONE` | chat-übergreifende Meilensteine (z.B. Trade #59 = 20-Trades-Review) |
| `INFO` | Merkposten ohne Handlungsbedarf (z.B. "nächstes FOMC 27.04.") |

---

## Modul `journal_utils.py`

Ab Layout v2 werden alle Journal-Operationen über das Modul `journal_utils.py` (im Skill-Ordner) abgewickelt. Es kapselt:
- Öffnen / Speichern inkl. Ghost-Value-Workaround
- Saldo-Block findet sich selbst (per Label in Spalte A — keine fixen Zeilen mehr)
- Trade-Nr-Zuweisung automatisch
- Style-Konsistenz (Gelb, Zebra, Farben, Formate)
- Portfolio-Block synchron mit Detail-Sheets
- Archiv-Einträge automatisch beim `close_trade`

Verwendung → `journal-utils-api.md` (dieselbe References-Ordner).
