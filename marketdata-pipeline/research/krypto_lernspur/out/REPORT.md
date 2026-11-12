# Lern-Spur-Regeln auf Krypto, mit Steuermodell (2026-11-12)

Daten: Yahoo, Tagesbasis in USD, 36 Coins, die es heute noch gibt und die bei Kraken handelbar sind (Survivorship-Bias), bis 2026-11-12. Kosten 0,50 % je Seite.

Coins: AAVE (ab 2020), ADA (ab 2017), ALGO (ab 2019), ATOM (ab 2019), AVAX (ab 2020), BAT (ab 2017), BCH (ab 2017), BTC (ab 2014), CRV (ab 2020), DASH (ab 2017), DOGE (ab 2017), DOT (ab 2020), EOS (ab 2017), ETC (ab 2017), ETH (ab 2017), FIL (ab 2017), GRT6719 (ab 2020), HBAR (ab 2019), ICP (ab 2021), INJ (ab 2020), KSM (ab 2019), LINK (ab 2017), LTC (ab 2014), MANA (ab 2017), NEAR (ab 2020), QNT (ab 2018), SAND (ab 2020), SNX (ab 2018), SOL (ab 2020), TRX (ab 2017), UNI7083 (ab 2020), VET (ab 2018), XLM (ab 2017), XRP (ab 2017), XTZ (ab 2017), ZEC (ab 2017)

| Variante | Regeln |
|---|---|
| K0 | LS-2 1:1: EMA20 kreuzt EMA50, Schluss > EMA200, EMA50 > EMA200, ATR% 0,5–6 %, Stop 1,5 ATR, Chandelier 3 ATR, Zeitausstieg 60 Tage |
| K1 | K0 ohne ATR%-Obergrenze |
| K2 | K1 + BTC ueber SMA200 |
| K3 | K2 ohne Zeitausstieg (nur Chandelier) |
| K4 | K3 mit Stop 2,5 ATR und Chandelier 4 ATR |

## Teil A: je Trade gegen Zufall

Zufall A = beliebiger Tag im selben Coin und Fenster, Zufall B = beliebiger Tag, an dem Trendregime (und ggf. BTC-Filter) ohnehin passen; beide mit gleichem Stop und Ausstieg.

| Variante | Fenster | Trades | Coins | Treffer | Ø Trade | Ø R | Zufall A Ø R | Zufall B Ø R | Vorsprung A / B | Median Tage | Trades >= 1 J | R-Anteil aus Trades >= 1 J |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| K0 | gesamt | 102 | 29 | 32 % | +7.3 % | +1.16 | +0.57 | +0.99 | +0.59 / +0.17 | 10 | 0 | 0 % |
| K0 | 2018–2021 | 24 | 14 | 46 % | +18.0 % | +2.90 | +0.26 | +1.31 | +2.64 / +1.59 | 10 | 0 | 0 % |
| K0 | 2022–heute | 70 | 29 | 27 % | +4.0 % | +0.59 | -0.03 | +0.88 | +0.62 / -0.29 | 10 | 0 | 0 % |
| K0 | letzte 2 J | 20 | 12 | 15 % | -3.1 % | -0.45 | -0.34 | +0.18 | -0.11 / -0.63 | 7 | 0 | 0 % |
| K1 | gesamt | 196 | 36 | 32 % | +7.5 % | +0.92 | +0.46 | +0.33 | +0.46 / +0.59 | 10 | 0 | 0 % |
| K1 | 2018–2021 | 86 | 31 | 40 % | +13.8 % | +1.50 | +0.96 | +0.76 | +0.54 / +0.74 | 10 | 0 | 0 % |
| K1 | 2022–heute | 100 | 36 | 25 % | +2.7 % | +0.46 | +0.15 | +0.08 | +0.31 / +0.38 | 9 | 0 | 0 % |
| K1 | letzte 2 J | 34 | 22 | 15 % | -2.0 % | -0.21 | +0.19 | -0.12 | -0.40 / -0.09 | 6 | 0 | 0 % |
| K2 | gesamt | 161 | 36 | 29 % | +6.3 % | +0.79 | +0.58 | +0.39 | +0.21 / +0.41 | 8 | 0 | 0 % |
| K2 | 2018–2021 | 69 | 29 | 35 % | +11.5 % | +1.32 | +0.71 | +0.97 | +0.61 / +0.35 | 7 | 0 | 0 % |
| K2 | 2022–heute | 82 | 36 | 24 % | +2.5 % | +0.39 | +0.20 | +0.20 | +0.19 / +0.18 | 8 | 0 | 0 % |
| K2 | letzte 2 J | 28 | 21 | 11 % | -2.1 % | -0.24 | +0.20 | -0.23 | -0.45 / -0.01 | 6 | 0 | 0 % |
| K3 | gesamt | 161 | 36 | 29 % | +6.3 % | +0.79 | +0.43 | +0.51 | +0.36 / +0.28 | 8 | 0 | 0 % |
| K3 | 2018–2021 | 69 | 29 | 35 % | +11.5 % | +1.32 | +0.70 | +0.27 | +0.62 / +1.05 | 7 | 0 | 0 % |
| K3 | 2022–heute | 82 | 36 | 24 % | +2.5 % | +0.39 | +0.15 | -0.03 | +0.23 / +0.42 | 8 | 0 | 0 % |
| K3 | letzte 2 J | 28 | 21 | 11 % | -2.1 % | -0.24 | -0.12 | -0.19 | -0.12 / -0.05 | 6 | 0 | 0 % |
| K4 | gesamt | 154 | 36 | 37 % | +25.2 % | +1.45 | +0.47 | +0.82 | +0.98 / +0.63 | 20 | 0 | 0 % |
| K4 | 2018–2021 | 65 | 29 | 43 % | +56.5 % | +3.11 | +1.39 | +1.62 | +1.73 / +1.49 | 20 | 0 | 0 % |
| K4 | 2022–heute | 79 | 36 | 33 % | +1.6 % | +0.20 | +0.37 | +0.20 | -0.18 / +0.00 | 20 | 0 | 0 % |
| K4 | letzte 2 J | 28 | 21 | 14 % | -7.4 % | -0.54 | -0.34 | -0.60 | -0.21 / +0.06 | 10 | 0 | 0 % |

## Teil B: Portfolio mit frischem Kapital 10.000 (nach Steuer, Annahme 35 %)

R = 1 % des aktuellen Kapitals, Risikobudget 3 R, hoechstens 30 % je Position. Steuer auf Gewinne aus Verkaeufen unter 1 Jahr, Freigrenze, Verlustvortrag; Steuer des laufenden Jahres noch nicht abgezogen. Halten: keine Steuer, solange nicht verkauft (nach 1 Jahr steuerfrei).

### Start 2018-01-01

| Strategie | Endkapital | CAGR | MaxDD | Trades | Ø investiert | Steuer gezahlt |
|---|---|---|---|---|---|---|
| K0 (R 1 %) | 18.635 | +7.3 % | -29 % | 76 | 7 % | 5.048 |
| K1 (R 1 %) | 22.487 | +9.6 % | -32 % | 148 | 10 % | 6.814 |
| K2 (R 1 %) | 17.388 | +6.4 % | -31 % | 115 | 7 % | 3.909 |
| K3 (R 1 %) | 17.382 | +6.4 % | -31 % | 115 | 7 % | 3.905 |
| K3 (R 2 %) | 25.299 | +11.0 % | -47 % | 109 | 12 % | 8.794 |
| K4 (R 1 %) | 25.956 | +11.4 % | -38 % | 102 | 9 % | 9.016 |
| K4 (R 2 %) | 49.500 | +19.8 % | -51 % | 100 | 16 % | 24.024 |
| BTC halten | 53.501 | +20.9 % | -82 % | 1 | 100 % | 0 |
| ETH halten | 26.344 | +11.6 % | -94 % | 1 | 100 % | 0 |
| BTC-T200 | 33.642 | +14.7 % | -68 % | – | – | 2.028 |
| BTC/ETH-T200 je 50 % | 81.736 | +26.8 % | -65 % | – | – | 14.244 |

### Start 2020-01-01

| Strategie | Endkapital | CAGR | MaxDD | Trades | Ø investiert | Steuer gezahlt |
|---|---|---|---|---|---|---|
| K0 (R 1 %) | 19.129 | +9.9 % | -30 % | 73 | 9 % | 5.324 |
| K1 (R 1 %) | 21.663 | +11.9 % | -32 % | 135 | 12 % | 6.367 |
| K2 (R 1 %) | 16.290 | +7.4 % | -31 % | 106 | 9 % | 3.322 |
| K3 (R 1 %) | 16.284 | +7.4 % | -31 % | 106 | 9 % | 3.318 |
| K3 (R 2 %) | 22.235 | +12.3 % | -47 % | 100 | 15 % | 7.077 |
| K4 (R 1 %) | 23.475 | +13.2 % | -37 % | 93 | 11 % | 7.698 |
| K4 (R 2 %) | 40.615 | +22.7 % | -51 % | 92 | 19 % | 18.825 |
| BTC halten | 101.481 | +40.3 % | -77 % | 1 | 100 % | 0 |
| ETH halten | 155.615 | +49.3 % | -79 % | 1 | 100 % | 0 |
| BTC-T200 | 52.492 | +27.3 % | -67 % | – | – | 5.125 |
| BTC/ETH-T200 je 50 % | 88.988 | +37.5 % | -55 % | – | – | 15.350 |

### Start 2022-01-01

| Strategie | Endkapital | CAGR | MaxDD | Trades | Ø investiert | Steuer gezahlt |
|---|---|---|---|---|---|---|
| K0 (R 1 %) | 11.872 | +3.6 % | -28 % | 55 | 9 % | 1.262 |
| K1 (R 1 %) | 11.833 | +3.5 % | -32 % | 76 | 11 % | 1.034 |
| K2 (R 1 %) | 10.768 | +1.5 % | -31 % | 58 | 8 % | 489 |
| K3 (R 1 %) | 10.764 | +1.5 % | -31 % | 58 | 8 % | 487 |
| K3 (R 2 %) | 11.322 | +2.6 % | -47 % | 54 | 12 % | 961 |
| K4 (R 1 %) | 10.057 | +0.1 % | -26 % | 53 | 7 % | 0 |
| K4 (R 2 %) | 9.609 | -0.8 % | -44 % | 53 | 13 % | 343 |
| BTC halten | 15.322 | +9.3 % | -67 % | 1 | 100 % | 0 |
| ETH halten | 5.400 | -11.8 % | -74 % | 1 | 100 % | 0 |
| BTC-T200 | 26.291 | +22.0 % | -35 % | – | – | 5.482 |
| BTC/ETH-T200 je 50 % | 20.332 | +15.8 % | -32 % | – | – | 3.658 |

### Start 2024-01-01

| Strategie | Endkapital | CAGR | MaxDD | Trades | Ø investiert | Steuer gezahlt |
|---|---|---|---|---|---|---|
| K0 (R 1 %) | 11.043 | +3.5 % | -28 % | 36 | 9 % | 798 |
| K1 (R 1 %) | 11.147 | +3.9 % | -32 % | 51 | 11 % | 662 |
| K2 (R 1 %) | 11.144 | +3.9 % | -32 % | 42 | 8 % | 694 |
| K3 (R 1 %) | 11.144 | +3.9 % | -32 % | 42 | 8 % | 694 |
| K3 (R 2 %) | 11.863 | +6.1 % | -48 % | 38 | 14 % | 1.264 |
| K4 (R 1 %) | 10.274 | +0.9 % | -28 % | 39 | 8 % | 400 |
| K4 (R 2 %) | 10.427 | +1.5 % | -46 % | 39 | 15 % | 815 |
| BTC halten | 16.543 | +19.4 % | -53 % | 1 | 100 % | 0 |
| ETH halten | 8.653 | -4.8 % | -68 % | 1 | 100 % | 0 |
| BTC-T200 | 13.136 | +10.2 % | -35 % | – | – | 988 |
| BTC/ETH-T200 je 50 % | 12.645 | +8.7 % | -32 % | – | – | 433 |

## Stand heute

BTC ueber SMA200: ja. Coins im Trendregime (Schluss > EMA200, EMA50 > EMA200): UNI7083, NEAR, BAT, ZEC, INJ, QNT. Signale heute (K2): keine. Signale der letzten 30 Tage (K2): DASH 2026-10-22, DASH 2026-10-26.

Grenzen: Survivorship-Bias (tote Coins fehlen), Kurse in USD, Steuermodell vereinfacht (FIFO je Position, Steuersatz angenommen, Soli/Kirchensteuer nicht), keine Zinsen auf Cash.
