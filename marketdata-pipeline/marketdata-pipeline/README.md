# marketdata-pipeline

GitHub-Action-basierte Pipeline für Marktdaten-Sync und Setup-Vorauswahl.

## Was macht das?

Alle 30 Min Mo-Fr (Tier A) und 1× täglich (Tier B) zieht eine GitHub Action
via yfinance Marktdaten für deine Watchlist + ein erweitertes Universe.
Schreibt zwei Dateien nach Drive `Trading/Briefing/`:

- `MARKETDATA-FULL-{datetime}.md` — alle Indikatoren
- `CANDIDATES-{datetime}.md` — Vorauswahl mit zwei Sektionen:
  - **Stufe 1:** Status deiner STATE-Watchlist-Trigger (sind sie aktiv?)
  - **Stufe 2:** Neue Kandidaten aus Universe-Setup-Filter

Routinen V1.6 und Chat-Sessions lesen diese Dateien — keine Web-Snippets
mehr für Kurse.

## Phase-Status

- [x] **Phase 0:** Configs (yamls + STATE-Erweiterung + Architektur-Doku)
- [x] **Phase 1:** Drive-Service-Account + GitHub Secret `GDRIVE_SA_KEY`
- [x] **Phase 2:** Skript `marketdata_sync.py` (yfinance + zweistufige Filter-Engine)
- [x] **Phase 3:** GitHub Actions Workflows (tier_a + tier_b)
- [ ] **Phase 4:** V1.6-Routinen (lesen MARKETDATA + CANDIDATES)
- [ ] **Phase 5:** Chat-Custom-Instruction (Auto-Load bei Session-Start)
- [ ] **Phase 6:** Earnings-Kalender-Sync (separate wöchentliche Action)

## Files

```
Repo-Root/
├── .github/workflows/                   ← muss ins Repo-Root, nicht in marketdata-pipeline!
│   ├── tier_a_sync.yml                  ← alle 30 Min Mo-Fr + Sa 10:00
│   └── tier_b_sync.yml                  ← 1× täglich Mo-Fr 07:30
└── marketdata-pipeline/
    ├── README.md                        ← du bist hier
    ├── requirements.txt                 ← Python-Dependencies
    ├── config/
    │   ├── tickers_tier_a.yaml          ← Indizes/Rohstoffe/Krypto/Positionen
    │   ├── tickers_tier_b.yaml          ← Gamechanger-Hunt-Universum
    │   ├── filter_config.yaml           ← Setup-Schwellwerte
    │   ├── STATE_extensions.md          ← STATE-Doc-Erweiterungen
    │   └── WATCHLIST_ARCHIV_template.md ← Vorlage für Drive-Archiv-Doc
    ├── src/
    │   ├── marketdata_sync.py           ← Main-Skript, Entry-Point
    │   ├── state_parser.py              ← STATE-Doc lesen + Watchlist parsen
    │   ├── market_data.py               ← yfinance-Pull + Indikatoren
    │   ├── filter_engine.py             ← Stufe 1 + Stufe 2
    │   ├── output_renderer.py           ← Markdown-Output erzeugen
    │   └── drive_writer.py              ← Drive-Upload via Service-Account
    └── docs/
        └── architecture.md              ← Wie die Filter-Engine arbeitet
```

## Single Source of Truth

| Datenart | Pflege wo |
|----------|-----------|
| Indizes/Rohstoffe/Krypto | `tickers_tier_a.yaml` (selten ändern) |
| Offene Positionen | `tickers_tier_a.yaml` (bei Trade-Eröffnung/Schluss) |
| **Aktive Watchlist** | **STATE-Doc (Drive)** — NICHT yaml |
| **Watchlist-Archiv** | **WATCHLIST-ARCHIV-Doc (Drive)** — separates Doc |
| Filter-Schwellwerte | `filter_config.yaml` (Tuning) |
| Filter-Override | STATE-Doc Sektion 4 |

## Anpassungen ohne Code-Push

- Watchlist-Wert hinzufügen/ändern → STATE-Doc editieren
- Filter-Schwellwert ändern → `filter_config.yaml` editieren + Repo-Push
- Override aktivieren → STATE-Doc Sektion 4

## Manueller Test (nach Push)

GitHub Action manuell auslösen:
1. `https://github.com/Mathematthias/Derivate-Trading-Automatisierung/actions`
2. Links den Workflow `Marketdata Sync Tier A` wählen
3. Rechts oben **`Run workflow`** → **`Run workflow`**
4. ~2 Minuten warten, dann in Drive `Trading/Briefing/` nachschauen

Falls Fehler: Action-Log im UI ansehen.

## Wichtige Pipeline-Konstanten

Im `marketdata_sync.py` und den Workflows:

- `STATE_DOC_ID = 17KgjCjFiy15JsSRD8h_EK5lL_PitkOJIC7ou1LYOcks`
- `BRIEFING_FOLDER_ID = 1jKuyo12c38sg8Ff4ZHFXHqsU_Nl2D4AA`
- Health-Check-Threshold: 80% der Ticker müssen erfolgreich sein

Falls IDs sich ändern, in Workflow-Files updaten.
