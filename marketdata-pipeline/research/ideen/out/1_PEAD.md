# Idee 1: Drift nach Kursluecke mit Volumen (PEAD-Naeherung), 2026-11-12

Daten: Yahoo, 506 Aktien (heutiges Pipeline-Universum, Survivorship-Bias), bis 2026-11-12. Earnings-Termine fuer 195 US-Aktien. Kosten 0,10 % je Seite. Zufall A = gleicher Wert, gleiches Fenster, gleiche Haltedauer und gleicher Stop, beliebiger Tag.

- P1: Luecke >= 1 ATR, Volumen >= 2x Schnitt
- P2: P1 + Schluss >= Eroeffnung
- P3: P2 + Luecke >= 2 ATR
- PE: P2 an einem Earnings-Reaktionstag (nur US mit Terminen)

Hinweis: Der Vorsprung in Prozent ist die belastbarere Zahl. R teilt durch die ATR am Signaltag, die durch die Luecke selbst aufgeblaeht ist; das drueckt das R der echten Trades gegenueber Zufall.

| Variante | Fenster | Trades | Trades/Jahr | Treffer | Ø Trade | Median | Ø R | Zufall Ø Trade | Vorsprung % | Zufall Ø R | Vorsprung R |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P1 H20 | Entwicklung 2008–18 | 4645 | 422 | 54 % | +0.45 % | +0.68 % | +0.21 | +1.27 % | -0.82 % | +0.30 | -0.10 |
| P1 H20 | Pruefung 2019–26 | 3599 | 458 | 56 % | +1.65 % | +1.31 % | +0.30 | +1.32 % | +0.33 % | +0.24 | +0.06 |
| P1 H20 | letzte 2 J | 996 | 498 | 52 % | +1.37 % | +0.44 % | +0.24 | +1.59 % | -0.22 % | +0.29 | -0.05 |
| P1 H60 | Entwicklung 2008–18 | 4039 | 367 | 61 % | +3.32 % | +3.29 % | +0.95 | +3.82 % | -0.50 % | +1.03 | -0.08 |
| P1 H60 | Pruefung 2019–26 | 3113 | 396 | 59 % | +4.26 % | +3.26 % | +0.80 | +4.29 % | -0.03 % | +0.87 | -0.07 |
| P1 H60 | letzte 2 J | 829 | 415 | 54 % | +3.75 % | +1.94 % | +0.70 | +5.16 % | -1.41 % | +1.03 | -0.32 |
| P2 H20 | Entwicklung 2008–18 | 2819 | 256 | 55 % | +0.38 % | +0.68 % | +0.22 | +0.95 % | -0.57 % | +0.26 | -0.04 |
| P2 H20 | Pruefung 2019–26 | 2147 | 273 | 57 % | +1.74 % | +1.61 % | +0.35 | +1.43 % | +0.31 % | +0.29 | +0.06 |
| P2 H20 | letzte 2 J | 571 | 286 | 52 % | +1.22 % | +0.50 % | +0.25 | +2.05 % | -0.83 % | +0.41 | -0.16 |
| P2 H60 | Entwicklung 2008–18 | 2574 | 234 | 61 % | +3.59 % | +3.12 % | +1.03 | +4.03 % | -0.44 % | +1.05 | -0.02 |
| P2 H60 | Pruefung 2019–26 | 1945 | 247 | 58 % | +4.50 % | +3.19 % | +0.88 | +4.25 % | +0.25 % | +0.85 | +0.03 |
| P2 H60 | letzte 2 J | 500 | 250 | 55 % | +4.26 % | +1.91 % | +0.85 | +6.26 % | -2.00 % | +1.25 | -0.40 |
| P2 H60 +Stop | Entwicklung 2008–18 | 2763 | 251 | 28 % | +0.99 % | -3.19 % | +0.33 | +1.18 % | -0.19 % | +0.30 | +0.04 |
| P2 H60 +Stop | Pruefung 2019–26 | 2066 | 263 | 29 % | +2.10 % | -3.53 % | +0.42 | +1.55 % | +0.55 % | +0.30 | +0.12 |
| P2 H60 +Stop | letzte 2 J | 538 | 269 | 25 % | +1.42 % | -4.00 % | +0.23 | +2.11 % | -0.69 % | +0.42 | -0.19 |
| P3 H60 | Entwicklung 2008–18 | 931 | 85 | 64 % | +4.62 % | +4.12 % | +1.27 | +4.38 % | +0.24 % | +1.22 | +0.06 |
| P3 H60 | Pruefung 2019–26 | 855 | 109 | 59 % | +4.53 % | +2.75 % | +0.86 | +5.41 % | -0.89 % | +1.15 | -0.29 |
| P3 H60 | letzte 2 J | 232 | 116 | 54 % | +4.95 % | +0.85 % | +0.83 | +6.08 % | -1.13 % | +1.22 | -0.39 |
| PE H20 | Entwicklung 2008–18 | 854 | 78 | 61 % | +1.46 % | +1.82 % | +0.40 | +1.20 % | +0.26 % | +0.30 | +0.10 |
| PE H20 | Pruefung 2019–26 | 662 | 84 | 60 % | +2.10 % | +1.96 % | +0.42 | +1.58 % | +0.51 % | +0.31 | +0.12 |
| PE H20 | letzte 2 J | 164 | 82 | 57 % | +2.38 % | +1.61 % | +0.36 | +2.84 % | -0.46 % | +0.52 | -0.16 |
| PE H60 | Entwicklung 2008–18 | 815 | 74 | 69 % | +5.25 % | +5.26 % | +1.38 | +4.89 % | +0.36 % | +1.33 | +0.05 |
| PE H60 | Pruefung 2019–26 | 625 | 79 | 60 % | +4.44 % | +2.88 % | +0.90 | +5.68 % | -1.25 % | +1.09 | -0.20 |
| PE H60 | letzte 2 J | 149 | 75 | 48 % | +2.91 % | -1.32 % | +0.31 | +3.17 % | -0.26 % | +0.36 | -0.05 |
| PE H60 +Stop | Entwicklung 2008–18 | 835 | 76 | 34 % | +2.13 % | -2.66 % | +0.53 | +1.50 % | +0.63 % | +0.41 | +0.12 |
| PE H60 +Stop | Pruefung 2019–26 | 640 | 81 | 32 % | +3.07 % | -3.30 % | +0.59 | +2.42 % | +0.66 % | +0.42 | +0.17 |
| PE H60 +Stop | letzte 2 J | 154 | 77 | 25 % | +3.39 % | -3.64 % | +0.47 | +3.05 % | +0.34 % | +0.48 | -0.01 |

## P2 H60 nach Region

| Region | Fenster | Trades | Treffer | Ø Trade | Ø R |
|---|---|---|---|---|---|
| EU | Entwicklung 2008–18 | 1377 | 57 % | +2.89 % | +0.87 |
| EU | Pruefung 2019–26 | 1029 | 56 % | +2.73 % | +0.59 |
| US | Entwicklung 2008–18 | 1197 | 65 % | +4.39 % | +1.21 |
| US | Pruefung 2019–26 | 916 | 61 % | +6.49 % | +1.22 |

## P2 H60 nach Jahr (Signaljahr)

| Jahr | Trades | Ø Trade | Ø R |
|---|---|---|---|
| 2007 | 153 | -2.54 % | -0.70 |
| 2008 | 196 | -14.93 % | -2.42 |
| 2009 | 193 | +11.65 % | +2.11 |
| 2010 | 245 | +6.40 % | +1.37 |
| 2011 | 210 | +1.48 % | +0.42 |
| 2012 | 209 | +3.82 % | +1.18 |
| 2013 | 281 | +8.27 % | +2.28 |
| 2014 | 253 | +3.74 % | +1.30 |
| 2015 | 214 | +1.49 % | +0.42 |
| 2016 | 248 | +6.64 % | +1.66 |
| 2017 | 300 | +6.62 % | +2.06 |
| 2018 | 225 | +0.06 % | -0.17 |
| 2019 | 273 | +4.12 % | +0.84 |
| 2020 | 241 | +9.78 % | +1.10 |
| 2021 | 192 | +2.33 % | +0.70 |
| 2022 | 162 | -0.32 % | +0.15 |
| 2023 | 284 | +5.31 % | +1.20 |
| 2024 | 323 | +4.10 % | +0.99 |
| 2025 | 298 | +3.73 % | +0.83 |
| 2026 | 172 | +5.40 % | +0.91 |

Grenzen: Survivorship-Bias, Luecke ist nur eine Naeherung fuer Ueberraschungen (auch News, Uebernahmen), Earnings-Termine nur US und nur so weit Yahoo sie liefert, keine Steuern, Waehrungen nicht umgerechnet.
