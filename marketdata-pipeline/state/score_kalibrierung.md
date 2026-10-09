# Score-Kalibrierung L12/L23 — 2026-10-09

Geschlossene Trades mit R: **43**, davon mit Score: **6**, mit dokumentiertem Risiko: 21.
Score-Quellen: Journal-Notiz 4, alt X/7 2.

**Kein Urteil (L28):** 6 von mindestens 20 gescorten Trades. Die Tabelle ist ein Zwischenstand, keine Evidenz.

| Score-Band | n | Treffer | Quote | Wilson 95 % | Ø R | Median R | Ø MFE |
|---|---|---|---|---|---|---|---|
| < 5,0 (kein GO) | 0 | 0 | — | — | — | — | — |
| 5,0-5,5 (1 %) | 1 | 0 | 0 % | 0–79 % | -1,05 | -1,05 | +0,21 |
| 6,0 (2 %) | 1 | 0 | 0 % | 0–79 % | -1,17 | -1,17 | +0,23 |
| >= 6,5 (3 %) | 4 | 2 | 50 % | 15–85 % | -0,30 | -0,47 | +1,02 |

Spearman ρ (Score ↔ R): **+0,77** (n = 6). Faustregel: |ρ| < 0,3 trennt praktisch nicht; erst ab n ≥ 20 deuten.

Gegenrechnung Sizing: flach 1 % = -3,42 R, Score-Sizing (1/2/3 %, < 5,0 = 0) = -6,99 R-Einheiten à 1 %. Liegt Score-Sizing nicht klar darueber, verdient die Staffel ihr Risiko nicht.

## Einstiegsqualität (Weg 3)

Einstiegsfehler (MFE < 0,5 R bei MAE ≥ 0,8 R) insgesamt: 12 von 43. Entscheid zu L27 erst bei n ≥ 20 je Einstiegsart.

| Einstiegsart | n | Einstiegsfehler | Quote | Treffer | Ø R |
|---|---|---|---|---|---|
| unklar | 21 | 3 | 14 % | 9 | +0,01 |
| Limit | 10 | 3 | 30 % | 3 | -0,25 |
| Markt | 10 | 4 | 40 % | 2 | -0,53 |
| Stop-Buy | 2 | 2 | 100 % | 0 | -1,04 |

| Setup-Klasse | n | Einstiegsfehler | Quote | Treffer | Ø R |
|---|---|---|---|---|---|
| unklar | 25 | 3 | 12 % | 13 | +0,28 |
| trend_pullback | 11 | 5 | 45 % | 1 | -0,87 |
| reversal | 3 | 1 | 33 % | 0 | -1,00 |
| thesen_korb | 2 | 1 | 50 % | 0 | -1,06 |
| breakout_retest | 1 | 1 | 100 % | 0 | -1,07 |
| grinder | 1 | 1 | 100 % | 0 | -1,09 |

Tatsaechliches Risiko je Trade (% RK → Anzahl): 0.3 → 1, 0.9 → 1, 1 → 11, 1.1 → 1, 1.2 → 2, 1.3 → 1, 1.5 → 1, 1.6 → 1, 2 → 1, 2.3 → 1
