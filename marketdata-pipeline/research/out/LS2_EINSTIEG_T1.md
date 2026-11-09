# LS-2: Einstieg Schluss T gegen Eroeffnung T+1 (2026-11-09)

Signale ab 2009: n = 8526, Daten bis 2026-11-05, 417 Werte EUR/USD/CHF. Raus wegen unbrauchbarer Eroeffnung: 0. Eroeffnung schon unter Stop: 46. Absolute R mit Survivorship- und Simulationsbias, ohne Kosten und Steuern. Protokoll im Kopf von `research/einstieg_t1.py`.

Kontrolle: Basis LS-2 im Bericht vom 2026-11-08 n 8.525, Ø R 0,35 / 0,32 / 0,25 (09-17 / 18-26 / 5J).

## 1 Varianten

|  | n | Ø R | SE | Ø R 09-17 | Ø R 18-26 | Ø R 5J | Ø R 2J | Δ zu A | SE Δ | Δ 5J |
|---|---|---|---|---|---|---|---|---|---|---|
| A Schluss T (Backtest) | 8526 | 0.34 | 0.02 | 0.35 | 0.32 | 0.26 | 0.32 | 0.00 | 0.00 | 0.00 |
| B Eroeffnung T+1 (live) | 8480 | 0.33 | 0.02 | 0.35 | 0.31 | 0.25 | 0.31 | -0.02 | 0.00 | -0.02 |
| C1 B, kein Gap > +1,0 ATR | 8398 | 0.33 | 0.02 | 0.35 | 0.31 | 0.24 | 0.30 | -0.01 | 0.00 | -0.01 |
| C2 B, kein Gap > +0,5 ATR | 8075 | 0.33 | 0.02 | 0.35 | 0.31 | 0.24 | 0.32 | 0.01 | 0.00 | 0.01 |

## 2 Zufall

|  | n | Ø R gesamt | Ø R 09-17 | Ø R 18-26 | Ø R 5J | Ø R 2J |
|---|---|---|---|---|---|---|
| Zufall alle Tage, A | 48767 | 0.24 | 0.33 | 0.17 | 0.10 | 0.14 |
| Zufall alle Tage, B | 48500 | 0.23 | 0.31 | 0.16 | 0.09 | 0.14 |
| Zufall Trendtage, A | 30516 | 0.21 | 0.26 | 0.15 | 0.10 | 0.12 |
| Zufall Trendtage, B | 30366 | 0.20 | 0.25 | 0.14 | 0.09 | 0.11 |


|  | Vorsprung gesamt | Vorsprung 09-17 | Vorsprung 18-26 | Vorsprung 5J | Vorsprung 2J |
|---|---|---|---|---|---|
| LS-2 A gegen Zufall alle Tage | 0.09 | 0.02 | 0.15 | 0.16 | 0.18 |
| LS-2 B gegen Zufall alle Tage | 0.10 | 0.04 | 0.15 | 0.16 | 0.17 |
| LS-2 A gegen Zufall Trendtage | 0.13 | 0.09 | 0.17 | 0.16 | 0.20 |
| LS-2 B gegen Zufall Trendtage | 0.13 | 0.11 | 0.17 | 0.15 | 0.20 |

## 3 Gap nach dem Signal

|  | n | Ø Gap ATR | Median | Ø Gap in R | > +0,5 ATR | > +1 ATR | < -0,5 ATR | Eroeffnung <= Stop | Ø Ist-Risiko R | P95 Ist-Risiko R | |Gap| > 5 ATR (n) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| LS-2 Signale | 8526 | 0.02 | 0.02 | 0.01 | 4.8% | 1.0% | 4.3% | 0.54% | 1.01 | 1.33 | 3 |
| LS-2 Signale 5J | 2347 | 0.02 | 0.02 | 0.01 | 4.9% | 0.9% | 4.0% | 0.34% | 1.01 | 1.33 | 1 |
| Zufall alle Tage | 48767 | 0.02 | 0.02 | 0.01 | 5.8% | 1.1% | 5.5% | 0.55% | 1.01 | 1.35 | 22 |
| Zufall Trendtage | 30516 | 0.02 | 0.02 | 0.01 | 5.6% | 1.2% | 5.5% | 0.49% | 1.01 | 1.35 | 16 |
| LS-2 EUR | 3710 | 0.01 | 0.01 | 0.01 | 4.3% | 0.8% | 4.5% | 0.67% | 1.01 | 1.31 | 1 |
| LS-2 USD | 4379 | 0.02 | 0.02 | 0.01 | 5.1% | 1.1% | 4.2% | 0.41% | 1.01 | 1.34 | 2 |
| LS-2 CHF | 437 | 0.02 | 0.00 | 0.01 | 4.6% | 0.9% | 3.9% | 0.69% | 1.01 | 1.32 | 0 |

## 4 Regionen

|  | n | Ø R A | Ø R B | Δ | SE Δ |
|---|---|---|---|---|---|
| EUR | 3685 | 0.24 | 0.22 | -0.02 | 0.00 |
| USD | 4361 | 0.43 | 0.41 | -0.02 | 0.00 |
| CHF | 434 | 0.49 | 0.47 | -0.02 | 0.01 |

## 5 Gap-Eimer (ATR)

|  | n | Ø R A | Ø R B | SE B | Ø R B 5J | n 5J |
|---|---|---|---|---|---|---|
| < -0,5 | 323 | -0.22 | 0.27 | 0.10 | 0.33 | 87 |
| -0,5 bis 0 | 3564 | 0.24 | 0.35 | 0.04 | 0.27 | 1003 |
| 0 bis +0,5 | 4188 | 0.43 | 0.32 | 0.03 | 0.21 | 1133 |
| +0,5 bis +1 | 323 | 0.73 | 0.29 | 0.13 | 0.11 | 95 |
| > +1 | 82 | 1.63 | 0.54 | 0.32 | 1.36 | 21 |

## 6 Portfolio (3 R a 50 EUR, 12.000 EUR, CHF-Deckel)

|  | Trades/J | Ø R | Ø R 5J | EUR/J | EUR/J 5J | DD R | Pos max |
|---|---|---|---|---|---|---|---|
| A Schluss T (Backtest) | 60.5 | 0.56 | 0.51 | 1,686 | 1,721 | -23.5 | 9 |
| B Eroeffnung T+1 (live) | 55.9 | 0.47 | 0.44 | 1,325 | 1,364 | -19.1 | 8 |
| C1 B, kein Gap > +1,0 ATR | 55.5 | 0.55 | 0.43 | 1,525 | 1,348 | -20.2 | 9 |
| C2 B, kein Gap > +0,5 ATR | 56.3 | 0.50 | 0.35 | 1,395 | 1,111 | -23.1 | 9 |

