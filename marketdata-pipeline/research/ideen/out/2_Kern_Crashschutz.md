# Idee 2: Kern-Rotation mit Crash-Schutz, 2026-11-12

Daten: Yahoo, Tagesbasis, bis 2026-11-11. Renditen in USD (Signal-ETFs), Kosten 0,10 % je Seite, Cash-Zins ueber BIL (US-T-Bills, Naeherung fuer Tagesgeld). Keine Steuern.

## Entwicklung 2008-06 bis 2018

| Variante | CAGR | Vola | MaxDD | CAGR / MaxDD |
|---|---|---|---|---|
| Basis, Cash ohne Zins | +8.6 % | 15.2 % | -19.4 % | 0.44 |
| Basis, Cash verzinst | +8.6 % | 15.2 % | -19.4 % | 0.44 |
| + Crash-Filter monatlich | +7.7 % | 14.2 % | -20.0 % | 0.38 |
| + Crash-Filter taeglich (Band 2 %) | +6.7 % | 13.2 % | -16.9 % | 0.39 |
| + Vol-Ziel 12 % | +7.7 % | 12.5 % | -17.2 % | 0.45 |
| S&P 500 halten (SPY) | +8.8 % | 20.1 % | -47.2 % | 0.19 |
| MSCI World halten (URTH, ab 2012) | +9.0 % | 14.9 % | -18.9 % | 0.48 |

## Pruefung 2019 bis heute

| Variante | CAGR | Vola | MaxDD | CAGR / MaxDD |
|---|---|---|---|---|
| Basis, Cash ohne Zins | +17.7 % | 20.5 % | -25.3 % | 0.70 |
| Basis, Cash verzinst | +17.8 % | 20.5 % | -25.3 % | 0.70 |
| + Crash-Filter monatlich | +13.2 % | 17.9 % | -18.7 % | 0.70 |
| + Crash-Filter taeglich (Band 2 %) | +15.0 % | 18.0 % | -18.6 % | 0.81 |
| + Vol-Ziel 12 % | +10.5 % | 14.1 % | -22.6 % | 0.46 |
| S&P 500 halten (SPY) | +16.9 % | 19.2 % | -33.7 % | 0.50 |
| MSCI World halten (URTH, ab 2012) | +14.9 % | 18.5 % | -34.0 % | 0.44 |

## gesamt

| Variante | CAGR | Vola | MaxDD | CAGR / MaxDD |
|---|---|---|---|---|
| Basis, Cash ohne Zins | +12.4 % | 17.7 % | -25.3 % | 0.49 |
| Basis, Cash verzinst | +12.4 % | 17.7 % | -25.3 % | 0.49 |
| + Crash-Filter monatlich | +10.0 % | 15.9 % | -20.0 % | 0.50 |
| + Crash-Filter taeglich (Band 2 %) | +10.2 % | 15.5 % | -19.4 % | 0.52 |
| + Vol-Ziel 12 % | +8.9 % | 13.2 % | -22.6 % | 0.39 |
| S&P 500 halten (SPY) | +12.2 % | 19.7 % | -47.2 % | 0.26 |
| MSCI World halten (URTH, ab 2012) | +12.1 % | 16.9 % | -34.0 % | 0.35 |

Zeit ganz in Cash (nur Crash-Filter): R1 20 %, R2 20 %. Umschlag je Jahr (Summe der Gewichtsaenderungen): R0 6.4, R0z 6.4, R1 6.1, R2 6.7, R3 5.9

## Jahresrenditen

| Jahr | R0z | R1 | R2 | R3 | SPY | URTH |
|---|---|---|---|---|---|---|
| 2008 | +0.2 % | +0.5 % | +0.5 % | -1.9 % | -28.5 % | – |
| 2009 | +18.6 % | +23.0 % | +18.4 % | +8.8 % | +26.4 % | – |
| 2010 | +6.7 % | +6.6 % | +5.0 % | +9.1 % | +15.1 % | – |
| 2011 | +4.8 % | -2.3 % | -4.8 % | +6.2 % | +1.9 % | – |
| 2012 | +2.9 % | +2.8 % | +3.8 % | +2.4 % | +16.0 % | +14.7 % |
| 2013 | +24.1 % | +24.1 % | +24.1 % | +22.0 % | +32.3 % | +26.7 % |
| 2014 | +14.6 % | +14.6 % | +14.6 % | +14.3 % | +13.5 % | +4.4 % |
| 2015 | -3.9 % | -5.4 % | -5.8 % | -3.1 % | +1.2 % | -0.6 % |
| 2016 | +4.8 % | +4.0 % | +2.6 % | +5.4 % | +12.0 % | +7.3 % |
| 2017 | +21.6 % | +21.6 % | +21.6 % | +21.3 % | +21.7 % | +22.9 % |
| 2018 | -0.5 % | -3.4 % | -4.6 % | -0.6 % | -4.6 % | -8.6 % |
| 2019 | +17.1 % | +10.7 % | +12.7 % | +14.6 % | +31.2 % | +28.1 % |
| 2020 | +29.7 % | +30.7 % | +23.3 % | +4.9 % | +18.3 % | +15.8 % |
| 2021 | +16.5 % | +16.5 % | +16.5 % | +8.5 % | +28.7 % | +22.3 % |
| 2022 | -3.2 % | -7.3 % | -3.4 % | -2.4 % | -18.2 % | -18.0 % |
| 2023 | +23.4 % | +8.1 % | +16.5 % | +15.8 % | +26.2 % | +23.9 % |
| 2024 | +22.6 % | +22.6 % | +22.6 % | +18.0 % | +24.9 % | +18.7 % |
| 2025 | +9.6 % | +10.9 % | +11.4 % | +6.9 % | +17.7 % | +21.4 % |
| 2026 | +27.0 % | +14.9 % | +20.4 % | +17.5 % | +12.3 % | +11.6 % |

Grenzen: kein Waehrungseffekt (Vehikel in EUR bei Trade Republic), BIL statt Tagesgeld, Crash-Filter misst nur SPY. Steuer: Crash-Filter realisiert Gewinne frueher.
