# Score-Kalibrierung L12/L23 — 2026-10-31

Geschlossene Trades mit R: **52**, davon mit Score: **10**, mit dokumentiertem Risiko: 29.
Score-Quellen: Journal-Notiz 4, alt X/7 2, Entry (User-Bestaetigung 6/7, 2026-10-12) 1, Entry (Claude-Checkliste 15:53, nicht bestaetigt) 1, Entry (Claude-Checkliste Tradeplan 14:19, 5/7) 1, Entry (Claude-Checkliste 22.10., nicht bestaetigt) 1.

**Kein Urteil (L28):** 10 von mindestens 20 gescorten Trades. Die Tabelle ist ein Zwischenstand, keine Evidenz.

| Score-Band | n | Treffer | Quote | Wilson 95 % | Ø R | Median R | Ø MFE |
|---|---|---|---|---|---|---|---|
| < 5,0 (kein GO) | 0 | 0 | — | — | — | — | — |
| 5,0-5,5 (1 %) | 3 | 0 | 0 % | 0–56 % | -1,02 | -1,04 | +0,24 |
| 6,0 (2 %) | 3 | 0 | 0 % | 0–56 % | -0,86 | -1,10 | +0,27 |
| >= 6,5 (3 %) | 4 | 2 | 50 % | 15–85 % | -0,30 | -0,47 | +1,02 |

Spearman ρ (Score ↔ R): **+0,38** (n = 10). Faustregel: |ρ| < 0,3 trennt praktisch nicht; erst ab n ≥ 20 deuten.

Gegenrechnung Sizing: flach 1 % = -6,85 R, Score-Sizing (1/2/3 %, < 5,0 = 0) = -11,83 R-Einheiten à 1 %. Liegt Score-Sizing nicht klar darueber, verdient die Staffel ihr Risiko nicht.

## Einstiegsqualität (Weg 3)

Einstiegsfehler (MFE < 0,5 R bei MAE ≥ 0,8 R) insgesamt: 14 von 52. Entscheid zu L27 erst bei n ≥ 20 je Einstiegsart.

| Einstiegsart | n | Einstiegsfehler | Quote | Treffer | Ø R |
|---|---|---|---|---|---|
| unklar | 24 | 3 | 12 % | 10 | -0,03 |
| Markt | 14 | 5 | 36 % | 3 | -0,47 |
| Limit | 11 | 3 | 27 % | 3 | -0,33 |
| Stop-Buy | 3 | 3 | 100 % | 0 | -1,06 |

| Setup-Klasse | n | Einstiegsfehler | Quote | Treffer | Ø R |
|---|---|---|---|---|---|
| unklar | 26 | 3 | 12 % | 13 | +0,24 |
| trend_pullback | 15 | 6 | 40 % | 2 | -0,76 |
| reversal | 3 | 1 | 33 % | 0 | -1,00 |
| thesen_korb | 3 | 2 | 67 % | 0 | -1,07 |
| bauchgefuehl | 2 | 0 | 0 % | 0 | -0,54 |
| breakout_retest | 2 | 1 | 50 % | 1 | -0,14 |
| grinder | 1 | 1 | 100 % | 0 | -1,09 |

Tatsaechliches Risiko je Trade (% RK → Anzahl): 0.3 → 1, 0.5 → 1, 0.9 → 3, 1 → 15, 1.1 → 2, 1.2 → 2, 1.3 → 1, 1.5 → 1, 1.6 → 1, 2 → 1, 2.3 → 1
