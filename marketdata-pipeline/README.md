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

- [x] Phase 0: Configs (diese Files)
- [ ] Phase 1: Drive-Service-Account
- [ ] Phase 2: marketdata_sync.py
- [ ] Phase 3: GitHub Actions
- [ ] Phase 4: Routinen V1.6
- [ ] Phase 5: Chat-Custom-Instruction

## Files

```
marketdata-pipeline/
├── README.md                            ← du bist hier
├── config/
│   ├── tickers_tier_a.yaml              ← Indizes/Rohstoffe/Krypto/Positionen
│   ├── tickers_tier_b.yaml              ← Gamechanger-Hunt-Universum
│   ├── filter_config.yaml               ← Setup-Schwellwerte
│   ├── STATE_extensions.md              ← STATE-Doc-Erweiterungen (manuell ins Drive-STATE)
│   └── WATCHLIST_ARCHIV_template.md     ← Vorlage für separates Archiv-Doc in Drive
└── docs/
    └── architecture.md                  ← Wie die Filter-Engine arbeitet
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
- Filter-Schwellwert ändern (z.B. EMA-Distance) → `filter_config.yaml` editieren + Repo-Push
- Override aktivieren (z.B. Liquiditäts-Bypass) → STATE-Doc Sektion 4

## Code-Push nötig nur bei:

- Indikator-Berechnung erweitern (Phase 2 Skript ändern)
- Neue Setup-Buckets (Code + Config)
- Action-Schedule ändern (`.github/workflows/*.yml`)
