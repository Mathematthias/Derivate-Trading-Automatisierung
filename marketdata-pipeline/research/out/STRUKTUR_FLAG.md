# Struktur-Flag und Strukturstop (Messung 2026-11-14)

Reine Messung, aendert keine Regel. Protokoll im Kopf von research/struktur_flag.py. Survivorship-Bias, Aktien ohne Kosten und Steuern.

## Aktien: LS-2-Signale

Signale 2009-02-12 bis 2026-11-11, 413 Werte, n = 8489 (Live-Variante B). Zufall: 3 % der Trendtage je Wert, gleiche Simulation.

### M1 Treppen-Flag je Signal

| Treppe am Signaltag | n | Ø R | SE | Median | Treffer | voller Stop | Anteil | Ø R 5J | Zufall Trendtage Ø R | Zufall n |
|---|---|---|---|---|---|---|---|---|---|---|
| aufwaerts | 1228 | 0.26 | 0.06 | -0.68 | 0.35 | 0.37 | 0.14 | 0.18 | 0.16 | 13937.00 |
| gemischt | 3925 | 0.35 | 0.04 | -0.70 | 0.37 | 0.37 | 0.46 | 0.23 | 0.26 | 11027.00 |
| abwaerts | 3336 | 0.34 | 0.04 | -0.64 | 0.38 | 0.37 | 0.39 | 0.31 | 0.30 | 5427.00 |
| alle | 8489 | 0.33 | 0.02 | -0.67 | 0.37 | 0.37 | 1.00 | 0.25 | 0.22 | 30392.00 |

### M1 Treppen-Flag im Portfolio

| Portfolio (3 R a 50 EUR) | Trades/J | Ø R | Ø R 5J | EUR/J | EUR/J 5J | DD R | Treffer |
|---|---|---|---|---|---|---|---|
| alle Signale (LS-2 heute) | 55.94 | 0.47 | 0.44 | 1265 | 1288 | -18.94 | 0.39 |
| ohne Treppe abwaerts | 52.86 | 0.39 | 0.32 | 1004 | 866 | -26.96 | 0.38 |
| nur Treppe aufwaerts | 34.10 | 0.31 | 0.33 | 519 | 507 | -36.92 | 0.36 |

### M2a Lage des ATR-Stops zum letzten Swing-Tief

| Lage ATR-Stop | n | Ø R | SE | Median | Treffer | voller Stop | Anteil | Ø R 5J |
|---|---|---|---|---|---|---|---|---|
| Stop > 0,5 ATR unter Swing-Tief | 58 | 0.56 | 0.33 | -0.54 | 0.40 | 0.40 | 0.01 | 0.53 |
| Stop 0-0,5 ATR unter Swing-Tief | 125 | 0.36 | 0.21 | -0.76 | 0.37 | 0.37 | 0.01 | -0.23 |
| Stop 0-0,25 ATR ueber Swing-Tief | 168 | 0.28 | 0.17 | -0.61 | 0.39 | 0.36 | 0.02 | 0.05 |
| Stop 0,25-1 ATR ueber Swing-Tief | 930 | 0.29 | 0.07 | -0.70 | 0.37 | 0.36 | 0.11 | 0.20 |
| Stop > 1 ATR ueber Swing-Tief | 7205 | 0.34 | 0.03 | -0.67 | 0.37 | 0.37 | 0.85 | 0.27 |
| kein Swing-Tief (<= 120 HT) | 3 | -7.65 | 7.65 | 0.00 | 0.00 | 0.33 | 0.00 |  |

### M2b Strukturstop min(ATR-Stop, Swing-Tief - 0,5 ATR)

| Trades | n | Ø Stopabstand ATR | P90 Stopabstand ATR | Ø R ATR-Stop | Ø R Strukturstop | Δ gepaart | SE Δ | voller Stop ATR | voller Stop Struktur | Δ 5J |
|---|---|---|---|---|---|---|---|---|---|---|
| alle | 8489 | 4.43 | 6.29 | 0.33 | 0.15 | -0.18 | 0.02 | 0.37 | 0.05 | -0.13 |
| Stop geaendert | 8428 | 4.45 | 6.30 | 0.33 | 0.15 | -0.18 | 0.02 | 0.37 | 0.04 | -0.14 |
| Stop gleich | 61 | 1.50 | 1.50 | 0.16 | 0.16 | 0.00 | 0.00 | 0.39 | 0.39 | 0.00 |

| Portfolio (3 R a 50 EUR) | Trades/J | Ø R | Ø R 5J | EUR/J | EUR/J 5J | DD R | Treffer |
|---|---|---|---|---|---|---|---|
| ATR-Stop (LS-2 heute) | 55.94 | 0.47 | 0.44 | 1265 | 1288 | -18.94 | 0.39 |
| Strukturstop | 72.12 | 0.18 | 0.08 | 685 | 328 | -23.01 | 0.46 |

## Krypto: Vorwaertsrenditen je Treppe

36 Coins, Tagesschluss USD, ab 2018. Renditen ueberlappen, Standardfehler darum nicht angegeben.

### alle Coins, alle Tage, ab 2018

| Treppe | n | Anteil | Ø 20T | Median 20T | 20T > 0 | Ø 60T | Median 60T | 60T > 0 |
|---|---|---|---|---|---|---|---|---|
| aufwaerts | 27659 | 29% | +2.8% | -3.1% | 43% | +13.5% | -6.1% | 43% |
| gemischt | 37925 | 40% | +3.4% | -1.8% | 46% | +11.0% | -4.9% | 44% |
| abwaerts | 29242 | 31% | +3.0% | -0.9% | 48% | +11.0% | -1.0% | 49% |
| alle | 94826 | 100% | +3.1% | -1.9% | 46% | +11.7% | -4.0% | 45% |

### alle Coins, alle Tage, ab 2022

| Treppe | n | Anteil | Ø 20T | Median 20T | 20T > 0 | Ø 60T | Median 60T | 60T > 0 |
|---|---|---|---|---|---|---|---|---|
| aufwaerts | 16979 | 27% | -0.9% | -4.4% | 39% | +2.5% | -8.3% | 39% |
| gemischt | 26057 | 41% | +0.9% | -2.8% | 43% | +2.9% | -7.0% | 41% |
| abwaerts | 20983 | 33% | +1.2% | -1.9% | 45% | +3.6% | -4.2% | 44% |
| alle | 64019 | 100% | +0.5% | -2.9% | 43% | +3.0% | -6.3% | 41% |

### alle Coins, Donchian-Einstiege, ab 2018

| Treppe | n | Anteil | Ø 20T | Median 20T | 20T > 0 | Ø 60T | Median 60T | 60T > 0 |
|---|---|---|---|---|---|---|---|---|
| aufwaerts | 1414 | 46% | +7.7% | -1.2% | 48% | +18.3% | -5.5% | 45% |
| gemischt | 1222 | 40% | +10.4% | +2.0% | 54% | +18.3% | +0.3% | 50% |
| abwaerts | 436 | 14% | +13.3% | +4.6% | 60% | +23.7% | +2.8% | 55% |
| alle | 3072 | 100% | +9.6% | +1.0% | 52% | +19.0% | -1.5% | 48% |

### alle Coins, Donchian-Einstiege, ab 2022

| Treppe | n | Anteil | Ø 20T | Median 20T | 20T > 0 | Ø 60T | Median 60T | 60T > 0 |
|---|---|---|---|---|---|---|---|---|
| aufwaerts | 783 | 43% | +2.2% | -3.7% | 42% | +3.7% | -9.6% | 37% |
| gemischt | 781 | 42% | +8.6% | -0.3% | 50% | +7.2% | -2.6% | 46% |
| abwaerts | 274 | 15% | +14.3% | +5.8% | 59% | +14.4% | +1.5% | 53% |
| alle | 1838 | 100% | +6.7% | -1.1% | 48% | +6.8% | -4.8% | 43% |

### BTC/ETH, alle Tage, ab 2018

| Treppe | n | Anteil | Ø 20T | Median 20T | 20T > 0 | Ø 60T | Median 60T | 60T > 0 |
|---|---|---|---|---|---|---|---|---|
| aufwaerts | 2261 | 36% | +3.7% | +0.8% | 52% | +14.7% | +5.4% | 55% |
| gemischt | 2402 | 38% | +1.3% | -0.2% | 49% | +5.4% | +0.1% | 50% |
| abwaerts | 1610 | 26% | +3.4% | +1.2% | 55% | +8.6% | +5.2% | 58% |
| alle | 6273 | 100% | +2.7% | +0.5% | 52% | +9.6% | +3.3% | 54% |

### BTC/ETH, alle Tage, ab 2022

| Treppe | n | Anteil | Ø 20T | Median 20T | 20T > 0 | Ø 60T | Median 60T | 60T > 0 |
|---|---|---|---|---|---|---|---|---|
| aufwaerts | 1220 | 34% | +0.8% | -0.6% | 48% | +4.6% | +1.1% | 51% |
| gemischt | 1332 | 37% | +2.2% | +0.0% | 50% | +4.2% | +1.9% | 53% |
| abwaerts | 1006 | 28% | +0.1% | -0.5% | 49% | +3.7% | +1.8% | 54% |
| alle | 3558 | 100% | +1.1% | -0.4% | 49% | +4.2% | +1.6% | 52% |

### BTC/ETH, Donchian-Einstiege, ab 2018

| Treppe | n | Anteil | Ø 20T | Median 20T | 20T > 0 | Ø 60T | Median 60T | 60T > 0 |
|---|---|---|---|---|---|---|---|---|
| aufwaerts | 154 | 56% | +5.8% | +1.2% | 52% | +22.0% | +12.1% | 60% |
| gemischt | 92 | 34% | +3.6% | +1.5% | 54% | +1.8% | +1.4% | 52% |
| abwaerts | 28 | 10% | +11.3% | +9.0% | 93% | +12.5% | +11.1% | 68% |
| alle | 274 | 100% | +5.6% | +2.5% | 57% | +14.3% | +6.4% | 58% |

### BTC/ETH, Donchian-Einstiege, ab 2022

| Treppe | n | Anteil | Ø 20T | Median 20T | 20T > 0 | Ø 60T | Median 60T | 60T > 0 |
|---|---|---|---|---|---|---|---|---|
| aufwaerts | 69 | 47% | -1.3% | -2.7% | 36% | +2.9% | -1.1% | 49% |
| gemischt | 63 | 43% | +3.6% | -0.3% | 49% | +4.0% | +4.9% | 56% |
| abwaerts | 15 | 10% | +11.1% | +8.4% | 93% | +9.1% | +1.8% | 67% |
| alle | 147 | 100% | +2.1% | -0.8% | 48% | +4.0% | +1.8% | 54% |

### Stand heute (Kontrolle)

- BTC am 2026-11-14: Treppe abwaerts, Schluss 67,187; letzte Swing-Hochs 81,890 (2026-10-29), 81,080 (2026-11-04); letzte Swing-Tiefs 80,337 (2026-10-08), 79,736 (2026-10-15)
- ETH am 2026-11-14: Treppe abwaerts, Schluss 1,907; letzte Swing-Hochs 2,523 (2026-10-21), 2,446 (2026-11-04); letzte Swing-Tiefs 2,321 (2026-10-15), 2,173 (2026-10-30)
