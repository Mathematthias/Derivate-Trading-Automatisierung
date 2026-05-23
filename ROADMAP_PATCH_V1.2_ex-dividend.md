# ROADMAP Patch — V1.2 Ex-Dividende-Anreicherung

**Erstellt:** 2026-05-17
**Anlass:** HEI.DE-Lehre (Watchlist-Eintrag 17.05.2026 als Breakdown-Short auf -7,16% am 15.05. — der Drop war Ex-Dividende-Effekt, nicht realer Verkaufsdruck; Setup tot, Eintrag direkt archiviert)
**Referenz:** Skill-Note #67, Lektion 16

Anweisung an mich selbst (Mathematthias): Diesen Patch als neuen Abschnitt in `ROADMAP.md` im Repo-Root einfügen, **zwischen V1.1 (Anomaly Layer, abgeschlossen) und V2 (Peer Divergence Detector, geplant)**. Wenn V1.2 implementiert ist, den Abschnitt mit Status-Tag „✅ DONE" markieren.

---

## V1.2 — Ex-Dividende-Anreicherung (Anomaly-Layer-Patch)

**Status:** ✅ DONE (2026-05-23)
**Aufwand-Schätzung:** ~2-3h
**Priorität:** Mittel — verhindert konkrete False-Positives bei Breakdown-Short-Erkennung

### Problem

Aktueller Anomaly-Layer V1.1 erkennt `gap_pct`, `atr_zscore_60d`, `volume_zscore_60d`, `nr7` — alle ohne Kenntnis darüber, ob ein Tagesverlust ein **Ex-Dividende-Effekt** ist. Konsequenz: ein -3% bis -10%-Tag in der HV-Saison (April–Juli für DE/EU, Q1+Q4 für US) wird fälschlich als Breakdown-Signal klassifiziert, obwohl der Drop kein realer Verkaufsdruck ist.

Konkreter False-Positive-Fall: HEI.DE 15.05.2026 — Pipeline meldete -7,16% bei Vol 1,89× Avg-20d als Breakdown-Short-Kandidat. Tatsächlich war der Tag Ex-Dividende-Tag, der Drop überwiegend buchhalterischer Effekt.

### Lösung

Jedes Symbol bekommt im MARKETDATA-FULL.md-Output zwei neue Felder:

```
- **Ex-Div:** Last=2026-05-15 (2d ago, Betrag 4,00€) · Next=2027-05-14 (geschätzt)
```

oder bei keinem aktuellen Ex-Tag:

```
- **Ex-Div:** Last=2025-05-23 (358d ago) · Next=unbekannt
```

### Implementierung (Skizze)

**Datenquelle:** `yfinance.Ticker(symbol).actions` oder `.dividends` Property — liefert historische Bardividenden mit Datum. Aus den letzten ~5 Einträgen ableiten:
- letzter Ex-Tag-Datum + Tagesabstand zu heute
- letzter Bardividenden-Betrag in Symbol-Währung
- nächster geschätzter Ex-Tag (= letzter Ex-Tag + ca. 365 Tage als Standard-Annahme bei jährlicher Auszahlung; bei Quartals-Dividende: + 91 Tage)

**Code-Stelle:** `pipeline/anomaly_detectors.py` (oder wo der MarketData-Render lebt) — neue Funktion `enrich_ex_dividend(symbol_data)`, die im normalen Render-Pfad nach den EMAs aufgerufen wird.

**Pre-Filter-Logik im Breakdown-Detector:**

```python
def detect_breakdown_short(symbol_data):
    # Pflicht-Check Ex-Tag rückwärts (Skill-Note #67, Lektion 16)
    if symbol_data.get('last_ex_div_days_ago', 999) <= 2:
        # Ex-Tag liegt 0-2 Tage zurück → Drop ist Ex-Effekt, kein Breakdown
        return None
    # ... bestehende Breakdown-Logik
```

Cutoff von 2 Tagen ist konservativ — bei reinen Ex-Tag-Drops ist die Bewegung am Tag selbst und ggf. Tag +1 (Catch-up-Käufer / Arbitrage-Schließung).

### Akzeptanzkriterien

- [x] Alle Tier-B- und Tier-A-Ticker liefern `last_ex_div_days_ago` und `last_ex_div_amount` im MARKETDATA-Output
- [x] Breakdown-Detector skippt Kandidaten mit `last_ex_div_days_ago ≤ 2`
- [x] Tests: Synthetic-Fall HEI.DE 15.05.2026 wird NICHT als Breakdown-Short gemeldet
- [x] CANDIDATES.md-Output zeigt Ex-Div-Info inline bei Kandidaten, falls Tag relevant (≤ 7 HT alt)
- [x] V1.1-Tests bleiben grün

### Umsetzungs-Notiz (2026-05-23) — Abweichung von der Skizze

Statt der oben skizzierten Pro-Symbol-`.actions`-Calls hinter einem ENV-Flag
wird der bestehende Batch-Download (`fetch_ticker_data`) mit `actions=True`
aufgerufen. Die `Dividends`-Spalte kommt damit im selben Pull mit — **null
zusätzliche Yahoo-Calls**. Der im Patch genannte Call-Budget-Grund für ein
Opt-in-Flag entfällt damit; die Anreicherung läuft ohne Flag auf allen Tiers.
`last_ex_div_days_ago` zählt exakte Handelstage (df-Index-Positionsdifferenz),
nicht Kalendertage. Implementiert in `market_data.py`
(`_compute_ex_dividend_fields`), `output_renderer.py` (MARKETDATA-FULL-Zeile +
`EX-DIVIDENDE kürzlich`-Sektion), `filter_engine.py` (`_check_bucket`-Skip).

### Nicht-Ziele für V1.2

- Erweiterung auf Sonderausschüttungen / Kapitalherabsetzungen / Spin-offs — V1.3 oder später
- Forward-Looking Ex-Tag-Block für Long-Setups — bereits in Skill-Note #64 für Shorts kodifiziert, aber nicht in Pipeline; ggf. V1.3
- Cluster-Ex-Tag-Erkennung (mehrere DAX-Werte am gleichen Tag ex) — nicht relevant für Setup-Filter

### Cross-Refs

- Skill: `SKILL.md` § Pre-Filter Ex-Tag rückwärts (Note #67, Lektion 16)
- Existing-Logik forward: Skill Note #64 (Ex-Div bei Short-Setups = harter Block in ≤ 5 HT)
