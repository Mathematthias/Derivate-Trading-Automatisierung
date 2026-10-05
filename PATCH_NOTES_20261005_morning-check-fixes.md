# Patch 2026-10-05 — Digest-Fixes nach dem ersten Morning Check v49

Anlass: erster Morning Check mit Digest v4 am 2026-10-05, 12:02 CEST. Das
Schema bleibt `briefing-digest/v4`; neue Felder kommen nur innerhalb
bestehender Blöcke dazu.

## 1 — `data_freshness.stale` je Börsengruppe

**Befund:** stale hieß `bar_date != heute`. Am Montagmittag standen so alle 68
US-Ticker mit dem Freitagsschluss auf „stale, kein Entry“, obwohl die US-Börse
noch gar nicht offen war. Das passiert jeden Vormittag.
**Fix:** `digest_renderer.exchange_group()` leitet die Gruppe aus dem Symbol ab
(EU, US, ASIA, CONT für FX/Futures, CRYPTO). Stale ist ein Ticker, der hinter
dem jüngsten bar_date seiner Gruppe liegt; der hängende Einzel-Feed
(G1A.DE 2026-09-07) wird weiter erkannt, einen Kalender braucht es nach wie
vor nicht. Neu sind `groups` und `pre_session`, Letzteres misst gegen den
jüngsten Balken des Universums und nicht gegen `as_of`, damit es am Wochenende
leer bleibt. Krypto ist eine eigene Gruppe und zählt für diesen Maßstab nicht
mit, sonst würden Samstagsbalken FX und Futures auf stale setzen.
**Test:** `tests/test_data_freshness.py` (Montagmittag, einzelner EU-Ticker
auf Vortag, Wochenende mit und ohne Krypto, Gruppenzuordnung).

## 2 — `watchlist_expiry` ohne archivierte Zeilen

**Befund:** 105 Einträge, davon 74 archiviert — die echten Fristen gingen darin
unter.
**Fix:** Der YAML-Status kommt jetzt als `WatchlistEntry.state_status` am Entry
an (`state_yaml.entries_from_yaml`). Im Expiry-Block landen nur `aktiv` und
`position`, jeder Eintrag trägt `status`. Ohne YAML (STATE-Doc) wird der
Status aus dem Monitor-Kriterium abgeleitet. `skill/state_parser.py` ist per
`scripts/build_skill_copy.py` neu erzeugt.
**Test:** `tests/test_digest_watchlist_filter.py`.

## 3 — Positions-Monitore nicht mehr in Stufe 1

**Befund:** NBIS und JST.DE standen in `buckets.ready`; bei DHL.DE wurde
„Invalidator … EMA50-1D (~55,86€)“ als approx-Trigger gelesen und BEREIT.
**Fix:** Vor der Bucket-Klassifikation fallen Monitore heraus (Status
`position`, Richtung `POSITION-MONITOR…` oder `[MONITOR` im Namen). Sie stehen
nur noch in `position_monitors`, ihre Indikatoren weiter im `universe`.
`counts.position_monitors` ist neu; im Ex-Tag-Radar tragen Monitore
`bucket: null`.
**Test:** `tests/test_digest_watchlist_filter.py`, Anpassung in
`tests/test_exdiv_radar.py`.

## 4 — 4h-Werte für LSE-Ticker in Pence

**Befund:** `universe["NG.L"].tf4h.close = 1147.5` neben `kurs = 11.455`. Der
Tagespfad normiert `.L` über `market_data._normalize_price_units`, der 4h-Pfad
nicht.
**Fix:** `intraday_4h.pull_4h` ruft dieselbe Funktion auf die 1h-Rohdaten auf,
bevor aggregiert wird. OHLC, EMAs und ATR sind damit in Pfund.
**Test:** `tests/test_pence_normalization.py` (4h-Pfad .L gegen .DE mit
identischen Rohdaten).

## Testbilanz

`python -m pytest tests/ -q` in `marketdata-pipeline/`: vorher 696 passed,
1 skipped; nachher 752 passed, 1 skipped.
