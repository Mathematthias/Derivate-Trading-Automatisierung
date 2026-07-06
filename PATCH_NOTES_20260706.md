# Pipeline-Patch 2026-07-06 — P0: Verdeckt-BEREIT-Regression

## Geändert
- `marketdata-pipeline/src/filter_engine.py` — `_evaluate_trigger`, require_hammer-Block

## Problem
Die 4h-Reverse-Demotion (Note #118, Juni-Patch 2026-06-01) war im Repo-Stand
2026-06-26 verlorengegangen — vermutlich beim Umbau des require_hammer-Blocks
(Bullish-Engulfing-Erweiterung, Note #70). Der Parser setzte `reverse_tf="4h"`
weiter (state_parser.py Z617), der Filter ignorierte es und schrieb den
fehlenden Reverse immer in `conditions_missing` (harter Block → NAHE).
Folge: verdeckt-BEREIT-Blindfleck faktisch wieder offen; Test
`test_verdeckt_bereit::test_4h_reverse_wird_pending_und_bereit_stern` ROT.

## Fix
Neuer `elif trigger.reverse_tf == "4h":`-Zweig VOR der bestehenden Daily-Logik.
Bei fehlendem Match und 4h-spezifiziertem Reverse → `conditions_pending` mit
"4h manuell prüfen"-Hinweis (→ BEREIT*) statt hartem Block. Daily-Pfad
(reverse_tf=None) unangetastet. Feuert der Reverse auf Daily, greift weiter
der conditions_met-Zweig (voller BEREIT).

## Abnahme
- tests/test_verdeckt_bereit.py: 8/8 grün (war 7/8)
- Volle Suite: 305/305 grün (war 304/305), keine Regression
