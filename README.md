# Derivate-Trading-Automatisierung

Pipeline, Zustand und Routinen fuer das Derivate-Trading (KO-Zertifikate /
Turbos auf DAX-Familie, EU- und US-Einzelwerte).

| Ordner | Inhalt |
|---|---|
| `marketdata-pipeline/` | Die Pipeline: yfinance-Pull, zweistufiger Filter, Digest, Scanner, Tests. **Kanonische Doku: [`marketdata-pipeline/README.md`](marketdata-pipeline/README.md)**, Architektur in [`marketdata-pipeline/docs/architecture.md`](marketdata-pipeline/docs/architecture.md). |
| `marketdata-pipeline/state/` | Operativer Zustand (Workflow B, seit 2026-10-04): `watchlist.yaml`, `radar.yaml`, `thesen.yaml`, `notes.jsonl`, `inbox_processed.json`. Aenderungen per Commit oder INBOX-Aktion. |
| `.github/workflows/` | GitHub Actions (alle `workflow_dispatch`, getriggert von cron-job.org). |
| `routines/` | Prompts der Scan-Routinen. Der Morning Check lebt im Skill `derivate-trading` (Routine 7), nicht mehr hier. |
| `PATCH_NOTES_*.md`, `ROADMAP*.md` | Aenderungshistorie und Planung. Juengster Stand: [`PATCH_NOTES_20261004_review.md`](PATCH_NOTES_20261004_review.md). |

Bis 2026-10-04 war diese Datei eine Byte-Kopie von `marketdata-pipeline/README.md`;
die Kopie ist gestrichen, damit es nur noch eine Stelle gibt, die veralten kann.
