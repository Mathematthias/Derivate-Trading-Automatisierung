# Patch 2026-10-04 — System-Review: Filter-Fixes, Breakout-Retest, Workflow B

User-Entscheide 2026-10-04 (Chat "System-Review"). Gegenstueck: Skill v49
(Vollschnitt) und Journal `Trading_Journal_20261004b.xlsx`. Review-Bericht:
Projekt-Doc `trading/System-Review_2026-10-04.md`.

## Befund (Kurzfassung)

Journal n=38 geschlossene Trades: Trefferquote 24 % (Wilson 13–39 %), Payoff
reicht nicht zum Break-even. Zwei Drittel der Verluste liegen bei −1 R (Stop
im Rauschen), MFE/MAE unbekannt — Einstiegs- und Ausstiegsfehler sind nicht
trennbar. Im Code: `earnings_blackout_days` stand seit 2026-04-25 in der
Config, wurde aber nie gelesen; der 30d-Move warf reife Trends ganz raus
statt sie kleiner zu sizen; `disqualifier_dividend_within_days` fuer Shorts
wurde ignoriert; "Breakout" war ein nackter Ausbruch ohne Retest. Operativ
lief der Zustand ueber drei Uebersetzungen (Journal-xlsx → watchlist_sync →
STATE-Doc → Digest), Automaten konnten nur Briefe schreiben.

## Teil 1 — Filter-Fixes (Commit 88f7eee)

- `filter_engine.py`: `_passes_universal_disqualifier(snap, config, today)` prueft
  Liquiditaet, ATR-Deckel (`max_atr_pct: 8.0`) und **Earnings-Blackout**
  (`0 <= Tage <= 7`). 30d-Move ist **Flag** `late_entry` (⚠️REIFE im Summary,
  `sizing_hint: floor_1pct`), kein Ausschluss. Ex-Div ≤14 Tage blockt
  `short_trend_pullback` und `breakdown_short`.
- **Breakout-Retest** statt Breakout: `market_data._compute_breakout_retest_fields`
  liefert `bo_level/bo_bars_ago/bo_vol_mult/bo_failed` (Short: `bd_*`).
  Definition: Schluss eines abgeschlossenen Balkens ueber dem Hoch der 20
  Vorbalken, hoechstens 10 HT zurueck, Volumen ≥1,2× (Daempfer <1,5× →
  `floor_1pct`), kein spaeterer Schluss zurueck unter das Niveau, Kurs jetzt im
  Band [Niveau −0,5 ATR, Niveau +0,75 ATR]. Summary endet mit `Retest=NHT`.
- `filter_config.yaml`: Buckets `breakout_long`/`breakdown_short` neu
  parametrisiert; `disqualifier_active_buyback` entfernt (war ohne Datenquelle).
- `output_renderer.py`: Labels "Breakout-Retest Long" / "Breakdown-Retest Short".
- Tests: `tests/test_review_2026_10_04.py` (20), Anpassungen in
  `test_vol_stufen_und_subquote.py`, `test_ex_dividend.py`, `test_pitches.py`,
  `test_pitch_universe_sync.py` (counter=0-Semantik dokumentiert).

## Teil 2 — Workflow B: Repo-YAML als Zustand

- **Neu `state/`**: `watchlist.yaml` (128 Eintraege: 45 aktiv, 9 Positionen,
  74 archiviert), `radar.yaml` (63 Zeilen), `thesen.yaml` (Stand Thesen-Lauf
  2026-10-03). Migriert aus `Trading_Journal_20261002c.xlsx` mit
  `scripts/migrate_journal_to_state.py --apply-review-2026-10-04`:
  HLMA.L, LIN, HLN.L, ALC.SW, HOLN.SW, ZTS archiviert (Klassen-Entscheid),
  GIVN.SW und TMO auf Breakout-Retest-Legs umgeschrieben.
- `src/state_yaml.py`: Laden/Speichern, `entries_from_yaml` → `WatchlistEntry`
  (Trigger-Grammatik unveraendert, filter_engine unberuehrt), INBOX-Vertrag
  (`apply_actions`, idempotent, kaputte Aktion kippt nichts), Digest-Bloecke
  (`radar_window` 28 Tage, `thesen_aktiv` mit Re-Check-Faelligkeit).
- `src/inbox_apply.py` + `.github/workflows/inbox_apply.yml`: INBOX-*.json aus
  dem Briefing-Ordner anwenden, Register `state/inbox_processed.json`,
  Commit durch den Bot. **cron-job.org-Slot neu anlegen** (Vorschlag
  `40 7 * * 1-6` Berlin).
- `src/state_export.py` + `state_export.yml`: Repo-Zustand → Journal-Blaetter
  Watchlist (nur aktiv/position), Watchlist-Archiv (archivierte angehaengt),
  Termin-Radar; alle anderen Blaetter samt Formeln unveraendert; Info-Blatt
  `State-Export`. Journal-Eingang per Drive-File-ID oder juengstes
  `Trading_Journal_*.xlsx`.
- `src/mfe_mae.py` + `mfe_mae.yml`: MFE/MAE in R je Trade aus Blatt
  "Trade-Audit" (Spalten `Symbol, Richtung, Kauf, Verkauf, EntryU, SL_U`),
  Vier-Felder-Klassifikation (Einstiegsfehler / Ausstiegsfehler / Stop im
  Rauschen / Gewinner). Rechenweg im Modul-Docstring.
- `marketdata_sync.py`: `WATCHLIST_SOURCE=yaml` + `STATE_DIR` lesen die
  Watchlist aus dem Repo; STATE-Doc nur noch fuer Overrides/Ticker-Map
  (Fehler dort ist kein Abbruch). `late_entry` wird je Snapshot gesetzt.
  Digest bekommt `state=`.
- `digest_renderer.py`: Schema **`briefing-digest/v4`**, Top-Level-Feld
  `state`; Universe-Eintraege tragen `late_entry, bo_level, bo_bars_ago,
  bd_level, bd_bars_ago`.
- `drive_writer.py`: `list_files_by_prefix`, `download_file_bytes`,
  `download_json_file`, `write_binary_file` (additiv).
- Workflows Tier A/B/C: `WATCHLIST_SOURCE: yaml`, `STATE_DIR: ./state`;
  Tier-A-Schritt `watchlist_sync.py` entfernt (Datei bleibt als Fallback).
- Doku: `README.md` (Root) ist jetzt Landing-Page statt Byte-Kopie;
  Pipeline-README "Single Source of Truth" + "Workflow B"; `docs/architecture.md`
  (Disqualifier, Buckets, Lifecycle); `routines/morning-check-prompt.md` ist
  ein Zeiger auf Skill-Routine 7.
- Tests: `tests/test_state_yaml.py` (26), `tests/test_state_export_mfe.py` (17);
  Schema-Tests auf v4. Suite: 695 passed, 1 skipped.

## Was NICHT im Repo liegt (Folgearbeit)

- Skill v49 (Vollschnitt: Klassen-Referenzen, Routine 7 mit 6-Block-Morning-
  Check und Trader-Tops, `pipeline_utils.render_briefing_slim`).
- Journal `Trading_Journal_20261004b.xlsx` (Export + Blatt "Trade-Audit").
- cron-job.org: Slots fuer `inbox_apply`, `catalyst_calendar_sync`,
  `dividend_scan` muessen von Hand angelegt werden.
- Geplante Claude-Tasks (Thesen-Lauf, Morning Check): Prompts auf INBOX-JSON
  und Digest-`state` umstellen.
