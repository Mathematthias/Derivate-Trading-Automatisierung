# Patch 2026-09-24 — Grinder-Tempo auf Trend-20 (Regression 20 HT)

User-Entscheid 2026-09-24, Variante B. Gegenstück: Skill v44.

## Befund (Abgleich Skill <-> Repo)

`move_30d_pct = Kurs / closes.iloc[-22] - 1` misst **21 Balken ≈ 30 Kalendertage**.
Die Grinder-Klasse im Skill sprach von „R:R 2 in ~30 HT", der Boden 0,6 von „~50 HT"
(real ~35 HT), der Hoch-ATR-Swing von „25 HT" bei Tempo 1,2 (real ~18). Der Feldname
meint Kalendertage und bleibt für Late-Entry, Counter-Lane und Short-Pool richtig.

## Änderung

- `market_data.py`: neue Snapshot-Felder `trend20_move_pct`, `trend20_r2`;
  `_compute_trend_regression()` = Regression ln(Close) über die letzten 20 Schlusskurse,
  Steigung b hochgerechnet: `(exp(20·b) − 1) × 100`. `TREND_WINDOW_HT = 20`.
- `filter_engine.py`: Grinder-Tempo und Richtungs-Check laufen auf `trend20`
  (`grinders.tempo_basis: trend20`), Rückfall auf `move_30d_pct` nur bei fehlendem Feld
  (`tempo_basis: move30d_fallback` im Payload). Payload + `trend20`, `r2`, `tempo_basis`.
- `digest_renderer.py`: je Ticker `trend20`, `r2` (kein Top-Level-Feld, Schema bleibt v2).
- `marketdata_sync.py`: PITCHES-Meta `grinders_tempo_basis`.
- `filter_config.yaml`: `tempo_basis: trend20`; Schwellen 0,6 / 0,9 unverändert
  (log-linearer Trend: neu = alt × 20/21), Horizonte jetzt 33 / 22 HT.
- `tests/test_grinder_trend20.py`: 20 Tests (Regression, Filter, Rollback, Snapshot, Digest).

## Warum Regression (Random-Walk-Simulation, n = 200.000)

| Zähler | Tagesjitter | Schwerpunkt zurück | erlahmter Trend zeigt noch |
|---|---|---|---|
| Endpunkt 21 Balken (alt) | 1,41 σ | 10 HT | 67 % (30-T-Endpunkt) |
| SMA20-Differenz | 0,32 σ | 19,5 HT | 86 % |
| Regression 20 HT (neu) | 0,76 σ | 9,5 HT | 46 % |

## Suite

572 passed, 1 skipped, **3 failed vorbestehend** (vor dem Patch identisch):
`test_pitches.py::TestLanesUndQuote::test_counter_verdraengt_trend_nicht`,
`::test_faecher_stuft_short_herab`, `test_pitch_universe_sync.py::…::test_merged_und_quotiert`.
Vermutete Ursache: die Tests erwarten eine Counter-Lane, die Config steht seit 2026-09-21
auf `pitches.quota.counter: 0`. Nicht Teil dieses Patches.

## Rollback

`grinders.tempo_basis: move30d`

## Offen

Nicht gegen echte Kursdaten kalibriert (kein Netz im Build-Container). Prüfpunkt: die ersten
zwei PITCHES-Läufe nach Deploy — Blockgröße und `grinders_dropped_by_tempo` gegen die Vorwoche.
