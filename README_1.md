# Derivate Trading Automation

Automatisierte Morning- und Breaking-News-Scans für Matthias' Derivate-Trading
(KO-Zertifikate / Turbos auf DAX/MDAX/SDAX + US-Einzelwerte), ausgeführt als
Claude Code Routines auf Anthropic-Cloud.

## Zweck dieses Repos

Dieses Repo ist **Skill-Host** für Claude Code Routines — es hält die
Trading-Logik, die Helper-Bibliothek und die Routine-Prompts, die täglich
automatisch ausgeführt werden.

**Was NICHT im Repo liegt:**
- Journal-Datei (`Trading_Journal_YYYYMMDD.xlsx`) — bleibt lokal
- Portfolio-State (offene Positionen, Einstiegskurse, etc.) — liegt im
  verknüpften Google Doc
- Persönliche Daten jeglicher Art

**Was im Repo liegt:**
- Skill-Definition (`skills/derivate-trading/SKILL.md`)
- Helper-Bibliothek (`journal_utils.py`)
- Referenzmaterial (News-Scan, Technische Analyse, Produktkenntnis, etc.)
- Routine-Prompts (Morning-Check, Afternoon-Scan, Evening-Scan)

## Aufbau

```
derivate-trading-automation/
├── README.md                           ← diese Datei
├── .gitignore                          ← blockt Excel, CSV, PDFs
├── skills/
│   └── derivate-trading/
│       ├── SKILL.md                    ← Skill-Definition (YAML-Front + Anleitung)
│       ├── journal_utils.py            ← openpyxl-Helper für Journal-I/O
│       └── references/
│           ├── journal-layout.md
│           ├── journal-utils-api.md
│           ├── news-scan.md
│           ├── produktkenntnis.md
│           ├── technische-analyse.md
│           └── trade-plan-templates.md
└── routines/
    ├── morning-check-prompt.md         ← Prompt für 08:45 Routine
    ├── scan-prompt-1545.md             ← Prompt für 15:45 Afternoon-Scan
    ├── scan-prompt-2030.md             ← Prompt für 20:30 Evening-Scan
    └── state-doc-template.md           ← Struktur + Pflege-Regeln des STATE-Docs
```

## Claude Code Routines Setup

Drei scheduled Routines, alle Mo–Fr, Timezone Europe/Berlin:

| Routine | Cron | Prompt-Datei |
|---------|------|--------------|
| `trading-morning-check` | `45 8 * * 1-5` | `routines/morning-check-prompt.md` |
| `trading-scan-afternoon` | `45 15 * * 1-5` | `routines/scan-prompt-1545.md` |
| `trading-scan-evening` | `30 20 * * 1-5` | `routines/scan-prompt-2030.md` |

Seit Version 1.3 sind die beiden Scans separate Prompt-Files mit hartkodiertem
Slot (statt einer parametrisierten Datei). Das ist Absicht: Routine-Prompts
haben keine Variable-Substitution, und zwei getrennte Files eliminieren die
Copy-Patch-Fehlerquelle beim Anlegen. Die Folder-ID des Ziel-Ordners ist
ebenfalls direkt in jedem Prompt eingetragen.

Connector-Anforderung:
- **Google Drive** (Pflicht, Read+Write auf `Trading/Briefing/` Ordner)
- Gmail (optional, für Phase 2 Push-Mail bei Gamechanger)

## Phase-Roadmap

Drei Feature-Phasen aus User-Sicht. Build-Schritte sind Sub-Items innerhalb
einer Phase und in `marketdata-pipeline/README.md` detailliert nachverfolgt.

- **Phase 1 — Pipeline-Foundation** (aktuell, Build seit 2026-04-24):
  Morning-Check + 2 Scans, Output ins Workspace-Drive-Briefing-Doc.
  Gamechanger-Flag wird im CANDIDATES/GAMECHANGER-File markiert,
  keine Push-Benachrichtigung. Build-Schritte 1.0–1.5 ✅, 1.6 (Earnings-
  Kalender + BaFin-Insider-Scrape) noch offen.

- **Phase 2 — Push-Notifications** (geplant, ab ~4–6 Wochen nach Phase-1-
  Stabilität): Echte Push-Mail via Resend bei Gamechanger-Kriterien
  (G1 Portfolio-Treffer / G2 Watchlist-Trigger / G3 Makro-Schock).

- **Phase 3 — Krypto-Integration** (geplant): Paralleles Krypto-Briefing
  mit `krypto-grid-trading` und `krypto-portfolio` Skills, Pipeline-Anbindung
  für Krypto-Setup-Filter.

> **Hinweis zur Nomenklatur:** Der `derivate-trading`-Skill referenziert
> intern „Phase 4" (V1.6-Routinen lesen Pipeline) und „Phase 5" (Auto-Load).
> Das sind die Build-Schritte 1.4 und 1.5 dieser Roadmap. Skill-Sprachgebrauch
> bleibt aus historischen Gründen erhalten — neue Doku verwendet das Schema
> hier.

## Sicherheit

- Repo ist privat, nur Matthias + Claude Code haben Zugriff.
- Keine API-Keys oder Passwörter im Repo — alles über Claude Code
  Cloud-Environment-Variables.
- Branch-Protection: Claude pushed per Default nur auf `claude/*`-Branches.

## Stand

- **Phase 1 Build**: 2026-04-24 gestartet, Build-Schritte 1.0–1.5 ✅ am 2026-04-26
- **Erste scharfe Routine**: ab Mo 2026-04-27 08:45 CET
- **Filename-Schema** (seit 2026-04-26): `MARKETDATA-FULL-STD-…` und `MARKETDATA-FULL-GC-…` mit Universum-Tag
- **Skill-Version**: 1.x (aktuelle Entwicklungsversion, Iterationen laufen)
