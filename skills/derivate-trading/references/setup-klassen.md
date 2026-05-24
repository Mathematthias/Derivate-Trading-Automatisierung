# Setup-Klassen — Referenz

Konsolidierte Spezifikationen der regelbasierten Long-/Short-Setup-Klassen. Jede Klasse hat Vorprüfung (falls zutreffend), 7/7-Filter, Entry-Trigger, Exit-Logik, Haltedauer, Sizing und — wo vorhanden — einen Validierungs- bzw. Negativ-Anker.

Diese Datei ist die **Single Source of Truth** für die vier Pilot-Klassen unten. Bereits in `SKILL.md` ausgeschriebene Klassen (Trend-Pullback, Breakout, Reversal, Momentum-Continuation-Long, Sell-the-News-Continuation-Short) sind hier nicht dupliziert — sie stehen in den jeweiligen `SKILL.md`-Abschnitten.

**Pilot-Status:** Alle vier Klassen unten sind v0.1-Piloten. Sizing pro Trade 1 % Risikokapital (150 €) für die ersten 5–10 Trades der jeweiligen Klasse, danach Re-Evaluation der Hit-Ratio + R-Multiple und Übergang auf Standard-Score-Sizing.

---

## 1. PEAD-Pilot v0.1 (Post-Earnings Announcement Drift, Long-only)

Komplement zu Trend-Pullback/Continuation/Reversal. Fängt die Drift nach einem starken, aber unterreagierten Earnings-Beat.

### 7/7-Filter

1. EPS-Beat ≥ 10 % über Konsens.
2. Revenue-Beat ≥ 2 % über Konsens.
3. Underreaction-Sweet-Spot: Earnings-Tag-Reaktion **+1 bis +6 %** (NICHT < 1 % — kein Signal; NICHT > 6 % — Drift schon eingepreist).
4. Liquidität: Marktkap ≥ 1 Mrd. € + Volumen ≥ 100k Stk/Tag (30D-Avg).
5. EMA-Stack 1D nicht stark bearisch (EMA20 nicht > 5 % unter EMA50).
6. Counter-These: max. 1 weiche Flag (Insider-Cluster-Sells, Analyst-Downgrades trotz Beat, Sektor-Schwäche, Ex-Div in Halte-Phase).
7. R:R ≥ 1,5 brutto / ≥ 1,8 US (FX-adjustiert nach Lektion 1 v2).

### Entry

- **Trigger A (bevorzugt):** 1–5 HT nach Earnings, Pullback 1–3 % vom Earnings-Tag-Close + Reverse-Kerze (Hammer / Bullish-Engulfing / Reverse-Close) + RSI 1D < 60.
- **Trigger B (Continuation):** Daily-Close > Earnings-Tag-Hoch + Vol ≥ 30D-Ø — nur wenn A nicht kommt.

### Exit

- SL unter Earnings-Tag-Tief − 0,5 × ATR (Trigger B: unter Earnings-Tag-Close).
- TP1 = Earnings-Tag-Close +6–8 % → 50 % Teil-Exit, SL → Breakeven (Lektion 6).
- TP2 = +12–15 % oder 1 HT vor den nächsten Earnings.
- Halte 10–40 HT (Min. 10 — sonst Continuation, nicht PEAD; Max. 40).

### Negativ-Anker

Henkel Q1 (07.05.2026) — Score 2/7, SKIP. Revenue-Miss −1,4 %, bearischer EMA-Stack 1D, drei harte Counter-Flags. Der Earnings-Tag-Pop +4,89 % kam aus einer M&A-Story (5 Akquisitionen ~1,6 Mrd. €), nicht aus operativem Beat — **Story-Pop ≠ Beat-Pop.** Reverse −2,83 % am Folgetag bestätigte Sell-the-News.

### Unterklasse — News-Catalyst-Continuation-Long

Lockerere Variante für Werte, die den strikten PEAD-Filter knapp verfehlen, aber faktisch driften (Beispiel DTE: Adj.-EPS +7,9 % Beat, Rev +1,44 % Beat, Tag-1 nur +0,58 % — unter Sweet-Spot, trotzdem laufende +5 %-Drift in 4 HT).

- **Beat-Schwelle gelockert:** ≥ 5 % EPS-Beat **ODER** Guidance-Anhebung + Rating-Upgrade.
- **Trigger:** Continuation — Daily-Close > Earnings-Tag-Hoch (statt Pullback-Trigger).
- Die Pre-Trigger-Pause (`SKILL.md` § Pre-Trigger-Orders) greift hier **nicht** — ein News-Catalyst liegt vor.
- Übrige Exit-/Halte-/Sizing-Logik wie PEAD-Pilot v0.1.

---

## 2. Insider-Buys-Cluster v0.1 (Long, Counter-Trend)

Long-Pendant zum Insider-Sells-Scan. Mehrere zeitgleiche Vorstands-/AR-Käufe am Tief sind ein hartes Edge-Signal.

### Datenquellen

Bundesanzeiger Directors' Dealings (DE) + BaFin §-19-MAR-Meldungen + SEC Form 4 (US; Aggregator openinsider.com, Backup secform4.com).

### Cluster-Definition (alle 6 Punkte Pflicht)

1. ≥ 2 verschiedene Insider-Personen.
2. Zeitfenster ≤ 14 Tage.
3. Mindest-Volumen pro Person ≥ 100k € (DE) bzw. ≥ 250k $ (US).
4. Filing-Code **P** (Open Market Purchase) — NICHT A (Award), G (Gift), V (Vested).
5. Mindestens eine Person aus C-Suite (CEO/CFO/COO) ODER Aufsichtsrat-Vorsitz.
6. Außerhalb der Sperrfrist (typisch 4–6 Wochen vor Quartalszahlen).

### 7/7-Filter

1. Cluster-Definition erfüllt.
2. Aktie ≥ 15 % unter 52W-Hoch (Insider kaufen am Tief, nicht am Hoch).
3. RSI 1D < 55 zum Cluster-Zeitpunkt (kein Chase nach Rally).
4. Counter-These sauber: keine parallelen Insider-Sells, keine Analyst-Downgrade-Cluster, keine harten DOJ-/Regulatory-Headlines.
5. EMA-Stack 1D nicht extrem bearisch (EMA20 nicht > 10 % unter EMA200).
6. Liquidität OK (Marktkap ≥ 500 Mio. €, Vol ≥ 50k Stk/Tag 30D-Avg — niedriger als PEAD, weil Buys-Setups oft Mid-/Small-Caps sind).
7. R:R ≥ 1,8 brutto (höher als PEAD wegen Counter-Trend-Charakter).

### Entry

- **Trigger A (bevorzugt):** Reverse-Kerze nach Cluster-Bekanntwerden (4h oder 1D) + Vol ≥ 30D-Avg + RSI 1D < 50.
- **Trigger B (Bestätigung):** Daily-Close > EMA20 1D + Vol ≥ 1,5 × Avg.

### Exit

- SL unter Tief der Bestätigungskerze − 0,5 × ATR.
- TP1 = EMA50 1D → 50 % Teil-Exit, SL → Breakeven (Lektion 6).
- TP2 = EMA100 1D oder 1 HT vor den nächsten Earnings.
- Halte 10–60 HT (Insider-Cluster wirken oft erst über Wochen, bis der Markt das Filing einpreist).

### Validierungs-Anker

CTS Eventim (April 2026) — Dreifach-Cluster CEO Schulenberg 4,9 Mio. € + Stiftung + AR, 7/7-Score, Ergebnis +369,75 € (+23,2 % auf Gesamteinsatz).

---

## 3. EMA200-Mean-Reversion v0.1 (1D, Long-only, rein technisch)

Erster EMA200-Touch in einem starken mehrmonatigen Aufwärtstrend zieht institutionelle Re-Allokations-Käufe an — EMA200 als „faires" Niveau. Bounce statistisch wahrscheinlich, mechanisches Setup ohne News-Trigger.

### Vorprüfung (alle 4 Punkte Pflicht für Qualifikation)

a. Bullisch-Trend ≥ 6 Monate (≥ 120 HT), EMA200 steigend ≥ 80 % der Zeit.
b. Aktueller Test = erste EMA200-Berührung seit ≥ 6 Monaten.
c. Trend intakt: höhere Hochs UND höhere Tiefs auf dem Wochen-Chart.
d. **Kein News-, Sektor- oder Makro-Schock als Auslöser.** Bei fundamentalem Bruch ist es ein Reversal-Versuch im neuen Trend, kein MeanRev-Trade. Erweiterung: Ein preisbasierter EMA200-Touch-Trigger ist auch dann **invalid**, wenn der Touch absehbar sektor-/makro-getrieben zustande kommt (Beispiel GV6: fallender Silberpreis zieht den Wert auf die EMA200). Dann ist die EMA200 Durchgangsstation, keine Unterstützung. Konsequenz für Sektor-Werte: Reversal-Trigger **sektor-konfirmiert** formulieren (z. B. „Underlying-Index-Close > EMA20 als Greenlight + Reverse-Kerze am Wert"), nicht über ein fixes EMA-Level allein.

### 7/7-Filter

1. Vorprüfung erfüllt.
2. Touch EMA200 1D in den letzten 5 HT, Toleranz ± 1 × ATR.
3. RSI 1D zwischen 30 und 45 zum Touch-Zeitpunkt.
4. Reverse-Kerze nach Touch: Hammer / Bullish-Engulfing / Reverse-Close 1D ODER 4h.
5. Volumen am Touch-Tag ≥ 30D-Avg (institutionelle Aktivität, kein stilles Tropfen).
6. EMA50 1D > EMA200 1D mit Abstand ≥ 3 % (Trend intakt, Touch ist Pullback, nicht Bruch).
7. R:R ≥ 1,8 brutto / ≥ 2,0 US (FX-adjustiert nach Lektion 1 v2).

### Entry

An der Bestätigungskerze nach dem Reverse-Signal, Daily-Close bevorzugt. Bei klarem Hammer auch 4h-Close möglich, dann Sizing reduziert.

### Exit

- SL unter Touch-Tief − 0,8 × ATR (bewusst weiter als PEAD wegen Stop-Run-Cluster). Bei Bruch ist das Setup tot.
- TP1 = EMA50 1D ODER +1,5 × ATR vom Entry, je nachdem was näher → 50 % Teil-Exit, SL → Breakeven (Lektion 6).
- TP2 = EMA20 1D ODER Vorhochs der letzten 30 HT, je nach Marktstruktur.
- Halte 5–25 HT (schneller als PEAD/Insider-Buys, weil mechanisch statt thesengetrieben).

### Erwartetes Profil

Hohe Hit-Ratio (60–70 %), moderates R-Multiple (1,3–1,8) — viele kleine Gewinner, gelegentlich Vollverlust bei Trend-Bruch.

---

## 4. Übersicht — Edge-Hierarchie bei Doppel-Trigger

Wenn zwei Setups gleichzeitig auf denselben oder korrelierte Werte feuern, gilt die Edge-Hierarchie (siehe `SKILL.md` § Pipeline-WL-Merge-Regel):

**Insider-Cluster > PEAD > EMA200-Mean-Reversion > Reversal > Trend-Pullback > Breakout.**

Bei gleichem Edge-Tier gewinnt das R:R-beste Setup.
