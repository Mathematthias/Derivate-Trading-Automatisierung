# Zusatzfilter LS-2 (2026-11-08)

Signale ab 2009: n = 8525 (EUR/USD/CHF). Standardabweichung je Trade 2.23 R, also Standardfehler der Bestaetigungshaelfte rund 0.03 R fuer die Basis. Absolute R mit ~+0,07 R Simulationsbias und Survivorship-Bias; massgeblich ist der Abstand zur Basis.

"traegt" = in Entdeckung, Bestaetigung und letzten 5 Jahren ueber der Basis und in der Bestaetigung mindestens 1 Standardfehler darueber. 16 Filter getestet: Einer davon besteht das rein zufaellig mit einer Wahrscheinlichkeit, die man nicht ignorieren sollte.

|  | n | Ø R 09-17 | Ø R 18-26 | Ø R 5J | Wochen >=1 (5J) | Wochen >=2 (5J) | PF Trades/J | PF Ø R | PF Ø R 5J | PF EUR/J | PF DD R | traegt |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Basis LS-2 | 8525 | 0.35 | 0.32 | 0.25 | 97% | 93% | 60.3 | 0.56 | 0.51 | 1,697 | -23.5 | – |
| Ueberdehnung <= 3 ATR | 8195 | 0.35 | 0.34 | 0.27 | 97% | 93% | 60.0 | 0.49 | 0.44 | 1,471 | -18.5 | – |
| Ueberdehnung <= 2 ATR | 6747 | 0.35 | 0.34 | 0.22 | 97% | 92% | 59.1 | 0.53 | 0.42 | 1,556 | -26.0 | – |
| RSI14 <= 70 | 8041 | 0.35 | 0.34 | 0.26 | 97% | 93% | 59.5 | 0.53 | 0.42 | 1,567 | -29.3 | – |
| Volumen >= 1,0x 20T | 3678 | 0.41 | 0.26 | 0.19 | 90% | 77% | 56.2 | 0.36 | 0.15 | 1,007 | -20.2 | – |
| Volumen >= 1,5x 20T | 1199 | 0.38 | 0.14 | 0.08 | 58% | 31% | 38.1 | 0.22 | 0.06 | 424 | -20.9 | – |
| Naehe 52W-Hoch <= 10 % | 7287 | 0.34 | 0.33 | 0.31 | 95% | 89% | 56.7 | 0.46 | 0.41 | 1,297 | -31.7 | – |
| Naehe 52W-Hoch <= 20 % | 8441 | 0.35 | 0.33 | 0.26 | 97% | 93% | 59.1 | 0.53 | 0.37 | 1,567 | -23.5 | – |
| Abstand 52W-Hoch > 10 % (Gegenprobe) | 1238 | 0.39 | 0.29 | -0.02 | 71% | 42% | 40.4 | 0.36 | 0.03 | 724 | -26.0 | – |
| 6M-Momentum > 0 | 7559 | 0.33 | 0.30 | 0.23 | 96% | 90% | 59.1 | 0.44 | 0.30 | 1,294 | -41.8 | – |
| 12M-Momentum > 0 | 8061 | 0.37 | 0.34 | 0.28 | 97% | 92% | 60.8 | 0.48 | 0.39 | 1,447 | -28.6 | – |
| 6M-Momentum obere Haelfte | 5066 | 0.35 | 0.28 | 0.22 | 95% | 86% | 55.3 | 0.33 | 0.18 | 899 | -30.9 | – |
| EMA200 steigt (20 HT) | 7784 | 0.35 | 0.32 | 0.25 | 97% | 92% | 58.6 | 0.55 | 0.40 | 1,610 | -33.7 | – |
| kein Gap-Tag (|Tagesbewegung| <= 2 ATR) | 8173 | 0.35 | 0.33 | 0.26 | 97% | 92% | 61.0 | 0.47 | 0.39 | 1,431 | -34.7 | – |
| S&P 500 ueber SMA200 | 7556 | 0.38 | 0.28 | 0.26 | 80% | 76% | 54.8 | 0.54 | 0.51 | 1,485 | -23.5 | – |
| Marktbreite >= 50 % ueber EMA50 | 7210 | 0.36 | 0.30 | 0.24 | 76% | 72% | 51.5 | 0.48 | 0.43 | 1,235 | -26.5 | – |

