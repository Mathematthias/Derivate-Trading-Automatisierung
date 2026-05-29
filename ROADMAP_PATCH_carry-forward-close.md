# PATCH — Carry-Forward bestätigter Tagesschluss-Breakouts (2026-05-29)

**Journal-Note:** #110 · **Priorität:** P1 · **Entdeckt via:** SAN.PA

## Problem

Ein reiner **Daily-Close-Breakout**-Trigger, der im Abendlauf nach Markt-Schluss
als `🎯 BEREIT — alle Bedingungen erfüllt` (volles Tagesvolumen) bestätigt wurde,
fiel am **Folgetag-Morgen** zurück auf `BEREIT*`/`very_close`:

- `filter_engine._evaluate_trigger` wertete Preis gegen `snap.price` (= letzter
  Balken-Close, intraday die **werdende** Kerze) und Volumen gegen
  `volume_multiplier_today` (partiell) aus.
- Folge: Die Bestätigung von Schluss N war nur in **einem** Snapshot sichtbar
  (dem Post-Close-/Post-`hard_evaluation_utc_hour`-Lauf). Im Morning-Check N+1
  war der bestätigte Breakout **unsichtbar**.

Konkret SAN.PA 28.05. (Do-Schluss 76,36 > Trigger 76,30, Vol 1,03×) →
29.05. 11:31 zeigte `BEREIT*` Vol 0,10× pending bzw. `very_close`.

## Fix

Für **reine Close-Breakout-Trigger** (`price_op` `>`/`<`, oder `in_range` mit
`zone_kind == "breakout"`, **ohne** `require_hammer`/`require_bounce`) werden
**Preis UND Volumen** gegen die zuletzt **abgeschlossene** Tageskerze (`prev_*`)
evaluiert, solange die aktuelle Sitzung noch läuft (`_last_bar_is_forming`).

- **Selbst-invalidierend:** schließt eine Tageskerze zurück durch den Trigger,
  zeigt `prev_close` das → kein BEREIT mehr. Keine Expiry-/State-Logik nötig.
- **Backward-kompatibel:** ohne Zeit-Kontext (`today`/`now_utc_hour` None) oder
  nach `hard_evaluation_utc_hour` → Live-Werte wie bisher.
- **Failing-Breakout-Watch:** ist der LIVE-Intraday-Kurs zurück durch den
  Trigger gelaufen, hängt das Summary einen Warnhinweis an (Bucket bleibt BEREIT).
- **Volumen final:** die abgeschlossene Kerze liefert `met`/`failed` direkt
  (nie `pending`) — ein echter Vol-Fail der Schluss-Kerze blockt BEREIT korrekt
  (KBX-Fall, 0,62×).

## Geänderte Dateien

- `marketdata-pipeline/src/market_data.py` — neues Feld
  `TickerSnapshot.prev_volume_multiplier` + Berechnung (vorletzter Balken / avg-20d).
- `marketdata-pipeline/src/filter_engine.py` — Helper `_is_close_breakout_trigger`,
  `_last_bar_is_forming`, `_live_back_through_trigger`; Carry-Forward in
  `_evaluate_trigger` (Preis-/Volumen-Quelle + Summary).
- `marketdata-pipeline/tests/test_carryforward_close.py` — 18 neue Tests.
- `skills/derivate-trading/references/pipeline-integration.md` — Doku-Notiz
  (Quelle; live wirksam erst nach separatem Skill-ZIP-Upload).

## Tests

`pytest tests/` — **275 passed** (257 Baseline + 18 neu), keine Regression.

## Bekannte Grenze

`Daily-Reverse-Close`-Breakouts (z.B. EBAY-Trigger A, mit `require_hammer`) sind
bewusst ausgenommen — die Reverse-Close-Form der Schluss-Kerze ließe sich nur
mit gespeicherter prev-OHLC rekonstruieren (nicht im Snapshot). Bei Bedarf
nachrüstbar (prev_high/prev_low/prev_open in TickerSnapshot + Pattern-Eval auf
der Vorkerze).
