# Hoch-ATR-Signale LS-2 (2026-11-19)

Protokoll im Kopf von `research/atr_ls2.py` (vorher festgelegt). Variante A: Einstieg Signalschluss, B: Eroeffnung T+1 wie live. Vorsprung = Signal minus Zufall in derselben ATR%-Klasse und Trendlage, Ausstieg A. Statistik nur ueber abgeschlossene Trades.

Signale ab 2009: n = 8560 abgeschlossen (45 offen), Symbole 414, Standardabweichung je Trade 2.23 R. Datenende 2026-11-19.

**Kriterium Summe > 6 %: traegt NICHT** (Vorsprung in 09-17/18-26/5J > 0: nein; B 18-26 nicht mehr als 1 SE unter <= 6 %: ja).

|  | n | Symbole | Ø R A gesamt | Ø R A 09-17 | Vorspr. 09-17 | Ø R A 18-26 | Vorspr. 18-26 | Ø R A 5J | Vorspr. 5J | Ø R A 2J | Vorspr. 2J | Ø R B 18-26 | SE 18-26 | Treffer A | Anteil <= -1,25 R (B) | Einsatz Median | Kosten R Ø | Ø R B 18-26 n. Kosten |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0,5-2 % | 3324 | 331 | +0.37 | +0.33 | +0.06 | +0.42 | +0.27 | +0.38 | +0.26 | +0.30 | +0.18 | +0.40 | 0.06 | 38% | 7% | 2,000 | 0.00 | +0.40 |
| 2-3 % | 3589 | 391 | +0.29 | +0.40 | +0.13 | +0.20 | +0.08 | +0.15 | +0.10 | +0.13 | +0.08 | +0.18 | 0.05 | 37% | 5% | 1,391 | 0.00 | +0.18 |
| 3-4 % | 1169 | 315 | +0.22 | +0.25 | +0.10 | +0.20 | -0.06 | +0.06 | -0.05 | +0.17 | +0.03 | +0.20 | 0.09 | 34% | 5% | 987 | 0.00 | +0.20 |
| 4-5 % | 323 | 148 | +0.60 | +0.65 | +0.52 | +0.58 | +0.08 | +0.33 | +0.00 | +0.89 | +0.48 | +0.56 | 0.15 | 38% | 7% | 759 | 0.00 | +0.56 |
| 5-6 % | 101 | 69 | +0.57 | -0.34 | -0.80 | +0.90 | +0.30 | +0.84 | +0.37 | -0.50 | -1.31 | +0.91 | 0.26 | 34% | 4% | 622 | 0.00 | +0.91 |
| 6-8 % | 47 | 28 | +1.12 | -0.53 | -1.11 | +1.56 | +1.06 | +1.90 | +1.68 | +1.89 | +1.86 | +1.53 | 0.37 | 49% | 4% | 519 | 0.06 | +1.46 |
| 8-10 % | 6 | 6 | +2.28 |  |  | +2.28 | +2.34 | +4.19 |  | +4.19 |  | +2.20 | 0.91 | 100% | 0% | 391 | 0.16 | +2.04 |
| ueber 10 % | 1 | 1 | +2.35 |  |  | +2.35 |  |  |  |  |  | +2.52 | 2.23 | 100% | 0% | 322 | 0.16 | +2.36 |
| Summe <= 6 % (LS-2) | 8506 | 414 | +0.33 | +0.35 | +0.10 | +0.30 | +0.12 | +0.23 | +0.12 | +0.23 | +0.09 | +0.29 | 0.03 | 37% | 6% | 1,518 | 0.00 | +0.29 |
| Summe > 6 % | 54 | 33 | +1.27 | -0.53 | -0.97 | +1.68 | +1.24 | +2.06 | +2.02 | +2.14 | +2.28 | +1.64 | 0.34 | 56% | 4% | 505 | 0.07 | +1.56 |


Haeufigkeit > 6 %: letzte 5 J in 4% der Wochen mindestens ein Signal (Ø 0.06 je Woche), letzte 2 J 5% (Ø 0.09).

## Anlass-Werte (alle Signale ab 2009, abgeschlossen)

| Symbol | n | R_A | R_B | ATRp_med |
|---|---|---|---|---|
| ANET | 16 | +0.60 | +0.64 | 3.5 |
| CRWD | 6 | -0.39 | -0.37 | 3.9 |
| NET | 9 | +0.95 | +0.98 | 4.6 |
| PANW | 19 | -0.04 | -0.06 | 3.0 |


## Juengste Hoch-ATR-Signale (180 Tage, R offen = Stand letzter Schluss)

| Symbol | Datum | ATRp | R_A | R_B | Art_B | offen |
|---|---|---|---|---|---|---|
| S92.DE | 2026-08-17 | 6.56 | -0.47 | -0.40 | stop | False |
| MRVL | 2026-08-19 | 7.75 | -1.00 | -1.01 | stop | False |


Kosten sind eine Annahme (4 EUR je Seite unter 500 EUR auf gettex), nicht aus dem Preisverzeichnis gelesen. Survivorship-Bias trifft die Hoch-ATR-Klassen vermutlich staerker als die ruhigen.
