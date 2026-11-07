# Score-Kalibrierung L12/L23 — 2026-11-07

Geschlossene Trades mit R: **59**, davon mit Score: **12**, mit dokumentiertem Risiko: 35.
Score-Quellen: Journal-Notiz 4, alt X/7 2, Entry (User-Bestaetigung 6/7, 2026-10-12) 1, Entry (Claude-Checkliste 15:53, nicht bestaetigt) 1, Entry (Claude-Checkliste Tradeplan 14:19, 5/7) 1, Entry (Claude-Checkliste 22.10., nicht bestaetigt) 1, Entry (Claude-Checkliste 2026-10-26 11:40, These 0) 1, Entry (Claude-Checkliste 2026-10-26 16:39, These 0) 1.

**Kein Urteil (L28):** 12 von mindestens 20 gescorten Trades. Die Tabelle ist ein Zwischenstand, keine Evidenz.

| Score-Band | n | Treffer | Quote | Wilson 95 % | Ø R | Median R | Ø MFE |
|---|---|---|---|---|---|---|---|
| < 5,0 (kein GO) | 0 | 0 | — | — | — | — | — |
| 5,0-5,5 (1 %) | 3 | 0 | 0 % | 0–56 % | -1,02 | -1,04 | +0,24 |
| 6,0 (2 %) | 5 | 0 | 0 % | -0–43 % | -0,73 | -1,02 | +0,37 |
| >= 6,5 (3 %) | 4 | 2 | 50 % | 15–85 % | -0,30 | -0,47 | +1,02 |

Spearman ρ (Score ↔ R): **+0,38** (n = 12). Faustregel: |ρ| < 0,3 trennt praktisch nicht; erst ab n ≥ 20 deuten.

Gegenrechnung Sizing: flach 1 % = -7,90 R, Score-Sizing (1/2/3 %, < 5,0 = 0) = -13,93 R-Einheiten à 1 %. Liegt Score-Sizing nicht klar darueber, verdient die Staffel ihr Risiko nicht.

## Einstiegsqualität (Weg 3)

Einstiegsfehler (MFE < 0,5 R bei MAE ≥ 0,8 R) insgesamt: 17 von 59. Entscheid zu L27 erst bei n ≥ 20 je Einstiegsart.

| Einstiegsart | n | Einstiegsfehler | Quote | Treffer | Ø R |
|---|---|---|---|---|---|
| unklar | 27 | 5 | 19 % | 11 | -0,05 |
| Markt | 16 | 5 | 31 % | 3 | -0,41 |
| Limit | 13 | 4 | 31 % | 4 | -0,31 |
| Stop-Buy | 3 | 3 | 100 % | 0 | -1,06 |

| Setup-Klasse | n | Einstiegsfehler | Quote | Treffer | Ø R |
|---|---|---|---|---|---|
| unklar | 26 | 3 | 12 % | 13 | +0,24 |
| trend_pullback | 17 | 6 | 35 % | 3 | -0,64 |
| bauchgefuehl | 5 | 1 | 20 % | 1 | -0,18 |
| breakout_retest | 3 | 2 | 67 % | 1 | -0,43 |
| reversal | 3 | 1 | 33 % | 0 | -1,00 |
| thesen_korb | 3 | 2 | 67 % | 0 | -1,07 |
| grinder | 1 | 1 | 100 % | 0 | -1,09 |
| thesen_spur | 1 | 1 | 100 % | 0 | -1,02 |

| Ausbruchs-Volumen (seit 2026-10-09) | n | Einstiegsfehler | Quote | Treffer | Ø R |
|---|---|---|---|---|---|
| 1,0-1,3 (gedaempft) | 1 | 1 | 100 % | 0 | -1,02 |

Tatsaechliches Risiko je Trade (% RK → Anzahl): 0.3 → 1, 0.5 → 1, 0.8 → 1, 0.9 → 5, 1 → 18, 1.1 → 2, 1.2 → 2, 1.3 → 1, 1.5 → 1, 1.6 → 1, 2 → 1, 2.3 → 1
