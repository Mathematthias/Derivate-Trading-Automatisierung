# Pipeline-Patch 2026-06-09 — Paket A (R:R-Vorfilter) + Paket B (Output-Diät)

## Geänderte Dateien (alle unter marketdata-pipeline/)
| Datei | Änderung |
|---|---|
| src/filter_engine.py | NEU `_rr_proxy_suffix()`; Summary-Suffix `RRprox=X.XX [⚠️ENG]` in long_/short_trend_pullback |
| src/output_renderer.py | `render_candidates(..., include_watchlist_block=True)`; bei False wird Stufe-1-Block per Post-Filter durch Hinweiszeile ersetzt; `import re` ergänzt |
| src/marketdata_sync.py | Flag-Logik: Tier A immer mit Watchlist-Block; Tier B/C nur wenn `output.gamechanger_include_watchlist: true` |
| config/filter_config.yaml | NEU `rr_proxy:` (enabled/atr_mult 1.5/min_rr 1.4) + `output.gamechanger_include_watchlist: false` |

## Paket A — Logik
RRprox = (20d-Hoch − Kurs) / (1,5 × ATR14) für Long-Pullbacks, gespiegelt für
Short. Entry-Annahme = aktueller Kurs (konservativ; Pullback-Entry an EMA20
ist real besser). < 1,4 → Flag ⚠️ENG im Summary. KEIN Ausschluss.
Validiert gegen Echtdaten 2026-06-09: ROST → 1,14 ENG, BKNG → 1,02 ENG
(beide manuell aus demselben Grund verworfen); Guards für ATR None/0 getestet.

## Paket B — Tradeoff
GAMECHANGER-Files schrumpfen ~50% (Stufe-1-Block war 1:1 redundant zu
CANDIDATES, vgl. pipeline_utils-Docstring). Einzige Randbedingung: Läuft
Tier A in einem Zeitfenster NICHT, in dem Tier B/C läuft, fehlt für dieses
Fenster der frischeste Watchlist-Status. Stand 2026-06-09 laufen die Slots
parallel (22:31 CANDIDATES + 22:32 GAMECHANGER vorhanden). Revert = eine
Config-Zeile auf true.

## Deploy
Dateien in den Repo-Pfaden ersetzen, committen, nächster Cron-Lauf genügt.
Skill-seitig: derivate-trading-Skill-ZIP neu hochladen (pipeline_utils.py
parst RRprox jetzt in GamechangerCandidate.rr_proxy/.rr_eng; SKILL.md hat
ein neues Warnsignal-Bullet). Alte Files bleiben parsebar (Suffix optional).
