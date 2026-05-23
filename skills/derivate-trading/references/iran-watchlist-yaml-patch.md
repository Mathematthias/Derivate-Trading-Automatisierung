# Pipeline-YAML-Patch — Iran-Watchlist + XAD5

**Zweck:** Anleitung für Pipeline-Maintenance, um die heutigen Iran-/Geopol-Watchlist-Erweiterungen produktiv zu machen.

**Stand:** Skizze, ausstehender Patch-Termin TBD. Skill und Excel sind bereits angepasst (06.05.2026); ohne YAML-Patch fehlt die MARKETDATA-Versorgung für die neuen Symbole — Pipeline-Trigger-Status bleibt für sie inaktiv.

**Note-Verweis:** Notes-Sheet im Trading-Journal, ID #30 (TODO).

---

## Was patchen

Datei `tickers_tier_a.yaml` (im Pipeline-Repo, GitHub-Action-Runner).
Standard-Universum erweitern um folgende Yahoo-Ticker.

### 12 neue Iran-Watchlist-Symbole

```yaml
# A1 — Energie & Rohstoffe
- TTE.PA       # TotalEnergies (EUR-direkt)
- EQNR.OL      # Equinor (NOK-Underlying)
- SHEL.L       # Shell (GBP-Underlying)

# A2 — Cybersecurity (Sub-Cluster MAX 1 parallel offen)
- CRWD         # CrowdStrike (USD)
- PANW         # Palo Alto Networks (USD)

# A3 — Logistik Air
- FDX          # FedEx (USD)

# A4 — Defensive / Vola-Profiteur
- MUV2.DE      # Münchener Rück (EUR-direkt)

# A5 — Dünger
- CF           # CF Industries (USD)
- OCI.AS       # OCI Global (EUR-direkt)
- SDF.DE       # K+S (EUR-direkt)

# B2 — Stahl/Chemie energie-intensiv
- BAS.DE       # BASF (EUR-direkt)
- TKA.DE       # ThyssenKrupp (EUR-direkt)
```

### XAD5 (Position-#39-Fix)

```yaml
# Position #39 — XAD5 ersetzt 4GLD-Mapping
- XAD5.DE      # Xtrackers Physical Gold ETC EUR (DE000A1E0HR8)
               # Falls XAD5.DE keine yfinance-Daten liefert: XAD5.MI als Fallback
```

**Hinweis:** `4GLD.DE` (Xetra-Gold) NICHT entfernen — sie kann als Cross-Reference im Briefing weiter nützlich sein. Die TICKER-MAP-Korrektur im STATE-Doc erfolgt separat (siehe `STATE_Doc_Patches_2026-05-06.md`, Patch 2).

---

## Größenwirkung

Vorher: ~47 Standard-Universum-Ticker.
Nach Patch: ~60 Standard-Universum-Ticker (+13).

Akzeptabel:
- Tier-A-Lauf alle 30 Min, yfinance-Calls skalieren linear
- 60 Ticker × bisheriger Latenz pro Call = leichte Pipeline-Verlangsamung, aber im Toleranzbereich
- MARKETDATA-FULL-STD-Filegröße steigt von ~18 KB auf ~22-23 KB — unkritisch

---

## Pre-Test-Empfehlung

Bevor Live-Push:

1. **Yahoo-Verfügbarkeit prüfen** für alle 13 Symbole:
   ```python
   import yfinance as yf
   for t in ['TTE.PA', 'EQNR.OL', 'SHEL.L', 'CRWD', 'PANW', 'FDX',
             'MUV2.DE', 'CF', 'OCI.AS', 'SDF.DE', 'BAS.DE', 'TKA.DE',
             'XAD5.DE']:
       try:
           hist = yf.Ticker(t).history(period='5d')
           print(f"{t:10} → {len(hist)} Bars, last close {hist['Close'].iloc[-1]:.2f}")
       except Exception as e:
           print(f"{t:10} → ERR {e}")
   ```
2. **Bei XAD5.DE Datenausfall:** auf XAD5.MI umschwenken — TICKER-MAP-Patch im STATE-Doc dann ebenfalls auf XAD5.MI anpassen.
3. **Bei OCI.AS Datenausfall:** Gettex-Liquidität war ohnehin als unsicher markiert; ggf. ganz aus der Hauptwatchlist entfernen und nur in `Iran-Universum`-Pool belassen.

---

## Geopol-Status-Tag-Erweiterung (separater, größerer Patch)

Der eigentliche Mehrwert kommt erst, wenn die Pipeline die `Geopolitics-Phase`-Sektion aus dem STATE-Doc liest und `geopol_status`-Tags in CANDIDATES/GAMECHANGER setzt:

- `🔥 confluent` — Setup + aktuelle Phase = Rückenwind (z.B. A1-Long bei `phase=acute` und Brent > esc_threshold)
- `🌊 counter-trend` — Setup widerspricht aktueller Phase (z.B. B-Short bei `phase=cooling`)
- `—` — neutral oder phase=neutral

**Implementierung:** Generator-Code von `marketdata_sync.py` (oder dem CANDIDATES-/GAMECHANGER-Generator) muss STATE-Doc-Sektion 6 parsen. Sub-Cluster-Regel A2-Cyber (max 1 von {CRWD, PANW, FTNT, ZS, NET, CHKP}) muss ebenfalls implementiert werden — gehört aber eher in die Pre-Trade-Plan-Logik (siehe `references/trade-plan-templates.md`, Counter-These-Liste) als in die Pipeline-Outputs.

**Reihenfolge empfohlen:**
1. Erst Symbol-Patch (oben) — schafft MARKETDATA-Grundlage.
2. Dann Geopol-Status-Tag-Patch — wertet die Symbole nach Bucket aus.

Schritt 2 ist nicht zeitkritisch; Schritt 1 ist der Engpass, der die Iran-Watchlist erst nutzbar macht.

---

## Pretest-Ergebnis 2026-05-06 13:50

Pretest-Script aus Sektion „Pre-Test-Empfehlung" wurde lokal ausgeführt (Sandbox-Allowlist erlaubt keinen Yahoo-Zugriff, daher Lokallauf). Alle 13 Symbole liefern saubere 5-Bar-Historien:

| Bucket | Ticker | Last Close | Status |
|---|---|---|---|
| A1 | TTE.PA | 76,02 € | ok |
| A1 | EQNR.OL | 350,20 NOK | ok |
| A1 | SHEL.L | 3192,00 **GBp** | ok ⚠️ Pence-Flag |
| A2 | CRWD | 476,53 USD | ok |
| A2 | PANW | 183,98 USD | ok |
| A3 | FDX | 362,75 USD | ok |
| A4 | MUV2.DE | 521,80 € | ok |
| A5 | CF | 128,04 USD | ok |
| A5 | OCI.AS | 3,67 € | ok |
| A5 | SDF.DE | 15,41 € | ok |
| B2 | BAS.DE | 51,53 € | ok |
| B2 | TKA.DE | 11,11 € | ok |
| #39 | XAD5.DE | 381,60 € | **bestätigt** |
| – | XAD5.MI | 382,22 € | nur Vergleich |

**XAD5-Entscheidung:** XAD5.DE wird beibehalten. Spread XAD5.DE ↔ XAD5.MI nur 0,16 % — kein liquiditäts-/abdeckungsbasierter Grund für Wechsel. Xetra-Listing in EUR konsistent zum SB+/Gettex-Routing. TICKER-MAP-Patch im STATE-Doc bleibt wie heute eingefügt.

**OCI.AS-Entscheidung:** Datenversorgung über Yahoo ist da (3,67 € Last Close). Gettex-Liquidität bleibt der separat zu prüfende Punkt vor einem realen Setup, ist aber kein Pipeline-Aufnahme-Blocker.

### ⚠️ SHEL.L Pence-Flag — Pipeline-Implementierungshinweis

Yahoo gibt für SHEL.L Werte in **Pence (GBp)**, nicht in Pound (GBP). Der `3192,00` aus dem Pretest entspricht 31,92 GBP. Wenn die MARKETDATA-Pipeline SHEL.L 1:1 als „Last Close 3192" übernimmt, sind alle nachgelagerten Berechnungen (ATR-Distanzen, KO-Abstand, R:R-Ziele, Lektion-1-v2-FX-Adjust) um Faktor 100 daneben.

**Listing-Status (recherchiert 2026-05-06):** Shell plc hat Primärlisting an der London Stock Exchange (LSE), Sekundärlistings an Euronext Amsterdam (`SHEL.AS`) und NYSE (`SHEL`). HQ und steuerlicher Sitz sind seit Januar 2022 in London (vorher Den Haag). ISIN: GB00BP6MXD84.

**Drei Implementierungs-Optionen** (vor Live-Patch zu entscheiden):

1. **Pipeline-Divisor (empfohlen):** In `tickers_tier_a.yaml` für `.L`-Suffix-Symbole einen `currency_unit: GBp` oder `price_divisor: 100` setzen, der im MARKETDATA-Generator auf den Yahoo-Close angewendet wird. Vorteil: SHEL.L bleibt Primär-Datenquelle (entspricht dem Underlying, auf dem deutsche KO-Emittenten ihre Zertifikate strukturieren) — keine Liquiditäts-/Coverage-Diskrepanz. Logik einmal sauber implementiert, gilt automatisch für alle LSE-Werte (BP.L, AZN.L, GSK.L, RIO.L, BATS.L, DGE.L). Nachteil: Eingriff in Pipeline-Code, nicht nur YAML.

2. **Symbol-Wechsel auf SHEL.AS (Sekundärlisting):** Pipeline-Daten aus Amsterdam (EUR, kein Pence-Problem) ziehen. Nachteil: SHEL.AS ist Sekundärlisting mit deutlich geringerer Liquidität als SHEL.L; mögliche Bar-Lücken. **Wichtiger:** Deutsche KO-Zertifikate auf Shell basieren typischerweise auf dem LSE-Primär-Underlying — Pipeline-Daten würden dann aus einem anderen Liquiditätspool kommen als das Zertifikats-Underlying selbst. ATR-/Trigger-Werte wären inkonsistent zur Trade-Realität.

3. **Symbol komplett ersetzen — Frankfurt/Xetra-Listing:** Falls vorhanden mit ausreichender Liquidität. Vor Patch: konkreten Xetra-Ticker recherchieren (der historische `RDSA.DE` für Royal Dutch Shell A-Aktie ist seit der Unification 2022 obsolet). Nachteil: zusätzliche Recherche, Liquidität an Xetra für UK-Aktien meist deutlich unter LSE.

**Empfehlung für den Live-Patch:** Option 1 (Pipeline-Divisor). Begründung: konsistent zum KO-Underlying, einmaliger Code-Eingriff zahlt sich für alle künftigen LSE-Werte aus, keine Liquiditätsdiskrepanz.

**Generelle Konsequenz:** UK-Listings (`.L`) sind in der Pipeline grundsätzlich Pence-Falle. Falls in Zukunft weitere LSE-Werte aufgenommen werden sollen: Pipeline-Divisor greift automatisch.
