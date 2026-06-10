# Routine 9 — Wochen-Research (Deep-Research auf Sektor-Thesen)

**Geladen bei:** Codewort „Wochen-Research" / „Thesen-Research" / „Research-Samstag".
**Seit:** 2026-06-10 (Paket C2). **Kein Code** — reiner Prozess + Prompt-Template.

## Zweck und Abgrenzung

Der Thesen-Engpass ist die Quellenlage, nicht die Verarbeitung (Befund Paket C).
Die täglichen Scans (Routine 8/8b/8c) sind breit und flach; diese Routine ist
schmal und tief: **1×/Woche 2–3 Sektor-/Makro-Thesen** per Research-Feature
durchleuchten. Sie ersetzt keinen Scan und keinen Pipeline-Trigger — das
Research-Ergebnis ist **Thesen-Input für die Watchlist**, kein Trade-Signal.
Einstiege laufen weiterhin über Trigger + 7/7-Checkliste.

**Default-Slot:** Samstag vormittags. Markt zu, Zeit vorhanden, Ergebnisse
liegen vorm Montags-Briefing. Wenn die Woche kein Signal-Material hergibt,
darf die Routine ersatzlos ausfallen — kein Pflichttermin.

## Ablauf (5 Schritte)

### Schritt 1 — Thesen-Kandidaten sammeln (Claude, OHNE Research-Feature)

Aus bereits vorhandenen Daten der Woche, keine neuen Web-Suchen nötig:

| Quelle | Wonach suchen |
|---|---|
| GAMECHANGER-HUNT EU/US (Wochenverlauf) | Sektoren/Ticker, die mehrfach in Setup-Buckets auftauchen (Häufung = Sektor bewegt sich) |
| ADHOC-CATALYSTS (Wochenverlauf) | Gehäufte Meldungen je Sektor (≥3 Catalysts gleicher Branche) |
| INSIDER-US + EQS-Insider | Cluster-Sektoren — auch knapp unterschwellige Häufungen |
| Offene Positionen + Watchlist | Sektoren mit bestehender Exposure (Vertiefung oder Gegencheck) |
| Makro-Kalender Folgewoche | Events mit Sektorwirkung (ECB/Fed, Rohstoff-Reports, Branchen-Earnings-Wellen) |

Output: **3–5 Thesen-Kandidaten**, je 1–2 Sätze mit Signal-Herkunft
(„Versicherer: 3× GAMECHANGER-Hits + MUV2-Position offen + Q-Zahlen-Welle KW25").

### Schritt 2 — Auswahl

User wählt **2–3** Thesen (eigene These jederzeit zulässig, schlägt Vorschläge).

### Schritt 3 — Credit-Gate (Prefs R16, Übergabe-Vorgabe)

Vor dem Start: Aufwand explizit nennen (1 Research-Lauf **pro These**, nicht
gebündelt — Bündelung verwässert die Tiefe), User nickt ab. Kein Auto-Start.

### Schritt 4 — Research-Lauf je These

Prompt-Template (Platzhalter ersetzen, Rest unverändert):

```
Sektor-These prüfen: {THESE — 1-2 Sätze, inkl. Richtung long/short}

Zeithorizont: 2-6 Wochen (Swing-Trading mit Knock-out-Zertifikaten).

Harte Constraints:
- Nur Einzelwerte, die als KO-Zertifikat bei deutschen Emittenten handelbar
  sind: EU-Large/Mid-Caps (Xetra/Euronext/SIX) und US-Large-Caps (NYSE/Nasdaq).
- Ethik-Ausschluss: keine Werte mit Angriffswaffen-Kerngeschäft (z.B.
  Rheinmetall, KNDS, BAE, Lockheed, Northrop, General Dynamics, RTX).
  Defensive Technologie nur, wenn Defense-Umsatz <30%.
- Keine Werte in EM-Währungen (TRY/ZAR/ARS/MXN/RUB/BRL).

Aufbau der Antwort:
1. These-Validierung: stärkste 3 Pro- und 3 Contra-Argumente mit Quellen
   und Datumsangaben. Explizit: Was würde die These FALSIFIZIEREN
   (konkrete, beobachtbare Kriterien)?
2. 3-5 Einzelwerte, die die These am direktesten spielen. Pro Wert:
   voller Name, Ticker, Sektor, 1-Satz-Geschäft, konkreter Katalysator
   MIT Termin (Earnings, Capital Markets Day, Zulassung, Auktion, ...),
   aktuelle Bewertungs-/Sentiment-Lage, die wichtigste Counter-These.
3. Zeitliche Struktur: Welche Katalysatoren liegen in den nächsten
   2-6 Wochen? Welche Werte sind "jetzt", welche "warten"?
4. Crowdedness-Check: Ist die These bereits Konsens (Kursreaktion gelaufen,
   Late-Entry-Risiko) oder noch unterbeachtet?
Keine Kursziele erfinden. Quellen mit Datum. Widersprüche zwischen Quellen
benennen statt glätten.
```

### Schritt 5 — Verwertung (im selben oder Folge-Chat)

1. Pro These **max. 1–2 Einzelwerte** in den 7/7-Vorcheck light (Late-Entry
   Lektion 8, Counter-These, FX/Lektion 1 v2, Ethik-Doppelcheck).
2. Übersteht ein Wert den Vorcheck und ergibt sich Trigger + SL + TP →
   **Watchlist-Frage aktiv stellen** (bestehende Regel: Setup konstruiert =
   fragen). These-Text in die These-Spalte, Verfall nach Standard
   (14 HT bzw. Event +3 HT).
3. These-Verdikt als Kurzeintrag (3–4 Zeilen) ins **Notes-Sheet, Block
   „Thesen-Log"**: Datum, These, Verdikt (spielen/beobachten/verworfen),
   Falsifikationskriterium, Re-Check-Datum (Default +4 Wochen oder Event).
   Kein neues Sheet, kein Memory-Eintrag — Notes ist Single Source of Truth.

## Leitplanken

- Research validiert Thesen, **handelt nicht**: kein Direkteinstieg aus dem
  Report, immer Pipeline-Trigger/Checkliste dazwischen.
- Quellen-Disziplin wie überall: harte Zahlen aus dem Report vor Verwendung
  in Trade-Plänen stichprobenartig gegen Primärquelle prüfen — Research
  aggregiert, erfindet aber im Zweifel Plausibles.
- Max. 3 Thesen/Woche. Mehr = wieder flach statt tief.

## Stellschrauben (Defaults, einzeilig änderbar)

| Schraube | Default | Alternative |
|---|---|---|
| Slot | Sa vormittags | So abends (näher am Montag, weniger Puffer) |
| Thesen-Anzahl | 2–3 | 1 (sehr tief) bei dünner Woche |
| Re-Check-Intervall Thesen-Log | +4 Wochen | event-basiert |
