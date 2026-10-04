# Morning Check — dieser Prompt ist ABGELOEST

Stand 2026-10-04 (System-Review). Die hier bis V1.5 gepflegte Fassung
(Markdown-File-Pattern, Content-Limit 1500) ist seit Monaten nicht mehr die
Fassung, die laeuft. Der Morning Check ist Routine 7 im Skill
`derivate-trading` (`references/routine-7.md`, ab Skill v49) und wird dort
gepflegt — eine Kopie an dieser Stelle wuerde nur wieder auseinanderlaufen.

Was der Morning Check seit v49 liest:
- `BRIEFING-DIGEST-*.json` (Schema `briefing-digest/v4`) aus dem Briefing-Ordner,
  inkl. Block `state` (Watchlist-Meta, Termin-Radar-Fenster, Thesen).
- Keine Journal-Uploads mehr fuer Watchlist/Radar: Quelle ist
  `marketdata-pipeline/state/*.yaml`.

Was er schreibt:
- Das Briefing (6 Bloecke: Kopfzeile/Health · 🔴 Handeln heute · 🟢 Einstiegs-
  kandidaten (max 3) · 📍 Offene Positionen · 🧭 Thesen & Termine · 🧹 Wartung ·
  🎯 Trader-Tops).
- Optional eine `INBOX-morning-check-<stamp>.json` mit typisierten Aktionen,
  die `inbox_apply.yml` auf den Zustand anwendet.

Die Scan-Prompts 15:45 / 20:30 in diesem Ordner sind davon nicht betroffen.
