#!/usr/bin/env python3
"""
inbox_apply.py — INBOX-JSON-Aktionen auf state/*.yaml anwenden (Workflow B).

Bis zum System-Review 2026-10-04 schrieben die automatischen Laeufe (Thesen-
Lauf, Termin-Radar-Pflege, Dividenden-Scan) nur Markdown-Briefe in den
Briefing-Ordner. Der Mensch hat sie im Morning Check gelesen und von Hand ins
Journal uebertragen — oder nicht. Jetzt liefern dieselben Laeufe zusaetzlich
eine typisierte Aktionsliste (``INBOX-<quelle>-<stamp>.json``, Vertrag in
``state_yaml.py``), und dieses Skript wendet sie an:

    INBOX-JSON (Drive oder lokal)  ->  apply_actions  ->  state/*.yaml  ->  commit

Idempotenz:
  * Jede Datei wird genau einmal angewendet; der Schluessel ist die Drive-
    File-ID bzw. lokal ``name:sha256[:12]``. Das Register liegt in
    ``state/inbox_processed.json`` und wandert mit dem Commit.
  * Jede einzelne Aktion ist in sich idempotent (siehe state_yaml). Ein
    zweiter Lauf ueber dieselbe Datei aendert nichts.
  * Eine unbekannte oder kaputte Aktion wird protokolliert und uebersprungen,
    kippt den Lauf aber nicht. Nur eine unlesbare Datei (kein JSON, falsches
    Schema) wird als ``fehler`` registriert, damit sie nicht bei jedem Lauf
    erneut probiert wird.

Aufrufe:
    python src/inbox_apply.py --inbox-dir ./inbox --state-dir ./state --today 2026-10-05
    python src/inbox_apply.py --drive                 # liest INBOX-*.json aus BRIEFING_FOLDER_ID
    python src/inbox_apply.py --drive --dry-run       # nur zeigen, nichts schreiben

Der Commit selbst passiert in .github/workflows/inbox_apply.yml (git add state
&& git commit), nicht hier — damit das Skript auch lokal und in Tests ohne
Git laeuft.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

import state_yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("inbox_apply")

INBOX_PREFIX = "INBOX-"
INBOX_SCHEMA = 1
ALLOWED_SOURCES = {
    "thesen-lauf", "termin-radar", "dividenden-scan", "morning-check",
    "insider-us", "catalyst-calendar", "manuell", "test",
}


# ---------------------------------------------------------------------------
# Eingang: lokale Dateien oder Drive
# ---------------------------------------------------------------------------

class InboxItem:
    def __init__(self, key: str, name: str, payload: Optional[dict], error: Optional[str] = None):
        self.key = key          # eindeutig je Datei (Drive-ID oder name:sha)
        self.name = name
        self.payload = payload
        self.error = error


def _parse_payload(raw: bytes, name: str) -> tuple[Optional[dict], Optional[str]]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"kein gueltiges JSON: {exc}"
    if not isinstance(data, dict):
        return None, "Wurzel ist kein Objekt"
    if data.get("schema") != INBOX_SCHEMA:
        return None, f"schema={data.get('schema')!r}, erwartet {INBOX_SCHEMA}"
    if not isinstance(data.get("actions"), list):
        return None, "Feld 'actions' fehlt oder ist keine Liste"
    src = str(data.get("source", "")).lower()
    if src and src not in ALLOWED_SOURCES:
        logger.warning(f"{name}: unbekannte Quelle {src!r} — wird trotzdem angewendet")
    return data, None


def iter_local_inbox(inbox_dir: Path) -> Iterable[InboxItem]:
    if not inbox_dir.exists():
        return
    for p in sorted(inbox_dir.glob(f"{INBOX_PREFIX}*.json")):
        raw = p.read_bytes()
        key = f"{p.name}:{hashlib.sha256(raw).hexdigest()[:12]}"
        payload, err = _parse_payload(raw, p.name)
        yield InboxItem(key, p.name, payload, err)


def iter_drive_inbox(drive_service, folder_id: str) -> Iterable[InboxItem]:
    from drive_writer import download_file_bytes, list_files_by_prefix
    for f in list_files_by_prefix(drive_service, folder_id, INBOX_PREFIX):
        if not f["name"].lower().endswith(".json"):
            continue
        raw = download_file_bytes(drive_service, f["id"])
        payload, err = _parse_payload(raw, f["name"])
        yield InboxItem(f["id"], f["name"], payload, err)


# ---------------------------------------------------------------------------
# Kern: anwenden + Register fuehren
# ---------------------------------------------------------------------------

def apply_inbox(
    state_dir: Path,
    items: Iterable[InboxItem],
    today: Optional[date] = None,
    dry_run: bool = False,
) -> dict:
    """Wendet alle noch nicht verarbeiteten Items an. Gibt einen Report zurueck.

    Report: {"applied": [name...], "skipped": [name...], "failed": [name...],
             "log": [zeilen...], "changed": bool}
    """
    today = today or date.today()
    state = state_yaml.load_state(state_dir)
    processed = state_yaml.load_processed(state_dir)
    report = {"applied": [], "skipped": [], "failed": [], "log": [], "changed": False}

    for item in items:
        if item.key in processed:
            report["skipped"].append(item.name)
            continue
        if item.error:
            report["failed"].append(item.name)
            report["log"].append(f"⚠️ {item.name}: {item.error}")
            processed[item.key] = {
                "name": item.name, "status": "fehler", "error": item.error,
                "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            continue

        actions = item.payload.get("actions", [])
        source = item.payload.get("source", "?")
        for a in actions:
            a.setdefault("source", source)
        log = state_yaml.apply_actions(state, actions, today=today)
        verworfen = sum(1 for l in log if l.startswith("⚠️"))
        report["applied"].append(item.name)
        report["log"].append(f"▶ {item.name} ({source}): {len(actions)} Aktionen, {verworfen} verworfen")
        report["log"].extend(f"   {l}" for l in log)
        processed[item.key] = {
            "name": item.name, "status": "ok", "source": source,
            "actions": len(actions), "verworfen": verworfen,
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        report["changed"] = True

    if dry_run:
        report["log"].append("(dry-run: nichts geschrieben)")
        return report

    if report["changed"] or report["failed"]:
        notes = state.pop("_notes", [])
        if report["changed"]:
            state_yaml.save_state(state_dir, state)
            state_yaml.append_notes(state_dir, notes)
        state_yaml.save_processed(state_dir, processed)
    return report


def render_report(report: dict) -> str:
    lines = [
        f"# INBOX-Apply {datetime.now().astimezone().isoformat(timespec='minutes')}",
        "",
        f"- angewendet: {len(report['applied'])}  "
        f"- uebersprungen (bereits verarbeitet): {len(report['skipped'])}  "
        f"- fehlerhaft: {len(report['failed'])}",
        "",
    ]
    lines.extend(report["log"] or ["(keine neuen INBOX-Dateien)"])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state-dir", default=os.environ.get("STATE_DIR", "./state"))
    ap.add_argument("--inbox-dir", default=os.environ.get("INBOX_DIR"),
                    help="lokaler Ordner mit INBOX-*.json (Tests, Handbetrieb)")
    ap.add_argument("--drive", action="store_true",
                    help="INBOX-*.json aus Drive lesen (GDRIVE_SA_KEY + INBOX_FOLDER_ID/BRIEFING_FOLDER_ID)")
    ap.add_argument("--today", default=None, help="ISO-Datum fuer Zeitstempel (Default: heute)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    today = date.fromisoformat(args.today) if args.today else date.today()
    state_dir = Path(args.state_dir)
    items: list[InboxItem] = []

    if args.inbox_dir:
        items.extend(iter_local_inbox(Path(args.inbox_dir)))
    if args.drive:
        from drive_writer import build_drive_service
        folder = os.environ.get("INBOX_FOLDER_ID") or os.environ.get("BRIEFING_FOLDER_ID")
        if not folder:
            logger.error("--drive braucht INBOX_FOLDER_ID oder BRIEFING_FOLDER_ID")
            return 2
        svc = build_drive_service()
        items.extend(iter_drive_inbox(svc, folder))
    if not args.inbox_dir and not args.drive:
        logger.error("Weder --inbox-dir noch --drive angegeben.")
        return 2

    report = apply_inbox(state_dir, items, today=today, dry_run=args.dry_run)
    text = render_report(report)
    print(text)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    # Fuer den Workflow: Exit 0 immer, Aenderung ueber Output-Datei signalisieren
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"changed={'true' if (report['changed'] or report['failed']) else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
