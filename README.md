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
    ├── scan-prompt.md                  ← Prompt für 15:45 + 20:30 (parametrisiert)
    └── state-block-template.md         ← Struktur des Google-Doc STATE-Blocks
```

## Claude Code Routines Setup

Drei scheduled Routines, alle Mo–Fr, Timezone Europe/Berlin:

| Routine | Cron | Prompt-Datei | SCAN_SLOT |
|---------|------|--------------|-----------|
| `trading-morning-check` | `45 8 * * 1-5` | `routines/morning-check-prompt.md` | — |
| `trading-scan-afternoon` | `45 15 * * 1-5` | `routines/scan-prompt.md` | `15:45` |
| `trading-scan-evening` | `30 20 * * 1-5` | `routines/scan-prompt.md` | `20:30` |

Connector-Anforderung:
- **Google Drive** (Pflicht, Read+Write auf `Trading/Briefing/` Ordner)
- Gmail (optional, für Phase 2 Push-Mail bei Gamechanger)

## Phase-Roadmap

- **Phase 1** (aktuell, Build-Wochenende 2026-04-24/26):
  Morning-Check + 2 Scans, Output ausschließlich ins Google-Doc.
  Gamechanger-Flag wird im Doc markiert, keine Push-Benachrichtigung.
- **Phase 2** (geplant, ab ~4–6 Wochen nach Phase-1-Stabilität):
  Echte Push-Mail via Resend bei Gamechanger-Kriterien
  (G1 Portfolio-Treffer / G2 Watchlist-Trigger / G3 Makro-Schock).
- **Phase 3** (geplant):
  Paralleles Krypto-Briefing mit `krypto-grid-trading` und
  `krypto-portfolio` Skills.

## Sicherheit

- Repo ist privat, nur Matthias + Claude Code haben Zugriff.
- Keine API-Keys oder Passwörter im Repo — alles über Claude Code
  Cloud-Environment-Variables.
- Branch-Protection: Claude pushed per Default nur auf `claude/*`-Branches.

## Stand

- **Phase 1 Build**: 2026-04-24 gestartet
- **Erste scharfe Routine**: ab Mo 2026-04-27 08:45 CET
- **Skill-Version**: 1.x (aktuelle Entwicklungsversion, Iterationen laufen)
