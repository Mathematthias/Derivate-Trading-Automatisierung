# Patch 2026-10-07 — Befunde aus dem Morning Check

Gegenstück im Skill: v54 (`geparkte_zeilen`, `reeval_annaeherung`, `tiw_status` am geschlossenen Balken).

## Vortagesbalken fehlt (`market_data`, `filter_engine`, `digest_renderer`)

Um 10:02 CEST trugen alle EU-Ticker den laufenden 07.10.-Balken, aber nicht den 06.10. `prev_close`
war damit der Schluss vom 05.10.; `chg` und `gap` stimmten nicht (JEN +0,47 % statt −3,3 %), und der
Carry-Forward der Filter-Engine hätte den 05.10. als „letzten Schluss" gelesen. Die Ursache im
yfinance-Batch ist offen; ohne Netzzugriff aus der Chat-Session nicht reproduzierbar.

Neu: `TickerSnapshot.prev_bar_date` und `prev_luecke` (fehlt ein Werktag zwischen vorletztem und
letztem Balken). Bei Lücke: `change_pct`/`gap_pct` = None, Warnung im Log mit Symbol, kein
Carry-Forward über `prev_close`. Digest-Universum trägt `prev_close`, `prev_bar_date` und bei
Lücke `prev_luecke: true`. Ein Feiertag erzeugt dasselbe Signal, gewollt konservativ.

**Offen:** Ursache. Das Log der nächsten Läufe nennt die betroffenen Symbole
(`Vortagesbalken fehlt (… -> …)`); damit lässt sie sich eingrenzen.

## Frische nach Gruppen-Mehrheit (`digest_renderer._data_freshness`)

`^VIX` trug um 10:02 schon den 07.10.-Balken und zog die US-Gruppe auf „latest 07.10.". 76 US-Ticker
galten als stale statt `pre_session`. Maßstab je Gruppe ist jetzt der bar_date der Mehrheit
(Gleichstand: der jüngere). Ein hängender Einzelfeed bleibt stale.

## Zustands-Metadaten (`state_yaml.watchlist_meta`)

Je Zeile neu `tiw` ({seite, level}) und `reeval` ({op, level}, nur die Form
`RE-EVAL: 1D-Schluss >/<X`). Der Morning Check liest daraus geparkte aktive Zeilen (alle Legs 🔴)
und Re-Evals archivierter Zeilen. Anlass VOS.DE, die in keinem Block stand.

Tests: `tests/test_morning_check_20261007.py` (10). Suite 768 grün.
