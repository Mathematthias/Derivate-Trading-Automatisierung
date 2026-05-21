# Watchlist-Archiv

> **Zweck:** Lern-History aller archivierten Watchlist-Einträge.
>
> **Beziehung zum STATE-Doc:** STATE führt die *aktive* Watchlist (was du
> gerade beobachtest). Dieses Doc führt die *toten* Einträge (was nicht mehr
> aktiv ist) — mit Grund und kurzer Notiz.
>
> **Pipeline-Verhalten:** Die Pipeline liest dieses Doc NICHT. Es ist reine
> Lern-History für deine eigene Reflexion.
>
> **Setup:** Diese Vorlage einmalig als neues Google Doc namens
> `WATCHLIST-ARCHIV` im selben Drive-Ordner wie das STATE-Doc anlegen.
> Inhalt 1:1 hier rein kopieren, Archiv-Tabelle wird mit der Zeit gefüllt.

## Archivierungs-Gründe (Definition)

- **✅ gelaufen** — Setup ist eingetreten. Trade gemacht (Journal #X) ODER
  verpasst. Beim Verpassen: 1 Satz "warum verpasst" — das ist Lektion.
- **❌ These geplatzt** — Fundamentaler Grund weggebrochen
  (Earnings-Miss, Skandal, Wettbewerber, regulatorisch).
- **📉 Chart bestätigt nicht** — Setup-Vorbedingung gebrochen
  (Trend gekippt, EMA-Stack zerlegt, ATH-Knack ohne Volumen → Bullenfalle).

## Workflow Archivierung

Wenn ein Eintrag in der aktiven Watchlist (STATE Sektion 2) tot ist:

1. Zeile aus aktiver Watchlist im STATE entfernen.
2. Neue Zeile in Tabelle unten anhängen.
3. Datum im ISO-Format YYYY-MM-DD.
4. Notiz: 1-2 Sätze, kein Roman. Was war die These, was ist passiert.

## Archiv-Tabelle

| Datum | Kandidat | Symbol | Richtung | Grund | Notiz |
|-------|----------|--------|----------|-------|-------|
| (initial leer — füllt sich mit der Zeit) | | | | | |

## Quartalsweise Reflexion

Alle 3 Monate: Tabelle durchsehen, nach Grund gruppieren.
Übergewicht eines Grundes deutet auf systemische Schwäche:

| Pattern | Vermutung | Was anpassen |
|---------|-----------|--------------|
| 80% ✅ aber meist verpasst | Pipeline-Sync zu langsam, Reaktionszeit zu kurz | Sync-Frequenz hoch, Routinen-Schedule prüfen |
| 80% ❌ These geplatzt | Watchlist zu News-getrieben | Fundamentaler Pre-Filter beim Aufnehmen |
| 80% 📉 Chart-not | Trigger zu naiv definiert | Mehr Indikator-Schichten bei Setup-Spezifikation |
| Mix mit Häufung bei einem Sektor | Sektor-Bias / Korrelations-Cluster | Watchlist-Diversifikation prüfen |

## Statistik-Snapshot (optional, manuell pro Quartal)

```
Q2 2026 (April-Juni):
  Archivierte Einträge: __
  davon ✅ gelaufen:    __  (% des Total)
    - getradet:         __
    - verpasst:         __
  davon ❌ These:       __
  davon 📉 Chart:       __

  Wichtigste Lektion: ____________________
```
