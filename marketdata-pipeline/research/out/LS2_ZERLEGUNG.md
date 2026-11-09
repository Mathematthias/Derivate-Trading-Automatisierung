# LS-2: Zerlegung Portfolio gegen alle Signale (2026-11-09)

Live-Einstieg Eroeffnung T+1, n = 8181 Signale nach CHF-Deckel, ohne Kosten, Survivorship- und Simulationsbias.

## 1 Alle Signale

|  | n | Ø R | SE | Median | Treffer | Ø Gewinn | Ø Verlust | Ø ATR% | Ø R 5J |
|---|---|---|---|---|---|---|---|---|---|
| Q1 ruhigste | 1637 | 0.35 | 0.06 | -0.69 | 36.5% | 2.63 | -0.96 | 1.44% | 0.43 |
| Q2 | 1636 | 0.35 | 0.05 | -0.64 | 39.3% | 2.34 | -0.94 | 1.86% | 0.30 |
| Q3 | 1636 | 0.29 | 0.05 | -0.72 | 35.5% | 2.49 | -0.91 | 2.21% | 0.25 |
| Q4 | 1636 | 0.30 | 0.05 | -0.62 | 37.2% | 2.32 | -0.90 | 2.66% | 0.16 |
| Q5 unruhigste | 1636 | 0.32 | 0.06 | -0.69 | 35.1% | 2.54 | -0.88 | 3.70% | 0.14 |
| alle | 8181 | 0.32 | 0.02 | -0.68 | 36.7% | 2.46 | -0.92 | 2.37% | 0.23 |


|  | n | Ø R | SE | Median | Treffer | Ø Gewinn | Ø Verlust |
|---|---|---|---|---|---|---|---|
| Rang 1 (ruhigster des Tages) | 3102 | 0.37 | 0.04 | -0.67 | 37.2% | 2.55 | -0.93 |
| Rang 2 | 1953 | 0.31 | 0.05 | -0.66 | 37.0% | 2.38 | -0.91 |
| Rang 3 und mehr | 3126 | 0.28 | 0.04 | -0.69 | 36.0% | 2.42 | -0.92 |
| einziges Signal des Tages | 1149 | 0.41 | 0.07 | -0.70 | 35.0% | 2.83 | -0.89 |
| Tage mit >= 3 Signalen | 5552 | 0.30 | 0.03 | -0.67 | 37.0% | 2.39 | -0.93 |

## 2 Zerlegung

|  | Ø R (Mittel) | Trades/J | Ø R 5J | Streuung SD | min | max |
|---|---|---|---|---|---|---|
| Alle Signale, ungewichtet | 0.32 | 458.5 | 0.23 |  |  |  |
| Portfolio, niedrigste ATR% (Regel) | 0.47 | 55.9 | 0.44 |  |  |  |
| Portfolio, zufaellige Auswahl (50x) | 0.42 | 56.0 | 0.25 | 0.05 | 0.31 | 0.58 |
| Portfolio, hoechste ATR% | 0.45 | 55.5 | 0.16 |  |  |  |
| Regel, 1 % Signale entfernt (50x) | 0.46 | 55.8 | 0.41 | 0.02 | 0.41 | 0.52 |

## 3 Genommene Trades

|  | n | Ø R | SE | Median | Treffer | Ø Gewinn | Ø Verlust | P10 | P90 | Anteil Summe R aus besten 5 % | Ø ATR% | Ø Haltetage (Kalender) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Regel-Portfolio | 997 | 0.47 | 0.07 | -0.63 | 39.2% | 2.61 | -0.90 | -1.15 | 3.70 | 80% | 2.20% | 29 |


Bootstrap ueber Kalenderjahre, 95 %: 0.32 bis 0.63 R


| Jahr | n | Ø R | Summe R |
|---|---|---|---|
| 2009 | 28 | 0.42 | 11.8 |
| 2010 | 52 | 0.44 | 22.7 |
| 2011 | 57 | 0.11 | 6.2 |
| 2012 | 57 | 0.82 | 46.6 |
| 2013 | 58 | 0.70 | 40.5 |
| 2014 | 52 | 0.76 | 39.6 |
| 2015 | 61 | 0.03 | 1.9 |
| 2016 | 61 | 0.28 | 17.2 |
| 2017 | 57 | 0.94 | 53.5 |
| 2018 | 59 | 0.19 | 11.5 |
| 2019 | 53 | 0.96 | 50.6 |
| 2020 | 41 | 0.56 | 22.8 |
| 2021 | 59 | 0.25 | 14.9 |
| 2022 | 59 | -0.06 | -3.6 |
| 2023 | 57 | 0.89 | 50.5 |
| 2024 | 67 | 0.88 | 59.0 |
| 2025 | 65 | 0.16 | 10.6 |
| 2026 | 54 | 0.31 | 16.5 |

## 4 Euro

|  | Ø Einsatz EUR | Anteil gedeckelt 2.000 EUR | Ø effektives R EUR | Ø EUR je Trade | EUR/J nominal (R x 50) | EUR/J mit Deckel | Anteil Einsatz < 1.000 EUR | Anteil Einsatz < 500 EUR |
|---|---|---|---|---|---|---|---|---|
| Regel-Portfolio | 1,593 | 28% | 47.74 | 22.64 | 1,325 | 1,265 | 10% | 0% |

