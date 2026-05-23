# Roadmap — Pipeline-Erweiterungen

Lebendes Dokument für Pipeline-Erweiterungen, die nach dem aktuellen Stand
noch nicht implementiert sind. Stand: 2026-05-23.

## Status-Übersicht

| Phase | Inhalt | Status |
|---|---|---|
| Anomaly-Layer V1 | Gap, Volumen-Z, ATR-Z, NR7 | ✅ Erledigt (2026-05-15, Note #50) |
| Anomaly-Layer V1.1 | Intraday-Guard (VOL-Z/NR7), Index/FX/Crypto-Filter | ✅ Erledigt (2026-05-15, Note #50.1) |
| Anomaly-Layer V1.2 | Ex-Dividende-Anreicherung (Breakdown-False-Positive-Filter) | ✅ Erledigt (2026-05-23, Note #67) |
| Anomaly-Layer V2 | Peer-Divergenz | 🔜 Geplant |
| Anomaly-Layer V3 | News-Kurs-Mismatch, Correlation-Breakdown | 💭 Idee |

---

## V2: Peer-Divergenz (geplant)

### Ziel

Aktien identifizieren, die sich entgegen ihres Sektors/ihrer Peer-Group
bewegen. Beispiel: Sektor +1,0%, Aktie −4,5% → individuelle Story, hohes
Erklärungsbedürfnis, oft Vorbote von News/Insider-Aktivität.

### Mechanik (Skizze)

1. **Peer-Mapping pro Ticker**:
   - Basis-Layer: `yfinance.Ticker(sym).info["sector"]` + `info["industry"]`
     für die ~300 Tickern in Tier-A/B-Universum automatisch laden.
   - Caching in YAML-Datei (`config/peer_mapping.yaml`), Refresh wöchentlich.
   - Manuelle Korrektur-Schicht für Sonderfälle (Konglomerate, Rüstungsmix etc.):
     ~30-50 Einträge erwartet.

2. **Peer-Group-Performance**:
   - Pro Ticker: rolling Median des Tagesreturns aller Peers derselben
     Industry (Fallback: Sector) der letzten 5 HT.

3. **Divergenz-Score**:
   - `divergence_pct = ticker_return_5d - peer_median_return_5d`
   - Flag bei |divergence| ≥ 5% (Schwelle empirisch zu kalibrieren).

### Open Questions

- Mindest-Anzahl Peers pro Group (sonst Median instabil) — Vorschlag: ≥5.
- Was tun bei Mini-Sektoren (z.B. einige SDAX-Cluster mit nur 2-3 Vertretern)?
  Fallback auf Sector-Median, sonst Flag deaktivieren.
- Index-Konstituenten (DAX, MDAX) als Zusatz-Peer-Layer? Eher nicht, würde
  Sektor-Information verwässern.

### Aufwand-Schätzung

- Peer-Mapping-Aufbau: ~3-4h (Code + manuelle Korrekturen).
- Code (Rolling-Returns, Divergenz-Berechnung, Renderer): ~3-4h.
- Tests: ~1-2h.
- **Gesamt: ~8-10h**, eine konzentrierte Pipeline-Session.

---

## V3-Ideen (nicht priorisiert)

### News-Kurs-Mismatch

Adhoc-Scanner findet News, market_data hat Snapshots — bisher nicht gekreuzt.
Mismatch-Cases sind aufschlussreich:

- News klassifiziert (Gewinnwarnung etc.), aber Kurs reagiert nicht
  (Markt hatte es eingepreist oder Glaubwürdigkeit gering).
- Großer Kurs-Move ohne klassifizierte News (jemand weiß etwas, was die
  RSS-Feeds noch nicht haben).

Architektur-Eingriff: zwei Workflows verknüpfen. Mittlerer Aufwand.

### Correlation-Breakdown zum Index

Wenn die 30-Tage-Korrelation einer Aktie zum DAX/MDAX plötzlich von z.B.
0,8 auf 0,2 bricht, ist das Vorbote individueller Stories. Erfordert
rolling Correl-Berechnung, aber kein Peer-Mapping.

### Multi-Day-Akkumulation

Erhöhtes Volumen über 3-5 Tage ohne nennenswerte Kursbewegung = stille
Akkumulation/Distribution. Im aktuellen Volumen-Z-Score nicht abgebildet,
weil der nur den letzten Tag isoliert betrachtet.

---

## Erledigte Phasen

### Anomaly-Layer V1 (2026-05-15, Note #50)

Vier statistische Detektoren oberhalb der bestehenden schwellenwert-basierten
Bucket-Filter:

| Detektor | Mechanik | Schwelle |
|---|---|---|
| `gap_pct` | (today_open − prev_close) / prev_close | ±2,0% (Anomalie), ±5,0% (Extreme) |
| `atr_zscore_60d` | Z-Score ATR-14 vs. 60-HT-Baseline | \|Z\| ≥ 2,0 |
| `volume_zscore_60d` | Z-Score log(Volumen) vs. 60-HT-Baseline | \|Z\| ≥ 2,0 |
| `nr7` | True-Range heute = niedrigste der letzten 7 HT | bool |

Output: Eigene `⚡ ANOMALY-FLAGS`-Sektion oben in CANDIDATES und
GAMECHANGER-HUNT, plus `Anomalies:`-Zeile pro Ticker in MARKETDATA-FULL
(nur bei aktiven Flags). Schwellen als Modul-Konstanten in `market_data.py`
(`ANOMALY_*`-Prefix) hinterlegt — Kalibrierung nach ersten 2-4 Wochen Live-
Beobachtung empfohlen.

Tests: `tests/test_anomaly_flags.py` mit 19 Testfällen (Edge Cases:
unzureichende History, 0-Volumen, Mehrfach-Anomalien, Sortier-Reihenfolge).

### Anomaly-Layer V1.2 — Ex-Dividende-Anreicherung (2026-05-23, Note #67)

Schließt eine Lücke des V1-Layers: ein −3% bis −10%-Tag in der HV-Saison wurde
ohne Ex-Dividende-Kontext fälschlich als Breakdown-Signal klassifiziert.
Auslöser war HEI.DE am 15.05.2026 — ein −7,16%-Ex-Tag, als Breakdown-Short
gemeldet, obwohl der Drop überwiegend buchhalterischer Effekt war.

Vier neue `TickerSnapshot`-Felder: `last_ex_div_date`, `last_ex_div_days_ago`
(exakte Handelstage aus der df-Index-Position), `last_ex_div_amount`,
`next_ex_div_date` (geschätzt aus der Auszahlungs-Kadenz, ≈91/182/365 Tage).

Abweichung von der ursprünglichen Patch-Skizze: statt eines Pro-Symbol-
`.actions`-Calls hinter einem ENV-Flag wird der bestehende Batch-Download mit
`actions=True` aufgerufen — die `Dividends`-Spalte kommt ohne einen einzigen
Extra-Call mit. Damit entfällt der Rate-Limit-Grund für ein Opt-in-Flag; die
Anreicherung läuft auf allen Tiers ohne zusätzliche Yahoo-Last.

Breakdown-Detector: `_check_bucket` überspringt `breakdown_short`-Kandidaten
mit `last_ex_div_days_ago ≤ 2`. Output: `Ex-Div:`-Zeile pro Ticker in
MARKETDATA-FULL plus `⚠️ EX-DIVIDENDE kürzlich`-Sektion in CANDIDATES /
GAMECHANGER-HUNT für Ex-Tage ≤ 7 HT.

Tests: `tests/test_ex_dividend.py`.
