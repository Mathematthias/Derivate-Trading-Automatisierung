# Score-Kalibrierung L12/L23 — 2026-10-27

Geschlossene Trades mit R: **50**, davon mit Score: **9**, mit dokumentiertem Risiko: 27.
Score-Quellen: Journal-Notiz 4, alt X/7 2, Entry (User-Bestaetigung 6/7, 2026-10-12) 1, Entry (Claude-Checkliste 15:53, nicht bestaetigt) 1, Entry (Claude-Checkliste Tradeplan 14:19, 5/7) 1.

**Kein Urteil (L28):** 9 von mindestens 20 gescorten Trades. Die Tabelle ist ein Zwischenstand, keine Evidenz.

| Score-Band | n | Treffer | Quote | Wilson 95 % | Ø R | Median R | Ø MFE |
|---|---|---|---|---|---|---|---|
| < 5,0 (kein GO) | 0 | 0 | — | — | — | — | — |
| 5,0-5,5 (1 %) | 3 | 0 | 0 % | 0–56 % | -1,02 | -1,04 | +0,24 |
| 6,0 (2 %) | 2 | 0 | 0 % | 0–66 % | -1,14 | -1,14 | +0,26 |
| >= 6,5 (3 %) | 4 | 2 | 50 % | 15–85 % | -0,30 | -0,47 | +1,02 |

Spearman ρ (Score ↔ R): **+0,36** (n = 9). Faustregel: |ρ| < 0,3 trennt praktisch nicht; erst ab n ≥ 20 deuten.

Gegenrechnung Sizing: flach 1 % = -6,54 R, Score-Sizing (1/2/3 %, < 5,0 = 0) = -11,21 R-Einheiten à 1 %. Liegt Score-Sizing nicht klar darueber, verdient die Staffel ihr Risiko nicht.

## Einstiegsqualität (Weg 3)

Einstiegsfehler (MFE < 0,5 R bei MAE ≥ 0,8 R) insgesamt: 14 von 50. Entscheid zu L27 erst bei n ≥ 20 je Einstiegsart.

| Einstiegsart | n | Einstiegsfehler | Quote | Treffer | Ø R |
|---|---|---|---|---|---|
| unklar | 23 | 3 | 13 % | 10 | -0,01 |
| Markt | 13 | 5 | 38 % | 3 | -0,42 |
| Limit | 11 | 3 | 27 % | 3 | -0,33 |
| Stop-Buy | 3 | 3 | 100 % | 0 | -1,06 |

| Setup-Klasse | n | Einstiegsfehler | Quote | Treffer | Ø R |
|---|---|---|---|---|---|
| unklar | 26 | 3 | 12 % | 13 | +0,24 |
| trend_pullback | 14 | 6 | 43 % | 2 | -0,79 |
| reversal | 3 | 1 | 33 % | 0 | -1,00 |
| thesen_korb | 3 | 2 | 67 % | 0 | -1,07 |
| breakout_retest | 2 | 1 | 50 % | 1 | -0,14 |
| bauchgefuehl | 1 | 0 | 0 % | 0 | -0,05 |
| grinder | 1 | 1 | 100 % | 0 | -1,09 |

Tatsaechliches Risiko je Trade (% RK → Anzahl): 0.3 → 1, 0.5 → 1, 0.9 → 3, 1 → 14, 1.1 → 1, 1.2 → 2, 1.3 → 1, 1.5 → 1, 1.6 → 1, 2 → 1, 2.3 → 1
